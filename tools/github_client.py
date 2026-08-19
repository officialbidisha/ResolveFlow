"""Thin, typed GitHub REST client — deliberately not PyGithub.

A hand-rolled client keeps the surface area small and every call explicit,
which matters more here than convenience: this is the one place in the
pipeline that talks to a real external system, so its failure modes (rate
limits, 404s, auth errors) need to stay visible, not wrapped away behind a
general-purpose SDK. Every write operation (post_comment, add_label) is a
distinct, auditable function — graph/nodes/execute.py may only ever call
these, never construct a request itself.
"""

from __future__ import annotations

import os

import requests

GITHUB_API = "https://api.github.com"
TIMEOUT = 10


def _headers() -> dict:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is not set")
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


def get_issue(repo: str, issue_number: int) -> dict:
    resp = requests.get(f"{GITHUB_API}/repos/{repo}/issues/{issue_number}", headers=_headers(), timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def get_comments(repo: str, issue_number: int) -> list[dict]:
    resp = requests.get(
        f"{GITHUB_API}/repos/{repo}/issues/{issue_number}/comments", headers=_headers(), timeout=TIMEOUT
    )
    resp.raise_for_status()
    return resp.json()


def get_check_runs(repo: str, ref: str) -> list[dict]:
    """`ref` is a commit SHA — callers must resolve it from a linked PR first.
    Returns [] if there's no PR yet, since an issue with no code changes has
    no CI to speak of.
    """
    resp = requests.get(
        f"{GITHUB_API}/repos/{repo}/commits/{ref}/check-runs", headers=_headers(), timeout=TIMEOUT
    )
    resp.raise_for_status()
    return resp.json().get("check_runs", [])


def get_codeowners(repo: str) -> str | None:
    for path in (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"):
        resp = requests.get(
            f"{GITHUB_API}/repos/{repo}/contents/{path}",
            headers={**_headers(), "Accept": "application/vnd.github.raw"},
            timeout=TIMEOUT,
        )
        if resp.status_code == 200:
            return resp.text
    return None


def post_comment(repo: str, issue_number: int, body: str) -> dict:
    resp = requests.post(
        f"{GITHUB_API}/repos/{repo}/issues/{issue_number}/comments",
        headers=_headers(),
        json={"body": body},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def add_label(repo: str, issue_number: int, label: str) -> dict:
    resp = requests.post(
        f"{GITHUB_API}/repos/{repo}/issues/{issue_number}/labels",
        headers=_headers(),
        json={"labels": [label]},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()
