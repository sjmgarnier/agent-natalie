---
name: natalie-research
description: >
  Five-phase web research workflow that deposits structured findings into the
  vault. Covers planning (vault-first check), iterative search, synthesis,
  storage via the natalie-memory routing map, and a completion handoff brief.
---

This skill is well-suited for delegation to `natalie-assistant` — apply `natalie-delegate` criteria when deciding.

## Phase 1 — Plan

Before searching the web:

1. **Clarify the goal** — what is the research question? What depth is needed? What does a good result look like?
2. **Check the vault first** — call `memory_search` (and `document_list` if a reference document might already exist) to find what is already known
3. **Assess sufficiency** — if existing vault content covers the goal adequately, surface it instead of running a web search; if it is present but insufficient in depth, scope the search to fill only the gap

Do not research what is already known.

## Phase 2 — Search

Run web search iteratively:

- Each round targets a **specific sub-question or angle** of the research goal — do not combine all terms into a single broad query
- After each round, evaluate whether the goal has been met or whether additional angles remain
- **Stop when the goal is met** or when successive rounds return substantially the same sources (diminishing returns)

## Phase 3 — Synthesise

Before storing anything:

- Extract key facts and conclusions
- Identify key sources worth preserving
- Draft a short summary narrative (two to five sentences)

**Do not store raw search results.** Everything stored in the vault must be synthesised. A list of URLs is not a research output.

## Phase 4 — Store

Apply the routing map from `natalie-memory`:

| Output type               | Tool              | Notes                                                    |
|---------------------------|-------------------|----------------------------------------------------------|
| Key source / reference    | `document_file`   | One entry per source; provide a thorough `description`   |
| Fact, conclusion, insight | `memory_store`    | One call per distinct finding                            |
| Summary note              | `note_write`      | Store in `Research/` or an appropriate vault directory   |

Complete all storage before producing the handoff brief.

## Phase 5 — Handoff

After all vault storage is complete, produce a brief stating:

- **Goal and scope** — what was researched
- **What was stored** — count of memories, documents, and notes created
- **Where it lives** — exact vault paths or note titles for each output

If running as `natalie-assistant`, return this brief to Natalie. If running inline, surface it to Simon.
