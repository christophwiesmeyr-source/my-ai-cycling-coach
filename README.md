# My AI Cycling Coach

A desktop application for analyzing cycling performance data from Strava activities, with an AI-powered training coach.

## Features

- **Sync from Strava**: Load the past year of activities directly from Strava metadata
- **Interactive Plotting**: Visualize power output and heart rate with synchronized charts
- **Time Selection**: Click-drag to select time ranges and analyze specific intervals
- **Performance Analytics**: Calculate statistics (mean, max, min, std dev) for selected intervals
- **Multi-Metric Analysis**: Compare multiple performance metrics simultaneously
- **AI Training Coach**: Generate personalized training plans, adapt them based on completed workouts, and chat with an AI coach about your progress

## Tech Stack

- **Python 3.9+**
- **PyQt6**: Desktop application framework
- **PyQtGraph**: High-performance data visualization
- **pandas/NumPy**: Data processing
- **Anthropic Claude**: AI training coach (claude-sonnet-4-6)

## Project Structure

```
src/
├── data/                  # Data layer
│   ├── activity.py        # Activity data model
│   └── strava_api.py      # Strava API client
├── analysis/              # Analysis layer
│   └── statistics.py      # Statistics calculator
├── ai/                    # AI layer
│   ├── client.py          # Anthropic API client wrapper
│   ├── tools.py           # Tool definitions for the adaptor agent
│   ├── plan_generator.py  # Training plan generation
│   ├── plan_adaptor.py    # Plan adaptation agent (tool use)
│   └── chat_session.py    # Coaching chat session
└── ui/                    # UI layer
    ├── main_window.py     # Main application window
    ├── training_tab.py    # AI training tab
    ├── workers.py         # Background QThread workers
    └── plot_widget.py     # Interactive plot widget

main.py                    # Application entry point
```

## Installation

### 1. Enter project directory
```bash
cd my-ai-cycling-coach
```

### 2. Create a virtual environment
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

## Authentication

### Strava

This application uses the Strava API and requires an access token and refresh token, plus your Strava API client credentials to support automatic token refreshes. Store these values in the file `~/.my-ai-cycling-coach/strava_tokens.json` with the following fields:

```json
{
  "access_token": "YOUR_ACCESS_TOKEN",
  "refresh_token": "YOUR_REFRESH_TOKEN",
  "strava_client_id": "YOUR_CLIENT_ID",
  "strava_client_secret": "YOUR_CLIENT_SECRET"
}
```

Where to get these values:

- Create an API app on Strava: sign in at https://developers.strava.com and go to "Create & Manage Your App". Copy the **Client ID** and **Client Secret** from your application settings.

- To obtain an `access_token` and `refresh_token` for your account, follow Strava's OAuth flow. A quick manual approach:

  1. Open in your browser (replace `YOUR_CLIENT_ID` and `REDIRECT_URI`):

     ```
     https://www.strava.com/oauth/authorize?client_id=YOUR_CLIENT_ID&response_type=code&redirect_uri=REDIRECT_URI&scope=activity:read_all&approval_prompt=auto
     ```

  2. After authorizing, Strava will redirect to `REDIRECT_URI` with a `code` parameter. Exchange that code for tokens:

     ```bash
     curl -X POST https://www.strava.com/oauth/token \
       -F client_id=YOUR_CLIENT_ID \
       -F client_secret=YOUR_CLIENT_SECRET \
       -F code=THE_CODE_FROM_REDIRECT \
       -F grant_type=authorization_code
     ```

  3. The JSON response will include `access_token` and `refresh_token`. Paste these into `~/.my-ai-cycling-coach/strava_tokens.json` along with your client id/secret.

Notes:

- The `StravaClient` uses the `strava_client_id` and `strava_client_secret` values to refresh expired access tokens automatically. If those fields are missing, token refresh will fail.
- Keep `~/.my-ai-cycling-coach/strava_tokens.json` private — it contains sensitive credentials.

#### Redirect URI and the helper script

The `redirect_uri` is a URL you register in your Strava app settings. For local development, register `http://localhost:5000/callback` and use the same value when running the helper script.

To automate obtaining tokens, run the included helper script:

```bash
python src/data/get_strava_tokens.py --client-id YOUR_CLIENT_ID --client-secret YOUR_CLIENT_SECRET --port 5000
```

It will open your browser, capture the redirect locally, exchange the code for tokens, and save them to `~/.my-ai-cycling-coach/strava_tokens.json`.

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

Alternatively, set the `ANTHROPIC_API_KEY` environment variable — the application checks this first if the file is absent:

```bash
export ANTHROPIC_API_KEY="sk-ant-your-key-here"
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

## Architecture Notes

The codebase is organized into four layers:

- **Data Layer**: Strava API integration and activity data models
- **Analysis Layer**: Statistical calculations (metric-agnostic)
- **AI Layer**: Anthropic Claude integration for plan generation, agentic adaptation (tool use), and streaming chat
- **UI Layer**: PyQt6-based desktop interface; background AI calls run in QThread workers to keep the UI responsive

## Features Roadmap
- [x] AI trainer functionality

## Contributing

Contributions are welcome! Feel free to submit issues or pull requests.

## License

MIT License
