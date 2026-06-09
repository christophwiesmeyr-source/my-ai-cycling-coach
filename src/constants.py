"""Application-wide constants — single source of truth for names, paths, and settings"""
from pathlib import Path

APP_NAME = "My AI Cycling Coach"
APP_DIR = Path.home() / ".my-ai-cycling-coach"

# Persisted file paths
STRAVA_TOKENS_PATH = APP_DIR / "strava_tokens.json"
CLAUDE_API_KEY_PATH = APP_DIR / "claude_api_key"
PLAN_ORIGINAL_PATH = APP_DIR / "plan_original.md"
PLAN_ADAPTED_PATH = APP_DIR / "plan_adapted.md"
SESSIONS_ORIGINAL_PATH = APP_DIR / "sessions_original.csv"
SESSIONS_ADAPTED_PATH = APP_DIR / "sessions_adapted.csv"
SESSIONS_LOG_PATH = APP_DIR / "sessions_log.json"
GOALS_PATH = APP_DIR / "goals.json"

# AI settings
AI_MODEL = "claude-sonnet-4-6"

# Strava history window used by the plan adaptor agent
STRAVA_HISTORY_WEEKS = 8
