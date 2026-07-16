"""Task 13.1 — verify all four agent definition files ship with the package."""

from pathlib import Path

import natalie


def _agents_dir() -> Path:
    return Path(natalie.__file__).parent / "agents"


def test_claude_agent_definition_exists() -> None:
    assert (_agents_dir() / "claude" / "natalie-assistant.md").exists()


def test_opencode_agent_definition_exists() -> None:
    assert (_agents_dir() / "opencode" / "natalie-assistant.json").exists()


def test_vibe_agent_toml_exists() -> None:
    assert (_agents_dir() / "vibe" / "natalie-assistant.toml").exists()


def test_vibe_agent_prompt_exists() -> None:
    assert (_agents_dir() / "vibe" / "natalie-assistant.md").exists()


def test_goose_recipe_exists() -> None:
    assert (_agents_dir() / "goose" / "natalie-assistant.yaml").exists()


def test_codex_agent_exists_and_is_valid_toml() -> None:
    import tomllib

    path = _agents_dir() / "codex" / "natalie-assistant.toml"
    assert path.exists()
    with open(path, "rb") as f:
        data = tomllib.load(f)
    assert set(data) == {"name", "description", "developer_instructions"}
    assert data["name"] == "natalie-assistant"


def test_claude_agent_has_required_frontmatter() -> None:
    content = (_agents_dir() / "claude" / "natalie-assistant.md").read_text(encoding="utf-8")
    assert "name: natalie-assistant" in content
    assert "description:" in content
    assert "skills:" in content
    assert "model:" in content


def test_opencode_agent_definition_is_valid_json() -> None:
    import json

    path = _agents_dir() / "opencode" / "natalie-assistant.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    agent = data["agent"]["natalie-assistant"]
    assert agent["mode"] == "subagent"
    assert agent["hidden"] is True
    assert "prompt" in agent
    assert agent.get("permission", {}).get("natalie_*") == "allow"


def test_vibe_agent_toml_has_required_fields() -> None:
    import tomllib

    with open(_agents_dir() / "vibe" / "natalie-assistant.toml", "rb") as f:
        data = tomllib.load(f)
    assert data["agent_type"] == "subagent"
    assert "display_name" in data
    assert "description" in data
    assert data["safety"] == "safe"
    assert "system_prompt_id" in data
    assert "enabled_tools" in data


def test_goose_recipe_has_required_fields() -> None:
    from ruamel.yaml import YAML

    yaml = YAML()
    with open(_agents_dir() / "goose" / "natalie-assistant.yaml") as f:
        data = yaml.load(f)
    for field in ("id", "version", "title", "description", "instructions", "extensions"):
        assert field in data, f"Goose recipe missing field: {field}"
    assert "natalie" in data["extensions"]
