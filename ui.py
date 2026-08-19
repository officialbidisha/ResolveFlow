"""Minimal Streamlit UI: paste a GitHub issue URL, run the compiled graph, show what comes back.

Calls compiled_graph directly (no FastAPI layer yet — see PLAN.md Day 4/5).
Only reflects what's actually wired in graph/build.py today: fetch -> normalize
-> classify -> (deterministic -> execute stub | ai_investigation/human_review -> END).
generate_diagnosis / independent_review aren't in the graph yet, so this UI says
so explicitly rather than pretending the pipeline goes further than it does.
"""

from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

import streamlit as st

from graph.build import compiled_graph

st.set_page_config(page_title="ResolveFlow", page_icon="\U0001f500")
st.title("ResolveFlow")
st.caption(
    "fetch_evidence -> normalize_evidence -> classify -> (routing). "
    "Diagnosis + independent review aren't wired into the graph yet."
)

issue_url = st.text_input(
    "GitHub issue URL",
    placeholder="https://github.com/owner/repo/issues/123",
)

run = st.button("Analyze", type="primary")

if run and not issue_url:
    st.warning("Paste an issue URL first.")

if run and issue_url:
    with st.spinner("Running the graph..."):
        try:
            result = compiled_graph.invoke({"issue_url": issue_url})
        except Exception as exc:  # noqa: BLE001 -- surfacing any pipeline failure to the UI is the point
            st.error(f"Pipeline failed: {exc}")
        else:
            evidence = result["evidence"]
            classification = result["classification"]

            st.subheader(evidence.title)
            st.write(
                f"**{evidence.repo}** #{evidence.issue_number} · "
                f"labels: {', '.join(evidence.labels) or '—'}"
            )

            badge = {
                "deterministic": "green",
                "ai_investigation": "blue",
                "human_review": "orange",
            }.get(classification, "gray")
            st.markdown(f"**Classification:** :{badge}[{classification}]")

            with st.expander("Issue body"):
                st.write(evidence.body or "*(empty)*")

            if evidence.comments:
                with st.expander(f"Comments ({len(evidence.comments)})"):
                    for comment in evidence.comments:
                        st.write(comment)
                        st.divider()

            if classification == "deterministic":
                st.info(
                    "Routed to `execute` — but `execute` requires human approval "
                    "(`state[\"approved\"] is True`) and its GitHub-write logic isn't "
                    "implemented yet, so this will raise rather than post anything."
                )
            elif classification == "ai_investigation":
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
                outcome_badge = {"approve": "green", "escalate_to_human": "orange"}.get(
                    review.outcome, "gray"
                )
                st.markdown(f"**Outcome:** :{outcome_badge}[{review.outcome}]")
                st.markdown(
                    f"groundedness_ok: `{review.groundedness_ok}` · "
                    f"risk_ok: `{review.risk_ok}` · "
                    f"permission_ok: `{review.permission_ok}`"
                )
                st.write(review.reasoning)

                st.warning(
                    "Even on `approve`, this stops here — the human-approval "
                    "`interrupt()` gate and `execute` wiring for this branch aren't "
                    "built yet, so nothing gets written to GitHub regardless of outcome."
                )
            else:
                st.warning(
                    f"Routed to `{classification}` — this is the conservative "
                    "fallback classification, no diagnosis is attempted for it "
                    "by design."
                )
