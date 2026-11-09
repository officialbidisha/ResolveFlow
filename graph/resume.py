"""Resuming a paused run, and retrying one whose execute step did not finish.

After await_approval resumes with approved=True, the checkpoint records the
approval and schedules execute. If execute then fails (a crash, a GitHub
timeout, no user credential), the thread is left with execute pending and
no interrupt to answer. Sending Command(resume=...) again would be
meaningless, so this re-runs the pending execute step instead. That retry
is safe because execute's writes go through tools/side_effects.py.
"""

from __future__ import annotations

from langgraph.types import Command


class NothingToResume(Exception):
    """The run has no pending approval and no pending execute step."""


def _plan(snapshot, approved: bool):
    if any(task.interrupts for task in snapshot.tasks):
        return Command(resume=approved)
    if "execute" in snapshot.next:
        if not approved:
            raise NothingToResume("this run was already approved; its GitHub write is pending and can only be retried")
        return None
    raise NothingToResume("this run has no pending approval or GitHub write")


def resume_or_retry(compiled_graph, config: dict, approved: bool) -> dict:
    payload = _plan(compiled_graph.get_state(config), approved)
    return compiled_graph.invoke(payload, config)


async def aresume_or_retry(compiled_graph, config: dict, approved: bool) -> dict:
    payload = _plan(await compiled_graph.aget_state(config), approved)
    return await compiled_graph.ainvoke(payload, config)
