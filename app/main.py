"""FastAPI layer in front of the compiled graph, for the React frontend.

ui.py (Streamlit) calls compiled_graph in-process and uses MemorySaver,
which only lives as long as that one process. This API is a separate
process serving separate HTTP requests — "analyze" and "resume" can
easily land on different requests seconds apart — so interrupt()/resume
needs a checkpointer that survives between them. SqliteSaver, opened
once at startup and kept open for the app's lifetime, does that; the
sqlite file lives on the backend host's disk, not in Python memory.

Deliberately not async: the graph's nodes (GitHub/OpenAI/Pinecone calls)
are synchronous, and FastAPI runs sync `def` endpoints in a threadpool
automatically. SqliteSaver opens its connection with check_same_thread=
False for exactly this reason.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from pydantic import BaseModel

from graph.build import graph

DB_PATH = "checkpoints.db"

_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    with SqliteSaver.from_conn_string(DB_PATH) as saver:
        saver.setup()
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
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest) -> dict:
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    try:
        result = _state["compiled_graph"].invoke({"issue_url": req.issue_url}, config)
    except Exception as exc:  # noqa: BLE001 -- surfacing any pipeline failure to the client is the point
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _serialize(thread_id, result)


@app.post("/api/resume/{thread_id}")
def resume(thread_id: str, req: ResumeRequest) -> dict:
    config = {"configurable": {"thread_id": thread_id}}
    try:
        result = _state["compiled_graph"].invoke(Command(resume=req.approved), config)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _serialize(thread_id, result)
