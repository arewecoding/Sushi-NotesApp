# Vadapav — Code Block Upgrade Spec
**For:** Antigravity  
**Project:** Vadapav (local-first, block-based note-taking app)  
**Stack:** PyTauri backend · Svelte frontend · `.jnote` file format  

---

## Overview

This document specifies a full upgrade to the code block experience in Vadapav. The current code block uses a basic editor and needs to be replaced entirely. The preferred implementation is **CodeMirror 6** as the editor foundation — it handles the majority of requirements below natively and should replace the current code block editor entirely, not be bolted on top of it.

---

## Requirement 1 — Tab and Exit Key Behaviour

**Current problem:** Pressing `Tab` inside a code block moves focus out of the block entirely, which breaks normal coding habits.

**Fix:**
- `Tab` must insert indentation at the cursor position — **2 spaces**. It must never move focus out of the block.
- `Shift+Tab` must remove one indent level (2 spaces) from the current line.
- To exit the code block with the keyboard, the user presses **`Escape`**. This is the standard convention used by CodeMirror, VS Code embedded editors, and Notion. It is preferred over `Ctrl+Tab` (conflicts with browser tab switching).
- After pressing `Escape`, focus should return to the block-level navigation, consistent with how focus is handled across other block types in Vadapav.

---

## Requirement 2 — Native Coding Behaviour

The code block must feel like a real lightweight code editor. Beyond Tab, implement the following behaviours:

| Action | Behaviour |
|---|---|
| `Tab` | Insert 2 spaces at cursor |
| `Shift+Tab` | Remove one indent level (2 spaces) from current line |
| `Enter` | Auto-indent to match the current line's indentation level |
| `(`, `[`, `{`, `"`, `'` | Auto-insert the matching closing character |
| Cursor style | Blinking line caret — not a block cursor |

All of the above are available as native CodeMirror 6 extensions. Use the built-in packages rather than implementing custom logic.

---

## Requirement 3 — Syntax Highlighting by Language

The code block must support syntax highlighting based on a user-selected language.

**Language selector:**
- A language label/dropdown is attached to the top of the code block.
- The user can click it to change the language at any time.
- The selected language is stored in the `.jnote` file alongside the block content and persists across sessions.
- If no language is selected, default to **Plaintext**.

**Supported languages for this ticket:**

| Label | CodeMirror Package |
|---|---|
| Plaintext / Pseudocode | (no highlighting, monospace only) |
| Python | `@codemirror/lang-python` |
| JavaScript | `@codemirror/lang-javascript` |
| SQL | `@codemirror/lang-sql` |
| Rust | `@codemirror/lang-rust` |
| Go | `@codemirror/lang-go` |
| HTML | `@codemirror/lang-html` |
| CSS | `@codemirror/lang-css` |

Use CodeMirror 6's first-party language packages for all of the above. Do not build a custom highlighter.

**Theme:** The syntax highlighting theme must match Vadapav's dark UI. Use CodeMirror's `oneDark` theme as the base, or a custom theme that fits the existing app palette. Do not use a light theme.

---

## Requirement 4 — Language Auto-Detection on Paste

When a user pastes code into a code block that currently has no language set (i.e. it is on Plaintext), make a best-effort attempt to detect the language automatically and set it.

- This only triggers on paste into an empty or Plaintext block — it must never override a language the user has already set manually.
- It does not need to be perfect. Common cases (Python, JavaScript, SQL, HTML) should be detectable from syntax patterns.
- If detection confidence is low, leave the language as Plaintext rather than guessing wrong.
- The auto-detected language can be changed by the user at any time via the language selector.

---

## Requirement 5 — Line Numbers and Active Line Highlight

These are both single configuration options in CodeMirror 6 and should be enabled by default.

- **Line numbers:** Show line numbers in the left gutter. Always visible.
- **Active line highlight:** The line the cursor is currently on gets a subtle background tint to make it easy to track position. The tint should be low contrast — visible but not distracting.

---

## Requirement 6 — Copy Button

A copy button must be permanently visible in the top-right corner of every code block.

**Behaviour:**
- Always visible — not just on hover.
- Copies the raw code content to the clipboard as plain text with no syntax markup, no HTML, and no leading or trailing whitespace.
- After clicking, the button shows a confirmation state (checkmark icon or "Copied" label) for **1.5 seconds**, then returns to its default state.
- The button must not interfere with the code editing area or overlap any text.

---

## Requirement 7 — Height Cap with Internal Scroll

Long code blocks must not push the rest of the note content arbitrarily far down the page.

- Cap the visible height of a code block at **400px**.
- If the code content exceeds this height, the block scrolls internally (the code block itself scrolls, not the page).
- The full code is always present — this is a display cap, not a content truncation.
- Short code blocks (under 400px) render at their natural height with no scrollbar.

---

## Requirement 8 — Collapse Toggle

Each code block has a collapse toggle — a small chevron (`›`) in the top-left corner of the block, next to the language label.

**Behaviour:**
- **Expanded (default):** Full code block is visible.
- **Collapsed:** The block folds down to a single bar showing the language label and the first line of code as a preview, truncated with an ellipsis if necessary.
- Clicking the chevron toggles between states.
- The collapsed/expanded state does not persist between sessions — all blocks open expanded by default on load.
- The collapse toggle must not interfere with the language selector or the copy button.

**Collapsed state layout:**
```
› Python   def calculate_total(items):...         [copy]
```

---

## What Good Looks Like

The code block should feel indistinguishable from a lightweight embedded code editor within a notes app. The user should never feel like they are fighting the editor. Reference implementations to study:

- **VS Code notebook code cells** — tab behaviour, line numbers, active line highlight
- **Notion code blocks** — copy button, language selector, collapse
- **Typora** — overall philosophy of staying out of the user's way

---

## Implementation Notes

- All requirements should be implemented in a single pass. Requirements 1, 2, and 5 all touch the same CodeMirror configuration — implement them together to avoid conflicts.
- The CodeMirror instance must be properly destroyed and re-initialised when a block is removed from the DOM to avoid memory leaks.
- The language selection and block content must both be written to the `.jnote` file on every change. Confirm the existing block save mechanism handles additional metadata fields, or add support for it.

---

## For Each Requirement, Please Provide

- A brief explanation of the approach taken.
- Any decisions made where the spec left room for interpretation.
- Any known limitations or follow-up work flagged for later.
