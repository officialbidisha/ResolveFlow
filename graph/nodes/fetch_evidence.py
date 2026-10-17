"""Day 1. Reads: issue_url. Writes: raw_evidence — hands raw API
responses to normalize_evidence rather than building IssueEvidence itself,
so a GitHub API shape change only touches one function.

Parse `issue_url` -> (repo, issue_number), call tools.github_client.get_issue
+ get_comments + get_codeowners. Return the raw dicts under raw_evidence;
do not construct IssueEvidence here.

CI check runs require a commit SHA, which only exists on a linked PR, so
get_linked_pull_request is tried first; if the issue has no linked PR yet,
check_runs stays []. The deterministic classification branch is still
exercised via synthetic fixtures in tests/test_classify.py rather than
requiring a live linked-PR lookup.
"""

from __future__ import annotations

import asyncio
import re

from graph.state import GraphState
from tools import github_client

_ISSUE_URL_RE = re.compile(r"github\.com/([^/]+/[^/]+)/issues/(\d+)")


def _parse_issue_url(issue_url: str) -> tuple[str, int]:
    match = _ISSUE_URL_RE.search(issue_url)
    if not match:
        raise ValueError(f"could not parse issue URL: {issue_url!r}")
    return match.group(1), int(match.group(2))


def fetch_evidence(state: GraphState) -> dict:
    """Sequential version. Kept as the reference implementation and for
    sync callers (graph.invoke, the eval harness); the deployed async path
    uses afetch_evidence below, and graph/build.py registers both."""
    repo, issue_number = _parse_issue_url(state["issue_url"])
    token = state.get("github_token")

    linked_pr = github_client.get_linked_pull_request(repo, issue_number, token=token)
    check_runs = (
        github_client.get_check_runs(repo, linked_pr["head"]["sha"], token=token) if linked_pr else []
    )

    raw_evidence = {
        "repo": repo,
        "issue_number": issue_number,
        "issue": github_client.get_issue(repo, issue_number, token=token),
        "comments": github_client.get_comments(repo, issue_number, token=token),
        "codeowners": github_client.get_codeowners(repo, token=token),
        "check_runs": check_runs,
    }

    return {"raw_evidence": raw_evidence}


async def afetch_evidence(state: GraphState) -> dict:
    """Same result as fetch_evidence, but the independent GitHub reads run
    concurrently.

    Dependency shape: issue, comments and codeowners need nothing from each
    other; check_runs needs the linked PR's head SHA, which needs the
    timeline lookup first. So that pair stays sequential (one chain) while
    the chain and the three other reads overlap. Wall time drops from the
    sum of all calls to roughly the longest chain.

    Why asyncio.to_thread and not an async HTTP client: tools/github_client.py
    is deliberately a thin `requests` client (see its docstring) and is also
    used by ingest.py and the sync path. `requests` is blocking, but a thread
    blocked on a socket releases the GIL, so these threads genuinely overlap.
    This work is network-bound, so the GIL is not the limit here. to_thread
    also copies the current contextvars into the worker thread, so trace/user
    ids from graph/request_context.py are visible inside github_client.

    Why gather and not TaskGroup: a thread already running a blocking
    `requests` call cannot be cancelled, so TaskGroup's "cancel the siblings
    on first failure" would not actually stop them. gather re-raises the
    first exception unchanged (requests.HTTPError), which app/main.py turns
    into its 502 detail; TaskGroup would wrap it in an ExceptionGroup and
    degrade that message. These are read-only calls, so letting the
    stragglers finish is harmless.
    """
    repo, issue_number = _parse_issue_url(state["issue_url"])
    token = state.get("github_token")

    async def pr_then_checks() -> list:
        linked_pr = await asyncio.to_thread(
            github_client.get_linked_pull_request, repo, issue_number, token=token
        )
        if not linked_pr:
            return []
        return await asyncio.to_thread(
            github_client.get_check_runs, repo, linked_pr["head"]["sha"], token=token
        )

    issue, comments, codeowners, check_runs = await asyncio.gather(
        asyncio.to_thread(github_client.get_issue, repo, issue_number, token=token),
        asyncio.to_thread(github_client.get_comments, repo, issue_number, token=token),
        asyncio.to_thread(github_client.get_codeowners, repo, token=token),
        pr_then_checks(),
    )

    return {
        "raw_evidence": {
            "repo": repo,
            "issue_number": issue_number,
            "issue": issue,
            "comments": comments,
            "codeowners": codeowners,
            "check_runs": check_runs,
        }
    }
