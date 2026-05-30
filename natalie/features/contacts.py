from __future__ import annotations

from pathlib import Path
from typing import Any

import frontmatter as fm

from ..config import NatalieConfig
from ..utils import safe_join


def _contacts_dir(vault: Path, config: NatalieConfig) -> Path:
    return safe_join(vault, config.contacts.directory)


def _contact_path(vault: Path, config: NatalieConfig, slug: str) -> Path:
    contacts_dir = _contacts_dir(vault, config)
    return safe_join(contacts_dir, f"{slug}.md")


def update_contact(vault: Path, config: NatalieConfig, slug: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Create or update a contact card (merge fields into existing frontmatter)."""
    if not slug or not slug.strip():
        raise ValueError("slug must not be empty or whitespace")
    path = _contact_path(vault, config, slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = dict(fields)  # avoid mutating caller's dict
    new_body = fields.pop("content", None)
    if path.exists():
        post = fm.loads(path.read_text(encoding="utf-8"))
        post.metadata.update(fields)
        if new_body is not None:
            post.content = new_body
    else:
        post = fm.Post(content=new_body or "")
        post.metadata.update(fields)
    path.write_text(fm.dumps(post), encoding="utf-8")
    return {"updated": True, "slug": slug}


def get_contact(vault: Path, config: NatalieConfig, slug: str) -> dict[str, Any] | None:
    """Return contact metadata dict (plus 'content' body if present), or None if not found."""
    path = _contact_path(vault, config, slug)
    if not path.exists():
        return None
    post = fm.loads(path.read_text(encoding="utf-8"))
    result = dict(post.metadata)
    if post.content is not None:
        result["content"] = post.content
    return result


def list_contacts(vault: Path, config: NatalieConfig) -> list[str]:
    """Return slugs of all contact cards, sorted."""
    contacts_dir = _contacts_dir(vault, config)
    if not contacts_dir.exists():
        return []
    return sorted(p.stem for p in contacts_dir.glob("*.md"))
