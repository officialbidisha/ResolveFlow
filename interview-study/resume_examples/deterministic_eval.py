"""Deterministic eval: no LLM judge, no network, same result every run. Exit code gates CI.

Covers: routing accuracy, retrieval hit, permission enforcement (negative tests), structured
output validation, groundedness, and a replayed production failure.
Run: uv run python deterministic_eval.py
"""
from __future__ import annotations

import json
import sys

import adaptive_rag as rag
import slack_bolt_example as slack

ROUTING = [("hello", "direct"), ("reset password for a user", "single"),
           ("permission sets and public groups", "multi"), ("thanks", "direct")]
RETRIEVAL = [("how do I reset a user password", "doc1"), ("what do queues own", "doc4")]
PERMISSION = [  # (slack_user, op, expected_allowed) <- the negative cases matter most
    ("U_ALICE", "AddUserToQueue", True),
    ("U_BOB", "AddUserToQueue", False),        # user without access must be refused
    ("U_ALICE", "DeleteOrg", False),           # not on the allowlist
    ("U_UNKNOWN", "AddUserToQueue", False),    # unmapped Slack user
]
SCHEMA_REQUIRED = {"op": str, "args": dict}


def valid_proposal(raw: str) -> bool:
    """Structured-output contract: JSON, exact required keys with right types, op on allowlist."""
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return False
    return (set(obj) == set(SCHEMA_REQUIRED)
            and all(isinstance(obj[k], t) for k, t in SCHEMA_REQUIRED.items())
            and obj["op"] in slack.ALLOWLIST)


# Replayed production failures: recorded model outputs that once broke something. Frozen forever.
REPLAYED = [
    ('{"op": "AddUserToQueue", "args": {"queue": "Support"}}', True),
    ('Sure! {"op": "AddUserToQueue"}', False),                  # prose around JSON
    ('{"op": "DropAllUsers", "args": {}}', False),              # hallucinated tool
    ('{"op": "AddUserToQueue", "args": "Support"}', False),     # wrong type
]


def run() -> dict[str, tuple[int, int]]:
    out = {}
    out["routing"] = (sum(rag.classify(q) == e for q, e in ROUTING), len(ROUTING))
    out["retrieval"] = (sum(rag.retrieve(q)[0][0] == d for q, d in RETRIEVAL), len(RETRIEVAL))
    out["permission"] = (sum(slack.authorize(slack.SLACK_TO_SFDC.get(u), op) == ok for u, op, ok in PERMISSION), len(PERMISSION))
    out["schema_replay"] = (sum(valid_proposal(r) == ok for r, ok in REPLAYED), len(REPLAYED))
    r = rag.answer("banana smoothie recipe")                    # must abstain, not invent
    out["abstain_on_no_evidence"] = (int(r.evidence == [] and rag.grounded(r)), 1)
    return out


# Per-category floors. Permission is a hard 100%: one leak blocks the release.
FLOORS = {"routing": 0.9, "retrieval": 0.9, "permission": 1.0, "schema_replay": 1.0, "abstain_on_no_evidence": 1.0}

if __name__ == "__main__":
    failed = False
    for cat, (ok, n) in run().items():
        rate = ok / n
        flag = "PASS" if rate >= FLOORS[cat] else "FAIL"
        failed |= flag == "FAIL"
        print(f"{flag}  {cat:24} {ok}/{n}  floor={FLOORS[cat]:.0%}")
    sys.exit(1 if failed else 0)
