from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from ..config import NatalieConfig
from ..utils import fts_quote, safe_join
from .memory import _get_embedding_model


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    try:
        d["tags"] = json.loads(d.get("tags") or "[]")
    except (json.JSONDecodeError, TypeError):
        d["tags"] = []
    return d


def file_document(
    vault: Path,
    config: NatalieConfig,
    db: sqlite3.Connection,
    rel_path: str,
    description: str,
    project: str | None = None,
    doc_type: str | None = None,
    tags: list[str] | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Register a vault file in the document index with a semantic description."""
    if not rel_path or not rel_path.strip():
        raise ValueError("rel_path must not be empty or whitespace")
    if not description or not description.strip():
        raise ValueError("description must not be empty or whitespace")

    full = safe_join(vault, rel_path)
    if not full.exists():
        raise ValueError(f"File not found in vault: {rel_path}")
    if not full.is_file():
        raise ValueError(f"Path is not a file: {rel_path}")

    sha = _sha256(full)
    now = datetime.now(timezone.utc).isoformat()
    tags_json = json.dumps(tags or [])

    existing = db.execute("SELECT id FROM documents WHERE rel_path = ?", (rel_path,)).fetchone()
    if existing and not overwrite:
        raise ValueError(f"Already filed at '{rel_path}'; pass overwrite=True to update")

    sha_match = db.execute(
        "SELECT rel_path FROM documents WHERE sha256 = ? AND rel_path != ?",
        (sha, rel_path),
    ).fetchone()

    if existing:
        doc_id: int = existing["id"]
        db.execute(
            """
            UPDATE documents
               SET description = ?, project = ?, doc_type = ?, tags = ?,
                   sha256 = ?, updated_at = ?
             WHERE id = ?
            """,
            (description, project, doc_type, tags_json, sha, now, doc_id),
        )
        db.execute("DELETE FROM document_embeddings WHERE doc_id = ?", (doc_id,))
    else:
        cursor = db.execute(
            """
            INSERT INTO documents
                (rel_path, sha256, description, project, doc_type, tags, filed_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (rel_path, sha, description, project, doc_type, tags_json, now, now),
        )
        assert cursor.lastrowid is not None
        doc_id = cursor.lastrowid

    model = _get_embedding_model(config.memory.embedding_model)
    vec = np.array(next(iter(model.embed([description]))), dtype=np.float32)
    db.execute(
        "INSERT OR IGNORE INTO document_embeddings (doc_id, vector) VALUES (?, ?)",
        (doc_id, vec.tobytes()),
    )
    db.commit()

    result: dict[str, Any] = {"filed": True, "path": rel_path, "sha256": sha, "id": doc_id}
    if sha_match:
        result["warning"] = (
            f"SHA256 matches existing record at '{sha_match['rel_path']}'"
            " — this file may have been moved or copied from there"
        )
    return result


def list_documents(
    vault: Path,
    config: NatalieConfig,
    db: sqlite3.Connection,
    query: str | None = None,
    project: str | None = None,
    doc_type: str | None = None,
    tags: list[str] | None = None,
    top_n: int = 10,
    include_metadata: bool = True,
) -> list[dict[str, Any]]:
    """List or semantically search filed documents. query triggers hybrid search with scores."""
    filter_clauses: list[str] = []
    filter_params: list[Any] = []

    if project:
        filter_clauses.append("project = ?")
        filter_params.append(project)
    if doc_type:
        filter_clauses.append("doc_type = ?")
        filter_params.append(doc_type)
    if tags:
        for tag in tags:
            filter_clauses.append("EXISTS (SELECT 1 FROM json_each(tags) WHERE value = ?)")
            filter_params.append(tag)

    where = ("WHERE " + " AND ".join(filter_clauses)) if filter_clauses else ""

    if query is None:
        sql = f"""
            SELECT id, rel_path, sha256, description, project, doc_type, tags, filed_at, updated_at
            FROM documents {where} ORDER BY filed_at DESC
        """  # nosec B608
        rows = db.execute(sql, filter_params).fetchall()
        if not include_metadata:
            return [{"rel_path": r["rel_path"]} for r in rows]
        return [_row_to_dict(r) for r in rows]

    # Narrow candidates by structured filters before running search
    id_sql = f"SELECT id FROM documents {where}"  # nosec B608
    candidate_ids = [r["id"] for r in db.execute(id_sql, filter_params).fetchall()]
    if not candidate_ids:
        return []

    placeholders = ",".join("?" * len(candidate_ids))

    # BM25 keyword search over descriptions
    fts_query = " ".join(fts_quote(t) + "*" for t in query.split() if t)
    kw_ranked: list[tuple[int, int, str]] = []  # (rank, doc_id, rel_path)
    if fts_query:
        kw_rows = db.execute(
            f"""
            SELECT d.id, d.rel_path, bm25(documents_fts) AS score
            FROM documents_fts
            JOIN documents d ON d.id = documents_fts.rowid
            WHERE documents_fts MATCH ? AND d.id IN ({placeholders})
            ORDER BY score
            LIMIT ?
            """,  # nosec B608
            [fts_query, *candidate_ids, top_n * 2],
        ).fetchall()
        kw_ranked = [(rank, r["id"], r["rel_path"]) for rank, r in enumerate(kw_rows, start=1)]

    # Cosine semantic search over description embeddings
    sem_ranked: list[tuple[int, int, str]] = []  # (rank, doc_id, rel_path)
    model = _get_embedding_model(config.memory.embedding_model)
    query_vec = np.array(next(iter(model.embed([query]))), dtype=np.float32)
    query_norm = float(np.linalg.norm(query_vec))
    if query_norm > 0:
        query_vec = query_vec / query_norm
        emb_rows = db.execute(
            f"""
            SELECT d.id, d.rel_path, e.vector
            FROM documents d JOIN document_embeddings e ON e.doc_id = d.id
            WHERE d.id IN ({placeholders})
            """,  # nosec B608
            candidate_ids,
        ).fetchall()
        scored: list[tuple[float, int, str]] = []
        for row in emb_rows:
            vec = np.frombuffer(row["vector"], dtype=np.float32)
            norm = float(np.linalg.norm(vec))
            if norm == 0:
                continue
            cos = float(np.dot(query_vec, vec / norm))
            scored.append((cos, row["id"], row["rel_path"]))
        scored.sort(reverse=True)
        sem_ranked = [
            (rank, doc_id, path) for rank, (_, doc_id, path) in enumerate(scored[: top_n * 2], start=1)
        ]

    # Reciprocal Rank Fusion — k=60 standard default
    K = 60
    rrf: dict[int, dict[str, Any]] = {}
    for rank, doc_id, path in kw_ranked:
        rrf.setdefault(doc_id, {"id": doc_id, "rel_path": path, "score": 0.0, "match": "keyword"})
        rrf[doc_id]["score"] += 1.0 / (K + rank)
    for rank, doc_id, path in sem_ranked:
        if doc_id not in rrf:
            rrf[doc_id] = {"id": doc_id, "rel_path": path, "score": 0.0, "match": "semantic"}
        else:
            rrf[doc_id]["match"] = "hybrid"
        rrf[doc_id]["score"] += 1.0 / (K + rank)

    ranked = sorted(rrf.values(), key=lambda x: x["score"], reverse=True)[:top_n]
    if not ranked:
        return []

    result_ids = [r["id"] for r in ranked]
    ph2 = ",".join("?" * len(result_ids))
    meta_map = {
        r["id"]: r
        for r in db.execute(
            f"SELECT * FROM documents WHERE id IN ({ph2})",  # nosec B608
            result_ids,
        ).fetchall()
    }

    out = []
    for r in ranked:
        meta = meta_map.get(r["id"])
        if meta is None:
            continue
        entry: dict[str, Any] = _row_to_dict(meta) if include_metadata else {"rel_path": meta["rel_path"]}
        entry["score"] = round(r["score"], 4)
        entry["match"] = r["match"]
        out.append(entry)
    return out
