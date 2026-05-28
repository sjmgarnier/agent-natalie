from pathlib import Path


def write_note(vault: Path, rel: str, content: str) -> Path:
    """Write a markdown file inside a test vault, creating parent dirs as needed."""
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p
