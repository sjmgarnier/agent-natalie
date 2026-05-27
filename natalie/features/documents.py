from __future__ import annotations

from pathlib import Path

from ..config import NatalieConfig


def _doc_dir(vault: Path, config: NatalieConfig) -> Path:
    return vault / config.documents.directory


def file_document(vault: Path, config: NatalieConfig, filename: str, content: str) -> dict:
    """Save content as a document in the documents directory."""
    doc_dir = _doc_dir(vault, config)
    doc_dir.mkdir(parents=True, exist_ok=True)
    (doc_dir / filename).write_text(content, encoding="utf-8")
    return {"filed": True, "path": f"{config.documents.directory}/{filename}"}


def retrieve_document(vault: Path, config: NatalieConfig, filename: str) -> str | None:
    """Return document content, or None if not found."""
    path = _doc_dir(vault, config) / filename
    return path.read_text(encoding="utf-8") if path.exists() else None


def list_documents(vault: Path, config: NatalieConfig) -> list[str]:
    """Return filenames in the documents directory, sorted."""
    doc_dir = _doc_dir(vault, config)
    if not doc_dir.exists():
        return []
    return sorted(p.name for p in doc_dir.iterdir() if p.is_file())
