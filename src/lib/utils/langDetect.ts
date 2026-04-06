/**
 * langDetect.ts
 * =============
 * Lightweight regex-based language auto-detection for pasted code.
 * Returns the best-guess language ID or "plaintext" if confidence is low.
 */

interface LangPattern {
    lang: string;
    patterns: RegExp[];
    weight?: number;
}

const LANG_PATTERNS: LangPattern[] = [
    {
        lang: "python",
        patterns: [
            /\bdef\s+\w+\s*\(/,
            /\bimport\s+\w+/,
            /\bfrom\s+\w+\s+import\b/,
            /\bclass\s+\w+.*:/,
            /\belif\b/,
            /\bprint\s*\(/,
            /^\s*#.*$/m,
            /\bself\./,
        ],
    },
    {
        lang: "javascript",
        patterns: [
            /\bconst\s+\w+\s*=/,
            /\blet\s+\w+\s*=/,
            /\bfunction\s+\w+\s*\(/,
            /=>\s*[{(]/,
            /\bconsole\.\w+\(/,
            /\bexport\s+(default\s+)?/,
            /\brequire\s*\(/,
            /\basync\s+function\b/,
        ],
    },
    {
        lang: "sql",
        patterns: [
            /\bSELECT\s+/i,
            /\bFROM\s+/i,
            /\bINSERT\s+INTO\b/i,
            /\bCREATE\s+TABLE\b/i,
            /\bWHERE\s+/i,
            /\bJOIN\s+/i,
            /\bALTER\s+TABLE\b/i,
            /\bGROUP\s+BY\b/i,
        ],
        weight: 1.5, // SQL keywords are distinctive
    },
    {
        lang: "html",
        patterns: [
            /<!DOCTYPE\s+html/i,
            /<html[\s>]/i,
            /<div[\s>]/i,
            /<\/\w+>/,
            /<meta\s/i,
            /<link\s/i,
            /<body[\s>]/i,
        ],
    },
    {
        lang: "css",
        patterns: [
            /\{\s*(color|margin|padding|display|font-size|background)\s*:/,
            /@media\s/,
            /\.([\w-]+)\s*\{/,
            /#([\w-]+)\s*\{/,
            /@import\s/,
            /@keyframes\s/,
        ],
    },
    {
        lang: "rust",
        patterns: [
            /\bfn\s+\w+/,
            /\blet\s+mut\b/,
            /\bimpl\s+\w+/,
            /\bpub\s+fn\b/,
            /\buse\s+\w+::/,
            /\bstruct\s+\w+/,
            /\benum\s+\w+/,
            /->.*\{/,
        ],
    },
    {
        lang: "go",
        patterns: [
            /\bfunc\s+\w+/,
            /\bpackage\s+\w+/,
            /\bimport\s*\(/,
            /\bfmt\.\w+/,
            /\btype\s+\w+\s+struct\b/,
            /:=\s*/,
        ],
    },
];

const THRESHOLD = 2;

/**
 * Detect the likely language of a code string.
 * Returns the language ID (e.g. "python") or "plaintext" if unsure.
 */
export function detectLanguage(code: string): string {
    if (!code.trim()) return "plaintext";

    let bestLang = "plaintext";
    let bestScore = 0;

    for (const { lang, patterns, weight = 1 } of LANG_PATTERNS) {
        let score = 0;
        for (const rx of patterns) {
            if (rx.test(code)) score++;
        }
        score *= weight;
        if (score > bestScore) {
            bestScore = score;
            bestLang = lang;
        }
    }

    return bestScore >= THRESHOLD ? bestLang : "plaintext";
}
