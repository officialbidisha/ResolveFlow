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

GitHub OAuth ("Sign in with GitHub") lets any visitor use the live app
under their own GitHub identity instead of the deployment owner's shared
GITHUB_TOKEN — see app/db.py for the session/rate-limit/thread-ownership
tables this needs, all in the same Postgres as the checkpointer (a
separate connection pool, since AsyncPostgresSaver owns its own schema
and shouldn't be reused for unrelated app tables). LLM/embedding calls
(generate_diagnosis, independent_review) still run on the deployment
owner's own OPENAI_API_KEY/PINECONE_API_KEY regardless of who's asking —
that's what the per-user daily analyze cap in app/db.py bounds.

The session cookie is SameSite=Lax + Secure. It used to be SameSite=None,
back when the browser talked to this API's *.onrender.com origin
directly from the *.vercel.app frontend — but that made the cookie a
cross-site ("third-party") cookie, which Chrome blocks outright
regardless of SameSite/Secure. Fixed by having frontend/vercel.json proxy
/api/* to this backend server-side, so the browser only ever talks to
its own origin; the cookie is first-party from the browser's point of
view even though this process is a different host underneath. Secure
still requires HTTPS, so the login round trip only fully works over a
real HTTPS deployment, not plain http://localhost — a known
local-dev-only gap (no proxy locally either), consistent with this
project's "not production-hardened" framing (see README).
"""

from __future__ import annotations

import os
import secrets
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel

from app import db
from graph.build import graph
from graph.serde import get_serde

DATABASE_URL = os.environ["DATABASE_URL"]
FRONTEND_URL = os.environ["FRONTEND_URL"]
GITHUB_OAUTH_CLIENT_ID = os.environ["GITHUB_OAUTH_CLIENT_ID"]
GITHUB_OAUTH_CLIENT_SECRET = os.environ["GITHUB_OAUTH_CLIENT_SECRET"]

SESSION_COOKIE = "session_id"

_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with (
        AsyncPostgresSaver.from_conn_string(DATABASE_URL, serde=get_serde()) as saver,
        # check=check_connection pings a pooled connection before handing it
        # out, transparently replacing it if it's dead — without this, a
        # connection killed server-side while idle in the pool (e.g. a
        # managed Postgres provider's autosuspend/idle-timeout sending
        # AdminShutdown) gets handed to the next request and blows up with
        # an unhandled psycopg.errors.AdminShutdown on first use.
        AsyncConnectionPool(DATABASE_URL, open=False, check=AsyncConnectionPool.check_connection) as pool,
    ):
        await saver.setup()
        await pool.open()
        await db.setup(pool)
        _state["compiled_graph"] = graph.compile(checkpointer=saver)
        _state["pool"] = pool
        yield
    _state.clear()


app = FastAPI(title="ResolveFlow API", lifespan=lifespan)

# Credentialed cookies require an explicit origin, not "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def current_user(request: Request) -> db.SessionUser:
    session_id = request.cookies.get(SESSION_COOKIE)
    user = await db.get_session_user(_state["pool"], session_id) if session_id else None
    if user is None:
        raise HTTPException(status_code=401, detail="not signed in")
    return user


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


@app.get("/api/auth/github/login")
async def github_login() -> RedirectResponse:
    state = secrets.token_urlsafe(24)
    # Persisted server-side (see app/db.py's oauth_states) rather than in a
    # cookie: this deployment is reachable on more than one Vercel domain
    # alias, but GitHub's OAuth callback always lands on the single one
    # registered for this OAuth App, so a cookie set on the *starting*
    # domain wouldn't reliably reach the callback.
    await db.insert_oauth_state(_state["pool"], state)
    # No explicit redirect_uri: this OAuth App has exactly one registered
    # callback URL, and GitHub uses that by default when it's omitted.
    return RedirectResponse(
        "https://github.com/login/oauth/authorize?"
        f"client_id={GITHUB_OAUTH_CLIENT_ID}&scope=public_repo&state={state}"
    )


@app.get("/api/auth/github/callback")
async def github_callback(request: Request, code: str, state: str) -> RedirectResponse:
    if not await db.consume_oauth_state(_state["pool"], state):
        raise HTTPException(status_code=400, detail="invalid OAuth state")

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": GITHUB_OAUTH_CLIENT_ID,
                "client_secret": GITHUB_OAUTH_CLIENT_SECRET,
                "code": code,
            },
        )
        if token_resp.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"GitHub token exchange request failed: {token_resp.status_code} {token_resp.text}",
            )
        token_json = token_resp.json()
        access_token = token_json.get("access_token")
        if not access_token:
            # Surface GitHub's actual error (e.g. "bad_verification_code",
            # "incorrect_client_credentials") instead of a generic message --
            # that's the only way to tell a wrong client secret apart from a
            # stale/already-used code from the client-facing error alone.
            raise HTTPException(
                status_code=400,
                detail=f"GitHub token exchange failed: {token_json.get('error', 'unknown')} "
                f"— {token_json.get('error_description', 'no description')}",
            )

        user_resp = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
        )
        if user_resp.status_code != 200:
            # A transient GitHub API failure (rate limit, brief outage) here
            # used to propagate as an unhandled httpx.HTTPStatusError, which
            # FastAPI turns into a bare 500 mid-redirect — worse than this
            # 502, which at least says which upstream call failed.
            raise HTTPException(
                status_code=502,
                detail=f"GitHub user lookup failed: {user_resp.status_code} {user_resp.text}",
            )
        gh_user = user_resp.json()

    session_id = await db.create_session(_state["pool"], gh_user["id"], gh_user["login"], access_token)

    redirect = RedirectResponse(FRONTEND_URL)
    redirect.set_cookie(
        SESSION_COOKIE, session_id, max_age=60 * 60 * 24 * 30, httponly=True, secure=True, samesite="lax"
    )
    return redirect


@app.get("/api/auth/me")
async def auth_me(user: db.SessionUser = Depends(current_user)) -> dict:
    return {"login": user.github_login}


@app.post("/api/auth/logout")
async def logout(request: Request, response: Response) -> dict:
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id:
        await db.delete_session(_state["pool"], session_id)
    response.delete_cookie(SESSION_COOKIE)
    return {"status": "ok"}


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest, user: db.SessionUser = Depends(current_user)) -> dict:
    if not await db.increment_and_check_daily_limit(_state["pool"], user.github_user_id):
        raise HTTPException(
            status_code=429, detail=f"daily analyze limit ({db.DAILY_ANALYZE_LIMIT}) reached — try again tomorrow"
        )

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    try:
        result = await _state["compiled_graph"].ainvoke(
            {"issue_url": req.issue_url, "github_token": user.github_token}, config
        )
    except Exception as exc:  # noqa: BLE001 -- surfacing any pipeline failure to the client is the point
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    await db.record_thread_owner(_state["pool"], thread_id, user.github_user_id)
    return _serialize(thread_id, result)


@app.post("/api/resume/{thread_id}")
async def resume(thread_id: str, req: ResumeRequest, user: db.SessionUser = Depends(current_user)) -> dict:
    owner_id = await db.get_thread_owner(_state["pool"], thread_id)
    if owner_id != user.github_user_id:
        raise HTTPException(status_code=403, detail="not the owner of this analysis run")

    config = {"configurable": {"thread_id": thread_id}}
    try:
        result = await _state["compiled_graph"].ainvoke(Command(resume=req.approved), config)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _serialize(thread_id, result)
