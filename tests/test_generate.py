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


def test_render_instructions_includes_tasks_note(vault):
    from natalie.config import TasksConfig

    cfg = NatalieConfig(tasks=TasksConfig(note="Natalie/MyTasks.md"))
    output = render_instructions(cfg, vault, target="claude")
    assert "Natalie/MyTasks.md" in output


def test_render_instructions_agents_includes_tasks_note(vault):
    from natalie.config import TasksConfig

    cfg = NatalieConfig(tasks=TasksConfig(note="Natalie/MyTasks.md"))
    output = render_instructions(cfg, vault, target="agents")
    assert "Natalie/MyTasks.md" in output


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


def test_render_instructions_contains_onboarding_section(vault, config):
    output = render_instructions(config, vault, target="claude")
    assert "## Onboarding" in output
    assert "onboarding_status" in output
    assert "onboarding_complete" in output


def test_render_instructions_agents_contains_onboarding_section(vault, config):
    output = render_instructions(config, vault, target="agents")
    assert "## Onboarding" in output
    assert "onboarding_status" in output
    assert "onboarding_complete" in output


def test_render_instructions_contains_tool_disambiguation(vault, config):
    output = render_instructions(config, vault, target="claude")
    assert "## Tool Disambiguation" in output
    assert "note_read" in output
    assert "note_write" in output
    assert "memory_store" in output
    assert "memory_search" in output
    assert "task_list" in output
    assert "document_file" in output
    assert "contact_search" in output
    assert "onboarding_complete" in output
    assert "watcher_status" in output


def test_render_instructions_agents_contains_tool_disambiguation(vault, config):
    output = render_instructions(config, vault, target="agents")
    assert "## Tool Disambiguation" in output
    assert "note_read" in output
    assert "note_write" in output
    assert "memory_store" in output
    assert "memory_search" in output
    assert "task_list" in output
    assert "document_file" in output
    assert "contact_search" in output
    assert "onboarding_complete" in output
    assert "watcher_status" in output


def test_render_instructions_supplements_delegation_import(vault, config):
    claude = render_instructions(config, vault, target="claude")
    agents = render_instructions(config, vault, target="agents")
    assert "@.claude/skills/natalie-delegate/SKILL.md" in claude
    assert "@./.agents/skills/natalie-delegate/SKILL.md" in agents
    guidance = "Before delegating work, load and follow the `natalie-delegate` skill."
    assert guidance in claude
    assert guidance in agents


def test_instruction_templates_differ_only_by_import_paths():
    from pathlib import Path

    templates = Path(__file__).parents[1] / "natalie" / "templates"
    claude = (templates / "claude.md.jinja").read_text(encoding="utf-8")
    agents = (templates / "agents.md.jinja").read_text(encoding="utf-8")
    normalized = agents.replace("@./.agents/skills/", "@.claude/skills/")
    assert normalized == claude


def test_render_instructions_contains_tool_priority_section(vault, config):
    for target in ("claude", "agents"):
        output = render_instructions(config, vault, target=target)
        assert "## Tool Priority" in output, f"Missing Tool Priority section in {target} template"


def test_render_instructions_tool_priority_before_onboarding(vault, config):
    for target in ("claude", "agents"):
        output = render_instructions(config, vault, target=target)
        priority_pos = output.index("## Tool Priority")
        onboarding_pos = output.index("## Onboarding")
        assert priority_pos < onboarding_pos, f"Tool Priority must precede Onboarding in {target} template"


def test_render_instructions_memory_contains_routing(vault, config):
    for target in ("claude", "agents"):
        output = render_instructions(config, vault, target=target)
        memory_start = output.index("## Memory")
        conventions_start = output.index("## Conventions")
        memory_section = output[memory_start:conventions_start]
        assert "hidden internal store" in memory_section, (
            f"No routing guidance in Memory section for {target}"
        )


def test_render_instructions_tasks_contains_routing(vault, config):
    for target in ("claude", "agents"):
        output = render_instructions(config, vault, target=target)
        tasks_start = output.index("## Tasks")
        system_start = output.index("## System Health")
        tasks_section = output[tasks_start:system_start]
        assert "task_capture" in tasks_section, f"No routing guidance in Tasks section for {target}"


def test_render_instructions_tool_disambiguation_contains_note_routing(vault, config):
    for target in ("claude", "agents"):
        output = render_instructions(config, vault, target=target)
        disambig_start = output.index("## Tool Disambiguation")
        disambig_section = output[disambig_start:]
        assert "note_write" in disambig_section, (
            f"Tool Disambiguation missing note_write routing for {target}"
        )


def test_render_instructions_documents_contacts_contains_routing(vault, config):
    for target in ("claude", "agents"):
        output = render_instructions(config, vault, target=target)
        docs_start = output.index("## Documents and Contacts")
        tool_disambig_start = output.index("## Tool Disambiguation")
        docs_section = output[docs_start:tool_disambig_start]
        assert "contact_get" in docs_section, (
            f"No routing guidance in Documents and Contacts section for {target}"
        )


def test_render_instructions_tool_priority_text(vault, config):
    for target in ("claude", "agents"):
        output = render_instructions(config, vault, target=target)
        assert "built-in tools" in output, f"Tool Priority missing 'built-in tools' in {target}"
        assert "genuinely ambiguous" in output, f"Tool Priority missing 'genuinely ambiguous' in {target}"


def test_render_instructions_tool_disambiguation_covers_note_tools(vault, config):
    for target in ("claude", "agents"):
        output = render_instructions(config, vault, target=target)
        disambig_start = output.index("## Tool Disambiguation")
        disambig_section = output[disambig_start:]
        for tool in ("note_write", "note_read", "note_list"):
            assert tool in disambig_section, f"Tool Disambiguation missing {tool} in {target}"
