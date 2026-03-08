# Sushi — Search Implementation Spec
**For:** Antigravity  
**Project:** Sushi (local-first, block-based note-taking app)  
**Stack:** PyTauri backend · Svelte frontend · GraphDB + FAISS block embeddings  

---

## 1. Overview

This document specifies the full implementation of the global search modal in Sushi. The current modal is a visual placeholder. This spec covers the backend query architecture, the two-tier search model, the frontend interaction design, and all edge cases.

The search modal is triggered via the existing UI (nav bar icon, keyboard shortcut). The same modal component is also reused for the linking flow — refer to the **Linking UX Spec** for that context. This document covers search as a standalone feature.

---

## 2. The Two-Tier Search Model

Search is split into two tiers with different speeds, data sources, and use cases. The user is never forced to choose a tier upfront — Tier 1 runs by default and Tier 2 is surfaced as an escape hatch.

| | Tier 1 — Fast Search | Tier 2 — Deep Search |
|---|---|---|
| **Trigger** | Automatic, as the user types | User presses `Tab`, or clicks "Deep search", or auto-prompted on zero results |
| **Data source** | Note titles + first line of each block | FAISS embeddings (one per block) in GraphDB |
| **Latency target** | < 30ms | 200–600ms (acceptable, show loader) |
| **Match type** | Keyword / fuzzy | Semantic similarity |
| **Best for** | "I know what I called it" | "I remember the idea, not the words" |
| **Result unit** | Note or block | Block (with parent note context) |

---

## 3. Backend API

### 3.1 Tier 1 — Fast Search

**PyTauri command:** `search_fast`

**Input:**
```json
{ "query": "string", "limit": 10 }
```

**Behaviour:**
- Query against an in-memory or SQLite FTS5 index.
- Index covers: note titles (primary signal) and the first line of each block (secondary signal).
- Do **not** index full block text in this tier — that is Tier 2's job.
- Return results ranked by match quality (title match > first-line match).

**Output:**
```json
{
  "results": [
    {
      "type": "note",
      "note_id": "uuid",
      "note_title": "Meeting Notes — March",
      "snippet": null
    },
    {
      "type": "block",
      "block_id": "uuid",
      "block_snippet": "Plain text, first 120 characters of block content, markdown stripped",
      "note_id": "uuid",
      "note_title": "Meeting Notes — March"
    }
  ]
}
```

**Notes:**
- Strip markdown syntax from `block_snippet` before returning — the frontend displays plain text in result rows.
- Cap results at 10 items total. If there are more than 10 matches, prioritise note title matches over block first-line matches.

---

### 3.2 Tier 2 — Deep Search

**PyTauri command:** `search_deep`

**Input:**
```json
{ "query": "string", "limit": 10 }
```

**Behaviour:**
- Embed the query string using the same model used to generate block embeddings.
- Run a FAISS nearest-neighbour search against the block embedding index in GraphDB.
- Enrich the raw `(block_id, score)` results by joining against block content and parent note metadata before returning.
- The frontend must never need to make a second call to resolve block or note details.

**Output:**
```json
{
  "results": [
    {
      "block_id": "uuid",
      "block_snippet": "Plain text, first 120 characters of block content, markdown stripped",
      "note_id": "uuid",
      "note_title": "Meeting Notes — March",
      "score": 0.91
    }
  ]
}
```

**Notes:**
- Do not return the raw `score` to the frontend UI — it is used only internally for ranking. Do not show confidence percentages to the user.
- Results are always at the block level. Never aggregate to note level for Tier 2 — the value is in the precision.
- Cap at 10 results.

---

### 3.3 Index Freshness

- The Tier 1 index (FTS5 or in-memory) must update whenever a note or block is created, renamed, or deleted. This should happen synchronously on write.
- FAISS block embeddings are presumably generated on block creation/edit already. Confirm the existing pipeline handles re-embedding on block content changes.

---

## 4. Frontend — Modal Behaviour

### 4.1 Modal Structure

The modal is centered in the viewport with a backdrop overlay. It is the same component already built for global search, extended with the two-tier logic described here.

```
┌─────────────────────────────────────────┐
│  🔍  Search anything...          [esc]  │
├─────────────────────────────────────────┤
│                                         │
│  NOTES                                  │
│    Meeting Notes — March                │
│    Project Plan Q2                      │
│                                         │
│  BLOCKS                                 │
│    "the block snippet text here..."     │
│    Meeting Notes — March          ↗     │
│                                         │
├─────────────────────────────────────────┤
│  [tab] deep search   [↑↓] navigate      │
│  [↵] open           [esc] close         │
└─────────────────────────────────────────┘
```

### 4.2 Default State (Modal Opens, No Query)

- Show recent searches (as currently mocked in the placeholder UI).
- Recent searches are stored locally (in-app state or a small local file — not synced).
- Maximum 5 recent searches shown.
- Keyboard hint bar at the bottom: `esc to close` · `↵ to select`.

### 4.3 Tier 1 Active State (User Is Typing)

- Fire `search_fast` with a **150ms debounce** after the user stops typing.
- Replace the recent searches list with live results.
- Results are grouped into two sections: **Notes** and **Blocks**.
  - Multiple blocks from the same note are grouped under a single note header row (greyed out note title, then indented block snippets below).
- Keyboard navigation: `↑` / `↓` moves through individual results. Group headers are not selectable.
- Keyboard hint bar updates to: `tab for deep search` · `↑↓ to navigate` · `↵ to open` · `esc to close`.

### 4.4 Zero Results State (Tier 1)

- Show: "No results for [query]."
- Below it, show a prompt: **"Try deep search for semantic results →"** with a visual affordance (button or highlighted hint).
- Pressing `Tab` or clicking the prompt triggers Tier 2.

### 4.5 Tier 2 Active State (Deep Search)

- Triggered by: `Tab` keypress, clicking the deep search prompt, or clicking the deep search hint in the footer.
- Show a subtle loading indicator (spinner or animated dots) in the results area while the FAISS query runs.
- The modal header or a small badge should indicate the mode has changed: e.g., a label "Deep search" appears near the search input.
- Results replace the loading indicator once returned.
- Results are always blocks (never bare notes) in Tier 2. Display format:

```
  "block snippet text, plain, truncated to ~120 chars..."
  Parent Note Title                                   ↗
```

- A small label — "semantic match" or similar — can be shown subtly on each result to communicate why it appeared. Keep it low-contrast; it's informational, not prominent.
- Keyboard navigation and `Enter` to open behave identically to Tier 1.

### 4.6 Switching Between Tiers

- `Tab` always switches from Tier 1 → Tier 2 (and re-runs the current query through FAISS).
- There is no keyboard shortcut to switch back from Tier 2 → Tier 1. The user can clear and retype their query, which defaults back to Tier 1.
- If the user edits their query while in Tier 2, the mode resets to Tier 1 (since the query changed, we run fast search again first).

### 4.7 On Confirm (`Enter`)

- For a **note result**: open that note in the editor.
- For a **block result**: open the parent note and scroll to / highlight the matching block.
- Log the query to recent searches.
- Close the modal.

---

## 5. Result Display Rules

### Grouping

- In Tier 1, if multiple blocks from the same note match, group them visually under the note's title as a non-selectable header. Each block is its own selectable row.
- In Tier 2, results are shown as a flat list ordered by FAISS score (highest first). No grouping — block-level precision is the point.

### Snippets

- All block snippets must have markdown stripped before display (no `**bold**`, `# headings`, backticks, etc.).
- Truncate to 120 characters maximum. Add an ellipsis if truncated.
- Do **not** highlight the matching keyword in the snippet in Tier 1 — this adds implementation complexity for little gain at this stage. Can be added later.

### Note titles

- Show as-is. If the note is untitled, show "Untitled Note" in italics.

---

## 6. Keyboard Shortcut Summary

| Action | Key |
|---|---|
| Open search modal | Existing shortcut (unchanged) |
| Close modal | `Escape` |
| Navigate results | `↑` / `↓` |
| Open selected result | `Enter` |
| Switch to deep search | `Tab` |
| Clear input | `Ctrl+A` then `Delete` (standard input behaviour) |

---

## 7. Edge Cases

| Scenario | Expected Behaviour |
|---|---|
| Query is empty | Show recent searches. Do not fire any backend query. |
| Tier 1 returns zero results | Show empty state + deep search prompt. Do not auto-trigger Tier 2. |
| Tier 2 returns zero results | Show: "Nothing found. Try different keywords." No further fallback. |
| Backend query fails (either tier) | Show: "Search unavailable. Please try again." Do not crash the modal. Allow retry. |
| Query is a single character | Still fire Tier 1, but expect low-quality results. No special handling needed. |
| User types very fast | Debounce at 150ms. Only the final settled query fires a request. |
| Note has no title | Display as "Untitled Note" in italics throughout all result rows. |
| Block has no content (empty block) | Exclude from both Tier 1 and Tier 2 results. |
| FAISS index is stale (block deleted) | Backend should guard against returning block_ids that no longer exist. If a stale ID slips through, frontend should degrade gracefully — show the result without a snippet rather than crashing. |
| Very long note title | Truncate at 60 characters with ellipsis in result rows. |

---

## 8. Out of Scope (This Ticket)

- Search within the linking modal (covered in the Linking UX Spec)
- Filtering results by date, tag, or note type
- Full-text keyword search across entire block content in Tier 1 (can be added later via FTS5 if needed)
- Search result highlighting / keyword bolding within snippets
- Syncing recent searches across devices
