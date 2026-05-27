#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/yourusername/agent-natalie"
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
