---
name: natalie-delegate
description: >
  Teaches Natalie when and how to delegate tasks to natalie-assistant.
  Covers suitability criteria, delegation brief format, completion
  verification, and failure fallback.
---

# Delegation to natalie-assistant

Natalie can delegate tasks to **natalie-assistant**, a background subagent with full access to natalie MCP tools. Use delegation to offload work that would otherwise consume your main context or block the user unnecessarily.

## When to delegate

Delegate when **all three** of the following are true:

- **Complexity or duration**: the task involves multiple steps, external lookups, or long-running work (filing, research, enrichment, synthesis)
- **Parallelisability**: the task does not require back-and-forth with Simon mid-way through
- **Specifiability**: you can write a complete, unambiguous brief right now

Do **not** delegate when:

- The task is **critical or irreversible** and the assistant's output must be reviewed before any action is taken — complete it inline, then show Simon the result
- **Uncertainty is high**: you do not know what success looks like, or the goal is open-ended enough that mid-task clarification will be needed
- **Cost-to-specify exceeds the benefit**: a two-sentence inline answer is faster than writing a five-paragraph brief

## Writing the delegation brief

The brief is the only thing natalie-assistant knows about the task — write it as if handing off to someone who cannot ask you anything.

Required elements:

1. **Goal** — what the assistant should accomplish, stated precisely
2. **Vault storage target** — where to write the result (`note_write` path, `memory_store` tag, or `document_file` title)
3. **Success criteria** — how to know the task is done (e.g., "note exists at Contacts/Enriched/Jane Doe.md with LinkedIn URL and current title")
4. **No-questions clause** — always end with: *"Do not ask for clarification. Make reasonable assumptions and document them alongside the result."*

If a natalie skill covers this task, reference it explicitly in the brief (e.g., *"Use the natalie-contact-enrichment skill."*). If no skill exists, include step-by-step instructions.

Example brief:

> Research Jane Doe (CEO at Acme, met at NeurIPS 2025). Find her current title, employer, LinkedIn URL, and any recent publications. Store results at `Contacts/Enriched/Jane Doe.md` using `note_write`. Use the natalie-contact-enrichment skill. Success: note exists with all four fields populated. Do not ask for clarification — make reasonable assumptions and document them.

## After delegation

Once natalie-assistant finishes, verify the result before summarising to Simon:

```
memory_search("Jane Doe enrichment")       # confirm memory was stored
note_read("Contacts/Enriched/Jane Doe.md") # confirm note exists and is complete
```

Then give Simon a brief summary: what was stored, where it lives, and any assumptions the assistant documented.

## Failure fallback

If natalie-assistant returns nothing useful, or the vault shows no trace of the expected output:

1. Complete the task inline yourself
2. Tell Simon: "I delegated this to natalie-assistant but the result was missing — I've completed it directly."

Do not silently drop a failed delegation.
