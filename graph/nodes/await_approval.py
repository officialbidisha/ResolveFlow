"""Every path to execute — deterministic or ai_investigation-approved —
passes through this one node first. It decides the exact comment/label
execute will post, then pauses on that exact payload via LangGraph's
interrupt(). "approved" always means "a human saw this specific action
and said yes," never "a human clicked an approve button blind" — execute
later posts state["proposed_action"] verbatim, it never recomputes it.

Resuming: the graph must be compiled with a checkpointer, and callers
resume with `compiled_graph.invoke(Command(resume=True_or_False), config)`
using the same thread_id the paused run started with.
"""

from __future__ import annotations

from langgraph.types import interrupt

from graph.state import GraphState


def _build_proposed_action(state: GraphState) -> dict:
    evidence = state["evidence"]

    if state["classification"] == "deterministic":
        return {
            "comment": (
                f"Automated triage: `{evidence.title}` has a failing CI check. "
                "Flagging for maintainer attention."
            ),
            "label": "needs-triage",
        }

    diagnosis = state["diagnosis"]
    steps = "\n".join(f"- {step}" for step in diagnosis.recommended_next_steps)
    return {
        "comment": (
            f"### Automated diagnosis\n\n"
            f"**Root cause:** {diagnosis.root_cause}\n\n"
            f"**Recommended next steps:**\n{steps}"
        ),
        "label": f"severity:{diagnosis.severity}",
    }


def await_approval(state: GraphState) -> dict:
    proposed_action = _build_proposed_action(state)
    approved = interrupt(
        {
            "classification": state["classification"],
            "proposed_action": proposed_action,
        }
    )
    return {"proposed_action": proposed_action, "approved": bool(approved)}
