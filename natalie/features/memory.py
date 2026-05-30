from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import frontmatter as fm
import numpy as np
from fastembed import TextEmbedding

DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"

# ── Indexing ──────────────────────────────────────────────────────────────────


def index_note(
    db: sqlite3.Connection,
    vault: Path,
    note_path: Path,
    collection: str = "global",
) -> bool:
    """Index or update a single vault note. Returns False (no-op) if mtime unchanged."""
    vault = vault.resolve()
    note_path = note_path.resolve()  # I1: ensure relative_to() works with symlinked note paths
    rel = note_path.relative_to(vault).as_posix()
    mtime = note_path.stat().st_mtime

    existing = db.execute("SELECT last_modified FROM notes WHERE path = ?", (rel,)).fetchone()
    if existing and existing["last_modified"] == mtime:
        return False

    post = fm.loads(note_path.read_text(encoding="utf-8"))
    meta = post.metadata
    title = meta.get("title") or note_path.stem
    tags_raw = meta.get("tags", [])
    tags = json.dumps(tags_raw if isinstance(tags_raw, list) else [tags_raw], default=str)
    body = post.content.strip()

    # Invalidate stale embedding when note content is being updated
    if existing:
        db.execute(
            "DELETE FROM embeddings WHERE note_id = (SELECT id FROM notes WHERE path = ?)",
            (rel,),
        )

    db.execute(
        """
        INSERT INTO notes (path, title, tags, frontmatter, body, last_modified, collection)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            title         = excluded.title,
            tags          = excluded.tags,
            frontmatter   = excluded.frontmatter,
            body          = excluded.body,
            last_modified = excluded.last_modified,
            collection    = excluded.collection
        """,
        (rel, title, tags, json.dumps(meta, default=str), body, mtime, collection),
    )
    db.commit()
    return True


def remove_note(db: sqlite3.Connection, rel_path: str) -> None:
    db.execute("DELETE FROM notes WHERE path = ? AND machine_mac IS NULL", (rel_path,))
    db.commit()


def get_notes(db: sqlite3.Connection, collection: str | None = None) -> list[sqlite3.Row]:
    if collection:
        return db.execute("SELECT * FROM notes WHERE collection = ?", (collection,)).fetchall()
    return db.execute("SELECT * FROM notes").fetchall()


# ── FTS Search ────────────────────────────────────────────────────────────────


def _fts_quote(token: str) -> str:
    return '"' + token.replace("\x00", "").replace('"', '""') + '"'


def keyword_search(
    db: sqlite3.Connection,
    query: str,
    limit: int = 10,
    collection: str | None = None,
) -> list[dict[str, Any]]:
    """Full-text search over indexed notes. Returns matches ranked by BM25."""
    fts_query = " ".join(_fts_quote(t) + "*" for t in query.split() if t)
    if not fts_query:
        return []

    collection_clause = "AND n.collection = :col" if collection else ""
    sql = f"""
        SELECT
            n.path,
            n.title,
            n.collection,
            bm25(notes_fts) AS score,
            snippet(notes_fts, 1, '[', ']', '…', 12) AS excerpt
        FROM notes_fts
        JOIN notes n ON n.id = notes_fts.rowid
        WHERE notes_fts MATCH :q
        {collection_clause}
        ORDER BY score
        LIMIT :lim
    """  # nosec B608
    params: dict[str, Any] = {"q": fts_query, "lim": limit}
    if collection:
        params["col"] = collection
    rows = db.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


# ── Embeddings ────────────────────────────────────────────────────────────────

_embedding_models: dict[str, TextEmbedding] = {}


def _get_embedding_model(model_name: str = DEFAULT_EMBEDDING_MODEL) -> TextEmbedding:
    if model_name not in _embedding_models:
        _embedding_models[model_name] = TextEmbedding(model_name=model_name)
    return _embedding_models[model_name]


def embed_notes(
    db: sqlite3.Connection,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
    batch_size: int = 32,
) -> int:
    """Generate and store embeddings for notes without one. Returns count embedded."""
    rows = db.execute(
        """
        SELECT id, title, body FROM notes
        WHERE id NOT IN (SELECT note_id FROM embeddings)
        """
    ).fetchall()
    if not rows:
        return 0

    model = _get_embedding_model(model_name)
    texts = [f"{r['title'] or ''}\n{r['body'] or ''}" for r in rows]

    count = 0
    for i in range(0, len(texts), batch_size):
        batch_texts = texts[i : i + batch_size]
        batch_rows = rows[i : i + batch_size]
        for row, vec in zip(batch_rows, model.embed(batch_texts)):
            arr = np.array(vec, dtype=np.float32)
            db.execute(
                "INSERT INTO embeddings (note_id, vector) VALUES (?, ?)",
                (row["id"], arr.tobytes()),
            )
            count += 1
    db.commit()
    return count


def semantic_search(
    db: sqlite3.Connection,
    query: str,
    limit: int = 10,
    collection: str | None = None,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
) -> list[dict[str, Any]]:
    """Semantic similarity search using stored embeddings."""
    model = _get_embedding_model(model_name)
    query_vec = np.array(next(iter(model.embed([query]))), dtype=np.float32)
    query_norm = float(np.linalg.norm(query_vec))
    if query_norm == 0:
        return []
    query_vec = query_vec / query_norm

    collection_clause = "AND n.collection = ?" if collection else ""
    params: list[Any] = [] if not collection else [collection]
    rows = db.execute(
        f"""
        SELECT n.id, n.path, n.title, n.body, n.collection, e.vector
        FROM notes n JOIN embeddings e ON e.note_id = n.id
        WHERE 1=1 {collection_clause}
        """,  # nosec B608
        params,
    ).fetchall()
    if not rows:
        return []

    scored = []
    for row in rows:
        note_vec = np.frombuffer(row["vector"], dtype=np.float32)
        norm = np.linalg.norm(note_vec)
        if norm == 0:
            continue
        score = float(np.dot(query_vec, note_vec / norm))
        scored.append((score, row))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {
            "path": row["path"],
            "title": row["title"],
            "collection": row["collection"],
            "score": round(score, 4),
            "excerpt": (row["body"] or "")[:200],
        }
        for score, row in scored[:limit]
    ]


# ── Conventions ───────────────────────────────────────────────────────────────

_VALID_SOURCES = frozenset(("explicit", "observed"))


def convention_add(
    db: sqlite3.Connection,
    domain: str,
    rule: str,
    source: str = "explicit",
) -> int:
    """Store a convention. source must be 'explicit' or 'observed'. Returns new row ID."""
    if not domain.strip():
        raise ValueError("domain must not be empty")
    if not rule.strip():
        raise ValueError("rule must not be empty")
    if source not in _VALID_SOURCES:
        raise ValueError(f"Invalid source {source!r}: must be one of {sorted(_VALID_SOURCES)}")
    cursor = db.execute(
        "INSERT INTO conventions (domain, rule, source) VALUES (?, ?, ?)",
        (domain, rule, source),
    )
    db.commit()
    assert cursor.lastrowid is not None
    return cursor.lastrowid


def convention_list(
    db: sqlite3.Connection,
    domain: str | None = None,
) -> list[dict[str, Any]]:
    if domain:
        rows = db.execute(
            "SELECT * FROM conventions WHERE domain = ? ORDER BY created_at",
            (domain,),
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM conventions ORDER BY domain, created_at").fetchall()
    return [dict(r) for r in rows]


def convention_delete(db: sqlite3.Connection, convention_id: int) -> bool:
    """Delete a convention by ID. Returns True if found and deleted, False otherwise."""
    cursor = db.execute("DELETE FROM conventions WHERE id = ?", (convention_id,))
    db.commit()
    return cursor.rowcount > 0
