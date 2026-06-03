"""Plan adaptor agent — compares original plan to Strava activities and produces an adapted plan"""
from typing import Any

from src.constants import APP_DIR, PLAN_ORIGINAL_PATH, PLAN_ADAPTED_PATH, AI_MODEL, STRAVA_HISTORY_WEEKS
from .client import get_client
from .tools import TOOLS, execute_tools

_SYSTEM = (
    "You are an expert cycling coach. You will analyse a training plan against the athlete's "
    "actual completed workouts retrieved from Strava, identify gaps and achievements, and "
    "produce an adapted plan that accounts for their real progress. "
    "Use the provided tools to query Strava data before drawing conclusions."
)

_USER_PROMPT = """\
Here is the original training plan:

{original_plan}

Please:
1. Use the tools to retrieve recent Strava activities (start with the last {weeks} weeks).
2. Compare completed workouts against the planned sessions — what was done, what was skipped, \
and what the current fitness trajectory looks like.
3. Identify 3-5 key observations about adherence and progress.
4. Produce a complete adapted training plan in Markdown format that retains the original goals \
but adjusts timing, intensity, and session structure based on what was actually completed.

Begin the adapted plan with a short "Adaptation Notes" section summarising your findings before \
the full plan."""


def adapt_plan(strava_client) -> str:
    """Run the agentic loop to adapt the original plan using Strava data."""
    if not PLAN_ORIGINAL_PATH.exists():
        raise FileNotFoundError(
            "No original plan found. Generate a plan first using the Training tab."
        )

    original_plan = PLAN_ORIGINAL_PATH.read_text()
    client = get_client()
    prompt = _USER_PROMPT.format(original_plan=original_plan, weeks=STRAVA_HISTORY_WEEKS)
    messages: list[Any] = [{"role": "user", "content": prompt}]

    while True:
        response = client.messages.create(
            model=AI_MODEL,
            max_tokens=4096,
            system=_SYSTEM,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            adapted = _extract_text(response.content)
            APP_DIR.mkdir(parents=True, exist_ok=True)
            PLAN_ADAPTED_PATH.write_text(adapted)
            return adapted

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": execute_tools(response.content, strava_client)})
            continue

        return _extract_text(response.content)


def _extract_text(content: list) -> str:
    return "\n".join(block.text for block in content if hasattr(block, "text"))
