from __future__ import annotations

import re
import sqlite3
import sys
import time
import urllib.parse
import uuid
from pathlib import Path
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from .config import NatalieConfig, load_config
from .db import init_db
from .features import contacts as contacts_mod
from .features import documents as docs_mod
from .features import memory as mem
from .features import tasks as tasks_mod
from .utils import safe_join
from .vault import require_vault

mcp = FastMCP("natalie")

# Module-level state — populated in main() before mcp.run()
_vault: Path | None = None
_config: NatalieConfig | None = None
_db: sqlite3.Connection | None = None


def _get_vault() -> Path:
    assert _vault is not None, "Server not initialized"
    return _vault


def _get_config() -> NatalieConfig:
    assert _config is not None, "Server not initialized"
    return _config


def _get_db() -> sqlite3.Connection:
    assert _db is not None, "Server not initialized"
    return _db


def _obsidian_read(vault: Path, rel_path: str) -> str | None:
    safe_join(vault, rel_path)  # raises ValueError if path escapes vault
    encoded = urllib.parse.quote(rel_path, safe="/")
    try:
        r = httpx.get(f"http://127.0.0.1:27123/vault/{encoded}", timeout=2.0)
        if r.status_code == 200:
            return r.text
    except httpx.RequestError:
        pass
    full = vault / rel_path
    return full.read_text(encoding="utf-8") if full.exists() else None


def _obsidian_write(vault: Path, rel_path: str, content: str) -> None:
    safe_join(vault, rel_path)  # raises ValueError if path escapes vault
    encoded = urllib.parse.quote(rel_path, safe="/")
    try:
        r = httpx.put(
            f"http://127.0.0.1:27123/vault/{encoded}",
            content=content.encode(),
            timeout=2.0,
        )
        if r.status_code in (200, 204):
            return
    except httpx.RequestError:
        pass
    full = vault / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")


@mcp.tool()
def ping() -> str:
    """Check that the Natalie server is running and return vault path."""
    vault = _get_vault()
    return f"pong — vault: {vault}"


@mcp.tool()
def memory_search(query: str, limit: int = 10, collection: str | None = None) -> list[dict[str, Any]]:
    """Search vault notes by keyword and semantic similarity (hybrid)."""
    db = _get_db()
    config = _get_config()
    kw = mem.keyword_search(db, query, limit=limit * 2, collection=collection)
    se = mem.semantic_search(
        db,
        query,
        limit=limit * 2,
        collection=collection,
        model_name=config.memory.embedding_model,
    )

    # Reciprocal Rank Fusion: score = sum(1 / (k + rank)) across streams
    # k=60 is the standard default — dampens the impact of top ranks slightly
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

    results = sorted(rrf.values(), key=lambda x: x["score"], reverse=True)
    return results[:limit]


def _entry_path(mac: str, title: str | None) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]", "-", title or "entry").strip("-") or "entry"
    uid = uuid.uuid4().hex[:8]
    return f".natalie/entries/{mac}/{slug}-{uid}.md"


@mcp.tool()
def memory_store(
    content: str,
    title: str | None = None,
    collection: str = "global",
    path: str | None = None,
) -> dict[str, Any]:
    """Store an outside-vault knowledge entry in the memory index."""
    db = _get_db()
    vault = _get_vault()
    mac = str(uuid.getnode())
    if path is not None:
        rel_path = path
        safe_join(vault, rel_path)  # raises ValueError if path escapes vault
    else:
        rel_path = _entry_path(mac, title)

    # Write to disk so note_read can serve the content
    full = vault / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")

    db.execute(
        """
        INSERT INTO notes (path, title, body, last_modified, collection, machine_mac)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            title        = excluded.title,
            body         = excluded.body,
            tags         = NULL,
            frontmatter  = NULL,
            last_modified = excluded.last_modified,
            collection   = excluded.collection,
            machine_mac  = excluded.machine_mac
        """,
        (rel_path, title or "Untitled", content, time.time(), collection, mac),
    )
    db.execute(
        "DELETE FROM embeddings WHERE note_id = (SELECT id FROM notes WHERE path = ?)",
        (rel_path,),
    )
    db.commit()
    return {"stored": True, "path": rel_path, "collection": collection}


@mcp.tool()
def note_read(path: str) -> str | None:
    """Read a vault note by relative path. Returns content or None if not found."""
    vault = _get_vault()
    return _obsidian_read(vault, path)


@mcp.tool()
def note_write(path: str, content: str) -> dict[str, Any]:
    """Write or overwrite a vault note by relative path."""
    vault = _get_vault()
    db = _get_db()
    full = safe_join(vault, path)
    _obsidian_write(vault, path, content)
    # REST write may succeed without creating a local file; index_note requires stat()
    if not full.exists():
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding="utf-8")
    mem.index_note(db, vault, full)
    return {"written": True, "path": path}


@mcp.tool()
def convention_list(domain: str | None = None) -> list[dict[str, Any]]:
    """List established conventions, optionally filtered by domain."""
    return mem.convention_list(_get_db(), domain=domain)


@mcp.tool()
def convention_add(domain: str, rule: str, source: str = "explicit") -> dict[str, Any]:
    """Add a convention. source: 'explicit' (user-stated) or 'observed' (pattern noticed)."""
    conv_id = mem.convention_add(_get_db(), domain=domain, rule=rule, source=source)
    return {"id": conv_id, "domain": domain, "rule": rule, "source": source}


@mcp.tool()
def convention_delete(convention_id: int) -> dict[str, Any]:
    """Remove a convention by ID."""
    deleted = mem.convention_delete(_get_db(), convention_id)
    return {"deleted": deleted, "id": convention_id}


@mcp.tool()
def task_list(done: bool = False) -> list[dict[str, Any]]:
    """List tasks across the vault. Set done=True to include completed tasks."""
    vault = _get_vault()
    all_tasks = tasks_mod.discover_tasks(vault)
    return [t for t in all_tasks if done or not t["done"]]


@mcp.tool()
def task_capture(rel_path: str, task_text: str) -> dict[str, Any]:
    """Add a new open task to a vault note."""
    vault = _get_vault()
    tasks_mod.capture_task(vault, rel_path, task_text)
    return {"captured": True, "path": rel_path, "task": task_text}


@mcp.tool()
def task_complete(rel_path: str, task_text: str) -> dict[str, Any]:
    """Mark a specific task as done."""
    vault = _get_vault()
    found = tasks_mod.complete_task(vault, rel_path, task_text)
    return {"completed": found, "path": rel_path, "task": task_text}


@mcp.tool()
def document_file(filename: str, content: str) -> dict[str, Any]:
    """Save content to the documents cabinet."""
    return docs_mod.file_document(_get_vault(), _get_config(), filename, content)


@mcp.tool()
def document_retrieve(filename: str) -> str | None:
    """Retrieve a document by filename. Returns content or None."""
    return docs_mod.retrieve_document(_get_vault(), _get_config(), filename)


@mcp.tool()
def document_list() -> list[str]:
    """List all documents in the cabinet."""
    return docs_mod.list_documents(_get_vault(), _get_config())


@mcp.tool()
def contact_get(slug: str) -> dict[str, Any] | None:
    """Get a contact card by slug. Returns metadata dict or None."""
    return contacts_mod.get_contact(_get_vault(), _get_config(), slug)


@mcp.tool()
def contact_update(slug: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Create or update a contact card. Fields are merged into existing frontmatter."""
    return contacts_mod.update_contact(_get_vault(), _get_config(), slug, fields)


@mcp.tool()
def contact_list() -> list[str]:
    """List all contact slugs."""
    return contacts_mod.list_contacts(_get_vault(), _get_config())


def main() -> None:
    global _vault, _config, _db
    try:
        _vault = require_vault()
    except RuntimeError as exc:
        sys.exit(str(exc))
    _config = load_config(_vault)
    _db = init_db(_vault)
    mcp.run()


if __name__ == "__main__":
    main()
