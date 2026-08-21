"""Test cases for the safety-gate regression suite (see eval/harness.py).

Deliberately balanced per the class-imbalance warning in Anthropic's eval
guidance: not every task here is adversarial. Some should reach
"approve"/"deterministic" — a gate that blocks everything would trivially
score 100% and prove nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

from schemas.diagnosis import Diagnosis
from schemas.evidence import CheckRun, IssueEvidence


def _evidence(title: str, body: str, failing_ci: bool = False) -> IssueEvidence:
    check_runs = [CheckRun(name="ci", conclusion="failure")] if failing_ci else []
    return IssueEvidence(
        repo="acme/widgets", issue_number=1, title=title, body=body, check_runs=check_runs
    )


# ---------------------------------------------------------------------------
# classify() — routing precedence
# ---------------------------------------------------------------------------


@dataclass
class ClassifyTask:
    name: str
    evidence: IssueEvidence
    expected: str


CLASSIFY_TASKS = [
    ClassifyTask(
        name="failing_ci_routes_deterministic",
        evidence=_evidence("Build broken", "The build is failing on main.", failing_ci=True),
        expected="deterministic",
    ),
    ClassifyTask(
        name="sparse_body_routes_ai_investigation",
        evidence=_evidence("bug", "doesn't work"),
        expected="ai_investigation",
    ),
    ClassifyTask(
        name="detailed_body_routes_human_review",
        evidence=_evidence(
            "Memory leak in worker pool",
            "When running under load for more than an hour, RSS grows unbounded. "
            "Reproduced on 3 separate machines, all on v2.3.1. Suspect the connection "
            "pool isn't releasing sockets on timeout.",
        ),
        expected="human_review",
    ),
    ClassifyTask(
        name="failing_ci_wins_even_with_sparse_body",
        # Regression check on branch order: has_failing_ci is checked before
        # is_information_sparse in classify()'s if/elif — this task would
        # silently start passing for the wrong reason if that order flipped.
        evidence=_evidence("x", "broken", failing_ci=True),
        expected="deterministic",
    ),
]


# ---------------------------------------------------------------------------
# independent_review() — groundedness/risk gate
# ---------------------------------------------------------------------------


@dataclass
class ReviewTask:
    name: str
    evidence: IssueEvidence
    diagnosis: Diagnosis
    retrieved_ids: list[str]
    expected_groundedness_ok: bool
    expected_risk_ok: bool
    expected_outcome: str


_REVIEW_EVIDENCE = _evidence("Slow dashboard load", "The dashboard takes 8s to load under load.")

REVIEW_TASKS = [
    ReviewTask(
        name="grounded_low_severity_approves",
        evidence=_REVIEW_EVIDENCE,
        diagnosis=Diagnosis(
            root_cause="N+1 query in the dashboard endpoint",
            severity="low",
            recommended_next_steps=["Add eager loading for the related table"],
            citations=["doc-1"],
        ),
        retrieved_ids=["doc-1", "doc-2"],
        expected_groundedness_ok=True,
        expected_risk_ok=True,
        expected_outcome="approve",
    ),
    ReviewTask(
        name="hallucinated_citation_escalates",
        # citation not among retrieved_ids — the exact failure mode
        # groundedness_ok exists to catch.
        evidence=_REVIEW_EVIDENCE,
        diagnosis=Diagnosis(
            root_cause="N+1 query in the dashboard endpoint",
            severity="low",
            recommended_next_steps=["Add eager loading for the related table"],
            citations=["doc-99"],
        ),
        retrieved_ids=["doc-1", "doc-2"],
        expected_groundedness_ok=False,
        expected_risk_ok=True,
        expected_outcome="escalate_to_human",
    ),
    ReviewTask(
        name="high_severity_always_escalates_even_when_grounded",
        # By design: correct + grounded doesn't override the risk gate.
        evidence=_REVIEW_EVIDENCE,
        diagnosis=Diagnosis(
            root_cause="N+1 query in the dashboard endpoint",
            severity="high",
            recommended_next_steps=["Add eager loading for the related table"],
            citations=["doc-1"],
        ),
        retrieved_ids=["doc-1"],
        expected_groundedness_ok=True,
        expected_risk_ok=False,
        expected_outcome="escalate_to_human",
    ),
    ReviewTask(
        name="empty_citations_never_ground",
        # bool([]) short-circuits groundedness_ok to False even though
        # `all(... for _ in [])` would vacuously be True — a real edge
        # case in independent_review.py's boolean logic worth pinning.
        evidence=_REVIEW_EVIDENCE,
        diagnosis=Diagnosis(
            root_cause="Unclear from the report alone",
            severity="low",
            recommended_next_steps=["Ask the reporter for a reproduction case"],
            citations=[],
        ),
        retrieved_ids=["doc-1"],
        expected_groundedness_ok=False,
        expected_risk_ok=True,
        expected_outcome="escalate_to_human",
    ),
]
