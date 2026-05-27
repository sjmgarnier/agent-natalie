from __future__ import annotations

from pathlib import Path


def safe_join(base: Path, user_part: str) -> Path:
    """Resolve user_part relative to base, raising ValueError if it escapes."""
    full = (base / user_part).resolve()
    base_resolved = base.resolve()
    if not full.is_relative_to(base_resolved):
        raise ValueError(f"path escapes base directory: {user_part!r}")
    return full
