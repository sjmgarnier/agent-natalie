from __future__ import annotations

import struct
import time

from natalie.features.browse import list_notes, vault_stats
from natalie.features.memory import index_note
from natalie.features.sync import sync_vault
from natalie.features.tasks import index_tasks
from tests.helpers import write_note


def test_list_notes_returns_all_vault_notes(vault, db):
    p1 = write_note(vault, "Notes/alpha.md", "# Alpha\nContent")
    p2 = write_note(vault, "Projects/beta.md", "# Beta\nContent")
    index_note(db, vault, p1)
    index_note(db, vault, p2)

    results = list_notes(db)
    paths = [r["path"] for r in results]
    assert "Notes/alpha.md" in paths
    assert "Projects/beta.md" in paths
    assert all("path" in r and "title" in r and "last_modified" in r for r in results)


def test_list_notes_directory_filter(vault, db):
    p1 = write_note(vault, "Projects/alpha.md", "# Alpha")
    p2 = write_note(vault, "Notes/beta.md", "# Beta")
    index_note(db, vault, p1)
    index_note(db, vault, p2)

    results = list_notes(db, directory="Projects")
    assert len(results) == 1
    assert results[0]["path"] == "Projects/alpha.md"


def test_list_notes_excludes_memory_entries(vault, db):
    db.execute(
        "INSERT INTO notes (path, title, body, last_modified, collection, machine_mac)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (".natalie/entries/abc/entry.md", "Memory", "content", time.time(), "global", "aabbccddeeff"),
    )
    db.commit()

    results = list_notes(db)
    assert all(r["path"] != ".natalie/entries/abc/entry.md" for r in results)


def test_list_notes_empty_directory(vault, db):
    results = list_notes(db, directory="NonExistent")
    assert results == []


def test_vault_stats_counts(vault, db):
    p1 = write_note(vault, "Notes/a.md", "# A\n- [ ] Task one")
    p2 = write_note(vault, "Notes/b.md", "# B")
    index_note(db, vault, p1)
    index_note(db, vault, p2)
    index_tasks(db, vault, p1)

    db.execute(
        "INSERT INTO notes (path, title, body, last_modified, collection, machine_mac)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (".natalie/entries/xx/mem.md", "Mem", "body", time.time(), "global", "aabbccddeeff"),
    )
    db.commit()

    stats = vault_stats(db)
    assert stats["vault_notes"] == 2
    assert stats["memory_entries"] == 1
    assert stats["open_tasks"] == 1


def test_vault_stats_embedding_coverage(vault, db):
    p1 = write_note(vault, "Notes/a.md", "# A")
    p2 = write_note(vault, "Notes/b.md", "# B")
    index_note(db, vault, p1)
    index_note(db, vault, p2)

    note_id = db.execute("SELECT id FROM notes WHERE path = ?", ("Notes/a.md",)).fetchone()[0]
    vector = struct.pack("4f", 0.1, 0.2, 0.3, 0.4)
    db.execute("INSERT INTO embeddings (note_id, vector) VALUES (?, ?)", (note_id, vector))
    db.commit()

    stats = vault_stats(db)
    assert stats["embedding_coverage_pct"] == 50.0


def test_vault_stats_last_synced_none(vault, db):
    stats = vault_stats(db)
    assert stats["last_synced_at"] is None


def test_vault_stats_last_synced(vault, db):
    before = time.time()
    sync_vault(db, vault)
    after = time.time()

    stats = vault_stats(db)
    assert stats["last_synced_at"] is not None
    assert before <= stats["last_synced_at"] <= after


def test_sync_log_trigger(vault, db):
    sync_vault(db, vault, trigger="manual")

    row = db.execute("SELECT trigger FROM sync_log ORDER BY id DESC LIMIT 1").fetchone()
    assert row is not None
    assert row[0] == "manual"
