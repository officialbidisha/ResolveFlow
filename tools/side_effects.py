"""Exactly-once GitHub writes for the approval path.

GitHub's comment API has no idempotency key, so "resume the same thread
twice" or "crash after posting, then retry" would post the comment twice.
This module records each approved write as its own operation row,
keyed by (thread_id, op), and claims the row before touching GitHub:

  claimed  a worker owns the operation; its outcome may be unknown
  done     the write happened; `result` is what execute() returns
  failed   the write was definitively rejected (labels only); terminal

Rules:
  * Only the worker that wins the claim may write. Concurrent resumes of
    one thread therefore produce one comment; the losers report
    "in_progress" or replay the recorded result.
  * The comment and the label are separate operations. A label failure is
    recorded on the label row and never touches the comment's result.
  * Every posted comment carries an invisible marker
    (<!-- resolveflow:<thread>:comment -->). Before posting, the claimant
    scans the issue for that marker. A worker that crashed after GitHub
    accepted the comment but before recording it leaves a stale "claimed"
    row; the next claimant (after STALE_AFTER_SECONDS) finds the marker and
    adopts that comment instead of posting again.
  * A fresh claim is never stolen: a slow worker may still be mid-request.
  * A 4xx from GitHub means the comment was not created, so the claim is
    released and an immediate retry may proceed. A timeout or 5xx leaves
    the outcome unknown, so the claim stays until it goes stale and the
    marker scan decides.

Production uses PostgresSideEffectStore (configured in app/main.py's
lifespan). InMemorySideEffectStore is the default for local scripts and
tests; it has the same claim semantics within one process.

This promotes docs/exactly-once/side_effects.py from a design demo into
the path execute() actually runs.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Protocol

import requests

from tools import github_client

STALE_AFTER_SECONDS = float(os.environ.get("SIDE_EFFECT_STALE_AFTER_SECONDS", "120"))

CLAIMED, DONE, FAILED = "claimed", "done", "failed"


@dataclass
class Record:
    status: str
    result: dict | None


class SideEffectStore(Protocol):
    def claim(self, thread_id: str, op: str, stale_after: float) -> bool: ...

    def get(self, thread_id: str, op: str) -> Record | None: ...

    def finish(self, thread_id: str, op: str, status: str, result: dict) -> None: ...

    def release(self, thread_id: str, op: str) -> None: ...


class InMemorySideEffectStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rows: dict[tuple[str, str], list] = {}  # key -> [status, result, claimed_at]

    def claim(self, thread_id: str, op: str, stale_after: float) -> bool:
        key = (thread_id, op)
        now = time.monotonic()
        with self._lock:
            row = self._rows.get(key)
            if row is None or (row[0] == CLAIMED and now - row[2] >= stale_after):
                self._rows[key] = [CLAIMED, None, now]
                return True
            return False

    def get(self, thread_id: str, op: str) -> Record | None:
        with self._lock:
            row = self._rows.get((thread_id, op))
            return Record(row[0], row[1]) if row else None

    def finish(self, thread_id: str, op: str, status: str, result: dict) -> None:
        with self._lock:
            self._rows[(thread_id, op)] = [status, result, time.monotonic()]

    def release(self, thread_id: str, op: str) -> None:
        with self._lock:
            row = self._rows.get((thread_id, op))
            if row and row[0] == CLAIMED:
                del self._rows[(thread_id, op)]


SCHEMA = """
CREATE TABLE IF NOT EXISTS github_side_effects (
    thread_id   TEXT NOT NULL,
    op          TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('claimed', 'done', 'failed')),
    result      JSONB,
    claimed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (thread_id, op)
)
"""


class PostgresSideEffectStore:
    """`pool` is a psycopg_pool.ConnectionPool (sync: execute() is a sync node
    running in a worker thread). Each method is one short transaction."""

    def __init__(self, pool) -> None:
        self.pool = pool

    def setup(self) -> None:
        with self.pool.connection() as conn:
            conn.execute(SCHEMA)

    def claim(self, thread_id: str, op: str, stale_after: float) -> bool:
        with self.pool.connection() as conn:
            row = conn.execute(
                """
                INSERT INTO github_side_effects (thread_id, op, status)
                VALUES (%s, %s, 'claimed')
                ON CONFLICT (thread_id, op) DO UPDATE
                    SET claimed_at = now(), updated_at = now(), result = NULL
                    WHERE github_side_effects.status = 'claimed'
                      AND github_side_effects.claimed_at < now() - make_interval(secs => %s)
                RETURNING 1
                """,
                (thread_id, op, float(stale_after)),
            ).fetchone()
        return row is not None

    def get(self, thread_id: str, op: str) -> Record | None:
        with self.pool.connection() as conn:
            row = conn.execute(
                "SELECT status, result FROM github_side_effects WHERE thread_id = %s AND op = %s",
                (thread_id, op),
            ).fetchone()
        return Record(row[0], row[1]) if row else None

    def finish(self, thread_id: str, op: str, status: str, result: dict) -> None:
        from psycopg.types.json import Jsonb

        with self.pool.connection() as conn:
            conn.execute(
                "UPDATE github_side_effects SET status = %s, result = %s, updated_at = now() "
                "WHERE thread_id = %s AND op = %s",
                (status, Jsonb(result), thread_id, op),
            )

    def release(self, thread_id: str, op: str) -> None:
        with self.pool.connection() as conn:
            conn.execute(
                "DELETE FROM github_side_effects WHERE thread_id = %s AND op = %s AND status = 'claimed'",
                (thread_id, op),
            )


_store: SideEffectStore = InMemorySideEffectStore()


def configure(store: SideEffectStore) -> None:
    global _store
    _store = store


def get_store() -> SideEffectStore:
    return _store


def marker(thread_id: str, op: str) -> str:
    return f"<!-- resolveflow:{thread_id}:{op} -->"


def _is_client_error(exc: requests.HTTPError) -> bool:
    status = getattr(exc.response, "status_code", None)
    return status is not None and 400 <= status < 500


def _comment_summary(comment: dict, adopted: bool = False) -> dict:
    summary = {"id": comment.get("id"), "html_url": comment.get("html_url")}
    if adopted:
        summary["adopted"] = True
    return summary


def post_comment_once(
    thread_id: str,
    repo: str,
    issue_number: int,
    body: str,
    token: str,
    *,
    store: SideEffectStore | None = None,
    stale_after: float | None = None,
) -> dict:
    store = store or _store
    stale = STALE_AFTER_SECONDS if stale_after is None else stale_after

    if not store.claim(thread_id, "comment", stale):
        record = store.get(thread_id, "comment")
        if record is not None and record.status == DONE:
            return record.result
        return {"status": "in_progress"}

    tag = marker(thread_id, "comment")
    try:
        existing = next(
            (c for c in github_client.list_issue_comments(repo, issue_number, token=token) if tag in (c.get("body") or "")),
            None,
        )
        if existing is not None:
            result = _comment_summary(existing, adopted=True)
        else:
            created = github_client.post_comment(repo, issue_number, f"{body}\n\n{tag}", token=token)
            result = _comment_summary(created)
    except requests.HTTPError as exc:
        if _is_client_error(exc):
            store.release(thread_id, "comment")
        raise
    except PermissionError:
        store.release(thread_id, "comment")
        raise

    store.finish(thread_id, "comment", DONE, result)
    return result


def add_label_once(
    thread_id: str,
    repo: str,
    issue_number: int,
    label: str,
    token: str,
    *,
    store: SideEffectStore | None = None,
    stale_after: float | None = None,
) -> dict:
    """Returns {"label": <GitHub response>} or {"label_error": <message>}.

    Adding a label GitHub already has is a no-op, so a stale claim can simply
    be retried; no marker is needed. A 4xx (typically: the acting user lacks
    triage access on someone else's repo) is recorded as a terminal failure.
    """
    store = store or _store
    stale = STALE_AFTER_SECONDS if stale_after is None else stale_after

    if not store.claim(thread_id, "label", stale):
        record = store.get(thread_id, "label")
        if record is not None and record.status in (DONE, FAILED):
            return record.result
        return {"label": {"status": "in_progress"}}

    try:
        labels = github_client.add_label(repo, issue_number, label, token=token)
    except requests.HTTPError as exc:
        if not _is_client_error(exc):
            raise
        result = {"label_error": str(exc)}
        store.finish(thread_id, "label", FAILED, result)
        return result

    result = {"label": labels}
    store.finish(thread_id, "label", DONE, result)
    return result
