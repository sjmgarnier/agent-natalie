import dataclasses
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SUPPORTED_CLIENTS: tuple[str, ...] = ("claude", "opencode", "vibe", "goose", "codex")
LEGACY_CLIENTS: tuple[str, ...] = ("claude", "opencode", "vibe", "goose")


def _filter(cls: type[Any], data: dict[str, Any]) -> dict[str, Any]:
    known = {f.name for f in dataclasses.fields(cls)}
    return {k: v for k, v in data.items() if k in known}


@dataclass
class PersonaConfig:
    name: str = "natalie"


DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"


@dataclass
class MemoryConfig:
    embedding_model: str = DEFAULT_EMBEDDING_MODEL


@dataclass
class SkillsConfig:
    preferred: list[str] = field(default_factory=list)
    denied: list[str] = field(default_factory=list)


@dataclass
class McpsConfig:
    preferred: list[str] = field(default_factory=list)
    denied: list[str] = field(default_factory=list)


@dataclass
class DocumentsConfig:
    directory: str = "Natalie/Documents"


@dataclass
class ContactsConfig:
    directory: str = "Natalie/Contacts"


@dataclass
class TasksConfig:
    note: str = "Tasks.md"


@dataclass
class ClientsConfig:
    # None distinguishes an older vault with no persisted selection from a
    # deliberately stored enabled-client list.
    enabled: list[str] | None = None


@dataclass
class NatalieConfig:
    persona: PersonaConfig = field(default_factory=PersonaConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    skills: SkillsConfig = field(default_factory=SkillsConfig)
    mcps: McpsConfig = field(default_factory=McpsConfig)
    documents: DocumentsConfig = field(default_factory=DocumentsConfig)
    contacts: ContactsConfig = field(default_factory=ContactsConfig)
    tasks: TasksConfig = field(default_factory=TasksConfig)
    clients: ClientsConfig = field(default_factory=ClientsConfig)


def load_config(vault: Path) -> NatalieConfig:
    cfg = NatalieConfig()
    config_path = vault / "Natalie" / "config.toml"
    if not config_path.exists():
        return cfg
    with open(config_path, "rb") as f:
        data = tomllib.load(f)
    if "persona" in data:
        cfg.persona = PersonaConfig(**_filter(PersonaConfig, data["persona"]))
    if "memory" in data:
        cfg.memory = MemoryConfig(**_filter(MemoryConfig, data["memory"]))
    if "skills" in data:
        cfg.skills = SkillsConfig(**_filter(SkillsConfig, data["skills"]))
    if "mcps" in data:
        cfg.mcps = McpsConfig(**_filter(McpsConfig, data["mcps"]))
    if "clients" in data:
        cfg.clients = ClientsConfig(**_filter(ClientsConfig, data["clients"]))
    if "features" in data:
        feats = data["features"]
        if "documents" in feats:
            cfg.documents = DocumentsConfig(**_filter(DocumentsConfig, feats["documents"]))
        if "contacts" in feats:
            cfg.contacts = ContactsConfig(**_filter(ContactsConfig, feats["contacts"]))
        if "tasks" in feats:
            cfg.tasks = TasksConfig(**_filter(TasksConfig, feats["tasks"]))
    return cfg
