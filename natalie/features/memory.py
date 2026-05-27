from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import frontmatter as fm


# ── Indexing ──────────────────────────────────────────────────────────────────

def index_note(
    db: sqlite3.Connection,
    vault: Path,
    note_path: Path,
    collection: str = "global",
    machine_mac: str | None = None,
) -> None:
    """Index or update a single vault note. No-op if mtime unchanged."""
    rel = note_path.relative_to(vault).as_posix()
    mtime = note_path.stat().st_mtime

    existing = db.execute(
        "SELECT last_modified FROM notes WHERE path = ?", (rel,)
    ).fetchone()
    if existing and existing["last_modified"] == mtime:
        return

    post = fm.loads(note_path.read_text(encoding="utf-8"))
    meta = post.metadata
    title = meta.get("title") or note_path.stem
    tags_raw = meta.get("tags", [])
    tags = json.dumps(tags_raw if isinstance(tags_raw, list) else [tags_raw])
    body = post.content.strip()

    db.execute(
        """
        INSERT INTO notes (path, title, tags, frontmatter, body, last_modified, collection, machine_mac)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            title         = excluded.title,
            tags          = excluded.tags,
            frontmatter   = excluded.frontmatter,
            body          = excluded.body,
            last_modified = excluded.last_modified,
            collection    = excluded.collection,
            machine_mac   = excluded.machine_mac
        """,
        (rel, title, tags, json.dumps(meta), body, mtime, collection, machine_mac),
    )
    db.commit()


def remove_note(db: sqlite3.Connection, rel_path: str) -> None:
    db.execute("DELETE FROM notes WHERE path = ?", (rel_path,))
    db.commit()


def get_notes(db: sqlite3.Connection, collection: str | None = None) -> list[sqlite3.Row]:
    if collection:
        return db.execute(
            "SELECT * FROM notes WHERE collection = ?", (collection,)
        ).fetchall()
    return db.execute("SELECT * FROM notes").fetchall()


# ── FTS Search ────────────────────────────────────────────────────────────────

def keyword_search(
    db: sqlite3.Connection,
    query: str,
    limit: int = 10,
    collection: str | None = None,
) -> list[dict]:
    """Full-text search over indexed notes. Returns matches ranked by BM25."""
    fts_query = " ".join(t + "*" for t in query.split() if t)
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
    """
    params: dict = {"q": fts_query, "lim": limit}
    if collection:
        params["col"] = collection
    rows = db.execute(sql, params).fetchall()
    return [dict(r) for r in rows]
