# ResolveFlow — First 5 Days Plan

Goal for the first 5 days: get a thin, end-to-end version of the pipeline running — fetch a real GitHub issue → normalize evidence → classify → produce a Pydantic diagnosis → review it → require human approval before any write. It doesn't need to be smart yet; it needs to be whole.

Suggested split across two workstreams (adjust names to your actual collaborator):

- **You (Person A):** Orchestration, diagnosis/reasoning, reviewer, evaluation
- **Collaborator (Person B):** GitHub integration layer, evidence schema, RAG ingestion

## Day 1 — Project skeleton + evidence schema

**Person A**
- Set up repo structure: `app/`, `graph/`, `tools/`, `schemas/`, `eval/`, `tests/`
- Set up FastAPI skeleton with a single `/analyze` endpoint (accepts issue/PR URL)
- Draft the normalized `IssueEvidence` Pydantic schema (issue body, comments, linked PRs, CI status, files touched, ownership hints)

**Person B**
- Set up GitHub API client (REST or GraphQL) with auth via token
- Implement fetch functions: issue, comments, linked PRs, Actions/CI run status
- Return raw (not yet normalized) JSON for a test issue

**End of day sync:** agree on the final shape of `IssueEvidence` schema — this is the contract between the two workstreams.

## Day 2 — Context fetching + LangGraph state

**Person A**
- Define LangGraph `GraphState` object
- Build the `START` → `Fetch GitHub Context` → `Validate/Normalize Evidence` nodes (stubbed, calling Person B's fetch functions)
- Wire up basic conditional routing skeleton (Deterministic / AI Investigation / Human)

**Person B**
- Implement the normalization layer: raw GitHub API responses → `IssueEvidence` schema
- Add ownership/CODEOWNERS parsing
- Add repo-documentation fetch (README, runbooks) as raw text, ready for RAG ingestion

**End of day sync:** run the fetch → normalize path end-to-end on one real issue.

## Day 3 — Classification + RAG retrieval

**Person A**
- Implement the `Classify Issue` node (rule-based first: failing CI → deterministic path; missing info → AI investigation; ambiguous/high-risk → human)
- Draft prompt + Pydantic output schema for the `Generate Diagnosis and Action Plan` node

**Person B**
- Stand up ChromaDB or FAISS index over repo docs
- Implement chunking + embedding ingestion pipeline
- Implement `retrieve_evidence(query)` tool the diagnosis node can call, returning cited snippets

**End of day sync:** verify classification routes correctly for at least 3 manually-crafted example issues (normal, failing-CI, ambiguous).

## Day 4 — Diagnosis, reviewer node, and approval gate

**Person A**
- Wire the diagnosis node to actually call the LLM with retrieved evidence + structured output parsing
- Build the `Independent Reviewer` node: checks groundedness (is every claim backed by retrieved evidence?), checks risk level, checks permissions
- Implement reviewer's three outcomes: Reject/retrieve more evidence, Escalate to human, Approve

**Person B**
- Implement the deterministic GitHub executor tool set (label add, assignee set, post comment, request-info comment) — but gated so it cannot run without an explicit `approved=True` flag
- Add a human confirmation step in the API (e.g., `/analyze` returns a plan + `plan_id`; a separate `/execute/{plan_id}` endpoint requires explicit confirmation)

**End of day sync:** confirm no write action can ever fire without going through both the reviewer approval and the human confirmation endpoint.

## Day 5 — Evaluation set + demo interface + hardening

**Person A**
- Build the small evaluation dataset: normal, incomplete, duplicate, failing-CI, ambiguous, and adversarial issues (can be a mix of real + synthetic issues)
- Write a basic scoring script (did it classify correctly? was the diagnosis grounded? did it avoid unapproved writes?)
- Add LangSmith tracing if time allows

**Person B**
- Build a minimal Streamlit (or simple React) interface: paste issue URL → see evidence → see diagnosis → approve/reject buttons
- Basic error handling for GitHub API failures, rate limits, missing permissions

**End of day sync:** run the full eval set through the pipeline, fix anything broken, and record a short demo (input → diagnosis → approval → executed action) to show the end-to-end story works.

## Notes

- Keep the "reasoning vs. execution" separation strict from Day 1 — it's the core differentiator, and it's much easier to enforce early than retrofit later.
- Prefer real GitHub issues (from a small test repo or your own repos) over synthetic ones wherever possible — the evidence-fetching edge cases (deleted PRs, missing CODEOWNERS, empty CI logs) are what actually break naive implementations.
- If Day 3–4 slips, cut scope on the RAG side (repo-doc retrieval) before cutting the reviewer/approval gate — the safety architecture is the differentiator; the retrieval quality is secondary for the MVP.
