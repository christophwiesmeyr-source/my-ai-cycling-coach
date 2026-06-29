"""Pure IO for the labeling bench — no GUI dependencies, so it is unit-testable.

Each activity has one annotation file ``labels/<id>.json`` holding both the
auto-derived activity meta and the hand-drawn interval ground truth:

    {
      "indoor": true,
      "sport_type": "Ride",
      "intervals": [
        {"start_s": 600.0, "end_s": 780.0, "type": "vo2max"}
      ]
    }

``intervals: null`` (or the key absent) means **not yet annotated**; an explicit
``[]`` means **annotated, no intervals** (a pure distractor ride). Evaluation
should only score activities whose ``intervals`` is a list.

These type tags are a bench/evaluation concern only — they are never fed to the
detector, whose output stays bare ``(start_s, end_s)``.
"""
import csv
import json
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

BENCH_DIR = Path(__file__).resolve().parent
ACTIVITIES_DIR = BENCH_DIR / "activities"
LABELS_DIR = BENCH_DIR / "labels"

# Controlled vocabulary for interval intensity, ordered low -> high intensity
# ("other" last). Extend as needed; "other" is the default the annotator changes.
INTERVAL_TYPES = ("endurance", "sweet_spot", "threshold", "vo2max", "anaerobic", "other")
DEFAULT_TYPE = "other"

# An interval is (start_s, end_s, type).
Interval = Tuple[float, float, str]


def list_activity_ids(activities_dir: Path = ACTIVITIES_DIR) -> List[str]:
    """Activity ids that have an exported CSV, sorted."""
    return sorted(p.stem for p in Path(activities_dir).glob("*.csv"))


def load_activity_csv(activity_id, activities_dir: Path = ACTIVITIES_DIR
                      ) -> Tuple[np.ndarray, np.ndarray]:
    """Load (t, power) arrays for an activity from its neutral CSV."""
    path = Path(activities_dir) / f"{activity_id}.csv"
    t, p = [], []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            t.append(float(row["t"]))
            p.append(float(row["power"]))
    return np.asarray(t, dtype=float), np.asarray(p, dtype=float)


def annotation_path(activity_id, labels_dir: Path = LABELS_DIR) -> Path:
    return Path(labels_dir) / f"{activity_id}.json"


def _coerce_interval(iv) -> Interval:
    """Accept (start, end) or (start, end, type); clamp type to the vocabulary."""
    start, end = float(iv[0]), float(iv[1])
    itype = iv[2] if len(iv) > 2 else DEFAULT_TYPE
    if itype not in INTERVAL_TYPES:
        itype = DEFAULT_TYPE
    return start, end, itype


def load_annotation(activity_id, labels_dir: Path = LABELS_DIR) -> dict:
    """Return ``{'indoor', 'sport_type', 'intervals'}``.

    ``intervals`` is a list of ``(start_s, end_s, type)`` tuples, or ``None`` if
    the activity has not been annotated yet.
    """
    path = annotation_path(activity_id, labels_dir)
    if not path.exists():
        return {"indoor": None, "sport_type": None, "intervals": None}
    data = json.loads(path.read_text())
    raw = data.get("intervals")
    intervals = None if raw is None else [
        _coerce_interval((iv["start_s"], iv["end_s"], iv.get("type", DEFAULT_TYPE)))
        for iv in raw
    ]
    return {
        "indoor": data.get("indoor"),
        "sport_type": data.get("sport_type"),
        "intervals": intervals,
    }


def _write_annotation(activity_id, ann: dict, labels_dir: Path) -> Path:
    Path(labels_dir).mkdir(parents=True, exist_ok=True)
    intervals = ann.get("intervals")
    if intervals is not None:
        cleaned = sorted(
            (_coerce_interval(iv) for iv in intervals if float(iv[1]) > float(iv[0])),
            key=lambda iv: iv[0],
        )
        intervals = [
            {"start_s": round(s, 1), "end_s": round(e, 1), "type": t}
            for s, e, t in cleaned
        ]
    obj = {
        "indoor": ann.get("indoor"),
        "sport_type": ann.get("sport_type"),
        "intervals": intervals,
    }
    path = annotation_path(activity_id, labels_dir)
    path.write_text(json.dumps(obj, indent=2) + "\n")
    return path


def save_intervals(activity_id, intervals, labels_dir: Path = LABELS_DIR) -> Path:
    """Save the interval ground truth, preserving existing activity meta.

    Pass a list (possibly empty) to mark the activity as annotated.
    """
    ann = load_annotation(activity_id, labels_dir)
    ann["intervals"] = list(intervals)
    return _write_annotation(activity_id, ann, labels_dir)


def save_meta(activity_id, indoor: Optional[bool], sport_type: Optional[str],
              labels_dir: Path = LABELS_DIR) -> Path:
    """Set activity meta, preserving existing intervals (incl. the unlabelled state)."""
    ann = load_annotation(activity_id, labels_dir)
    ann["indoor"] = indoor
    ann["sport_type"] = sport_type
    return _write_annotation(activity_id, ann, labels_dir)
