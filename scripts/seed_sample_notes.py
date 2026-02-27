"""
scripts/seed_sample_notes.py
============================
Creates rich sample notes in the CORRECT Sushi .jnote format for testing
the GraphRAG pipeline and note-linking features.

The ACTUAL format (from inspecting real app-created notes) is:
{
  "metadata": {
    "note_id": "<uuid>",
    "title": "...",
    "created_at": "<ISO>",
    "last_modified": "<ISO>",
    "version": "1.0",
    "status": 0,
    "tags": [],
    "last_known_path": "<abs_path>"
  },
  "custom_fields": {},
  "blocks": [
    {
      "block_id": "<uuid>",
      "type": "text" | "todo" | "code",
      "data": {
        "content": "...",
        "format": "markdown"        <- required for text/todo
        "checked": false            <- only for todo
      },
      "version": "1.0",
      "tags": [],
      "backlinks": []
    }
  ]
}

File name: <slugified-title>-<first-8-chars-of-id>.jnote

Run from the project root:
    uv run python scripts/seed_sample_notes.py

Or pass a custom vault path:
    uv run python scripts/seed_sample_notes.py --vault /path/to/vault
"""

import argparse
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _uuid() -> str:
    return str(uuid.uuid4())


def _short(uid: str) -> str:
    """First 7 chars of id (no hyphens) — used for filenames."""
    return uid.replace("-", "")[:7]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(title: str) -> str:
    """Convert title to kebab-case slug."""
    s = title.lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s]+", "-", s.strip())
    s = re.sub(r"-+", "-", s)
    return s[:50]


def make_text_block(content: str, tags: list[str] | None = None) -> dict:
    return {
        "block_id": _uuid(),
        "type": "text",
        "data": {
            "content": content,
            "format": "markdown",
        },
        "version": "1.0",
        "tags": tags or [],
        "backlinks": [],
    }


def make_todo_block(content: str, checked: bool = False) -> dict:
    return {
        "block_id": _uuid(),
        "type": "todo",
        "data": {
            "content": content,
            "format": "markdown",
            "checked": checked,
        },
        "version": "1.0",
        "tags": [],
        "backlinks": [],
    }


def make_code_block(content: str) -> dict:
    return {
        "block_id": _uuid(),
        "type": "code",
        "data": {
            "content": content,
            "format": "markdown",
        },
        "version": "1.0",
        "tags": [],
        "backlinks": [],
    }


def write_note(vault: Path, title: str, blocks: list[dict]) -> tuple[str, Path]:
    """Write a .jnote file with proper format. Returns (note_id, file_path)."""
    note_id = _uuid()
    now = _now()
    filename = f"{_slug(title)}-{_short(note_id)}.jnote"
    filepath = vault / filename

    note = {
        "metadata": {
            "note_id": note_id,
            "title": title,
            "created_at": now,
            "last_modified": now,
            "version": "1.0",
            "status": 0,
            "tags": [],
            "last_known_path": str(filepath.resolve()),
        },
        "custom_fields": {},
        "blocks": blocks,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(note, f, indent=2, ensure_ascii=False)

    print(f"  Created: '{title}' → {filename}")
    return note_id, filepath


# ---------------------------------------------------------------------------
# Main seeding function
# ---------------------------------------------------------------------------


def seed(vault: Path) -> None:
    vault.mkdir(parents=True, exist_ok=True)
    print(f"Seeding sample notes into: {vault}\n")

    # ── Pass 1: pre-allocate IDs so we can cross-link ─────────────────────
    note_titles = [
        "ML Overview",
        "Neural Networks Deep Dive",
        "Transformers and Attention",
        "Training Tips and Tricks",
        "Datasets and Preprocessing",
        "Evaluation Metrics Guide",
        "My Research Notes",
        "Reading List",
    ]
    ids: dict[str, str] = {t: str(uuid.uuid4()) for t in note_titles}

    def link(display: str, target_title: str) -> str:
        """Inline [[link]] using the app's syntax."""
        return f"[[{display}|{ids[target_title]}]]"

    # ── Pass 2: write each note with real format ───────────────────────────

    # 1. ML Overview
    note_id = ids["ML Overview"]
    title = "ML Overview"
    blocks = [
        make_text_block(
            "Machine Learning (ML) is a subset of Artificial Intelligence that gives systems "
            "the ability to automatically learn and improve from experience without being "
            "explicitly programmed. It focuses on developing programs that access data and "
            "learn from it.",
            tags=["intro", "ml"],
        ),
        make_text_block(
            "There are three major learning paradigms:\n\n"
            "• **Supervised Learning** — trained on labelled examples\n"
            "• **Unsupervised Learning** — finds structure without labels\n"
            "• **Reinforcement Learning** — learns via reward signals"
        ),
        make_text_block(
            f"The workhorse of modern ML is the deep neural network. "
            f"See {link('Neural Networks Deep Dive', 'Neural Networks Deep Dive')} for a full breakdown, "
            f"and {link('Transformers and Attention', 'Transformers and Attention')} for the dominant architecture in NLP and vision today."
        ),
        make_text_block(
            f"For practical guidance: "
            f"{link('Training Tips and Tricks', 'Training Tips and Tricks')} covers optimisation, "
            f"{link('Datasets and Preprocessing', 'Datasets and Preprocessing')} covers data pipelines, "
            f"and {link('Evaluation Metrics Guide', 'Evaluation Metrics Guide')} explains how to measure success."
        ),
    ]
    filepath = vault / f"{_slug(title)}-{_short(note_id)}.jnote"
    now = _now()
    note = {
        "metadata": {
            "note_id": note_id,
            "title": title,
            "created_at": now,
            "last_modified": now,
            "version": "1.0",
            "status": 0,
            "tags": [],
            "last_known_path": str(filepath.resolve()),
        },
        "custom_fields": {},
        "blocks": blocks,
    }
    filepath.write_text(
        json.dumps(note, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  Created: '{title}' → {filepath.name}")

    # 2. Neural Networks Deep Dive
    note_id = ids["Neural Networks Deep Dive"]
    title = "Neural Networks Deep Dive"
    blocks = [
        make_text_block(
            "A neural network is a computational model loosely inspired by the human brain. "
            "It consists of layers of interconnected nodes that transform input data through "
            "learned weighted sums and non-linear activation functions.",
            tags=["neural-net", "deep-learning"],
        ),
        make_text_block(
            "**Architecture layers:**\n\n"
            "• **Input layer** — receives raw features (pixels, tokens, etc.)\n"
            "• **Hidden layers** — learn intermediate representations\n"
            "• **Output layer** — produces the final prediction\n\n"
            "**Activation functions:** ReLU, GELU, sigmoid, tanh"
        ),
        make_text_block(
            "**Backpropagation** computes gradients of the loss with respect to every weight "
            "using the chain rule, allowing gradient descent to minimise the loss iteratively. "
            "Modern optimisers like Adam and AdamW add adaptive learning rates per parameter."
        ),
        make_code_block(
            "# Simple dense layer forward pass (NumPy)\n"
            "import numpy as np\n\n"
            "def relu(x):\n"
            "    return np.maximum(0, x)\n\n"
            "def dense_forward(x, W, b):\n"
            "    return relu(x @ W + b)"
        ),
        make_text_block(
            f"Neural networks are the foundation of the "
            f"{link('Transformers and Attention', 'Transformers and Attention')} architecture. "
            f"Training them well requires the strategies in "
            f"{link('Training Tips and Tricks', 'Training Tips and Tricks')}."
        ),
    ]
    filepath = vault / f"{_slug(title)}-{_short(note_id)}.jnote"
    now = _now()
    note = {
        "metadata": {
            "note_id": note_id,
            "title": title,
            "created_at": now,
            "last_modified": now,
            "version": "1.0",
            "status": 0,
            "tags": [],
            "last_known_path": str(filepath.resolve()),
        },
        "custom_fields": {},
        "blocks": blocks,
    }
    filepath.write_text(
        json.dumps(note, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  Created: '{title}' → {filepath.name}")

    # 3. Transformers and Attention
    note_id = ids["Transformers and Attention"]
    title = "Transformers and Attention"
    blocks = [
        make_text_block(
            "The Transformer architecture (Vaswani et al. 2017, *Attention Is All You Need*) "
            "replaced recurrent networks as the dominant paradigm for sequence modelling. "
            "Its key innovation is **self-attention**, which allows every token to directly "
            "attend to every other token in the sequence.",
            tags=["transformers", "attention", "nlp"],
        ),
        make_text_block(
            "**Scaled Dot-Product Attention:**\n\n"
            "```\nAttention(Q, K, V) = softmax(QKᵀ / √dₖ) · V\n```\n\n"
            "Q (query), K (key), V (value) are linear projections of the input embeddings. "
            "**Multi-Head Attention** runs h independent attention heads in parallel and "
            "concatenates their outputs."
        ),
        make_code_block(
            "# Simplified self-attention (NumPy)\n"
            "import numpy as np\n\n"
            "def attention(Q, K, V):\n"
            "    d_k = Q.shape[-1]\n"
            "    scores = (Q @ K.T) / np.sqrt(d_k)\n"
            "    weights = np.exp(scores) / np.exp(scores).sum(-1, keepdims=True)\n"
            "    return weights @ V"
        ),
        make_text_block(
            "**Landmark models:**\n\n"
            "• BERT — bidirectional encoder, understanding tasks\n"
            "• GPT family — autoregressive decoder, generation tasks\n"
            "• T5 — unified text-to-text framework\n"
            "• Vision Transformer (ViT) — 16×16 word patches for images\n"
            "• Gemini / Claude / GPT-4 — multimodal large language models"
        ),
        make_text_block(
            f"Transformers are built on top of {link('Neural Networks Deep Dive', 'Neural Networks Deep Dive')}. "
            f"For tuning them effectively see {link('Training Tips and Tricks', 'Training Tips and Tricks')}."
        ),
    ]
    filepath = vault / f"{_slug(title)}-{_short(note_id)}.jnote"
    now = _now()
    note = {
        "metadata": {
            "note_id": note_id,
            "title": title,
            "created_at": now,
            "last_modified": now,
            "version": "1.0",
            "status": 0,
            "tags": [],
            "last_known_path": str(filepath.resolve()),
        },
        "custom_fields": {},
        "blocks": blocks,
    }
    filepath.write_text(
        json.dumps(note, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  Created: '{title}' → {filepath.name}")

    # 4. Training Tips and Tricks
    note_id = ids["Training Tips and Tricks"]
    title = "Training Tips and Tricks"
    blocks = [
        make_text_block(
            "Training deep learning models well is more art than science. "
            "Small choices — learning rate, batch size, regularisation — can have "
            "a surprisingly large effect on convergence speed and final accuracy.",
            tags=["training", "hyperparameters"],
        ),
        make_text_block(
            "**Learning Rate:**\n\n"
            "• Too high → loss diverges or oscillates\n"
            "• Too low → slow convergence, local minima\n"
            "• Best practice: **warmup** for the first ~1000 steps, then **cosine decay**\n"
            "• Cyclical LR (Smith 2017) works well for CNNs"
        ),
        make_text_block(
            "**Regularisation techniques:**\n\n"
            "• Dropout (p=0.1–0.5) — randomly zeros activations\n"
            "• Weight decay (L2) — penalises large weights; built into AdamW\n"
            "• Data augmentation — artificially increases dataset diversity\n"
            "• Early stopping — halt when validation loss plateaus\n"
            "• Label smoothing — prevents overconfident softmax outputs"
        ),
        make_text_block(
            "**Batch size effects:**\n\n"
            "• Larger batch → more stable gradients, faster GPU utilisation\n"
            "• Smaller batch → implicit regularisation, often better generalisation\n"
            "• *Linear scaling rule*: multiply LR by the same factor as batch size\n"
            "• Gradient accumulation lets you simulate large batches on limited VRAM"
        ),
        make_text_block(
            f"Good data is half the battle — see {link('Datasets and Preprocessing', 'Datasets and Preprocessing')}. "
            f"After training, check {link('Evaluation Metrics Guide', 'Evaluation Metrics Guide')} "
            f"to understand if your model is actually improving."
        ),
    ]
    filepath = vault / f"{_slug(title)}-{_short(note_id)}.jnote"
    now = _now()
    note = {
        "metadata": {
            "note_id": note_id,
            "title": title,
            "created_at": now,
            "last_modified": now,
            "version": "1.0",
            "status": 0,
            "tags": [],
            "last_known_path": str(filepath.resolve()),
        },
        "custom_fields": {},
        "blocks": blocks,
    }
    filepath.write_text(
        json.dumps(note, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  Created: '{title}' → {filepath.name}")

    # 5. Datasets and Preprocessing
    note_id = ids["Datasets and Preprocessing"]
    title = "Datasets and Preprocessing"
    blocks = [
        make_text_block(
            "The quality of your training data is arguably the most important factor in ML. "
            "'Garbage in, garbage out' — even the best architecture will fail on poorly "
            "curated data.",
            tags=["datasets", "data"],
        ),
        make_text_block(
            "**Common public datasets:**\n\n"
            "• ImageNet — 1.2M images, 1000 classes (vision benchmark)\n"
            "• MNIST / CIFAR-10 — beginner benchmarks\n"
            "• The Pile / RedPajama — large text corpora for LLMs\n"
            "• SQuAD — reading comprehension / question answering\n"
            "• GLUE / SuperGLUE — NLP benchmark suites\n"
            "• Common Crawl — raw web-scale text"
        ),
        make_text_block(
            "**Standard preprocessing pipeline:**\n\n"
            "1. Collect and deduplicate\n"
            "2. Clean (fix encoding, remove nulls, normalise whitespace)\n"
            "3. Feature engineering (tokenise, scale, encode)\n"
            "4. Split: 80% train / 10% val / 10% test\n"
            "5. Shuffle training set; keep val/test fixed\n"
            "⚠️ Compute statistics (mean, std) on **training set only** — never on val or test"
        ),
        make_text_block(
            "**Handling class imbalance:**\n\n"
            "• Oversample minority (SMOTE or random oversample)\n"
            "• Undersample majority\n"
            "• Class-weighted loss function\n"
            "• Focal loss for extreme imbalance (e.g., detection tasks)"
        ),
    ]
    filepath = vault / f"{_slug(title)}-{_short(note_id)}.jnote"
    now = _now()
    note = {
        "metadata": {
            "note_id": note_id,
            "title": title,
            "created_at": now,
            "last_modified": now,
            "version": "1.0",
            "status": 0,
            "tags": [],
            "last_known_path": str(filepath.resolve()),
        },
        "custom_fields": {},
        "blocks": blocks,
    }
    filepath.write_text(
        json.dumps(note, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  Created: '{title}' → {filepath.name}")

    # 6. Evaluation Metrics Guide
    note_id = ids["Evaluation Metrics Guide"]
    title = "Evaluation Metrics Guide"
    blocks = [
        make_text_block(
            "Choosing the right metric is critical. Optimising the wrong metric can produce "
            "a model that looks good on paper but fails silently in production.",
            tags=["evaluation", "metrics"],
        ),
        make_text_block(
            "**Classification metrics:**\n\n"
            "• **Accuracy** — proportion correct; misleading on imbalanced classes\n"
            "• **Precision** — TP / (TP + FP); of predicted positives, how many are real?\n"
            "• **Recall** — TP / (TP + FN); of real positives, how many did we find?\n"
            "• **F1** — harmonic mean of precision and recall\n"
            "• **AUC-ROC** — threshold-independent; area under the ROC curve\n"
            "• **MCC** — Matthews Correlation Coefficient; balanced for binary tasks"
        ),
        make_text_block(
            "**Regression metrics:**\n\n"
            "• **MAE** — Mean Absolute Error; robust to outliers\n"
            "• **RMSE** — Root Mean Squared Error; penalises large errors more\n"
            "• **R²** — coefficient of determination; proportion of variance explained"
        ),
        make_text_block(
            "**Generation / NLP metrics:**\n\n"
            "• **BLEU** — n-gram overlap (machine translation)\n"
            "• **ROUGE** — recall-oriented overlap (summarisation)\n"
            "• **BERTScore** — semantic similarity via embeddings\n"
            "• **Perplexity** — how well a LM predicts the test corpus"
        ),
        make_text_block(
            f"Always hold out a clean test set — see {link('Datasets and Preprocessing', 'Datasets and Preprocessing')} "
            f"for split strategies. Early stopping in {link('Training Tips and Tricks', 'Training Tips and Tricks')} "
            f"relies on the validation metric."
        ),
    ]
    filepath = vault / f"{_slug(title)}-{_short(note_id)}.jnote"
    now = _now()
    note = {
        "metadata": {
            "note_id": note_id,
            "title": title,
            "created_at": now,
            "last_modified": now,
            "version": "1.0",
            "status": 0,
            "tags": [],
            "last_known_path": str(filepath.resolve()),
        },
        "custom_fields": {},
        "blocks": blocks,
    }
    filepath.write_text(
        json.dumps(note, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  Created: '{title}' → {filepath.name}")

    # 7. My Research Notes
    note_id = ids["My Research Notes"]
    title = "My Research Notes"
    blocks = [
        make_text_block(
            "Personal scratchpad for research ideas and observations. "
            "Half-formed thoughts go here before being written up properly.",
            tags=["personal", "research"],
        ),
        make_text_block(
            f"Been deep-diving into {link('Transformers and Attention', 'Transformers and Attention')} this week. "
            f"The Q/K/V formulation finally clicked when I stopped thinking of them as separate weight "
            f"matrices and started thinking of them as three different 'views' of the same sequence."
        ),
        make_text_block(
            f"Open question: is there a better init scheme for very deep transformers? "
            f"Current wisdom from {link('Training Tips and Tricks', 'Training Tips and Tricks')} says "
            f"warmup + cosine decay, but some papers argue layer-scale (tiny per-layer multipliers) "
            f"helps more at depth."
        ),
        make_text_block(
            f"Next experiment: try a smaller LR with larger batch and see if the "
            f"{link('Evaluation Metrics Guide', 'Evaluation Metrics Guide')} F1 on my NER task improves. "
            f"Current baseline: F1=0.83 with Adam, lr=3e-4, batch=32."
        ),
        make_todo_block(
            "Read 'Scaling Laws for Neural Language Models' (Kaplan et al. 2020)"
        ),
        make_todo_block("Reproduce BERT fine-tuning on SQuAD from scratch"),
        make_todo_block("Compare MCC vs F1 on my imbalanced NER entity types"),
        make_todo_block("Try Flash Attention on the transformer experiment"),
    ]
    filepath = vault / f"{_slug(title)}-{_short(note_id)}.jnote"
    now = _now()
    note = {
        "metadata": {
            "note_id": note_id,
            "title": title,
            "created_at": now,
            "last_modified": now,
            "version": "1.0",
            "status": 0,
            "tags": [],
            "last_known_path": str(filepath.resolve()),
        },
        "custom_fields": {},
        "blocks": blocks,
    }
    filepath.write_text(
        json.dumps(note, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  Created: '{title}' → {filepath.name}")

    # 8. Reading List
    note_id = ids["Reading List"]
    title = "Reading List"
    blocks = [
        make_text_block(
            "Papers and resources I want to read, grouped by topic. "
            "Updated as I find things on arXiv or Twitter.",
            tags=["reading", "papers"],
        ),
        make_text_block(
            "**Foundational Papers:**\n\n"
            "• *Attention Is All You Need* — Vaswani et al. (2017)\n"
            "• *BERT* — Devlin et al. (2019)\n"
            "• *Language Models are Few-Shot Learners (GPT-3)* — Brown et al. (2020)\n"
            "• *Scaling Laws for Neural Language Models* — Kaplan et al. (2020)\n"
            "• *An Image is Worth 16×16 Words (ViT)* — Dosovitskiy et al. (2021)"
        ),
        make_text_block(
            f"**Optimisation and Training** (also see {link('Training Tips and Tricks', 'Training Tips and Tricks')}):\n\n"
            "• *AdamW: Decoupled Weight Decay* — Loshchilov & Hutter (2019)\n"
            "• *Cyclical Learning Rates* — Smith (2017)\n"
            "• *Layer Normalisation* — Ba et al. (2016)\n"
            "• *Flash Attention* — Dao et al. (2022)"
        ),
        make_todo_block("Read: Flash Attention 2 (Dao 2023)"),
        make_todo_block("Watch: Karpathy 'Let's build GPT from scratch' (YouTube)"),
        make_todo_block(
            "Read: Chinchilla — Training Compute-Optimal LLMs (Hoffmann 2022)"
        ),
        make_todo_block("Read: Mixtral of Experts (Jiang et al. 2024)"),
    ]
    filepath = vault / f"{_slug(title)}-{_short(note_id)}.jnote"
    now = _now()
    note = {
        "metadata": {
            "note_id": note_id,
            "title": title,
            "created_at": now,
            "last_modified": now,
            "version": "1.0",
            "status": 0,
            "tags": [],
            "last_known_path": str(filepath.resolve()),
        },
        "custom_fields": {},
        "blocks": blocks,
    }
    filepath.write_text(
        json.dumps(note, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  Created: '{title}' → {filepath.name}")

    print(f"\n✓ Seeded 8 sample notes successfully into: {vault}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Seed sample notes into the Sushi vault"
    )
    parser.add_argument(
        "--vault",
        type=Path,
        default=Path(__file__).parent.parent / "sample_notes",
        help="Path to the vault directory (default: ./sample_notes)",
    )
    args = parser.parse_args()
    seed(args.vault)
