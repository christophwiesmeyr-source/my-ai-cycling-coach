# bench

Test bench for the interval detector.

- `activities/` — activities in the neutral CSV format (`t,power`), one file per
  activity (`<activity_id>.csv`). Produced by the app-side export script
  (`src/data/export_for_bench.py` in the fit-data-viewer app while co-located).
- `labels/` — ground-truth interval labels as JSON:
  `{ "<activity_id>": [[start_s, end_s], ...] }`.
- `evaluate.py` — (TODO) IoU@0.5 matching → precision/recall/F1 + boundary error.
- `label_tool.py` — (TODO) pyqtgraph GUI for annotating intervals.

Activities and labels are committed to git in this stripped form.
