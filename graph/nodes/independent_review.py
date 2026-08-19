"""Day 2. Reads: evidence, diagnosis. Writes: review_result (ReviewResult).

Must use a separate prompt/call than generate_diagnosis — "independent"
means it isn't the same reasoning trace grading itself. Checks:
  - groundedness_ok: every citation in diagnosis.citations actually
    corresponds to a snippet that was retrieved (not hallucinated)
  - risk_ok: diagnosis.severity is within what a deterministic write
    (comment/label) is allowed to act on without a human
  - permission_ok: the implied action is inside the fixed operation
    allowlist tools/github_client.py exposes (comment, label — nothing else)

outcome="approve" only if all three are True. Otherwise "escalate_to_human"
or "reject_retrieve_more" (loop back to generate_diagnosis with feedback —
optional stretch goal, fine to hardcode escalate_to_human first).
"""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from graph.state import GraphState
from schemas.review import ReviewResult

# "high" severity always escalates to a human — never auto-approved.
_ALLOWED_SEVERITIES = {"low", "medium"}

_SYSTEM_PROMPT = """You are an independent reviewer. Another model just
produced a diagnosis of a GitHub issue; you did not write it. Critique it —
do not rubber-stamp it. Point out anything under-supported by the issue as
described, or any recommended step that seems too aggressive for what's
actually known. Keep it to a few sentences."""


def independent_review(state: GraphState) -> dict:
    evidence = state["evidence"]
    diagnosis = state["diagnosis"]
    retrieved_ids = set(state.get("retrieved_ids", []))

    # groundedness/risk/permission are computed here in code, not trusted
    # from the LLM call below — the LLM only ever supplies human-readable
    # reasoning, never the actual approve/escalate gate. Don't let the model
    # grade its own (or another model's) risk assessment.
    groundedness_ok = bool(diagnosis.citations) and all(
        citation_id in retrieved_ids for citation_id in diagnosis.citations
    )
    risk_ok = diagnosis.severity in _ALLOWED_SEVERITIES
    # comment/label are the only writes execute.py can make today (see
    # tools/github_client.py) — there's no broader action space yet for a
    # diagnosis to have exceeded, so this is always True for now.
    permission_ok = True

    prompt = (
        f"Issue: {evidence.title}\n{evidence.body}\n\n"
        f"Diagnosis root cause: {diagnosis.root_cause}\n"
        f"Severity: {diagnosis.severity}\n"
        f"Recommended next steps: {diagnosis.recommended_next_steps}\n"
        f"Citations: {diagnosis.citations}"
    )
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    reasoning = llm.invoke([("system", _SYSTEM_PROMPT), ("human", prompt)]).content

    outcome = "approve" if (groundedness_ok and risk_ok and permission_ok) else "escalate_to_human"

    return {
        "review_result": ReviewResult(
            outcome=outcome,
            groundedness_ok=groundedness_ok,
            risk_ok=risk_ok,
            permission_ok=permission_ok,
            reasoning=reasoning,
        )
    }
