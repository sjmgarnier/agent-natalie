import pytest
from pathlib import Path
from natalie.features.tasks import discover_tasks, capture_task, complete_task


def _write(vault: Path, rel: str, content: str) -> Path:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def test_discover_tasks_finds_open_checkboxes(vault):
    _write(vault, "work.md", "# Work\n\n- [ ] Write report\n- [x] Done thing\n- [ ] Review PR\n")
    tasks = discover_tasks(vault)
    open_tasks = [t for t in tasks if not t["done"]]
    assert len(open_tasks) == 2
    texts = [t["text"] for t in open_tasks]
    assert "Write report" in texts
    assert "Review PR" in texts


def test_discover_tasks_marks_done_items(vault):
    _write(vault, "tasks.md", "- [x] Completed task\n")
    tasks = discover_tasks(vault)
    assert len(tasks) == 1
    assert tasks[0]["done"] is True


def test_discover_tasks_returns_source_path(vault):
    _write(vault, "project.md", "- [ ] My task\n")
    tasks = discover_tasks(vault)
    assert tasks[0]["path"] == "project.md"


def test_capture_task_appends_to_file(vault):
    note = _write(vault, "inbox.md", "# Inbox\n\n- [ ] Existing task\n")
    capture_task(vault, "inbox.md", "New task")
    content = note.read_text()
    assert "- [ ] New task" in content


def test_capture_task_creates_file_if_missing(vault):
    capture_task(vault, "new-inbox.md", "First task")
    content = (vault / "new-inbox.md").read_text()
    assert "- [ ] First task" in content


def test_complete_task_marks_checkbox_done(vault):
    note = _write(vault, "todo.md", "- [ ] Finish the thing\n")
    result = complete_task(vault, "todo.md", "Finish the thing")
    assert result is True
    content = note.read_text()
    assert "- [x] Finish the thing" in content


def test_complete_task_returns_false_if_not_found(vault):
    _write(vault, "empty.md", "- [ ] Something else\n")
    result = complete_task(vault, "empty.md", "Nonexistent task")
    assert result is False
