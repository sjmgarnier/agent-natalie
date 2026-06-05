# agent-natalie — Personal Assistant MCP Server for Obsidian

[![PyPI](https://img.shields.io/pypi/v/agent-natalie)](https://pypi.org/project/agent-natalie/)
[![Python](https://img.shields.io/pypi/pyversions/agent-natalie)](https://pypi.org/project/agent-natalie/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A portable personal assistant MCP server for AI coding agents. Natalie lives in your Obsidian vault — memory, tasks, contacts, and conventions stay fully local and offline, no cloud or external API required.

Tested with Claude Code and OpenCode. Any MCP-compatible agent client
should work — see [Connecting your agent](#connecting-your-agent) below.

## What it does

- **Memory** — indexes your vault with FTS + semantic search (fastembed, fully offline)
- **Tasks** — discovers and manages checkbox tasks across your notes
- **Documents** — files and retrieves reference material
- **Contacts** — maintains entity/person reference cards
- **Conventions** — remembers your working rules and applies them before acting
- **Personas** — ships 8 preset personalities; drop a `.md` file to add your own

---

## Requirements

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) (installed automatically by `install.sh` if missing)
- Obsidian (optional but recommended — Natalie falls back to direct file I/O without it)

---

## Install

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/sjmgarnier/agent-natalie/main/install.sh)
```

The script:
1. Installs `uv` if missing
2. Creates `~/.natalie/.venv/` with an isolated Python environment
3. Prompts for your vault path and persona
4. Scaffolds the vault (dashboard, CLAUDE.md, AGENTS.md, CSS snippets, MCP config)
5. Builds the initial search index

> **Note:** Step 5 downloads the embedding model (~130 MB) on first run. This is cached
> after the first sync. Allow extra time on slow connections.

---

## Obsidian setup

After running `install.sh`, complete these steps in Obsidian before use.

### 1. Add the vault

Open Obsidian → **Open folder as vault** → select the vault path you provided to `install.sh`.

### 2. Enable the CSS snippets

The dashboard layout requires three CSS snippets that `install.sh` already copied into
`.obsidian/snippets/`. Enable them:

1. Go to **Settings → Appearance → CSS snippets**
2. Toggle on **natalie-dashboard**, **MCL Multi Column**, and **MCL Wide Views**

If the snippets are not listed, click the folder icon to refresh the snippets directory.
If the multi-column layout still doesn't render, open the Command palette (Cmd+P / Ctrl+P) and run **Reload app without saving**.

### 3. Install and configure Dataview

The dashboard uses [Dataview](https://github.com/blacksmithgu/obsidian-dataview) for
live queries. Install it from the community plugin browser:

1. **Settings → Community plugins → Browse**
2. Search **Dataview** → **Install** → **Enable**
3. Open **Dataview settings** → enable **Enable JavaScript Queries** and **Enable Inline JavaScript Queries**

Without Dataview the dashboard will show raw code blocks instead of rendered tables and task lists.

### 4. Install the Tasks plugin

The [Tasks](https://github.com/obsidian-tasks-group/obsidian-tasks) plugin enables rich task metadata — due dates, priorities, and recurrence rules — that Natalie can read and write via `task_capture` and `task_complete`.

1. **Settings → Community plugins → Browse**
2. Search **Tasks** → **Install** → **Enable**

Without the Tasks plugin, Natalie falls back to plain checkboxes and the metadata fields (`due`, `priority`, `recurrence`) will not be available.

### 5. Open the Dashboard

Click **Dashboard.md** in the vault root. Switch to Reading view if it doesn't render automatically.

---

## Connecting your agent

`natalie-server` is a standard MCP server. Any MCP-compatible agent client can use it.
`natalie init` pre-wires **Claude Code** and **OpenCode** automatically; for other clients
follow the generic instructions below.

> **Compatibility note:** Natalie has been tested with Claude Code and OpenCode.
> Other MCP clients should work but have not been verified.

### Claude Code

Start Claude Code from inside the vault directory:

```bash
cd /path/to/your/vault
claude
```

Claude Code reads `.mcp.json` and connects to `natalie-server` automatically.
The Natalie tools (`memory_search`, `note_write`, `task_list`, …) will appear in the tool list.
`natalie sync` runs automatically as a post-tool-use hook after every tool call.

### OpenCode

Start OpenCode from inside the vault directory:

```bash
cd /path/to/your/vault
opencode
```

OpenCode reads `opencode.json` and connects to `natalie-server` automatically.
`natalie sync` runs automatically as a post-tool-use hook after every tool call.

### Other MCP clients

Point your client at the `natalie-server` binary and run it from inside the vault directory:

```
command: /Users/<you>/.natalie/.venv/bin/natalie-server
args:    []
cwd:     /path/to/your/vault
```

The server uses stdio transport. It discovers the vault by walking up from its working
directory looking for `.natalie/natalie.db`, so the working directory must be set to
the vault root (or any subdirectory of it).

Run `natalie sync` from the vault directory any time you add new notes outside of an
agent session.

---

## CLI commands

```bash
natalie sync [--full]              # Rebuild vault index (--full wipes and reindexes everything)
natalie config --persona donna     # Switch persona and regenerate CLAUDE.md / AGENTS.md
natalie config --regen             # Regenerate CLAUDE.md / AGENTS.md without changing persona
natalie init <vault-path>          # Scaffold a new vault (called by install.sh)
```

---

## MCP tools

| Tool | Description |
|------|-------------|
| `ping` | Check that the server is running |
| `memory_search` | Hybrid FTS + semantic search across vault notes |
| `memory_store` | Store an outside-vault knowledge entry |
| `note_read` | Read a vault note by path |
| `note_write` | Write or update a vault note |
| `task_list` | List open (or all) tasks across the vault |
| `task_capture` | Add a task to a note |
| `task_complete` | Mark a task done |
| `document_file` | Register a vault file in the document index with a semantic description |
| `document_list` | List or semantically search filed documents |
| `contact_get` | Get a contact card by slug |
| `contact_update` | Create or update a contact card |
| `contact_list` | List all contact slugs |
| `convention_list` | List conventions, optionally filtered by domain |
| `convention_add` | Add a convention |
| `convention_delete` | Delete a convention by ID |

---

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

### Custom personas

Drop a `.md` file in `<vault>/Natalie/personas/`:

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

Then activate it:

```bash
natalie config --persona my-assistant
```

---

## Configuration

Edit `<vault>/Natalie/config.toml`, then run `natalie config --regen`:

```toml
[persona]
name = "natalie"

[memory]
embedding_model = "BAAI/bge-small-en-v1.5"

[skills]
preferred = []   # e.g. ["superpowers", "r-lib"] — agent will prefer these
denied    = []

[mcps]
preferred = []   # e.g. ["obsidian", "github"]
denied    = []

[features.documents]
directory = "Natalie/Documents"

[features.contacts]
directory = "Natalie/Contacts"
```

---

## Known limitations

**Changing the embedding model** — Existing embeddings are incompatible with a new model.
After changing `embedding_model` in `config.toml`, run `natalie sync --full` to rebuild
the index from scratch.

**Single active session per vault** — `natalie.db` lives inside the vault. If you sync
your vault across machines (iCloud, Dropbox, Syncthing, or similar), running
`natalie-server` on two machines simultaneously against the same vault risks SQLite WAL
corruption. Keep one active session at a time.

---

## Upgrade

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/sjmgarnier/agent-natalie/main/install.sh)
```

The script detects an existing install and offers to upgrade in place.

---

## Uninstall

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/sjmgarnier/agent-natalie/main/uninstall.sh)
```
