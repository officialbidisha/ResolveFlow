"""Day 2. Reads: evidence. Writes: diagnosis (Diagnosis).

Only reached on the "ai_investigation" branch. Retrieve relevant doc/runbook
snippets via tools/retrieval.py, then call the LLM with
`.with_structured_output(Diagnosis)` so the output is schema-constrained,
not parsed out of free text. Every claim in `recommended_next_steps` should
be traceable to a citation id from the retrieved snippets — that's what
independent_review checks next.
"""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from graph.state import GraphState
from schemas.diagnosis import Diagnosis
from tools.retrieval import retrieve_evidence

_SYSTEM_PROMPT = """You are a senior maintainer diagnosing a GitHub issue.

Ground every claim in the provided evidence snippets. Every entry in
`citations` must be exactly one of the snippet ids given below — never
invent an id, and never cite a snippet that doesn't actually support the
claim it's attached to. If the snippets don't support a confident
diagnosis, say so in `missing_info` rather than guessing."""


def generate_diagnosis(state: GraphState) -> dict:
    evidence = state["evidence"]
    query = f"{evidence.title}\n\n{evidence.body}"
    snippets = retrieve_evidence(query, k=3)
    snippet_block = "\n\n".join(f"[{s['id']}] {s['text']}" for s in snippets)

    prompt = (
        f"Issue: {evidence.title}\n{evidence.body}\n\n"
        f"Comments:\n{chr(10).join(evidence.comments) or '(none)'}\n\n"
        f"Evidence snippets (cite by id in square brackets):\n{snippet_block}"
    )

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    structured_llm = llm.with_structured_output(Diagnosis)
    diagnosis = structured_llm.invoke([("system", _SYSTEM_PROMPT), ("human", prompt)])

    return {
        "diagnosis": diagnosis,
        "retrieved_ids": [s["id"] for s in snippets],
    }
