from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any


def get_onboarding_status(db: sqlite3.Connection) -> dict[str, Any]:
    """Return onboarding state, creating the singleton row if absent."""
    db.execute("INSERT OR IGNORE INTO onboarding (id, completed_at) VALUES (1, NULL)")
    db.commit()
    row = db.execute("SELECT completed_at FROM onboarding WHERE id = 1").fetchone()
    completed_at: str | None = row["completed_at"]
    return {
        "completed": completed_at is not None,
        "completed_at": completed_at,
    }


def set_onboarding_complete(db: sqlite3.Connection) -> dict[str, Any]:
    """Mark onboarding as completed with the current UTC timestamp."""
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO onboarding (id, completed_at) VALUES (1, ?)"
        " ON CONFLICT(id) DO UPDATE SET completed_at = excluded.completed_at",
        (now,),
    )
    db.commit()
    return {
        "completed": True,
        "completed_at": now,
    }
