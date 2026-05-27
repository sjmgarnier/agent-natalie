import pytest
from natalie.features.contacts import update_contact, get_contact, list_contacts


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
