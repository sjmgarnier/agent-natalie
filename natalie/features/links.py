"""Shared wikilink parsing and canonicalization.

Used by note_write (write-time normalization) and note_move (move-time
backlink rewriting) so both share one definition of what a wikilink is and
how it resolves to a canonical form. See openspec change
note-move-link-integrity for the design rationale (D1/D2/D3).
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import PurePosixPath

from ..utils import fts_quote

_WIKILINK_RE = re.compile(r"(!?)\[\[([^\[\]\n]+)\]\]")
_FENCE_OPEN_RE = re.compile(r"(`{3,}|~{3,})")
_TICK_RUN_RE = re.compile(r"`+")


@dataclass(frozen=True)
class WikilinkMatch:
    """A single [[...]] or ![[...]] match found in Markdown content."""

    start: int
    end: int
    is_embed: bool
    path_part: str
    heading: str | None
    block: str | None
    alias: str | None

    def canonical(self, new_path_part: str) -> str:
        """Render this match with path_part replaced, preserving suffixes."""
        if self.heading is not None:
            suffix = f"#{self.heading}"
        elif self.block is not None:
            suffix = f"^{self.block}"
        else:
            suffix = ""
        alias_suffix = f"|{self.alias}" if self.alias is not None else ""
        bang = "!" if self.is_embed else ""
        return f"{bang}[[{new_path_part}{suffix}{alias_suffix}]]"


def _split_target(inner: str) -> tuple[str, str | None, str | None, str | None]:
    """Split wikilink inner text into (path_part, heading, block, alias)."""
    target_part, sep, alias = inner.partition("|")
    alias_val = alias if sep else None

    hash_idx = target_part.find("#")
    caret_idx = target_part.find("^")
    if hash_idx != -1 and (caret_idx == -1 or hash_idx < caret_idx):
        return target_part[:hash_idx], target_part[hash_idx + 1 :], None, alias_val
    if caret_idx != -1:
        return target_part[:caret_idx], None, target_part[caret_idx + 1 :], alias_val
    return target_part, None, None, alias_val


def _fenced_code_ranges(content: str) -> list[tuple[int, int]]:
    """Return (start, end) offsets of fenced code blocks (``` or ~~~)."""
    ranges: list[tuple[int, int]] = []
    offset = 0
    open_fence: str | None = None
    open_start = 0
    for line in content.splitlines(keepends=True):
        stripped = line.lstrip(" \t")
        if open_fence is None:
            m = _FENCE_OPEN_RE.match(stripped)
            if m:
                open_fence = m.group(1)
                open_start = offset
        else:
            m = _FENCE_OPEN_RE.match(stripped)
            if m and m.group(1)[0] == open_fence[0] and len(m.group(1)) >= len(open_fence):
                ranges.append((open_start, offset + len(line)))
                open_fence = None
        offset += len(line)
    if open_fence is not None:
        ranges.append((open_start, len(content)))
    return ranges


def _inline_code_ranges(content: str, fenced_ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Return (start, end) offsets of inline code spans (`...`), outside fenced blocks."""

    def _in_fence(pos: int) -> bool:
        return any(start <= pos < end for start, end in fenced_ranges)

    ticks = [m for m in _TICK_RUN_RE.finditer(content) if not _in_fence(m.start())]
    ranges: list[tuple[int, int]] = []
    i = 0
    while i < len(ticks):
        open_len = len(ticks[i].group())
        j = i + 1
        found = None
        while j < len(ticks):
            if len(ticks[j].group()) == open_len:
                found = ticks[j]
                break
            j += 1
        if found:
            ranges.append((ticks[i].start(), found.end()))
            i = j + 1
        else:
            i += 1
    return ranges


def find_wikilinks(content: str) -> list[WikilinkMatch]:
    """Find [[...]]/![[...]] wikilinks in content, skipping fenced/inline code."""
    fenced = _fenced_code_ranges(content)
    protected = fenced + _inline_code_ranges(content, fenced)

    def _protected_pos(pos: int) -> bool:
        return any(start <= pos < end for start, end in protected)

    matches = []
    for m in _WIKILINK_RE.finditer(content):
        if _protected_pos(m.start()):
            continue
        path_part, heading, block, alias = _split_target(m.group(2))
        matches.append(
            WikilinkMatch(
                start=m.start(),
                end=m.end(),
                is_embed=bool(m.group(1)),
                path_part=path_part,
                heading=heading,
                block=block,
                alias=alias,
            )
        )
    return matches


def stem_for_path(rel_path: str) -> str:
    """Return the canonical link target (filename stem) for a vault-relative note path."""
    return PurePosixPath(rel_path).stem


def _presumed_rel_path(path_part: str) -> str:
    return path_part if path_part.lower().endswith(".md") else f"{path_part}.md"


def _minimal_disambiguating_path(rel_path: str, colliding_paths: list[str]) -> str:
    """Shortest path suffix of rel_path that isn't shared by any colliding path."""
    target_parts = PurePosixPath(rel_path).parts
    other_parts = [PurePosixPath(p).parts for p in colliding_paths]

    for n in range(1, len(target_parts) + 1):
        candidate = target_parts[-n:]
        if not any(op[-len(candidate) :] == candidate for op in other_parts if len(op) >= len(candidate)):
            joined = "/".join(candidate)
            return joined[: -len(".md")] if joined.endswith(".md") else joined

    # Every suffix (including the full path) still collides — inherent ambiguity
    # (e.g. a root-level note sharing a basename with a note in a subfolder).
    # Fall back to the fully-qualified path; this mirrors Obsidian's own
    # undefined-resolution behavior for this case.
    joined = "/".join(target_parts)
    return joined[: -len(".md")] if joined.endswith(".md") else joined


def resolve_link_target(db: sqlite3.Connection, rel_path: str) -> str:
    """Canonical wikilink target for rel_path: bare stem, or the minimal
    disambiguating path if another vault note shares the same filename stem."""
    stem = stem_for_path(rel_path)
    rows = db.execute("SELECT path FROM notes WHERE path != ?", (rel_path,)).fetchall()
    colliding = [r["path"] for r in rows if PurePosixPath(r["path"]).stem == stem]
    if not colliding:
        return stem
    return _minimal_disambiguating_path(rel_path, colliding)


def normalize_wikilinks(db: sqlite3.Connection, content: str) -> str:
    """Normalize folder-qualified wikilink targets in content to canonical form.

    Already-bare links and matches inside code fences/spans are left untouched.
    """
    if "[[" not in content:
        return content
    matches = [m for m in find_wikilinks(content) if "/" in m.path_part]
    if not matches:
        return content

    pieces = []
    cursor = 0
    for match in matches:
        canonical_target = resolve_link_target(db, _presumed_rel_path(match.path_part))
        pieces.append(content[cursor : match.start])
        pieces.append(match.canonical(canonical_target))
        cursor = match.end
    pieces.append(content[cursor:])
    return "".join(pieces)


def link_matches_note(path_part: str, rel_path: str) -> bool:
    """True if a wikilink's path_part plausibly refers to the note at rel_path."""
    candidate_parts = PurePosixPath(_presumed_rel_path(path_part)).parts
    note_parts = PurePosixPath(rel_path).parts
    if candidate_parts[-1].lower() != note_parts[-1].lower():
        return False
    if "/" not in path_part:
        return True
    return len(note_parts) >= len(candidate_parts) and note_parts[-len(candidate_parts) :] == candidate_parts


def find_backlink_candidates(db: sqlite3.Connection, old_rel_path: str, new_rel_path: str) -> list[str]:
    """FTS-shortlist of other notes whose body plausibly references old_rel_path.

    Excludes new_rel_path (the moved note's current path), not old_rel_path —
    by the time this runs, the moved note's own row already lives at
    new_rel_path (relocate_note has run), so excluding the stale old path would
    fail to exclude the moved note itself.

    Over-inclusive by design: correctness comes from rewrite_links_in_content
    re-parsing each candidate, this just narrows which notes are worth scanning.
    """
    stem = stem_for_path(old_rel_path)
    tokens = [t for t in re.split(r"\s+", stem) if t]
    if not tokens:
        return []

    query = " ".join(fts_quote(t) + "*" for t in tokens)
    rows = db.execute(
        """
        SELECT n.path FROM notes_fts
        JOIN notes n ON n.id = notes_fts.rowid
        WHERE notes_fts MATCH ? AND n.path != ?
        """,
        (query, new_rel_path),
    ).fetchall()
    return [r["path"] for r in rows]


def _basename_is_unique(db: sqlite3.Connection, stem: str, exclude_path: str) -> bool:
    """True if no vault note other than exclude_path shares this filename stem."""
    rows = db.execute("SELECT path FROM notes WHERE path != ?", (exclude_path,)).fetchall()
    return not any(PurePosixPath(r["path"]).stem == stem for r in rows)


def rewrite_links_in_content(
    db: sqlite3.Connection, content: str, old_rel_path: str, new_rel_path: str
) -> tuple[str, bool]:
    """Rewrite wikilinks in content that reference old_rel_path to point at new_rel_path.

    A bare link (no folder) is only rewritten if old_rel_path's basename was
    unique in the vault — otherwise a bare [[Name]] could have meant a
    different note sharing that basename, and rewriting it would silently
    redirect an ambiguous link rather than resolve it. Path-qualified matches
    are unambiguous (they name the old path or a suffix of it) and are always
    rewritten. Returns (new_content, changed), where changed reflects whether
    the text actually differs, not merely whether a candidate match was found.
    """
    old_stem = stem_for_path(old_rel_path)
    old_basename_unique = _basename_is_unique(db, old_stem, new_rel_path)

    relevant = [
        m
        for m in find_wikilinks(content)
        if link_matches_note(m.path_part, old_rel_path) and ("/" in m.path_part or old_basename_unique)
    ]
    if not relevant:
        return content, False

    new_target = resolve_link_target(db, new_rel_path)
    pieces = []
    cursor = 0
    for match in relevant:
        pieces.append(content[cursor : match.start])
        pieces.append(match.canonical(new_target))
        cursor = match.end
    pieces.append(content[cursor:])
    new_content = "".join(pieces)
    return new_content, new_content != content
