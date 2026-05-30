import pytest

from natalie.features.documents import file_document, list_documents, retrieve_document


def test_file_document_creates_file(vault, config):
    result = file_document(vault, config, "meeting-notes.md", "# Meeting\n\nNotes here.")
    assert result["filed"] is True
    expected = vault / config.documents.directory / "meeting-notes.md"
    assert expected.exists()
    assert "Notes here" in expected.read_text()


def test_file_document_overwrites_existing(vault, config):
    file_document(vault, config, "doc.md", "v1 content")
    file_document(vault, config, "doc.md", "v2 content")
    content = (vault / config.documents.directory / "doc.md").read_text()
    assert "v2 content" in content
    assert "v1 content" not in content


def test_retrieve_document_returns_content(vault, config):
    file_document(vault, config, "my-doc.md", "Document body.")
    content = retrieve_document(vault, config, "my-doc.md")
    assert "Document body" in content


def test_retrieve_document_returns_none_if_missing(vault, config):
    assert retrieve_document(vault, config, "nonexistent.md") is None


def test_list_documents_returns_filenames(vault, config):
    file_document(vault, config, "alpha.md", "Alpha")
    file_document(vault, config, "beta.md", "Beta")
    docs = list_documents(vault, config)
    assert "alpha.md" in docs
    assert "beta.md" in docs


def test_file_document_rejects_traversal_in_directory(vault, config):
    """A config.documents.directory that escapes the vault must raise ValueError."""
    from natalie.config import DocumentsConfig, NatalieConfig

    bad_config = NatalieConfig(documents=DocumentsConfig(directory="../../etc"))
    with pytest.raises(ValueError):
        file_document(vault, bad_config, "passwd", "root:x:0:0")
