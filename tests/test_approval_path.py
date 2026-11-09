"""The real approval/resume path against a simulated GitHub API.

Drives graph/build.py's actual graph (fetch -> normalize -> classify ->
await_approval interrupt -> resume -> execute) with eval/fake_github.py in
place of GitHub. The fake has no idempotency keys, like the real API, so a
duplicate write shows up as a second comment.

The write ledger runs against an in-memory store always, and against
Postgres too when TEST_DATABASE_URL is set (CI provides a postgres service):

  TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres uv run pytest

No network, no API keys: the deterministic path (failing CI) never calls
an LLM or Pinecone.
"""

from __future__ import annotations

import os
import threading
import uuid

import pytest
import requests
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from eval.fake_github import FakeGitHub
from graph import credentials
from graph.build import graph as uncompiled_graph
from graph.resume import NothingToResume, resume_or_retry
from graph.serde import get_serde
from tools import side_effects

TOKEN = "ghu_test_visitor_token_51c9"
ISSUE_URL = "https://github.com/acme/widgets/issues/7"

STORE_KINDS = ["memory"] + (["postgres"] if os.environ.get("TEST_DATABASE_URL") else [])


@pytest.fixture(scope="module")
def pg_pool():
    if not os.environ.get("TEST_DATABASE_URL"):
        yield None
        return
    from psycopg_pool import ConnectionPool

    pool = ConnectionPool(os.environ["TEST_DATABASE_URL"], min_size=1, max_size=8, open=True)
    side_effects.PostgresSideEffectStore(pool).setup()
    yield pool
    pool.close()


@pytest.fixture(params=STORE_KINDS)
def store(request, pg_pool):
    if request.param == "memory":
        s = side_effects.InMemorySideEffectStore()
    else:
        with pg_pool.connection() as conn:
            conn.execute("TRUNCATE github_side_effects")
        s = side_effects.PostgresSideEffectStore(pg_pool)
    side_effects.configure(s)
    yield s
    side_effects.configure(side_effects.InMemorySideEffectStore())


@pytest.fixture
def run():
    """A compiled graph with its own checkpointer and a fresh thread id."""
    saver = MemorySaver(serde=get_serde())
    compiled = uncompiled_graph.compile(checkpointer=saver)
    config = {"configurable": {"thread_id": f"t-{uuid.uuid4().hex[:8]}"}}
    return compiled, saver, config


def _pause_at_approval(compiled, config, gh: FakeGitHub) -> dict:
    with gh.patched(), credentials.acting_as(TOKEN):
        paused = compiled.invoke({"issue_url": ISSUE_URL}, config)
    assert "__interrupt__" in paused, "expected the deterministic path to pause for approval"
    return paused


# --- 1. credentials stay out of checkpoints --------------------------------


def test_checkpoints_never_contain_the_user_token(store, run):
    compiled, saver, config = run
    gh = FakeGitHub()
    _pause_at_approval(compiled, config, gh)
    at_interrupt = repr(vars(saver))

    with gh.patched(), credentials.acting_as(TOKEN):
        compiled.invoke(Command(resume=True), config)
    after_execute = repr(vars(saver))

    assert "acme/widgets" in at_interrupt  # the scan really sees checkpoint contents
    assert TOKEN not in at_interrupt
    assert TOKEN not in after_execute
    assert len(gh.comments) == 1
    assert {tok for _, tok in gh.write_tokens} == {TOKEN}


def test_resume_without_credential_makes_zero_writes_then_retries_cleanly(store, run, monkeypatch):
    compiled, _, config = run
    gh = FakeGitHub()
    _pause_at_approval(compiled, config, gh)

    # The shared deployment token must not be used as a fallback for writes.
    monkeypatch.setenv("GITHUB_TOKEN", "shared-deployment-token")
    with gh.patched(), pytest.raises(credentials.MissingCredential):
        compiled.invoke(Command(resume=True), config)
    assert gh.writes == 0

    # Same run, now with the user's credential: the pending execute is
    # retried (no interrupt left to answer) and writes exactly once.
    with gh.patched(), credentials.acting_as(TOKEN):
        result = resume_or_retry(compiled, config, approved=True)
    assert len(gh.comments) == 1
    assert result["execution_result"]["comment"]["id"] == 1


# --- 2. the approval flow is safe to retry ---------------------------------


def test_concurrent_resumes_produce_one_comment(store, run):
    compiled, _, config = run
    gh = FakeGitHub(post_delay=0.2)  # widen the race window
    _pause_at_approval(compiled, config, gh)

    results, errors = [], []

    def resume_once():
        try:
            with credentials.acting_as(TOKEN):
                results.append(compiled.invoke(Command(resume=True), config))
        except Exception as exc:  # noqa: BLE001 -- collected and asserted below
            errors.append(exc)

    with gh.patched():
        threads = [threading.Thread(target=resume_once) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert errors == []
    assert len(gh.comments) == 1
    comment_results = [r["execution_result"]["comment"] for r in results]
    assert sum(1 for c in comment_results if c.get("id") == 1) >= 1
    assert all(c.get("id") == 1 or c == {"status": "in_progress"} for c in comment_results)


class _DiesAfterGitHubWrite:
    """Delegating store whose first 'comment' finish() raises, as if the worker
    died after GitHub accepted the comment but before the ledger recorded it."""

    def __init__(self, inner):
        self.inner = inner
        self.crashed = False

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def finish(self, thread_id, op, status, result):
        if op == "comment" and not self.crashed:
            self.crashed = True
            raise RuntimeError("worker died after the GitHub write")
        return self.inner.finish(thread_id, op, status, result)


def test_restart_after_posting_does_not_duplicate(store, run, monkeypatch):
    compiled, _, config = run
    gh = FakeGitHub()
    _pause_at_approval(compiled, config, gh)

    side_effects.configure(_DiesAfterGitHubWrite(store))
    with gh.patched(), credentials.acting_as(TOKEN), pytest.raises(RuntimeError):
        compiled.invoke(Command(resume=True), config)
    assert len(gh.comments) == 1  # GitHub has it; the ledger still says "claimed"

    # "Restart": healthy store over the same rows, and the claim is now stale.
    side_effects.configure(store)
    monkeypatch.setattr(side_effects, "STALE_AFTER_SECONDS", 0)
    with gh.patched(), credentials.acting_as(TOKEN):
        result = resume_or_retry(compiled, config, approved=True)

    assert len(gh.comments) == 1
    assert result["execution_result"]["comment"] == {
        "id": 1,
        "html_url": gh.comments[0]["html_url"],
        "adopted": True,
    }


def test_label_failure_preserves_the_successful_comment(store, run):
    compiled, _, config = run
    gh = FakeGitHub(label_status=403)
    _pause_at_approval(compiled, config, gh)

    with gh.patched(), credentials.acting_as(TOKEN):
        result = compiled.invoke(Command(resume=True), config)["execution_result"]
    assert result["comment"]["id"] == 1
    assert "403" in result["label_error"]

    # Re-running the write step for this thread replays both recorded
    # outcomes: no second comment, and the refused label isn't retried.
    from graph.nodes.execute import execute

    state = compiled.get_state(config).values
    with gh.patched(), credentials.acting_as(TOKEN):
        again = execute(state, config)["execution_result"]
    assert again == result
    assert len(gh.comments) == 1
    assert [op for op, _ in gh.write_tokens] == ["comment", "label"]


def test_finished_run_has_nothing_to_resume(store, run):
    compiled, _, config = run
    gh = FakeGitHub()
    _pause_at_approval(compiled, config, gh)
    with gh.patched(), credentials.acting_as(TOKEN):
        compiled.invoke(Command(resume=True), config)
        with pytest.raises(NothingToResume):
            resume_or_retry(compiled, config, approved=True)
    assert len(gh.comments) == 1


# --- ledger rules, directly -------------------------------------------------


def test_fresh_claim_is_never_stolen(store):
    gh = FakeGitHub()
    assert store.claim("t-fresh", "comment", 120)
    with gh.patched():
        out = side_effects.post_comment_once("t-fresh", "acme/widgets", 7, "body", TOKEN, stale_after=120)
    assert out == {"status": "in_progress"}
    assert gh.writes == 0


def test_client_error_releases_the_claim_for_an_immediate_retry(store):
    from unittest.mock import patch

    gh = FakeGitHub()

    def rejected(*args, **kwargs):
        response = requests.Response()
        response.status_code = 422
        raise requests.HTTPError("422 Unprocessable Entity", response=response)

    with gh.patched(), patch("tools.github_client.post_comment", rejected):
        with pytest.raises(requests.HTTPError):
            side_effects.post_comment_once("t-422", "acme/widgets", 7, "body", TOKEN)
    assert store.get("t-422", "comment") is None

    with gh.patched():
        out = side_effects.post_comment_once("t-422", "acme/widgets", 7, "body", TOKEN)
    assert out["id"] == 1
    assert len(gh.comments) == 1
