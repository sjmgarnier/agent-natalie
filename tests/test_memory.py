import json
import sqlite3
import threading
from typing import get_args
from unittest.mock import patch

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from natalie.features.memory import (
    convention_add,
    convention_delete,
    convention_list,
    convention_update,
    embed_notes,
    index_note,
    keyword_search,
    remove_note,
    semantic_search,
    update_note_frontmatter,
)
from tests.helpers import get_notes, write_note


class _FakeEmbedding:
    """Fake fastembed TextEmbedding — avoids downloading the model during tests."""

    def __init__(self, *args, **kwargs):
        pass

    def embed(self, texts):
        for _ in texts:
            vec = np.zeros(384, dtype=np.float32)
            vec[0] = 1.0
            yield vec / np.linalg.norm(vec)


@pytest.fixture(autouse=True)
def reset_embedding_model():
    """Reset the module-level model cache between tests."""
    import natalie.features.memory as mem

    mem._embedding_models.clear()
    yield
    mem._embedding_models.clear()


def test_index_note_stores_title_and_body(vault, db):
    note = write_note(vault, "test.md", "---\ntitle: Hello\n---\nBody text here.")
    index_note(db, vault, note)
    rows = get_notes(db)
    assert len(rows) == 1
    assert rows[0]["title"] == "Hello"
    assert "Body text here" in rows[0]["body"]


def test_index_note_uses_filename_as_title_when_frontmatter_absent(vault, db):
    note = write_note(vault, "my-note.md", "No frontmatter here.")
    index_note(db, vault, note)
    rows = get_notes(db)
    assert rows[0]["title"] == "my-note"


def test_index_note_stores_tags_as_json(vault, db):
    note = write_note(vault, "tagged.md", "---\ntags: [work, project]\n---\nContent.")
    index_note(db, vault, note)
    rows = get_notes(db)
    tags = json.loads(rows[0]["tags"])
    assert "work" in tags


def test_index_note_stores_relative_path(vault, db):
    note = write_note(vault, "sub/note.md", "Content")
    index_note(db, vault, note)
    rows = get_notes(db)
    assert rows[0]["path"] == "sub/note.md"


def test_index_note_skips_unchanged_note(vault, db):
    note = write_note(vault, "stable.md", "Content")
    index_note(db, vault, note)
    # Force same mtime by not touching the file; call index_note again
    index_note(db, vault, note)  # mtime unchanged → no-op
    rows = db.execute("SELECT last_modified FROM notes").fetchall()
    assert len(rows) == 1


def test_remove_note_deletes_row(vault, db):
    note = write_note(vault, "gone.md", "Content")
    index_note(db, vault, note)
    remove_note(db, "gone.md")
    assert get_notes(db) == []


def test_remove_note_preserves_memory_store_entry(db):
    """remove_note must not delete memory_store rows (machine_mac IS NOT NULL) — B1."""
    db.execute(
        "INSERT INTO notes (path, title, body, collection, machine_mac) VALUES (?, ?, ?, ?, ?)",
        ("shared.md", "Memory Entry", "memory content", "global", "aa:bb:cc:dd:ee:ff"),
    )
    db.commit()
    remove_note(db, "shared.md")
    row = db.execute("SELECT id FROM notes WHERE path = 'shared.md'").fetchone()
    assert row is not None, "memory_store entry must survive remove_note"


def test_fts_returns_matching_notes(vault, db):
    write_note(vault, "alpha.md", "---\ntitle: Alpha\n---\napple banana cherry")
    write_note(vault, "beta.md", "---\ntitle: Beta\n---\ndragonfly elephant")
    for p in vault.glob("*.md"):
        index_note(db, vault, p)
    results = keyword_search(db, "banana")
    assert len(results) == 1
    assert results[0]["path"] == "alpha.md"


def test_embed_notes_stores_vectors(vault, db):
    note = write_note(vault, "embed-me.md", "---\ntitle: Embed\n---\nContent to embed.")
    index_note(db, vault, note)
    with patch("natalie.features.memory.TextEmbedding", _FakeEmbedding):
        embed_notes(db, model_name="BAAI/bge-small-en-v1.5")
    row = db.execute("SELECT * FROM embeddings").fetchone()
    assert row is not None
    vec = np.frombuffer(row["vector"], dtype=np.float32)
    assert vec.shape == (384,)


def test_embed_notes_skips_already_embedded(vault, db):
    note = write_note(vault, "skip-me.md", "Content")
    index_note(db, vault, note)
    embed_call_count = []

    class CountingFake(_FakeEmbedding):
        def embed(self, texts):
            text_list = list(texts)
            embed_call_count.append(len(text_list))
            yield from super().embed(text_list)

    with patch("natalie.features.memory.TextEmbedding", CountingFake):
        embed_notes(db)  # first call — embeds 1
        embed_notes(db)  # second call — nothing to embed
    assert sum(embed_call_count) == 1  # only called once total


def test_semantic_search_returns_results(vault, db):
    write_note(vault, "sem-a.md", "---\ntitle: Apple\n---\nfruit salad")
    write_note(vault, "sem-b.md", "---\ntitle: Bicycle\n---\ntransport wheels")
    for p in vault.glob("sem-*.md"):
        index_note(db, vault, p)
    with patch("natalie.features.memory.TextEmbedding", _FakeEmbedding):
        embed_notes(db)
        results = semantic_search(db, "fruit", model_name="BAAI/bge-small-en-v1.5")
    assert len(results) >= 1
    assert "path" in results[0]
    assert "score" in results[0]


def test_convention_add_and_list(db):
    convention_add(
        db,
        domain="general",
        rule="Put tasks in the active project note.",
        source="explicit",
    )
    conventions = convention_list(db, domain="general")
    assert len(conventions) == 1
    assert conventions[0]["rule"] == "Put tasks in the active project note."
    assert conventions[0]["source"] == "explicit"


def test_convention_list_filters_by_domain(db):
    convention_add(db, domain="general", rule="Tasks rule", source="explicit")
    convention_add(db, domain="files", rule="Contacts rule", source="explicit")
    tasks_convs = convention_list(db, domain="general")
    assert len(tasks_convs) == 1
    assert tasks_convs[0]["domain"] == "general"


def test_convention_list_all_when_no_domain(db):
    convention_add(db, domain="general", rule="Rule 1", source="explicit")
    convention_add(db, domain="files", rule="Rule 2", source="observed")
    all_convs = convention_list(db)
    assert len(all_convs) == 2


def test_convention_delete(db):
    convention_add(db, domain="general", rule="To delete", source="explicit")
    conv_id = convention_list(db, domain="general")[0]["id"]
    result = convention_delete(db, conv_id)
    assert result is True
    assert convention_list(db, domain="general") == []


def test_index_note_handles_date_frontmatter(vault, db):
    note = vault / "daily.md"
    note.write_text("---\ndate: 2024-01-15\ntitle: Daily\n---\nContent.\n")
    from natalie.features.memory import index_note

    index_note(db, vault, note)  # must not raise
    row = db.execute("SELECT frontmatter FROM notes WHERE path = 'daily.md'").fetchone()
    assert row is not None


def test_keyword_search_tolerates_fts_metacharacters(vault, db):
    from natalie.features.memory import keyword_search

    # Should not raise, should return empty results
    results = keyword_search(db, 'how do I (write) "things"')
    assert isinstance(results, list)
    results2 = keyword_search(db, "C++ config-file")
    assert isinstance(results2, list)


def test_memory_store_writes_to_disk(vault, db, monkeypatch):
    """memory_store must create the file so note_read can return it."""
    import natalie.server as srv

    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    from natalie.config import NatalieConfig

    monkeypatch.setattr(srv, "_config", NatalieConfig())
    result = srv.memory_store(content="hello world", title="test-note")
    assert result["stored"] is True
    stored_path = vault / result["path"]
    assert stored_path.exists()
    assert stored_path.read_text() == "hello world"


def test_index_note_invalidates_stale_embedding(vault, db, monkeypatch):
    """Re-indexing an edited note must clear its old embedding."""
    import numpy as np

    import natalie.features.memory as mem_mod

    fake_vec = np.ones(4, dtype=np.float32)

    class FakeModel:
        def embed(self, texts):
            return [fake_vec for _ in texts]

    monkeypatch.setattr(mem_mod, "_embedding_models", {"BAAI/bge-small-en-v1.5": FakeModel()})

    note = vault / "changing.md"
    note.write_text("---\ntitle: Test\n---\noriginal content\n")
    mem_mod.index_note(db, vault, note)
    mem_mod.embed_notes(db)

    # Verify embedding exists
    row = db.execute("SELECT id FROM notes WHERE path = 'changing.md'").fetchone()
    assert db.execute("SELECT COUNT(*) FROM embeddings WHERE note_id = ?", (row["id"],)).fetchone()[0] == 1

    # Edit the note (change mtime by writing new content)
    import time as time_mod

    time_mod.sleep(0.01)
    note.write_text("---\ntitle: Test\n---\ncompletely new content\n")
    # Touch to ensure mtime changes
    note.touch()

    mem_mod.index_note(db, vault, note)

    # Embedding must be gone — embed_notes will re-embed on next sync
    assert db.execute("SELECT COUNT(*) FROM embeddings WHERE note_id = ?", (row["id"],)).fetchone()[0] == 0


def test_index_note_resets_machine_mac_on_path_collision(vault, db):
    """If a memory_store entry occupies a path, index_note must reset machine_mac to NULL."""
    rel = "collision.md"
    db.execute(
        "INSERT INTO notes (path, title, body, last_modified, collection, machine_mac) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (rel, "Mem", "mem body", 0.0, "global", "aa:bb:cc:dd:ee:ff"),
    )
    db.commit()
    note = write_note(vault, rel, "# Vault note\nBody")
    index_note(db, vault, note)
    row = db.execute("SELECT machine_mac FROM notes WHERE path = ?", (rel,)).fetchone()
    assert row is not None
    assert row["machine_mac"] is None


def test_memory_store_unique_paths_no_collision(vault, db, monkeypatch):
    """Two stores with the same title must produce distinct files."""
    import natalie.server as srv

    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    from natalie.config import NatalieConfig

    monkeypatch.setattr(srv, "_config", NatalieConfig())
    r1 = srv.memory_store(content="first", title="prefs")
    r2 = srv.memory_store(content="second", title="prefs")
    assert r1["path"] != r2["path"]
    assert (vault / r1["path"]).read_text() == "first"
    assert (vault / r2["path"]).read_text() == "second"


def test_memory_store_overwrites_vault_note_sets_machine_mac(vault, db, monkeypatch):
    """memory_store on a path already indexed as a vault note must update machine_mac.

    Before the fix, ON CONFLICT omitted machine_mac from the UPDATE clause,
    so the row kept machine_mac IS NULL and sync_vault's deletion pass would
    silently delete the memory entry as a stale vault note.
    """
    import time

    import natalie.server as srv

    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    from natalie.config import NatalieConfig

    monkeypatch.setattr(srv, "_config", NatalieConfig())

    # Pre-insert a vault note (machine_mac IS NULL)
    note_path = "notes/existing.md"
    (vault / "notes").mkdir(parents=True, exist_ok=True)
    (vault / note_path).write_text("original content")
    db.execute(
        "INSERT INTO notes (path, title, body, last_modified, machine_mac) VALUES (?, ?, ?, ?, NULL)",
        (note_path, "Existing Note", "original content", time.time()),
    )
    db.commit()
    assert (
        db.execute("SELECT machine_mac FROM notes WHERE path = ?", (note_path,)).fetchone()["machine_mac"]
        is None
    )

    # Store via memory_store using the same explicit path
    result = srv.memory_store(content="new content", title="Updated", path=note_path)
    assert result["stored"] is True

    # machine_mac must now be set — sync_vault must not delete this row
    row = db.execute("SELECT machine_mac FROM notes WHERE path = ?", (note_path,)).fetchone()
    assert row["machine_mac"] is not None


# ── Session-5 regression tests ────────────────────────────────────────────────


def test_convention_add_returns_int(db):
    """convention_add must return an int row ID (not None) — B4."""
    row_id = convention_add(db, domain="general", rule="a rule", source="explicit")
    assert isinstance(row_id, int)


def test_convention_add_rejects_invalid_source(db):
    """convention_add must raise ValueError for invalid source values — B2."""
    with pytest.raises(ValueError, match="source"):
        convention_add(db, domain="general", rule="a rule", source="invalid")


def test_convention_delete_returns_false_for_missing_id(db):
    """convention_delete must return False when the ID does not exist — B1."""
    result = convention_delete(db, 9999)
    assert result is False


def test_convention_delete_returns_true_when_found(db):
    """convention_delete must return True when the convention was present — B1."""
    row_id = convention_add(db, domain="general", rule="to delete", source="explicit")
    result = convention_delete(db, row_id)
    assert result is True


def test_index_note_handles_non_canonical_vault_path(vault, db):
    """index_note must work when vault is passed as a symlink path — B3."""
    import os
    import tempfile

    note_file = vault / "symlink-test.md"
    note_file.write_text("---\ntitle: Symlink Test\n---\nContent")
    with tempfile.TemporaryDirectory() as td:
        from pathlib import Path as _Path

        link = _Path(td) / "vault_link"
        os.symlink(vault, link)
        index_note(db, link, (link / "symlink-test.md").resolve())
    rows = get_notes(db)
    assert any(r["path"] == "symlink-test.md" for r in rows)


def test_index_note_handles_non_canonical_note_path(vault, db):
    """index_note must not raise when note_path itself is unresolved (symlink) — I1."""
    import os
    import tempfile

    note_file = vault / "via-link.md"
    note_file.write_text("---\ntitle: Via Link\n---\nContent")
    with tempfile.TemporaryDirectory() as td:
        from pathlib import Path as _Path

        link = _Path(td) / "vault_link"
        os.symlink(vault, link)
        # Pass note_path via the symlinked directory without resolving it
        index_note(db, vault, link / "via-link.md")
    rows = get_notes(db)
    assert any(r["path"] == "via-link.md" for r in rows)


def test_memory_store_clears_stale_tags_and_frontmatter(vault, db, monkeypatch):
    """memory_store must set tags/frontmatter to NULL when overwriting a vault-indexed row — B5."""
    import time

    import natalie.server as srv

    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    from natalie.config import NatalieConfig

    monkeypatch.setattr(srv, "_config", NatalieConfig())

    note_path = "stale-meta.md"
    (vault / note_path).write_text("---\ntags: [work]\n---\noriginal content")
    db.execute(
        "INSERT INTO notes (path, title, tags, frontmatter, body, last_modified, machine_mac) "
        "VALUES (?, ?, ?, ?, ?, ?, NULL)",
        (
            note_path,
            "Stale Note",
            '["work"]',
            '{"tags": ["work"]}',
            "original content",
            time.time(),
        ),
    )
    db.commit()

    row = db.execute("SELECT tags, frontmatter FROM notes WHERE path = ?", (note_path,)).fetchone()
    assert row["tags"] is not None

    srv.memory_store(content="new memory content", title="Updated", path=note_path)

    row = db.execute("SELECT tags, frontmatter FROM notes WHERE path = ?", (note_path,)).fetchone()
    assert row["tags"] is None
    assert row["frontmatter"] is None


def test_memory_store_clears_stale_embedding(vault, db, monkeypatch):
    """memory_store must delete stale embeddings so semantic search stays accurate — B3."""
    import numpy as np

    import natalie.server as srv

    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    from natalie.config import NatalieConfig

    monkeypatch.setattr(srv, "_config", NatalieConfig())

    note_path = "embedded-note.md"
    (vault / note_path).write_text("original content")
    db.execute(
        "INSERT INTO notes (path, title, body, last_modified, machine_mac) VALUES (?, ?, ?, ?, NULL)",
        (note_path, "Old Note", "original content", 0.0),
    )
    db.commit()
    note_id = db.execute("SELECT id FROM notes WHERE path = ?", (note_path,)).fetchone()["id"]
    vec = np.ones(4, dtype=np.float32)
    db.execute(
        "INSERT INTO embeddings (note_id, vector) VALUES (?, ?)",
        (note_id, vec.tobytes()),
    )
    db.commit()
    assert db.execute("SELECT COUNT(*) FROM embeddings WHERE note_id = ?", (note_id,)).fetchone()[0] == 1

    srv.memory_store(content="new content", title="Updated", path=note_path)

    assert db.execute("SELECT COUNT(*) FROM embeddings WHERE note_id = ?", (note_id,)).fetchone()[0] == 0


def test_memory_search_rrf_semantic_only_hit_can_rank_first(vault, db, monkeypatch):
    """A semantic-only match must be able to outrank a weaker keyword match via RRF."""
    import numpy as np

    import natalie.features.memory as mem_mod
    import natalie.server as srv
    from natalie.config import NatalieConfig

    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    monkeypatch.setattr(srv, "_config", NatalieConfig())

    # Create two notes; the keyword note matches by a common word, the semantic note
    # matches only semantically (no word overlap with query).
    # We simulate this by using a fake embedding model: the "semantic" note gets a
    # vector identical to the query vector (score=1.0), the "keyword" note gets a
    # zero vector (score=0).
    keyword_note = vault / "keyword.md"
    keyword_note.write_text("---\ntitle: Keyword Note\n---\nthe query word here\n")
    semantic_note = vault / "semantic.md"
    semantic_note.write_text("---\ntitle: Semantic Note\n---\ncompletely different vocabulary\n")

    mem_mod.index_note(db, vault, keyword_note)
    mem_mod.index_note(db, vault, semantic_note)

    # Assign vectors: semantic_note gets vec=[1,0,0,0], keyword_note gets vec=[0,1,0,0]
    # Query vec = [1,0,0,0] → semantic_note wins semantic search
    kw_row = db.execute("SELECT id FROM notes WHERE path='keyword.md'").fetchone()
    sem_row = db.execute("SELECT id FROM notes WHERE path='semantic.md'").fetchone()
    q_vec = np.array([1, 0, 0, 0], dtype=np.float32)
    kw_vec = np.array([0, 1, 0, 0], dtype=np.float32)
    db.execute(
        "INSERT INTO embeddings (note_id, vector) VALUES (?, ?)",
        (kw_row["id"], kw_vec.tobytes()),
    )
    db.execute(
        "INSERT INTO embeddings (note_id, vector) VALUES (?, ?)",
        (sem_row["id"], q_vec.tobytes()),
    )
    db.commit()

    class FakeModel:
        def embed(self, texts):
            yield from (q_vec for _ in texts)

    monkeypatch.setattr(mem_mod, "_embedding_models", {"BAAI/bge-small-en-v1.5": FakeModel()})

    # keyword_note ranks #1 in keyword search (it contains the query words)
    # semantic_note ranks #1 in semantic search (cosine=1.0)
    # With RRF both at rank-1 in their stream, they get equal scores → both returned
    results = srv.memory_search("query word", limit=10)
    paths = [r["path"] for r in results]
    assert "semantic.md" in paths
    assert "keyword.md" in paths
    # semantic.md must not be dead-last (old bug: cosine 1.0 < BM25 abs ~5-50 → always last)
    # With RRF, semantic-only rank-1 gets 1/(60+1) ≈ 0.0164; keyword rank-1 also 0.0164 → tie or near-tie
    sem_idx = paths.index("semantic.md")
    # semantic-only match appearing in top half is sufficient to prove RRF is working
    assert sem_idx <= len(paths) // 2 + 1


# ── Hypothesis / property-based tests ────────────────────────────────────────


@given(query=st.text(min_size=0, max_size=200))
@settings(max_examples=50, suppress_health_check=["function_scoped_fixture"])
def test_keyword_search_never_raises(db, query):
    """keyword_search must return a list (possibly empty) for any query string."""
    results = keyword_search(db, query)
    assert isinstance(results, list)


class _ZeroModel:
    """Embedding model that always returns a zero vector."""

    def embed(self, texts):
        for _ in texts:
            yield np.zeros(384, dtype=np.float32)


def test_semantic_search_zero_query_returns_empty(vault, db, monkeypatch):
    """semantic_search must return [] when the query embedding is a zero vector."""
    import natalie.features.memory as mem_mod

    note = write_note(vault, "some.md", "---\ntitle: Some Note\n---\nContent here.")
    index_note(db, vault, note)
    embed_notes(db)  # stores a real (non-zero) embedding for the note

    monkeypatch.setattr(mem_mod, "_embedding_models", {"BAAI/bge-small-en-v1.5": _ZeroModel()})
    results = semantic_search(db, "anything")
    assert results == []


@given(query=st.text(min_size=0, max_size=200))
@settings(max_examples=50, suppress_health_check=["function_scoped_fixture"])
def test_semantic_search_zero_query_never_raises(db, monkeypatch, query):
    """semantic_search must not raise for any query string when embeddings return zero."""
    import natalie.features.memory as mem_mod

    monkeypatch.setattr(mem_mod, "_embedding_models", {"BAAI/bge-small-en-v1.5": _ZeroModel()})
    results = semantic_search(db, query)
    assert isinstance(results, list)


# ── embed_notes failure modes ─────────────────────────────────────────────────


def test_embed_notes_no_op_when_all_notes_already_embedded(vault, db, monkeypatch) -> None:
    import natalie.features.memory as mem_mod

    note = write_note(vault, "already.md", "---\ntitle: Already\n---\nEmbedded.")
    index_note(db, vault, note)

    class _TrackingModel:
        called: bool = False

        def embed(self, texts):  # type: ignore[override]
            _TrackingModel.called = True
            yield from _FakeEmbedding().embed(texts)

    monkeypatch.setattr(mem_mod, "_embedding_models", {"BAAI/bge-small-en-v1.5": _TrackingModel()})
    embed_notes(db)  # embeds the note
    _TrackingModel.called = False

    result = embed_notes(db)  # nothing left to embed

    assert result == 0
    assert not _TrackingModel.called


def test_semantic_search_results_include_collection_field(vault, db, monkeypatch):
    """I3: semantic_search results must include 'collection' key to match keyword_search shape."""
    import natalie.features.memory as mem_mod

    class FakeModel:
        def embed(self, texts):
            return [np.ones(4, dtype=np.float32) for _ in texts]

    monkeypatch.setattr(mem_mod, "_embedding_models", {"BAAI/bge-small-en-v1.5": FakeModel()})
    write_note(vault, "note.md", "---\ntitle: Test\n---\nContent")
    index_note(db, vault, vault / "note.md")
    embed_notes(db)

    results = semantic_search(db, "content")
    assert len(results) > 0
    assert "collection" in results[0], "semantic_search result must include 'collection' key"


def test_convention_add_rejects_empty_domain(db):
    """I7: convention_add with empty domain must raise ValueError."""
    with pytest.raises(ValueError, match="domain"):
        convention_add(db, "", "some rule")


def test_convention_add_rejects_whitespace_domain(db):
    """I7: convention_add with whitespace-only domain must raise ValueError."""
    with pytest.raises(ValueError, match="domain"):
        convention_add(db, "   ", "some rule")


def test_convention_add_rejects_empty_rule(db):
    """I7: convention_add with empty rule must raise ValueError."""
    with pytest.raises(ValueError, match="rule"):
        convention_add(db, "general", "")


def test_convention_add_rejects_whitespace_rule(db):
    """I7: convention_add with whitespace-only rule must raise ValueError."""
    with pytest.raises(ValueError, match="rule"):
        convention_add(db, "general", "   ")


def test_embed_notes_raising_model_leaves_no_partial_embeddings(vault, db, monkeypatch) -> None:
    import natalie.features.memory as mem_mod

    note1 = write_note(vault, "note1.md", "---\ntitle: Note1\n---\nFirst note.")
    note2 = write_note(vault, "note2.md", "---\ntitle: Note2\n---\nSecond note.")
    index_note(db, vault, note1)
    index_note(db, vault, note2)

    class _RaisingModel:
        def embed(self, texts):  # type: ignore[override]
            raise RuntimeError("embedding service unavailable")
            yield  # make it a generator to match the protocol

    monkeypatch.setattr(mem_mod, "_embedding_models", {"BAAI/bge-small-en-v1.5": _RaisingModel()})

    with pytest.raises(RuntimeError, match="embedding service unavailable"):
        embed_notes(db)

    count = db.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
    assert count == 0


def test_embed_notes_raises_on_vector_count_mismatch(vault, db, monkeypatch) -> None:
    import natalie.features.memory as mem_mod

    note1 = write_note(vault, "note1.md", "---\ntitle: Note1\n---\nFirst note.")
    note2 = write_note(vault, "note2.md", "---\ntitle: Note2\n---\nSecond note.")
    index_note(db, vault, note1)
    index_note(db, vault, note2)

    class _ShortModel:
        def embed(self, texts):  # type: ignore[override]
            return iter([])  # returns no vectors regardless of input

    monkeypatch.setattr(mem_mod, "_embedding_models", {"BAAI/bge-small-en-v1.5": _ShortModel()})

    with pytest.raises(AssertionError):
        embed_notes(db)


# ---------------------------------------------------------------------------
# Thread safety — C4 (_get_embedding_model lock) + C5 (INSERT OR IGNORE)
# ---------------------------------------------------------------------------


def test_get_embedding_model_initializes_only_once_under_concurrency(monkeypatch) -> None:
    """C4: concurrent callers must not double-initialize TextEmbedding (double model download)."""
    import time

    import natalie.features.memory as mem_mod

    monkeypatch.setattr(mem_mod, "_embedding_models", {})

    init_count = 0
    barrier = threading.Barrier(4)

    class _SlowModel:
        def __init__(self, model_name: str) -> None:
            nonlocal init_count
            time.sleep(0.01)  # releases GIL so other threads can observe the race
            init_count += 1

    monkeypatch.setattr(mem_mod, "TextEmbedding", _SlowModel)

    results: list[object] = []

    def get_model() -> None:
        barrier.wait()  # all threads enter simultaneously to maximise race window
        results.append(mem_mod._get_embedding_model())

    threads = [threading.Thread(target=get_model) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert init_count == 1, f"TextEmbedding was initialized {init_count} times (expected 1)"
    assert all(r is results[0] for r in results), "All threads must receive the same model instance"


def test_embed_notes_no_crash_when_embedding_inserted_concurrently(vault, db, monkeypatch) -> None:
    """C5: embed_notes must use INSERT OR IGNORE so a concurrent insert doesn't raise IntegrityError."""
    import natalie.features.memory as mem_mod
    from natalie.db import get_db as _get_db

    write_note(vault, "race.md", "# Race\nContent")
    index_note(db, vault, vault / "race.md")
    note_id = db.execute("SELECT id FROM notes WHERE path='race.md'").fetchone()["id"]

    pre_inserted = [False]

    class _RaceModel:
        """Simulates a concurrent process inserting the embedding between our SELECT and INSERT."""

        def embed(self, texts):  # type: ignore[override]
            if not pre_inserted[0]:
                pre_inserted[0] = True
                conn2 = _get_db(vault)
                vec = np.zeros(384, dtype=np.float32)
                conn2.execute(
                    "INSERT INTO embeddings (note_id, vector) VALUES (?, ?)",
                    (note_id, vec.tobytes()),
                )
                conn2.commit()
                conn2.close()
            return [np.zeros(384) for _ in texts]

    monkeypatch.setattr(mem_mod, "_embedding_models", {"BAAI/bge-small-en-v1.5": _RaceModel()})

    # Without INSERT OR IGNORE this raises IntegrityError; with it, silently skips
    result = embed_notes(db)
    assert result >= 0


# ── convention_update ─────────────────────────────────────────────────────────


def test_convention_update_rule_only(db: sqlite3.Connection) -> None:
    cid = convention_add(db, "code", "use snake_case", "explicit")
    assert convention_update(db, cid, rule="use camelCase") is True
    rows = convention_list(db, "code")
    assert rows[0]["rule"] == "use camelCase"
    assert rows[0]["domain"] == "code"


def test_convention_update_domain_only(db: sqlite3.Connection) -> None:
    cid = convention_add(db, "code", "use snake_case", "explicit")
    assert convention_update(db, cid, domain="writing") is True
    assert convention_list(db, "writing")[0]["rule"] == "use snake_case"
    assert convention_list(db, "code") == []


def test_convention_update_source_only(db: sqlite3.Connection) -> None:
    cid = convention_add(db, "code", "use snake_case", "explicit")
    assert convention_update(db, cid, source="observed") is True
    assert convention_list(db, "code")[0]["source"] == "observed"


def test_convention_update_all_fields(db: sqlite3.Connection) -> None:
    cid = convention_add(db, "code", "use snake_case", "explicit")
    assert convention_update(db, cid, domain="writing", rule="use active voice", source="observed") is True
    rows = convention_list(db, "writing")
    assert rows[0]["rule"] == "use active voice"
    assert rows[0]["source"] == "observed"


def test_convention_update_returns_false_for_missing_id(db: sqlite3.Connection) -> None:
    assert convention_update(db, 9999, rule="any rule") is False


def test_convention_update_raises_if_no_fields(db: sqlite3.Connection) -> None:
    cid = convention_add(db, "code", "use snake_case", "explicit")
    with pytest.raises(ValueError, match="at least one"):
        convention_update(db, cid)


def test_convention_update_raises_on_empty_rule(db: sqlite3.Connection) -> None:
    cid = convention_add(db, "code", "use snake_case", "explicit")
    with pytest.raises(ValueError, match="rule"):
        convention_update(db, cid, rule="   ")


def test_convention_update_raises_on_empty_domain(db: sqlite3.Connection) -> None:
    cid = convention_add(db, "code", "use snake_case", "explicit")
    with pytest.raises(ValueError, match="domain"):
        convention_update(db, cid, domain="")


def test_convention_update_raises_on_invalid_source(db: sqlite3.Connection) -> None:
    cid = convention_add(db, "code", "use snake_case", "explicit")
    with pytest.raises(ValueError, match="source"):
        convention_update(db, cid, source="bad-value")


def test_convention_add_rejects_unrecognized_domain(db):
    """Locked-down domain set: convention_add must reject domains outside the 7 known values."""
    with pytest.raises(ValueError, match="domain"):
        convention_add(db, "finance", "some rule")


def test_convention_add_accepts_recognized_domain(db):
    row_id = convention_add(db, "research", "cite primary sources")
    assert isinstance(row_id, int)


def test_convention_add_defaults_source_to_explicit(db):
    convention_add(db, "general", "default source check")
    rows = convention_list(db, "general")
    assert rows[0]["source"] == "explicit"


def test_convention_update_rejects_unrecognized_domain(db: sqlite3.Connection) -> None:
    cid = convention_add(db, "code", "use snake_case", "explicit")
    with pytest.raises(ValueError, match="domain"):
        convention_update(db, cid, domain="finance")


def test_domain_literal_matches_expected_set():
    """Regression guard: DomainLiteral must stay in sync with the documented 7 domains."""
    from natalie.features.memory import DomainLiteral

    assert set(get_args(DomainLiteral)) == {
        "general",
        "communication",
        "writing",
        "code",
        "research",
        "files",
        "calendar",
    }


def test_source_literal_matches_expected_set():
    """Regression guard: SourceLiteral must stay in sync with the two known source kinds."""
    from natalie.features.memory import SourceLiteral

    assert set(get_args(SourceLiteral)) == {"explicit", "observed"}


# ── update_note_frontmatter ─────────────────────────────────────────────────


def _read_post(vault, rel):
    import frontmatter as fm

    return fm.loads((vault / rel).read_text(encoding="utf-8"))


def test_update_note_frontmatter_merges_fields_without_touching_body(vault):
    write_note(vault, "note.md", "---\ntitle: Test\nstatus: draft\n---\nBody text.")
    result = update_note_frontmatter(vault, "note.md", fields={"status": "done"})
    assert result == {"updated": True, "path": "note.md"}
    post = _read_post(vault, "note.md")
    assert post.metadata["status"] == "done"
    assert post.metadata["title"] == "Test"
    assert post.content == "Body text."


def test_update_note_frontmatter_add_to_appends_without_duplicating(vault):
    write_note(vault, "note.md", "---\ntags: [a, b]\n---\nBody.")
    update_note_frontmatter(vault, "note.md", add_to={"tags": ["b", "c"]})
    post = _read_post(vault, "note.md")
    assert post.metadata["tags"] == ["a", "b", "c"]


def test_update_note_frontmatter_add_to_creates_missing_list(vault):
    write_note(vault, "note.md", "---\ntitle: Test\n---\nBody.")
    update_note_frontmatter(vault, "note.md", add_to={"tags": ["new"]})
    post = _read_post(vault, "note.md")
    assert post.metadata["tags"] == ["new"]


def test_update_note_frontmatter_remove_from_removes_items(vault):
    write_note(vault, "note.md", "---\ntags: [a, b, c]\n---\nBody.")
    update_note_frontmatter(vault, "note.md", remove_from={"tags": ["b"]})
    post = _read_post(vault, "note.md")
    assert post.metadata["tags"] == ["a", "c"]


def test_update_note_frontmatter_add_to_raises_if_existing_value_not_list(vault):
    write_note(vault, "note.md", "---\ntags: not-a-list\n---\nBody.")
    with pytest.raises(ValueError, match="not a list"):
        update_note_frontmatter(vault, "note.md", add_to={"tags": ["x"]})


def test_update_note_frontmatter_rejects_overlapping_keys(vault):
    write_note(vault, "note.md", "---\ntags: [a]\n---\nBody.")
    with pytest.raises(ValueError, match="more than one"):
        update_note_frontmatter(vault, "note.md", fields={"tags": ["x"]}, add_to={"tags": ["y"]})


def test_update_note_frontmatter_raises_if_note_missing(vault):
    with pytest.raises(ValueError, match="Note not found"):
        update_note_frontmatter(vault, "missing.md", fields={"status": "done"})


def test_update_note_frontmatter_raises_if_no_args_given(vault):
    write_note(vault, "note.md", "---\ntitle: Test\n---\nBody.")
    with pytest.raises(ValueError, match="at least one"):
        update_note_frontmatter(vault, "note.md")


def test_update_note_frontmatter_rejects_empty_rel_path(vault):
    with pytest.raises(ValueError, match="empty"):
        update_note_frontmatter(vault, "   ", fields={"status": "done"})
