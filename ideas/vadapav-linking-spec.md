# Vadapav — Linking UX Implementation Spec
**For:** Antigravity  
**Project:** Vadapav (local-first, block-based note-taking app)  
**Stack:** PyTauri backend · Svelte frontend · `.jnote` file format  

---

## 1. Overview

This document specifies the complete UX and implementation requirements for the **interlinking system** in Vadapav. The goal is to let users create links between notes and blocks without ever seeing or manually typing the raw link syntax. All three interaction pathways described below must be keyboard-navigable end-to-end.

---

## 2. The Underlying Syntax (Backend Contract)

The `.jnote` file format uses the following raw syntax for links:

```
[[ display text || type || id ]]
```

| Field | Description |
|---|---|
| `display text` | Human-readable label shown in the pill |
| `type` | Either `note` or `block` |
| `id` | The UUID of the target entity |

**The user must never see or manually write this syntax.** The Svelte frontend is solely responsible for constructing and injecting it, and for rendering it visually as a pill.

---

## 3. Core Principles

- **Keyboard-first, mouse-supported.** Every interaction pathway must be completable without a mouse. No step should require a click.
- **Type-agnostic search.** Users search by name only. They never select a "type" (note vs. block) upfront.
- **Single, consistent modal.** All linking flows converge on the same centered search modal. This is consistent with the existing global search experience in the app.
- **Zero syntax exposure.** The raw `[[ ... ]]` string is only ever written to the `.jnote` file. The editor always renders it as a pill.

---

## 4. The Link Pill (Rendered Output)

When a link is present in the `.jnote` file, the editor must render it as a styled inline pill — never as raw text.

**Pill states:**

| State | Appearance |
|---|---|
| Default | Styled chip with display text; visually distinct from surrounding prose |
| Hover | Cursor changes to pointer; subtle highlight or tooltip showing target name |
| Broken (target deleted) | Pill is removed from the editor entirely; the raw syntax string is also cleaned up from the `.jnote` file |
| Renamed target | No change — links are stored by ID, so renames are transparent |

**Important:** When a linked note or block is deleted, the cleanup logic must remove the entire `[[ ... ]]` string from the `.jnote` file, not leave behind orphaned syntax or an empty pill.

---

## 5. Interaction Pathways

There are three ways to trigger the link modal. All three open the same modal component.

### 5.1 Keyboard Trigger — `[[`

The primary flow for power users.

1. User types `[[` in the editor.
2. A `keydown` listener detects the second `[`.
3. The link modal opens immediately (centered, full focus trap).
4. The `[[` characters are held in a pending state — they are **not** committed to the document yet.
5. On modal confirm → the `[[` is replaced with the constructed link syntax.
6. On modal dismiss (`Escape`) → the `[[` characters are either removed or left as plain text (decide on one behaviour and make it consistent).

### 5.2 Highlight Trigger — Select Text → Link Button

For users who write first and link after.

1. User selects a range of text in the editor.
2. A small floating toolbar appears above the selection (existing pattern if available, or new minimal toolbar).
3. The toolbar contains a **Link** button (icon sufficient, no label needed).
4. Clicking the Link button (or pressing a keyboard shortcut if one is assigned) opens the link modal.
5. The selected text is:
   - Pre-populated as the **search query** in the modal input field.
   - Used as the **display text** in the final pill regardless of what search query the user ends up running.
6. If the highlighted text exceeds **60 characters**, truncate the pre-populated search query to 60 characters. The full highlighted text is still used as the pill display text.
7. On modal confirm → the selected text is replaced with the rendered pill.
8. On modal dismiss → the selection is preserved as plain text, no change.

### 5.3 Fallbacks (Discoverable)

- **Navigation bar:** A Link icon in the top bar opens the modal. Since no text is selected, the modal opens with an empty search field and inserts the pill at the current cursor position on confirm.
- **Right-click context menu:** A "Link…" option in the editor's context menu. Behaviour identical to the nav bar trigger if no text is selected; identical to the highlight trigger if text is selected.

---

## 6. The Link Modal

### 6.1 Layout & Positioning

- Centered in the viewport (not anchored to the cursor or selection).
- Appears as a floating modal with a backdrop overlay.
- Width: approximately 560–640px. Should feel like the existing global search modal.
- The input field receives focus automatically on open.

### 6.2 Default State — Omni-Search

The modal opens in global omni-search mode by default.

- Single search input at the top.
- As the user types, the backend is queried for **both notes and blocks** simultaneously.
- Results are displayed in a single grouped list:
  - **Notes** group first
  - **Blocks** group second
- Each result shows the entity name and enough context to disambiguate (e.g., for a block: the parent note name as a subtitle).
- Keyboard navigation: `↑` / `↓` to move through results, `Enter` to confirm, `Escape` to dismiss.

### 6.3 Drill-Down State — Note-Scoped Search

If the user wants to link a specific block within a specific note:

1. Navigate to a **Note** result in the list using arrow keys.
2. Press `>` to enter drill-down mode.
3. The modal shifts state:
   - The search input is cleared.
   - A breadcrumb appears at the top of the modal, e.g.: `Meeting Notes >` indicating the user is now scoped inside that note.
   - The list now shows only the blocks belonging to that note.
4. The user can type to filter the blocks by name.
5. Press `Backspace` on an empty search input (or `Escape` once) to return to the global omni-search state. Pressing `Escape` again from the global state dismisses the modal entirely.

**State summary:**

```
[Modal open] → Omni-search
  → Press > on a Note result → Note-scoped block search
    → Backspace (empty input) or Escape → Omni-search
      → Escape → Modal closed
```

### 6.4 On Confirm

When the user presses `Enter` on a result:

1. Extract: display text, entity type (`note` or `block`), entity ID.
2. Construct the raw syntax string: `[[ display text || type || id ]]`
3. Write this string to the `.jnote` file at the correct position.
4. Render the pill immediately in the editor.
5. Close the modal and return cursor focus to the editor, positioned after the new pill.

---

## 7. URL / Hyperlink Handling

The same `[[` trigger should also support linking to external URLs. The parser must distinguish between an internal link and a hyperlink based on the content of the search field.

**Detection rule:** If the text in the search input matches a URL pattern, treat it as an external hyperlink instead of triggering a backend search.

URL patterns to detect:
- Standard URLs with protocol: `https://...`, `http://...`
- Bare domains: `google.com`, `sub.domain.org`
- URLs with paths, query strings, and fragments

**Behaviour when a URL is detected:**
- The results list is replaced with a single option: **"Link to [url]"** (or similar affordance).
- The user can confirm to insert an external hyperlink pill.
- The underlying syntax for hyperlinks should be determined by the backend contract (this may differ from the internal link syntax — confirm with backend team).

**Bare domain handling:** `google.com` should be normalised to `https://google.com` before storing.

---

## 8. Edge Cases & Error States

| Scenario | Expected Behaviour |
|---|---|
| No results found | Show a friendly empty state: "No notes or blocks found." Do not show an error. |
| Backend query fails | Show a transient error message in the modal. Allow the user to retry or dismiss. |
| Target note/block deleted after link is created | Remove the pill from the editor and clean the raw syntax from the `.jnote` file. |
| Target note/block renamed | No change needed — links reference the ID, not the name. |
| Highlighted text is very long (>60 chars) | Truncate the pre-filled search query. Keep full text as pill display text. |
| User types `[[` then immediately presses Escape | Remove the `[[` characters and return to normal editing state. |
| Modal opened via nav bar with no cursor position | Insert the pill at the end of the current focused block, or prompt the user to click a position first. |
| Duplicate entity names | Show full context (e.g. parent note name, creation date) in the result subtitle to help the user disambiguate. |

---

## 9. Keyboard Shortcut Summary

| Action | Key |
|---|---|
| Trigger link modal | `[[` |
| Move through results | `↑` / `↓` |
| Confirm selection | `Enter` |
| Enter drill-down (note → blocks) | `>` |
| Exit drill-down / back to global search | `Backspace` (empty input) or `Escape` |
| Dismiss modal entirely | `Escape` (from global state) |

---

## 10. Frontend Implementation Notes

### Event Listening
- Attach a `keydown` listener to the editor container to detect the `[[` sequence.
- The trigger should fire on the second `[` keypress.
- Ensure the listener does not interfere with other `[` usages (e.g. Markdown, code blocks). If the user is inside a code block, suppress the link trigger.

### Modal Component
- The modal should be a single Svelte component managing both the omni-search and drill-down states internally.
- Use a state enum or flag: `{ mode: 'global' | 'scoped', scopedNoteId: string | null }`.
- The modal must implement a **focus trap** — tab and arrow keys must not escape the modal while it is open.

### Backend Queries
- Global search: query both notes and blocks in a single call if the API supports it, or fire two parallel calls and merge results client-side.
- Scoped search: query blocks filtered by `noteId`.
- Debounce search queries by ~150ms to avoid hammering the backend on every keystroke.

### `.jnote` File Writes
- The raw `[[ ... ]]` string is written to the file; the editor renders the pill over it.
- Ensure the write operation is atomic with the cursor repositioning — there should be no flash of raw syntax in the editor.

### Cleanup on Deletion
- Whenever a note or block is deleted, the backend or a background process must scan for any `[[ ... || ... || deleted-id ]]` strings across all `.jnote` files and remove them.
- This should happen silently with no user-facing notification unless a significant number of links are affected.

---

## 11. Out of Scope (This Ticket)

- Backlinks panel (viewing what links to a given note)
- Link previews on hover (showing a snippet of the target)
- Drag-and-drop linking
- Any changes to the `.jnote` schema beyond what is described here
