# FIT Data Visualizer

A desktop application for analyzing cycling performance data from Garmin activities.

## Features

- **Sync from Strava**: Load the past year of activities directly from Strava metadata
- **Interactive Plotting**: Visualize power output and heart rate with synchronized charts
- **Time Selection**: Click-drag to select time ranges and analyze specific intervals
- **Performance Analytics**: Calculate statistics (mean, max, min, std dev) for selected intervals
- **Multi-Metric Analysis**: Compare multiple performance metrics simultaneously

## Tech Stack

- **Python 3.9+**
- **PyQt6**: Desktop application framework
# FIT Data Visualizer

A desktop application for analyzing cycling performance data from Garmin activities.

## Features

- **Sync from Strava**: Load the past year of activities directly from Strava metadata
- **Interactive Plotting**: Visualize power output and heart rate with synchronized charts
- **Time Selection**: Click-drag to select time ranges and analyze specific intervals
- **Performance Analytics**: Calculate statistics (mean, max, min, std dev) for selected intervals
- **Multi-Metric Analysis**: Compare multiple performance metrics simultaneously

## Tech Stack

- **Python 3.9+**
- **PyQt6**: Desktop application framework
- **PyQtGraph**: High-performance data visualization
- **fitparse**: FIT file parsing
- **pandas/NumPy**: Data processing

## Project Structure

```
src/
├── data/              # Data layer
│   ├── activity.py    # Activity data model
│   └── fit_parser.py  # FIT file parser
├── analysis/          # Analysis layer
│   └── statistics.py  # Statistics calculator
└── ui/                # UI layer
    ├── main_window.py # Main application window
    └── plot_widget.py # Interactive plot widget

data/                  # Directory for FIT files to analyze
main.py                # Application entry point
```

## Installation

### 1. Enter project directory
```bash
cd fit-data-viewer
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

### Authentication and Strava tokens

This application uses the Strava API and requires an access token and refresh token, plus your Strava API client credentials to support automatic token refreshes. Store these values in the file `~/.aitrainer/strava_tokens.json` with the following fields:

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

     https://www.strava.com/oauth/authorize?client_id=YOUR_CLIENT_ID&response_type=code&redirect_uri=REDIRECT_URI&scope=activity:read_all&approval_prompt=auto

  2. After authorizing, Strava will redirect to `REDIRECT_URI` with a `code` parameter. Exchange that code for tokens:

     ```bash
     curl -X POST https://www.strava.com/oauth/token \
       -F client_id=YOUR_CLIENT_ID \
       -F client_secret=YOUR_CLIENT_SECRET \
       -F code=THE_CODE_FROM_REDIRECT \
       -F grant_type=authorization_code
     ```

  3. The JSON response will include `access_token` and `refresh_token`. Paste these into `~/.aitrainer/strava_tokens.json` along with your client id/secret.

Notes:

- The `StravaClient` in this project uses the `strava_client_id` and `strava_client_secret` values to refresh expired access tokens. If those fields are missing the client cannot refresh tokens automatically.
- Keep `~/.aitrainer/strava_tokens.json` private — it contains sensitive credentials.

Redirect URI and the script helper

- The `redirect_uri` is a URL you register in your Strava app settings. During OAuth the browser is redirected to that URL with a temporary `code` parameter. For local development, register a redirect URI like `http://localhost:5000/callback` in your Strava app configuration and use the same value when running the helper script.

- To automate obtaining tokens, run the included helper script `src/data/get_strava_tokens.py`. It will open your browser, capture the redirect locally, exchange the code for tokens, and save them to `~/.aitrainer/strava_tokens.json` (including your client id/secret).

Example:

```bash
python src/data/get_strava_tokens.py --client-id YOUR_CLIENT_ID --client-secret YOUR_CLIENT_SECRET --port 5000
```

If you choose a different port or path, make sure the redirect URI you register on https://developers.strava.com matches `http://localhost:<port><path>` exactly.

## Usage

### Running the Application

```bash
python main.py
```

### Loading Activities

On startup, activities from the last year are loaded from Strava using metadata only.

1. Use the "Refresh Activities" button to re-sync the latest activity list from Strava
2. Select an activity in the table to download its data and display it

### Analyzing Data

1. Select primary and secondary metrics from the dropdowns
2. Click and drag on the plots to select a time range
3. View statistics for the selected interval in the "Selection Statistics" panel
4. Use middle mouse button to pan, scroll wheel to zoom

## Features Roadmap
- [ ] Multi-activity comparison
- [ ] Custom interval definitions (training zones)
- [ ] Export statistics and reports
- [ ] Direct Garmin API integration
- [ ] Web-based version
- [ ] Data smoothing and filtering options
- [ ] Advanced interval detection

## Architecture Notes

The codebase is organized into three layers:
- **Data Layer**: Handles FIT file parsing and activity data models
- **Analysis Layer**: Provides statistical calculations (metric-agnostic)
- **UI Layer**: PyQt6-based desktop interface

This modular structure enables easy porting to web technologies in the future.

## Contributing

Contributions are welcome! Feel free to submit issues or pull requests.

## License

MIT License
