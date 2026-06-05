from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

import natalie.server as srv

# ---------------------------------------------------------------------------
# main() — vault-not-found path
# ---------------------------------------------------------------------------


def test_main_exits_when_vault_not_found() -> None:
    with (
        patch("natalie.server.require_vault", side_effect=RuntimeError("vault not found")),
        pytest.raises(SystemExit) as exc_info,
    ):
        srv.main()
    assert str(exc_info.value) == "vault not found"


def test_main_exit_message_matches_exception_text() -> None:
    with (
        patch("natalie.server.require_vault", side_effect=RuntimeError("no vault at /foo")),
        pytest.raises(SystemExit) as exc_info,
    ):
        srv.main()
    assert "no vault at /foo" in str(exc_info.value)


# ---------------------------------------------------------------------------
# _obsidian_read — REST success path
# ---------------------------------------------------------------------------


def test_obsidian_read_returns_rest_response_on_200(vault: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "# Hello from REST"

    with patch("natalie.server.httpx.get", return_value=mock_response) as mock_get:
        result = srv._obsidian_read(vault, "notes/hello.md")

    assert result == "# Hello from REST"
    called_url = mock_get.call_args[0][0]
    assert called_url == "https://127.0.0.1:27123/vault/notes/hello.md"


def test_obsidian_read_url_encodes_spaces_in_path(vault: Path) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "content"

    with patch("natalie.server.httpx.get", return_value=mock_response) as mock_get:
        srv._obsidian_read(vault, "my notes/a note.md")

    called_url = mock_get.call_args[0][0]
    assert "my%20notes/a%20note.md" in called_url


def test_obsidian_read_url_preserves_slashes(vault: Path) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "ok"

    with patch("natalie.server.httpx.get", return_value=mock_response) as mock_get:
        srv._obsidian_read(vault, "sub/dir/note.md")

    called_url = mock_get.call_args[0][0]
    assert "/vault/sub/dir/note.md" in called_url


def test_obsidian_read_sends_auth_header_when_api_key_set(vault: Path) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "content"

    with patch("natalie.server.httpx.get", return_value=mock_response) as mock_get:
        srv._obsidian_read(vault, "note.md", api_key="my-secret-key")

    headers = mock_get.call_args.kwargs.get("headers", {})
    assert headers.get("Authorization") == "Bearer my-secret-key"


def test_obsidian_read_sends_no_auth_header_when_api_key_empty(vault: Path) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "content"

    with patch("natalie.server.httpx.get", return_value=mock_response) as mock_get:
        srv._obsidian_read(vault, "note.md", api_key="")

    headers = mock_get.call_args.kwargs.get("headers", {})
    assert "Authorization" not in headers


# ---------------------------------------------------------------------------
# _obsidian_read — REST failure → file I/O fallback
# ---------------------------------------------------------------------------


def test_obsidian_read_falls_back_to_file_on_request_error(vault: Path) -> None:
    (vault / "fallback.md").write_text("file content", encoding="utf-8")

    with patch("natalie.server.httpx.get", side_effect=httpx.ConnectError("refused")):
        result = srv._obsidian_read(vault, "fallback.md")

    assert result == "file content"


def test_obsidian_read_falls_back_to_file_on_non_200_status(vault: Path) -> None:
    (vault / "note.md").write_text("direct read", encoding="utf-8")

    mock_response = MagicMock()
    mock_response.status_code = 404

    with patch("natalie.server.httpx.get", return_value=mock_response):
        result = srv._obsidian_read(vault, "note.md")

    assert result == "direct read"


def test_obsidian_read_returns_none_when_file_missing_and_rest_fails(vault: Path) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 503

    with patch("natalie.server.httpx.get", return_value=mock_response):
        result = srv._obsidian_read(vault, "nonexistent.md")

    assert result is None


# ---------------------------------------------------------------------------
# _obsidian_write — REST success path
# ---------------------------------------------------------------------------


def test_obsidian_write_uses_rest_on_200(vault: Path) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("natalie.server.httpx.put", return_value=mock_response) as mock_put:
        srv._obsidian_write(vault, "out.md", "new content")

    called_url = mock_put.call_args[0][0]
    assert called_url == "https://127.0.0.1:27123/vault/out.md"
    assert not (vault / "out.md").exists()


def test_obsidian_write_uses_rest_on_204(vault: Path) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 204

    with patch("natalie.server.httpx.put", return_value=mock_response):
        srv._obsidian_write(vault, "out.md", "new content")

    assert not (vault / "out.md").exists()


def test_obsidian_write_url_encodes_path(vault: Path) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("natalie.server.httpx.put", return_value=mock_response) as mock_put:
        srv._obsidian_write(vault, "my notes/a note.md", "x")

    called_url = mock_put.call_args[0][0]
    assert "my%20notes/a%20note.md" in called_url


def test_obsidian_write_sends_auth_header_when_api_key_set(vault: Path) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("natalie.server.httpx.put", return_value=mock_response) as mock_put:
        srv._obsidian_write(vault, "note.md", "content", api_key="my-secret-key")

    headers = mock_put.call_args.kwargs.get("headers", {})
    assert headers.get("Authorization") == "Bearer my-secret-key"


def test_obsidian_write_sends_no_auth_header_when_api_key_empty(vault: Path) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("natalie.server.httpx.put", return_value=mock_response) as mock_put:
        srv._obsidian_write(vault, "note.md", "content", api_key="")

    headers = mock_put.call_args.kwargs.get("headers", {})
    assert "Authorization" not in headers


# ---------------------------------------------------------------------------
# _obsidian_write — REST failure → file I/O fallback
# ---------------------------------------------------------------------------


def test_obsidian_write_falls_back_to_file_on_request_error(vault: Path) -> None:
    with patch("natalie.server.httpx.put", side_effect=httpx.ConnectError("refused")):
        srv._obsidian_write(vault, "written.md", "fallback content")

    assert (vault / "written.md").read_text(encoding="utf-8") == "fallback content"


def test_obsidian_write_falls_back_to_file_on_non_200_status(vault: Path) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 500

    with patch("natalie.server.httpx.put", return_value=mock_response):
        srv._obsidian_write(vault, "written.md", "fallback content")

    assert (vault / "written.md").read_text(encoding="utf-8") == "fallback content"


def test_obsidian_write_creates_parent_dirs_on_fallback(vault: Path) -> None:
    with patch("natalie.server.httpx.put", side_effect=httpx.ConnectError("refused")):
        srv._obsidian_write(vault, "deep/nested/note.md", "hello")

    assert (vault / "deep" / "nested" / "note.md").read_text(encoding="utf-8") == "hello"


# ---------------------------------------------------------------------------
# note_write — REST success must not crash when local file absent (C1)
# ---------------------------------------------------------------------------


def test_note_write_rejects_empty_path(vault: Path, config, monkeypatch: pytest.MonkeyPatch) -> None:
    """I6: note_write with empty path must raise ValueError."""
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    monkeypatch.setattr(srv, "_config", config)
    with pytest.raises(ValueError, match="path"):
        srv.note_write("", "content")


def test_note_write_rejects_whitespace_path(vault: Path, config, monkeypatch: pytest.MonkeyPatch) -> None:
    """I6: note_write with whitespace-only path must raise ValueError."""
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    monkeypatch.setattr(srv, "_config", config)
    with pytest.raises(ValueError, match="path"):
        srv.note_write("   ", "content")


def test_note_write_succeeds_when_rest_returns_200_and_no_local_file(
    vault: Path, config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C1: note_write must not raise FileNotFoundError when Obsidian REST returns 200."""
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    monkeypatch.setattr(srv, "_config", config)

    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("natalie.server.httpx.put", return_value=mock_response):
        result = srv.note_write("new-note.md", "# New Note\n\nContent here")

    assert result == {"written": True, "path": "new-note.md"}


def test_note_write_indexes_note_in_db_when_rest_succeeds(
    vault: Path, db, config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C1: note_write must index the note in the DB even when REST handles the write."""
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db_vault", vault)
    monkeypatch.setattr(srv, "_db_local", threading.local())
    monkeypatch.setattr(srv, "_config", config)

    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("natalie.server.httpx.put", return_value=mock_response):
        srv.note_write("indexed.md", "# Indexed\n\nShould be in DB")

    row = db.execute("SELECT title FROM notes WHERE path = 'indexed.md'").fetchone()
    assert row is not None  # note was indexed via committed thread-local connection


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
    assert result is True
    mock_fn.assert_called_once()


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
        patch("natalie.server.tasks_mod.capture_task", return_value=expected) as mock_fn,
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
        patch("natalie.server.tasks_mod.complete_task", return_value=expected) as mock_fn,
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
        patch("natalie.server.tasks_mod.update_task", return_value=expected) as mock_fn,
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
