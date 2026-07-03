from __future__ import annotations

import datetime
import re
import sqlite3
from pathlib import Path
from typing import Any, Literal

from ..utils import safe_join

_ANY_RE: re.Pattern[str] = re.compile(r"^([ \t]*- \[[ xX]\] )(.+)$", re.MULTILINE)
_TAG_RE: re.Pattern[str] = re.compile(r"#[a-zA-Z][a-zA-Z0-9\-_/]*")

_PRIORITY_EMOJIS: dict[str, str] = {
    "🔺": "highest",
    "⏫": "high",
    "🔼": "medium",
    "🔽": "low",
    "⏬": "lowest",
}
_PRIORITY_TO_EMOJI: dict[str, str] = {v: k for k, v in _PRIORITY_EMOJIS.items()}
_VALID_PRIORITIES: frozenset[str] = frozenset(_PRIORITY_EMOJIS.values())

PriorityLiteral = Literal["highest", "high", "medium", "low", "lowest"]

_PRIORITY_RE: re.Pattern[str] = re.compile(r"[🔺⏫🔼🔽⏬]️?")
_DUE_DATE_RE: re.Pattern[str] = re.compile(r"📅\s*(\d{4}-\d{2}-\d{2})")
_RECURRENCE_RE: re.Pattern[str] = re.compile(r"🔁\s*([^📅⏳🛫✅🔺⏫🔼🔽⏬]+)")

# Matches the start of Tasks plugin metadata (used in complete_task match pattern)
_META_EMOJI: str = r"[📅🔺⏫🔼🔽⏬🔁✅⏳🛫]"

_OPEN_TASK_RE: re.Pattern[str] = re.compile(r"^(\s*)- \[ \] (.+)$")


def _split_tags(text: str) -> tuple[list[str], str, list[str]]:
    """Split text into (leading_tags, middle_text, trailing_tags).

    Only consecutive #tag tokens at the very start and very end are extracted.
    Tags embedded mid-sentence are left in middle_text unchanged.
    """
    tokens = text.split()
    i = 0
    while i < len(tokens) and _TAG_RE.fullmatch(tokens[i]):
        i += 1
    j = len(tokens) - 1
    while j >= i and _TAG_RE.fullmatch(tokens[j]):
        j -= 1
    leading = tokens[:i]
    trailing = tokens[j + 1 :]
    middle = " ".join(tokens[i : j + 1])
    return leading, middle, trailing


def _parse_task_text(raw: str) -> dict[str, Any]:
    """Extract clean title, inline tags, and Tasks plugin metadata from a raw task string."""
    text = raw

    priority: str | None = None
    pm = _PRIORITY_RE.search(text)
    if pm:
        emoji = pm.group(0).removesuffix("️")
        priority = _PRIORITY_EMOJIS.get(emoji)
        text = text[: pm.start()] + text[pm.end() :]

    due_date: str | None = None
    dm = _DUE_DATE_RE.search(text)
    if dm:
        raw_due = dm.group(1)
        try:
            datetime.date.fromisoformat(raw_due)
            due_date = raw_due
            text = text[: dm.start()] + text[dm.end() :]
        except ValueError:
            due_date = None

    recurrence: str | None = None
    rm = _RECURRENCE_RE.search(text)
    if rm:
        recurrence = rm.group(1).strip()
        text = text[: rm.start()] + text[rm.end() :]

    leading, middle, trailing = _split_tags(text.strip())
    return {
        "text": middle,
        "tags": leading + trailing,
        "leading_tags": leading,
        "trailing_tags": trailing,
        "due_date": due_date,
        "priority": priority,
        "recurrence": recurrence,
    }


def _format_task_metadata(
    due_date: str | None,
    priority: str | None,
    recurrence: str | None,
) -> str:
    """Build the Tasks plugin emoji suffix in canonical order: priority recurrence due."""
    parts: list[str] = []
    if priority and priority in _PRIORITY_TO_EMOJI:
        parts.append(_PRIORITY_TO_EMOJI[priority])
    if recurrence:
        parts.append(f"🔁 {recurrence}")
    if due_date:
        parts.append(f"📅 {due_date}")
    return " ".join(parts)


def _format_task_line(
    text: str,
    leading_tags: list[str],
    trailing_tags: list[str],
    due_date: str | None,
    priority: str | None,
    recurrence: str | None,
    indent: str = "",
) -> str:
    """Assemble a canonical open-task line: #leading text #trailing 🔁 📅 🔺"""
    if "\n" in text or "\r" in text:
        raise ValueError(f"task text must not contain newlines: {text!r}")
    parts = leading_tags + ([text] if text else []) + trailing_tags
    content = " ".join(p for p in parts if p)
    metadata = _format_task_metadata(due_date, priority, recurrence)
    line = f"{indent}- [ ] {content}"
    if metadata:
        line += f" {metadata}"
    return line


def discover_tasks(vault: Path, today: datetime.date | None = None) -> list[dict[str, Any]]:
    """Return all task checkboxes across vault markdown files."""
    if today is None:
        today = datetime.date.today()
    tasks = []
    vault = vault.resolve()
    for md in vault.rglob("*.md"):
        if any(part.startswith(".") for part in md.relative_to(vault).parts):
            continue
        rel = md.relative_to(vault).as_posix()
        text = md.read_text(encoding="utf-8")
        for m in _ANY_RE.finditer(text):
            marker, raw_text = m.group(1), m.group(2).strip()
            parsed = _parse_task_text(raw_text)
            due_date = parsed["due_date"]
            overdue = False
            if due_date:
                try:
                    overdue = datetime.date.fromisoformat(due_date) < today
                except ValueError:
                    pass
            tasks.append(
                {
                    "text": parsed["text"],
                    "tags": parsed["tags"],
                    "done": "[x]" in marker.lower(),
                    "path": rel,
                    "line": text[: m.start()].count("\n") + 1,
                    "due_date": due_date,
                    "priority": parsed["priority"],
                    "recurrence": parsed["recurrence"],
                    "overdue": overdue,
                }
            )
    return tasks


def capture_task(
    vault: Path,
    rel_path: str,
    task_text: str,
    *,
    tags: list[str] | None = None,
    due_date: str | None = None,
    priority: PriorityLiteral | None = None,
    recurrence: str | None = None,
) -> dict[str, Any]:
    """Append a new open task to a note (creates the file if missing)."""
    if not task_text.strip():
        raise ValueError("task_text must not be empty")
    if priority is not None and priority not in _VALID_PRIORITIES:
        raise ValueError(f"priority must be one of {sorted(_VALID_PRIORITIES)}, got {priority!r}")
    if due_date is not None:
        try:
            datetime.date.fromisoformat(due_date)
        except ValueError:
            raise ValueError(f"due_date must be in YYYY-MM-DD format, got {due_date!r}")

    line = _format_task_line(task_text, tags or [], [], due_date, priority, recurrence) + "\n"

    full = safe_join(vault, rel_path)
    if full.exists():
        existing = full.read_text(encoding="utf-8")
        if not existing.endswith("\n"):
            existing += "\n"
        full.write_text(existing + line, encoding="utf-8")
    else:
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(line, encoding="utf-8")
    return {
        "captured": True,
        "path": rel_path,
        "task": task_text,
        "tags": list(tags) if tags else [],
        "due_date": due_date,
        "priority": priority,
        "recurrence": recurrence,
    }


def complete_task(
    vault: Path,
    rel_path: str,
    task_text: str,
    today: datetime.date | None = None,
) -> dict[str, Any]:
    """Mark a specific open task as done. Returns dict with completed and completed_date."""
    if not task_text.strip():
        raise ValueError("task_text must not be empty")
    if today is None:
        today = datetime.date.today()
    full = safe_join(vault, rel_path)
    if not full.exists():
        return {"completed": False, "path": rel_path, "task": task_text, "completed_date": None}
    content = full.read_text(encoding="utf-8")
    pattern = re.compile(
        r"^(\s*)- \[ \] (" + re.escape(task_text) + r")(\s*" + _META_EMOJI + r".*|\s*)$",
        re.MULTILINE,
    )
    completed_date = today.isoformat()

    def _replace(m: re.Match[str]) -> str:
        trailing = m.group(3).rstrip()
        return f"{m.group(1)}- [x] {m.group(2)}{trailing} ✅ {completed_date}"

    new_content, count = pattern.subn(_replace, content)
    if count == 0:
        return {"completed": False, "path": rel_path, "task": task_text, "completed_date": None}
    full.write_text(new_content, encoding="utf-8")
    return {"completed": True, "path": rel_path, "task": task_text, "completed_date": completed_date}


def update_task(
    vault: Path,
    rel_path: str,
    task_text: str,
    *,
    new_text: str | None = None,
    tags: list[str] | Literal["clear"] | None = None,
    due_date: str | Literal["clear"] | None = None,
    priority: PriorityLiteral | Literal["clear"] | None = None,
    recurrence: str | Literal["clear"] | None = None,
) -> dict[str, Any]:
    """Edit an existing open task in place without marking it complete."""
    if new_text is None and tags is None and due_date is None and priority is None and recurrence is None:
        raise ValueError("at least one of new_text, tags, due_date, priority, or recurrence must be provided")
    if priority is not None and priority != "clear" and priority not in _VALID_PRIORITIES:
        raise ValueError(f"priority must be one of {sorted(_VALID_PRIORITIES)} or 'clear', got {priority!r}")
    if due_date is not None and due_date != "clear":
        try:
            datetime.date.fromisoformat(due_date)
        except ValueError:
            raise ValueError(f"due_date must be in YYYY-MM-DD format or 'clear', got {due_date!r}")

    full = safe_join(vault, rel_path)
    if not full.exists():
        return {
            "updated": False,
            "path": rel_path,
            "task": task_text,
            "tags": [],
            "due_date": None,
            "priority": None,
            "recurrence": None,
        }

    content = full.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)

    for i, line in enumerate(lines):
        m = _OPEN_TASK_RE.match(line.rstrip("\n\r"))
        if m is None:
            continue
        parsed = _parse_task_text(m.group(2).strip())
        if parsed["text"] != task_text:
            continue

        final_text = new_text if new_text is not None else task_text
        final_leading: list[str] = (
            [] if tags == "clear" else (list(tags) if tags is not None else parsed["leading_tags"])
        )
        final_due = (
            None if due_date == "clear" else (due_date if due_date is not None else parsed["due_date"])
        )
        final_prio = (
            None if priority == "clear" else (priority if priority is not None else parsed["priority"])
        )
        final_recur = (
            None
            if recurrence == "clear"
            else (recurrence if recurrence is not None else parsed["recurrence"])
        )

        indent = m.group(1)
        new_line = _format_task_line(
            final_text, final_leading, parsed["trailing_tags"], final_due, final_prio, final_recur, indent
        )
        stripped_len = len(line.rstrip("\n\r"))
        ending = line[stripped_len:] or "\n"
        lines[i] = new_line + ending

        full.write_text("".join(lines), encoding="utf-8")
        final_tags = final_leading + parsed["trailing_tags"]
        return {
            "updated": True,
            "path": rel_path,
            "task": final_text,
            "tags": final_tags,
            "due_date": final_due,
            "priority": final_prio,
            "recurrence": final_recur,
        }

    return {
        "updated": False,
        "path": rel_path,
        "task": task_text,
        "tags": [],
        "due_date": None,
        "priority": None,
        "recurrence": None,
    }


def index_tasks(db: sqlite3.Connection, vault: Path, note_path: Path, *, commit: bool = True) -> int:
    """Parse tasks from a vault note and upsert into DB. Returns count of task rows written."""
    vault = vault.resolve()
    note_path = note_path.resolve()
    rel = note_path.relative_to(vault).as_posix()

    db.execute("DELETE FROM tasks WHERE path = ?", (rel,))

    if not note_path.exists():
        if commit:
            db.commit()
        return 0

    text = note_path.read_text(encoding="utf-8")
    count = 0
    for m in _ANY_RE.finditer(text):
        marker, raw_text = m.group(1), m.group(2).strip()
        parsed = _parse_task_text(raw_text)
        done = 1 if "[x]" in marker.lower() else 0
        line = text[: m.start()].count("\n") + 1
        tags_str = " ".join(parsed["tags"]) if parsed["tags"] else None
        db.execute(
            "INSERT OR REPLACE INTO tasks (path, line, text, done, due_date, priority, recurrence, tags) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                rel,
                line,
                parsed["text"],
                done,
                parsed["due_date"],
                parsed["priority"],
                parsed["recurrence"],
                tags_str,
            ),
        )
        count += 1

    if commit:
        db.commit()
    return count


def sync_tasks(db: sqlite3.Connection, vault: Path) -> int:
    """Re-index all tasks from vault notes in a single atomic transaction."""
    vault = vault.resolve()
    md_files = [
        p for p in vault.rglob("*.md") if not any(part.startswith(".") for part in p.relative_to(vault).parts)
    ]
    total = 0
    db.execute("DELETE FROM tasks")
    for p in md_files:
        total += index_tasks(db, vault, p, commit=False)
    db.commit()
    return total
