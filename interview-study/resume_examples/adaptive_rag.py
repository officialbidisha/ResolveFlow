"""Adaptive + corrective RAG, minimal and runnable (no network, no LLM).

Illustrative. Stand-ins are marked: the classifier is rules (production: a small LLM or
fine-tuned classifier), scoring is token overlap (production: embeddings + FAISS + reranker).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

CORPUS = {
    "doc1": "To reset a user password open Setup and choose Users then Reset Password.",
    "doc2": "Permission sets grant extra access on top of a profile and can be assigned to many users.",
    "doc3": "Public groups can contain users roles and other groups and are used in sharing rules.",
    "doc4": "Queues own records such as cases and leads and have members who can accept them.",
}
RELEVANCE_MIN = 0.25      # below this the evidence may not influence the answer
MAX_REWRITES = 1          # corrective loop is bounded


def toks(s: str) -> set[str]:
    return set(re.findall(r"[a-z]+", s.lower()))


def classify(query: str) -> str:
    """Route: 'direct' (no retrieval), 'single' (one retrieval), 'multi' (decompose)."""
    q = query.lower()
    if re.fullmatch(r"(hi|hello|thanks|thank you)[!. ]*", q):
        return "direct"
    if " and " in q or " compare " in q or " versus " in q or q.count("?") > 1:
        return "multi"
    return "single"


def retrieve(query: str, k: int = 3) -> list[tuple[str, float]]:
    qt = toks(query)
    scored = [(d, len(qt & toks(t)) / (len(qt) or 1)) for d, t in CORPUS.items()]
    return sorted(scored, key=lambda x: x[1], reverse=True)[:k]


def grade(hits: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Corrective step: drop chunks under the threshold."""
    return [(d, s) for d, s in hits if s >= RELEVANCE_MIN]


def rewrite(query: str) -> str:
    """Stand-in for an LLM rewrite: strip filler words."""
    return " ".join(w for w in query.split() if w.lower() not in {"how", "do", "i", "the", "a", "can", "please"})


@dataclass
class Result:
    route: str
    evidence: list[str]
    answer: str
    rewrites: int = 0


def answer(query: str) -> Result:
    route = classify(query)
    if route == "direct":
        return Result(route, [], "Hello! How can I help?")
    subqueries = [p.strip() for p in re.split(r"\band\b|\?", query) if p.strip()] if route == "multi" else [query]
    evidence: list[str] = []
    rewrites = 0
    for sq in subqueries:
        good = grade(retrieve(sq))
        while not good and rewrites < MAX_REWRITES:        # corrective loop, bounded
            sq, rewrites = rewrite(sq), rewrites + 1
            good = grade(retrieve(sq))
        evidence += [d for d, _ in good]
    evidence = sorted(set(evidence))
    if not evidence:
        return Result(route, [], "I could not find supporting documents, so I won't guess.", rewrites)
    return Result(route, evidence, "Answer built from: " + ", ".join(evidence), rewrites)


def grounded(res: Result) -> bool:
    """Deterministic groundedness: every cited doc id exists in the corpus and is in the evidence."""
    cited = set(re.findall(r"doc\d+", res.answer))
    return cited <= set(res.evidence) and cited <= set(CORPUS)


if __name__ == "__main__":
    for q in ["hello", "reset password for a user", "permission sets and public groups", "banana smoothie recipe"]:
        r = answer(q)
        print(f"{q!r:45} route={r.route:6} evidence={r.evidence} rewrites={r.rewrites} grounded={grounded(r)}")
