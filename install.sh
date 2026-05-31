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

# ── Update detection ──────────────────────────────────────────────────────────
if [[ -d "$VENV_DIR" ]]; then
    echo "Existing Natalie install found at $VENV_DIR."
    read -rp "Upgrade agent-natalie? [Y/n] " _UPGRADE
    _UPGRADE="${_UPGRADE:-Y}"
    if [[ "$_UPGRADE" =~ ^[Yy]$ ]]; then
        echo "Upgrading agent-natalie..."
        uv pip install --python "$VENV_DIR" --upgrade agent-natalie
        echo ""
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

# ── Prompt for vault path ─────────────────────────────────────────────────────
echo ""
read -rp "Vault path (default: $HOME/Natalie): " VAULT_PATH
VAULT_PATH="${VAULT_PATH:-$HOME/Natalie}"
VAULT_PATH="${VAULT_PATH/#\~/$HOME}"

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

# ── Build initial index ───────────────────────────────────────────────────────
echo ""
echo "Building initial search index..."
echo "On first run this downloads the embedding model (~130 MB)."
echo "A progress bar will appear below — this may take several minutes on slow connections."
echo ""
cd "$VAULT_PATH"
"$NATALIE" sync --full

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Done! Here's what to do next:"
echo ""
echo "  1. Open Obsidian and add '$VAULT_PATH' as a vault."
echo "     The Dashboard layout and CSS snippets are pre-configured."
echo "     If the multi-column layout doesn't appear, go to:"
echo "       Settings → Appearance → CSS snippets"
echo "     and make sure natalie-dashboard, MCL Multi Column, and MCL Wide Views"
echo "     are toggled on. Then reload Obsidian (Cmd+R)."
echo ""
echo "  2. Install the Dataview community plugin (required for the Dashboard):"
echo "       Settings → Community Plugins → turn off Safe Mode → Browse"
echo "       Search 'Dataview' → Install → Enable"
echo "     Then open Dataview settings and enable 'Enable JavaScript Queries'."
echo ""
echo "  3. Start Claude Code from inside the vault:"
echo "       cd '$VAULT_PATH' && claude"
echo "     Claude Code reads .mcp.json and connects to natalie-server automatically."
echo "     The natalie tools (memory_search, note_write, task_list, …) will appear"
echo "     in the tool list."
echo ""
echo "  4. Run 'natalie sync' from the vault directory any time you add new notes."
echo "     (It runs automatically as a Claude Code hook after every tool use.)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
