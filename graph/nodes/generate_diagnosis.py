"""Day 2. Reads: evidence. Writes: diagnosis (Diagnosis).

Only reached on the "ai_investigation" branch. Retrieve relevant doc/runbook
snippets via tools/retrieval.py, then call the LLM with
`.with_structured_output(Diagnosis)` so the output is schema-constrained,
not parsed out of free text. Every claim in `recommended_next_steps` should
be traceable to a citation id from the retrieved snippets — that's what
independent_review checks next.
"""

from __future__ import annotations

from graph.state import GraphState


def generate_diagnosis(state: GraphState) -> dict:
    raise NotImplementedError
