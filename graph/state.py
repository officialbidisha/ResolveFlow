"""The single state object threaded through every node in the graph.

Treat this as append-only: once fetch_evidence sets `evidence`, nothing
downstream should mutate it — nodes should only ever add new keys
(classification, diagnosis, review_result, ...). That's what makes the
graph auditable: at any point you can look at GraphState and see exactly
which stages have run and what each one produced.
"""

from __future__ import annotations

from typing import Literal, TypedDict

from schemas.diagnosis import Diagnosis
from schemas.evidence import IssueEvidence
from schemas.review import ReviewResult

Classification = Literal["deterministic", "ai_investigation", "human_review"]


class GraphState(TypedDict, total=False):
    issue_url: str
    github_token: str  # the logged-in visitor's own token; falls back to GITHUB_TOKEN if unset
    evidence: IssueEvidence
    classification: Classification
    diagnosis: Diagnosis
    review_result: ReviewResult
    approved: bool
    proposed_action: dict
    execution_result: dict
    raw_evidence: dict
    retrieved_ids: list[str]
    retrieved_scores: dict[str, float]  # id -> cosine similarity, for independent_review's groundedness check
