"""Tests for the evaluation harness (pinned cases + integration)."""
import sys
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parents[1] / "bench"
sys.path.insert(0, str(BENCH))
import labelio  # noqa: E402
import evaluate  # noqa: E402


# --------------------------------------------------------------------------- #
# Pinned unit cases: score(preds, gts) -> (tp, fp, fn) + boundary errors
# --------------------------------------------------------------------------- #

# (label, preds, gts, tp, fp, fn, sorted boundary errors of TPs)
CASES = [
    ("exact hit",        [(0, 600)],            [(0, 600)],            1, 0, 0, [0]),
    ("hit w/ slop",      [(150, 720)],          [(100, 700)],          1, 0, 0, [70]),
    ("near-miss 0.47",   [(320, 600)],          [(0, 600)],            0, 1, 1, []),
    ("exactly 0.5",      [(300, 600)],          [(0, 600)],            1, 0, 0, [300]),
    ("even split",       [(0, 290), (310, 600)],[(0, 600)],            0, 2, 1, []),
    ("lopsided split",   [(0, 400), (420, 600)],[(0, 600)],            1, 1, 0, [200]),
    ("full merge",       [(0, 1300)],           [(0, 600), (700, 1300)],0, 1, 2, []),
    ("partial merge",    [(0, 800)],            [(0, 600), (650, 1050)],1, 0, 1, [200]),
    ("over-extend empty",[(100, 1300)],         [(100, 700)],          1, 0, 0, [600]),
    ("distractor none",  [],                    [],                    0, 0, 0, []),
    ("distractor FP",    [(100, 300)],          [],                    0, 1, 0, []),
    ("mixed",            [(0, 600), (1000, 1200), (2000, 2200)],
                                                [(0, 600), (1000, 1600)],1, 2, 1, [0]),
]


@pytest.mark.parametrize("label,preds,gts,tp,fp,fn,berr",
                         CASES, ids=[c[0] for c in CASES])
def test_pinned_cases(label, preds, gts, tp, fp, fn, berr):
    result = evaluate.score(preds, gts)
    assert (result["tp"], result["fp"], result["fn"]) == (tp, fp, fn)
    assert sorted(result["boundary_errors"]) == berr


def test_coverage_and_boundary_helpers():
    assert evaluate.coverage((0, 300), (0, 600)) == 0.5
    assert evaluate.coverage((0, 600), (0, 600)) == 1.0
    assert evaluate.coverage((700, 800), (0, 600)) == 0.0
    assert evaluate.boundary_error((150, 720), (100, 700)) == 70


def test_prf_edge_cases():
    assert evaluate._prf(0, 0, 0) == (None, None, None)   # nothing happened
    assert evaluate._prf(0, 0, 2)[1] == 0.0               # recall 0 with FN
    p, r, f = evaluate._prf(3, 1, 1)
    assert p == 0.75 and r == 0.75 and f == 0.75


# --------------------------------------------------------------------------- #
# Integration on a synthetic temp bench
# --------------------------------------------------------------------------- #

@pytest.fixture
def bench(tmp_path):
    acts = tmp_path / "activities"
    labs = tmp_path / "labels"
    acts.mkdir()

    def write_activity(aid, n):
        (acts / f"{aid}.csv").write_text(
            "t,power\n" + "\n".join(f"{i},200" for i in range(n)) + "\n"
        )

    # A: indoor, two vo2max reps
    write_activity("A", 1600)
    labelio.save_meta("A", indoor=True, sport_type="Ride", labels_dir=labs)
    labelio.save_intervals("A", [(100, 700, "vo2max"), (800, 1400, "vo2max")], labels_dir=labs)
    # D: outdoor distractor, labelled with no intervals
    write_activity("D", 1100)
    labelio.save_meta("D", indoor=False, sport_type="Ride", labels_dir=labs)
    labelio.save_intervals("D", [], labels_dir=labs)
    # U: exported but not yet labelled -> must be skipped
    write_activity("U", 800)
    labelio.save_meta("U", indoor=True, sport_type="Ride", labels_dir=labs)

    return acts, labs


def _gt_predict(labs):
    def predict(aid, t, power):
        return labelio.load_annotation(aid, labels_dir=labs)["intervals"] or []
    return predict


def test_oracle_scores_perfect(bench):
    acts, labs = bench
    rep = evaluate.evaluate(predict=_gt_predict(labs), activities_dir=acts, labels_dir=labs)
    assert rep["n_activities"] == 2  # U skipped
    o = rep["overall"]
    assert o["precision"] == 1.0 and o["recall"] == 1.0 and o["f1"] == 1.0
    assert o["boundary"]["mean"] == 0.0
    assert rep["by_type"]["vo2max"]["recall"] == 1.0


def test_jittered_oracle_boundary_error(bench):
    acts, labs = bench

    def predict(aid, t, power):
        return [(s + 10, e + 10) for s, e, _ in
                (labelio.load_annotation(aid, labels_dir=labs)["intervals"] or [])]

    rep = evaluate.evaluate(predict=predict, activities_dir=acts, labels_dir=labs)
    assert rep["overall"]["recall"] == 1.0 and rep["overall"]["precision"] == 1.0
    assert rep["overall"]["boundary"]["mean"] == 20.0  # |10| + |10|


def test_empty_detector_is_zero_recall(bench):
    acts, labs = bench
    rep = evaluate.evaluate(activities_dir=acts, labels_dir=labs)  # default detect_intervals -> []
    assert rep["overall"]["recall"] == 0.0
    assert rep["overall"]["precision"] is None  # no predictions at all
    assert rep["overall"]["fn"] == 2


def test_merge_rule_blocks_whole_ride_gaming(bench):
    acts, labs = bench

    def predict(aid, t, power):
        return [(0, 1500)] if aid == "A" else []

    rep = evaluate.evaluate(predict=predict, activities_dir=acts, labels_dir=labs)
    # one ride-spanning prediction over two reps -> merge, not 2 TPs
    assert rep["overall"]["recall"] == 0.0
    assert rep["overall"]["precision"] == 0.0
    assert rep["overall"]["fn"] == 2 and rep["overall"]["fp"] == 1


def test_short_gt_excluded_from_scope(tmp_path):
    acts = tmp_path / "activities"
    labs = tmp_path / "labels"
    acts.mkdir()
    (acts / "S.csv").write_text("t,power\n" + "\n".join(f"{i},200" for i in range(700)) + "\n")
    labelio.save_meta("S", indoor=True, sport_type="Ride", labels_dir=labs)
    # a 30 s anaerobic rep (out of envelope) + a 300 s vo2max rep (in scope)
    labelio.save_intervals("S", [(100, 130, "anaerobic"), (200, 500, "vo2max")], labels_dir=labs)

    # a detector that only finds the in-scope rep
    def predict(aid, t, power):
        return [(200, 500)]

    rep = evaluate.evaluate(predict=predict, activities_dir=acts, labels_dir=labs)
    assert rep["excluded_short_gt"] == 1
    assert rep["overall"]["tp"] == 1 and rep["overall"]["fn"] == 0  # short one is not an FN
    assert "anaerobic" not in rep["by_type"]                        # excluded from stratification
    assert rep["by_type"]["vo2max"]["recall"] == 1.0


def test_stratification_structure(bench):
    acts, labs = bench
    rep = evaluate.evaluate(predict=_gt_predict(labs), activities_dir=acts, labels_dir=labs)
    assert set(rep["by_place"]) == {"indoor", "outdoor"}
    assert rep["by_place"]["indoor"]["tp"] == 2
    assert rep["by_type"]["vo2max"]["n"] == 2
    rendered = evaluate.format_report(rep)  # renders without error
    assert "Overall" in rendered
