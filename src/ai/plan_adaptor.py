"""Plan adaptor agent — compares original plan to recent activities and produces an adapted plan"""

import csv
import datetime
import json
import logging
from io import StringIO
from typing import Any

from src.constants import (
    APP_DIR,
    PLAN_ORIGINAL_PATH,
    PLAN_ADAPTED_PATH,
    SESSIONS_ORIGINAL_PATH,
    SESSIONS_ADAPTED_PATH,
    AI_MODEL,
    ACTIVITY_HISTORY_WEEKS,
    SESSIONS_LOG_PATH,
)
from src.data.intervals_api import IntervalsClient
from src.goals import format_goals_table, load_goals
from .client import get_client
from .plan_generator import (
    _SESSIONS_SYSTEM,
    _build_sessions_prompt,
    _extract_csv,
    _extract_text_content,
    _raise_if_truncated,
)
from .tools import TOOLS, execute_tools

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are an expert cycling coach. You will analyse a training plan against the athlete's "
    "actual completed workouts, identify gaps and achievements, and "
    "produce an adapted plan that accounts for their real progress. "
    "Use the provided tools to query recent activity data before drawing conclusions."
)
_SYSTEM_BLOCKS: list[Any] = [
    {"type": "text", "text": _SYSTEM, "cache_control": {"type": "ephemeral"}}
]

_USER_PROMPT = """\
Today's date is {today}. Use this as your reference for past vs future.

Here is the original training plan:

{original_plan}

{current_profile_section}
If a "Current athlete profile (live)" section appears above, treat its values as authoritative \
over the original plan's "Plan parameters" table where the two disagree (e.g. FTP) — the plan's \
table is a snapshot from when the plan was generated and may be stale.

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


def _build_user_prompt(original_plan: str, today: str, goals: dict) -> str:
    return _USER_PROMPT.format(
        today=today,
        original_plan=original_plan,
        current_profile_section=format_goals_table(
            goals, "Current athlete profile (live)"
        ),
        log_section=_build_log_section(),
        weeks=ACTIVITY_HISTORY_WEEKS,
    )


def adapt_plan(activity_client: IntervalsClient) -> str:
    if not PLAN_ORIGINAL_PATH.exists():
        raise FileNotFoundError(
            "No original plan found. Generate a plan first using the Training tab."
        )

    original_plan = PLAN_ORIGINAL_PATH.read_text()
    today = datetime.date.today().isoformat()
    current_goals = load_goals()
    client = get_client()
    prompt = _build_user_prompt(original_plan, today, current_goals)
    messages: list[Any] = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}
            ],
        }
    ]

    while True:
        with client.messages.stream(
            model=AI_MODEL,
            max_tokens=32768,
            system=_SYSTEM_BLOCKS,
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
            header = format_goals_table(
                current_goals, "Plan parameters (at adaptation)"
            )
            full_adapted = f"{header}\n\n{adapted}" if header else adapted
            APP_DIR.mkdir(parents=True, exist_ok=True)
            PLAN_ADAPTED_PATH.write_text(full_adapted)
            return full_adapted

        if response.stop_reason == "tool_use":
            # Move the cache breakpoint forward instead of stacking one on every
            # historical message — keeps each request under the API's 4-block
            # cache_control cap regardless of how many tool round-trips this loop takes.
            last_content = messages[-1]["content"]
            if isinstance(last_content, list) and last_content:
                last_content[-1].pop("cache_control", None)

            messages.append({"role": "assistant", "content": response.content})
            tool_results = execute_tools(response.content, activity_client)
            if tool_results:
                tool_results[-1]["cache_control"] = {"type": "ephemeral"}
            messages.append({"role": "user", "content": tool_results})
            continue

        raise RuntimeError(
            f"Plan adaptation stopped unexpectedly (stop_reason={response.stop_reason!r}); "
            "no adapted plan was saved. This usually means the response was truncated — "
            "try again."
        )


def _extract_text(content: list) -> str:
    return "\n".join(block.text for block in content if hasattr(block, "text"))


def adapt_sessions(plan_text: str) -> tuple[str, int]:
    goals = load_goals()
    client = get_client()
    with client.messages.stream(
        model=AI_MODEL,
        max_tokens=32768,
        system=_SESSIONS_SYSTEM,
        messages=[
            {"role": "user", "content": _build_sessions_prompt(plan_text, goals)}
        ],
    ) as stream:
        message = stream.get_final_message()
    _raise_if_truncated(message.stop_reason, "Adapted session list generation")

    raw = _extract_text_content(message.content).strip()
    csv_text = _extract_csv(raw)
    spliced, dropped_rows = _splice_past_sessions(csv_text)
    APP_DIR.mkdir(parents=True, exist_ok=True)
    SESSIONS_ADAPTED_PATH.write_text(spliced)
    return spliced, dropped_rows


def _drop_malformed_rows(rows: list[dict]) -> tuple[list[dict], int]:
    # A row with an unescaped comma in a free-text field (e.g. description)
    # gives a column-count mismatch: too many fields overflow into a `None`
    # key, or too few leave trailing columns as `None`. Either way the
    # row's fields can be silently shifted/misassigned — e.g. an earlier
    # comma pushes real cooldown/description text into the overflow while
    # cooldown/description end up holding what should've been main_set.
    # Drop the row rather than write plausible-looking but wrong data.
    clean = [row for row in rows if None not in row and None not in row.values()]
    return clean, len(rows) - len(clean)


def _splice_past_sessions(generated_csv: str) -> tuple[str, int]:
    generated_reader = csv.DictReader(StringIO(generated_csv))
    generated_rows = list(generated_reader)
    if not generated_rows or not generated_reader.fieldnames:
        return generated_csv, 0

    generated_rows, dropped = _drop_malformed_rows(generated_rows)
    if dropped:
        # The raw response is never persisted anywhere else — the Anthropic
        # SDK's debug logging captures outgoing requests, not response
        # bodies — so this is the only place the exact malformed row(s) can
        # be recovered from for diagnosis.
        logger.warning(
            "dropped %d malformed row(s) from the freshly generated sessions CSV; "
            "raw response was:\n%s",
            dropped,
            generated_csv,
        )

    try:
        original_rows = list(
            csv.DictReader(StringIO(SESSIONS_ORIGINAL_PATH.read_text()))
        )
    except (OSError, csv.Error):
        # Nothing to splice against, so nothing to protect for past dates —
        # trust the (malformed-filtered) generated CSV wholesale rather than
        # date-filtering it against an empty "original", which would silently
        # drop any past-dated rows the model included instead of preserving them.
        logger.warning(
            "no usable original sessions CSV to splice against; writing generated CSV as-is"
        )
        merged = generated_rows
    else:
        original_rows, dropped_past = _drop_malformed_rows(original_rows)
        if dropped_past:
            logger.warning(
                "dropped %d malformed row(s) from the on-disk original sessions CSV",
                dropped_past,
            )
        dropped += dropped_past
        # A future session's model-generated row always wins; a past
        # session's row is always taken verbatim from the original — the
        # model is never trusted to preserve history correctly, no matter
        # what it outputs.
        today = datetime.date.today().isoformat()
        past = [row for row in original_rows if row.get("date", "") < today]
        future = [row for row in generated_rows if row.get("date", "") >= today]
        merged = sorted(past + future, key=lambda row: row.get("date", ""))

    buf = StringIO()
    writer = csv.DictWriter(
        buf, fieldnames=generated_reader.fieldnames, lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(merged)
    return buf.getvalue().strip(), dropped
