"""Training plan generator — single-shot plan creation from user goals"""
from src.constants import APP_DIR, PLAN_ORIGINAL_PATH, AI_MODEL
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
        messages=[{"role": "user", "content": _build_prompt(goals)}],
    )

    plan = message.content[0].text
    PLAN_ORIGINAL_PATH.write_text(plan)
    return plan


def _build_prompt(goals: dict) -> str:
    goal_lines = "\n".join(
        f"- {key}: {value}" for key, value in goals.items() if value
    )
    return f"""Create a detailed cycling training plan in Markdown format based on the following goals:

{goal_lines}

The plan must include:
1. **Overview**: A brief summary of the training approach and the reasoning behind it.
2. **Phase breakdown**: Divide the plan into phases (e.g. Base, Build, Peak, Taper) with start/end weeks and goals for each phase.
3. **Weekly structure**: For each phase, describe a typical training week with specific sessions including:
   - Day of the week
   - Session type (e.g. Z2 endurance, threshold intervals, recovery ride)
   - Duration
   - Target intensity (power zones or heart rate zones)
   - Purpose of the session
4. **Key workouts**: Highlight 2-3 signature workouts per phase with detailed instructions.
5. **Progression notes**: How load should increase week-to-week and when to back off.
6. **Metrics to track**: What the athlete should monitor to judge whether the plan is working.

Use Markdown headers, bullet points, and tables where appropriate. Be specific and practical."""
