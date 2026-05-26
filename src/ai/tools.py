"""Tool schema definitions for the plan adaptor agent"""

TOOLS = [
    {
        "name": "list_recent_activities",
        "description": (
            "List recent Strava activities with summary metadata: date, sport type, "
            "distance, duration, average heart rate, and average power where available. "
            "Use this to get a broad overview of completed workouts before drilling into specifics."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "weeks": {
                    "type": "integer",
                    "description": "Number of weeks to look back. Defaults to 12, maximum 52.",
                    "default": 12,
                }
            },
            "required": [],
        },
    },
    {
        "name": "get_activity_power_data",
        "description": (
            "Download detailed power and heart rate data for a specific activity. "
            "Returns average power, max power, average heart rate, max heart rate, "
            "duration, and distance. Use the activity ID returned by list_recent_activities."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "activity_id": {
                    "type": "integer",
                    "description": "The Strava activity ID.",
                }
            },
            "required": ["activity_id"],
        },
    },
]
