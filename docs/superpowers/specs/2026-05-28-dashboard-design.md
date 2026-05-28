# Dashboard Upgrade Design

**Date:** 2026-05-28  
**Status:** Approved  
**Scope:** Replace the barebones `Dashboard.md` shipped by `natalie init` with the rich multi-column Obsidian dashboard, and bundle the three CSS snippets it requires.

---

## Background

`natalie init` currently writes a 7-line placeholder `Dashboard.md` (the `_DASHBOARD_MD` string hardcoded in `cli.py`). No CSS snippets are installed. The new dashboard uses Obsidian callouts (`banner`, `multi-column`, `task-list`, `briefing`, `links`) and requires three CSS snippet files to render correctly.

---

## Decision: bundle all three CSS files

The two external files (`MCL Multi Column.css`, `MCL Wide Views.css`) are GPL-3.0. After adding an MIT license to agent-natalie, bundling them is clean under GPL's "mere aggregation" clause — the CSS files remain GPL-3.0, the Python package remains MIT, and both are clearly marked. Bundling avoids a network dependency at init time and is appropriate given the MCL library is mature and slow-moving.

---

## File layout changes

```
natalie/
  snippets/                          ← new directory
    natalie-dashboard.css            ← custom CSS (MIT)
    MCL Multi Column.css             ← vendored, GPL-3.0, attribution header added
    MCL Wide Views.css               ← vendored, GPL-3.0, attribution header added
  templates/
    Dashboard.md                     ← new: rich dashboard markup (replaces _DASHBOARD_MD)
    claude.md.jinja                  (unchanged)
    agents.md.jinja                  (unchanged)
```

`_DASHBOARD_MD` in `cli.py` is deleted. Hatchling already includes all files under `natalie/` recursively — no `pyproject.toml` changes needed for asset inclusion.

The two GPL files receive a short attribution comment at the top:
```css
/* MCL Multi Column — efemkay/obsidian-modular-css-layout (GPL-3.0)
   https://github.com/efemkay/obsidian-modular-css-layout */
```

---

## `natalie init` changes

Four additions to the existing `init()` function. All follow the "skip if already exists" invariant already applied to `CLAUDE.md`, `AGENTS.md`, and `config.toml`.

### 1. Dashboard.md

Read from `natalie/templates/Dashboard.md` (same resolution pattern as persona files):

```python
dashboard = vault / "Dashboard.md"
if not dashboard.exists():
    _DASHBOARD_TEMPLATE = Path(__file__).parent / "templates" / "Dashboard.md"
    dashboard.write_text(_DASHBOARD_TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
```

### 2. Snippets directory

```python
(vault / ".obsidian" / "snippets").mkdir(parents=True, exist_ok=True)
```

### 3. Copy CSS files (skip if target exists)

```python
_SNIPPETS_SRC = Path(__file__).parent / "snippets"
for css in _SNIPPETS_SRC.glob("*.css"):
    dest = vault / ".obsidian" / "snippets" / css.name
    if not dest.exists():
        dest.write_bytes(css.read_bytes())
```

### 4. Enable snippets in `appearance.json`

Reuses the existing `_merge_json` helper, whose `_deep_merge` already appends list items without duplicates:

```python
snippet_names = [p.stem for p in _SNIPPETS_SRC.glob("*.css")]
_merge_json(
    vault / ".obsidian" / "appearance.json",
    {"enabledCssSnippets": snippet_names},
)
```

Obsidian's snippet name is the CSS filename without the `.css` extension: `"MCL Multi Column"`, `"MCL Wide Views"`, `"natalie-dashboard"`.

---

## `install.sh` changes

### 1. Remove dead `REPO_URL` placeholder

`REPO_URL="https://github.com/yourusername/agent-natalie"` is defined but never used. Delete it.

### 2. Vault modification confirmation prompt

Inserted between the embedding provider prompt and the `natalie init` call:

```bash
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
```

---

## Tests

All new tests go in `tests/test_cli.py`, using the existing `tmp_path`/`vault`/`db` fixtures and the Typer CLI test runner.

| Test | Assertion |
|------|-----------|
| `test_init_copies_css_snippets` | All 3 CSS files exist in `<vault>/.obsidian/snippets/` after init |
| `test_init_skips_existing_css` | A pre-existing CSS file with sentinel content is not overwritten |
| `test_init_enables_css_snippets` | `appearance.json` is created with `enabledCssSnippets` containing all 3 names |
| `test_init_merges_existing_appearance_json` | Pre-existing keys and snippet names are preserved; new names appended without duplicates |
| `test_init_writes_rich_dashboard` | `Dashboard.md` contains multi-column callout markup (e.g. `multi-column`, `banner`) |
| `test_init_skips_existing_dashboard` | Pre-existing `Dashboard.md` is not overwritten |

---

## Invariants preserved

- `safe_join` is not relevant here (no user-supplied paths in this flow).
- "Skip if exists" applied consistently: `Dashboard.md`, each CSS file, and existing `appearance.json` entries are never overwritten.
- `_merge_json` / `_deep_merge` handles `appearance.json` — existing keys and snippet lists are preserved.
- `natalie/snippets/` files are static; they are never written back by the server or CLI post-init.
