# agent-natalie

A portable personal assistant plugin for Claude Code and OpenCode.
Natalie lives in your Obsidian vault and is only active when your agent
is working from that directory.

## What it does

- **Memory** — indexes your vault with FTS + semantic search (fastembed, no API key)
- **Tasks** — discovers and manages checkbox tasks across your notes
- **Documents** — files and retrieves reference material
- **Contacts** — maintains entity/person reference cards
- **Conventions** — remembers your working rules and applies them before acting
- **Personas** — ships 8 preset personalities; drop a `.md` file to add your own

## Requirements

- Python 3.11+
- `uv` (installed automatically by `install.sh` if missing)
- Obsidian (optional but recommended; Natalie falls back to direct file I/O)
- OpenCode (optional; Claude Code works out of the box)

## Install

```bash
git clone <repo-url> agent-natalie
bash agent-natalie/install.sh
```

The script:
1. Installs `uv` if missing
2. Creates `~/.natalie/.venv/` with an isolated Python environment
3. Prompts for your vault path and persona
4. Scaffolds the vault and generates `CLAUDE.md` / `AGENTS.md`
5. Builds the initial search index

## Usage

Open your Obsidian vault directory in Claude Code or OpenCode. Natalie is active
automatically — the MCP server starts when the agent starts, and the vault index
updates after every tool use.

### CLI commands

```bash
natalie sync [--full]          # Rebuild vault index
natalie config --persona donna # Switch persona
natalie init <vault-path>      # Scaffold a new vault (called by install.sh)
```

### MCP tools (available to the agent)

| Tool | Description |
|------|-------------|
| `memory_search` | Hybrid FTS + semantic search across vault notes |
| `memory_store` | Store an outside-vault knowledge entry |
| `note_read` | Read a vault note by path |
| `note_write` | Write or update a vault note |
| `task_list` | List open tasks across the vault |
| `task_capture` | Add a task to a note |
| `task_complete` | Mark a task done |
| `document_file` | File a document |
| `document_retrieve` | Retrieve a document |
| `document_list` | List documents |
| `contact_get` | Get a contact card |
| `contact_update` | Create or update a contact card |
| `contact_list` | List contacts |
| `convention_list` | List conventions for a domain |
| `convention_add` | Add a convention |
| `convention_delete` | Delete a convention |

## Personas

| Preset | Character | Source |
|--------|-----------|--------|
| `natalie` | Natalie Teeger | Monk |
| `donna` | Donna Paulsen | Suits |
| `moneypenny` | Miss Moneypenny | James Bond |
| `smithers` | Waylon Smithers | The Simpsons |
| `april` | April Ludgate | Parks & Recreation |
| `finch` | Dennis Finch | Just Shoot Me! |
| `gary` | Gary Walsh | Veep |
| `pam` | Pam Beesly | The Office |

Add a custom persona by dropping a `.md` file in `<vault>/Natalie/personas/`:

```markdown
---
name: My Assistant
source: Original
tone:
  - helpful
  - direct
---

Your persona prose here.
```

Then: `natalie config --persona my-assistant`

## Configuration

Edit `<vault>/Natalie/config.toml`:

```toml
[persona]
name = "natalie"

[memory]
embedding_model = "BAAI/bge-small-en-v1.5"

[skills]
preferred = ["superpowers", "r-lib"]   # agent will prefer these
denied    = []

[mcps]
preferred = ["obsidian", "github"]
denied    = []
```

After editing, run `natalie config --regen` to regenerate `CLAUDE.md` and `AGENTS.md`.

## Uninstall

```bash
bash /path/to/agent-natalie/uninstall.sh
```

## Things to verify before shipping

- Exact schema for `<vault>/opencode.json` (project-level MCP config for OpenCode)
- Maturity / release status of
  [opencode-claude-hooks](https://github.com/magarcia/opencode-claude-hooks)
  before depending on it for hook registration
- Whether `<vault>/.natalie/natalie.db` needs exclusion from iCloud sync
  (it will sync; embeddings may make it large over time)
