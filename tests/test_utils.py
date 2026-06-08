from __future__ import annotations

import pytest

from natalie.utils import require_md_path


def test_require_md_path_accepts_md() -> None:
    require_md_path("note.md")  # must not raise


def test_require_md_path_accepts_md_uppercase() -> None:
    require_md_path("note.MD")  # case-insensitive; must not raise


def test_require_md_path_accepts_nested_md() -> None:
    require_md_path("Projects/myproject/note.md")  # must not raise


def test_require_md_path_rejects_json() -> None:
    with pytest.raises(ValueError, match=r"Only \.md files are accepted"):
        require_md_path("config.json")


def test_require_md_path_rejects_toml() -> None:
    with pytest.raises(ValueError, match=r"Only \.md files are accepted"):
        require_md_path("settings.toml")


def test_require_md_path_rejects_no_extension() -> None:
    with pytest.raises(ValueError, match=r"Only \.md files are accepted"):
        require_md_path("README")


def test_require_md_path_includes_hint_in_message() -> None:
    with pytest.raises(ValueError, match="Use the Read tool"):
        require_md_path("data.json", hint="Use the Read tool for this.")


def test_require_md_path_names_offending_path_in_message() -> None:
    with pytest.raises(ValueError, match="data.json"):
        require_md_path("data.json")
