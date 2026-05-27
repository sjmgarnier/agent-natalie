from unittest.mock import patch
from pathlib import Path

from typer.testing import CliRunner
from natalie.cli import app

runner = CliRunner()


def test_version_flag():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "natalie" in result.output.lower()


def test_config_persona_writes_claude_md(vault):
    with patch("natalie.cli.require_vault", return_value=vault), \
         patch("natalie.cli.load_config") as mock_cfg:
        from natalie.config import NatalieConfig, PersonaConfig
        mock_cfg.return_value = NatalieConfig(vault=vault, persona=PersonaConfig(name="natalie"))
        result = runner.invoke(app, ["config", "--persona", "natalie"])
    assert result.exit_code == 0
    assert (vault / "CLAUDE.md").exists()
    assert (vault / "AGENTS.md").exists()


def test_config_persona_writes_persona_markers(vault):
    with patch("natalie.cli.require_vault", return_value=vault), \
         patch("natalie.cli.load_config") as mock_cfg:
        from natalie.config import NatalieConfig, PersonaConfig
        mock_cfg.return_value = NatalieConfig(vault=vault, persona=PersonaConfig(name="natalie"))
        runner.invoke(app, ["config", "--persona", "natalie"])
    content = (vault / "CLAUDE.md").read_text()
    assert "<!-- agent-natalie:persona:start -->" in content
    assert "<!-- agent-natalie:persona:end -->" in content
