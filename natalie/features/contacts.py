from __future__ import annotations

from pathlib import Path

import frontmatter as fm

from ..config import NatalieConfig


def _contacts_dir(vault: Path, config: NatalieConfig) -> Path:
    return vault / config.contacts.directory


def _contact_path(vault: Path, config: NatalieConfig, slug: str) -> Path:
    return _contacts_dir(vault, config) / f"{slug}.md"


def update_contact(vault: Path, config: NatalieConfig, slug: str, fields: dict) -> dict:
    """Create or update a contact card (merge fields into existing frontmatter)."""
    path = _contact_path(vault, config, slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        post = fm.loads(path.read_text(encoding="utf-8"))
        post.metadata.update(fields)
    else:
        post = fm.Post(content="", **fields)
    path.write_text(fm.dumps(post), encoding="utf-8")
    return {"updated": True, "slug": slug}


def get_contact(vault: Path, config: NatalieConfig, slug: str) -> dict | None:
    """Return contact metadata dict, or None if not found."""
    path = _contact_path(vault, config, slug)
    if not path.exists():
        return None
    post = fm.loads(path.read_text(encoding="utf-8"))
    return dict(post.metadata)


def list_contacts(vault: Path, config: NatalieConfig) -> list[str]:
    """Return slugs of all contact cards, sorted."""
    contacts_dir = _contacts_dir(vault, config)
    if not contacts_dir.exists():
        return []
    return sorted(p.stem for p in contacts_dir.glob("*.md"))
