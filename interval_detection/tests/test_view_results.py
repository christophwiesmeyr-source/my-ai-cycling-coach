"""Tests for the read-only results viewer (headless)."""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # no display in tests
import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402

BENCH = Path(__file__).resolve().parents[1] / "bench"
sys.path.insert(0, str(BENCH))
import labelio  # noqa: E402
import view_results  # noqa: E402


@pytest.fixture
def bench(tmp_path: Path) -> tuple[Path, Path]:
    acts = tmp_path / "activities"
    labs = tmp_path / "labels"
    acts.mkdir()
    n = 1500
    power = [100] * n
    for i in range(600, 1000):  # 400 s block at 300 W
        power[i] = 300
    (acts / "A.csv").write_text("t,power\n" + "\n".join(f"{i},{power[i]}" for i in range(n)) + "\n")
    labelio.save_meta("A", indoor=False, sport_type="Ride", labels_dir=labs)
    # one in-scope vo2max + one short (excluded) anaerobic
    labelio.save_intervals("A", [(600, 1000, "vo2max"), (100, 140, "anaerobic")], labels_dir=labs)
    return acts, labs


def test_result_for_activity(bench: tuple[Path, Path]) -> None:
    acts, labs = bench
    r = view_results.result_for_activity("A", ftp=250, activities_dir=acts, labels_dir=labs)
    assert r["threshold"] == 0.8 * 250
    assert len(r["gts"]) == 1 and len(r["excluded"]) == 1   # short one is excluded
    assert r["tp"] == 1 and r["fp"] == 0 and r["fn"] == 0
    assert len(r["preds"]) >= 1


def test_plot_activity_runs_headless(bench: tuple[Path, Path]) -> None:
    acts, labs = bench
    r = view_results.result_for_activity("A", ftp=250, activities_dir=acts, labels_dir=labs)
    fig, ax = plt.subplots()
    view_results.plot_activity(r, ax)  # must not raise
    assert ax.get_title().startswith("A")
    plt.close(fig)


def test_viewer_navigation_changes_index(bench: tuple[Path, Path]) -> None:
    acts, labs = bench
    r = view_results.result_for_activity("A", ftp=250, activities_dir=acts, labels_dir=labs)
    viewer = view_results.Viewer(["A", "B"], {"A": r, "B": r})
    assert viewer.idx == 0
    viewer._step(+1)
    assert viewer.idx == 1
    viewer._step(+1)          # wraps around
    assert viewer.idx == 0
    plt.close(viewer.fig)
