from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import frontmatter as fm
import numpy as np

from ..config import DEFAULT_EMBEDDING_MODEL, NatalieConfig
from ..utils import fts_quote, safe_join
from .memory import _get_embedding_model, _merge_frontmatter


def _contacts_dir(vault: Path, config: NatalieConfig) -> Path:
    return safe_join(vault, config.contacts.directory)


def _contact_path(vault: Path, config: NatalieConfig, slug: str) -> Path:
    contacts_dir = _contacts_dir(vault, config)
    return safe_join(contacts_dir, f"{slug}.md")


def update_contact(vault: Path, config: NatalieConfig, slug: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Create or update a contact card (merge fields into existing frontmatter)."""
    if not slug or not slug.strip():
        raise ValueError("slug must not be empty or whitespace")
    path = _contact_path(vault, config, slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = dict(fields)  # avoid mutating caller's dict
    new_body = fields.pop("content", None)
    if path.exists():
        post = fm.loads(path.read_text(encoding="utf-8"))
        _merge_frontmatter(post.metadata, fields)
        if new_body is not None:
            post.content = new_body
    else:
        post = fm.Post(content=new_body or "")
        _merge_frontmatter(post.metadata, fields)
    path.write_text(fm.dumps(post), encoding="utf-8")
    return {"updated": True, "slug": slug}


def get_contact(vault: Path, config: NatalieConfig, slug: str) -> dict[str, Any] | None:
    """Return contact metadata dict (plus 'content' body if present), or None if not found."""
    path = _contact_path(vault, config, slug)
    if not path.exists():
        return None
    post = fm.loads(path.read_text(encoding="utf-8"))
    result = dict(post.metadata)
    if post.content is not None:
        result["content"] = post.content
    return result


def list_contacts(vault: Path, config: NatalieConfig) -> list[str]:
    """Return slugs of all contact cards, sorted."""
    contacts_dir = _contacts_dir(vault, config)
    if not contacts_dir.exists():
        return []
    return sorted(p.stem for p in contacts_dir.glob("*.md"))


def search_contacts(
    db: sqlite3.Connection,
    vault: Path,
    config: NatalieConfig,
    query: str,
    limit: int = 10,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
) -> list[dict[str, Any]]:
    """Hybrid keyword + semantic search over indexed contact notes."""
    if not query or not query.strip():
        raise ValueError("query must not be empty")

    vault = vault.resolve()
    contacts_dir = _contacts_dir(vault, config)
    contacts_rel = contacts_dir.relative_to(vault).as_posix()
    path_pattern = contacts_rel + "/%"

    # Keyword pass: FTS on title/body, supplemented by frontmatter LIKE search
    # (contact metadata such as name, email, company lives in frontmatter JSON,
    # which is not part of the FTS index)
    fts_query = " ".join(fts_quote(t) + "*" for t in query.split() if t)
    terms = [t for t in query.split() if t]
    seen: dict[str, dict[str, Any]] = {}

    if fts_query:
        rows = db.execute(
            """
            SELECT n.path, n.title, bm25(notes_fts) AS score,
                   snippet(notes_fts, 1, '[', ']', '…', 12) AS excerpt
            FROM notes_fts
            JOIN notes n ON n.id = notes_fts.rowid
            WHERE notes_fts MATCH ?
              AND n.path LIKE ?
              AND n.machine_mac IS NULL
            ORDER BY score
            LIMIT ?
            """,  # nosec B608
            (fts_query, path_pattern, limit * 2),
        ).fetchall()
        for r in rows:
            seen[r["path"]] = dict(r)

    if terms:
        fm_clause = " AND ".join("n.frontmatter LIKE ?" for _ in terms)
        fm_params: list[Any] = [f"%{t}%" for t in terms]
        fm_rows = db.execute(
            f"SELECT n.path, n.title FROM notes n"  # nosec B608
            f" WHERE n.path LIKE ? AND n.machine_mac IS NULL AND ({fm_clause}) LIMIT ?",
            [path_pattern, *fm_params, limit * 2],
        ).fetchall()
        for r in fm_rows:
            if r["path"] not in seen:
                seen[r["path"]] = {"path": r["path"], "title": r["title"], "score": -999.0, "excerpt": ""}

    kw: list[dict[str, Any]] = list(seen.values())

    # Semantic pass — skipped when no contact embeddings exist yet
    se: list[dict[str, Any]] = []
    emb_rows = db.execute(
        """
        SELECT n.path, n.title, n.body, e.vector
        FROM notes n JOIN embeddings e ON e.note_id = n.id
        WHERE n.path LIKE ?
          AND n.machine_mac IS NULL
        """,  # nosec B608
        (path_pattern,),
    ).fetchall()
    if emb_rows:
        model = _get_embedding_model(model_name)
        query_vec = np.array(next(iter(model.embed([query]))), dtype=np.float32)
        query_norm = float(np.linalg.norm(query_vec))
        if query_norm > 0:
            query_vec = query_vec / query_norm
            scored: list[tuple[float, sqlite3.Row]] = []
            for row in emb_rows:
                note_vec = np.frombuffer(row["vector"], dtype=np.float32)
                norm = np.linalg.norm(note_vec)
                if norm == 0:
                    continue
                score = float(np.dot(query_vec, note_vec / norm))
                scored.append((score, row))
            scored.sort(key=lambda x: x[0], reverse=True)
            se = [
                {
                    "path": row["path"],
                    "title": row["title"],
                    "score": round(s, 4),
                    "excerpt": (row["body"] or "")[:200],
                }
                for s, row in scored[: limit * 2]
            ]

    # Reciprocal Rank Fusion (k=60)
    K = 60
    rrf: dict[str, dict[str, Any]] = {}
    for rank, r in enumerate(kw, start=1):
        path = r["path"]
        rrf.setdefault(
            path,
            {
                "path": path,
                "title": r.get("title"),
                "score": 0.0,
                "excerpt": r.get("excerpt", ""),
                "source": "keyword",
            },
        )
        rrf[path]["score"] += 1.0 / (K + rank)
    for rank, r in enumerate(se, start=1):
        path = r["path"]
        if path not in rrf:
            rrf[path] = {
                "path": path,
                "title": r.get("title"),
                "score": 0.0,
                "excerpt": r.get("excerpt", ""),
                "source": "semantic",
            }
        else:
            rrf[path]["source"] = "hybrid"
        rrf[path]["score"] += 1.0 / (K + rank)

    return sorted(rrf.values(), key=lambda x: x["score"], reverse=True)[:limit]
