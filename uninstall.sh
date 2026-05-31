#!/usr/bin/env bash
set -euo pipefail

VENV_DIR="$HOME/.natalie/.venv"

echo "This will remove the Natalie Python environment at $VENV_DIR."
read -rp "Continue? [y/N] " CONFIRM
[[ "$CONFIRM" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }

# ── Remove Python environment ─────────────────────────────────────────────────
if [[ -d "$HOME/.natalie" ]]; then
    rm -rf "$HOME/.natalie"
    echo "Removed $HOME/.natalie"
fi

# ── Remove host configs ───────────────────────────────────────────────────────
read -rp "Vault path to remove host configs from (leave empty to skip): " VAULT_PATH
VAULT_PATH="${VAULT_PATH/#\~/$HOME}"

if [[ -n "$VAULT_PATH" && -d "$VAULT_PATH" ]]; then
    for f in \
        "$VAULT_PATH/.mcp.json" \
        "$VAULT_PATH/.claude/settings.json" \
        "$VAULT_PATH/opencode.json" \
        "$VAULT_PATH/.opencode/hooks.json" \
        "$VAULT_PATH/.obsidian/appearance.json"
    do
        if [[ -f "$f" ]]; then
            rm "$f"
            echo "Removed $f"
        fi
    done

    # ── Remove Natalie CSS snippets ───────────────────────────────────────────
    for css in natalie-dashboard "MCL Multi Column" "MCL Wide Views"; do
        f="$VAULT_PATH/.obsidian/snippets/${css}.css"
        if [[ -f "$f" ]]; then
            rm "$f"
            echo "Removed $f"
        fi
    done

    # ── Optionally remove vault scaffold ─────────────────────────────────────
    echo ""
    echo "The following vault files were created by Natalie:"
    echo "  $VAULT_PATH/.natalie/"
    echo "  $VAULT_PATH/Natalie/"
    echo "  $VAULT_PATH/CLAUDE.md"
    echo "  $VAULT_PATH/AGENTS.md"
    echo "  $VAULT_PATH/Dashboard.md"
    echo ""
    echo "All other vault notes are untouched regardless of your answer."
    read -rp "Remove vault scaffold? [y/N] " REMOVE_SCAFFOLD
    if [[ "$REMOVE_SCAFFOLD" =~ ^[Yy]$ ]]; then
        rm -rf "$VAULT_PATH/.natalie" "$VAULT_PATH/Natalie"
        for f in CLAUDE.md AGENTS.md Dashboard.md; do
            if [[ -f "$VAULT_PATH/$f" ]]; then
                rm "$VAULT_PATH/$f"
            fi
        done
        echo "Vault scaffold removed."
    fi
fi

echo ""
echo "Uninstall complete."
