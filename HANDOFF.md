# agent-natalie — Session Handoff

**Date:** 2026-05-27
**From:** Natalie (brainstorming session in the Natalie vault)
**Next step:** Write an implementation plan using the `writing-plans` skill

---

## What this repo is

`agent-natalie` is a portable personal assistant plugin for Claude Code and OpenCode.
It started as a collection of scripts, CLAUDE.md behaviors, and mnem memory tooling
specific to Simon's setup. This session designed it as a proper, distributable plugin.

The full design spec is at: `docs/specs/2026-05-27-agent-natalie-plugin-design.md`

---

## Key decisions made this session

### Architecture
- **Option B**: Python MCP server (`natalie-server`) + CLI companion (`natalie`)
- Two entry points in one Python package (`pyproject.toml`)
- Feature modules in `natalie/features/` — internal boundary in v1, public in v2

### The vault is everything
- The Obsidian vault is the single source of truth
- `CLAUDE.md` and `AGENTS.md` live at the vault root (editable in Obsidian)
- All config lives in `<vault>/Natalie/config.toml`
- All agent host configs live in the vault:
  - `<vault>/.claude/settings.json` — Claude Code MCP + PostToolUse hook
  - `<vault>/opencode.json` — OpenCode MCP entry
  - `<vault>/.opencode/hooks.json` — OpenCode PostToolUse via opencode-claude-hooks
- The only outside-vault footprint is `~/.natalie/.venv/` (Python env, not portable)
- No global CLAUDE.md patching; no per-project config files outside the vault
- Natalie is only active when the agent's working directory is the vault

### Memory system
- SQLite (`<vault>/.natalie/natalie.db`) — hidden from Obsidian file explorer
- Three search mechanisms: FTS5 (keyword), fastembed (semantic), direct query
- `fastembed` with `BAAI/bge-small-en-v1.5` — no API key, no server, downloads on first use
- Obsidian Local REST API (port 27123) primary; direct file I/O fallback
- Collections for project scoping (column in db, no separate files)
- Conventions table — user rules queried before every action
- Outside-vault entries tagged with MAC address via `uuid.getnode()` (cross-platform)
- `machines` table stores MAC + hostname for display

### Persona system
- Default: **Natalie Teeger** (Monk, seasons 3–8)
- Ships a preset library: Donna Paulsen, Miss Moneypenny, Waylon Smithers,
  April Ludgate, Dennis Finch, Gary Walsh, Pam Beesly
- Personas are `.md` files: frontmatter (name, source, tone keywords) + prose spec
- User custom personas go in `<vault>/Natalie/personas/`
- Active persona set in `config.toml`; `natalie config --persona X` regenerates
  the marked section in CLAUDE.md/AGENTS.md

### Extension model
- **Level 1 (v1)**: config-based — `preferred`/`denied` lists for skills and MCPs
  written into the generated CLAUDE.md/AGENTS.md
- **Level 2 (v2)**: module system — `natalie/features/` boundary made public,
  community modules register new MCP tools

### Install / uninstall
- One-liner shell scripts (`install.sh`, `uninstall.sh`)
- Uses `uv` for isolated Python env in `~/.natalie/.venv/`
- Install: prompts for vault path + persona, scaffolds vault, generates
  CLAUDE.md/AGENTS.md, writes host configs, runs initial sync
- Uninstall: removes `.venv`, host configs; optionally removes vault scaffold

### Platform compatibility
| Concern | Claude Code | OpenCode |
|---|---|---|
| Instructions | `CLAUDE.md` | `AGENTS.md` |
| MCP config | `<vault>/.claude/settings.json` | `<vault>/opencode.json` |
| Hooks | `PostToolUse` in settings.json | `tool.execute.after` in `.opencode/hooks.json` via [opencode-claude-hooks](https://github.com/magarcia/opencode-claude-hooks) |
| Machine ID | `uuid.getnode()` | same |

### Still to verify during implementation
- Exact schema for `<vault>/opencode.json` (project-level MCP config)
- opencode-claude-hooks maturity / release status before depending on it
- Whether `<vault>/.natalie/natalie.db` needs to be excluded from iCloud sync
  (it will sync, which is fine; but embeddings may make it large over time)

---

## v1 feature scope

| Module | What it provides |
|---|---|
| `memory` | Vault indexing, FTS + semantic search, conventions |
| `tasks` | Task discovery across vault (no fixed file), capture, completion |
| `documents` | Document cabinet (file, retrieve, reconcile) |
| `contacts` | Entity/person reference cards |
| `sync` | Vault watcher, index rebuild, CLAUDE.md↔AGENTS.md sync |

Each module is a generalized port of existing Simon-specific scripts in the Natalie
vault. Hardcoded paths become configurable defaults in `config.toml`.

---

## What to do next

1. Open Claude Code in this repo directory
2. Run the `writing-plans` skill
3. Point it at `docs/specs/2026-05-27-agent-natalie-plugin-design.md`
4. The plan should decompose implementation into phases, likely:
   - Phase 1: repo scaffold, pyproject.toml, CLI skeleton, install/uninstall scripts
   - Phase 2: MCP server skeleton + vault detection
   - Phase 3: memory module (SQLite + FTS5 + fastembed + sync)
   - Phase 4: conventions system
   - Phase 5: tasks, documents, contacts modules (port + generalize existing scripts)
   - Phase 6: persona system + CLAUDE.md/AGENTS.md generation
   - Phase 7: extension model (config-based skills/MCPs)
   - Phase 8: packaging + README

---

## Reference

- Design spec: `docs/specs/2026-05-27-agent-natalie-plugin-design.md`
- Existing scripts to port: `/Users/simon/Library/CloudStorage/ProtonDrive-simon.garnier@pm.me-folder/Natalie/scripts/`
- Existing CLAUDE.md (persona source): `/Users/simon/Library/CloudStorage/ProtonDrive-simon.garnier@pm.me-folder/Natalie/CLAUDE.md`
- Inspiration: https://github.com/vuldin/yapa
- OpenCode hooks shim: https://github.com/magarcia/opencode-claude-hooks
