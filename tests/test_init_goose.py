from pathlib import Path

from ruamel.yaml import YAML

from natalie.cli import _merge_yaml


def _load_yaml(path: Path) -> dict:  # type: ignore[type-arg]
    yaml = YAML()
    with open(path) as f:
        return yaml.load(f) or {}  # type: ignore[return-value]


def test_merge_yaml_creates_file(tmp_path: Path) -> None:
    target = tmp_path / "config.yaml"
    _merge_yaml(target, {"extensions": {"natalie": {"enabled": True}}})
    assert target.exists()
    data = _load_yaml(target)
    assert data["extensions"]["natalie"]["enabled"] is True


def test_merge_yaml_merges_into_existing(tmp_path: Path) -> None:
    target = tmp_path / "config.yaml"
    yaml = YAML()
    with open(target, "w") as f:
        yaml.dump({"GOOSE_PROVIDER": "anthropic", "extensions": {"developer": {"enabled": True}}}, f)
    _merge_yaml(target, {"extensions": {"natalie": {"enabled": True}}})
    data = _load_yaml(target)
    assert data["GOOSE_PROVIDER"] == "anthropic"
    assert data["extensions"]["developer"]["enabled"] is True
    assert data["extensions"]["natalie"]["enabled"] is True


def test_merge_yaml_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "config.yaml"
    update = {"extensions": {"natalie": {"enabled": True, "cmd": "/bin/natalie-server"}}}
    _merge_yaml(target, update)
    _merge_yaml(target, update)
    data = _load_yaml(target)
    assert isinstance(data["extensions"]["natalie"], dict)
    assert data["extensions"]["natalie"]["cmd"] == "/bin/natalie-server"


def test_merge_yaml_updates_existing_extension(tmp_path: Path) -> None:
    target = tmp_path / "config.yaml"
    yaml = YAML()
    with open(target, "w") as f:
        yaml.dump({"extensions": {"natalie": {"enabled": False, "cmd": "/old/path"}}}, f)
    _merge_yaml(target, {"extensions": {"natalie": {"enabled": True, "cmd": "/new/path"}}})
    data = _load_yaml(target)
    assert data["extensions"]["natalie"]["enabled"] is True
    assert data["extensions"]["natalie"]["cmd"] == "/new/path"


def test_merge_yaml_creates_parent_dirs(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "config.yaml"
    _merge_yaml(target, {"key": "value"})
    assert target.exists()
    data = _load_yaml(target)
    assert data["key"] == "value"


def test_merge_yaml_handles_corrupt_file(tmp_path: Path) -> None:
    target = tmp_path / "config.yaml"
    target.write_text("{{invalid: yaml: [}", encoding="utf-8")
    _merge_yaml(target, {"extensions": {"natalie": {"enabled": True}}})
    data = _load_yaml(target)
    assert data["extensions"]["natalie"]["enabled"] is True
