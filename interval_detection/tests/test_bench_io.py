"""Tests for the bench label IO (no GUI)."""

import sys
from pathlib import Path

# bench/ is a script dir, not part of the installed package — add it to the path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench"))
import labelio  # noqa: E402


def test_save_and_load_intervals_round_trip(tmp_path: Path) -> None:
    labelio.save_intervals(
        "123",
        [(120.0, 300.0, "threshold"), (60.0, 150.0, "vo2max")],
        labels_dir=tmp_path,
    )
    ann = labelio.load_annotation("123", labels_dir=tmp_path)
    # sorted by start
    assert ann["intervals"] == [(60.0, 150.0, "vo2max"), (120.0, 300.0, "threshold")]


def test_unlabelled_vs_empty_are_distinct(tmp_path: Path) -> None:
    # never annotated -> intervals is None
    assert labelio.load_annotation("999", labels_dir=tmp_path)["intervals"] is None
    # explicitly saved empty -> intervals is []
    labelio.save_intervals("999", [], labels_dir=tmp_path)
    assert labelio.load_annotation("999", labels_dir=tmp_path)["intervals"] == []


def test_default_and_invalid_type_coerced_to_other(tmp_path: Path) -> None:
    labelio.save_intervals(
        "1", [(0.0, 90.0), (100.0, 200.0, "bogus")], labels_dir=tmp_path
    )
    types = [
        iv[2] for iv in labelio.load_annotation("1", labels_dir=tmp_path)["intervals"]
    ]
    assert types == ["other", "other"]


def test_save_drops_zero_or_negative_length(tmp_path: Path) -> None:
    labelio.save_intervals(
        "1", [(100.0, 100.0, "vo2max"), (50.0, 80.0, "threshold")], labels_dir=tmp_path
    )
    ann = labelio.load_annotation("1", labels_dir=tmp_path)
    assert ann["intervals"] == [(50.0, 80.0, "threshold")]


def test_save_meta_preserves_intervals(tmp_path: Path) -> None:
    labelio.save_intervals("5", [(10.0, 80.0, "vo2max")], labels_dir=tmp_path)
    labelio.save_meta("5", indoor=True, sport_type="Ride", labels_dir=tmp_path)
    ann = labelio.load_annotation("5", labels_dir=tmp_path)
    assert ann["indoor"] is True and ann["sport_type"] == "Ride"
    assert ann["intervals"] == [(10.0, 80.0, "vo2max")]


def test_save_meta_keeps_unlabelled_state(tmp_path: Path) -> None:
    # exporting meta before any labelling must NOT mark the activity as annotated
    labelio.save_meta("7", indoor=False, sport_type="Ride", labels_dir=tmp_path)
    ann = labelio.load_annotation("7", labels_dir=tmp_path)
    assert ann["indoor"] is False
    assert ann["intervals"] is None


def test_save_intervals_preserves_meta(tmp_path: Path) -> None:
    labelio.save_meta("8", indoor=True, sport_type="VirtualRide", labels_dir=tmp_path)
    labelio.save_intervals("8", [(0.0, 90.0, "sweet_spot")], labels_dir=tmp_path)
    ann = labelio.load_annotation("8", labels_dir=tmp_path)
    assert ann["indoor"] is True and ann["sport_type"] == "VirtualRide"
    assert ann["intervals"] == [(0.0, 90.0, "sweet_spot")]


def test_load_activity_csv(tmp_path: Path) -> None:
    (tmp_path / "7.csv").write_text("t,power\n0,100\n1,200\n2,150\n")
    t, p = labelio.load_activity_csv("7", activities_dir=tmp_path)
    assert list(t) == [0.0, 1.0, 2.0]
    assert list(p) == [100.0, 200.0, 150.0]


def test_list_activity_ids(tmp_path: Path) -> None:
    (tmp_path / "200.csv").write_text("t,power\n0,1\n")
    (tmp_path / "100.csv").write_text("t,power\n0,1\n")
    assert labelio.list_activity_ids(activities_dir=tmp_path) == ["100", "200"]
