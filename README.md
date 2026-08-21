# ResolveFlow

**A LangGraph agent that diagnoses GitHub issues and proposes fixes — but
never touches GitHub without passing an independent LLM review *and* an
explicit human approval.**

<img width="612" height="663" alt="Screenshot 2026-08-20 at 6 35 12 PM" src="https://github.com/user-attachments/assets/08bebe51-ee23-411f-837b-1ebd42069cba" />


![Python](https://img.shields.io/badge/python-3.12-blue)
![LangGraph](https://img.shields.io/badge/LangGraph-StateGraph-1c1c1c)
![status](https://img.shields.io/badge/status-approval--gated%20execution%20live-brightgreen)

**Live:** [resolveflow-web-officialbidishas-projects.vercel.app](https://resolveflow-web-officialbidishas-projects.vercel.app) &middot; API: [resolveflow-1h99.onrender.com](https://resolveflow-1h99.onrender.com/api/health)

ResolveFlow takes a GitHub issue URL, gathers evidence, classifies the
issue, and — depending on that classification — either runs a
deterministic action, kicks off an LLM investigation with cited retrieval,
or escalates straight to a human. The core architectural bet: **reasoning
and execution are separated by construction, not convention.** A second,
independent LLM call reviews the first model's diagnosis before anything
reaches a human for approval, and the single node allowed to write to
GitHub refuses to run without an explicit `approved` flag — checked in the
node itself, not just at an API boundary.

## Why this exists

This is a portfolio project, built to show a real, working slice of
agentic system design: state machines over prompt chains, a hard boundary
between the part of the system that reasons and the part that acts, and
an evidence/citation trail a reviewer can actually audit. It is not
trying to be production-hardened — see [Status](#status) for exactly what
is real, what is a deliberate placeholder, and what is simply unbuilt.

## Architecture

```
issue_url
   |
fetch_evidence -> normalize_evidence -> classify
                                            |
                    +-----------------------+-----------------------+
                    |                       |                       |
              deterministic          ai_investigation           human_review
             (failing CI)            (sparse issue)            (ambiguous/risky)
                    |                       |                       |
             await_approval*     generate_diagnosis (LLM,          END
                    |             structured output + RAG
                   ...           citations)
                                            |
                                  independent_review (LLM,
                                  separate call — groundedness,
                                  risk, permission checks)
                                            |
                    +-----------------------+-----------------------+
                    |                       |                       |
                 approve          escalate_to_human      reject_retrieve_more
                    |                       |                       |
             await_approval*               END              generate_diagnosis
                    |                                            (loop, not built)
        (conditional on state["approved"])
              /            \
          execute†          END
              |
             END
```

`*` `await_approval` builds the exact comment/label that would be posted,
then pauses via LangGraph's `interrupt()` — every path to `execute` goes
through this same gate, none skip it. The paused run resumes with
`Command(resume=True/False)`, using the same `thread_id` (requires a
checkpointer, see `graph/build.py`).

`†` `execute` is the only node with side effects
(`tools/github_client.py`'s `post_comment` / `add_label`). It posts
`state["proposed_action"]` **verbatim** — the exact thing shown at the
approval gate, never recomputed — and refuses to run at all without
`state["approved"] is True`, checked in the node itself as a second,
independent guarantee on top of the graph routing.

## Status

| Piece | State |
|---|---|
| `fetch_evidence` / `normalize_evidence` | ✅ Real GitHub REST calls, validated into `IssueEvidence` |
| `classify` | ✅ Rule-based routing (deliberate — see the node's docstring) |
| `generate_diagnosis` | ✅ Real OpenAI call, structured `Diagnosis` output with citations, grounded via real Pinecone retrieval |
| `independent_review` | ✅ Separate OpenAI critique call; approve/escalate gate computed in code, not trusted from the LLM |
| Retrieval corpus | ✅ `ingest.py` builds a real Pinecone index (`resolveflow-issues`, ~2,750 chunks) from closed issues across 4 real repos (`facebook/react`, `langchain-ai/langchain`, `microsoft/terminal`, `vercel/next.js`; `text-embedding-3-small`), self-healing (creates the index if missing), idempotent (clears stale vectors before re-ingesting). `tools/retrieval.py` queries it directly. Verified against real issues end-to-end: correct, specific, citation-grounded root-cause diagnoses on real bugs — see `CHANGELOG.md` for `facebook/react#36932`. |
| `execute` + human approval gate | ✅ `await_approval` builds the proposed comment/label and pauses via `interrupt()`; every path to `execute` goes through it. `execute` posts that exact payload via `tools/github_client.py`, gated on `state["approved"]`. The deployed FastAPI backend drives the real approve/reject flow via `Command(resume=...)`, checkpointed with `SqliteSaver`. Verified end-to-end (mocked GitHub reads/writes, real OpenAI + Pinecone calls): interrupt payload and posted content match exactly. |
| React frontend + FastAPI backend | ✅ `frontend/` (Vite + React + TypeScript) talks to `app/main.py` (FastAPI) over HTTP — the only deployed surface. Backend uses a persistent `SqliteSaver` checkpointer since interrupt()/resume happen across separate HTTP requests. Deployed: frontend on Vercel, backend on Render. Verified end-to-end on the live production URLs. |
| `eval/` | ❌ Empty — no evaluation harness yet. |
| Tests | ❌ Not written yet. |

See [`CHANGELOG.md`](./CHANGELOG.md) for the build history, and
[`PLAN.md`](./PLAN.md) for the original 5-day/2-person plan this was
compressed from into a solo, thinner end-to-end slice.

## Setup

```bash
uv sync                  # installs from pyproject.toml
cp .env.example .env     # fill in GITHUB_TOKEN, OPENAI_API_KEY, PINECONE_API_KEY
```

## Running

```bash
uv run uvicorn app.main:app --reload                     # FastAPI backend, for the React frontend
cd frontend && npm install && npm run dev                # React frontend (localhost:5173)
uv run python ingest.py                                  # (re)populate the Pinecone index from live GitHub issues
uv run pytest                                             # once tests exist
```

Live: see the badges/links above. No local UI is needed to try it — the deployed frontend talks to the deployed backend directly.

## Roadmap

1. Build out `eval/` — scenario coverage across deterministic, sparse,
   and adversarial issues.
2. Tests for the node functions and the compiled graph.
3. Register the Pydantic schemas with LangGraph's checkpoint serializer
   (currently a deprecation warning, not yet enforced) — see
   `CHANGELOG.md`.
