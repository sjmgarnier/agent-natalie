import pytest

from natalie.features.tasks import capture_task, complete_task, discover_tasks
from tests.helpers import write_note


def test_discover_tasks_finds_open_checkboxes(vault):
    write_note(
        vault,
        "work.md",
        "# Work\n\n- [ ] Write report\n- [x] Done thing\n- [ ] Review PR\n",
    )
    tasks = discover_tasks(vault)
    open_tasks = [t for t in tasks if not t["done"]]
    assert len(open_tasks) == 2
    texts = [t["text"] for t in open_tasks]
    assert "Write report" in texts
    assert "Review PR" in texts


def test_discover_tasks_marks_done_items(vault):
    write_note(vault, "tasks.md", "- [x] Completed task\n")
    tasks = discover_tasks(vault)
    assert len(tasks) == 1
    assert tasks[0]["done"] is True


def test_discover_tasks_returns_source_path(vault):
    write_note(vault, "project.md", "- [ ] My task\n")
    tasks = discover_tasks(vault)
    assert tasks[0]["path"] == "project.md"


def test_capture_task_appends_to_file(vault):
    note = write_note(vault, "inbox.md", "# Inbox\n\n- [ ] Existing task\n")
    capture_task(vault, "inbox.md", "New task")
    content = note.read_text()
    assert "- [ ] New task" in content


def test_capture_task_creates_file_if_missing(vault):
    capture_task(vault, "new-inbox.md", "First task")
    content = (vault / "new-inbox.md").read_text()
    assert "- [ ] First task" in content


def test_complete_task_marks_checkbox_done(vault):
    note = write_note(vault, "todo.md", "- [ ] Finish the thing\n")
    result = complete_task(vault, "todo.md", "Finish the thing")
    assert result is True
    content = note.read_text()
    assert "- [x] Finish the thing" in content


def test_complete_task_returns_false_if_not_found(vault):
    write_note(vault, "empty.md", "- [ ] Something else\n")
    result = complete_task(vault, "empty.md", "Nonexistent task")
    assert result is False


def test_discover_tasks_recognises_uppercase_X(vault):
    """Obsidian allows [X] (uppercase) for completed tasks; both forms must be found."""
    write_note(
        vault,
        "mixed.md",
        "- [X] Done uppercase\n- [x] Done lowercase\n- [ ] Still open\n",
    )
    tasks = discover_tasks(vault)
    assert len(tasks) == 3
    done = [t for t in tasks if t["done"]]
    assert len(done) == 2
    texts = {t["text"] for t in done}
    assert "Done uppercase" in texts
    assert "Done lowercase" in texts


def test_capture_task_returns_dict(vault):
    result = capture_task(vault, "tasks.md", "buy milk")
    assert isinstance(result, dict)
    assert result["captured"] is True
    assert result["path"] == "tasks.md"


def test_complete_task_handles_trailing_whitespace(vault):
    from natalie.features.tasks import complete_task, discover_tasks

    note = vault / "tasks.md"
    note.write_text("- [ ] Buy groceries  \n")  # two trailing spaces
    tasks = discover_tasks(vault)
    assert tasks[0]["text"] == "Buy groceries"
    result = complete_task(vault, "tasks.md", "Buy groceries")
    assert result is True
    assert "[x]" in note.read_text()


def test_complete_task_rejects_empty_task_text(vault):
    """C2: empty task_text must raise ValueError, not silently mark all open tasks done."""
    write_note(vault, "tasks.md", "- [ ] Important task\n- [ ] Another task\n")
    with pytest.raises(ValueError, match="task_text"):
        complete_task(vault, "tasks.md", "")
    content = (vault / "tasks.md").read_text()
    assert content.count("- [ ]") == 2  # nothing was modified


def test_complete_task_rejects_whitespace_only_task_text(vault):
    """C2: whitespace-only task_text is also invalid."""
    write_note(vault, "tasks.md", "- [ ] Some task\n")
    with pytest.raises(ValueError, match="task_text"):
        complete_task(vault, "tasks.md", "   ")
    content = (vault / "tasks.md").read_text()
    assert "- [ ]" in content  # nothing was modified


def test_discover_tasks_works_with_symlinked_vault(vault):
    """discover_tasks must not raise ValueError when vault is a symlink — B2."""
    import os
    import tempfile
    from pathlib import Path

    write_note(vault, "tasks.md", "- [ ] A task\n")
    with tempfile.TemporaryDirectory() as td:
        link = Path(td) / "vault_link"
        os.symlink(vault, link)
        tasks = discover_tasks(link)
    assert any(t["text"] == "A task" for t in tasks)
