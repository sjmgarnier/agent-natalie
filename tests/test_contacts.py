import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from natalie.features import memory as mem_mod
from natalie.features.contacts import get_contact, list_contacts, search_contacts, update_contact
from natalie.features.memory import embed_notes, index_note
from tests.helpers import write_note


def test_update_contact_creates_card(vault, config):
    update_contact(vault, config, "alice", {"name": "Alice Smith", "role": "Engineer"})
    path = vault / config.contacts.directory / "alice.md"
    assert path.exists()
    content = path.read_text()
    assert "Alice Smith" in content


def test_get_contact_returns_metadata(vault, config):
    update_contact(vault, config, "bob", {"name": "Bob Jones", "email": "bob@example.com"})
    card = get_contact(vault, config, "bob")
    assert card is not None
    assert card["name"] == "Bob Jones"
    assert card["email"] == "bob@example.com"


def test_get_contact_returns_none_if_missing(vault, config):
    assert get_contact(vault, config, "nobody") is None


def test_update_contact_merges_fields(vault, config):
    update_contact(vault, config, "carol", {"name": "Carol", "role": "Designer"})
    update_contact(vault, config, "carol", {"email": "carol@example.com"})
    card = get_contact(vault, config, "carol")
    assert card["name"] == "Carol"
    assert card["email"] == "carol@example.com"


def test_list_contacts_returns_slugs(vault, config):
    update_contact(vault, config, "alice", {"name": "Alice"})
    update_contact(vault, config, "bob", {"name": "Bob"})
    slugs = list_contacts(vault, config)
    assert "alice" in slugs
    assert "bob" in slugs


def test_update_contact_handles_content_key(vault, config):
    from natalie.features.contacts import get_contact, update_contact

    result = update_contact(vault, config, "alice", {"content": "bio text", "name": "Alice"})
    assert result["updated"] is True
    data = get_contact(vault, config, "alice")
    assert data["content"] == "bio text"
    assert data["name"] == "Alice"


def test_get_contact_returns_whitespace_only_body(vault, config):
    """get_contact must include whitespace-only body (e.g. newlines) — B7."""
    update_contact(vault, config, "dave", {"name": "Dave", "content": "\n"})
    card = get_contact(vault, config, "dave")
    assert card is not None
    assert "content" in card


def test_update_contact_rejects_traversal_in_directory(vault, config):
    """A config.contacts.directory that escapes the vault must raise ValueError."""
    import pytest

    from natalie.config import ContactsConfig, NatalieConfig
    from natalie.features.contacts import update_contact

    bad_config = NatalieConfig(contacts=ContactsConfig(directory="../../etc"))
    with pytest.raises(ValueError):
        update_contact(vault, bad_config, "passwd", {"name": "Evil"})


@given(slug=st.one_of(st.just(""), st.text(alphabet="\t\n ", min_size=1, max_size=20)))
@settings(max_examples=50, suppress_health_check=["function_scoped_fixture"])
def test_update_contact_rejects_empty_slug(vault, config, slug):
    with pytest.raises(ValueError, match="empty"):
        update_contact(vault, config, slug, {"name": "Test"})


# ── search_contacts ───────────────────────────────────────────────────────────


def test_search_contacts_keyword_match(vault: Path, db: sqlite3.Connection, config: Any) -> None:
    update_contact(vault, config, "alice", {"name": "Alice Engineer", "company": "Acme Corp"})
    index_note(db, vault, vault / config.contacts.directory / "alice.md")
    results = search_contacts(db, vault, config, "Alice Engineer")
    assert len(results) >= 1
    assert any(r["path"].endswith("alice.md") for r in results)


def test_search_contacts_no_match_returns_empty(vault: Path, db: sqlite3.Connection, config: Any) -> None:
    update_contact(vault, config, "bob", {"name": "Bob Jones"})
    index_note(db, vault, vault / config.contacts.directory / "bob.md")
    results = search_contacts(db, vault, config, "xyzzy")
    assert results == []


def test_search_contacts_result_has_source_field(vault: Path, db: sqlite3.Connection, config: Any) -> None:
    update_contact(vault, config, "dave", {"name": "Dave Manager"})
    index_note(db, vault, vault / config.contacts.directory / "dave.md")
    results = search_contacts(db, vault, config, "Dave Manager")
    assert results[0]["source"] in ("keyword", "semantic", "hybrid")


def test_search_contacts_path_filter_excludes_non_contacts(
    vault: Path, db: sqlite3.Connection, config: Any
) -> None:
    write_note(vault, "Notes/alice-meeting.md", "# Alice Meeting\nAlice is a great engineer")
    index_note(db, vault, vault / "Notes" / "alice-meeting.md")
    update_contact(vault, config, "alice", {"name": "Alice Engineer"})
    index_note(db, vault, vault / config.contacts.directory / "alice.md")
    results = search_contacts(db, vault, config, "Alice Engineer")
    assert all(config.contacts.directory in r["path"] for r in results)


def test_search_contacts_semantic(
    vault: Path, db: sqlite3.Connection, config: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeModel:
        def embed(self, texts: list[str]) -> Any:
            rng = np.random.default_rng(42)
            for _ in texts:
                yield rng.random(384).astype(np.float32)

    monkeypatch.setattr(mem_mod, "_embedding_models", {"BAAI/bge-small-en-v1.5": FakeModel()})
    update_contact(vault, config, "carol", {"name": "Carol Designer", "content": "UX expert"})
    index_note(db, vault, vault / config.contacts.directory / "carol.md")
    embed_notes(db)
    results = search_contacts(db, vault, config, "UX design", model_name="BAAI/bge-small-en-v1.5")
    assert isinstance(results, list)
    if results:
        assert "source" in results[0]


def test_search_contacts_empty_query_raises(vault: Path, db: sqlite3.Connection, config: Any) -> None:
    with pytest.raises(ValueError, match="query"):
        search_contacts(db, vault, config, "")


def test_search_contacts_whitespace_query_raises(vault: Path, db: sqlite3.Connection, config: Any) -> None:
    with pytest.raises(ValueError, match="query"):
        search_contacts(db, vault, config, "   ")
