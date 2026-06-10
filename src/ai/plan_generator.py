"""Training plan generator — plan narrative and structured session list"""
from typing import cast

from anthropic.types import TextBlock

from src.constants import APP_DIR, PLAN_ORIGINAL_PATH, SESSIONS_ORIGINAL_PATH, AI_MODEL
from src.goals import GOAL_FIELDS
from .client import get_client


def generate_plan(goals: dict) -> str:
    """Generate a structured training plan from user goals and save to plan_original.md."""
    APP_DIR.mkdir(parents=True, exist_ok=True)

    client = get_client()
    message = client.messages.create(
        model=AI_MODEL,
        max_tokens=4096,
        system=(
            "You are an expert cycling coach. Create detailed, structured training plans "
            "that are realistic, evidence-based, and tailored to the athlete's goals and "
            "current fitness. Always include reasoning for your session choices."
        ),
        messages=[{"role": "user", "content": _build_plan_prompt(goals)}],
    )

    plan = cast(TextBlock, message.content[0]).text
    full_plan = _build_plan_header(goals) + "\n\n" + plan
    PLAN_ORIGINAL_PATH.write_text(full_plan)
    return full_plan


def generate_sessions(plan_text: str, goals: dict) -> str:
    """Generate a structured session CSV from the narrative plan and save to sessions_original.csv."""
    APP_DIR.mkdir(parents=True, exist_ok=True)

    client = get_client()
    message = client.messages.create(
        model=AI_MODEL,
        max_tokens=4096,
        system=(
            "You are a cycling coach assistant that converts training plans into structured "
            "session data. Output only clean CSV — no prose, no markdown fences."
        ),
        messages=[{"role": "user", "content": _build_sessions_prompt(plan_text, goals)}],
    )

    raw = cast(TextBlock, message.content[0]).text.strip()
    csv_text = _extract_csv(raw)
    SESSIONS_ORIGINAL_PATH.write_text(csv_text)
    return csv_text


# ------------------------------------------------------------------ #
# Prompt builders                                                      #
# ------------------------------------------------------------------ #

def _build_plan_header(goals: dict) -> str:
    """Markdown block recording the parameter values used to generate this plan."""
    rows = []
    for gm in GOAL_FIELDS:
        v = goals.get(gm.key)
        if v:
            rows.append((gm.label, gm.format_value(v)))
        # insert computed event fields directly after event_name
        if gm.key == "event_name":
            if goals.get("event_date"):
                rows.append(("Event date", goals["event_date"]))
            if goals.get("weeks_until_event"):
                rows.append(("Weeks to event", str(goals["weeks_until_event"])))
    if goals.get("current_date"):
        rows.append(("Generated on", goals["current_date"]))

    table_rows = "\n".join(f"| {k} | {v} |" for k, v in rows)
    return f"## Plan parameters\n\n| Parameter | Value |\n|-----------|-------|\n{table_rows}\n\n---"


def _build_plan_prompt(goals: dict) -> str:
    event_name = goals.get("event_name") or "target event"
    event_date = goals.get("event_date", "")
    current_date = goals.get("current_date", "")
    weeks = goals.get("weeks_until_event", "")
    days = goals.get("days_until_event", "")

    other_lines = "\n".join(
        f"- {key}: {value}"
        for key, value in goals.items()
        if value and key not in {
            "event_name", "event_date", "current_date",
            "days_until_event", "weeks_until_event",
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
- Do not wrap any field in quotes unless the field itself contains a comma"""


def _extract_csv(raw: str) -> str:
    """Strip any preamble/postamble, returning only lines from the header row onwards."""
    for i, line in enumerate(raw.splitlines()):
        if line.strip().startswith("date,"):
            return "\n".join(raw.splitlines()[i:])
    return raw
