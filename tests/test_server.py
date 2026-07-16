from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import natalie.server as srv
from natalie.features import memory as mem


def test_mcp_server_advertises_client_neutral_instructions() -> None:
    instructions = srv.MCP_INSTRUCTIONS
    assert srv.mcp.instructions == instructions
    assert "vault-managed content" in instructions[:512]
    for required in ("conventions", "memory", "note_move", "tasks", "documents", "contacts"):
        assert required in instructions
    for forbidden in ("Claude", "OpenCode", "Codex", "persona", "model"):
        assert forbidden not in instructions


@pytest.mark.asyncio
async def test_mcp_server_instruction_change_preserves_tool_contract() -> None:
    tools = await srv.mcp.list_tools()
    assert {tool.name for tool in tools} == {
        "ping",
        "watcher_status",
        "note_list",
        "vault_stats",
        "memory_search",
        "memory_store",
        "note_read",
        "note_write",
        "note_move",
        "note_frontmatter_update",
        "convention_list",
        "convention_add",
        "convention_delete",
        "convention_update",
        "onboarding_status",
        "onboarding_complete",
        "task_list",
        "task_capture",
        "task_complete",
        "task_cancel",
        "task_update",
        "document_file",
        "document_list",
        "contact_get",
        "contact_update",
        "contact_list",
        "contact_search",
    }
    assert all(tool.inputSchema for tool in tools)


# ---------------------------------------------------------------------------
# main() — vault-not-found path
# ---------------------------------------------------------------------------


def test_main_starts_in_degraded_mode_when_vault_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    run_called: list[bool] = []
    monkeypatch.setattr(srv, "require_vault", lambda: (_ for _ in ()).throw(RuntimeError("vault not found")))
    monkeypatch.setattr(srv.mcp, "run", lambda: run_called.append(True))
    srv.main()
    assert run_called


def test_main_degraded_mode_skips_init_db(monkeypatch: pytest.MonkeyPatch) -> None:
    init_db_called: list[bool] = []
    monkeypatch.setattr(srv, "require_vault", lambda: (_ for _ in ()).throw(RuntimeError("no vault at /foo")))
    monkeypatch.setattr(srv, "init_db", lambda v: init_db_called.append(True))
    monkeypatch.setattr(srv.mcp, "run", lambda: None)
    srv.main()
    assert not init_db_called


# ---------------------------------------------------------------------------
# note_write
# ---------------------------------------------------------------------------


def test_note_write_rejects_empty_path(vault: Path, config, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    monkeypatch.setattr(srv, "_config", config)
    with pytest.raises(ValueError, match="path"):
        srv.note_write("", "content")


def test_note_write_rejects_whitespace_path(vault: Path, config, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    monkeypatch.setattr(srv, "_config", config)
    with pytest.raises(ValueError, match="path"):
        srv.note_write("   ", "content")


def test_note_write_rejects_json_path(vault: Path, config, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    monkeypatch.setattr(srv, "_config", config)
    with pytest.raises(ValueError, match=r"Only \.md files are accepted"):
        srv.note_write("data.json", '{"key": "value"}')


def test_note_write_rejects_toml_path(vault: Path, config, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    monkeypatch.setattr(srv, "_config", config)
    with pytest.raises(ValueError, match=r"Only \.md files are accepted"):
        srv.note_write("settings.toml", "[section]\nkey = 'value'")


def test_note_write_creates_file_on_disk(vault: Path, config, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    monkeypatch.setattr(srv, "_config", config)
    result = srv.note_write("new-note.md", "# New Note\n\nContent here")
    assert result == {"written": True, "path": "new-note.md"}
    assert (vault / "new-note.md").read_text(encoding="utf-8") == "# New Note\n\nContent here"


def test_note_write_indexes_note_in_db(vault: Path, db, config, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    monkeypatch.setattr(srv, "_config", config)
    srv.note_write("indexed.md", "# Indexed\n\nShould be in DB")
    row = db.execute("SELECT title FROM notes WHERE path = 'indexed.md'").fetchone()
    assert row is not None


def test_note_write_normalizes_path_qualified_wikilink(
    vault: Path, db, config, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    monkeypatch.setattr(srv, "_config", config)
    srv.note_write("Projects/Alpha/Meeting Notes.md", "# Meeting Notes")
    srv.note_write("Journal.md", "See [[Projects/Alpha/Meeting Notes]] for details.")
    content = (vault / "Journal.md").read_text(encoding="utf-8")
    assert content == "See [[Meeting Notes]] for details."


def test_note_write_leaves_bare_wikilink_unchanged(
    vault: Path, config, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    monkeypatch.setattr(srv, "_config", config)
    srv.note_write("Journal.md", "See [[Meeting Notes]] for details.")
    content = (vault / "Journal.md").read_text(encoding="utf-8")
    assert content == "See [[Meeting Notes]] for details."


def test_note_write_leaves_code_block_wikilink_untouched(
    vault: Path, config, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    monkeypatch.setattr(srv, "_config", config)
    body = "```\n[[Projects/Alpha/Example]]\n```"
    srv.note_write("Journal.md", body)
    assert (vault / "Journal.md").read_text(encoding="utf-8") == body


def test_note_write_retains_disambiguating_path_on_collision(
    vault: Path, config, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    monkeypatch.setattr(srv, "_config", config)
    srv.note_write("Projects/Alpha/Meeting Notes.md", "a")
    srv.note_write("Projects/Beta/Meeting Notes.md", "b")
    srv.note_write("Journal.md", "[[Projects/Alpha/Meeting Notes]]")
    content = (vault / "Journal.md").read_text(encoding="utf-8")
    assert content == "[[Alpha/Meeting Notes]]"


# ---------------------------------------------------------------------------
# note_move
# ---------------------------------------------------------------------------


def _set_vault(monkeypatch: pytest.MonkeyPatch, vault: Path, config) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    monkeypatch.setattr(srv, "_config", config)


def test_note_move_relocates_file_and_reports_paths(
    vault: Path, config, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_vault(monkeypatch, vault, config)
    srv.note_write("Projects/Alpha/Old.md", "# Old")
    result = srv.note_move("Projects/Alpha/Old.md", "Projects/Beta/New.md")
    assert result["moved"] is True
    assert result["from_path"] == "Projects/Alpha/Old.md"
    assert result["to_path"] == "Projects/Beta/New.md"
    assert not (vault / "Projects/Alpha/Old.md").exists()
    assert (vault / "Projects/Beta/New.md").read_text(encoding="utf-8") == "# Old"


def test_note_move_rejects_empty_paths(vault: Path, config, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_vault(monkeypatch, vault, config)
    with pytest.raises(ValueError, match="path"):
        srv.note_move("", "New.md")
    with pytest.raises(ValueError, match="path"):
        srv.note_move("Old.md", "")


def test_note_move_rejects_out_of_vault_source(vault: Path, config, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_vault(monkeypatch, vault, config)
    with pytest.raises(ValueError, match="escapes"):
        srv.note_move("../outside.md", "New.md")


def test_note_move_rejects_out_of_vault_destination(
    vault: Path, config, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_vault(monkeypatch, vault, config)
    srv.note_write("Old.md", "content")
    with pytest.raises(ValueError, match="escapes"):
        srv.note_move("Old.md", "../outside.md")


def test_note_move_rejects_non_md_source(vault: Path, config, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_vault(monkeypatch, vault, config)
    with pytest.raises(ValueError, match=r"Only \.md files are accepted"):
        srv.note_move("data.json", "New.md")


def test_note_move_rejects_non_md_destination(vault: Path, config, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_vault(monkeypatch, vault, config)
    srv.note_write("Old.md", "content")
    with pytest.raises(ValueError, match=r"Only \.md files are accepted"):
        srv.note_move("Old.md", "data.json")


def test_note_move_rejects_missing_source(vault: Path, config, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_vault(monkeypatch, vault, config)
    with pytest.raises(ValueError, match="not found"):
        srv.note_move("missing.md", "New.md")


def test_note_move_rejects_existing_destination(vault: Path, config, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_vault(monkeypatch, vault, config)
    srv.note_write("Old.md", "old content")
    srv.note_write("New.md", "existing content")
    with pytest.raises(ValueError, match="already exists"):
        srv.note_move("Old.md", "New.md")
    assert (vault / "Old.md").exists()
    assert (vault / "New.md").read_text(encoding="utf-8") == "existing content"


def test_note_move_preserves_note_id_task_and_embedding(
    vault: Path, db, config, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import patch

    from tests.test_memory import _FakeEmbedding

    _set_vault(monkeypatch, vault, config)
    srv.note_write("Old.md", "- [ ] Do the thing\n")
    with patch("natalie.features.memory.TextEmbedding", _FakeEmbedding):
        mem.embed_notes(db)
    old_id = db.execute("SELECT id FROM notes WHERE path = 'Old.md'").fetchone()["id"]

    srv.note_move("Old.md", "New.md")

    new_row = db.execute("SELECT id, title FROM notes WHERE path = 'New.md'").fetchone()
    assert new_row["id"] == old_id
    assert new_row["title"] == "New"
    assert db.execute("SELECT * FROM embeddings WHERE note_id = ?", (old_id,)).fetchone() is not None
    assert db.execute("SELECT COUNT(*) FROM tasks WHERE path = 'Old.md'").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM tasks WHERE path = 'New.md'").fetchone()[0] == 1


def test_note_move_repairs_bare_link_broken_by_rename(
    vault: Path, config, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_vault(monkeypatch, vault, config)
    srv.note_write("Old Name.md", "# Old Name")
    srv.note_write("Journal.md", "See [[Old Name]] for details.")

    result = srv.note_move("Old Name.md", "New Name.md")

    assert result["links_updated_in"] == ["Journal.md"]
    content = (vault / "Journal.md").read_text(encoding="utf-8")
    assert content == "See [[New Name]] for details."


def test_note_move_repairs_legacy_path_qualified_link(
    vault: Path, db, config, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_vault(monkeypatch, vault, config)
    srv.note_write("old/folder/Note.md", "# Note")
    # Bypass note_write's own normalization to simulate a pre-existing legacy link.
    (vault / "Journal.md").write_text("[[old/folder/Note]]", encoding="utf-8")
    mem.index_note(db, vault, vault / "Journal.md")

    result = srv.note_move("old/folder/Note.md", "Projects/Alpha/Note.md")

    assert result["links_updated_in"] == ["Journal.md"]
    content = (vault / "Journal.md").read_text(encoding="utf-8")
    assert content == "[[Note]]"


def test_note_move_leaves_unrelated_links_untouched(
    vault: Path, config, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_vault(monkeypatch, vault, config)
    srv.note_write("Old Name.md", "# Old Name")
    srv.note_write("Journal.md", "See [[Unrelated Note]] and [[Another One]].")

    result = srv.note_move("Old Name.md", "New Name.md")

    assert result["links_updated_in"] == []
    content = (vault / "Journal.md").read_text(encoding="utf-8")
    assert content == "See [[Unrelated Note]] and [[Another One]]."


def test_note_move_excludes_self_from_backlink_candidates(
    vault: Path, db, config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A note that self-references its own old name must not be treated as its
    own backlink candidate — that would re-write+re-index it a second time
    inside the same note_move call, destroying the embedding relocate_note
    just preserved. Self-links are out of scope ("other notes" per spec)."""
    from unittest.mock import patch

    from tests.test_memory import _FakeEmbedding

    _set_vault(monkeypatch, vault, config)
    srv.note_write("Old Name.md", "See also [[Old Name]] elsewhere.")
    with patch("natalie.features.memory.TextEmbedding", _FakeEmbedding):
        mem.embed_notes(db)
    old_id = db.execute("SELECT id FROM notes WHERE path = 'Old Name.md'").fetchone()["id"]

    result = srv.note_move("Old Name.md", "New Name.md")

    assert result["links_updated_in"] == []
    assert db.execute("SELECT * FROM embeddings WHERE note_id = ?", (old_id,)).fetchone() is not None
    assert (vault / "New Name.md").read_text(encoding="utf-8") == "See also [[Old Name]] elsewhere."


def test_note_move_folder_only_move_preserves_backlinking_notes_embeddings(
    vault: Path, db, config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A folder-only move (basename unchanged, no collision) re-resolves a
    bare link to identical text — the backlinking note must not be rewritten
    or reindexed, since that would needlessly invalidate its embedding."""
    from unittest.mock import patch

    from tests.test_memory import _FakeEmbedding

    _set_vault(monkeypatch, vault, config)
    srv.note_write("Projects/Alpha/Note.md", "# Note")
    srv.note_write("Journal.md", "See [[Note]] for details.")
    with patch("natalie.features.memory.TextEmbedding", _FakeEmbedding):
        mem.embed_notes(db)
    journal_id = db.execute("SELECT id FROM notes WHERE path = 'Journal.md'").fetchone()["id"]

    result = srv.note_move("Projects/Alpha/Note.md", "Projects/Beta/Note.md")

    assert result["links_updated_in"] == []
    assert db.execute("SELECT * FROM embeddings WHERE note_id = ?", (journal_id,)).fetchone() is not None
    assert (vault / "Journal.md").read_text(encoding="utf-8") == "See [[Note]] for details."


def test_note_move_no_referencing_notes_leaves_vault_unchanged(
    vault: Path, config, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_vault(monkeypatch, vault, config)
    srv.note_write("Old Name.md", "# Old Name")
    srv.note_write("Unrelated.md", "Nothing to see here.")

    result = srv.note_move("Old Name.md", "New Name.md")

    assert result["links_updated_in"] == []
    assert (vault / "Unrelated.md").read_text(encoding="utf-8") == "Nothing to see here."


# ---------------------------------------------------------------------------
# note_frontmatter_update
# ---------------------------------------------------------------------------


def test_note_frontmatter_update_rejects_empty_path(
    vault: Path, config, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    monkeypatch.setattr(srv, "_config", config)
    with pytest.raises(ValueError, match="path"):
        srv.note_frontmatter_update("", fields={"status": "done"})


def test_note_frontmatter_update_rejects_non_md_path(
    vault: Path, config, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    monkeypatch.setattr(srv, "_config", config)
    with pytest.raises(ValueError, match=r"Only \.md files are accepted"):
        srv.note_frontmatter_update("data.json", fields={"status": "done"})


def test_note_frontmatter_update_merges_fields_on_disk(
    vault: Path, config, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    monkeypatch.setattr(srv, "_config", config)
    (vault / "note.md").write_text("---\ntitle: Test\n---\nBody text.", encoding="utf-8")
    result = srv.note_frontmatter_update("note.md", fields={"status": "done"})
    assert result == {"updated": True, "path": "note.md"}
    content = (vault / "note.md").read_text(encoding="utf-8")
    assert "status: done" in content
    assert "Body text." in content


def test_note_frontmatter_update_reindexes_note_in_db(
    vault: Path, db, config, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    monkeypatch.setattr(srv, "_config", config)
    (vault / "note.md").write_text("---\ntitle: Test\n---\nBody text.", encoding="utf-8")
    srv.note_frontmatter_update("note.md", fields={"status": "done"})
    row = db.execute("SELECT tags FROM notes WHERE path = 'note.md'").fetchone()
    assert row is not None


def test_note_frontmatter_update_raises_if_note_missing(
    vault: Path, config, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    monkeypatch.setattr(srv, "_config", config)
    with pytest.raises(ValueError, match="Note not found"):
        srv.note_frontmatter_update("missing.md", fields={"status": "done"})


def test_memory_store_rejects_path_traversal(
    vault: Path, config: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    monkeypatch.setattr(srv, "_config", config)
    with pytest.raises(ValueError, match="escapes"):
        srv.memory_store(content="x", path="../../../etc/passwd")


def test_memory_store_canonicalizes_path_in_db(
    vault: Path, db: object, config: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    monkeypatch.setattr(srv, "_config", config)
    result = srv.memory_store(content="hello", path="subdir/../note.md")
    assert result["path"] == "note.md"
    row = db.execute("SELECT path FROM notes WHERE path = 'note.md'").fetchone()  # type: ignore[union-attr]
    assert row is not None


# ---------------------------------------------------------------------------
# Thread-local DB connections — C3
# ---------------------------------------------------------------------------


def test_get_db_returns_thread_local_connections(vault: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """C3: each FastMCP worker thread must get its own connection, not share the main-thread connection."""
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())

    connections: dict[str, int] = {}

    def capture(name: str) -> None:
        connections[name] = id(srv._get_db())

    t1 = threading.Thread(target=capture, args=("t1",))
    t2 = threading.Thread(target=capture, args=("t2",))
    t1.start()
    t1.join()
    t2.start()
    t2.join()

    assert connections["t1"] != connections["t2"], "Each thread must receive its own connection object"


def test_convention_update_tool_delegates_to_mem(monkeypatch: pytest.MonkeyPatch) -> None:
    with (
        patch("natalie.server._get_db", return_value=MagicMock()),
        patch("natalie.server.mem.convention_update", return_value=True) as mock_fn,
    ):
        result = srv.convention_update(1, rule="new rule")
    assert result["updated"] is True
    mock_fn.assert_called_once()


def test_convention_update_tool_returns_dict(vault: Path, config, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    monkeypatch.setattr(srv, "_config", config)
    add_result = srv.convention_add("code", "use snake_case")
    conv_id = add_result["id"]
    result = srv.convention_update(conv_id, rule="use snake_case always")
    assert isinstance(result, dict)
    assert result["updated"] is True
    assert result["id"] == conv_id


def test_watcher_status_survives_emitters_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _BadObserver:
        @property
        def emitters(self) -> None:
            raise RuntimeError("set changed size during iteration")

        def is_alive(self) -> bool:
            return True

        ident = 42
        daemon = True

    monkeypatch.setattr(srv, "_observer", _BadObserver())
    result = srv.watcher_status()
    assert result["alive"] is True
    assert result["path"] is None


def test_note_read_rejects_empty_path(vault: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    with pytest.raises(ValueError, match="path"):
        srv.note_read("")


def test_note_read_rejects_whitespace_path(vault: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    with pytest.raises(ValueError, match="path"):
        srv.note_read("   ")


def test_note_read_rejects_json_path(vault: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    with pytest.raises(ValueError, match=r"Only \.md files are accepted"):
        srv.note_read("config.json")


def test_note_read_rejects_toml_path(vault: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    with pytest.raises(ValueError, match=r"Only \.md files are accepted"):
        srv.note_read("settings.toml")


def test_task_capture_rejects_empty_rel_path(vault: Path, config, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    monkeypatch.setattr(srv, "_config", config)
    with pytest.raises(ValueError, match="rel_path"):
        srv.task_capture("", "My task")


def test_task_complete_rejects_empty_rel_path(vault: Path, config, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    monkeypatch.setattr(srv, "_config", config)
    with pytest.raises(ValueError, match="rel_path"):
        srv.task_complete("", "My task")


def test_task_update_rejects_empty_rel_path(vault: Path, config, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    monkeypatch.setattr(srv, "_config", config)
    with pytest.raises(ValueError, match="rel_path"):
        srv.task_update("", "My task", new_text="Updated")


def test_task_cancel_rejects_empty_rel_path(vault: Path, config, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    monkeypatch.setattr(srv, "_config", config)
    with pytest.raises(ValueError, match="rel_path"):
        srv.task_cancel("", "My task")


def test_contact_search_tool_delegates_to_contacts_mod(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_results = [
        {"path": "People/alice.md", "title": "Alice", "score": 0.9, "source": "keyword", "excerpt": "Alice"}
    ]
    with (
        patch("natalie.server._get_db", return_value=MagicMock()),
        patch("natalie.server._get_vault", return_value=Path("/vault")),
        patch("natalie.server._get_config", return_value=MagicMock()),
        patch("natalie.server.contacts_mod.search_contacts", return_value=mock_results),
    ):
        result = srv.contact_search("Alice")
    assert result == mock_results


def test_contact_search_clamps_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_search = MagicMock(return_value=[])
    with (
        patch("natalie.server._get_db", return_value=MagicMock()),
        patch("natalie.server._get_vault", return_value=Path("/vault")),
        patch("natalie.server._get_config", return_value=MagicMock()),
        patch("natalie.server.contacts_mod.search_contacts", mock_search),
    ):
        srv.contact_search("Alice", limit=10_000_000)
    assert mock_search.call_args.kwargs["limit"] == srv._MAX_LIMIT


def test_memory_search_clamps_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_kw = MagicMock(return_value=[])
    mock_se = MagicMock(return_value=[])
    with (
        patch("natalie.server._get_db", return_value=MagicMock()),
        patch("natalie.server._get_config", return_value=MagicMock()),
        patch("natalie.server.mem.keyword_search", mock_kw),
        patch("natalie.server.mem.semantic_search", mock_se),
    ):
        srv.memory_search("query", limit=10_000_000)
    assert mock_kw.call_args.kwargs["limit"] == srv._MAX_LIMIT * 2
    assert mock_se.call_args.kwargs["limit"] == srv._MAX_LIMIT * 2


def test_document_list_clamps_top_n(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_list = MagicMock(return_value=[])
    with (
        patch("natalie.server._get_vault", return_value=Path("/vault")),
        patch("natalie.server._get_config", return_value=MagicMock()),
        patch("natalie.server._get_db", return_value=MagicMock()),
        patch("natalie.server.docs_mod.list_documents", mock_list),
    ):
        srv.document_list(top_n=10_000_000)
    assert mock_list.call_args.args[7] == srv._MAX_LIMIT


# ---------------------------------------------------------------------------
# task_capture / task_complete — metadata delegation
# ---------------------------------------------------------------------------


def test_task_capture_passes_metadata_to_tasks_mod() -> None:
    expected = {
        "captured": True,
        "path": "tasks.md",
        "task": "File taxes",
        "due_date": "2026-06-30",
        "priority": "high",
        "recurrence": "every year",
    }
    with (
        patch("natalie.server._get_vault", return_value=Path("/vault")),
        patch("natalie.server._get_db", return_value=MagicMock()),
        patch("natalie.server.tasks_mod.capture_task", return_value=expected) as mock_fn,
        patch("natalie.server.tasks_mod.index_tasks"),
    ):
        result = srv.task_capture(
            "tasks.md",
            "File taxes",
            due_date="2026-06-30",
            priority="high",
            recurrence="every year",
        )
    assert result == expected
    mock_fn.assert_called_once_with(
        Path("/vault"),
        "tasks.md",
        "File taxes",
        tags=None,
        due_date="2026-06-30",
        priority="high",
        recurrence="every year",
    )


def test_task_complete_passes_through_dict() -> None:
    expected = {
        "completed": True,
        "path": "tasks.md",
        "task": "File taxes",
        "completed_date": "2026-06-04",
    }
    with (
        patch("natalie.server._get_vault", return_value=Path("/vault")),
        patch("natalie.server._get_db", return_value=MagicMock()),
        patch("natalie.server.tasks_mod.complete_task", return_value=expected) as mock_fn,
        patch("natalie.server.tasks_mod.index_tasks"),
    ):
        result = srv.task_complete("tasks.md", "File taxes")
    assert result == expected
    mock_fn.assert_called_once_with(Path("/vault"), "tasks.md", "File taxes")


def test_task_cancel_passes_through_dict() -> None:
    expected = {
        "cancelled": True,
        "path": "tasks.md",
        "task": "File taxes",
        "cancelled_date": "2026-06-04",
    }
    with (
        patch("natalie.server._get_vault", return_value=Path("/vault")),
        patch("natalie.server._get_db", return_value=MagicMock()),
        patch("natalie.server.tasks_mod.cancel_task", return_value=expected) as mock_fn,
        patch("natalie.server.tasks_mod.index_tasks"),
    ):
        result = srv.task_cancel("tasks.md", "File taxes")
    assert result == expected
    mock_fn.assert_called_once_with(Path("/vault"), "tasks.md", "File taxes")


def test_task_update_passes_through_dict() -> None:
    expected = {
        "updated": True,
        "path": "tasks.md",
        "task": "Write report",
        "due_date": "2026-07-01",
        "priority": "high",
        "recurrence": None,
    }
    with (
        patch("natalie.server._get_vault", return_value=Path("/vault")),
        patch("natalie.server._get_db", return_value=MagicMock()),
        patch("natalie.server.tasks_mod.update_task", return_value=expected) as mock_fn,
        patch("natalie.server.tasks_mod.index_tasks"),
    ):
        result = srv.task_update("tasks.md", "Write report", due_date="2026-07-01", priority="high")
    assert result == expected
    mock_fn.assert_called_once_with(
        Path("/vault"),
        "tasks.md",
        "Write report",
        new_text=None,
        tags=None,
        due_date="2026-07-01",
        priority="high",
        recurrence=None,
    )


# ---------------------------------------------------------------------------
# task_list — DB-backed query
# ---------------------------------------------------------------------------


def _setup_server(vault, db_vault):
    """Point module-level server state at the given vault/db."""
    srv._vault = vault
    srv._db_vault = db_vault
    srv._db_local = threading.local()


def test_task_list_returns_open_tasks_from_db(vault, db):
    # Insert directly into DB — no file on disk — proves task_list uses DB not filesystem scan
    db.execute(
        "INSERT INTO tasks (path, line, text, status, due_date, priority, recurrence) VALUES (?,?,?,?,?,?,?)",
        ("todo.md", 1, "Buy milk", "open", None, None, None),
    )
    db.execute(
        "INSERT INTO tasks (path, line, text, status, due_date, priority, recurrence) VALUES (?,?,?,?,?,?,?)",
        ("todo.md", 2, "Done thing", "done", None, None, None),
    )
    db.commit()
    _setup_server(vault, vault)

    result = srv.task_list(status="open")
    assert len(result) == 1
    assert result[0]["text"] == "Buy milk"
    assert result[0]["status"] == "open"


def test_task_list_rejects_invalid_status(vault, db):
    _setup_server(vault, vault)
    with pytest.raises(ValueError, match="status"):
        srv.task_list(status="bogus")


def test_task_list_done_status_returns_only_completed(vault, db):
    db.execute(
        "INSERT INTO tasks (path, line, text, status, due_date, priority, recurrence) VALUES (?,?,?,?,?,?,?)",
        ("todo.md", 1, "Open task", "open", None, None, None),
    )
    db.execute(
        "INSERT INTO tasks (path, line, text, status, due_date, priority, recurrence) VALUES (?,?,?,?,?,?,?)",
        ("todo.md", 2, "Done task", "done", None, None, None),
    )
    db.commit()
    _setup_server(vault, vault)

    result = srv.task_list(status="done")
    assert len(result) == 1
    assert result[0]["text"] == "Done task"


def test_task_list_cancelled_status_returns_only_cancelled(vault, db):
    db.execute(
        "INSERT INTO tasks (path, line, text, status, due_date, priority, recurrence) VALUES (?,?,?,?,?,?,?)",
        ("todo.md", 1, "Open task", "open", None, None, None),
    )
    db.execute(
        "INSERT INTO tasks (path, line, text, status, due_date, priority, recurrence) VALUES (?,?,?,?,?,?,?)",
        ("todo.md", 2, "Cancelled task", "cancelled", None, None, None),
    )
    db.commit()
    _setup_server(vault, vault)

    result = srv.task_list(status="cancelled")
    assert len(result) == 1
    assert result[0]["text"] == "Cancelled task"


def test_task_list_all_status_includes_every_state(vault, db):
    db.execute(
        "INSERT INTO tasks (path, line, text, status, due_date, priority, recurrence) VALUES (?,?,?,?,?,?,?)",
        ("todo.md", 1, "Open task", "open", None, None, None),
    )
    db.execute(
        "INSERT INTO tasks (path, line, text, status, due_date, priority, recurrence) VALUES (?,?,?,?,?,?,?)",
        ("todo.md", 2, "Done task", "done", None, None, None),
    )
    db.execute(
        "INSERT INTO tasks (path, line, text, status, due_date, priority, recurrence) VALUES (?,?,?,?,?,?,?)",
        ("todo.md", 3, "Cancelled task", "cancelled", None, None, None),
    )
    db.commit()
    _setup_server(vault, vault)

    result = srv.task_list(status="all")
    assert len(result) == 3


def test_task_list_overdue_flag(vault, db):
    db.execute(
        "INSERT INTO tasks (path, line, text, status, due_date, priority, recurrence) VALUES (?,?,?,?,?,?,?)",
        ("todo.md", 1, "Late task", "open", "2020-01-01", None, None),
    )
    db.commit()
    _setup_server(vault, vault)

    result = srv.task_list()
    assert result[0]["overdue"] is True


def test_task_list_cancelled_overdue_task_not_flagged(vault, db):
    db.execute(
        "INSERT INTO tasks (path, line, text, status, due_date, priority, recurrence) VALUES (?,?,?,?,?,?,?)",
        ("todo.md", 1, "Late cancelled task", "cancelled", "2020-01-01", None, None),
    )
    db.commit()
    _setup_server(vault, vault)

    result = srv.task_list(status="cancelled")
    assert result[0]["overdue"] is False


def test_task_list_returns_tags_as_list(vault, db):
    db.execute(
        "INSERT INTO tasks (path, line, text, status, due_date, priority, recurrence, tags) "
        "VALUES (?,?,?,?,?,?,?,?)",
        ("todo.md", 1, "Buy milk", "open", None, None, None, "#task #errands"),
    )
    db.commit()
    _setup_server(vault, vault)

    result = srv.task_list()
    assert result[0]["tags"] == ["#task", "#errands"]


def test_task_list_returns_empty_tags_for_untagged(vault, db):
    db.execute(
        "INSERT INTO tasks (path, line, text, status, due_date, priority, recurrence) VALUES (?,?,?,?,?,?,?)",
        ("todo.md", 1, "Buy milk", "open", None, None, None),
    )
    db.commit()
    _setup_server(vault, vault)

    result = srv.task_list()
    assert result[0]["tags"] == []


# ---------------------------------------------------------------------------
# Return type contract tests (Task 4)
# ---------------------------------------------------------------------------


def test_ping_returns_dict(vault: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    result = srv.ping()
    assert isinstance(result, dict)
    assert result["status"] == "ok"
    assert "vault" in result


def test_watcher_status_none_observer_returns_full_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(srv, "_observer", None)
    result = srv.watcher_status()
    assert result["alive"] is False
    assert "path" in result
    assert "recursive" in result
    assert "thread_ident" in result
    assert "daemon" in result
    assert "error" not in result


def test_note_read_returns_dict_when_found(vault: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    (vault / "hello.md").write_text("# Hello", encoding="utf-8")
    result = srv.note_read("hello.md")
    assert isinstance(result, dict)
    assert result["found"] is True
    assert result["content"] == "# Hello"
    assert result["path"] == "hello.md"


def test_note_read_returns_dict_when_missing(vault: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    result = srv.note_read("no-such-note.md")
    assert isinstance(result, dict)
    assert result["found"] is False
    assert result["content"] is None


def test_contact_list_returns_list_of_dicts(vault: Path, config, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_config", config)
    with patch("natalie.server.contacts_mod.list_contacts", return_value=["alice", "bob"]):
        result = srv.contact_list()
    assert all(isinstance(item, dict) for item in result)
    assert result[0]["slug"] == "alice"
    assert result[1]["slug"] == "bob"


def test_memory_search_keyword_only_result_includes_collection(
    vault: Path, config, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    monkeypatch.setattr(srv, "_config", config)
    with (
        patch(
            "natalie.server.mem.keyword_search",
            return_value=[{"path": "a.md", "title": "A", "excerpt": "x", "collection": "global"}],
        ),
        patch("natalie.server.mem.semantic_search", return_value=[]),
    ):
        results = srv.memory_search("test")
    assert len(results) == 1
    assert "collection" in results[0]
    assert results[0]["collection"] == "global"


def test_task_complete_rejects_empty_task_text(vault: Path, config, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    with pytest.raises(ValueError, match="task_text"):
        srv.task_complete("tasks.md", "")


def test_task_complete_rejects_whitespace_task_text(
    vault: Path, config, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    with pytest.raises(ValueError, match="task_text"):
        srv.task_complete("tasks.md", "   ")


def test_task_cancel_rejects_empty_task_text(vault: Path, config, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    with pytest.raises(ValueError, match="task_text"):
        srv.task_cancel("tasks.md", "")


def test_task_cancel_rejects_whitespace_task_text(
    vault: Path, config, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    with pytest.raises(ValueError, match="task_text"):
        srv.task_cancel("tasks.md", "   ")


def test_task_update_rejects_empty_task_text(vault: Path, config, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    with pytest.raises(ValueError, match="task_text"):
        srv.task_update("tasks.md", "", new_text="New text")


def test_task_update_rejects_whitespace_task_text(
    vault: Path, config, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    with pytest.raises(ValueError, match="task_text"):
        srv.task_update("tasks.md", "  ", new_text="New text")


# ---------------------------------------------------------------------------
# Graceful no-vault mode
# ---------------------------------------------------------------------------


def test_ping_returns_no_vault_when_vault_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(srv, "_vault", None)
    result = srv.ping()
    assert result["status"] == "no-vault"
    assert result["vault"] is None


def test_get_vault_raises_value_error_when_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(srv, "_vault", None)
    with pytest.raises(ValueError, match="No natalie vault found"):
        srv._get_vault()


def test_get_config_raises_value_error_when_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(srv, "_config", None)
    with pytest.raises(ValueError, match="No natalie vault found"):
        srv._get_config()


def test_get_db_raises_value_error_when_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(srv, "_db_vault", None)
    with pytest.raises(ValueError, match="No natalie vault found"):
        srv._get_db()


def test_main_no_vault_calls_mcp_run(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_runtime() -> None:
        raise RuntimeError("No vault found")

    monkeypatch.setattr(srv, "require_vault", _raise_runtime)
    run_called: list[bool] = []
    monkeypatch.setattr(srv.mcp, "run", lambda: run_called.append(True))
    srv.main()
    assert run_called, "mcp.run() was not called"


def test_main_no_vault_leaves_vault_none(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_runtime() -> None:
        raise RuntimeError("No vault found")

    init_db_called: list[bool] = []
    monkeypatch.setattr(srv, "_vault", None)  # ensure known starting state
    monkeypatch.setattr(srv, "require_vault", _raise_runtime)
    monkeypatch.setattr(srv, "init_db", lambda v: init_db_called.append(True))
    monkeypatch.setattr(srv.mcp, "run", lambda: None)
    srv.main()
    assert not init_db_called
    assert srv._vault is None
