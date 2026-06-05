from __future__ import annotations

import pytest
from watchdog.events import (
    DirCreatedEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
)

from natalie.features.tasks import index_tasks
from natalie.features.watcher import _VaultEventHandler
from tests.helpers import write_note


@pytest.fixture
def handler(vault):
    return _VaultEventHandler(vault, vault)


def test_handler_indexes_created_md(vault, db, handler):
    write_note(vault, "new.md", "- [ ] My new task\n")
    handler.on_created(FileCreatedEvent(str(vault / "new.md")))
    rows = db.execute("SELECT * FROM tasks WHERE path = 'new.md'").fetchall()
    assert len(rows) == 1
    assert rows[0]["text"] == "My new task"


def test_handler_indexes_modified_md(vault, db, handler):
    write_note(vault, "edit.md", "- [ ] Original task\n")
    index_tasks(db, vault, vault / "edit.md")
    write_note(vault, "edit.md", "- [ ] Updated task\n")
    handler.on_modified(FileModifiedEvent(str(vault / "edit.md")))
    rows = db.execute("SELECT text FROM tasks WHERE path = 'edit.md'").fetchall()
    assert len(rows) == 1
    assert rows[0]["text"] == "Updated task"


def test_handler_removes_deleted_md(vault, db, handler):
    write_note(vault, "gone.md", "- [ ] Disappearing task\n")
    index_tasks(db, vault, vault / "gone.md")
    (vault / "gone.md").unlink()
    handler.on_deleted(FileDeletedEvent(str(vault / "gone.md")))
    assert db.execute("SELECT COUNT(*) FROM tasks WHERE path = 'gone.md'").fetchone()[0] == 0


def test_handler_handles_moved_md(vault, db, handler):
    write_note(vault, "old_name.md", "- [ ] Moved task\n")
    index_tasks(db, vault, vault / "old_name.md")
    (vault / "old_name.md").rename(vault / "new_name.md")
    handler.on_moved(FileMovedEvent(str(vault / "old_name.md"), str(vault / "new_name.md")))
    assert db.execute("SELECT COUNT(*) FROM tasks WHERE path = 'old_name.md'").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM tasks WHERE path = 'new_name.md'").fetchone()[0] == 1


def test_handler_ignores_non_md_files(vault, db, handler):
    (vault / "image.png").write_bytes(b"fake png")
    handler.on_created(FileCreatedEvent(str(vault / "image.png")))
    assert db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0


def test_handler_ignores_dot_directory_files(vault, db, handler):
    dot = vault / ".obsidian"
    dot.mkdir()
    write_note(vault, ".obsidian/config.md", "- [ ] Hidden task\n")
    handler.on_created(FileCreatedEvent(str(vault / ".obsidian" / "config.md")))
    assert db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0


def test_handler_ignores_directory_events(vault, db, handler):
    subdir = vault / "Projects"
    subdir.mkdir()
    handler.on_created(DirCreatedEvent(str(subdir)))
    assert db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0


def test_start_watcher_returns_running_observer(vault):
    from natalie.features.watcher import start_watcher

    observer = start_watcher(vault, vault)
    assert observer.is_alive()
    observer.stop()
    observer.join()
