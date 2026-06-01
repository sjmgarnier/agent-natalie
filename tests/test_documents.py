from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from natalie.features import memory as mem_mod
from natalie.features.documents import file_document, list_documents


class FakeModel:
    def embed(self, texts: list[str]):  # type: ignore[override]
        for _ in texts:
            yield np.ones(384, dtype=np.float32)


@pytest.fixture(autouse=True)
def fake_embeddings(monkeypatch):
    monkeypatch.setattr(mem_mod, "_embedding_models", {"BAAI/bge-small-en-v1.5": FakeModel()})


# ── file_document ─────────────────────────────────────────────────────────────


def test_file_document_happy_path(vault, config, db):
    (vault / "report.pdf").write_bytes(b"%PDF-1.4 fake")
    result = file_document(vault, config, db, "report.pdf", "Q1 earnings report")
    assert result["filed"] is True
    assert result["path"] == "report.pdf"
    assert len(result["sha256"]) == 64
    assert isinstance(result["id"], int)
    assert "warning" not in result


def test_file_document_stores_all_metadata(vault, config, db):
    (vault / "grant.pdf").write_bytes(b"grant content")
    file_document(
        vault,
        config,
        db,
        "grant.pdf",
        "NSF grant application",
        project="army-ants",
        doc_type="grant",
        tags=["research", "NSF"],
    )
    row = db.execute("SELECT * FROM documents WHERE rel_path = 'grant.pdf'").fetchone()
    assert row["project"] == "army-ants"
    assert row["doc_type"] == "grant"
    assert json.loads(row["tags"]) == ["research", "NSF"]
    assert row["description"] == "NSF grant application"
    assert row["sha256"] is not None


def test_file_document_sha256_matches_file_content(vault, config, db):
    content = b"hello world"
    (vault / "hello.txt").write_bytes(content)
    result = file_document(vault, config, db, "hello.txt", "A hello world file")
    assert result["sha256"] == hashlib.sha256(content).hexdigest()


def test_file_document_stores_embedding(vault, config, db):
    (vault / "note.txt").write_bytes(b"content")
    result = file_document(vault, config, db, "note.txt", "A text note")
    row = db.execute("SELECT vector FROM document_embeddings WHERE doc_id = ?", (result["id"],)).fetchone()
    assert row is not None
    assert len(row["vector"]) > 0


def test_file_document_rejects_missing_file(vault, config, db):
    with pytest.raises(ValueError, match="not found"):
        file_document(vault, config, db, "nonexistent.pdf", "desc")


def test_file_document_rejects_directory_path(vault, config, db):
    with pytest.raises(ValueError, match="not a file"):
        file_document(vault, config, db, "Natalie", "desc")


def test_file_document_rejects_overwrite_without_flag(vault, config, db):
    (vault / "doc.pdf").write_bytes(b"v1")
    file_document(vault, config, db, "doc.pdf", "Version 1")
    with pytest.raises(ValueError, match="overwrite=True"):
        file_document(vault, config, db, "doc.pdf", "Version 2")


def test_file_document_allows_overwrite_with_flag(vault, config, db):
    (vault / "doc.pdf").write_bytes(b"v1")
    file_document(vault, config, db, "doc.pdf", "Version 1")
    (vault / "doc.pdf").write_bytes(b"v2")
    result = file_document(vault, config, db, "doc.pdf", "Version 2", overwrite=True)
    assert result["filed"] is True
    row = db.execute("SELECT description FROM documents WHERE rel_path = 'doc.pdf'").fetchone()
    assert row["description"] == "Version 2"


def test_file_document_overwrite_replaces_stale_embedding(vault, config, db):
    (vault / "doc.txt").write_bytes(b"v1")
    r1 = file_document(vault, config, db, "doc.txt", "Version 1")
    (vault / "doc.txt").write_bytes(b"v2")
    file_document(vault, config, db, "doc.txt", "Version 2", overwrite=True)
    emb = db.execute("SELECT vector FROM document_embeddings WHERE doc_id = ?", (r1["id"],)).fetchone()
    assert emb is not None  # embedding was re-created after overwrite


def test_file_document_warns_on_sha_match(vault, config, db):
    content = b"identical content"
    (vault / "original.pdf").write_bytes(content)
    file_document(vault, config, db, "original.pdf", "The original")
    (vault / "copy.pdf").write_bytes(content)
    result = file_document(vault, config, db, "copy.pdf", "A copy")
    assert "warning" in result
    assert "original.pdf" in result["warning"]


def test_file_document_rejects_path_traversal(vault, config, db):
    with pytest.raises(ValueError):
        file_document(vault, config, db, "../../etc/passwd", "desc")


@given(rel_path=st.one_of(st.just(""), st.text(alphabet="\t\n ", min_size=1, max_size=20)))
@settings(max_examples=50, suppress_health_check=["function_scoped_fixture"])
def test_file_document_rejects_empty_or_whitespace_rel_path(vault, config, db, rel_path):
    with pytest.raises(ValueError, match="empty"):
        file_document(vault, config, db, rel_path, "desc")


@given(description=st.one_of(st.just(""), st.text(alphabet="\t\n ", min_size=1, max_size=20)))
@settings(max_examples=50, suppress_health_check=["function_scoped_fixture"])
def test_file_document_rejects_empty_or_whitespace_description(vault, config, db, description):
    (vault / "f.txt").write_bytes(b"x")
    with pytest.raises(ValueError, match="empty"):
        file_document(vault, config, db, "f.txt", description)


# ── list_documents ────────────────────────────────────────────────────────────


def test_list_documents_empty(vault, config, db):
    assert list_documents(vault, config, db) == []


def test_list_documents_returns_all(vault, config, db):
    for name in ("a.pdf", "b.pdf", "c.pdf"):
        (vault / name).write_bytes(b"x")
        file_document(vault, config, db, name, f"Description of {name}")
    results = list_documents(vault, config, db)
    rel_paths = [r["rel_path"] for r in results]
    assert "a.pdf" in rel_paths
    assert "b.pdf" in rel_paths
    assert "c.pdf" in rel_paths


def test_list_documents_include_metadata_false(vault, config, db):
    (vault / "x.pdf").write_bytes(b"x")
    file_document(vault, config, db, "x.pdf", "Some doc")
    results = list_documents(vault, config, db, include_metadata=False)
    assert results == [{"rel_path": "x.pdf"}]


def test_list_documents_filter_by_project(vault, config, db):
    (vault / "a.pdf").write_bytes(b"x")
    (vault / "b.pdf").write_bytes(b"y")
    file_document(vault, config, db, "a.pdf", "Doc A", project="proj-alpha")
    file_document(vault, config, db, "b.pdf", "Doc B", project="proj-beta")
    results = list_documents(vault, config, db, project="proj-alpha")
    assert len(results) == 1
    assert results[0]["rel_path"] == "a.pdf"


def test_list_documents_filter_by_doc_type(vault, config, db):
    (vault / "a.pdf").write_bytes(b"x")
    (vault / "b.pdf").write_bytes(b"y")
    file_document(vault, config, db, "a.pdf", "A grant", doc_type="grant")
    file_document(vault, config, db, "b.pdf", "A report", doc_type="report")
    results = list_documents(vault, config, db, doc_type="grant")
    assert len(results) == 1
    assert results[0]["rel_path"] == "a.pdf"


def test_list_documents_filter_by_tags(vault, config, db):
    (vault / "a.pdf").write_bytes(b"x")
    (vault / "b.pdf").write_bytes(b"y")
    file_document(vault, config, db, "a.pdf", "Doc A", tags=["NSF", "research"])
    file_document(vault, config, db, "b.pdf", "Doc B", tags=["internal"])
    results = list_documents(vault, config, db, tags=["NSF"])
    assert len(results) == 1
    assert results[0]["rel_path"] == "a.pdf"


def test_list_documents_filter_returns_empty_when_no_match(vault, config, db):
    (vault / "a.pdf").write_bytes(b"x")
    file_document(vault, config, db, "a.pdf", "A doc", project="alpha")
    assert list_documents(vault, config, db, project="beta") == []


def test_list_documents_query_returns_scores_and_match(vault, config, db):
    (vault / "report.pdf").write_bytes(b"content")
    file_document(vault, config, db, "report.pdf", "Annual earnings report for fiscal year 2024")
    results = list_documents(vault, config, db, query="earnings report")
    assert len(results) >= 1
    assert "score" in results[0]
    assert "match" in results[0]
    assert results[0]["match"] in ("keyword", "semantic", "hybrid")


def test_list_documents_query_respects_top_n(vault, config, db):
    for i in range(5):
        (vault / f"doc{i}.pdf").write_bytes(b"x")
        file_document(vault, config, db, f"doc{i}.pdf", f"Document number {i} about research")
    results = list_documents(vault, config, db, query="research document", top_n=2)
    assert len(results) <= 2


def test_list_documents_query_with_filter_searches_subset(vault, config, db):
    (vault / "a.pdf").write_bytes(b"x")
    (vault / "b.pdf").write_bytes(b"y")
    file_document(vault, config, db, "a.pdf", "NSF grant proposal for army ant research", project="alpha")
    file_document(vault, config, db, "b.pdf", "NSF grant proposal for bee research", project="beta")
    results = list_documents(vault, config, db, query="NSF grant", project="alpha")
    rel_paths = [r["rel_path"] for r in results]
    assert "a.pdf" in rel_paths
    assert "b.pdf" not in rel_paths


def test_list_documents_query_empty_when_no_candidates(vault, config, db):
    (vault / "a.pdf").write_bytes(b"x")
    file_document(vault, config, db, "a.pdf", "A doc", project="alpha")
    results = list_documents(vault, config, db, query="something", project="beta")
    assert results == []
