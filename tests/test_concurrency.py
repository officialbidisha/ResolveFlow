"""Concurrency behaviour: async fetch fan-out, ContextVar propagation, and the
analyze gate. No network, no API keys -- GitHub calls are replaced with
sleeping fakes so timing differences are real but deterministic enough.

Run with: uv run pytest tests/test_concurrency.py
(pytest-asyncio is not a dependency, so async code runs via asyncio.run.)
"""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
import time
import types

import pytest
import requests

from app.limits import AnalysisGate, GateBusy
from graph import request_context
from graph.nodes import fetch_evidence as fe
from tools import github_client

DELAY = 0.15


@pytest.fixture
def fake_github(monkeypatch):
    """Each fake sleeps DELAY (a blocking call, like `requests`) and records
    which thread ran it."""
    calls: list[tuple[str, int]] = []

    def slow(name, value):
        def fn(*args, **kwargs):
            calls.append((name, threading.get_ident()))
            time.sleep(DELAY)
            return value
        return fn

    pr = {"head": {"sha": "abc123"}}
    monkeypatch.setattr(github_client, "get_issue", slow("issue", {"title": "t", "body": "b", "labels": []}))
    monkeypatch.setattr(github_client, "get_comments", slow("comments", []))
    monkeypatch.setattr(github_client, "get_codeowners", slow("codeowners", "* @owner"))
    monkeypatch.setattr(github_client, "get_linked_pull_request", slow("pr", pr))
    monkeypatch.setattr(github_client, "get_check_runs", slow("checks", [{"name": "ci", "conclusion": "failure"}]))
    return calls


STATE = {"issue_url": "https://github.com/acme/widgets/issues/7", "github_token": "tok"}


# --- asyncio fan-out -------------------------------------------------------


def test_async_fetch_matches_sync_result(fake_github):
    assert asyncio.run(fe.afetch_evidence(STATE)) == fe.fetch_evidence(STATE)


def test_async_fetch_overlaps_independent_calls(fake_github):
    start = time.perf_counter()
    fe.fetch_evidence(STATE)
    sequential = time.perf_counter() - start

    start = time.perf_counter()
    asyncio.run(fe.afetch_evidence(STATE))
    concurrent = time.perf_counter() - start

    # 5 calls sequentially ~ 5*DELAY. Async: the pr->checks chain (2*DELAY)
    # overlaps issue/comments/codeowners, so ~2*DELAY.
    assert sequential >= 4.5 * DELAY
    assert concurrent < 3 * DELAY
    assert concurrent < sequential / 1.5


def test_async_fetch_runs_blocking_calls_on_worker_threads(fake_github):
    asyncio.run(fe.afetch_evidence(STATE))
    assert threading.get_ident() not in {tid for _, tid in fake_github}


def test_check_runs_only_fetched_after_linked_pr(fake_github, monkeypatch):
    monkeypatch.setattr(github_client, "get_linked_pull_request", lambda *a, **k: None)
    result = asyncio.run(fe.afetch_evidence(STATE))
    assert result["raw_evidence"]["check_runs"] == []
    assert "checks" not in [name for name, _ in fake_github]


def test_async_fetch_propagates_original_exception_type(fake_github, monkeypatch):
    def boom(*a, **k):
        raise requests.HTTPError("404 Not Found")

    monkeypatch.setattr(github_client, "get_issue", boom)
    with pytest.raises(requests.HTTPError):
        asyncio.run(fe.afetch_evidence(STATE))


def test_bad_url_still_raises_value_error():
    with pytest.raises(ValueError):
        asyncio.run(fe.afetch_evidence({"issue_url": "not a url"}))


# --- ContextVar ------------------------------------------------------------


def test_context_reaches_to_thread_workers():
    async def main():
        with request_context.bind(trace_id="t-1", user_id=42):
            return await asyncio.to_thread(lambda: (request_context.trace_id_var.get(), request_context.user_id_var.get()))

    assert asyncio.run(main()) == ("t-1", "42")


def test_concurrent_tasks_do_not_see_each_others_context():
    seen = {}

    async def request(name: str, delay: float):
        with request_context.bind(trace_id=name):
            await asyncio.sleep(delay)  # interleave with the other task
            seen[name] = await asyncio.to_thread(request_context.trace_id_var.get)

    async def main():
        await asyncio.gather(request("A", 0.05), request("B", 0.01), request("C", 0.03))

    asyncio.run(main())
    assert seen == {"A": "A", "B": "B", "C": "C"}


def test_bind_restores_previous_value_even_on_error():
    with request_context.bind(trace_id="outer"):
        with pytest.raises(RuntimeError):
            with request_context.bind(trace_id="inner"):
                raise RuntimeError
        assert request_context.trace_id_var.get() == "outer"
    assert request_context.trace_id_var.get() == "-"


def test_plain_threading_thread_does_not_inherit_context():
    """Documents the caveat in request_context's docstring: only to_thread /
    executors that copy the context propagate it. A bare Thread starts empty."""
    out = []
    with request_context.bind(trace_id="main-thread"):
        t = threading.Thread(target=lambda: out.append(request_context.trace_id_var.get()))
        t.start()
        t.join()
    assert out == ["-"]


def test_langgraph_sync_node_sees_request_context():
    """The claim execute.py relies on: LangGraph runs sync nodes in a thread
    pool under ainvoke, and the caller's context comes along."""
    from typing import TypedDict

    from langgraph.graph import END, StateGraph

    class S(TypedDict, total=False):
        seen: str

    def node(state: S) -> dict:
        return {"seen": request_context.trace_id_var.get()}

    g = StateGraph(S)
    g.add_node("n", node)
    g.set_entry_point("n")
    g.add_edge("n", END)
    compiled = g.compile()

    async def main():
        with request_context.bind(trace_id="via-graph"):
            return await compiled.ainvoke({})

    assert asyncio.run(main())["seen"] == "via-graph"


def test_log_records_carry_trace_and_user():
    request_context.install_logging()
    records: list[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    logger = logging.getLogger("resolveflow.test")
    logger.addHandler(Capture())
    logger.setLevel(logging.INFO)
    with request_context.bind(trace_id="abc", user_id=7):
        logger.info("hello")
    logger.info("outside")
    assert (records[0].trace_id, records[0].user_id) == ("abc", "7")
    assert (records[1].trace_id, records[1].user_id) == ("-", "-")


# --- Semaphore / AnalysisGate ---------------------------------------------


def test_gate_never_exceeds_limit():
    async def main():
        gate = AnalysisGate(limit=2, wait_seconds=5)
        in_flight = peak = 0

        async def job():
            nonlocal in_flight, peak
            async with gate.slot():
                in_flight += 1
                peak = max(peak, in_flight)
                await asyncio.sleep(0.02)
                in_flight -= 1

        await asyncio.gather(*(job() for _ in range(10)))
        return peak

    assert asyncio.run(main()) == 2


def test_gate_sheds_load_after_wait_budget():
    async def main():
        gate = AnalysisGate(limit=1, wait_seconds=0.05)
        async with gate.slot():
            with pytest.raises(GateBusy):
                async with gate.slot():
                    pytest.fail("should not have been admitted")

    asyncio.run(main())


def test_gate_releases_slot_when_body_raises():
    async def main():
        gate = AnalysisGate(limit=1, wait_seconds=0.05)
        with pytest.raises(ValueError):
            async with gate.slot():
                raise ValueError
        async with gate.slot():  # would raise GateBusy if the slot leaked
            return True

    assert asyncio.run(main()) is True


def test_gate_releases_slot_when_task_is_cancelled():
    async def main():
        gate = AnalysisGate(limit=1, wait_seconds=0.05)

        async def holder():
            async with gate.slot():
                await asyncio.sleep(10)

        task = asyncio.create_task(holder())
        await asyncio.sleep(0.01)
        task.cancel()  # e.g. client disconnected mid-request
        with pytest.raises(asyncio.CancelledError):
            await task
        async with gate.slot():
            return True

    assert asyncio.run(main()) is True


def test_gate_rejects_nonpositive_limit():
    async def main():
        with pytest.raises(ValueError):
            AnalysisGate(limit=0, wait_seconds=1)

    asyncio.run(main())


# --- graph wiring ----------------------------------------------------------


@pytest.fixture
def built_graph(monkeypatch):
    """Imports graph.build with tools.retrieval stubbed: the real module
    opens a Pinecone connection at import time and needs live API keys."""
    stub = types.ModuleType("tools.retrieval")
    stub.retrieve_evidence = lambda *a, **k: []
    monkeypatch.setitem(sys.modules, "tools.retrieval", stub)
    for name in ("graph.build", "graph.nodes.generate_diagnosis"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    import graph.build as build

    return build


def test_graph_runs_async_and_sync_paths_to_same_evidence(built_graph, fake_github):
    def run(config_id):
        return {"configurable": {"thread_id": config_id}}

    async_result = asyncio.run(built_graph.compiled_graph.ainvoke(dict(STATE), run("async")))
    sync_result = built_graph.compiled_graph.invoke(dict(STATE), run("sync"))

    assert async_result["evidence"] == sync_result["evidence"]
    assert async_result["classification"] == sync_result["classification"] == "deterministic"
