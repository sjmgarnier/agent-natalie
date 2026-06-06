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


def test_handler_on_created_exception_does_not_propagate(vault, db, handler):
    """An exception in _index_file must not escape the event handler and kill the observer thread."""
    from unittest.mock import patch

    with patch.object(handler, "_index_file", side_effect=OSError("Permission denied")):
        # Should not raise — handler must absorb the error
        handler.on_created(FileCreatedEvent(str(vault / "any.md")))


def test_start_watcher_returns_running_observer(vault):
    from natalie.features.watcher import start_watcher

    observer = start_watcher(vault, vault)
    assert observer.is_alive()
    observer.stop()
    observer.join()


def test_handler_on_modified_exception_is_logged(vault, db, handler, caplog):
    import logging
    from unittest.mock import patch

    with caplog.at_level(logging.ERROR, logger="natalie.features.watcher"):
        with patch.object(handler, "_index_file", side_effect=RuntimeError("disk full")):
            handler.on_modified(FileModifiedEvent(str(vault / "note.md")))

    # The exception is logged via _log.exception — check a watcher ERROR record was emitted
    watcher_errors = [
        r for r in caplog.records if r.name == "natalie.features.watcher" and r.levelno >= logging.ERROR
    ]
    assert watcher_errors, "expected at least one ERROR log record from watcher"


def test_handler_on_deleted_exception_is_logged(vault, db, handler, caplog):
    import logging
    from unittest.mock import patch

    with caplog.at_level(logging.ERROR, logger="natalie.features.watcher"):
        with patch.object(handler, "_remove_file", side_effect=RuntimeError("disk full")):
            handler.on_deleted(FileDeletedEvent(str(vault / "gone.md")))

    watcher_errors = [
        r for r in caplog.records if r.name == "natalie.features.watcher" and r.levelno >= logging.ERROR
    ]
    assert watcher_errors, "expected at least one ERROR log record from watcher"


def test_handler_on_moved_from_outside_vault_only_indexes_dest(vault, db):
    import tempfile

    handler = _VaultEventHandler(vault, vault)
    indexed: list[str] = []
    removed: list[str] = []
    handler._index_file = lambda p: indexed.append(p)  # type: ignore[method-assign]
    handler._remove_file = lambda p: removed.append(p)  # type: ignore[method-assign]

    with tempfile.TemporaryDirectory() as external_dir:
        from pathlib import Path as _Path

        outside = _Path(external_dir) / "external.md"
        outside.write_text("x", encoding="utf-8")
        dest = vault / "arrived.md"
        dest.write_text("x", encoding="utf-8")

        handler.on_moved(FileMovedEvent(str(outside), str(dest)))

    assert indexed == [str(dest)]
    assert removed == []


def test_handler_on_moved_to_outside_vault_only_removes_src(vault, db):
    import tempfile

    handler = _VaultEventHandler(vault, vault)
    indexed: list[str] = []
    removed: list[str] = []
    handler._index_file = lambda p: indexed.append(p)  # type: ignore[method-assign]
    handler._remove_file = lambda p: removed.append(p)  # type: ignore[method-assign]

    src = vault / "leaving.md"
    src.write_text("x", encoding="utf-8")

    with tempfile.TemporaryDirectory() as external_dir:
        from pathlib import Path as _Path

        dest = _Path(external_dir) / "external.md"
        handler.on_moved(FileMovedEvent(str(src), str(dest)))

    assert removed == [str(src)]
    assert indexed == []
