"""Output of the independent reviewer node.

This must come from a separate model call/prompt than generate_diagnosis —
the whole point of "independent" review is that it isn't the same call
grading its own homework. Enforce that in graph/nodes/independent_review.py,
not just in naming.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ReviewResult(BaseModel):
    outcome: Literal["approve", "escalate_to_human", "reject_retrieve_more"]
    groundedness_ok: bool  # every Diagnosis.citations entry maps to a real retrieved snippet
    risk_ok: bool  # severity/blast-radius within what deterministic execution may touch
    permission_ok: bool  # the proposed action is inside this pipeline's allowed operation set
    reasoning: str
