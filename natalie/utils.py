from __future__ import annotations

from pathlib import Path


def safe_join(base: Path, user_part: str) -> Path:
    """Resolve user_part relative to base, raising ValueError if it escapes.

    Also rejects paths landing inside base/.natalie/ (internal bookkeeping:
    the sqlite DB, config.toml, etc.), except .natalie/entries/, which is the
    memory_store default-write location.
    """
    full = (base / user_part).resolve()
    base_resolved = base.resolve()
    if not full.is_relative_to(base_resolved):
        raise ValueError(f"path escapes base directory: {user_part!r}")
    natalie_dir = base_resolved / ".natalie"
    entries_dir = natalie_dir / "entries"
    if full.is_relative_to(natalie_dir) and not full.is_relative_to(entries_dir):
        raise ValueError(f"path targets a protected internal file: {user_part!r}")
    return full


def fts_quote(token: str) -> str:
    """Wrap an FTS5 query token in double-quotes, escaping internal quotes and NUL bytes."""
    return '"' + token.replace("\x00", "").replace('"', '""') + '"'


def require_md_path(path: str, hint: str = "") -> None:
    """Raise ValueError if path does not end with .md."""
    if not path.lower().endswith(".md"):
        msg = f"Only .md files are accepted; '{path}' is not a Markdown file."
        if hint:
            msg += f" {hint}"
        raise ValueError(msg)
