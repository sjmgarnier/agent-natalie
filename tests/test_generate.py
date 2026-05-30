import pytest

from natalie.config import NatalieConfig
from natalie.generate import load_persona, render_instructions


def test_load_persona_returns_preset(tmp_path):
    persona = load_persona("natalie")
    assert persona.metadata.get("name") == "Natalie Teeger"
    assert len(persona.content) > 0


def test_load_persona_raises_for_unknown(tmp_path):
    with pytest.raises(ValueError, match="Persona 'nobody' not found"):
        load_persona("nobody")


def test_load_persona_prefers_vault_custom(vault):
    custom = vault / "Natalie" / "personas" / "natalie.md"
    custom.write_text("---\nname: Custom Natalie\n---\nCustom content.\n")
    persona = load_persona("natalie", vault=vault)
    assert persona.metadata["name"] == "Custom Natalie"


def test_render_instructions_contains_persona_markers(vault, config):
    output = render_instructions(config, vault, target="claude")
    assert "<!-- agent-natalie:persona:start -->" in output
    assert "<!-- agent-natalie:persona:end -->" in output


def test_render_instructions_contains_persona_content(vault, config):
    output = render_instructions(config, vault, target="claude")
    assert "Natalie Teeger" in output


def test_render_instructions_agents_target(vault, config):
    output = render_instructions(config, vault, target="agents")
    assert "<!-- agent-natalie:persona:start -->" in output


def test_render_instructions_includes_preferred_skills(vault):
    from natalie.config import SkillsConfig

    cfg = NatalieConfig(skills=SkillsConfig(preferred=["superpowers"]))
    output = render_instructions(cfg, vault, target="claude")
    assert "superpowers" in output


def test_render_instructions_includes_denied_mcps(vault):
    from natalie.config import McpsConfig

    cfg = NatalieConfig(mcps=McpsConfig(denied=["bad-mcp"]))
    output = render_instructions(cfg, vault, target="claude")
    assert "bad-mcp" in output


def test_load_persona_rejects_path_traversal_vault(vault):
    """Persona name with path traversal must raise ValueError, not read arbitrary files."""
    with pytest.raises(ValueError):
        load_persona("../../etc/passwd", vault=vault)


def test_load_persona_rejects_path_traversal_preset():
    """Path traversal must be rejected even when no vault is provided."""
    with pytest.raises(ValueError):
        load_persona("../../etc/passwd")


def test_render_instructions_uses_persona_name_in_header(vault, config):
    """The file header must use the persona metadata name, not a hardcoded string — I3."""
    output = render_instructions(config, vault, target="claude")
    header_section = output.split("<!-- agent-natalie:persona:start -->")[0]
    assert "Natalie Teeger" in header_section
