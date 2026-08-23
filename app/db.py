"""App-level Postgres state: GitHub OAuth sessions, per-thread ownership,
and the daily per-user analyze cap. Separate from `graph/build.py`'s
`AsyncPostgresSaver`, which owns its own tables (LangGraph's checkpoint
schema) against the same DATABASE_URL — this module never touches those.

A session row holds the visitor's real GitHub access token server-side;
the browser only ever holds an opaque, random session_id in an httpOnly
cookie. That's what keeps a stolen/leaked cookie from being directly
usable outside this app's own session lookup, and keeps the token out of
anything client-visible (network tab, JS, logs of the frontend).
"""

from __future__ import annotations

import secrets
from datetime import date

from psycopg_pool import AsyncConnectionPool

DAILY_ANALYZE_LIMIT = 30

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id      TEXT PRIMARY KEY,
    github_user_id  BIGINT NOT NULL,
    github_login    TEXT NOT NULL,
    github_token    TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS thread_owners (
    thread_id       TEXT PRIMARY KEY,
    github_user_id  BIGINT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Server-side CSRF state for the OAuth handshake. Not a cookie: Vercel
-- gives this deployment more than one live domain alias (its short
-- <project>.vercel.app auto-alias alongside the canonical
-- <project>-<team>.vercel.app one this app's single GitHub OAuth callback
-- URL is registered against), and a visitor can start the login on either
-- one. A host-only cookie set on the *starting* domain never reaches the
-- callback when it lands on the *other* domain, so state must be looked
-- up here instead of read back from the browser.
CREATE TABLE IF NOT EXISTS oauth_states (
    state           TEXT PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS analyze_calls (
    github_user_id  BIGINT NOT NULL,
    day             DATE NOT NULL,
    count           INT NOT NULL DEFAULT 0,
    PRIMARY KEY (github_user_id, day)
);

CREATE TABLE IF NOT EXISTS feedback (
    id              SERIAL PRIMARY KEY,
    thread_id       TEXT NOT NULL,
    github_user_id  BIGINT NOT NULL,
    repo            TEXT NOT NULL,
    issue_number    INT NOT NULL,
    verdict         TEXT NOT NULL CHECK (verdict IN ('correct', 'incorrect', 'incomplete')),
    reason          TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_feedback_thread_id ON feedback(thread_id);
CREATE INDEX IF NOT EXISTS idx_feedback_repo_issue ON feedback(repo, issue_number);
"""


class SessionUser:
    def __init__(self, github_user_id: int, github_login: str, github_token: str):
        self.github_user_id = github_user_id
        self.github_login = github_login
        self.github_token = github_token


async def setup(pool: AsyncConnectionPool) -> None:
    async with pool.connection() as conn:
        await conn.execute(_SCHEMA)


async def create_session(pool: AsyncConnectionPool, github_user_id: int, github_login: str, github_token: str) -> str:
    session_id = secrets.token_urlsafe(32)
    async with pool.connection() as conn:
        await conn.execute(
            "INSERT INTO sessions (session_id, github_user_id, github_login, github_token) "
            "VALUES (%s, %s, %s, %s)",
            (session_id, github_user_id, github_login, github_token),
        )
    return session_id


async def get_session_user(pool: AsyncConnectionPool, session_id: str) -> SessionUser | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT github_user_id, github_login, github_token FROM sessions WHERE session_id = %s",
            (session_id,),
        )
        row = await cur.fetchone()
    return SessionUser(*row) if row else None


async def delete_session(pool: AsyncConnectionPool, session_id: str) -> None:
    async with pool.connection() as conn:
        await conn.execute("DELETE FROM sessions WHERE session_id = %s", (session_id,))


async def insert_oauth_state(pool: AsyncConnectionPool, state: str) -> None:
    async with pool.connection() as conn:
        await conn.execute("INSERT INTO oauth_states (state) VALUES (%s)", (state,))


async def consume_oauth_state(pool: AsyncConnectionPool, state: str) -> bool:
    """Single-use, 10-minute-TTL check: true iff `state` was issued and not yet consumed/expired."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            "DELETE FROM oauth_states WHERE state = %s AND created_at > now() - interval '10 minutes' "
            "RETURNING state",
            (state,),
        )
        row = await cur.fetchone()
    return row is not None


async def record_thread_owner(pool: AsyncConnectionPool, thread_id: str, github_user_id: int) -> None:
    async with pool.connection() as conn:
        await conn.execute(
            "INSERT INTO thread_owners (thread_id, github_user_id) VALUES (%s, %s)",
            (thread_id, github_user_id),
        )


async def get_thread_owner(pool: AsyncConnectionPool, thread_id: str) -> int | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT github_user_id FROM thread_owners WHERE thread_id = %s", (thread_id,)
        )
        row = await cur.fetchone()
    return row[0] if row else None


async def increment_and_check_daily_limit(pool: AsyncConnectionPool, github_user_id: int) -> bool:
    """Atomically increments today's analyze count for this user and
    returns whether they're still within DAILY_ANALYZE_LIMIT (True = ok).
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            "INSERT INTO analyze_calls (github_user_id, day, count) VALUES (%s, %s, 1) "
            "ON CONFLICT (github_user_id, day) DO UPDATE SET count = analyze_calls.count + 1 "
            "RETURNING count",
            (github_user_id, date.today()),
        )
        (count,) = await cur.fetchone()
    return count <= DAILY_ANALYZE_LIMIT


async def submit_feedback(
    pool: AsyncConnectionPool,
    thread_id: str,
    github_user_id: int,
    repo: str,
    issue_number: int,
    verdict: str,
    reason: str | None = None,
) -> None:
    """Store customer feedback on a diagnosis."""
    async with pool.connection() as conn:
        await conn.execute(
            "INSERT INTO feedback (thread_id, github_user_id, repo, issue_number, verdict, reason) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (thread_id, github_user_id, repo, issue_number, verdict, reason),
        )


async def get_feedback_by_issue(pool: AsyncConnectionPool, repo: str, issue_number: int) -> list[dict]:
    """Get all feedback for a specific issue."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT id, thread_id, github_user_id, verdict, reason, created_at "
            "FROM feedback WHERE repo = %s AND issue_number = %s "
            "ORDER BY created_at DESC",
            (repo, issue_number),
        )
        rows = await cur.fetchall()
    return [
        {
            "id": row[0],
            "thread_id": row[1],
            "github_user_id": row[2],
            "verdict": row[3],
            "reason": row[4],
            "created_at": row[5],
        }
        for row in rows
    ]


async def get_feedback_summary(pool: AsyncConnectionPool) -> dict:
    """Get aggregated feedback stats for monitoring."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT verdict, COUNT(*) as count FROM feedback GROUP BY verdict"
        )
        rows = await cur.fetchall()
    return {row[0]: row[1] for row in rows}
