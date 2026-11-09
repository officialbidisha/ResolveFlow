"""The only node allowed to make GitHub writes (a comment and, optionally, a
label). Refuses to run without state["approved"] is True — checked here, not
just at the graph-routing level, so nothing upstream can ever reach GitHub by
skipping await_approval, even by mistake in a future refactor. Posts
state["proposed_action"] verbatim — the exact thing a human already signed
off on in await_approval, never anything recomputed after the fact.

Credential: the acting user's token is read from graph/credentials.py at the
moment of the write, from whatever request is running this node. It is never
read from GraphState (which the checkpointer persists), and there is no
fallback to the deployment's shared GITHUB_TOKEN. No credential, no writes.

Retry safety: each write goes through tools/side_effects.py, keyed by this
run's thread_id, so concurrent resumes, a retry after a crash, or a label
failure can never duplicate the comment or lose its recorded result.
"""

# No `from __future__ import annotations` here: LangGraph injects `config`
# only when the annotation is a real RunnableConfig type, not a string.
import logging

from langchain_core.runnables import RunnableConfig

from graph import credentials
from graph.state import GraphState
from tools import side_effects

log = logging.getLogger("resolveflow.execute")


def execute(state: GraphState, config: RunnableConfig | None = None) -> dict:
    if not state.get("approved"):
        raise PermissionError("execute() called without explicit approval")

    token = credentials.require_token()

    thread_id = ((config or {}).get("configurable") or {}).get("thread_id")
    if not thread_id:
        raise ValueError("execute() needs the run's thread_id to make writes idempotent")

    evidence = state["evidence"]
    action = state["proposed_action"]

    # Audit line for the one node with side effects. trace/user ids are
    # stamped by graph/request_context.py (this node runs in a worker
    # thread; the context is copied into it).
    log.info(
        "github write thread=%s repo=%s issue=%s label=%s",
        thread_id,
        evidence.repo,
        evidence.issue_number,
        action.get("label"),
    )

    result = {
        "comment": side_effects.post_comment_once(
            thread_id, evidence.repo, evidence.issue_number, action["comment"], token
        )
    }
    if action.get("label"):
        result.update(
            side_effects.add_label_once(thread_id, evidence.repo, evidence.issue_number, action["label"], token)
        )

    return {"execution_result": result}
