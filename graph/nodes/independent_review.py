"""Day 2. Reads: evidence, diagnosis. Writes: review_result (ReviewResult).

Must use a separate prompt/call than generate_diagnosis — "independent"
means it isn't the same reasoning trace grading itself. Checks:
  - groundedness_ok: every citation in diagnosis.citations actually
    corresponds to a snippet that was retrieved (not hallucinated)
  - risk_ok: diagnosis.severity is within what a deterministic write
    (comment/label) is allowed to act on without a human
  - permission_ok: the implied action is inside the fixed operation
    allowlist tools/github_client.py exposes (comment, label — nothing else)

outcome="approve" only if all three are True. Otherwise "escalate_to_human"
or "reject_retrieve_more" (loop back to generate_diagnosis with feedback —
optional stretch goal, fine to hardcode escalate_to_human first).
"""

from __future__ import annotations

from graph.state import GraphState


def independent_review(state: GraphState) -> dict:
    raise NotImplementedError
