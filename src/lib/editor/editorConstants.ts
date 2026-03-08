/**
 * editorConstants.ts
 * ==================
 * Shared constants and data definitions used by the note editor.
 * Extracted from MainArea.svelte to keep the component focused on
 * rendering and interaction logic.
 */

// ── Timing Constants ─────────────────────────────────────────────────────

/** Delay before clearing toolbar focus (lets toolbar button clicks fire first) */
export const FOCUS_BLUR_DELAY_MS = 150;

/** Delay before scrolling to a linked block after navigation */
export const NAVIGATE_SCROLL_DELAY_MS = 150;

// ── LaTeX Toolbar Snippets ──────────────────────────────────────────────

export interface LatexSnippet {
    label: string;
    title: string;
    snippet: string;
    sep?: boolean;
}

export const latexSnippets: LatexSnippet[] = [
    { label: "√", title: "Square root", snippet: "\\sqrt{}" },
    { label: "½", title: "Fraction", snippet: "\\frac{}{}" },
    { label: "∫", title: "Integral", snippet: "\\int_{a}^{b}" },
    { label: "Σ", title: "Summation", snippet: "\\sum_{i=1}^{n}" },
    { label: "lim", title: "Limit", snippet: "\\lim_{x \\to \\infty}" },
    { label: "", title: "", snippet: "", sep: true },
    { label: "x²", title: "Superscript", snippet: "^{}" },
    { label: "x₂", title: "Subscript", snippet: "_{}" },
    {
        label: "⊞",
        title: "Matrix (2×2)",
        snippet: "\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}",
    },
    { label: "", title: "", snippet: "", sep: true },
    { label: "α", title: "Alpha", snippet: "\\alpha" },
    { label: "β", title: "Beta", snippet: "\\beta" },
    { label: "π", title: "Pi", snippet: "\\pi" },
    { label: "θ", title: "Theta", snippet: "\\theta" },
    { label: "∞", title: "Infinity", snippet: "\\infty" },
];
