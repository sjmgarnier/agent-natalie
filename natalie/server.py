from __future__ import annotations

import datetime
import re
import sqlite3
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, cast

from mcp.server.fastmcp import FastMCP

from .config import NatalieConfig, load_config
from .db import get_db, init_db
from .features import browse as browse_mod
from .features import contacts as contacts_mod
from .features import documents as docs_mod
from .features import memory as mem
from .features import onboarding as onboarding_mod
from .features import tasks as tasks_mod
from .features.watcher import start_watcher
from .utils import safe_join
from .vault import require_vault

mcp = FastMCP("natalie")

# Module-level state — populated in main() before mcp.run()
_vault: Path | None = None
_config: NatalieConfig | None = None
_db_vault: Path | None = None  # vault path used to create per-thread connections
_db_local: threading.local = threading.local()  # each FastMCP worker thread gets its own connection
_observer: Any | None = None


def _get_vault() -> Path:
    assert _vault is not None, "Server not initialized"
    return _vault


def _get_config() -> NatalieConfig:
    assert _config is not None, "Server not initialized"
    return _config


def _get_db() -> sqlite3.Connection:
    assert _db_vault is not None, "Server not initialized"
    if not hasattr(_db_local, "conn"):
        _db_local.conn = get_db(_db_vault)
    return cast(sqlite3.Connection, _db_local.conn)


@mcp.tool()
def ping() -> dict[str, Any]:
    """Check that the Natalie server is running and return vault path."""
    vault = _get_vault()
    return {"status": "ok", "vault": str(vault)}


@mcp.tool()
def watcher_status() -> dict[str, Any]:
    """Return the status of the vault file-watcher daemon."""
    if _observer is None:
        return {"alive": False, "path": None, "recursive": None, "thread_ident": None, "daemon": None}
    try:
        emitters = list(_observer.emitters)
    except RuntimeError:
        emitters = []
    watch = emitters[0].watch if emitters else None
    return {
        "alive": _observer.is_alive(),
        "path": str(watch.path) if watch else None,
        "recursive": watch.is_recursive if watch else None,
        "thread_ident": _observer.ident,
        "daemon": _observer.daemon,
    }


@mcp.tool()
def note_list(directory: str | None = None) -> list[dict[str, Any]]:
    """List indexed vault notes. Pass directory to filter by subdirectory (e.g. 'Projects/Alpha')."""
    return browse_mod.list_notes(_get_db(), directory=directory)


@mcp.tool()
def vault_stats() -> dict[str, Any]:
    """Return vault index statistics: note count, memory count, open tasks, embedding coverage, last sync."""
    return browse_mod.vault_stats(_get_db())


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
                "collection": r.get("collection"),
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
                "collection": r.get("collection"),
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
        full = safe_join(vault, path)  # raises ValueError if path escapes vault
        rel_path = full.relative_to(vault.resolve()).as_posix()
    else:
        rel_path = _entry_path(mac, title)
        full = safe_join(vault, rel_path)

    # Write to disk so note_read can serve the content
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
def note_read(path: str) -> dict[str, Any]:
    """Read a vault note by relative path. Returns {found, content, path}."""
    if not path.strip():
        raise ValueError("path must not be empty")
    vault = _get_vault()
    full = safe_join(vault, path)
    if not full.exists():
        return {"found": False, "content": None, "path": path}
    return {"found": True, "content": full.read_text(encoding="utf-8"), "path": path}


@mcp.tool()
def note_write(path: str, content: str) -> dict[str, Any]:
    """Write or overwrite a vault note by relative path."""
    if not path.strip():
        raise ValueError("path must not be empty")
    vault = _get_vault()
    db = _get_db()
    full = safe_join(vault, path)
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    mem.index_note(db, vault, full)
    tasks_mod.index_tasks(db, vault, full)
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
def convention_update(
    id: int,
    domain: str | None = None,
    rule: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """Edit a convention in place. Supply only the fields to change. Returns updated and id."""
    updated = mem.convention_update(_get_db(), id, domain=domain, rule=rule, source=source)
    return {"updated": updated, "id": id}


@mcp.tool()
def onboarding_status() -> dict[str, Any]:
    """Return whether the onboarding meeting has been completed."""
    return onboarding_mod.get_onboarding_status(_get_db())


@mcp.tool()
def onboarding_complete() -> dict[str, Any]:
    """Mark the onboarding meeting as completed."""
    return onboarding_mod.set_onboarding_complete(_get_db())


@mcp.tool()
def task_list(done: bool = False) -> list[dict[str, Any]]:
    """List tasks across the vault. Set done=True to include completed tasks."""
    db = _get_db()
    today = datetime.date.today().isoformat()
    if done:
        rows = db.execute(
            "SELECT path, line, text, done, due_date, priority, recurrence, "
            "CASE WHEN done=0 AND due_date IS NOT NULL AND due_date < ? THEN 1 ELSE 0 END AS overdue "
            "FROM tasks ORDER BY due_date ASC NULLS LAST, path",
            (today,),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT path, line, text, done, due_date, priority, recurrence, "
            "CASE WHEN due_date IS NOT NULL AND due_date < ? THEN 1 ELSE 0 END AS overdue "
            "FROM tasks WHERE done=0 ORDER BY due_date ASC NULLS LAST, path",
            (today,),
        ).fetchall()
    result = []
    for r in rows:
        t = dict(r)
        t["done"] = bool(t["done"])
        t["overdue"] = bool(t["overdue"])
        result.append(t)
    return result


@mcp.tool()
def task_capture(
    rel_path: str,
    task_text: str,
    due_date: str | None = None,
    priority: str | None = None,
    recurrence: str | None = None,
) -> dict[str, Any]:
    """Add a new open task to a vault note."""
    if not rel_path.strip():
        raise ValueError("rel_path must not be empty")
    vault = _get_vault()
    result = tasks_mod.capture_task(
        vault, rel_path, task_text, due_date=due_date, priority=priority, recurrence=recurrence
    )
    tasks_mod.index_tasks(_get_db(), vault, safe_join(vault, rel_path))
    return result


@mcp.tool()
def task_complete(rel_path: str, task_text: str) -> dict[str, Any]:
    """Mark a specific task as done."""
    if not rel_path.strip():
        raise ValueError("rel_path must not be empty")
    if not task_text.strip():
        raise ValueError("task_text must not be empty")
    vault = _get_vault()
    result = tasks_mod.complete_task(vault, rel_path, task_text)
    tasks_mod.index_tasks(_get_db(), vault, safe_join(vault, rel_path))
    return result


@mcp.tool()
def task_update(
    rel_path: str,
    task_text: str,
    new_text: str | None = None,
    due_date: str | None = None,
    priority: str | None = None,
    recurrence: str | None = None,
) -> dict[str, Any]:
    """Edit an existing open task in place. Pass 'clear' to remove due_date/priority/recurrence."""
    if not rel_path.strip():
        raise ValueError("rel_path must not be empty")
    if not task_text.strip():
        raise ValueError("task_text must not be empty")
    vault = _get_vault()
    result = tasks_mod.update_task(
        vault,
        rel_path,
        task_text,
        new_text=new_text,
        due_date=due_date,
        priority=priority,
        recurrence=recurrence,
    )
    tasks_mod.index_tasks(_get_db(), vault, safe_join(vault, rel_path))
    return result


@mcp.tool()
def document_file(
    rel_path: str,
    description: str,
    project: str | None = None,
    doc_type: str | None = None,
    tags: list[str] | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Register an existing vault file in the document index with a semantic description."""
    return docs_mod.file_document(
        _get_vault(),
        _get_config(),
        _get_db(),
        rel_path,
        description,
        project,
        doc_type,
        tags,
        overwrite,
    )


@mcp.tool()
def document_list(
    query: str | None = None,
    project: str | None = None,
    doc_type: str | None = None,
    tags: list[str] | None = None,
    top_n: int = 10,
    include_metadata: bool = True,
) -> list[dict[str, Any]]:
    """List or semantically search filed documents. Pass query for hybrid semantic search."""
    return docs_mod.list_documents(
        _get_vault(),
        _get_config(),
        _get_db(),
        query,
        project,
        doc_type,
        tags,
        top_n,
        include_metadata,
    )


@mcp.tool()
def contact_get(slug: str) -> dict[str, Any] | None:
    """Get a contact card by slug. Returns metadata dict or None."""
    return contacts_mod.get_contact(_get_vault(), _get_config(), slug)


@mcp.tool()
def contact_update(slug: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Create or update a contact card. Fields are merged into existing frontmatter."""
    return contacts_mod.update_contact(_get_vault(), _get_config(), slug, fields)


@mcp.tool()
def contact_list() -> list[dict[str, Any]]:
    """List all contacts as a list of dicts with at least a 'slug' key."""
    slugs = contacts_mod.list_contacts(_get_vault(), _get_config())
    return [{"slug": s} for s in slugs]


@mcp.tool()
def contact_search(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search contacts by name, company, email, tags, or body text. Hybrid keyword + semantic."""
    config = _get_config()
    return contacts_mod.search_contacts(
        _get_db(), _get_vault(), config, query, limit=limit, model_name=config.memory.embedding_model
    )


def main() -> None:
    global _vault, _config, _db_vault, _observer
    try:
        _vault = require_vault()
    except RuntimeError as exc:
        sys.exit(str(exc))
    _config = load_config(_vault)
    init_db(_vault)  # create schema; connections are opened per-thread via _get_db()
    _db_vault = _vault
    tasks_mod.sync_tasks(_get_db(), _vault)
    _observer = start_watcher(_vault, _db_vault)
    mcp.run()


if __name__ == "__main__":
    main()
