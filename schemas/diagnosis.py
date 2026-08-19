"""Structured output the diagnosis LLM call must produce.

Enforced via LangChain's `.with_structured_output(Diagnosis)`, not parsed
out of free text after the fact — the model is constrained to this shape
at generation time.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Diagnosis(BaseModel):
    root_cause: str
    severity: Literal["low", "medium", "high"]
    missing_info: list[str] = Field(default_factory=list)
    recommended_next_steps: list[str]
    citations: list[str] = Field(
        default_factory=list,
        description="IDs of retrieved evidence/doc snippets that support each claim above",
    )
