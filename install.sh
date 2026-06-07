#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$HOME/.natalie/.venv"
NATALIE="$VENV_DIR/bin/natalie"

# ── uv ────────────────────────────────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    [ -f "$HOME/.local/bin/env" ] && source "$HOME/.local/bin/env"
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi

# ── Skill installer ───────────────────────────────────────────────────────────
_install_skills() {
    local vault_path="$1"
    local skills_src
    skills_src="$("$VENV_DIR/bin/python" -c \
        "import natalie, pathlib; print(pathlib.Path(natalie.__file__).parent / 'skills')")"
    if [[ ! -d "$skills_src" ]]; then
        echo "  No skills directory found in package; skipping."
        return
    fi
    mkdir -p "$vault_path/.claude/skills"
    mkdir -p "$vault_path/.opencode/skills"
    for skill_dir in "$skills_src"/*/; do
        [[ -d "$skill_dir" ]] || continue
        local skill_name="$(basename "$skill_dir")"
        cp -r "$skill_dir" "$vault_path/.claude/skills/$skill_name"
        cp -r "$skill_dir" "$vault_path/.opencode/skills/$skill_name"
        echo "  Installed: $skill_name"
    done
}

# ── Install or upgrade agent-natalie ─────────────────────────────────────────
IS_UPGRADE=false
if [[ -d "$VENV_DIR" ]]; then
    IS_UPGRADE=true
    echo "Upgrading agent-natalie..."
    uv pip install --python "$VENV_DIR" --upgrade agent-natalie
else
    echo "Creating Python environment at $VENV_DIR..."
    mkdir -p "$HOME/.natalie"
    uv venv "$VENV_DIR"
    uv pip install --python "$VENV_DIR" agent-natalie

    # Add natalie to PATH (fresh install only)
    mkdir -p "$HOME/.local/bin"
    ln -sf "$VENV_DIR/bin/natalie" "$HOME/.local/bin/natalie"
    for _RC in "$HOME/.zshrc" "$HOME/.bashrc"; do
        if [[ -f "$_RC" ]] && ! grep -q '\.local/bin' "$_RC"; then
            echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$_RC"
            echo "Added ~/.local/bin to PATH in $_RC"
        fi
    done
    export PATH="$HOME/.local/bin:$PATH"
fi

# Refresh symlink in case the binary path changed
mkdir -p "$HOME/.local/bin"
ln -sf "$VENV_DIR/bin/natalie" "$HOME/.local/bin/natalie"

# ── Prompt for vault path ─────────────────────────────────────────────────────
echo ""
read -ep "Vault path (default: $HOME/Natalie): " VAULT_PATH
VAULT_PATH="${VAULT_PATH:-$HOME/Natalie}"
VAULT_PATH="${VAULT_PATH/#\~/$HOME}"
VAULT_PATH="${VAULT_PATH//\\/}"
VAULT_PATH="$(cd "$VAULT_PATH" 2>/dev/null && pwd || echo "$VAULT_PATH")"

# ── Prompt for persona (fresh install only) ───────────────────────────────────
PERSONA="natalie"
if [[ "$IS_UPGRADE" == false ]]; then
    echo ""
    echo "Available personas: natalie, donna, moneypenny, smithers, april, finch, gary, pam"
    read -rp "Persona (default: natalie): " PERSONA
    PERSONA="${PERSONA:-natalie}"
fi

# ── Confirm ───────────────────────────────────────────────────────────────────
echo ""
echo "natalie will configure the following in: $VAULT_PATH"
echo "  .mcp.json, .claude/settings.json       (Claude Code)"
echo "  opencode.json, .opencode/hooks.json    (OpenCode)"
echo "  .vibe/config.toml, .vibe/hooks.toml    (Mistral Vibe)"
if [[ "$IS_UPGRADE" == false ]]; then
    echo "  Dashboard.md, CLAUDE.md, AGENTS.md     (created if absent)"
    echo "  .obsidian/snippets/                    (3 CSS files, created if absent)"
fi
echo "  All writes are idempotent — existing content is preserved."
echo ""
read -rp "Proceed? [Y/n] " _PROCEED
_PROCEED="${_PROCEED:-Y}"
if [[ ! "$_PROCEED" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

# ── Initialize vault ──────────────────────────────────────────────────────────
echo ""
echo "Configuring vault at $VAULT_PATH..."
"$NATALIE" init "$VAULT_PATH" --persona "$PERSONA" --venv-path "$VENV_DIR"

# On upgrade, regen CLAUDE.md / AGENTS.md to pick up updated persona templates
if [[ "$IS_UPGRADE" == true ]]; then
    echo ""
    (cd "$VAULT_PATH" && "$NATALIE" config --regen)
    echo "CLAUDE.md and AGENTS.md updated with the latest tool instructions."
fi

# ── Install companion skills ──────────────────────────────────────────────────
echo ""
read -rp "Install/update companion Claude Code skills into this vault? [Y/n] " _INSTALL_SKILLS
_INSTALL_SKILLS="${_INSTALL_SKILLS:-Y}"
if [[ "$_INSTALL_SKILLS" =~ ^[Yy]$ ]]; then
    echo ""
    _install_skills "$VAULT_PATH"
fi

# ── Build / refresh search index ─────────────────────────────────────────────
echo ""
if [[ "$IS_UPGRADE" == true ]]; then
    echo "Refreshing search index..."
    if ! (cd "$VAULT_PATH" && "$NATALIE" sync); then
        echo ""
        echo "WARNING: Search index refresh failed. Run 'natalie sync' from the vault directory when ready."
    fi
else
    echo "Building initial search index..."
    echo "On first run this downloads the embedding model (~130 MB)."
    echo "A progress bar will appear below — this may take several minutes on slow connections."
    echo ""
    if ! (cd "$VAULT_PATH" && "$NATALIE" sync --full); then
        echo ""
        echo "WARNING: Search index build failed (network or model download issue)."
        echo "   Your vault was still created at $VAULT_PATH."
        echo "   Run 'natalie sync --full' from the vault directory when ready."
    fi
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [[ "$IS_UPGRADE" == true ]]; then
    echo "  Done! agent-natalie upgraded and vault reconfigured."
    echo ""
    echo "  Start your agent from inside the vault:"
    echo "       cd '$VAULT_PATH' && claude     # Claude Code"
    echo "       cd '$VAULT_PATH' && opencode   # OpenCode"
    echo "       cd '$VAULT_PATH' && vibe       # Mistral Vibe"
    echo ""
    echo "  To configure additional vaults: run 'natalie init <path>' directly."
else
    echo "  Done! Here's what to do next:"
    echo ""
    echo "  1. Open Obsidian and add '$VAULT_PATH' as a vault."
    echo "     The Dashboard layout and CSS snippets are pre-configured."
    echo "     If the multi-column layout doesn't appear, go to:"
    echo "       Settings → Appearance → CSS snippets"
    echo "     and make sure natalie-dashboard, MCL Multi Column, and MCL Wide Views"
    echo "     are toggled on. If they aren't listed, click the folder icon to refresh."
    echo ""
    echo "  2. Install the Dataview community plugin (required for the Dashboard):"
    echo "       Settings → Community Plugins → Browse"
    echo "       Search 'Dataview' → Install → Enable"
    echo "     Then open Dataview settings and enable 'Enable JavaScript Queries'"
    echo "     and 'Enable Inline JavaScript Queries'."
    echo ""
    echo "  3. Install the Tasks community plugin (recommended for task management):"
    echo "       Settings → Community Plugins → Browse"
    echo "       Search 'Tasks' → Install → Enable"
    echo "     No additional configuration needed."
    echo ""
    echo "  4. Start your agent from inside the vault:"
    echo "       cd '$VAULT_PATH' && claude     # Claude Code"
    echo "       cd '$VAULT_PATH' && opencode   # OpenCode"
    echo "       cd '$VAULT_PATH' && vibe       # Mistral Vibe"
    echo "     Both read their config files and connect to natalie-server automatically."
    echo "     The natalie tools (memory_search, note_write, task_list, …) will appear"
    echo "     in the tool list."
    echo ""
    echo "  5. Run 'natalie sync' from any directory any time you add new notes."
    echo "     (It also runs automatically as a post-tool-use hook after every tool call.)"
    echo "     Note: open a new terminal tab to pick up the PATH update if needed."
    echo ""
    echo "  To add more vaults: re-run this script, or run 'natalie init <path>' directly."
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
