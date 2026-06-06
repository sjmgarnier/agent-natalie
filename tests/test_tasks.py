import datetime

import pytest

from natalie.features.tasks import (
    _parse_task_text,
    capture_task,
    complete_task,
    discover_tasks,
    index_tasks,
    sync_tasks,
    update_task,
)
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
    assert result["completed"] is True
    assert result["completed_date"] is not None
    content = note.read_text()
    assert "- [x] Finish the thing" in content


def test_complete_task_returns_false_if_not_found(vault):
    write_note(vault, "empty.md", "- [ ] Something else\n")
    result = complete_task(vault, "empty.md", "Nonexistent task")
    assert result["completed"] is False
    assert result["completed_date"] is None


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
    assert result["completed"] is True
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


def test_capture_task_rejects_empty_task_text(vault):
    with pytest.raises(ValueError, match="task_text"):
        capture_task(vault, "Note.md", "")


def test_capture_task_rejects_whitespace_task_text(vault):
    with pytest.raises(ValueError, match="task_text"):
        capture_task(vault, "Note.md", "   ")


# --- _parse_task_text ---


def test_parse_task_text_plain_title():
    result = _parse_task_text("Write report")
    assert result == {"text": "Write report", "due_date": None, "priority": None, "recurrence": None}


def test_parse_task_text_due_date():
    result = _parse_task_text("Write report 📅 2026-06-10")
    assert result["text"] == "Write report"
    assert result["due_date"] == "2026-06-10"


def test_parse_task_text_priority_all_levels():
    cases = [
        ("Buy milk 🔺", "highest"),
        ("Buy milk ⏫", "high"),
        ("Buy milk 🔼", "medium"),
        ("Buy milk 🔽", "low"),
        ("Buy milk ⏬", "lowest"),
    ]
    for raw, expected in cases:
        result = _parse_task_text(raw)
        assert result["text"] == "Buy milk", f"failed for {raw}"
        assert result["priority"] == expected, f"failed for {raw}"


def test_parse_task_text_recurrence():
    result = _parse_task_text("Water plants 🔁 every week")
    assert result["text"] == "Water plants"
    assert result["recurrence"] == "every week"


def test_parse_task_text_all_fields():
    result = _parse_task_text("Team standup ⏫ 🔁 every day 📅 2026-06-05")
    assert result["text"] == "Team standup"
    assert result["priority"] == "high"
    assert result["recurrence"] == "every day"
    assert result["due_date"] == "2026-06-05"


def test_parse_task_text_order_independent():
    result = _parse_task_text("Review PR 📅 2026-06-10 🔼")
    assert result["text"] == "Review PR"
    assert result["due_date"] == "2026-06-10"
    assert result["priority"] == "medium"


# --- discover_tasks new fields ---


def test_discover_tasks_parses_due_date(vault):
    write_note(vault, "tasks.md", "- [ ] File tax return 📅 2026-06-10\n")
    tasks = discover_tasks(vault)
    assert tasks[0]["due_date"] == "2026-06-10"
    assert tasks[0]["text"] == "File tax return"


def test_discover_tasks_parses_priority(vault):
    write_note(vault, "tasks.md", "- [ ] Urgent thing ⏫\n")
    tasks = discover_tasks(vault)
    assert tasks[0]["priority"] == "high"
    assert tasks[0]["text"] == "Urgent thing"


def test_discover_tasks_parses_recurrence(vault):
    write_note(vault, "tasks.md", "- [ ] Water plants 🔁 every week\n")
    tasks = discover_tasks(vault)
    assert tasks[0]["recurrence"] == "every week"


def test_discover_tasks_overdue_true(vault):
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    write_note(vault, "tasks.md", f"- [ ] Late task 📅 {yesterday}\n")
    tasks = discover_tasks(vault)
    assert tasks[0]["overdue"] is True


def test_discover_tasks_overdue_false_future(vault):
    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    write_note(vault, "tasks.md", f"- [ ] Future task 📅 {tomorrow}\n")
    tasks = discover_tasks(vault)
    assert tasks[0]["overdue"] is False


def test_discover_tasks_overdue_false_no_date(vault):
    write_note(vault, "tasks.md", "- [ ] No due date\n")
    tasks = discover_tasks(vault)
    assert tasks[0]["overdue"] is False


def test_discover_tasks_today_param(vault):
    write_note(vault, "tasks.md", "- [ ] Task 📅 2026-01-01\n")
    tasks = discover_tasks(vault, today=datetime.date(2025, 12, 31))
    assert tasks[0]["overdue"] is False
    tasks2 = discover_tasks(vault, today=datetime.date(2026, 1, 2))
    assert tasks2[0]["overdue"] is True


def test_discover_tasks_plain_task_has_none_fields(vault):
    write_note(vault, "tasks.md", "- [ ] Plain task\n")
    tasks = discover_tasks(vault)
    assert tasks[0]["due_date"] is None
    assert tasks[0]["priority"] is None
    assert tasks[0]["recurrence"] is None
    assert tasks[0]["overdue"] is False


# --- capture_task with metadata ---


def test_capture_task_with_due_date(vault):
    note = write_note(vault, "tasks.md", "")
    capture_task(vault, "tasks.md", "File taxes", due_date="2026-06-30")
    assert "- [ ] File taxes 📅 2026-06-30" in note.read_text()


def test_capture_task_with_priority(vault):
    note = write_note(vault, "tasks.md", "")
    capture_task(vault, "tasks.md", "Urgent fix", priority="highest")
    assert "- [ ] Urgent fix 🔺" in note.read_text()


def test_capture_task_with_recurrence(vault):
    note = write_note(vault, "tasks.md", "")
    capture_task(vault, "tasks.md", "Water plants", recurrence="every week")
    assert "- [ ] Water plants 🔁 every week" in note.read_text()


def test_capture_task_with_all_metadata(vault):
    note = write_note(vault, "tasks.md", "")
    capture_task(vault, "tasks.md", "Standup", due_date="2026-06-05", priority="high", recurrence="every day")
    assert "- [ ] Standup ⏫ 🔁 every day 📅 2026-06-05" in note.read_text()


def test_capture_task_round_trips_metadata(vault):
    write_note(vault, "tasks.md", "")
    capture_task(vault, "tasks.md", "Review PR", due_date="2026-07-01", priority="medium")
    tasks = discover_tasks(vault)
    t = next(t for t in tasks if t["text"] == "Review PR")
    assert t["due_date"] == "2026-07-01"
    assert t["priority"] == "medium"


def test_capture_task_returns_metadata_fields(vault):
    write_note(vault, "tasks.md", "")
    result = capture_task(vault, "tasks.md", "Buy milk", due_date="2026-06-10", priority="low")
    assert result["due_date"] == "2026-06-10"
    assert result["priority"] == "low"
    assert result["recurrence"] is None


def test_capture_task_rejects_invalid_priority(vault):
    with pytest.raises(ValueError, match="priority"):
        capture_task(vault, "tasks.md", "Do thing", priority="urgent")


def test_capture_task_rejects_invalid_due_date(vault):
    with pytest.raises(ValueError, match="due_date"):
        capture_task(vault, "tasks.md", "Do thing", due_date="June 10")


# --- complete_task with completion date ---


def test_complete_task_appends_completion_date(vault):
    write_note(vault, "tasks.md", "- [ ] Buy groceries\n")
    today = datetime.date(2026, 6, 4)
    result = complete_task(vault, "tasks.md", "Buy groceries", today=today)
    assert result["completed"] is True
    assert result["completed_date"] == "2026-06-04"
    assert "- [x] Buy groceries ✅ 2026-06-04" in (vault / "tasks.md").read_text()


def test_complete_task_preserves_existing_metadata(vault):
    write_note(vault, "tasks.md", "- [ ] File taxes ⏫ 📅 2026-06-30\n")
    today = datetime.date(2026, 6, 4)
    result = complete_task(vault, "tasks.md", "File taxes", today=today)
    assert result["completed"] is True
    assert "- [x] File taxes ⏫ 📅 2026-06-30 ✅ 2026-06-04" in (vault / "tasks.md").read_text()


def test_complete_task_clean_title_matches_metadata_line(vault):
    write_note(vault, "tasks.md", "- [ ] Water plants 🔁 every week 📅 2026-06-10\n")
    result = complete_task(vault, "tasks.md", "Water plants")
    assert result["completed"] is True


def test_complete_task_does_not_match_partial_title(vault):
    write_note(vault, "tasks.md", "- [ ] Buy milk\n")
    result = complete_task(vault, "tasks.md", "Buy")
    assert result["completed"] is False


# --- update_task ---


def test_update_task_due_date_only(vault):
    write_note(vault, "tasks.md", "- [ ] Write report ⏫\n")
    result = update_task(vault, "tasks.md", "Write report", due_date="2026-07-01")
    assert result["updated"] is True
    assert result["due_date"] == "2026-07-01"
    assert result["priority"] == "high"  # preserved
    content = (vault / "tasks.md").read_text()
    assert "- [ ] Write report ⏫ 📅 2026-07-01" in content


def test_update_task_priority_only(vault):
    write_note(vault, "tasks.md", "- [ ] Write report 📅 2026-07-01\n")
    result = update_task(vault, "tasks.md", "Write report", priority="high")
    assert result["updated"] is True
    assert result["priority"] == "high"
    assert result["due_date"] == "2026-07-01"  # preserved
    content = (vault / "tasks.md").read_text()
    assert "- [ ] Write report ⏫ 📅 2026-07-01" in content


def test_update_task_recurrence_only(vault):
    write_note(vault, "tasks.md", "- [ ] Water plants\n")
    result = update_task(vault, "tasks.md", "Water plants", recurrence="every week")
    assert result["updated"] is True
    assert result["recurrence"] == "every week"
    content = (vault / "tasks.md").read_text()
    assert "- [ ] Water plants 🔁 every week" in content


def test_update_task_rename_only(vault):
    write_note(vault, "tasks.md", "- [ ] Write report ⏫ 📅 2026-07-01\n")
    result = update_task(vault, "tasks.md", "Write report", new_text="Write final report")
    assert result["updated"] is True
    assert result["task"] == "Write final report"
    assert result["priority"] == "high"  # preserved
    assert result["due_date"] == "2026-07-01"  # preserved
    content = (vault / "tasks.md").read_text()
    assert "- [ ] Write final report ⏫ 📅 2026-07-01" in content
    assert "- [ ] Write report" not in content


def test_update_task_multiple_fields(vault):
    write_note(vault, "tasks.md", "- [ ] Write report 🔽\n")
    result = update_task(vault, "tasks.md", "Write report", priority="highest", due_date="2026-08-01")
    assert result["updated"] is True
    assert result["priority"] == "highest"
    assert result["due_date"] == "2026-08-01"
    content = (vault / "tasks.md").read_text()
    assert "- [ ] Write report 🔺 📅 2026-08-01" in content


def test_update_task_clear_due_date(vault):
    write_note(vault, "tasks.md", "- [ ] Write report ⏫ 📅 2026-07-01\n")
    result = update_task(vault, "tasks.md", "Write report", due_date="clear")
    assert result["updated"] is True
    assert result["due_date"] is None
    assert result["priority"] == "high"  # preserved
    content = (vault / "tasks.md").read_text()
    assert "📅" not in content
    assert "⏫" in content


def test_update_task_not_found(vault):
    write_note(vault, "tasks.md", "- [ ] Something else\n")
    result = update_task(vault, "tasks.md", "Nonexistent task", due_date="2026-07-01")
    assert result["updated"] is False


def test_update_task_no_fields_raises(vault):
    write_note(vault, "tasks.md", "- [ ] Write report\n")
    with pytest.raises(ValueError, match="at least one"):
        update_task(vault, "tasks.md", "Write report")


def test_update_task_invalid_priority_raises(vault):
    write_note(vault, "tasks.md", "- [ ] Write report\n")
    with pytest.raises(ValueError, match="priority"):
        update_task(vault, "tasks.md", "Write report", priority="urgent")


def test_update_task_invalid_due_date_raises(vault):
    write_note(vault, "tasks.md", "- [ ] Write report\n")
    with pytest.raises(ValueError, match="due_date"):
        update_task(vault, "tasks.md", "Write report", due_date="next Monday")


# ---------------------------------------------------------------------------
# index_tasks
# ---------------------------------------------------------------------------


def test_index_tasks_inserts_open_task(vault, db):
    write_note(vault, "todo.md", "- [ ] Buy milk\n")
    count = index_tasks(db, vault, vault / "todo.md")
    assert count == 1
    row = db.execute("SELECT * FROM tasks WHERE path = 'todo.md'").fetchone()
    assert row["text"] == "Buy milk"
    assert row["done"] == 0


def test_index_tasks_inserts_done_task(vault, db):
    write_note(vault, "done.md", "- [x] Finished thing\n")
    index_tasks(db, vault, vault / "done.md")
    row = db.execute("SELECT * FROM tasks WHERE path = 'done.md'").fetchone()
    assert row["done"] == 1


def test_index_tasks_parses_metadata(vault, db):
    write_note(vault, "meta.md", "- [ ] Plan trip 📅 2026-07-01 ⏫\n")
    index_tasks(db, vault, vault / "meta.md")
    row = db.execute("SELECT * FROM tasks WHERE path = 'meta.md'").fetchone()
    assert row["text"] == "Plan trip"
    assert row["due_date"] == "2026-07-01"
    assert row["priority"] == "high"


def test_index_tasks_stores_line_number(vault, db):
    write_note(vault, "lines.md", "- [ ] First task\n- [ ] Second task\n")
    index_tasks(db, vault, vault / "lines.md")
    rows = db.execute("SELECT line FROM tasks WHERE path = 'lines.md' ORDER BY line").fetchall()
    assert rows[0]["line"] == 1
    assert rows[1]["line"] == 2


def test_index_tasks_replaces_on_reindex(vault, db):
    write_note(vault, "todo.md", "- [ ] Old task\n")
    index_tasks(db, vault, vault / "todo.md")
    write_note(vault, "todo.md", "- [ ] New task\n")
    index_tasks(db, vault, vault / "todo.md")
    rows = db.execute("SELECT * FROM tasks WHERE path = 'todo.md'").fetchall()
    assert len(rows) == 1
    assert rows[0]["text"] == "New task"


def test_index_tasks_missing_file_clears_tasks(vault, db):
    write_note(vault, "todo.md", "- [ ] My task\n")
    index_tasks(db, vault, vault / "todo.md")
    (vault / "todo.md").unlink()
    count = index_tasks(db, vault, vault / "todo.md")
    assert count == 0
    assert db.execute("SELECT COUNT(*) FROM tasks WHERE path = 'todo.md'").fetchone()[0] == 0


def test_index_tasks_returns_count(vault, db):
    write_note(vault, "multi.md", "- [ ] Task A\n- [x] Done B\n- [ ] Task C\n")
    count = index_tasks(db, vault, vault / "multi.md")
    assert count == 3


# ---------------------------------------------------------------------------
# sync_tasks
# ---------------------------------------------------------------------------


def test_sync_tasks_indexes_all_vault_tasks(vault, db):
    write_note(vault, "a.md", "- [ ] Task A\n")
    write_note(vault, "b.md", "- [ ] Task B\n- [ ] Task C\n")
    total = sync_tasks(db, vault)
    assert total == 3


def test_sync_tasks_skips_dot_directories(vault, db):
    dot = vault / ".obsidian"
    dot.mkdir()
    (dot / "hidden.md").write_text("- [ ] Hidden\n", encoding="utf-8")
    write_note(vault, "visible.md", "- [ ] Visible task\n")
    sync_tasks(db, vault)
    rows = db.execute("SELECT path FROM tasks").fetchall()
    assert len(rows) == 1
    assert rows[0]["path"] == "visible.md"


def test_sync_tasks_replaces_stale_data(vault, db):
    write_note(vault, "todo.md", "- [ ] Old task\n")
    sync_tasks(db, vault)
    write_note(vault, "todo.md", "- [ ] New task\n")
    sync_tasks(db, vault)
    rows = db.execute("SELECT text FROM tasks").fetchall()
    assert len(rows) == 1
    assert rows[0]["text"] == "New task"


def test_index_tasks_stores_none_for_invalid_due_date(vault, db):
    """A syntactically matching but semantically invalid date must be stored as NULL."""
    write_note(vault, "tasks.md", "- [ ] Bad date task 📅 2024-99-99\n")
    index_tasks(db, vault, vault / "tasks.md")
    row = db.execute("SELECT due_date FROM tasks WHERE path = 'tasks.md'").fetchone()
    assert row is not None
    assert row["due_date"] is None


def test_discover_tasks_stores_none_for_invalid_due_date(vault):
    """discover_tasks must not report overdue=False via silent swallow; it clears bad dates."""
    write_note(vault, "tasks.md", "- [ ] Bad date task 📅 2024-99-99\n")
    tasks = discover_tasks(vault)
    assert len(tasks) == 1
    assert tasks[0]["due_date"] is None
    assert tasks[0]["overdue"] is False


def test_index_tasks_line_number_after_heading_and_blank(vault, db):
    write_note(vault, "heading.md", "# My Notes\n\n- [ ] First task\n- [ ] Second task\n")
    index_tasks(db, vault, vault / "heading.md")
    rows = db.execute("SELECT line, text FROM tasks WHERE path = 'heading.md' ORDER BY line").fetchall()
    assert len(rows) == 2
    assert rows[0]["line"] == 3, f"first task should be on line 3, got {rows[0]['line']}"
    assert rows[1]["line"] == 4, f"second task should be on line 4, got {rows[1]['line']}"


def test_parse_task_text_priority_variation_selector(vault, db):
    result = _parse_task_text("My Task 🔺️")
    assert result["priority"] == "highest", f"got {result['priority']!r}"
    assert result["text"] == "My Task", f"got {result['text']!r}"


def test_index_tasks_no_duplicate_rows_on_double_call(vault, db):
    write_note(vault, "dup.md", "- [ ] Task One\n")
    index_tasks(db, vault, vault / "dup.md")
    index_tasks(db, vault, vault / "dup.md")
    rows = db.execute("SELECT * FROM tasks WHERE path = 'dup.md'").fetchall()
    assert len(rows) == 1


def test_index_tasks_commit_false_does_not_commit(vault, db):
    import sqlite3 as _sqlite3

    write_note(vault, "tasks.md", "- [ ] My Task\n")
    count = index_tasks(db, vault, vault / "tasks.md", commit=False)
    assert count == 1

    db2 = _sqlite3.connect(str(vault / ".natalie" / "natalie.db"), check_same_thread=False)
    db2.row_factory = _sqlite3.Row
    db2.execute("PRAGMA journal_mode=WAL")
    rows = db2.execute("SELECT * FROM tasks").fetchall()
    db2.close()
    assert len(rows) == 0, "uncommitted rows must not be visible to other connections"

    db.commit()

    db3 = _sqlite3.connect(str(vault / ".natalie" / "natalie.db"), check_same_thread=False)
    db3.row_factory = _sqlite3.Row
    rows2 = db3.execute("SELECT * FROM tasks").fetchall()
    db3.close()
    assert len(rows2) == 1


def test_sync_tasks_is_complete_after_call(vault, db):
    """sync_tasks must index all files and return total count in a single pass."""
    write_note(vault, "a.md", "- [ ] Task A\n- [ ] Task B\n")
    write_note(vault, "b.md", "- [ ] Task C\n")
    total = sync_tasks(db, vault)
    assert total == 3
    rows = db.execute("SELECT text FROM tasks ORDER BY text").fetchall()
    assert [r["text"] for r in rows] == ["Task A", "Task B", "Task C"]


def test_sync_tasks_concurrent_reader_never_sees_empty_table(vault, db):
    """A second connection opened after sync_tasks starts must not see an empty tasks table.

    The fix (single transaction) means readers see either the old data or the new data,
    never an empty table. We verify this by opening a reader AFTER sync_tasks commits
    and checking it sees the full result.
    """
    import sqlite3 as _sqlite3

    write_note(vault, "a.md", "- [ ] Task A\n")
    write_note(vault, "b.md", "- [ ] Task B\n")
    sync_tasks(db, vault)

    # A reader opened after sync_tasks finishes must see all rows (not 0)
    db2 = _sqlite3.connect(str(vault / ".natalie" / "natalie.db"), check_same_thread=False)
    db2.row_factory = _sqlite3.Row
    db2.execute("PRAGMA journal_mode=WAL")
    n = db2.execute("SELECT count(*) as n FROM tasks").fetchone()["n"]
    db2.close()
    assert n == 2, f"reader saw {n} tasks after sync_tasks, expected 2"
