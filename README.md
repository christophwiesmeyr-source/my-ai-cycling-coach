# My AI Cycling Coach

A desktop application for analyzing cycling performance data from Strava activities, with an AI-powered training coach.

## Features

- **Sync from Strava**: Load the past year of activities directly from Strava metadata
- **Interactive Plotting**: Visualize power output and heart rate with synchronized charts
- **Time Selection**: Click-drag to select time ranges and analyze specific intervals
- **Performance Analytics**: Calculate statistics (mean, max, min, std dev) for selected intervals
- **AI Training Coach**: Generate personalized training plans, adapt them based on completed workouts, and chat with an AI coach about your progress

## Tech Stack

- **Linux System**: Should in theory work on other platforms as well but might need some adaption
- **Python 3.9+**
- **PyQt6**: Desktop application framework
- **PyQtGraph**: High-performance data visualization
- **pandas/NumPy**: Data processing
- **Anthropic Claude**: AI training coach (claude-sonnet-4-6)

## Installation

From the project directory, run the setup script:

```bash
./setup.sh
```

This creates a virtual environment, installs dependencies, and registers the app as a desktop entry (icon + launcher).

## Authentication

### Strava

1. Sign in at [developers.strava.com](https://developers.strava.com) and go to **Create & Manage Your App**. Copy your **Client ID** and **Client Secret**.
2. In your Strava app settings, add `http://localhost:5000/callback` as an authorised redirect URI.
3. Run the included helper script — it opens your browser, handles the OAuth redirect, and saves the tokens automatically:

```bash
python src/data/get_strava_tokens.py --client-id YOUR_CLIENT_ID --client-secret YOUR_CLIENT_SECRET
```

Tokens are saved to `~/.my-ai-cycling-coach/strava_tokens.json`. Keep this file private — it contains sensitive credentials.

### Claude API (AI Training Features)

The Training tab uses the Claude API from Anthropic for AI-powered plan generation, adaptation, and coaching chat. This requires a **separate API account** — a Claude.ai subscription does not grant API access.

#### Setting up your Claude API key

1. Sign up at [console.anthropic.com](https://console.anthropic.com)
2. Add a payment method. Usage is billed per token — generating or adapting a training plan typically costs a few cents per run; chat is similarly inexpensive.
3. Navigate to **API Keys** and create a new key.
4. Save the key to `~/.my-ai-cycling-coach/claude_api_key`:

```bash
mkdir -p ~/.my-ai-cycling-coach
echo "sk-ant-your-key-here" > ~/.my-ai-cycling-coach/claude_api_key
chmod 600 ~/.my-ai-cycling-coach/claude_api_key
```

> **Keep your API key private.** Anyone with your key can make API calls billed to your account.

## Usage

### Running the Application

```bash
python main.py
```

### Loading Activities

On startup, activities from the last year are loaded from Strava using metadata only.

1. Use the **Refresh Activities** button to re-sync the latest activity list from Strava.
2. Select an activity in the table to download its full data and display it.

### Analyzing Data

1. Select primary and secondary metrics from the dropdowns.
2. Click and drag on the plot to select a time range.
3. View statistics for the selected interval in the **Selection Statistics** panel.
4. Use middle mouse button to pan, scroll wheel to zoom.

### AI Training Coach

Navigate to the **Training** tab to use the AI features:

1. **Generate Plan**: Fill in your training goals (target event, weekly hours, current FTP, etc.) and click **Generate Plan**. The plan is saved to `~/.my-ai-cycling-coach/plan_original.md` and displayed in the viewer.
2. **Adapt Plan**: After completing some workouts, click **Adapt Plan**. The AI queries your recent Strava activities, compares them against the plan, and writes an updated version to `~/.my-ai-cycling-coach/plan_adapted.md`.
3. **Chat**: Use the chat panel at the bottom to ask your AI coach questions about your progress, request session advice, or discuss adjustments to the plan.

## License

MIT License
