from __future__ import annotations

import sqlite3
from typing import Any


def list_notes(
    db: sqlite3.Connection,
    directory: str | None = None,
) -> list[dict[str, Any]]:
    if directory and directory.strip():
        prefix = directory.rstrip("/") + "/%"
        rows = db.execute(
            "SELECT path, title, last_modified FROM notes"
            " WHERE machine_mac IS NULL AND path LIKE ?"
            " ORDER BY path",
            (prefix,),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT path, title, last_modified FROM notes WHERE machine_mac IS NULL ORDER BY path"
        ).fetchall()
    return [dict(r) for r in rows]


def vault_stats(db: sqlite3.Connection) -> dict[str, Any]:
    vault_notes: int = db.execute("SELECT COUNT(*) FROM notes WHERE machine_mac IS NULL").fetchone()[0]
    memory_entries: int = db.execute("SELECT COUNT(*) FROM notes WHERE machine_mac IS NOT NULL").fetchone()[0]
    open_tasks: int = db.execute("SELECT COUNT(*) FROM tasks WHERE status='open'").fetchone()[0]
    embedded: int = db.execute(
        "SELECT COUNT(*) FROM embeddings WHERE note_id IN (SELECT id FROM notes WHERE machine_mac IS NULL)"
    ).fetchone()[0]
    coverage_pct = round(embedded / vault_notes * 100, 1) if vault_notes > 0 else 0.0
    last_synced: float | None = db.execute("SELECT MAX(synced_at) FROM sync_log").fetchone()[0]
    return {
        "vault_notes": vault_notes,
        "memory_entries": memory_entries,
        "open_tasks": open_tasks,
        "embedding_coverage_pct": coverage_pct,
        "last_synced_at": last_synced,
    }
