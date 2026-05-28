#!/usr/bin/env bash
set -euo pipefail

VENV_DIR="$HOME/.natalie/.venv"

# ── uv ────────────────────────────────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    [ -f "$HOME/.local/bin/env" ] && source "$HOME/.local/bin/env"
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi

# ── Install agent-natalie ─────────────────────────────────────────────────────
echo "Creating Python environment at $VENV_DIR..."
mkdir -p "$HOME/.natalie"
uv venv "$VENV_DIR"
uv pip install --python "$VENV_DIR" agent-natalie

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
fi

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

# ── Prompt for embedding provider ────────────────────────────────────────────
echo ""
echo "Embedding providers: fastembed (default, no API key), openai, anthropic"
read -rp "Embedding provider (default: fastembed): " EMBEDDING_PROVIDER
EMBEDDING_PROVIDER="${EMBEDDING_PROVIDER:-fastembed}"

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
"$NATALIE" init "$VAULT_PATH" --persona "$PERSONA" --venv-path "$VENV_DIR" --embedding-provider "$EMBEDDING_PROVIDER"

# ── Build initial index ───────────────────────────────────────────────────────
echo ""
echo "Building initial search index (fastembed model downloads on first run)..."
cd "$VAULT_PATH"
"$NATALIE" sync --full

echo ""
echo "Done. Open '$VAULT_PATH' as your Obsidian vault and start Claude Code from that directory."
