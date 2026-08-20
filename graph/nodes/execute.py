"""The only node allowed to call tools/github_client.py's write functions
(post_comment, add_label). Refuses to run without state["approved"] is
True — checked here, not just at the graph-routing level, so nothing
upstream can ever reach GitHub by skipping await_approval, even by mistake
in a future refactor. Posts state["proposed_action"] verbatim — the exact
thing a human already signed off on in await_approval, never anything
recomputed after the fact.
"""

from __future__ import annotations

from graph.state import GraphState
from tools.github_client import add_label, post_comment


def execute(state: GraphState) -> dict:
    if not state.get("approved"):
        raise PermissionError("execute() called without explicit approval")

    evidence = state["evidence"]
    action = state["proposed_action"]

    result = {"comment": post_comment(evidence.repo, evidence.issue_number, action["comment"])}
    if action.get("label"):
        result["label"] = add_label(evidence.repo, evidence.issue_number, action["label"])

    return {"execution_result": result}
