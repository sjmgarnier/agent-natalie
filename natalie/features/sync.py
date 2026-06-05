from __future__ import annotations

import sqlite3
from pathlib import Path

from .memory import DEFAULT_EMBEDDING_MODEL, embed_notes, index_note, remove_note
from .tasks import index_tasks


def sync_vault(
    db: sqlite3.Connection,
    vault: Path,
    full: bool = False,
    model_name: str = DEFAULT_EMBEDDING_MODEL,
) -> dict[str, int]:
    """Index new/changed vault notes; optionally remove stale entries.

    Returns: {indexed: int, removed: int, embedded: int}
    """
    vault = vault.resolve()

    if full:
        # Do not commit here — the DELETE stays in the same transaction as the first
        # index_note commit, so a crash before re-indexing rolls back the delete.
        db.execute("DELETE FROM notes WHERE machine_mac IS NULL")
        db.execute("DELETE FROM tasks")

    md_files = {
        p for p in vault.rglob("*.md") if not any(part.startswith(".") for part in p.relative_to(vault).parts)
    }

    indexed = 0
    for p in md_files:
        if index_note(db, vault, p):
            indexed += 1
        index_tasks(db, vault, p)

    # Always reconcile deletions (not just on --full)
    indexed_paths = {p.relative_to(vault).as_posix() for p in md_files}
    stored_paths = {
        r["path"] for r in db.execute("SELECT path FROM notes WHERE machine_mac IS NULL").fetchall()
    }
    removed = 0
    for stale in stored_paths - indexed_paths:
        remove_note(db, stale)
        db.execute("DELETE FROM tasks WHERE path = ?", (stale,))
        db.commit()
        removed += 1

    embedded = embed_notes(db, model_name=model_name)
    # full=True wipes and rebuilds from scratch; indexed means "new/changed", which is undefined
    return {"indexed": 0 if full else indexed, "removed": removed, "embedded": embedded}
