from pathlib import Path


def find_vault(start: Path | None = None) -> Path | None:
    current = (start or Path.cwd()).resolve()
    for directory in [current, *current.parents]:
        if (directory / ".natalie" / "natalie.db").exists():
            return directory
    return None


def require_vault(start: Path | None = None) -> Path:
    vault = find_vault(start)
    if vault is None:
        raise RuntimeError(
            "No Natalie vault found. Run 'natalie init <vault-path>' to set one up."
        )
    return vault
