from unittest.mock import patch

import pytest

from natalie.config import DEFAULT_EMBEDDING_MODEL
from natalie.features.sync import sync_vault
from tests.helpers import get_notes, write_note


def test_sync_vault_indexes_markdown_files(vault, db):
    write_note(vault, "note1.md", "---\ntitle: Note One\n---\nContent one.")
    write_note(vault, "note2.md", "---\ntitle: Note Two\n---\nContent two.")
    with patch("natalie.features.sync.embed_notes"):
        sync_vault(db, vault)
    rows = get_notes(db)
    assert len(rows) == 2


def test_sync_vault_skips_dotfiles(vault, db):
    write_note(vault, ".natalie/skip-me.md", "Should not be indexed.")
    write_note(vault, "real.md", "Should be indexed.")
    with patch("natalie.features.sync.embed_notes"):
        sync_vault(db, vault)
    rows = get_notes(db)
    paths = [r["path"] for r in rows]
    assert "real.md" in paths
    assert not any(".natalie" in p for p in paths)


def test_sync_vault_removes_deleted_notes(vault, db):
    note = write_note(vault, "temp.md", "Temporary note.")
    with patch("natalie.features.sync.embed_notes"):
        sync_vault(db, vault)
    assert len(get_notes(db)) == 1
    note.unlink()
    with patch("natalie.features.sync.embed_notes"):
        sync_vault(db, vault, full=True)
    assert len(get_notes(db)) == 0


def test_sync_cli_command_runs(vault, db):
    from typer.testing import CliRunner

    from natalie.cli import app

    write_note(vault, "indexed.md", "---\ntitle: Indexed\n---\nContent.")
    runner = CliRunner()
    with (
        patch("natalie.cli.require_vault", return_value=vault),
        patch("natalie.cli.load_config") as mock_cfg,
        patch("natalie.cli.init_db"),
        patch("natalie.cli.get_db", return_value=db),
        patch("natalie.features.sync.embed_notes"),
    ):
        mock_cfg.return_value.memory.embedding_model = DEFAULT_EMBEDDING_MODEL
        result = runner.invoke(app, ["sync"])
    assert result.exit_code == 0
    assert "1 indexed" in result.output


def test_sync_vault_full_indexed_count_is_zero(vault, db):
    """full sync must return indexed=0 — it rebuilds from scratch, not new/changed — I2."""
    write_note(vault, "existing.md", "---\ntitle: Existing\n---\nContent.")
    with patch("natalie.features.sync.embed_notes"):
        result = sync_vault(db, vault, full=True)
    assert result["indexed"] == 0


def test_sync_vault_full_wipes_and_reindexes(vault, db):
    """--full must delete all vault rows first so DB corruption is repaired."""
    write_note(vault, "stable.md", "---\ntitle: Stable\n---\nReal content.")
    with patch("natalie.features.sync.embed_notes"):
        sync_vault(db, vault)

    # Corrupt the DB body directly — mtime is still current, so incremental skips it
    db.execute("UPDATE notes SET body = 'corrupted' WHERE path = 'stable.md'")
    db.commit()

    with patch("natalie.features.sync.embed_notes"):
        sync_vault(db, vault, full=False)  # incremental — mtime matches, skips
    row = db.execute("SELECT body FROM notes WHERE path = 'stable.md'").fetchone()
    assert row["body"] == "corrupted", "incremental must not touch unchanged mtime"

    with patch("natalie.features.sync.embed_notes"):
        sync_vault(db, vault, full=True)  # full — wipe and re-index
    row = db.execute("SELECT body FROM notes WHERE path = 'stable.md'").fetchone()
    assert row["body"] == "Real content.", "full must re-index from disk"


def test_sync_vault_removes_deleted_notes_incrementally(vault, db, monkeypatch):
    """Deleted notes must be removed on incremental sync, not only --full."""
    import natalie.features.memory as mem_mod

    class FakeModel:
        def embed(self, texts):
            import numpy as np

            return [np.ones(4, dtype=np.float32) for _ in texts]

    monkeypatch.setattr(mem_mod, "_embedding_models", {DEFAULT_EMBEDDING_MODEL: FakeModel()})

    note = vault / "will-be-deleted.md"
    note.write_text("hello")
    sync_vault(db, vault, full=False)

    row = db.execute("SELECT id FROM notes WHERE path = 'will-be-deleted.md'").fetchone()
    assert row is not None

    # Delete the file
    note.unlink()

    result = sync_vault(db, vault, full=False)  # incremental
    assert result["removed"] >= 1
    row = db.execute("SELECT id FROM notes WHERE path = 'will-be-deleted.md'").fetchone()
    assert row is None


def test_sync_vault_indexed_count_excludes_unchanged_notes(vault, db):
    """indexed count must reflect only actually re-indexed notes, not mtime-skipped ones."""
    write_note(vault, "stable.md", "---\ntitle: Stable\n---\nNo changes.")
    with patch("natalie.features.sync.embed_notes"):
        first = sync_vault(db, vault)
    assert first["indexed"] == 1

    # Second sync — mtime unchanged, index_note is a no-op
    with patch("natalie.features.sync.embed_notes"):
        second = sync_vault(db, vault)
    assert second["indexed"] == 0


def test_full_sync_preserves_notes_if_reindex_fails(vault, db):
    """I15: if index_note raises during full sync, the pre-existing notes must survive."""
    write_note(vault, "existing.md", "---\ntitle: Existing\n---\nContent.")
    with patch("natalie.features.sync.embed_notes"):
        sync_vault(db, vault)

    before = db.execute("SELECT COUNT(*) FROM notes WHERE machine_mac IS NULL").fetchone()[0]
    assert before == 1

    # Simulate a crash during re-index by making index_note raise
    with (
        patch("natalie.features.sync.embed_notes"),
        patch("natalie.features.sync.index_note", side_effect=OSError("disk full")),
        pytest.raises(OSError),
    ):
        sync_vault(db, vault, full=True)

    # Roll back the uncommitted DELETE — simulates what SQLite WAL does on process crash.
    # With the old code the DELETE was committed before re-index, so rollback does nothing.
    # With the fix the DELETE is uncommitted, so rollback restores the notes.
    db.rollback()
    after = db.execute("SELECT COUNT(*) FROM notes WHERE machine_mac IS NULL").fetchone()[0]
    assert after == 1, "notes must survive rollback after failed full-sync"


def test_sync_vault_indexes_tasks(vault, db):
    write_note(vault, "tasks.md", "- [ ] Do something\n- [ ] Do another\n")
    with patch("natalie.features.sync.embed_notes"):
        sync_vault(db, vault)
    rows = db.execute("SELECT * FROM tasks").fetchall()
    assert len(rows) == 2


def test_sync_vault_full_clears_and_rebuilds_tasks(vault, db):
    write_note(vault, "tasks.md", "- [ ] Old task\n")
    with patch("natalie.features.sync.embed_notes"):
        sync_vault(db, vault)
    write_note(vault, "tasks.md", "- [ ] New task\n")
    with patch("natalie.features.sync.embed_notes"):
        sync_vault(db, vault, full=True)
    rows = db.execute("SELECT text FROM tasks").fetchall()
    assert len(rows) == 1
    assert rows[0]["text"] == "New task"


def test_sync_vault_removes_tasks_for_deleted_notes(vault, db):
    note = write_note(vault, "tasks.md", "- [ ] Disappearing task\n")
    with patch("natalie.features.sync.embed_notes"):
        sync_vault(db, vault)
    note.unlink()
    with patch("natalie.features.sync.embed_notes"):
        sync_vault(db, vault)
    assert db.execute("SELECT COUNT(*) FROM tasks WHERE path = 'tasks.md'").fetchone()[0] == 0


def test_sync_vault_works_with_symlinked_vault(vault, db):
    """sync_vault must not raise ValueError when vault is accessed via a symlink — B1."""
    import os
    import tempfile
    from pathlib import Path

    write_note(vault, "test.md", "---\ntitle: Test\n---\nContent")
    with tempfile.TemporaryDirectory() as td:
        link = Path(td) / "vault_link"
        os.symlink(vault, link)
        with patch("natalie.features.sync.embed_notes"):
            result = sync_vault(db, link)
    assert result["indexed"] >= 1


def test_sync_vault_defers_task_commits(vault, db):
    """sync_vault must commit task inserts once after the loop, not per-file."""
    import sqlite3 as _sqlite3

    write_note(vault, "a.md", "- [ ] Task A\n")
    write_note(vault, "b.md", "- [ ] Task B\n")

    with patch("natalie.features.sync.embed_notes"):
        sync_vault(db, vault)

    # A reader opened after sync_vault finishes must see all task rows
    db2 = _sqlite3.connect(str(vault / ".natalie" / "natalie.db"), check_same_thread=False)
    db2.row_factory = _sqlite3.Row
    db2.execute("PRAGMA journal_mode=WAL")
    n = db2.execute("SELECT count(*) as n FROM tasks").fetchone()["n"]
    db2.close()
    assert n == 2, f"expected 2 tasks after sync_vault, got {n}"
