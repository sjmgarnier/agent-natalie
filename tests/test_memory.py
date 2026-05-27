import json
import pytest
import numpy as np
from pathlib import Path
from unittest.mock import patch
from natalie.features.memory import index_note, get_notes, remove_note, keyword_search
from natalie.features.memory import embed_notes, semantic_search
from natalie.features.memory import convention_add, convention_list, convention_delete


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
    mem._embedding_model = None
    yield
    mem._embedding_model = None


def _write_note(vault: Path, rel_path: str, content: str) -> Path:
    p = vault / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def test_index_note_stores_title_and_body(vault, db):
    note = _write_note(vault, "test.md", "---\ntitle: Hello\n---\nBody text here.")
    index_note(db, vault, note)
    rows = get_notes(db)
    assert len(rows) == 1
    assert rows[0]["title"] == "Hello"
    assert "Body text here" in rows[0]["body"]


def test_index_note_uses_filename_as_title_when_frontmatter_absent(vault, db):
    note = _write_note(vault, "my-note.md", "No frontmatter here.")
    index_note(db, vault, note)
    rows = get_notes(db)
    assert rows[0]["title"] == "my-note"


def test_index_note_stores_tags_as_json(vault, db):
    note = _write_note(vault, "tagged.md", "---\ntags: [work, project]\n---\nContent.")
    index_note(db, vault, note)
    rows = get_notes(db)
    tags = json.loads(rows[0]["tags"])
    assert "work" in tags


def test_index_note_stores_relative_path(vault, db):
    note = _write_note(vault, "sub/note.md", "Content")
    index_note(db, vault, note)
    rows = get_notes(db)
    assert rows[0]["path"] == "sub/note.md"


def test_index_note_skips_unchanged_note(vault, db):
    note = _write_note(vault, "stable.md", "Content")
    index_note(db, vault, note)
    first_mtime = db.execute("SELECT last_modified FROM notes").fetchone()[0]
    # Write same content — mtime updates but our stored mtime is still old
    # We should NOT re-index if the mtime matches the stored value
    stored_mtime = first_mtime
    # Force same mtime by not touching the file; call index_note again
    index_note(db, vault, note)  # mtime unchanged → no-op
    rows = db.execute("SELECT last_modified FROM notes").fetchall()
    assert len(rows) == 1


def test_remove_note_deletes_row(vault, db):
    note = _write_note(vault, "gone.md", "Content")
    index_note(db, vault, note)
    remove_note(db, "gone.md")
    assert get_notes(db) == []


def test_fts_returns_matching_notes(vault, db):
    _write_note(vault, "alpha.md", "---\ntitle: Alpha\n---\napple banana cherry")
    _write_note(vault, "beta.md", "---\ntitle: Beta\n---\ndragonfly elephant")
    for p in vault.glob("*.md"):
        index_note(db, vault, p)
    results = keyword_search(db, "banana")
    assert len(results) == 1
    assert results[0]["path"] == "alpha.md"


def test_embed_notes_stores_vectors(vault, db):
    note = _write_note(vault, "embed-me.md", "---\ntitle: Embed\n---\nContent to embed.")
    index_note(db, vault, note)
    with patch("natalie.features.memory.TextEmbedding", _FakeEmbedding):
        embed_notes(db, model_name="BAAI/bge-small-en-v1.5")
    row = db.execute("SELECT * FROM embeddings").fetchone()
    assert row is not None
    vec = np.frombuffer(row["vector"], dtype=np.float32)
    assert vec.shape == (384,)


def test_embed_notes_skips_already_embedded(vault, db):
    note = _write_note(vault, "skip-me.md", "Content")
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
    _write_note(vault, "sem-a.md", "---\ntitle: Apple\n---\nfruit salad")
    _write_note(vault, "sem-b.md", "---\ntitle: Bicycle\n---\ntransport wheels")
    for p in vault.glob("sem-*.md"):
        index_note(db, vault, p)
    with patch("natalie.features.memory.TextEmbedding", _FakeEmbedding):
        embed_notes(db)
        results = semantic_search(db, "fruit", model_name="BAAI/bge-small-en-v1.5")
    assert len(results) >= 1
    assert "path" in results[0]
    assert "score" in results[0]


def test_convention_add_and_list(db):
    convention_add(db, domain="tasks", rule="Put tasks in the active project note.", source="explicit")
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
    convention_delete(db, conv_id)
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
    monkeypatch.setattr(srv, "_config", NatalieConfig(vault=vault))
    result = srv.memory_store(content="hello world", title="test-note")
    assert result["stored"] is True
    stored_path = vault / result["path"]
    assert stored_path.exists()
    assert stored_path.read_text() == "hello world"


def test_index_note_invalidates_stale_embedding(vault, db, monkeypatch):
    """Re-indexing an edited note must clear its old embedding."""
    import natalie.features.memory as mem_mod
    import numpy as np

    fake_vec = np.ones(4, dtype=np.float32)

    class FakeModel:
        def embed(self, texts):
            return [fake_vec for _ in texts]

    monkeypatch.setattr(mem_mod, "_embedding_model", FakeModel())

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
    monkeypatch.setattr(srv, "_config", NatalieConfig(vault=vault))
    r1 = srv.memory_store(content="first", title="prefs")
    r2 = srv.memory_store(content="second", title="prefs")
    assert r1["path"] != r2["path"]
    assert (vault / r1["path"]).read_text() == "first"
    assert (vault / r2["path"]).read_text() == "second"
