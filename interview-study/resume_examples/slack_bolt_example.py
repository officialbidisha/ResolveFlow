"""Slack Bolt (Python) agent skeleton: ack fast, approve with Block Kit, run as the requester.

Illustrative. Run (needs a Slack app + tokens):
  SLACK_BOT_TOKEN=xoxb-... SLACK_APP_TOKEN=xapp-... uv run --with slack-bolt python slack_bolt_example.py
The pure helpers below are testable without Slack; deterministic_eval.py imports them.
"""
from __future__ import annotations

import os
import uuid

ALLOWLIST = {"AddUserToQueue", "AssignPermissionSet"}                   # operation allowlist
SLACK_TO_SFDC = {"U_ALICE": "sf-alice", "U_BOB": "sf-bob"}               # real: SSO/identity lookup
SFDC_PERMS = {"sf-alice": {"AddUserToQueue"}, "sf-bob": set()}           # real: ask Company W, not a dict
PENDING: dict[str, dict] = {}                                            # real: Redis/DB with TTL
DONE: set[str] = set()                                                   # idempotency


def authorize(sfdc_user: str | None, op: str) -> bool:
    """Deterministic gate. The model never decides this."""
    return sfdc_user is not None and op in ALLOWLIST and op in SFDC_PERMS.get(sfdc_user, set())


def approval_blocks(request_id: str, summary: str) -> list[dict]:
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Approval needed*\n{summary}"}},
        {"type": "actions", "block_id": "approval", "elements": [
            {"type": "button", "action_id": "approve", "style": "primary", "value": request_id,
             "text": {"type": "plain_text", "text": "Approve"}},
            {"type": "button", "action_id": "reject", "style": "danger", "value": request_id,
             "text": {"type": "plain_text", "text": "Reject"}},
        ]},
    ]


def propose(slack_user: str, op: str, args: dict) -> tuple[str, list[dict]] | tuple[None, str]:
    """Called after the LLM proposed (op, args). Code validates before the human is even asked."""
    sf = SLACK_TO_SFDC.get(slack_user)
    if not authorize(sf, op):
        return None, f"You are not allowed to run `{op}`."
    rid = str(uuid.uuid4())
    PENDING[rid] = {"slack_user": slack_user, "sf_user": sf, "op": op, "args": args}
    return rid, approval_blocks(rid, f"`{op}` with `{args}` as you ({sf})")


def execute(request_id: str, clicker: str) -> str:
    """Runs on Approve. Re-checks everything: the click is untrusted input."""
    if request_id in DONE:
        return "Already executed."                                       # double-click / Slack retry
    req = PENDING.get(request_id)
    if req is None:
        return "Request expired."
    if clicker != req["slack_user"]:
        return "Only the requester can approve."                         # no approving someone else's request
    if not authorize(req["sf_user"], req["op"]):                         # permissions may have changed
        return "Not permitted any more."
    DONE.add(request_id)
    PENDING.pop(request_id, None)
    return f"Executed {req['op']} as {req['sf_user']}"                   # real: call API with THEIR token


def build_app():
    from slack_bolt import App
    app = App(token=os.environ["SLACK_BOT_TOKEN"])

    @app.event("app_mention")
    def on_mention(event, say, ack=None):
        # Events API: Bolt acks the HTTP request for you; do slow LLM work off the request thread.
        op, args = "AddUserToQueue", {"queue": "Support", "user": "carol"}   # real: LLM proposal + schema validation
        rid, blocks = propose(event["user"], op, args)
        if rid is None:
            say(blocks, thread_ts=event["ts"])
        else:
            say(blocks=blocks, text="Approval needed", thread_ts=event["ts"])

    @app.action("approve")
    def on_approve(ack, body, respond):
        ack()                                                            # MUST be within 3 seconds
        respond(replace_original=True, text=execute(body["actions"][0]["value"], body["user"]["id"]))

    @app.action("reject")
    def on_reject(ack, body, respond):
        ack()
        PENDING.pop(body["actions"][0]["value"], None)
        respond(replace_original=True, text="Rejected.")
    return app


if __name__ == "__main__":
    from slack_bolt.adapter.socket_mode import SocketModeHandler
    SocketModeHandler(build_app(), os.environ["SLACK_APP_TOKEN"]).start()
