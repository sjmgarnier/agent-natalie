from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import natalie.server as srv

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
        "INSERT INTO tasks (path, line, text, done, due_date, priority, recurrence) VALUES (?,?,?,?,?,?,?)",
        ("todo.md", 1, "Buy milk", 0, None, None, None),
    )
    db.execute(
        "INSERT INTO tasks (path, line, text, done, due_date, priority, recurrence) VALUES (?,?,?,?,?,?,?)",
        ("todo.md", 2, "Done thing", 1, None, None, None),
    )
    db.commit()
    _setup_server(vault, vault)

    result = srv.task_list(done=False)
    assert len(result) == 1
    assert result[0]["text"] == "Buy milk"
    assert result[0]["done"] is False


def test_task_list_done_true_includes_completed(vault, db):
    db.execute(
        "INSERT INTO tasks (path, line, text, done, due_date, priority, recurrence) VALUES (?,?,?,?,?,?,?)",
        ("todo.md", 1, "Open task", 0, None, None, None),
    )
    db.execute(
        "INSERT INTO tasks (path, line, text, done, due_date, priority, recurrence) VALUES (?,?,?,?,?,?,?)",
        ("todo.md", 2, "Done task", 1, None, None, None),
    )
    db.commit()
    _setup_server(vault, vault)

    result = srv.task_list(done=True)
    assert len(result) == 2


def test_task_list_overdue_flag(vault, db):
    db.execute(
        "INSERT INTO tasks (path, line, text, done, due_date, priority, recurrence) VALUES (?,?,?,?,?,?,?)",
        ("todo.md", 1, "Late task", 0, "2020-01-01", None, None),
    )
    db.commit()
    _setup_server(vault, vault)

    result = srv.task_list()
    assert result[0]["overdue"] is True


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
