"""Training plan generator — plan narrative and structured session list"""

from src.constants import (
    APP_DIR,
    PLAN_ORIGINAL_PATH,
    SESSIONS_ORIGINAL_PATH,
    AI_MODEL,
    PLAN_ADAPTED_PATH,
    SESSIONS_ADAPTED_PATH,
    SESSIONS_LOG_PATH,
)
from src.goals import format_goals_table
from .client import get_client


def _extract_text_content(content: list) -> str:
    # The response's first block isn't always text — a model may emit a
    # ThinkingBlock (or other non-text block) ahead of it, so scan for text
    # blocks by attribute rather than assuming content[0].
    return "\n".join(block.text for block in content if hasattr(block, "text"))


def _raise_if_truncated(stop_reason: str | None, what: str) -> None:
    # A single-shot create() call has no equivalent to adapt_plan()'s
    # tool-use loop, where hitting max_tokens is caught via stop_reason —
    # here it's the only signal that the response was cut off mid-output
    # (e.g. missing an entire tail of weeks from a session list) rather than
    # genuinely finished.
    if stop_reason != "end_turn":
        raise RuntimeError(
            f"{what} stopped unexpectedly (stop_reason={stop_reason!r}); "
            "this usually means the response was truncated — try again."
        )


def clear_derived_plan_data() -> None:
    # The adapted plan, its session list, and the completion log are all keyed
    # to the old plan's dates, so they're meaningless once a new plan replaces it.
    for path in (PLAN_ADAPTED_PATH, SESSIONS_ADAPTED_PATH, SESSIONS_LOG_PATH):
        path.unlink(missing_ok=True)


def generate_plan(goals: dict) -> str:
    APP_DIR.mkdir(parents=True, exist_ok=True)

    client = get_client()
    # A non-streaming create() call refuses to run if max_tokens implies more
    # than ~10 minutes of generation time (anthropic SDK's built-in guard) —
    # stream() has no such ceiling, so it's required at this max_tokens size.
    with client.messages.stream(
        model=AI_MODEL,
        max_tokens=32768,
        system=(
            "You are an expert cycling coach. Create detailed, structured training plans "
            "that are realistic, evidence-based, and tailored to the athlete's goals and "
            "current fitness. Always include reasoning for your session choices."
        ),
        messages=[{"role": "user", "content": _build_plan_prompt(goals)}],
    ) as stream:
        message = stream.get_final_message()
    _raise_if_truncated(message.stop_reason, "Plan generation")

    plan = _extract_text_content(message.content)
    full_plan = _build_plan_header(goals) + "\n\n" + plan
    PLAN_ORIGINAL_PATH.write_text(full_plan)
    return full_plan


_SESSIONS_SYSTEM = (
    "You are a cycling coach assistant that converts training plans into structured "
    "session data. Output only clean CSV — no prose, no markdown fences."
)


def generate_sessions(plan_text: str, goals: dict) -> str:
    APP_DIR.mkdir(parents=True, exist_ok=True)

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
    _raise_if_truncated(message.stop_reason, "Session list generation")

    raw = _extract_text_content(message.content).strip()
    csv_text = _extract_csv(raw)
    SESSIONS_ORIGINAL_PATH.write_text(csv_text)
    return csv_text


# ------------------------------------------------------------------ #
# Prompt builders                                                      #
# ------------------------------------------------------------------ #


def _build_plan_header(goals: dict) -> str:
    return format_goals_table(goals, "Plan parameters")


def _build_plan_prompt(goals: dict) -> str:
    event_name = goals.get("event_name") or "target event"
    event_date = goals.get("event_date", "")
    current_date = goals.get("current_date", "")
    weeks = goals.get("weeks_until_event", "")
    days = goals.get("days_until_event", "")

    other_lines = "\n".join(
        f"- {key}: {value}"
        for key, value in goals.items()
        if value
        and key
        not in {
            "event_name",
            "event_date",
            "current_date",
            "days_until_event",
            "weeks_until_event",
        }
    )

    return f"""Create a detailed cycling training plan in Markdown format.

## Planning context
- Today's date: {current_date}
- Target event: {event_name} on {event_date} — that is {weeks} weeks ({days} days) from today
- The plan must span exactly {weeks} weeks, starting this week and finishing on race week

## Athlete profile
{other_lines}

## Required plan structure
1. **Overview**: Summarise the training approach and explain why it fits the available {weeks} weeks and the athlete's profile.
2. **Phase breakdown**: Divide the {weeks} weeks into phases (e.g. Base, Build, Peak, Taper) with exact calendar week ranges and the goal of each phase.
3. **Weekly structure**: For each phase, show a typical training week as a table with columns: Day | Session type | Duration | Intensity | Purpose.
4. **Key workouts**: Describe 2–3 signature workouts per phase with full instructions (warm-up, intervals, cool-down).
5. **Progression**: How training load increases week-to-week and the criteria for a recovery week.
6. **Metrics to track**: What the athlete should monitor to confirm the plan is working.
7. **FTP tests**: Schedule an FTP test at the start of the plan to establish a baseline, and again after each major phase transition (e.g. end of Base, end of Build). Do not schedule a test within 2 weeks of the target event.

Be specific and practical. All dates and week numbers must be consistent with the {weeks}-week window above."""


def _build_sessions_prompt(plan_text: str, goals: dict) -> str:
    current_date = goals.get("current_date", "")
    event_date = goals.get("event_date", "")
    weeks = goals.get("weeks_until_event", "")

    return f"""Convert the training plan below into a complete list of individual sessions as a CSV file.

## Training plan
{plan_text}

## Planning context
- Plan start date: {current_date}
- Event date: {event_date}
- Total weeks: {weeks}

## Output requirements
- Output ONLY the CSV rows — no introduction, no commentary, no markdown fences
- First row must be exactly this header:
  date,week,phase,type,duration_min,intensity,target_power_pct_ftp,warmup,main_set,cooldown,description
- Column definitions:
  - date: ISO 8601 (YYYY-MM-DD), calculated from the plan start date {current_date}
  - week: integer week number within the plan (1 to {weeks})
  - phase: training phase (e.g. Base, Build, Peak, Taper)
  - type: session name (e.g. Z2 Endurance, Threshold Intervals, Recovery Ride, Long Ride)
  - duration_min: integer total session duration in minutes
  - intensity: human-readable label for the main effort (e.g. Zone 1, Zone 2, Tempo, Threshold, VO2max)
  - target_power_pct_ftp: target power for the main effort as a % of FTP range (e.g. <55%, 56-75%, 76-90%, 91-105%, 106-120%)
  - warmup: warm-up protocol as plain text (e.g. 15 min @ Zone 1-2 easy spinning)
  - main_set: core workout using interval notation (e.g. 3 x 10 min @ 91-105% FTP / 5 min @ Zone 1 recovery — or: 60 min steady @ Zone 2)
  - cooldown: cool-down protocol as plain text (e.g. 10 min @ Zone 1 easy spinning)
  - description: one concise sentence on the purpose and expected adaptation of this session
- Include every training session — typically 2–6 per week
- Do not include rest days
- Do not wrap a field in quotes unless it contains a comma — but if a field
  (e.g. main_set or description) does contain a comma, you MUST wrap that
  field in double quotes, or the row breaks. For example, if main_set is
  "3 x 20 min @ 76-90% FTP, then 10 min @ Zone 1 recovery", write it as:
  2026-10-03,7,Race,Long Ride,300,Zone 2,56-75%,15 min @ Zone 1-2 easy spinning,"3 x 20 min @ 76-90% FTP, then 10 min @ Zone 1 recovery",10 min @ Zone 1 easy spinning,"Builds durability, especially in the final third of the ride"
"""


def _extract_csv(raw: str) -> str:
    for i, line in enumerate(raw.splitlines()):
        if line.strip().startswith("date,"):
            return "\n".join(raw.splitlines()[i:])
    return raw
