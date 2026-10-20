"""
Reference MCP server for interview discussion: a "setup agent" exposed over MCP.

This is an ILLUSTRATIVE reimplementation of the shape of the work, not the production code.
Say so in the interview. Production facts you can defend (from your drill notes):
  - the agent was exposed through a near-core proxy, session key (orgId, mcpSessionId, botId)
  - proxy timeout 60s with 2 retries
  - tool retrieval: top 5 at similarity >= 0.7; skill docs carry a `tools:` list -> enabled_tools
  - the first shipped version was ONE coarse tool wrapping the whole agent
What this file adds on top, and is labelled as design (not shipped): per-tool exposure,
identity from headers, write confirmation, and idempotency.

Run:  uv run --with "mcp<2" python mcp_server_reference.py          (stdio)
"""
from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import dataclass, field

from mcp.server.fastmcp import Context, FastMCP

mcp = FastMCP("setup-agent-mcp")

# --------------------------------------------------------------------------- tool catalog
# Fine-grained tools the agent can use internally. `writes` marks side effects.
CATALOG: dict[str, dict] = {
    "FindUser":            {"desc": "look up a user by name or email",            "writes": False},
    "FindPermissionSets":  {"desc": "list permission sets assigned to a user",    "writes": False},
    "FindPublicGroups":    {"desc": "list public groups a user belongs to",       "writes": False},
    "FindQueues":          {"desc": "list queues a user belongs to",              "writes": False},
    "AssignPermissionSet": {"desc": "assign a permission set to a user",          "writes": True},
    "DeactivateUser":      {"desc": "deactivate a user account",                  "writes": True},
}

TOP_K = 5
THRESHOLD = 0.7


def _tokens(s: str) -> set[str]:
    return set(re.findall(r"[a-z]+", s.lower()))


def score(query: str, desc: str) -> float:
    """Stand-in for embedding cosine similarity (Jaccard on tokens). Swap for a real embedder."""
    q, d = _tokens(query), _tokens(desc)
    return len(q & d) / len(q | d) if q | d else 0.0


def select_tools(query: str, k: int = TOP_K, threshold: float = THRESHOLD) -> list[str]:
    """Selective tool calling: narrow the menu BEFORE the LLM sees it.

    Fails open on nothing: if no tool clears the threshold we return [] and the caller must
    say 'I can't do that' rather than hand the model all tools (that is the failure mode
    selective calling exists to prevent).
    """
    ranked = sorted(CATALOG, key=lambda n: score(query, CATALOG[n]["desc"] + " " + n), reverse=True)
    return [n for n in ranked[:k] if score(query, CATALOG[n]["desc"] + " " + n) >= threshold]


# --------------------------------------------------------------------------- session state
@dataclass
class Session:
    org_id: str
    user_id: str
    enabled: set[str] = field(default_factory=set)
    pending_writes: dict[str, dict] = field(default_factory=dict)   # confirmation_id -> action
    done_keys: dict[str, dict] = field(default_factory=dict)        # idempotency_key -> result


SESSIONS: dict[tuple[str, str, str], Session] = {}   # (org_id, mcp_session_id, bot_id)


def identity(ctx: Context) -> tuple[str, str, str]:
    """DESIGN: derive identity from transport headers, never from tool arguments.

    The model controls tool arguments, so an `org_id` argument is attacker-controlled via
    prompt injection. Headers are set by the trusted proxy. (In the shipped version the
    user-identity header was not read - own that if asked.)
    """
    req = ctx.request_context.request          # present on HTTP transports; None on stdio
    h = req.headers if req is not None else {}
    org = h.get("x-org-id", "dev-org")
    user = h.get("x-sfdc-user-id", "dev-user")
    sid = h.get("mcp-session-id", "stdio")
    return org, user, sid


def get_session(ctx: Context, bot_id: str = "setup-bot") -> Session:
    org, user, sid = identity(ctx)
    return SESSIONS.setdefault((org, sid, bot_id), Session(org_id=org, user_id=user))


# --------------------------------------------------------------------------- tool execution
async def run_tool(name: str, args: dict) -> dict:
    """Stub for the real backend call (proxy -> core). Real one: 60s timeout, 2 retries,
    retry ONLY reads - a retried write without an idempotency key can double-apply."""
    await asyncio.sleep(0)
    return {"tool": name, "args": args, "ok": True}


# --------------------------------------------------------------------------- MCP surface
@mcp.tool()
async def ask_setup_agent(utterance: str, ctx: Context) -> dict:
    """COARSE tool (what shipped first): hand the whole request to the agent.

    Pro: tiny surface, the agent keeps planning internally, easy to onboard teams.
    Con: the calling model gets no visibility, no per-step permissions or approvals,
    and latency is the whole agent run (p50 ~35s, p95 ~98s in the local sample),
    which is uncomfortably close to a 60s proxy timeout.
    """
    s = get_session(ctx)
    s.enabled = set(select_tools(utterance))
    if not s.enabled:
        return {"status": "no_capable_tool", "message": "No setup tool matches this request."}

    results = []
    for name in sorted(s.enabled):
        if CATALOG[name]["writes"]:
            cid = str(uuid.uuid4())
            s.pending_writes[cid] = {"tool": name, "utterance": utterance}
            results.append({"tool": name, "status": "needs_confirmation", "confirmation_id": cid})
        else:
            results.append(await run_tool(name, {"utterance": utterance}))
    return {"status": "ok", "enabled_tools": sorted(s.enabled), "results": results}


@mcp.tool()
async def find_tools(query: str, ctx: Context) -> list[dict]:
    """Fine-grained alternative: let the client discover which tools apply to a request
    (retrieval-based narrowing exposed as a tool) instead of dumping the full catalog."""
    return [{"name": n, "description": CATALOG[n]["desc"], "writes": CATALOG[n]["writes"]}
            for n in select_tools(query)]


@mcp.tool()
async def confirm_action(confirmation_id: str, idempotency_key: str, ctx: Context) -> dict:
    """Execute a pending write after explicit user approval. Idempotent on `idempotency_key`
    so a retry after a timeout cannot apply the write twice."""
    s = get_session(ctx)
    if idempotency_key in s.done_keys:
        return s.done_keys[idempotency_key]
    action = s.pending_writes.pop(confirmation_id, None)
    if action is None:
        return {"status": "error", "message": "unknown or expired confirmation_id"}
    result = await run_tool(action["tool"], {"utterance": action["utterance"]})
    s.done_keys[idempotency_key] = result
    return result


if __name__ == "__main__":
    mcp.run()   # stdio; use mcp.run(transport="streamable-http") behind the proxy
