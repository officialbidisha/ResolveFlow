# ResolveFlow

**A LangGraph agent that diagnoses GitHub issues and proposes fixes — but
never touches GitHub without passing an independent LLM review *and* an
explicit human approval.**

![Python](https://img.shields.io/badge/python-3.12-blue)
![LangGraph](https://img.shields.io/badge/LangGraph-StateGraph-1c1c1c)
![status](https://img.shields.io/badge/status-in%20progress-yellow)

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
                 execute*        generate_diagnosis (LLM,          END
                    |             structured output + RAG
                   END            citations)
                                            |
                                  independent_review (LLM,
                                  separate call — groundedness,
                                  risk, permission checks)
                                            |
                    +-----------------------+-----------------------+
                    |                       |                       |
                 approve          escalate_to_human      reject_retrieve_more
                    |                       |                       |
              [human approval]            END              generate_diagnosis
                interrupt() †                                    (loop)
                    |
                 execute*
                    |
                   END
```

`*` `execute` is the only node with side effects
(`tools/github_client.py`'s `post_comment` / `add_label`), and it refuses
to run without `state["approved"] is True` — enforced in the node itself.

`†` the `interrupt()` human-approval gate and `execute`'s real logic are
**not built yet** — see [Status](#status). Today, the `approve` branch
routes straight to `END`; nothing writes to GitHub on any path.

## Status

| Piece | State |
|---|---|
| `fetch_evidence` / `normalize_evidence` | ✅ Real GitHub REST calls, validated into `IssueEvidence` |
| `classify` | ✅ Rule-based routing (deliberate — see the node's docstring) |
| `generate_diagnosis` | ✅ Real OpenAI call, structured `Diagnosis` output with citations, grounded via real Pinecone retrieval |
| `independent_review` | ✅ Separate OpenAI critique call; approve/escalate gate computed in code, not trusted from the LLM |
| Retrieval corpus | ✅ `ingest.py` builds a real Pinecone index (`resolveflow-issues`) from live GitHub issues (`facebook/react`, `text-embedding-3-small`), self-healing (creates the index if missing). `tools/retrieval.py` queries it directly — verified end-to-end through `generate_diagnosis`. |
| `execute` + human approval gate | ❌ Not built. `execute()` raises `NotImplementedError`; LangGraph's `interrupt()` isn't wired into `graph/build.py` yet. This is the architectural centerpiece and the next milestone. |
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
uv run streamlit run ui.py     # interactive UI, drives compiled_graph directly
uv run python ingest.py        # (re)populate the Pinecone index from live GitHub issues
uv run pytest                  # once tests exist
```

## Roadmap

1. Wire `interrupt()` + `execute`'s real logic — the approval-gated write
   path that's the whole point of the architecture.
2. Build out `eval/` — scenario coverage across deterministic, sparse,
   and adversarial issues.
3. Tests for the node functions and the compiled graph.
