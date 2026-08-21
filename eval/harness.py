"""Safety-gate regression suite.

Scope, deliberately: classify()'s routing precedence, independent_review()'s
groundedness/risk gate, and execute()'s permission check. Does NOT cover
await_approval()'s interrupt()/resume mechanics (see docs/CHECKPOINTING.md,
that's an integration-level concern) or generate_diagnosis's output quality
(a capability eval -- expected to improve over time, different bar, not
built yet).

This is a regression suite, not a capability suite: every task has an
unambiguous expected outcome, and the bar is 100% forever. A failure here
means the safety gate weakened, not "needs more training data" -- treat
pass^k semantics, not pass@k: one bypassed gate across any number of
trials is a critical failure, never something to average away.

independent_review() makes one real OpenAI call per review task (for the
`reasoning` field) -- the gate booleans themselves are computed in code,
before that call, so this suite tests the actual production function
rather than a reimplementation of its logic. Requires OPENAI_API_KEY.
execute()'s GitHub writes are mocked -- this suite must never post to
real GitHub.

Run with: uv run python -m eval.harness
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

from dotenv import load_dotenv

load_dotenv()

from eval.tasks import CLASSIFY_TASKS, REVIEW_TASKS
from graph.nodes.classify import classify
from graph.nodes.execute import execute
from graph.nodes.independent_review import independent_review
from graph.state import GraphState
from schemas.evidence import IssueEvidence


def run_classify_tasks() -> list[dict]:
    results = []
    for task in CLASSIFY_TASKS:
        actual = classify({"evidence": task.evidence})["classification"]
        results.append(
            {
                "suite": "classify",
                "task": task.name,
                "passed": actual == task.expected,
                "expected": task.expected,
                "actual": actual,
            }
        )
    return results


def run_review_tasks() -> list[dict]:
    results = []
    for task in REVIEW_TASKS:
        state: GraphState = {
            "evidence": task.evidence,
            "diagnosis": task.diagnosis,
            "retrieved_ids": task.retrieved_ids,
            "retrieved_scores": task.retrieved_scores,
        }
        review = independent_review(state)["review_result"]
        expected = {
            "groundedness_ok": task.expected_groundedness_ok,
            "risk_ok": task.expected_risk_ok,
            "outcome": task.expected_outcome,
        }
        actual = {
            "groundedness_ok": review.groundedness_ok,
            "risk_ok": review.risk_ok,
            "outcome": review.outcome,
        }
        results.append(
            {
                "suite": "independent_review",
                "task": task.name,
                "passed": actual == expected,
                "expected": expected,
                "actual": actual,
            }
        )
    return results


def run_execute_tasks() -> list[dict]:
    results = []
    evidence = IssueEvidence(repo="acme/widgets", issue_number=1, title="x", body="x")

    # An unapproved action must never execute, regardless of what's proposed.
    try:
        execute({"approved": False, "evidence": evidence, "proposed_action": {"comment": "should never post"}})
        raised = False
    except PermissionError:
        raised = True
    results.append(
        {
            "suite": "execute",
            "task": "refuses_without_approval",
            "passed": raised,
            "expected": "raises PermissionError",
            "actual": "raised" if raised else "did NOT raise -- critical failure",
        }
    )

    # An approved action must post the proposed payload verbatim, and only
    # through tools.github_client -- never touching real GitHub in this suite.
    with (
        patch("graph.nodes.execute.post_comment") as mock_post,
        patch("graph.nodes.execute.add_label") as mock_label,
    ):
        mock_post.return_value = {"id": 1}
        mock_label.return_value = {"ok": True}
        state: GraphState = {
            "approved": True,
            "evidence": evidence,
            "proposed_action": {"comment": "exact proposed text", "label": "needs-triage"},
            "github_token": "visitor-token-abc",
        }
        out = execute(state)
        # token is threaded through so a write runs as the visitor who
        # approved it, not the deployment's shared GITHUB_TOKEN.
        mock_post.assert_called_once_with(
            "acme/widgets", 1, "exact proposed text", token="visitor-token-abc"
        )
        mock_label.assert_called_once_with("acme/widgets", 1, "needs-triage", token="visitor-token-abc")
        passed = out["execution_result"]["comment"] == {"id": 1} and out["execution_result"]["label"] == {
            "ok": True
        }
    results.append(
        {
            "suite": "execute",
            "task": "posts_verbatim_when_approved",
            "passed": passed,
            "expected": "posts exactly the proposed comment/label via mocked github_client",
            "actual": out["execution_result"],
        }
    )
    return results


def main() -> None:
    results = run_classify_tasks() + run_review_tasks() + run_execute_tasks()
    passed = sum(r["passed"] for r in results)
    total = len(results)

    for r in results:
        mark = "PASS" if r["passed"] else "FAIL"
        print(f"[{mark}] {r['suite']}/{r['task']}")
        if not r["passed"]:
            print(f"        expected={r['expected']!r}")
            print(f"        actual  ={r['actual']!r}")

    print(f"\n{passed}/{total} passed")

    Path(__file__).parent.joinpath("results.json").write_text(json.dumps(results, indent=2))

    if passed != total:
        sys.exit(1)


if __name__ == "__main__":
    main()
