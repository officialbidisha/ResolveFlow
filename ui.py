"""Streamlit UI: paste a GitHub issue URL, run the compiled graph, and —
if it reaches await_approval — approve or reject the exact GitHub write
before it happens. Calls compiled_graph directly (no FastAPI layer).

Each analysis run gets its own thread_id, required because the graph is
compiled with a checkpointer (interrupt()/resume needs somewhere to
persist state across the pause). Approve/Reject resume that same thread
via Command(resume=...) rather than starting a new run.
"""

from __future__ import annotations

import uuid

from dotenv import load_dotenv

load_dotenv()

import streamlit as st
from langgraph.types import Command

from graph.build import compiled_graph

st.set_page_config(page_title="ResolveFlow", page_icon="\U0001f500")
st.title("ResolveFlow")
st.caption(
    "fetch_evidence -> normalize_evidence -> classify -> (deterministic | "
    "ai_investigation -> generate_diagnosis -> independent_review) -> "
    "await_approval -> execute. Nothing posts to GitHub without approval."
)

if "thread_id" not in st.session_state:
    st.session_state.thread_id = None
    st.session_state.result = None

issue_url = st.text_input(
    "GitHub issue URL",
    placeholder="https://github.com/owner/repo/issues/123",
)

run = st.button("Analyze", type="primary")

if run and not issue_url:
    st.warning("Paste an issue URL first.")

if run and issue_url:
    st.session_state.thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": st.session_state.thread_id}}
    with st.spinner("Running the graph..."):
        try:
            st.session_state.result = compiled_graph.invoke({"issue_url": issue_url}, config)
        except Exception as exc:  # noqa: BLE001 -- surfacing any pipeline failure to the UI is the point
            st.error(f"Pipeline failed: {exc}")
            st.session_state.result = None

result = st.session_state.result

if result:
    evidence = result["evidence"]
    classification = result["classification"]

    st.subheader(evidence.title)
    st.write(f"**{evidence.repo}** #{evidence.issue_number} · labels: {', '.join(evidence.labels) or '—'}")

    badge = {"deterministic": "green", "ai_investigation": "blue", "human_review": "orange"}.get(
        classification, "gray"
    )
    st.markdown(f"**Classification:** :{badge}[{classification}]")

    with st.expander("Issue body"):
        st.write(evidence.body or "*(empty)*")

    if evidence.comments:
        with st.expander(f"Comments ({len(evidence.comments)})"):
            for comment in evidence.comments:
                st.write(comment)
                st.divider()

    if classification == "ai_investigation" and result.get("diagnosis"):
        diagnosis = result["diagnosis"]
        review = result["review_result"]

        st.markdown("#### Diagnosis")
        st.write(diagnosis.root_cause)
        st.markdown(f"**Severity:** {diagnosis.severity}")
        if diagnosis.missing_info:
            st.markdown("**Missing info:** " + "; ".join(diagnosis.missing_info))
        st.markdown("**Recommended next steps:**")
        for step in diagnosis.recommended_next_steps:
            st.markdown(f"- {step}")
        st.caption("Citations: " + ", ".join(diagnosis.citations or ["(none)"]))

        st.markdown("#### Independent review")
        outcome_badge = {"approve": "green", "escalate_to_human": "orange"}.get(review.outcome, "gray")
        st.markdown(f"**Outcome:** :{outcome_badge}[{review.outcome}]")
        st.markdown(
            f"groundedness_ok: `{review.groundedness_ok}` · "
            f"risk_ok: `{review.risk_ok}` · "
            f"permission_ok: `{review.permission_ok}`"
        )
        st.write(review.reasoning)

        if review.outcome == "escalate_to_human":
            st.warning("Escalated to a human — no proposed action was generated, nothing to approve.")
    elif classification == "human_review":
        st.warning(
            "Routed to `human_review` — the conservative fallback classification, "
            "no diagnosis is attempted for it by design."
        )

    if "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        action = payload["proposed_action"]

        st.markdown("#### Pending human approval")
        st.caption("This is the exact comment execute will post — nothing gets recomputed after you decide.")
        st.code(action["comment"], language="markdown")
        if action.get("label"):
            st.caption(f"Label to add: `{action['label']}`")

        thread_config = {"configurable": {"thread_id": st.session_state.thread_id}}
        col_approve, col_reject = st.columns(2)

        if col_approve.button("Approve — post to GitHub", type="primary"):
            with st.spinner("Posting..."):
                st.session_state.result = compiled_graph.invoke(Command(resume=True), thread_config)
            st.rerun()

        if col_reject.button("Reject"):
            st.session_state.result = compiled_graph.invoke(Command(resume=False), thread_config)
            st.rerun()

    elif result.get("execution_result"):
        st.success("Posted to GitHub.")
        st.json(result["execution_result"])

    elif result.get("approved") is False:
        st.info("Rejected — nothing was posted to GitHub.")
