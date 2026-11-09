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
rather than a reimplementation of its logic. With --offline that one call
is replaced by a fixed string (no OPENAI_API_KEY needed), which cannot
change any gate outcome; PR CI runs it that way. GitHub is always the
in-process fake in eval/fake_github.py -- this suite must never touch real
GitHub.

The execute/credential cases also cover the two write-path invariants:
no GitHub write happens without a user credential bound to the request,
and a checkpoint never contains that credential.

Run with: uv run python -m eval.harness            (real OpenAI call)
          uv run python -m eval.harness --offline  (no external calls)
"""

from __future__ import annotations

import argparse
import json
import sys
import types
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from dotenv import load_dotenv

load_dotenv()

from langgraph.checkpoint.memory import MemorySaver

from eval.fake_github import FakeGitHub
from eval.tasks import CLASSIFY_TASKS, REVIEW_TASKS
from graph import credentials
from graph.nodes.classify import classify
from graph.nodes.execute import execute
from graph.nodes.independent_review import independent_review
from graph.serde import get_serde
from graph.state import GraphState
from schemas.evidence import IssueEvidence
from tools.side_effects import InMemorySideEffectStore, configure

USER_TOKEN = "ghu_harness_visitor_token_7f3a"


class _OfflineChat:
    """Replaces ChatOpenAI inside independent_review for --offline runs."""

    def __init__(self, *args, **kwargs):
        pass

    def invoke(self, messages):
        return types.SimpleNamespace(content="[offline] reasoning stubbed; gate booleans are computed in code")


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


def _result(task: str, passed: bool, expected: str, actual) -> dict:
    return {"suite": "execute", "task": task, "passed": passed, "expected": expected, "actual": actual}


def run_execute_tasks() -> list[dict]:
    results = []
    evidence = IssueEvidence(repo="acme/widgets", issue_number=1, title="x", body="x")
    action = {"comment": "exact proposed text", "label": "needs-triage"}

    # 1. An unapproved action must never execute, even with a credential bound.
    gh = FakeGitHub()
    configure(InMemorySideEffectStore())
    with gh.patched(), credentials.acting_as(USER_TOKEN):
        try:
            execute({"approved": False, "evidence": evidence, "proposed_action": action}, {"configurable": {"thread_id": "t1"}})
            raised = False
        except PermissionError:
            raised = True
    results.append(
        _result("refuses_without_approval", raised and gh.writes == 0, "raises PermissionError, 0 writes", f"raised={raised} writes={gh.writes}")
    )

    # 2. Approved, but no user credential on this request: zero writes, and no
    #    fallback to the deployment's shared GITHUB_TOKEN.
    gh = FakeGitHub()
    configure(InMemorySideEffectStore())
    with gh.patched(), patch.dict("os.environ", {"GITHUB_TOKEN": "shared-deployment-token"}):
        try:
            execute({"approved": True, "evidence": evidence, "proposed_action": action}, {"configurable": {"thread_id": "t2"}})
            raised = False
        except credentials.MissingCredential:
            raised = True
    results.append(
        _result(
            "refuses_writes_without_user_credential",
            raised and gh.writes == 0,
            "raises MissingCredential, 0 writes",
            f"raised={raised} writes={gh.writes}",
        )
    )

    # 3. Approved with a credential: posts the proposed text verbatim, as that
    #    user, exactly once even if execute runs again for the same thread.
    gh = FakeGitHub()
    configure(InMemorySideEffectStore())
    config = {"configurable": {"thread_id": "t3"}}
    state: GraphState = {"approved": True, "evidence": evidence, "proposed_action": action}
    with gh.patched(), credentials.acting_as(USER_TOKEN):
        first = execute(state, config)["execution_result"]
        second = execute(state, config)["execution_result"]
    passed = (
        len(gh.comments) == 1
        and gh.comments[0]["body"].startswith("exact proposed text")
        and gh.labels == ["needs-triage"]
        and {tok for _, tok in gh.write_tokens} == {USER_TOKEN}
        and first == second
    )
    results.append(
        _result(
            "posts_verbatim_once_as_acting_user",
            passed,
            "1 comment + 1 label as the acting user; re-run replays the same result",
            {"comments": len(gh.comments), "labels": gh.labels, "first": first, "second": second},
        )
    )

    # 4. Drive the real graph to the approval interrupt and through execute:
    #    no checkpoint ever contains the user's token.
    from graph.build import graph as uncompiled_graph

    gh = FakeGitHub()
    configure(InMemorySideEffectStore())
    saver = MemorySaver(serde=get_serde())
    compiled = uncompiled_graph.compile(checkpointer=saver)
    config = {"configurable": {"thread_id": "t4"}}
    with gh.patched(), credentials.acting_as(USER_TOKEN):
        paused = compiled.invoke({"issue_url": "https://github.com/acme/widgets/issues/1"}, config)
        at_interrupt = repr(vars(saver))
        from langgraph.types import Command

        compiled.invoke(Command(resume=True), config)
        after_execute = repr(vars(saver))
    leaked = USER_TOKEN in at_interrupt or USER_TOKEN in after_execute
    control = "acme/widgets" in at_interrupt  # proves the scan actually sees checkpoint contents
    results.append(
        _result(
            "checkpoint_contains_no_credential",
            "__interrupt__" in paused and control and not leaked and len(gh.comments) == 1,
            "paused at approval, token absent from every checkpoint, 1 comment after resume",
            {"paused": "__interrupt__" in paused, "control_seen": control, "token_leaked": leaked, "comments": len(gh.comments)},
        )
    )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Safety-gate regression suite")
    parser.add_argument("--offline", action="store_true", help="stub independent_review's single LLM call")
    args = parser.parse_args()

    stub = patch("graph.nodes.independent_review.ChatOpenAI", _OfflineChat) if args.offline else nullcontext()
    with stub:
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
