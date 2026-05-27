import pytest
from pathlib import Path
from natalie.generate import load_persona, render_instructions
from natalie.config import NatalieConfig, PersonaConfig


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
    cfg = NatalieConfig(vault=vault, skills=SkillsConfig(preferred=["superpowers"]))
    output = render_instructions(cfg, vault, target="claude")
    assert "superpowers" in output


def test_render_instructions_includes_denied_mcps(vault):
    from natalie.config import McpsConfig
    cfg = NatalieConfig(vault=vault, mcps=McpsConfig(denied=["bad-mcp"]))
    output = render_instructions(cfg, vault, target="claude")
    assert "bad-mcp" in output
