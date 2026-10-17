"""Request-scoped identity (trace id, GitHub user id) carried in ContextVars.

Why ContextVar and not a module global: this process serves many users at
once. A plain global would be shared by every concurrent request, so user
B's logs could be stamped with user A's id. A ContextVar is isolated per
asyncio task (and per thread), so each request sees only its own value.

Propagation, which is what makes this usable inside the graph:
  - `await` inside the same task: same context, nothing to do.
  - `asyncio.to_thread(...)` and `loop.run_in_executor` via LangChain/
    LangGraph: the context is *copied* into the worker thread, so sync graph
    nodes running in a thread pool still read the right values. This is
    verified by tests/test_concurrency.py, not assumed.
  - `threading.Thread(...)` / a bare `ThreadPoolExecutor.submit(...)`: NOT
    copied. Use `contextvars.copy_context().run` there.

These values are for logging/audit correlation only. They are never an
authorization input: who may do what is decided from the session in
app/db.py, not from anything a caller can influence through a header.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="-")
user_id_var: ContextVar[str] = ContextVar("user_id", default="-")


@contextmanager
def bind(*, trace_id: str | None = None, user_id: int | str | None = None) -> Iterator[None]:
    """Sets the given vars for the duration of the block and always restores
    the previous values (token.reset), even on exceptions."""
    tokens = []
    if trace_id is not None:
        tokens.append((trace_id_var, trace_id_var.set(trace_id)))
    if user_id is not None:
        tokens.append((user_id_var, user_id_var.set(str(user_id))))
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


def set_user(user_id: int | str) -> None:
    """For use after authentication inside a request that has no natural
    `with` block (a FastAPI dependency). The value lives until the request's
    task ends, because each request runs in its own task/context."""
    user_id_var.set(str(user_id))


_installed = False


def install_logging() -> None:
    """Stamps every log record with trace_id/user_id and gives the
    `resolveflow` logger a handler that prints them. Safe to call twice.

    Uses a LogRecord factory rather than a handler filter so it works for any
    handler (uvicorn's, pytest's caplog, ...), and never raises if a var is
    unset (the defaults are "-")."""
    global _installed
    if _installed:
        return
    _installed = True

    previous_factory = logging.getLogRecordFactory()

    def factory(*args, **kwargs):
        record = previous_factory(*args, **kwargs)
        record.trace_id = trace_id_var.get()
        record.user_id = user_id_var.get()
        return record

    logging.setLogRecordFactory(factory)

    logger = logging.getLogger("resolveflow")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s trace=%(trace_id)s user=%(user_id)s %(message)s")
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
