"""The acting user's GitHub credential, carried for the duration of one request.

Why not GraphState: everything in GraphState is written to the checkpointer
(Postgres in production) every time the graph pauses at interrupt(), so a
token placed there outlives the request and sits in the checkpoint tables
indefinitely. Why not the invoke config either: LangGraph copies
`configurable` values into checkpoint metadata, so that is persisted too.

So the API binds the signed-in user's token here, around each ainvoke()
call, from the server-side session (app/db.py). Graph nodes read it at the
moment they need it. A resumed run gets whatever credential the *resuming*
request carries, never one saved from an earlier request.

Propagation is the same as graph/request_context.py: a ContextVar is copied
into asyncio.to_thread workers and into the executor threads LangGraph uses
for sync nodes, and is isolated between concurrent requests.

Reads may fall back to the deployment's shared GITHUB_TOKEN (ingest.py and
local scripts rely on that). Writes never do: execute() calls
require_token(), and tools/github_client.py's write functions refuse to run
without an explicit token.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

_acting_token: ContextVar[str | None] = ContextVar("acting_github_token", default=None)


class MissingCredential(PermissionError):
    """Raised when a GitHub write is attempted with no acting user credential."""


@contextmanager
def acting_as(token: str | None) -> Iterator[None]:
    """Binds `token` for the block and always restores the previous value."""
    reset = _acting_token.set(token or None)
    try:
        yield
    finally:
        _acting_token.reset(reset)


def current_token() -> str | None:
    return _acting_token.get()


def require_token() -> str:
    token = _acting_token.get()
    if not token:
        raise MissingCredential("no acting user credential for this request; refusing GitHub writes")
    return token
