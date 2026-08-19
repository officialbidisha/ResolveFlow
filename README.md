# ResolveFlow

Diagnoses a GitHub issue, proposes a fix or next step with cited evidence, and executes only after an independent review and an explicit human approval. Built to demonstrate a strict separation between *reasoning* (diagnosis, retrieval, classification) and *execution* (the one deterministic GitHub write layer) — nothing writes to GitHub without passing through both a second model's review and a human-approved gate.

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
                interrupt()                                     (loop)
                    |
                 execute*
                    |
                   END
```

`*` execute is the only node with side effects (`tools/github_client.py`'s `post_comment` / `add_label`), and it refuses to run without `state["approved"] is True` — checked in the node itself, not just at the API boundary.

## What's real vs. mocked

- GitHub evidence fetching: real REST API calls (`tools/github_client.py`), needs a `GITHUB_TOKEN`.
- Diagnosis + review: real LLM calls via `langchain-openai`, needs `OPENAI_API_KEY`.
- Retrieval: a small FAISS index over a couple of repo docs — intentionally tiny for a 2-day scope, not meant to demonstrate retrieval quality at scale.
- Classification: rule-based, not learned — deliberate, see `graph/nodes/classify.py` docstring.
- Human approval: `interrupt()` (LangGraph's native human-in-the-loop primitive) pausing the graph before `execute`, resumed via the FastAPI `/execute/{thread_id}` endpoint.

## Setup

```bash
uv sync                  # installs from pyproject.toml
cp .env.example .env     # then fill in GITHUB_TOKEN + OPENAI_API_KEY
```

## Running

```bash
uv run uvicorn app.main:app --reload
uv run pytest
uv run python eval/runner.py
```

## Status

See `PLAN.md` for the original 5-day/2-person plan this was compressed from. Current build is solo, 2 days, thin end-to-end slice — see inline docstrings in `graph/nodes/*.py` for exactly what's implemented vs. stubbed.
