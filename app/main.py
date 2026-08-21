"""FastAPI layer in front of the compiled graph, for the React frontend.

This is the only deployed surface (frontend on Vercel, this API on
Render) — there is no in-process UI anymore. "analyze" and "resume" can
easily land on separate HTTP requests seconds apart, possibly on
different worker threads, so interrupt()/resume needs a checkpointer
that survives between them, not one scoped to a single Python process's
memory (that's what graph/build.py's MemorySaver-backed `compiled_graph`
is for — local/ad-hoc use only).

Checkpointer is AsyncPostgresSaver, not SqliteSaver — a real Postgres
instance survives container recycling, unlike a local sqlite file on
Render's free-tier disk, which is wiped on every spin-down/spin-up (no
persistent volume on the free plan). AsyncPostgresSaver has no sync
interface, which is why this file is fully async now: `ainvoke()`
instead of `invoke()`, `async def` endpoints, `await saver.setup()`.
Graph nodes themselves stay synchronous (GitHub/OpenAI/Pinecone calls
via `requests`/SDKs, not `httpx`/`aiohttp`) — LangGraph's `ainvoke()`
runs sync node functions in a thread pool executor automatically, so
nothing in graph/nodes/*.py needed to change for this.
"""

from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from pydantic import BaseModel

from graph.build import graph
from graph.serde import get_serde

DATABASE_URL = os.environ["DATABASE_URL"]

_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncPostgresSaver.from_conn_string(DATABASE_URL, serde=get_serde()) as saver:
        await saver.setup()
        _state["compiled_graph"] = graph.compile(checkpointer=saver)
        yield
    _state.clear()


app = FastAPI(title="ResolveFlow API", lifespan=lifespan)

# Permissive for the demo — tighten to the actual deployed frontend
# origin once that URL is stable.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    issue_url: str


class ResumeRequest(BaseModel):
    approved: bool


def _serialize(thread_id: str, result: dict) -> dict:
    evidence = result.get("evidence")
    diagnosis = result.get("diagnosis")
    review_result = result.get("review_result")
    execution_result = result.get("execution_result")

    return {
        "thread_id": thread_id,
        "evidence": evidence.model_dump() if evidence else None,
        "classification": result.get("classification"),
        "diagnosis": diagnosis.model_dump() if diagnosis else None,
        "review_result": review_result.model_dump() if review_result else None,
        "pending_approval": result["__interrupt__"][0].value if "__interrupt__" in result else None,
        "execution_result": execution_result,
        "rejected": result.get("approved") is False and execution_result is None,
    }


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest) -> dict:
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    try:
        result = await _state["compiled_graph"].ainvoke({"issue_url": req.issue_url}, config)
    except Exception as exc:  # noqa: BLE001 -- surfacing any pipeline failure to the client is the point
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _serialize(thread_id, result)


@app.post("/api/resume/{thread_id}")
async def resume(thread_id: str, req: ResumeRequest) -> dict:
    config = {"configurable": {"thread_id": thread_id}}
    try:
        result = await _state["compiled_graph"].ainvoke(Command(resume=req.approved), config)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _serialize(thread_id, result)
