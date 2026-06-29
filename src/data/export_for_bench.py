"""Export a Strava activity to the interval-detection bench's neutral format.

This is the *only* Strava-aware piece of the interval-detection workflow: it
dumps an activity to a stripped ``t,power`` CSV that the (app-independent) bench
and detector consume. Keeps the dependency arrow app -> package.

Usage:
    python -m src.data.export_for_bench <activity_id> [<activity_id> ...]
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.strava_api import StravaClient

# interval_detection/bench/activities, relative to this file (src/data/...).
BENCH_ACTIVITIES_DIR = (
    Path(__file__).resolve().parents[2] / "interval_detection" / "bench" / "activities"
)


def export_activity(activity_id: int, client: StravaClient | None = None,
                    out_dir: Path = BENCH_ACTIVITIES_DIR) -> Path:
    """Download an activity and write its (t, power) series as CSV.

    Returns the path written. Raises ValueError if the activity has no power.
    """
    client = client or StravaClient()
    activity = client.download_activity(activity_id)

    power = activity.get_time_series("power")
    if power is None or len(power) == 0:
        raise ValueError(f"Activity {activity_id} has no power data; skipping.")

    time_s = activity.get_time_array()
    n = min(len(time_s), len(power))
    df = pd.DataFrame({"t": np.asarray(time_s)[:n], "power": np.asarray(power)[:n]})

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{activity_id}.csv"
    df.to_csv(out_path, index=False)
    return out_path


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    client = StravaClient()
    for raw_id in argv:
        try:
            path = export_activity(int(raw_id), client=client)
            print(f"wrote {path}")
        except Exception as exc:  # noqa: BLE001 - report and continue
            print(f"activity {raw_id}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
