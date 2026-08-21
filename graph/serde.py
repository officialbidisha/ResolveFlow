"""Shared checkpoint serializer, registering this project's Pydantic state
models for msgpack (de)serialization.

Both checkpointers -- graph/build.py's in-process MemorySaver and
app/main.py's AsyncPostgresSaver -- round-trip GraphState through msgpack
whenever interrupt() pauses mid-graph, so any Pydantic model that can end
up in GraphState has to be listed here or a future LangGraph version
enforcing LANGGRAPH_STRICT_MSGPACK will refuse to serialize it (see
CHANGELOG.md's "Known issue" entry).
"""

from __future__ import annotations

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

_ALLOWED_MSGPACK_MODULES = [
    ("schemas.evidence", "IssueEvidence"),
    ("schemas.evidence", "CheckRun"),
    ("schemas.evidence", "LinkedPR"),
    ("schemas.diagnosis", "Diagnosis"),
    ("schemas.review", "ReviewResult"),
]


def get_serde() -> JsonPlusSerializer:
    return JsonPlusSerializer(allowed_msgpack_modules=_ALLOWED_MSGPACK_MODULES)
