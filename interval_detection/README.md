# interval_detection

Detect structured work intervals (reps) in a cycling activity from power data.

Plan-agnostic by design: **power + timestamps in, list of intervals out**. No
prescription is injected — comparing detected intervals against a planned
workout happens in the consuming application.

```python
from interval_detection import detect_intervals

intervals = detect_intervals(time_s, power, ftp=325)
for iv in intervals:
    print(iv.start_s, iv.end_s, iv.duration_s)
```

## Scope / operating envelope

- Target: **structured work reps only** (not unstructured surges/climbs).
- Minimum interval duration: **≥ 1 min** nominal.
- Minimum separation between reps: **30 s** (closer reps are merged).
- Input is resampled to **1 Hz** internally.
- `ftp` is optional; when supplied it acts as a *soft* intensity prior (intervals
  are usually at least sweet spot), never a hard cut-off.

## Layout

```
src/interval_detection/   # the importable package (pure: numpy only)
  types.py                # Interval(start_s, end_s)
  resample.py             # raw time+power -> uniform 1 Hz
  detector.py             # detect_intervals (algorithm TBD after annotation)
bench/                    # test bench (activities, labels, evaluation)
tests/                    # unit tests
```

The bench stores activities in a neutral `t,power` CSV format so it is fully
decoupled from any specific application or data source.
