from __future__ import annotations

import datetime
import re
from pathlib import Path
from typing import Any

from ..utils import safe_join

_ANY_RE: re.Pattern[str] = re.compile(r"^(\s*- \[[ xX]\] )(.+)$", re.MULTILINE)

_PRIORITY_EMOJIS: dict[str, str] = {
    "🔺": "highest",
    "⏫": "high",
    "🔼": "medium",
    "🔽": "low",
    "⏬": "lowest",
}
_PRIORITY_TO_EMOJI: dict[str, str] = {v: k for k, v in _PRIORITY_EMOJIS.items()}
_VALID_PRIORITIES: frozenset[str] = frozenset(_PRIORITY_EMOJIS.values())

_PRIORITY_RE: re.Pattern[str] = re.compile(r"[🔺⏫🔼🔽⏬]️?")
_DUE_DATE_RE: re.Pattern[str] = re.compile(r"📅\s*(\d{4}-\d{2}-\d{2})")
_RECURRENCE_RE: re.Pattern[str] = re.compile(r"🔁\s*([^📅⏳🛫✅🔺⏫🔼🔽⏬]+)")

# Matches the start of Tasks plugin metadata (used in complete_task match pattern)
_META_EMOJI: str = r"[📅🔺⏫🔼🔽⏬🔁✅⏳🛫]"


def _parse_task_text(raw: str) -> dict[str, str | None]:
    """Extract clean title and Tasks plugin metadata from a raw task string."""
    text = raw

    priority: str | None = None
    pm = _PRIORITY_RE.search(text)
    if pm:
        emoji = pm.group(0).rstrip("️")
        priority = _PRIORITY_EMOJIS.get(emoji)
        text = text[: pm.start()] + text[pm.end() :]

    due_date: str | None = None
    dm = _DUE_DATE_RE.search(text)
    if dm:
        due_date = dm.group(1)
        text = text[: dm.start()] + text[dm.end() :]

    recurrence: str | None = None
    rm = _RECURRENCE_RE.search(text)
    if rm:
        recurrence = rm.group(1).strip()
        text = text[: rm.start()] + text[rm.end() :]

    return {"text": text.strip(), "due_date": due_date, "priority": priority, "recurrence": recurrence}


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
    due_date: str | None = None,
    priority: str | None = None,
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

    metadata = _format_task_metadata(due_date, priority, recurrence)
    line = f"- [ ] {task_text}"
    if metadata:
        line += f" {metadata}"
    line += "\n"

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
