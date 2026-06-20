from pathlib import Path

import pytest
from typer.testing import CliRunner

import natalie
from natalie.cli import app

runner = CliRunner()


def _parse_frontmatter(content: str) -> dict:  # type: ignore[type-arg]
    """Extract YAML frontmatter fields (name, description) from a SKILL.md."""
    import re

    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}
    result = {}
    for line in match.group(1).splitlines():
        if ": " in line and not line.startswith(" "):
            key, _, val = line.partition(": ")
            result[key.strip()] = val.strip()
    return result


def test_contact_enrichment_skill_exists():
    skills_dir = Path(natalie.__file__).parent / "skills"
    skill = skills_dir / "natalie-contact-enrichment" / "SKILL.md"
    assert skill.exists(), f"SKILL.md not found at {skill}"


def test_contact_enrichment_skill_has_required_sections():
    skill = Path(natalie.__file__).parent / "skills" / "natalie-contact-enrichment" / "SKILL.md"
    content = skill.read_text(encoding="utf-8")
    for section in ["auto", "contact_list", "contact_get", "contact_update"]:
        assert section in content, f"SKILL.md missing reference to '{section}'"


# Task 13.7 — natalie-delegate agentskills.io compliance


def test_natalie_delegate_skill_exists():
    skill = Path(natalie.__file__).parent / "skills" / "natalie-delegate" / "SKILL.md"
    assert skill.exists(), f"SKILL.md not found at {skill}"


def test_natalie_delegate_has_valid_frontmatter():
    content = (Path(natalie.__file__).parent / "skills" / "natalie-delegate" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    fm = _parse_frontmatter(content)
    assert fm.get("name") == "natalie-delegate", "frontmatter must have name: natalie-delegate"
    assert "description" in fm, "frontmatter must have a description field"


def test_natalie_delegate_no_disallowed_frontmatter_fields():
    """Agentskills.io: only name, description, license, compatibility, metadata, allowed-tools are valid."""
    import re

    content = (Path(natalie.__file__).parent / "skills" / "natalie-delegate" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    assert match, "SKILL.md must have YAML frontmatter"
    allowed = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
    for line in match.group(1).splitlines():
        if ": " in line and not line.startswith(" "):
            key = line.split(":")[0].strip()
            assert key in allowed, f"Disallowed frontmatter field: {key!r}"


# Task 13.8 — natalie init installs natalie-delegate


def test_init_installs_natalie_delegate_to_agents_skills(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    runner.invoke(app, ["init", str(vault)], input="y\n")
    skill = vault / ".agents" / "skills" / "natalie-delegate" / "SKILL.md"
    assert skill.exists()


def test_init_creates_claude_symlink_for_natalie_delegate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    runner.invoke(app, ["init", str(vault)], input="y\n")
    link = vault / ".claude" / "skills" / "natalie-delegate"
    assert link.is_symlink() or link.is_dir(), ".claude/skills/natalie-delegate must exist"
