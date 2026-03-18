# FIT Data Visualizer

A desktop application for analyzing cycling performance data from Garmin activities.

## Features

- **Load FIT Files**: Import activity files from your Garmin device or folder
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

## Usage

### Running the Application

```bash
python main.py
```

### Loading Activities

1. **From Folder**: Click "Open Folder" to load all .fit files from a directory
2. **Single File**: Click "Open FIT File" to load a specific activity

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
