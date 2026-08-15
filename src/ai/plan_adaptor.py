"""Plan adaptor agent — compares original plan to recent activities and produces an adapted plan"""

import datetime
import json
import logging
from typing import Any

from src.constants import (
    APP_DIR,
    PLAN_ORIGINAL_PATH,
    PLAN_ADAPTED_PATH,
    AI_MODEL,
    ACTIVITY_HISTORY_WEEKS,
    SESSIONS_LOG_PATH,
)
from src.data.intervals_api import IntervalsClient
from .client import get_client
from .tools import TOOLS, execute_tools

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are an expert cycling coach. You will analyse a training plan against the athlete's "
    "actual completed workouts, identify gaps and achievements, and "
    "produce an adapted plan that accounts for their real progress. "
    "Use the provided tools to query recent activity data before drawing conclusions."
)

_USER_PROMPT = """\
Today's date is {today}. Use this as your reference for past vs future.

Here is the original training plan:

{original_plan}

{log_section}
Please:
1. Use the tools to retrieve recent activities (start with the last {weeks} weeks).
2. Compare completed workouts against the planned sessions — what was done, what was skipped, \
and what the current fitness trajectory looks like. Where the session log above records a \
completion date, use that date to find the matching activity and assess quality.
3. Identify 3-5 key observations about adherence and progress.
4. Produce a complete adapted training plan in Markdown format that retains the original goals \
but adjusts timing, intensity, and session structure based on what was actually completed.

IMPORTANT: Only modify sessions scheduled for {today} or later. Sessions before today are \
history — include them in your analysis but do not change their prescriptions.

Begin the adapted plan with a short "Adaptation Notes" section summarising your findings before \
the full plan."""


def _build_log_section() -> str:
    try:
        log = json.loads(SESSIONS_LOG_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return ""
    if not log:
        return ""
    lines = ["## Session completion log\n"]
    for plan_date, entry in sorted(log.items()):
        completed = entry.get("completed_date", "")
        comment = entry.get("comment", "")
        line = (
            f"- Plan date {plan_date}: completed {completed}"
            if completed
            else f"- Plan date {plan_date}: not yet marked complete"
        )
        if comment:
            line += f' — "{comment}"'
        lines.append(line)
    return "\n".join(lines) + "\n\n"


def adapt_plan(activity_client: IntervalsClient) -> str:
    if not PLAN_ORIGINAL_PATH.exists():
        raise FileNotFoundError(
            "No original plan found. Generate a plan first using the Training tab."
        )

    original_plan = PLAN_ORIGINAL_PATH.read_text()
    today = datetime.date.today().isoformat()
    client = get_client()
    prompt = _USER_PROMPT.format(
        today=today,
        original_plan=original_plan,
        log_section=_build_log_section(),
        weeks=ACTIVITY_HISTORY_WEEKS,
    )
    messages: list[Any] = [{"role": "user", "content": prompt}]

    while True:
        with client.messages.stream(
            model=AI_MODEL,
            max_tokens=32768,
            system=_SYSTEM,
            tools=TOOLS,
            messages=messages,
        ) as stream:
            response = stream.get_final_message()

        usage = response.usage
        logger.info(
            "plan adaptation turn stop_reason=%s input_tokens=%s output_tokens=%s "
            "cache_creation=%s cache_read=%s",
            response.stop_reason,
            usage.input_tokens,
            usage.output_tokens,
            getattr(usage, "cache_creation_input_tokens", None),
            getattr(usage, "cache_read_input_tokens", None),
        )

        if response.stop_reason == "end_turn":
            adapted = _extract_text(response.content)
            APP_DIR.mkdir(parents=True, exist_ok=True)
            PLAN_ADAPTED_PATH.write_text(adapted)
            return adapted

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            messages.append(
                {
                    "role": "user",
                    "content": execute_tools(response.content, activity_client),
                }
            )
            continue

        raise RuntimeError(
            f"Plan adaptation stopped unexpectedly (stop_reason={response.stop_reason!r}); "
            "no adapted plan was saved. This usually means the response was truncated — "
            "try again."
        )


def _extract_text(content: list) -> str:
    return "\n".join(block.text for block in content if hasattr(block, "text"))
