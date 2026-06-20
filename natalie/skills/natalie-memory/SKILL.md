---
name: natalie-memory
description: >
  Full information lifecycle for the vault: when to store, where to store
  (routing map), how to retrieve effectively, and how to recover from sparse
  results. The routing map here is the authoritative reference for all vault
  storage decisions, including natalie-research.
---

## Storage Routing Map

Route information to the correct vault store based on its nature. Do NOT use
`memory_store` as a catch-all — it is correct only for episodic facts and decisions.

| Information type                        | Tool              | When to use                                          |
|-----------------------------------------|-------------------|------------------------------------------------------|
| Recurring rule or preference            | `convention_add`  | Something Simon wants applied consistently           |
| Fact about a specific person            | `contact_update`  | Detail about a named person Simon knows              |
| Episodic fact, decision, or insight     | `memory_store`    | Something that happened, was decided, or was learned |
| Reference artifact (PDF, report, doc)   | `document_file`   | A file that already exists in the vault              |
| User-readable structured note           | `note_write`      | Output Simon will navigate to and read directly      |

**If the information fits more than one category**, prefer the most specific:
- A person's recurring preference → `contact_update` (not `convention_add`)
- A decision Simon made → `memory_store` (not `note_write`)
- A document mentioned but not yet filed → `memory_store` a fact about it; use `document_file` only once the file exists in the vault

## When to Store

**Store when:**
- Simon explicitly asks to remember something ("note that…", "remember…")
- A decision is made with reasoning that should survive this session
- A recurring preference or rule is identified for the first time
- A fact about a person is mentioned that is not already in their contact card

**Do NOT store when:**
- The information is already in the vault — search first; do not duplicate
- The context is transient and has no value beyond this exchange
- Simon can trivially reproduce the fact (a number he just calculated, his own name)

When in doubt: search first with `memory_search` or `contact_get`, then store only if absent or materially different.

## Retrieval Strategy

Choose retrieval tools based on what is being asked. Do NOT call retrieval tools on every
message — only when the query requires vault context to answer correctly.

| Query type                                  | Primary tool       | Secondary tool  |
|---------------------------------------------|--------------------|-----------------|
| Question about a specific person            | `contact_get`      | `memory_search` |
| Question about a past decision or event     | `memory_search`    | —               |
| Starting a task with a known workflow type  | `convention_list`  | `memory_search` |
| "What did we say about X?"                  | `memory_search`    | `note_list`     |
| Browsing vault structure                    | `note_list`        | —               |
| Finding a filed document                    | `document_list`    | —               |

**When to retrieve:** when the query concerns past events, person details, established
preferences, or prior decisions. Not for general knowledge or questions about the external world.

## Sparse-Results Recovery

When a retrieval query returns insufficient results, attempt recovery before concluding nothing exists:

1. **Widen terms** — retry with broader synonyms or remove restrictive qualifiers
2. **Try one alternate store** — if `memory_search` returns nothing, try `note_list` for a relevant directory; if looking for a person, try `contact_search` instead of `contact_get`

**Stop after two steps.** If both the original and widened queries fail, the vault does not
contain the information. Proceed accordingly and let Simon know if relevant.
