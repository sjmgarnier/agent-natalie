import subprocess
from pathlib import Path

import pytest

INSTALL_SCRIPT = Path(__file__).parents[1] / "install.sh"

# macOS ships /bin/bash pinned at 3.2.57 (GPLv3 licensing), where `"${arr[@]}"`
# on an empty array is an unbound-variable error under `set -u`. A PATH `bash`
# (e.g. Homebrew's) is typically >=4.4 and won't reproduce the bug, so this
# check must target the system binary directly to be meaningful.
_MACOS_SYSTEM_BASH = Path("/bin/bash")


def test_install_script_has_valid_bash_syntax() -> None:
    result = subprocess.run(["bash", "-n", str(INSTALL_SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_install_script_collects_all_supported_clients() -> None:
    content = INSTALL_SCRIPT.read_text(encoding="utf-8")
    for client in ("claude", "opencode", "vibe", "goose", "codex"):
        assert client in content
    assert 'CLIENT_ARGS+=(--client "$_CLIENT")' in content


def test_install_script_keeps_upgrade_selection_when_input_is_blank() -> None:
    content = INSTALL_SCRIPT.read_text(encoding="utf-8")
    assert "blank keeps the vault's current selection" in content
    assert '"${CLIENT_ARGS[@]}"' in content


def test_install_script_fresh_default_excludes_codex() -> None:
    content = INSTALL_SCRIPT.read_text(encoding="utf-8")
    assert "default: claude,opencode,vibe,goose" in content
    assert 'CLIENT_INPUT="${CLIENT_INPUT:-claude,opencode,vibe,goose}"' in content


@pytest.mark.skipif(not _MACOS_SYSTEM_BASH.exists(), reason="/bin/bash (macOS system bash) not present")
def test_install_script_blank_client_selection_survives_macos_default_bash() -> None:
    """Regression test: an upgrade with a blank client prompt (the documented
    "keep current selection" flow) must not crash on macOS's stock /bin/bash.
    """
    content = INSTALL_SCRIPT.read_text(encoding="utf-8")
    start = content.index("# ── Prompt for agent clients")
    end = content.index("# ── Confirm")
    prompt_block = content[start:end]
    init_line_start = content.index('"$NATALIE" init')
    init_line = content[init_line_start : content.index("\n", init_line_start)]

    harness = f"""
set -euo pipefail
IS_UPGRADE=true
NATALIE=echo
VAULT_PATH=/tmp/vault
PERSONA=natalie
VENV_DIR=/tmp/venv
{prompt_block}
{init_line}
"""
    result = subprocess.run(
        [str(_MACOS_SYSTEM_BASH), "-c", harness],
        input="\n",
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "unbound variable" not in result.stderr
