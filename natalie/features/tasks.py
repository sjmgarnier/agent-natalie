from __future__ import annotations

import re
from pathlib import Path

from ..utils import safe_join

_ANY_RE = re.compile(r"^(\s*- \[[ xX]\] )(.+)$", re.MULTILINE)


def discover_tasks(vault: Path) -> list[dict]:
    """Return all task checkboxes across vault markdown files."""
    tasks = []
    for md in vault.rglob("*.md"):
        if any(part.startswith(".") for part in md.relative_to(vault).parts):
            continue
        rel = md.relative_to(vault).as_posix()
        text = md.read_text(encoding="utf-8")
        for m in _ANY_RE.finditer(text):
            marker, task_text = m.group(1), m.group(2).strip()
            tasks.append(
                {
                    "text": task_text,
                    "done": "[x]" in marker.lower(),
                    "path": rel,
                    "line": text[: m.start()].count("\n") + 1,
                }
            )
    return tasks


def capture_task(vault: Path, rel_path: str, task_text: str) -> None:
    """Append a new open task to a note (creates the file if missing)."""
    full = safe_join(vault, rel_path)
    if full.exists():
        existing = full.read_text(encoding="utf-8")
        if not existing.endswith("\n"):
            existing += "\n"
        full.write_text(existing + f"- [ ] {task_text}\n", encoding="utf-8")
    else:
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(f"- [ ] {task_text}\n", encoding="utf-8")


def complete_task(vault: Path, rel_path: str, task_text: str) -> bool:
    """Mark a specific open task as done. Returns True if found and marked."""
    full = safe_join(vault, rel_path)
    if not full.exists():
        return False
    content = full.read_text(encoding="utf-8")
    pattern = re.compile(r"^(\s*)- \[ \] (" + re.escape(task_text) + r")\s*$", re.MULTILINE)
    new_content = pattern.sub(r"\g<1>- [x] \g<2>", content)
    if new_content == content:
        return False
    full.write_text(new_content, encoding="utf-8")
    return True
