"""Day 2. Reads: evidence, diagnosis, approved. Writes: execution_result.

The only node allowed to call tools/github_client.py's write functions
(post_comment, add_label). Must raise if `approved` is not True — this
check exists here, not just at the API layer, so nothing upstream can ever
reach GitHub by skipping the interrupt/approval step, even by mistake in a
future refactor. See graph/build.py for where the graph pauses
(LangGraph `interrupt()`) before this node runs.
"""

from __future__ import annotations

from graph.state import GraphState


def execute(state: GraphState) -> dict:
    if not state.get("approved"):
        raise PermissionError("execute() called without explicit approval")
    raise NotImplementedError
