"""Bounds how many /api/analyze runs execute at once in this process.

Each analyze run fans out to OpenAI, Pinecone and GitHub, and runs its sync
graph nodes in worker threads. Without a cap, a burst of requests means a
burst of concurrent paid LLM calls, provider 429s, and worker-thread
exhaustion that also starves cheap endpoints like /api/health.

Per process, not global: Render runs up to `maxInstances: 3` of this app
(render.yaml), so the real ceiling is limit x instances. A global limit
would need shared state (Postgres/Redis), which this does not try to be.

The semaphore must be created inside the running event loop (the FastAPI
lifespan), not at import time: an asyncio.Semaphore is tied to the loop it
is first used on, and creating it at module import can bind it to the wrong
loop (or none).
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator


class GateBusy(Exception):
    """No slot became free within the wait budget."""


class AnalysisGate:
    def __init__(self, limit: int, wait_seconds: float) -> None:
        if limit < 1:
            raise ValueError("limit must be >= 1")
        self._sem = asyncio.Semaphore(limit)
        self._wait_seconds = wait_seconds

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        # Wait a bounded time, then shed load. Queueing forever would hold
        # the client's connection open and hide overload until the proxy
        # times out.
        try:
            await asyncio.wait_for(self._sem.acquire(), timeout=self._wait_seconds)
        except asyncio.TimeoutError:
            raise GateBusy from None
        # Acquired. The `finally` below is the only place it is released, so
        # an exception or cancellation (client disconnect) inside the body
        # can never leak a slot.
        try:
            yield
        finally:
            self._sem.release()
