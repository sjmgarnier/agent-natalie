from __future__ import annotations

from pathlib import Path

import frontmatter as fm
from jinja2 import Environment, FileSystemLoader

from .config import NatalieConfig
from .utils import safe_join

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_PERSONAS_DIR = Path(__file__).parent / "personas"


def load_persona(name: str, vault: Path | None = None) -> fm.Post:
    if vault:
        custom = safe_join(vault / "Natalie" / "personas", f"{name}.md")
        if custom.exists():
            return fm.loads(custom.read_text(encoding="utf-8"))
    preset = safe_join(_PERSONAS_DIR, f"{name}.md")
    if preset.exists():
        return fm.loads(preset.read_text(encoding="utf-8"))
    raise ValueError(f"Persona '{name}' not found")


def render_instructions(
    config: NatalieConfig,
    vault: Path,
    target: str = "claude",
) -> str:
    persona = load_persona(config.persona.name, vault=vault)
    env = Environment(loader=FileSystemLoader(str(_TEMPLATES_DIR)), keep_trailing_newline=True)
    template = env.get_template(f"{target}.md.jinja")
    return template.render(
        persona_content=persona.content.strip(),
        persona_name=persona.metadata.get("name", ""),
        preferred_skills=config.skills.preferred,
        denied_skills=config.skills.denied,
        preferred_mcps=config.mcps.preferred,
        denied_mcps=config.mcps.denied,
    )
