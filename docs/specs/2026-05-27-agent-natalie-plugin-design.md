# agent-natalie Plugin — Design Spec

**Date:** 2026-05-27
**Status:** Draft

---

## 1. Overview

`agent-natalie` is a portable, self-contained personal assistant plugin for Claude Code
and OpenCode (and any MCP-compatible host). It ships a Python MCP server, a companion
CLI, and a library of persona presets. The Obsidian vault is the canonical knowledge
base — human-readable, portable, and sync-friendly. Natalie exists only when the agent
is working from the vault directory; she is invisible in all other projects.

**Design principles:**
- The vault is self-contained and portable. Moving it moves everything.
- Natalie adapts to the user; the user does not adapt to Natalie.
- Zero footprint on the user's existing Python environment.
- No required external services — no cloud API keys, no servers to run.
- Works identically in Claude Code and OpenCode.

---

## 2. Repository Structure

```
agent-natalie/                     # GitHub repo
├── natalie/                       # Python package
│   ├── server.py                  # MCP server entry point
│   ├── cli.py                     # CLI entry point
│   ├── features/                  # Feature modules
│   │   ├── memory.py              # Vault indexing, FTS + semantic search
│   │   ├── tasks.py               # Task management
│   │   ├── documents.py           # Document cabinet
│   │   ├── contacts.py            # Contact reference cards
│   │   └── sync.py                # Vault watcher, index rebuild, CLAUDE.md↔AGENTS.md sync
│   ├── personas/                  # Persona presets
│   │   ├── natalie.md             # Natalie Teeger — Monk [default]
│   │   ├── donna.md               # Donna Paulsen — Suits
│   │   ├── moneypenny.md          # Miss Moneypenny — James Bond
│   │   ├── smithers.md            # Waylon Smithers — The Simpsons
│   │   ├── april.md               # April Ludgate — Parks & Recreation
│   │   ├── finch.md               # Dennis Finch — Just Shoot Me
│   │   ├── gary.md                # Gary Walsh — Veep
│   │   └── pam.md                 # Pam Beesly — The Office
│   └── templates/                 # CLAUDE.md / AGENTS.md templates
├── install.sh                     # One-liner install script
├── uninstall.sh                   # One-liner uninstall script
├── pyproject.toml
└── README.md
```

---

## 3. Architecture

**Option B: MCP server + CLI companion** — two entry points in one Python package.

### MCP server (`natalie-server`)

Exposes tools to the agent: vault search, note read/write, task operations, document
cabinet, contact cards, convention lookup. Started by Claude Code / OpenCode via the
vault-local MCP config. Detects the vault by walking up from its working directory
until it finds `.natalie/natalie.db` — no env var needed, the config survives the vault
being moved.

### CLI (`natalie`)

Handles operational concerns: `install`, `uninstall`, `sync`, `config`. The vault
watcher runs here. The install script registers `natalie sync` as a `PostToolUse` hook
so the index stays current after file mutations.

The `natalie/features/` modules are independent internal units in v1. That boundary
becomes public in v2 (see §7), so it is designed now with that seam in mind.

---

## 4. Vault Structure

The vault is the single source of truth for everything except the Python environment.

```
<vault>/
├── CLAUDE.md                      # Canonical instructions — editable in Obsidian
├── AGENTS.md                      # Kept in sync with CLAUDE.md by Natalie
├── Dashboard.md                   # Scaffolded on install
├── .claude/
│   └── settings.json              # Claude Code: MCP server entry + PostToolUse hook
├── opencode.json                  # OpenCode: MCP server entry (project-level)
├── .opencode/
│   └── hooks.json               # OpenCode: PostToolUse hook via opencode-claude-hooks
├── .natalie/
│   └── natalie.db                 # SQLite: search index + conventions (hidden from Obsidian)
└── Natalie/
    ├── config.toml                # Vault-level config (visible, editable in Obsidian)
    ├── personas/                  # Custom user personas (.md files)
    ├── Documents/                 # Document cabinet
    └── Contacts/                  # Contact reference cards
```

**Outside-vault footprint (machine-local, not portable):**

```
~/.natalie/
└── .venv/                         # Isolated Python environment
```

This is the only thing outside the vault. There are no global instruction file patches,
no per-project config files, and no other system-level modifications.

---

## 5. Memory System

### Two layers

**Obsidian vault** — human-readable source of truth. The user writes here: notes,
tasks, meeting logs, drafts, research. Cross-links (`[[wiki-links]]`) and tags handle
relationships natively. Obsidian is the graph; the database is the index.

**`natalie.db`** — SQLite in `<vault>/.natalie/`. Machine-readable search index derived
from the vault, plus conventions and outside-vault knowledge entries. Always rebuildable
from vault content.

### Database schema

```
notes         — path, title, tags, frontmatter, full text, last_modified,
                collection, machine_mac (null for in-vault notes)
notes_fts     — FTS5 virtual table over notes.body (keyword search)
embeddings    — vector blob per note (semantic search)
conventions   — domain, rule, source (explicit | observed), created_at
machines      — mac_address, hostname, last_seen
```

### Collections

Every row carries a `collection` field (default: `"global"`). Collections scope search
and memory to a topic or project without requiring external config files. A project
living outside the vault can have its own collection populated by explicit knowledge
entries Natalie stores when the user tells her about it.

### Outside-vault entries

Natalie does not crawl external directories. She stores knowledge *about* outside-vault
resources when the user tells her or when she observes something worth remembering. Any
entry referencing an outside-vault path is tagged with the machine's MAC address
(obtained via Python's `uuid.getnode()`). On a different machine, those entries are
visible but flagged as locally unresolvable, with the originating hostname shown as a
label. Works on macOS, Windows, and Linux without platform-specific code.

### Vault access

At startup the server pings the Obsidian Local REST API (default port 27123). If it
responds, use it for vault reads and writes. Otherwise fall back to direct file I/O.
The Obsidian MCP is not a dependency.

### Embedding

Default: `fastembed` with `BAAI/bge-small-en-v1.5`. Downloads the ONNX model on first
use, caches locally, works offline thereafter. No API key or external server required.
Configurable in `Natalie/config.toml`:

```toml
[memory]
embedding_provider = "fastembed"
embedding_model    = "BAAI/bge-small-en-v1.5"
# embedding_provider = "openai"      # requires api_key
# embedding_provider = "anthropic"
```

### Sync

`natalie sync` re-indexes changed notes (incremental). `natalie sync --full` rebuilds
the entire index. The install script registers `natalie sync` as a `PostToolUse` hook
in both `.claude/settings.json` and `.opencode/hooks.json` (via opencode-claude-hooks).

---

## 6. Persona System

Personas are markdown files with frontmatter (name, source, tone keywords) followed by
a prose personality spec. The plugin ships a preset library (see §2). Users add custom
personas by dropping `.md` files in `<vault>/Natalie/personas/`.

Active persona is set in `Natalie/config.toml`:

```toml
[persona]
name = "natalie"          # any preset name, or filename from Natalie/personas/
```

At install the script asks which persona to use, then generates `CLAUDE.md` and
`AGENTS.md` with the persona content baked in, using markers for clean future
replacement:

```
<!-- agent-natalie:persona:start -->
...persona content...
<!-- agent-natalie:persona:end -->
```

Changing persona: `natalie config --persona donna` regenerates only the marked section
in both files. Behavioral instructions (memory rules, conventions, task handling) are
persona-independent and live outside the markers.

---

## 7. Extension Model

### Level 1 — Registered tools (config-based, v1)

Users declare what is available in their environment:

```toml
[skills]
preferred = ["superpowers", "r-lib"]
denied    = []

[mcps]
preferred = ["obsidian", "github"]
denied    = []
```

The generated `CLAUDE.md` / `AGENTS.md` instruct the agent to prefer registered skills
and MCPs when relevant, and to avoid denied ones entirely. This requires no Python code
— the plugin simply tells the agent what is available.

### Level 2 — Feature modules (future v2)

The `natalie/features/` boundary is internal in v1. In v2 a `[modules]` config section
will allow additional Python modules to register new MCP tools at server startup.
Community contributions land here.

---

## 8. Conventions System

Conventions are user-established rules stored in the `conventions` table and queried
before Natalie acts on any request in the relevant domain.

**Sources:**
- **Explicit** — user states a preference: "from now on put tasks in project notes"
- **Observed** — Natalie notices a pattern, asks the user to confirm it as a convention

**Before acting**, the MCP server queries conventions scoped to the relevant domain and
incorporates matching rules into its behavior.

**Example entries:**
- `domain: tasks | rule: "Create tasks in the active project note, not a dedicated file"`
- `domain: contacts | rule: "Always include the person's institution in the card title"`

---

## 9. CLAUDE.md / AGENTS.md Management

Both files live at the vault root, visible and editable in Obsidian. They are picked up
automatically by Claude Code and OpenCode when the working directory is the vault. No
global instruction file is modified.

`CLAUDE.md` is canonical. `AGENTS.md` mirrors it with OpenCode-specific adjustments
(hook syntax, tool names). The user can ask Natalie to sync them at any time; Natalie
diffs the two and applies changes, adjusting platform-specific language as needed.

---

## 10. Install / Uninstall

### Install (`install.sh`)

1. Check for `uv`; install it if missing.
2. Prompt: vault path (existing vault or create new), persona choice, embedding
   provider.
3. Clone repo; run `uv venv ~/.natalie/.venv && uv pip install`.
4. Scaffold the vault: `.natalie/`, `Natalie/` structure, `Dashboard.md`,
   `Natalie/config.toml` with answers from step 2.
5. Generate `CLAUDE.md` and `AGENTS.md` at vault root with the selected persona.
6. Write `<vault>/.claude/settings.json` with the `natalie-server` MCP entry and
   `PostToolUse` hook.
7. Write `<vault>/opencode.json` with the OpenCode MCP entry.
8. Write `<vault>/.opencode/hooks.json` with the `tool.execute.after` hook
   (requires opencode-claude-hooks to be installed).
9. Run `natalie sync --full` to build the initial index.

The MCP server entry points at `~/.natalie/.venv/bin/natalie-server`. The server
locates the vault from its working directory — no env var required.

### Uninstall (`uninstall.sh`)

1. Remove `~/.natalie/` (Python environment).
2. Remove `.claude/settings.json` and `.opencode.json` from the vault.
3. Prompt: remove vault scaffold (`Natalie/`, `.natalie/`, `CLAUDE.md`, `AGENTS.md`)?
   All other vault notes are untouched regardless.

---

## 11. Configuration

### Vault-level (`<vault>/Natalie/config.toml`)

```toml
[persona]
name = "natalie"

[memory]
embedding_provider = "fastembed"
embedding_model    = "BAAI/bge-small-en-v1.5"

[skills]
preferred = []
denied    = []

[mcps]
preferred = []
denied    = []

[features.documents]
directory = "Natalie/Documents"

[features.contacts]
directory = "Natalie/Contacts"

[features.sync]
tag          = "natalie"
subdirectory = "Natalie"
```

There is no per-project config file. Project-level scoping is handled through
collections within `natalie.db`.

---

## 12. v1 Feature Scope

Each feature is a generalized port of the current Simon-specific implementation.
Hardcoded paths and conventions become configurable defaults in `config.toml`.

| Module | What it provides | Key generalization |
|---|---|---|
| `memory` | Vault indexing, FTS + semantic search, conventions | Replaces mnem graph |
| `tasks` | Task discovery across vault, capture, completion | No single required file; adapts to user conventions |
| `documents` | Document filing, retrieval, reconciliation | Configurable directory |
| `contacts` | Entity/person reference cards | Configurable directory |
| `sync` | Vault watcher, index rebuild, CLAUDE.md↔AGENTS.md sync | Configurable tag + subdirectory |

Existing Python scripts (`natalie_sync.py`, `natalie_index_document.py`, etc.) are
ported into the module structure and extended to read from `config.toml`.

---

## 13. Cross-platform Compatibility

| Concern | Claude Code | OpenCode |
|---|---|---|
| Instructions file | `CLAUDE.md` (vault root) | `AGENTS.md` (vault root) |
| MCP config | `<vault>/.claude/settings.json` | `<vault>/opencode.json` |
| Hook registration | `PostToolUse` in `.claude/settings.json` | `tool.execute.after` in `.opencode/hooks.json` via opencode-claude-hooks |
| Machine ID | `uuid.getnode()` — works on macOS, Windows, Linux | same |

The MCP server is host-agnostic — it speaks the MCP protocol regardless of which
client connects. Both clients are configured by the install script; neither requires
manual setup.
