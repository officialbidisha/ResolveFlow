

"""Day 1. Reads: evidence. Writes: classification.

Rule-based, not an LLM call — classification decides how much of the
expensive/risky path (LLM diagnosis, RAG, writes) a given issue even needs,
so it has to be cheap, fast, and fully deterministic itself.

Suggested rules (adjust after testing on real issues):
  - evidence.has_failing_ci               -> "deterministic"
    (clear signal, no investigation needed — just label/comment)
  - evidence.is_information_sparse        -> "ai_investigation"
    (need the LLM to figure out what's even being asked)
  - anything else / high blast-radius     -> "human_review"
    (ambiguous or high-risk; don't let the pipeline guess)
"""

from __future__ import annotations

from graph.state import GraphState


def classify(state: GraphState) -> dict:
    if state["evidence"].has_failing_ci:
      return {"classification":"deterministic"}
    elif state["evidence"].is_information_sparse:
      return {"classification": "ai_investigation"}
    else:
      return {"classification":"human_review"}
