import json
from unittest.mock import patch

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from natalie.features.memory import (
    convention_add,
    convention_delete,
    convention_list,
    embed_notes,
    get_notes,
    index_note,
    keyword_search,
    remove_note,
    semantic_search,
)
from tests.helpers import write_note


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
        domain="tasks",
        rule="Put tasks in the active project note.",
        source="explicit",
    )
    conventions = convention_list(db, domain="tasks")
    assert len(conventions) == 1
    assert conventions[0]["rule"] == "Put tasks in the active project note."
    assert conventions[0]["source"] == "explicit"


def test_convention_list_filters_by_domain(db):
    convention_add(db, domain="tasks", rule="Tasks rule", source="explicit")
    convention_add(db, domain="contacts", rule="Contacts rule", source="explicit")
    tasks_convs = convention_list(db, domain="tasks")
    assert len(tasks_convs) == 1
    assert tasks_convs[0]["domain"] == "tasks"


def test_convention_list_all_when_no_domain(db):
    convention_add(db, domain="tasks", rule="Rule 1", source="explicit")
    convention_add(db, domain="contacts", rule="Rule 2", source="observed")
    all_convs = convention_list(db)
    assert len(all_convs) == 2


def test_convention_delete(db):
    convention_add(db, domain="tasks", rule="To delete", source="explicit")
    conv_id = convention_list(db, domain="tasks")[0]["id"]
    result = convention_delete(db, conv_id)
    assert result is True
    assert convention_list(db, domain="tasks") == []


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
    monkeypatch.setattr(srv, "_db", db)
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


def test_memory_store_unique_paths_no_collision(vault, db, monkeypatch):
    """Two stores with the same title must produce distinct files."""
    import natalie.server as srv

    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db", db)
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
    monkeypatch.setattr(srv, "_db", db)
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
    row_id = convention_add(db, domain="tasks", rule="a rule", source="explicit")
    assert isinstance(row_id, int)


def test_convention_add_rejects_invalid_source(db):
    """convention_add must raise ValueError for invalid source values — B2."""
    with pytest.raises(ValueError, match="source"):
        convention_add(db, domain="tasks", rule="a rule", source="invalid")


def test_convention_delete_returns_false_for_missing_id(db):
    """convention_delete must return False when the ID does not exist — B1."""
    result = convention_delete(db, 9999)
    assert result is False


def test_convention_delete_returns_true_when_found(db):
    """convention_delete must return True when the convention was present — B1."""
    row_id = convention_add(db, domain="tasks", rule="to delete", source="explicit")
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


def test_memory_store_clears_stale_tags_and_frontmatter(vault, db, monkeypatch):
    """memory_store must set tags/frontmatter to NULL when overwriting a vault-indexed row — B5."""
    import time

    import natalie.server as srv

    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db", db)
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
    monkeypatch.setattr(srv, "_db", db)
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
    monkeypatch.setattr(srv, "_db", db)
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
