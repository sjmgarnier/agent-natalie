from __future__ import annotations

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
    assert called_url == "http://127.0.0.1:27123/vault/notes/hello.md"


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
    assert called_url == "http://127.0.0.1:27123/vault/out.md"
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


def test_note_write_succeeds_when_rest_returns_200_and_no_local_file(
    vault: Path, db, config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C1: note_write must not raise FileNotFoundError when Obsidian REST returns 200."""
    monkeypatch.setattr(srv, "_vault", vault)
    monkeypatch.setattr(srv, "_db", db)
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
    monkeypatch.setattr(srv, "_db", db)
    monkeypatch.setattr(srv, "_config", config)

    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("natalie.server.httpx.put", return_value=mock_response):
        srv.note_write("indexed.md", "# Indexed\n\nShould be in DB")

    row = db.execute("SELECT title FROM notes WHERE path = 'indexed.md'").fetchone()
    assert row is not None  # note was indexed
