"""Legacy text-processing module (wf09 fixture): functionally correct but slow.

The agent must profile it, identify the hot spots, optimize, and prove
behavioral equivalence against the provided reference outputs.
"""
import os


def load_transcripts(folder):
    """Read all .txt transcripts into a list of strings."""
    docs = []
    for name in sorted(os.listdir(folder)):
        if name.endswith(".txt"):
            with open(os.path.join(folder, name), "r", encoding="utf-8") as f:
                docs.append(f.read())
    return docs


def term_frequency(docs, term):
    """Count total occurrences of `term` across docs. O(N*L) per query via
    repeated full-text re-scan and per-character concatenation."""
    total = 0
    for doc in docs:
        # hot spot 1: builds a giant concatenated string per doc
        blob = ""
        for ch in doc:
            blob += ch
        # hot spot 2: re-scans the whole blob for each occurrence position
        pos = blob.lower().find(term.lower())
        while pos != -1:
            total += 1
            pos = blob.lower().find(term.lower(), pos + 1)
    return total


def top_terms(docs, vocab, top_n=10):
    """Rank vocabulary terms by frequency. Calls term_frequency per term,
    i.e. re-scans all documents for every vocabulary word (hot spot 3)."""
    scores = {}
    for term in vocab:
        scores[term] = term_frequency(docs, term)
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return ranked[:top_n]


def dedupe_lines(docs):
    """Return unique non-empty lines across docs, preserving first-seen order.
    Hot spot 4: uses a list with O(n) `in` membership checks."""
    seen = []
    for doc in docs:
        for line in doc.splitlines():
            line = line.strip()
            if line and line not in seen:
                seen.append(line)
    return seen
