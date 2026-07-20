"""Read-only viewer: detector output overlaid on the annotations.

Deliberately separate from the label tool — labelling must stay blind to the
detector (no anchoring bias) and edit-safe. This tool never writes. It reuses
``labelio``, the package smoother, the detector, and ``evaluate.match``.

Per activity it shows the power trace and its 20 s average, the 0.8 x FTP
detection threshold, and two tracks: ground-truth intervals (green = found,
red = missed) and detections (green = TP, orange = false positive). Drawing the
smoothed curve against the threshold makes the boundary behaviour visible.

Usage:
    python interval_detection/bench/view_results.py             # worst cases first
    python interval_detection/bench/view_results.py <id>        # start at an activity
    python interval_detection/bench/view_results.py --order id  # natural order
    python interval_detection/bench/view_results.py --save out  # dump PNGs, no window
Navigate with the Prev / Next buttons or the left/right arrow keys (toolbar has
the usual zoom/pan/save). q quits.
"""

import argparse
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.transforms import blended_transform_factory
from matplotlib.widgets import Button

sys.path.insert(0, str(Path(__file__).resolve().parent))
import labelio  # noqa: E402
import evaluate  # noqa: E402
from interval_detection import detect_intervals, moving_average  # noqa: E402
from interval_detection.detector import FTP_FRACTION  # noqa: E402


def result_for_activity(
    aid: str,
    ftp: float = evaluate.ATHLETE_FTP,
    activities_dir: Path = labelio.ACTIVITIES_DIR,
    labels_dir: Path = labelio.LABELS_DIR,
) -> dict:
    """Everything needed to plot one activity's detection result (no I/O side effects)."""
    t, p = labelio.load_activity_csv(aid, activities_dir)
    ann = labelio.load_annotation(aid, labels_dir)
    all_gt = ann["intervals"] or []
    gts = [(s, e, ty) for s, e, ty in all_gt if e - s >= evaluate.MIN_INTERVAL_S]
    excluded = [(s, e, ty) for s, e, ty in all_gt if e - s < evaluate.MIN_INTERVAL_S]
    preds = [(iv.start_s, iv.end_s) for iv in detect_intervals(t, p, ftp=ftp)]

    tp_pairs, fp, fn = evaluate.match(preds, [(s, e) for s, e, _ in gts])
    return {
        "aid": aid,
        "indoor": ann["indoor"],
        "t": t,
        "p": p,
        "smoothed": moving_average(t, p),
        "threshold": FTP_FRACTION * ftp,
        "gts": gts,
        "excluded": excluded,
        "preds": preds,
        "matched_gt": {j for _, j in tp_pairs},
        "matched_pred": {i for i, _ in tp_pairs},
        "tp": len(tp_pairs),
        "fp": len(fp),
        "fn": len(fn),
    }


def plot_activity(r: dict, ax: Any) -> None:
    ax.clear()
    ax.plot(r["t"], r["p"], color="0.8", lw=0.6, label="power")
    ax.plot(r["t"], r["smoothed"], color="tab:blue", lw=1.1, label="power (20 s)")
    ax.axhline(r["threshold"], color="tab:red", ls="--", lw=0.8, label="0.8·FTP")

    trans = blended_transform_factory(ax.transData, ax.transAxes)

    def bar(s: float, e: float, y: float, color: str) -> None:
        ax.add_patch(
            Rectangle((s, y), e - s, 0.05, transform=trans, color=color, alpha=0.75)
        )

    for s, e, _ in r["excluded"]:  # out-of-scope GT, for context
        bar(s, e, 0.93, "0.6")
    for k, (s, e, _) in enumerate(r["gts"]):  # GT: found vs missed
        bar(s, e, 0.93, "tab:green" if k in r["matched_gt"] else "tab:red")
    for k, (s, e) in enumerate(r["preds"]):  # detections: TP vs FP
        bar(s, e, 0.86, "tab:green" if k in r["matched_pred"] else "tab:orange")

    ax.text(0.002, 0.955, "GT", transform=ax.transAxes, fontsize=8, va="center")
    ax.text(0.002, 0.885, "DET", transform=ax.transAxes, fontsize=8, va="center")
    place = "indoor" if r["indoor"] else "outdoor"
    ax.set_title(
        f"{r['aid']}  {place}    TP {r['tp']}  FP {r['fp']}  FN {r['fn']}    "
        f"(green=match · red=missed GT · orange=FP · grey=excluded GT)"
    )
    ax.set_xlabel("time (s)")
    ax.set_ylabel("power (W)")
    ax.set_ylim(bottom=0)
    ax.margins(x=0.01)
    ax.legend(loc="upper right", fontsize=8)


class Viewer:
    def __init__(self, ids: list, results: dict):
        self.ids, self.results, self.idx = ids, results, 0
        self.fig, self.ax = plt.subplots(figsize=(14, 6))
        self.fig.subplots_adjust(bottom=0.16)
        # Buttons (kept as attributes so they aren't garbage-collected).
        self.b_prev = Button(self.fig.add_axes((0.44, 0.02, 0.05, 0.05)), "◀ Prev")
        self.b_next = Button(self.fig.add_axes((0.51, 0.02, 0.05, 0.05)), "Next ▶")
        self.b_prev.on_clicked(lambda _event: self._step(-1))
        self.b_next.on_clicked(lambda _event: self._step(+1))
        self.fig.canvas.mpl_connect("key_press_event", self._on_key)
        self._draw()

    def _step(self, delta: int) -> None:
        self.idx = (self.idx + delta) % len(self.ids)
        self._draw()

    def _draw(self) -> None:
        plot_activity(self.results[self.ids[self.idx]], self.ax)
        self.fig.suptitle(
            f"[{self.idx + 1}/{len(self.ids)}]   ←/→ or Prev/Next to navigate",
            fontsize=9,
        )
        self.fig.canvas.draw_idle()

    def _on_key(self, event: Any) -> None:
        if event.key in ("right", "n"):
            self._step(+1)
        elif event.key in ("left", "p"):
            self._step(-1)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("activity", nargs="?", help="activity id to start at")
    ap.add_argument("--order", choices=["worst", "id"], default="worst")
    ap.add_argument("--save", metavar="DIR", help="save a PNG per activity and exit")
    ap.add_argument("--ftp", type=float, default=evaluate.ATHLETE_FTP)
    args = ap.parse_args(argv)

    ids = [
        a
        for a in labelio.list_activity_ids()
        if labelio.load_annotation(a)["intervals"] is not None
    ]
    if not ids:
        print("No labelled activities found.")
        return 1
    results = {a: result_for_activity(a, args.ftp) for a in ids}
    if args.order == "worst":
        ids.sort(key=lambda a: results[a]["fp"] + results[a]["fn"], reverse=True)
    if args.activity in ids:
        ids.remove(args.activity)
        ids.insert(0, args.activity)

    if args.save:
        matplotlib.use("Agg")
        out = Path(args.save)
        out.mkdir(parents=True, exist_ok=True)
        fig, ax = plt.subplots(figsize=(14, 6))
        for a in ids:
            plot_activity(results[a], ax)
            fig.savefig(out / f"{a}.png", dpi=110, bbox_inches="tight")
        print(f"saved {len(ids)} PNGs to {out}")
        return 0

    viewer = Viewer(ids, results)  # keep a strong ref so its callbacks survive
    plt.show()
    return 0 if viewer else 0


if __name__ == "__main__":
    raise SystemExit(main())
