"""In-process stand-in for the GitHub REST API, used by eval/harness.py and
tests/. Like the real API it has no idempotency keys: every post_comment
call creates a new comment, so duplicate writes are visible as duplicates.

`patched()` swaps it in for tools/github_client.py's functions, which is
the only module that talks to GitHub. Nothing here touches the network.
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from typing import Iterator
from unittest.mock import patch

import requests

_PATCHED = (
    "get_issue",
    "get_comments",
    "list_issue_comments",
    "get_codeowners",
    "get_linked_pull_request",
    "get_check_runs",
    "post_comment",
    "add_label",
)


class FakeGitHub:
    def __init__(self, *, failing_ci: bool = True, label_status: int | None = None, post_delay: float = 0.0):
        self.failing_ci = failing_ci
        self.label_status = label_status  # e.g. 403: add_label raises like GitHub would
        self.post_delay = post_delay  # widens race windows in concurrency tests
        self.comments: list[dict] = []
        self.labels: list[str] = []
        self.write_tokens: list[tuple[str, str]] = []  # (op, token) for every write attempt that reached "GitHub"
        self._lock = threading.Lock()

    # --- reads ---------------------------------------------------------------

    def get_issue(self, repo, issue_number, token=None):
        return {"title": "Build broken on main", "body": "CI fails after the last merge.", "labels": []}

    def get_comments(self, repo, issue_number, token=None):
        with self._lock:
            return [dict(c) for c in self.comments[:30]]

    def list_issue_comments(self, repo, issue_number, token=None, max_pages=50):
        with self._lock:
            return [dict(c) for c in self.comments]

    def get_codeowners(self, repo, token=None):
        return "* @maintainer"

    def get_linked_pull_request(self, repo, issue_number, token=None):
        return {"head": {"sha": "abc123"}} if self.failing_ci else None

    def get_check_runs(self, repo, ref, token=None):
        return [{"name": "ci", "conclusion": "failure"}]

    # --- writes --------------------------------------------------------------

    def post_comment(self, repo, issue_number, body, token=None):
        if not token:
            raise PermissionError("GitHub writes require an explicit acting-user token")
        time.sleep(self.post_delay)
        with self._lock:
            comment_id = len(self.comments) + 1
            comment = {
                "id": comment_id,
                "body": body,
                "html_url": f"https://github.com/{repo}/issues/{issue_number}#issuecomment-{comment_id}",
            }
            self.comments.append(comment)
            self.write_tokens.append(("comment", token))
            return dict(comment)

    def add_label(self, repo, issue_number, label, token=None):
        if not token:
            raise PermissionError("GitHub writes require an explicit acting-user token")
        with self._lock:
            self.write_tokens.append(("label", token))
            if self.label_status:
                response = requests.Response()
                response.status_code = self.label_status
                raise requests.HTTPError(f"{self.label_status} Client Error: label refused", response=response)
            if label not in self.labels:
                self.labels.append(label)
            return [{"name": name} for name in self.labels]

    @property
    def writes(self) -> int:
        with self._lock:
            return len(self.write_tokens)

    @contextmanager
    def patched(self) -> Iterator["FakeGitHub"]:
        with patch.multiple("tools.github_client", **{name: getattr(self, name) for name in _PATCHED}):
            yield self
