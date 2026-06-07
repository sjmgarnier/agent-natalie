---
name: natalie-contact-enrichment
description: >
  Create or enrich a Natalie contact card for a person mentioned in context.
  Invoke proactively at natural pause points when an unfamiliar person appears.
  When invoking proactively (not in direct response to a user request), pass
  `auto` as the argument to suppress output when the card is already complete.
---

# Contact Card Creation and Enrichment

Create or enrich a contact card in the Natalie vault for a specific person.

## Invocation modes

**User-initiated** (`/natalie-contact-enrichment`): Announce findings; ask before
each significant action; offer to enrich even if the card is already complete.

**Agent-initiated** (`/natalie-contact-enrichment auto`): Exit silently if the card
is already complete. Otherwise proceed identically to user-initiated.

> If you are invoking this skill yourself because you spotted an unfamiliar person
> in context, pass `auto`. Do not add `auto` if the user explicitly requested it.

## Target fields

Aim to populate: `name`, `email`, `organization`, `title`, `website`, `linkedin`,
`phone`, `location`, and the freeform `content` body (relationship context, notes,
how you know this person).

## Steps

### 1. Identify seed

Extract a seed — full name, email address, URL, or any reference to a specific
person — from the invocation context. If nothing is visible, ask:

> "Who would you like to create a contact card for?"

### 2. Look up existing card

Derive the expected slug: `firstname-lastname`, lowercase, hyphenated, ASCII only
(e.g. `john-smith`). Call `contact_list` to enumerate all existing slugs and find
the closest match, then call `contact_get` with that slug.

### 3. Gap analysis

Compare the existing card (or empty state if no card) against the target fields.

- **No card exists** → all fields are gaps; proceed to Step 4.
- **Gaps found** → proceed to Step 4.
- **Card complete, user-initiated** → say "This contact card looks complete. Would
  you like me to enrich it further anyway?" Exit if the user declines.
- **Card complete, auto-initiated** → exit immediately, no output.

### 4. Context harvest

Scan the surrounding conversation for data that is already visible: email addresses
in thread headers, job titles in introductions, URLs in signatures. Record what you
find without asking the user.

### 5. Quick questions

Ask the user one or two short questions for gaps that are easy to answer and
unlikely to be found by web search (e.g. a personal phone number, an informal role
description). Keep this to two questions at most; do not ask about things you can
find online.

### 6. Web search — round 1

Search for the person using the seed and all harvested context. Present findings
with source URLs. When results are ambiguous (more than one plausible match), ask
the user to confirm identity before proceeding:

> "I found a John Smith who is a Professor of Computer Science at NJIT
> (https://cs.njit.edu/people/john-smith). Is this the right person?"

Do not record any result until the user confirms the identity.

### 7. Web search — round 2

Using the now-confirmed identity, run a more targeted search to fill remaining
gaps. Present the full proposed field set for user review before writing anything:

> "Here is what I would like to save:
> - name: John Smith
> - email: john.smith@njit.edu
> - organization: NJIT
> - title: Professor of Computer Science
> - website: https://cs.njit.edu/people/john-smith
> - linkedin: https://linkedin.com/in/johnsmithnjit
>
> Shall I create the card?"

### 8. Additional rounds

Do not run further searches on your own. If the user asks for another round,
repeat Steps 6–7 with any new query terms the user provides.

### 9. Write the card

Call `contact_update` with the vetted data:

```
contact_update(
    slug="john-smith",
    fields={
        "name": "John Smith",
        "email": "john.smith@njit.edu",
        "organization": "NJIT",
        "title": "Professor of Computer Science",
        "website": "https://cs.njit.edu/people/john-smith",
        "linkedin": "https://linkedin.com/in/johnsmithnjit",
        "content": "Researcher in neural architecture search. Met at AI conf 2025."
    }
)
```

**Slug collision:** If `firstname-lastname` already belongs to a different person,
say so and ask the user to choose a disambiguated slug (e.g. `john-smith-njit`).
