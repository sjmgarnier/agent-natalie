#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$HOME/.natalie/.venv"

# ── uv ────────────────────────────────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    [ -f "$HOME/.local/bin/env" ] && source "$HOME/.local/bin/env"
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi

NATALIE="$VENV_DIR/bin/natalie"

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
        local skill_name="natalie-$(basename "$skill_dir")"
        cp -r "$skill_dir" "$vault_path/.claude/skills/$skill_name"
        cp -r "$skill_dir" "$vault_path/.opencode/skills/$skill_name"
        echo "  Installed: $skill_name"
    done
}

# ── Update detection ──────────────────────────────────────────────────────────
if [[ -d "$VENV_DIR" ]]; then
    echo "Existing Natalie install found at $VENV_DIR."
    read -rp "Upgrade agent-natalie? [Y/n] " _UPGRADE
    _UPGRADE="${_UPGRADE:-Y}"
    if [[ "$_UPGRADE" =~ ^[Yy]$ ]]; then
        echo "Upgrading agent-natalie..."
        uv pip install --python "$VENV_DIR" --upgrade agent-natalie
        echo ""
        read -ep "Regenerate agent instructions for a vault? Enter vault path (blank to skip): " _VAULT_PATH
        if [[ -n "$_VAULT_PATH" ]]; then
            _VAULT_PATH="${_VAULT_PATH/#\~/$HOME}"
            _VAULT_PATH="${_VAULT_PATH//\\/}"
            _VAULT_PATH="$(cd "$_VAULT_PATH" 2>/dev/null && pwd || echo "$_VAULT_PATH")"
            echo ""
            (cd "$_VAULT_PATH" && "$NATALIE" config --regen)
            echo ""
            echo "CLAUDE.md and AGENTS.md updated with the latest tool instructions."
            echo "Repeat for each vault you want to update."
        fi
        echo ""
        read -ep "Install/update companion skills? Enter vault path (blank to skip): " _SKILLS_PATH
        if [[ -z "$_SKILLS_PATH" && -n "$_VAULT_PATH" ]]; then
            _SKILLS_PATH="$_VAULT_PATH"
        fi
        if [[ -n "$_SKILLS_PATH" ]]; then
            _SKILLS_PATH="${_SKILLS_PATH/#\~/$HOME}"
            _SKILLS_PATH="${_SKILLS_PATH//\\/}"
            _SKILLS_PATH="$(cd "$_SKILLS_PATH" 2>/dev/null && pwd || echo "$_SKILLS_PATH")"
            echo ""
            _install_skills "$_SKILLS_PATH"
            echo "  Skills installed. Repeat for each vault you want to update."
        fi
        echo ""
        # Refresh symlink in case the binary path changed
        mkdir -p "$HOME/.local/bin"
        ln -sf "$VENV_DIR/bin/natalie" "$HOME/.local/bin/natalie"
        echo "Done. Run 'natalie sync --full' from your vault directory to rebuild the search index."
        exit 0
    fi
    echo "Proceeding with full re-install..."
    rm -rf "$VENV_DIR"
fi

# ── Install agent-natalie ─────────────────────────────────────────────────────
echo "Creating Python environment at $VENV_DIR..."
mkdir -p "$HOME/.natalie"
uv venv "$VENV_DIR"
uv pip install --python "$VENV_DIR" agent-natalie

# ── Add natalie to PATH ───────────────────────────────────────────────────────
mkdir -p "$HOME/.local/bin"
ln -sf "$VENV_DIR/bin/natalie" "$HOME/.local/bin/natalie"
for _RC in "$HOME/.zshrc" "$HOME/.bashrc"; do
    if [[ -f "$_RC" ]] && ! grep -q '\.local/bin' "$_RC"; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$_RC"
        echo "Added ~/.local/bin to PATH in $_RC"
    fi
done
export PATH="$HOME/.local/bin:$PATH"

# ── Prompt for vault path ─────────────────────────────────────────────────────
echo ""
read -ep "Vault path (default: $HOME/Natalie): " VAULT_PATH
VAULT_PATH="${VAULT_PATH:-$HOME/Natalie}"
VAULT_PATH="${VAULT_PATH/#\~/$HOME}"
# Strip shell escape backslashes (read -e doesn't reliably remove them from readline input)
VAULT_PATH="${VAULT_PATH//\\/}"
# Resolve to absolute path so relative entries and symlinks work correctly
VAULT_PATH="$(cd "$VAULT_PATH" 2>/dev/null && pwd || echo "$VAULT_PATH")"

# ── Prompt for persona ────────────────────────────────────────────────────────
echo ""
echo "Available personas: natalie, donna, moneypenny, smithers, april, finch, gary, pam"
read -rp "Persona (default: natalie): " PERSONA
PERSONA="${PERSONA:-natalie}"

# ── Confirm vault modification ────────────────────────────────────────────────
echo ""
echo "natalie will create or modify the following in: $VAULT_PATH"
echo "  Dashboard.md, CLAUDE.md, AGENTS.md   (skipped if already present)"
echo "  .obsidian/snippets/                  (3 CSS files, skipped if already present)"
echo "  .obsidian/appearance.json            (enables CSS snippets)"
echo "  .mcp.json, .claude/settings.json, opencode.json, .opencode/hooks.json"
echo ""
read -rp "Proceed? [Y/n] " _PROCEED
_PROCEED="${_PROCEED:-Y}"
if [[ ! "$_PROCEED" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

# ── Initialize vault ─────────────────────────────────────────────────────────
echo ""
echo "Initializing vault at $VAULT_PATH..."
"$NATALIE" init "$VAULT_PATH" --persona "$PERSONA" --venv-path "$VENV_DIR"

echo ""
read -rp "Install companion Claude Code skills into this vault? [Y/n] " _INSTALL_SKILLS
_INSTALL_SKILLS="${_INSTALL_SKILLS:-Y}"
if [[ "$_INSTALL_SKILLS" =~ ^[Yy]$ ]]; then
    echo ""
    _install_skills "$VAULT_PATH"
fi

# ── Build initial index ───────────────────────────────────────────────────────
echo ""
echo "Building initial search index..."
echo "On first run this downloads the embedding model (~130 MB)."
echo "A progress bar will appear below — this may take several minutes on slow connections."
echo ""
cd "$VAULT_PATH"
if ! "$NATALIE" sync --full; then
    echo ""
    echo "WARNING: Search index build failed (network or model download issue)."
    echo "   Your vault was still created at $VAULT_PATH."
    echo "   Run 'natalie sync --full' from the vault directory when ready."
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Done! Here's what to do next:"
echo ""
echo "  1. Open Obsidian and add '$VAULT_PATH' as a vault."
echo "     The Dashboard layout and CSS snippets are pre-configured."
echo "     If the multi-column layout doesn't appear, go to:"
echo "       Settings → Appearance → CSS snippets"
echo "     and make sure natalie-dashboard, MCL Multi Column, and MCL Wide Views"
echo "     are toggled on. If they aren't listed, click the folder icon to refresh."
echo ""
echo "  2. Install the Local REST API community plugin (recommended):"
echo "       Settings → Community plugins → turn off Restricted Mode → Browse"
echo "       Search 'Local REST API' → Install → Enable"
echo "     Then open Settings → Community plugins → Local REST API, copy the API Key,"
echo "     and paste it into $VAULT_PATH/Natalie/config.toml:"
echo "       [obsidian]"
echo "       api_key = \"paste-your-key-here\""
echo "     Natalie works without it but falls back to direct file I/O."
echo ""
echo "  3. Install the Dataview community plugin (required for the Dashboard):"
echo "       Settings → Community Plugins → Browse"
echo "       Search 'Dataview' → Install → Enable"
echo "     Then open Dataview settings and enable 'Enable JavaScript Queries'
     and 'Enable Inline JavaScript Queries'."
echo ""
echo "  4. Start your agent from inside the vault:"
echo "       cd '$VAULT_PATH' && claude     # Claude Code"
echo "       cd '$VAULT_PATH' && opencode   # OpenCode"
echo "     Both read their config files and connect to natalie-server automatically."
echo "     The natalie tools (memory_search, note_write, task_list, …) will appear"
echo "     in the tool list."
echo ""
echo "  5. Run 'natalie sync' from any directory any time you add new notes."
echo "     (It also runs automatically as a post-tool-use hook after every tool call.)"
echo "     Note: open a new terminal tab to pick up the PATH update if needed."
echo ""
echo "  To add more vaults: re-run this script, or run 'natalie init <path>' directly."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
