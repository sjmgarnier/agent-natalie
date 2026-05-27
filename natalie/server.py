from __future__ import annotations

import sqlite3
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .config import NatalieConfig, load_config
from .db import init_db
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


@mcp.tool()
def ping() -> str:
    """Check that the Natalie server is running and return vault path."""
    vault = _get_vault()
    return f"pong — vault: {vault}"


def main() -> None:
    global _vault, _config, _db
    _vault = require_vault()
    _config = load_config(_vault)
    _db = init_db(_vault)
    mcp.run()


if __name__ == "__main__":
    main()
