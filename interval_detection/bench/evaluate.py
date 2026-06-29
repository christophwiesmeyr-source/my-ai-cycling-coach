"""Evaluation harness for the interval detector.

Matching is **coverage-based** (lenient): a prediction "covers" a ground-truth
interval when ``overlap / len(GT) >= 0.5``. Per activity:

  * a prediction covering >= 2 GT is a **merge** -> that prediction is a false
    positive and every GT it covers is a false negative (zero credit). This rule
    is parameter-free and necessary: without it a single ride-spanning
    prediction would score perfect recall.
  * otherwise each GT covered by a prediction is a **true positive** (matched to
    its best-covering prediction); surplus predictions are false positives,
    uncovered GT are false negatives.

Coverage is blind to a prediction over-extending past a GT (into empty space):
that stays a TP and only shows up in the boundary-error statistic
``|Δstart| + |Δend|`` reported over matched pairs.

Metrics are micro-averaged (intervals pooled across activities) and stratified
by indoor/outdoor (full P/R/F1) and by interval type (recall + boundary error;
predictions carry no type so FP cannot be attributed to one).
"""
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import labelio  # noqa: E402

# Importing the package detector; the bench dir is alongside the installed pkg.
from interval_detection import detect_intervals  # noqa: E402

COVERAGE_THRESHOLD = 0.5
ATHLETE_FTP = 325.0


def _overlap(a, b) -> float:
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def coverage(pred, gt) -> float:
    """Fraction of the GT interval covered by the prediction."""
    length = gt[1] - gt[0]
    return _overlap(pred, gt) / length if length > 0 else 0.0


def boundary_error(pred, gt) -> float:
    """Absolute boundary error |Δstart| + |Δend| for a matched pair."""
    return abs(pred[0] - gt[0]) + abs(pred[1] - gt[1])


def match(preds, gts, threshold: float = COVERAGE_THRESHOLD):
    """Lenient coverage matching.

    Returns ``(tp_pairs, fp, fn)`` where ``tp_pairs`` is a list of
    ``(pred_idx, gt_idx)``, ``fp`` is a sorted list of prediction indices and
    ``fn`` a sorted list of GT indices.
    """
    n, m = len(preds), len(gts)
    covers = [
        {j for j in range(m) if coverage(preds[i], gts[j]) >= threshold}
        for i in range(n)
    ]

    tp_pairs, fp, fn = [], set(), set()
    merged_preds, consumed_gts = set(), set()

    # Merges: one prediction covering >= 2 GT -> zero credit for all involved.
    for i in range(n):
        if len(covers[i]) >= 2:
            merged_preds.add(i)
            fp.add(i)
            for j in covers[i]:
                fn.add(j)
                consumed_gts.add(j)

    # Remaining preds cover <= 1 GT. Assign each free GT to its best coverer.
    available = {
        i: covers[i] - consumed_gts for i in range(n) if i not in merged_preds
    }
    for j in range(m):
        if j in consumed_gts:
            continue
        candidates = [i for i, cov in available.items() if cov == {j}]
        if candidates:
            best = max(candidates, key=lambda i: coverage(preds[i], gts[j]))
            tp_pairs.append((best, j))
            fp.update(i for i in candidates if i != best)
        else:
            fn.add(j)

    assigned = {i for i, _ in tp_pairs} | fp
    fp.update(i for i in range(n) if i not in merged_preds and i not in assigned)

    return tp_pairs, sorted(fp), sorted(fn)


def score(preds, gts, threshold: float = COVERAGE_THRESHOLD) -> dict:
    """Per-activity counts and boundary errors for matched pairs."""
    tp_pairs, fp, fn = match(preds, gts, threshold)
    return {
        "tp": len(tp_pairs),
        "fp": len(fp),
        "fn": len(fn),
        "tp_pairs": tp_pairs,
        "boundary_errors": [boundary_error(preds[i], gts[j]) for i, j in tp_pairs],
    }


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #

def _prf(tp, fp, fn):
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    if precision is None or recall is None:
        f1 = None
    elif precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)
    return precision, recall, f1


def _bstats(values):
    if not values:
        return {"mean": None, "median": None, "n": 0, "values": []}
    return {
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "n": len(values),
        "values": list(values),
    }


def _summary(counts, boundary):
    precision, recall, f1 = _prf(counts["tp"], counts["fp"], counts["fn"])
    out = {**counts, "precision": precision, "recall": recall, "f1": f1}
    if boundary is not None:
        out["boundary"] = _bstats(boundary)
    return out


def evaluate(predict=None, ftp: float = ATHLETE_FTP, activity_ids=None,
             activities_dir: Path = labelio.ACTIVITIES_DIR,
             labels_dir: Path = labelio.LABELS_DIR,
             threshold: float = COVERAGE_THRESHOLD) -> dict:
    """Run a detector over the labelled bench and return a stratified report.

    ``predict`` is a callable ``(activity_id, t, power) -> list[(start_s, end_s)]``.
    The default wraps the package detector with ``ftp``. Only activities whose
    annotation has been labelled (``intervals`` is a list, not ``None``) are
    scored; ``[]`` distractors count toward precision only.
    """
    if predict is None:
        def predict(_aid, t, power):
            return detect_intervals(t, power, ftp=ftp)

    ids = activity_ids if activity_ids is not None else labelio.list_activity_ids(activities_dir)

    overall = {"tp": 0, "fp": 0, "fn": 0}
    place = {"indoor": {"tp": 0, "fp": 0, "fn": 0}, "outdoor": {"tp": 0, "fp": 0, "fn": 0}}
    boundary_all = []
    type_total, type_found = Counter(), Counter()
    type_boundary = defaultdict(list)
    n_act = 0

    for aid in ids:
        ann = labelio.load_annotation(aid, labels_dir)
        if ann["intervals"] is None:
            continue
        n_act += 1
        t, power = labelio.load_activity_csv(aid, activities_dir)
        preds = [(float(iv[0]), float(iv[1])) for iv in predict(aid, t, power)]
        gt_se = [(s, e) for s, e, _ in ann["intervals"]]

        tp_pairs, fp, fn = match(preds, gt_se, threshold)
        tp = len(tp_pairs)
        for bucket in (overall, place["indoor" if ann["indoor"] else "outdoor"]):
            bucket["tp"] += tp
            bucket["fp"] += len(fp)
            bucket["fn"] += len(fn)

        matched = {j: i for i, j in tp_pairs}
        boundary_all.extend(boundary_error(preds[i], gt_se[j]) for i, j in tp_pairs)
        for j, (s, e, typ) in enumerate(ann["intervals"]):
            type_total[typ] += 1
            if j in matched:
                type_found[typ] += 1
                type_boundary[typ].append(boundary_error(preds[matched[j]], gt_se[j]))

    return {
        "n_activities": n_act,
        "overall": _summary(overall, boundary_all),
        "by_place": {g: _summary(c, None) for g, c in place.items()},
        "by_type": {
            typ: {
                "n": type_total[typ],
                "found": type_found[typ],
                "recall": type_found[typ] / type_total[typ] if type_total[typ] else None,
                "boundary": _bstats(type_boundary[typ]),
            }
            for typ in sorted(type_total)
        },
    }


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #

def _fmt(x, pct=False):
    if x is None:
        return "  n/a"
    return f"{100 * x:5.1f}%" if pct else f"{x:6.1f}"


def _secs(x):
    return "n/a" if x is None else f"{x:.1f}s"


def _text_histogram(values, bins: int = 10, width: int = 40) -> str:
    if not values:
        return "  (no matched intervals)"
    lo, hi = min(values), max(values)
    if hi == lo:
        return f"  all {len(values)} matches at {lo:.0f} s"
    step = (hi - lo) / bins
    counts = [0] * bins
    for v in values:
        idx = min(bins - 1, int((v - lo) / step))
        counts[idx] += 1
    peak = max(counts) or 1
    lines = []
    for k, c in enumerate(counts):
        edge = lo + k * step
        bar = "#" * round(width * c / peak)
        lines.append(f"  {edge:6.0f}–{edge + step:<6.0f}s | {bar} {c}")
    return "\n".join(lines)


def format_report(report: dict) -> str:
    lines = [f"Evaluated {report['n_activities']} labelled activities.", ""]

    o = report["overall"]
    lines.append("Overall (micro-averaged):")
    lines.append(f"  TP {o['tp']}  FP {o['fp']}  FN {o['fn']}")
    lines.append(f"  precision {_fmt(o['precision'], True)}   "
                 f"recall {_fmt(o['recall'], True)}   f1 {_fmt(o['f1'], True)}")
    b = o["boundary"]
    lines.append(f"  boundary error: mean {_secs(b['mean'])}  median {_secs(b['median'])}  (n={b['n']})")
    lines.append("")

    lines.append("By recording:")
    for place, s in report["by_place"].items():
        lines.append(f"  {place:8} TP {s['tp']:2} FP {s['fp']:2} FN {s['fn']:2} | "
                     f"P {_fmt(s['precision'], True)} R {_fmt(s['recall'], True)} F1 {_fmt(s['f1'], True)}")
    lines.append("")

    lines.append("By interval type (recall + boundary):")
    for typ, s in report["by_type"].items():
        bb = s["boundary"]
        lines.append(f"  {typ:11} n {s['n']:2}  found {s['found']:2}  "
                     f"recall {_fmt(s['recall'], True)}  "
                     f"boundary mean {_secs(bb['mean'])}")
    lines.append("")

    lines.append("Boundary-error distribution (matched intervals):")
    lines.append(_text_histogram(o["boundary"]["values"]))
    return "\n".join(lines)


def plot_boundary_histogram(values, path=None, bins: int = 20):
    """Optional matplotlib histogram (requires the `bench` extra)."""
    import matplotlib
    if path is not None:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    ax.hist(values, bins=bins)
    ax.set_xlabel("boundary error |Δstart| + |Δend| (s)")
    ax.set_ylabel("matched intervals")
    if path is not None:
        fig.savefig(path)
    return fig


def main():
    print(format_report(evaluate()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
