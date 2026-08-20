"""Normalized shape of everything we know about a GitHub issue before diagnosis.

This is the contract between evidence-fetching (tools/github_client.py) and
every downstream graph node — nothing past `normalize_evidence` should ever
touch a raw GitHub API response again.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

_TEMPLATE_NOISE = re.compile(r"^(#{1,6}\s|<!--|-->|-\s*\[[ xX]\]\s)")


class CheckRun(BaseModel):
    name: str
    conclusion: str | None  # "success" | "failure" | "neutral" | None (still running)


class LinkedPR(BaseModel):
    number: int
    title: str
    state: str
    merged: bool


class IssueEvidence(BaseModel):
    repo: str
    issue_number: int
    title: str
    body: str
    labels: list[str] = Field(default_factory=list)
    comments: list[str] = Field(default_factory=list)
    linked_prs: list[LinkedPR] = Field(default_factory=list)
    check_runs: list[CheckRun] = Field(default_factory=list)
    files_touched: list[str] = Field(default_factory=list)
    owner_hint: str | None = None

    @property
    def has_failing_ci(self) -> bool:
        return any(c.conclusion == "failure" for c in self.check_runs)

    @property
    def is_information_sparse(self) -> bool:
        """True if the body has under 40 chars of real content once markdown
        template scaffolding (headers, checkboxes, HTML comments) is
        stripped out — not raw body length.

        Raw length doesn't work on repos with issue templates: template
        boilerplate ("## Describe the bug", checkbox lists) pads every
        report past any reasonable threshold regardless of how little the
        reporter actually wrote. This also doesn't require zero comments —
        a triage/bot comment says nothing about how much the *reporter*
        actually said.
        """
        body = self.body.strip()
        # Some issue bodies contain literal "\n" text instead of real line
        # breaks (a paste/formatting artifact seen on real GitHub issues,
        # not hypothetical) — with no real newlines, the whole body reads
        # as one "line" and a leading "## Header" would wrongly discard
        # the entire thing as boilerplate. Only unescape when there's no
        # genuine newline already, so real code blocks containing "\n"
        # text elsewhere aren't touched.
        if "\n" not in body and "\\n" in body:
            body = body.replace("\\n", "\n")
        lines = (line.strip() for line in body.splitlines())
        content = " ".join(line for line in lines if line and not _TEMPLATE_NOISE.match(line))
        return len(content) < 40
