from pathlib import Path

import natalie


def test_contact_enrichment_skill_exists():
    skills_dir = Path(natalie.__file__).parent / "skills"
    skill = skills_dir / "natalie-contact-enrichment" / "SKILL.md"
    assert skill.exists(), f"SKILL.md not found at {skill}"


def test_contact_enrichment_skill_has_required_sections():
    skill = Path(natalie.__file__).parent / "skills" / "natalie-contact-enrichment" / "SKILL.md"
    content = skill.read_text(encoding="utf-8")
    for section in ["auto", "contact_list", "contact_get", "contact_update"]:
        assert section in content, f"SKILL.md missing reference to '{section}'"
