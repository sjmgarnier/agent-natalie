from pathlib import Path
from unittest.mock import patch
from natalie.features.sync import sync_vault, sync_instructions
from natalie.features.memory import get_notes


def _write(vault: Path, rel: str, content: str) -> Path:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def test_sync_vault_indexes_markdown_files(vault, db, config):
    _write(vault, "note1.md", "---\ntitle: Note One\n---\nContent one.")
    _write(vault, "note2.md", "---\ntitle: Note Two\n---\nContent two.")
    with patch("natalie.features.sync.embed_notes"):
        sync_vault(db, vault, config)
    rows = get_notes(db)
    assert len(rows) == 2


def test_sync_vault_skips_dotfiles(vault, db, config):
    _write(vault, ".natalie/skip-me.md", "Should not be indexed.")
    _write(vault, "real.md", "Should be indexed.")
    with patch("natalie.features.sync.embed_notes"):
        sync_vault(db, vault, config)
    rows = get_notes(db)
    paths = [r["path"] for r in rows]
    assert "real.md" in paths
    assert not any(".natalie" in p for p in paths)


def test_sync_vault_removes_deleted_notes(vault, db, config):
    note = _write(vault, "temp.md", "Temporary note.")
    with patch("natalie.features.sync.embed_notes"):
        sync_vault(db, vault, config)
    assert len(get_notes(db)) == 1
    note.unlink()
    with patch("natalie.features.sync.embed_notes"):
        sync_vault(db, vault, config, full=True)
    assert len(get_notes(db)) == 0


def test_sync_cli_command_runs(vault, db):
    from typer.testing import CliRunner
    from natalie.cli import app
    runner = CliRunner()
    with patch("natalie.cli.require_vault", return_value=vault), \
         patch("natalie.cli.load_config") as mock_cfg, \
         patch("natalie.cli.get_db", return_value=db), \
         patch("natalie.features.sync.embed_notes"):
        mock_cfg.return_value.memory.embedding_model = "BAAI/bge-small-en-v1.5"
        result = runner.invoke(app, ["sync"])
    assert result.exit_code == 0


def test_sync_instructions_copies_non_persona_content(vault):
    (vault / "CLAUDE.md").write_text(
        "<!-- agent-natalie:persona:start -->\nNatalie persona.\n<!-- agent-natalie:persona:end -->\n\n## Memory\n\nRemember everything.\n",
        encoding="utf-8",
    )
    sync_instructions(vault)
    agents_md = vault / "AGENTS.md"
    assert agents_md.exists()
    content = agents_md.read_text()
    assert "Remember everything" in content


def test_sync_instructions_preserves_persona_block(vault):
    (vault / "CLAUDE.md").write_text(
        "<!-- agent-natalie:persona:start -->\nNatalie here.\n<!-- agent-natalie:persona:end -->\n\n## Tools\n\nUse them.\n",
        encoding="utf-8",
    )
    sync_instructions(vault)
    content = (vault / "AGENTS.md").read_text()
    assert "Natalie here" in content
    assert "<!-- agent-natalie:persona:start -->" in content


def test_sync_instructions_no_op_when_claude_md_missing(vault):
    result = sync_instructions(vault)
    assert result["synced"] is False


def test_sync_vault_full_wipes_and_reindexes(vault, db, config):
    """--full must delete all vault rows first so DB corruption is repaired."""
    _write(vault, "stable.md", "---\ntitle: Stable\n---\nReal content.")
    with patch("natalie.features.sync.embed_notes"):
        sync_vault(db, vault, config)

    # Corrupt the DB body directly — mtime is still current, so incremental skips it
    db.execute("UPDATE notes SET body = 'corrupted' WHERE path = 'stable.md'")
    db.commit()

    with patch("natalie.features.sync.embed_notes"):
        sync_vault(db, vault, config, full=False)  # incremental — mtime matches, skips
    row = db.execute("SELECT body FROM notes WHERE path = 'stable.md'").fetchone()
    assert row["body"] == "corrupted", "incremental must not touch unchanged mtime"

    with patch("natalie.features.sync.embed_notes"):
        sync_vault(db, vault, config, full=True)  # full — wipe and re-index
    row = db.execute("SELECT body FROM notes WHERE path = 'stable.md'").fetchone()
    assert row["body"] == "Real content.", "full must re-index from disk"


def test_sync_vault_removes_deleted_notes_incrementally(vault, db, config, monkeypatch):
    """Deleted notes must be removed on incremental sync, not only --full."""
    import natalie.features.memory as mem_mod

    class FakeModel:
        def embed(self, texts):
            import numpy as np
            return [np.ones(4, dtype=np.float32) for _ in texts]

    monkeypatch.setattr(mem_mod, "_embedding_models", {"BAAI/bge-small-en-v1.5": FakeModel()})

    from natalie.features.sync import sync_vault

    note = vault / "will-be-deleted.md"
    note.write_text("hello")
    sync_vault(db, vault, config, full=False)

    row = db.execute("SELECT id FROM notes WHERE path = 'will-be-deleted.md'").fetchone()
    assert row is not None

    # Delete the file
    note.unlink()

    result = sync_vault(db, vault, config, full=False)  # incremental
    assert result["removed"] >= 1
    row = db.execute("SELECT id FROM notes WHERE path = 'will-be-deleted.md'").fetchone()
    assert row is None
