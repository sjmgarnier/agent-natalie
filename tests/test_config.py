from natalie.config import load_config


def test_load_config_returns_defaults_when_no_file(vault):
    cfg = load_config(vault)
    assert cfg.persona.name == "natalie"
    assert cfg.memory.embedding_model == "BAAI/bge-small-en-v1.5"
    assert cfg.skills.preferred == []
    assert cfg.skills.denied == []
    assert cfg.documents.directory == "Natalie/Documents"
    assert cfg.contacts.directory == "Natalie/Contacts"


def test_load_config_reads_persona_name(vault):
    config_path = vault / "Natalie" / "config.toml"
    config_path.write_text('[persona]\nname = "donna"\n')
    cfg = load_config(vault)
    assert cfg.persona.name == "donna"


def test_load_config_reads_skills(vault):
    config_path = vault / "Natalie" / "config.toml"
    config_path.write_text('[skills]\npreferred = ["superpowers", "r-lib"]\ndenied = ["deprecated-skill"]\n')
    cfg = load_config(vault)
    assert cfg.skills.preferred == ["superpowers", "r-lib"]
    assert cfg.skills.denied == ["deprecated-skill"]


def test_load_config_reads_features(vault):
    config_path = vault / "Natalie" / "config.toml"
    config_path.write_text(
        '[features.documents]\ndirectory = "Notes/Docs"\n[features.contacts]\ndirectory = "Notes/People"\n'
    )
    cfg = load_config(vault)
    assert cfg.documents.directory == "Notes/Docs"
    assert cfg.contacts.directory == "Notes/People"


def test_load_config_ignores_unknown_keys(vault):
    config_path = vault / "Natalie" / "config.toml"
    config_path.write_text('[persona]\nname = "donna"\nunknown_key = "ignored"\n')
    cfg = load_config(vault)
    assert cfg.persona.name == "donna"  # must not raise TypeError
