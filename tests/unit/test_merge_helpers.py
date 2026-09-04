"""Cover the merge's own decisions, without a matrix around them.

test_merge_cli.py and test_shards.py drive real legs and a real merge, which is
the only honest way to prove the whole thing works. It is also why the corners
go untested: producing four shards that disagree about their environment, or a
folder holding yesterday's leftovers beside today's, means orchestrating a run
to be wrong in one specific way.

These build the bundles directly instead. Each test is one rule the merge is
written around - a figure that covers only part of the run must say so, two
legs disagreeing must not have one of them silently picked - and those rules
are the ones whose failure is invisible: the report still renders, and the
numbers are simply wrong.
"""

import os
import time

import pytest

from pytest_html_reporter.merge import (
    MergeOptions,
    _coverage_data_files,
    _pairs,
    bundles_from_this_run,
    merge_coverage,
    merged_logs_notice,
    provenance_lines,
)
from pytest_html_reporter.shards import Bundle


def _bundle(shard_id="shard-1", token="", records=None, coverage=None,
            session_end=0.0, label="", path=None):
    payload = {
        "shard": {"id": shard_id, "label": label},
        "run": {"token": token, "session_end": session_end},
        "records": records if records is not None else [],
        "coverage": coverage,
    }

    return Bundle(path or os.path.join(os.sep, "builds", shard_id, "bundle.json"),
                  payload)


def _summary(percent=80.0, statements=100, files_total=3):
    return {"files": [], "files_total": files_total, "percent": percent,
            "statements": statements, "covered": 80, "missing": 20,
            "excluded": 0, "branches": 0, "branches_covered": 0, "partial": 0,
            "branch": False, "generated": "", "source": "coverage.json"}


class _Meta:
    def __init__(self, capture_notices=()):
        self.capture_notices = list(capture_notices)


# ------------------------------------------------- bundles_from_this_run ---

def test_without_a_token_every_bundle_in_the_folder_is_merged():
    """The behaviour before legs were given one, and still the default."""
    bundles = [_bundle("a"), _bundle("b")]

    mine, foreign = bundles_from_this_run(bundles, "")

    assert mine == bundles
    assert foreign == []


def test_a_leg_with_a_token_keeps_only_the_bundles_carrying_it():
    mine_bundle = _bundle("a", token="run-7")
    theirs = _bundle("b", token="run-6")

    mine, foreign = bundles_from_this_run([mine_bundle, theirs], "run-7")

    assert mine == [mine_bundle]
    assert foreign == [theirs]


def test_a_bundle_with_no_token_is_put_aside_rather_than_merged():
    """The failure it causes is invisible: the totals are simply larger than
    the run was."""
    tokenless = _bundle("b")

    mine, foreign = bundles_from_this_run([_bundle("a", token="run-7"), tokenless],
                                          "run-7")

    assert [bundle.shard.id for bundle in mine] == ["a"]
    assert foreign == [tokenless]


def test_a_folder_holding_nothing_but_another_runs_leftovers_merges_nothing():
    mine, foreign = bundles_from_this_run([_bundle("a", token="run-6")], "run-7")

    assert mine == []
    assert len(foreign) == 1


# ------------------------------------------------------ provenance_lines ---

def test_every_merged_bundle_is_named_with_what_it_contributed():
    """Printed every time, with no threshold: there is no honest way to decide
    from inside a merge that a bundle is stale."""
    finished = time.mktime((2024, 9, 1, 14, 18, 22, 0, 0, -1))
    bundle = _bundle("gw0", records=[{"nodeid": "a"}, {"nodeid": "b"}],
                     session_end=finished)

    line, = provenance_lines([bundle])

    assert line.startswith("shard gw0: 2 tests, finished 2024-09-01 14:18:22")


def test_one_test_is_counted_in_the_singular():
    line, = provenance_lines([_bundle("gw0", records=[{"nodeid": "a"}],
                                      session_end=1.0)])

    assert "1 test," in line


def test_a_collection_error_is_not_counted_as_a_test():
    bundle = _bundle("gw0", records=[{"nodeid": "a"},
                                     {"nodeid": "b", "collect": True}],
                     session_end=1.0)

    assert "1 test," in provenance_lines([bundle])[0]


def test_a_bundle_that_never_recorded_when_it_finished_says_so():
    """Printing the epoch instead would read as a real date."""
    line, = provenance_lines([_bundle("gw0", session_end=0.0)])

    assert "at a time it did not record" in line


def test_nothing_merged_is_nothing_to_say():
    assert provenance_lines([]) == []


# -------------------------------------------------------- merge_coverage ---

def test_coverage_switched_off_is_not_read_at_all():
    summary, notice = merge_coverage([_bundle(coverage=_summary())],
                                     MergeOptions(report_coverage="none"))

    assert summary is None
    assert notice == ""


def test_a_single_shard_that_measured_coverage_reports_it_plainly():
    measured = _summary()

    summary, notice = merge_coverage([_bundle(coverage=measured)], MergeOptions())

    assert summary is measured
    assert notice == ""


def test_one_shard_of_several_measuring_coverage_says_what_it_covers():
    """The figure is real but it is that shard's share, and a headline number
    that quietly means a quarter of the run is worse than no number."""
    summary, notice = merge_coverage(
        [_bundle("a", coverage=_summary()), _bundle("b"), _bundle("c")],
        MergeOptions())

    assert summary is not None
    assert "1 of 3 shards measured coverage" in notice


def test_several_shards_measuring_coverage_are_not_reconciled_by_guessing():
    """Averaging them would be a made-up number; adding them counts shared
    lines twice. The answer is to combine the data, and the notice says how."""
    summary, notice = merge_coverage(
        [_bundle("a", coverage=_summary()), _bundle("b", coverage=_summary())],
        MergeOptions())

    assert summary is None
    assert "cannot be reconciled" in notice
    assert "--report-coverage-file" in notice
    assert "--coverage-data" in notice


def test_no_shard_measuring_coverage_says_how_to_get_some():
    """An empty Coverage tab on a sharded run reads as a broken feature; the
    notice is what makes it read as a run that was never asked to measure."""
    summary, notice = merge_coverage([_bundle("a"), _bundle("b")], MergeOptions())

    assert summary is None
    assert "none of them was asked for coverage" in notice
    assert "--report-coverage-file" in notice


def test_a_named_coverage_file_is_read_in_preference_to_the_shards(tmp_path):
    report = tmp_path / "coverage.json"
    report.write_text(
        '{"totals": {"num_statements": 100, "covered_lines": 90, '
        '"missing_lines": 10, "excluded_lines": 0, "num_branches": 0, '
        '"num_partial_branches": 0}, "files": {}}')

    summary, notice = merge_coverage(
        [_bundle(coverage=_summary())],
        MergeOptions(report_coverage_file=str(report)))

    assert summary["statements"] == 100
    assert notice == ""


def test_a_named_coverage_file_that_is_not_coverage_says_which_file(tmp_path):
    """Pointing the flag at the wrong file is the ordinary mistake, and a
    silent empty tab does not help anybody find it."""
    report = tmp_path / "notes.txt"
    report.write_text("this is not coverage data")

    summary, notice = merge_coverage(
        [], MergeOptions(report_coverage_file=str(report)))

    assert summary is None
    assert str(report) in notice


def test_coverage_data_naming_nothing_readable_says_so(tmp_path):
    pytest.importorskip("coverage")

    summary, notice = merge_coverage(
        [], MergeOptions(coverage_data=[str(tmp_path)]))

    assert summary is None
    assert "named nothing that looks like a coverage data file" in notice


# --------------------------------------------------- _coverage_data_files ---

def test_a_folder_is_searched_for_the_data_files_inside_it(tmp_path):
    (tmp_path / ".coverage").write_text("")
    (tmp_path / ".coverage.host.1").write_text("")
    (tmp_path / "report.json").write_text("{}")

    found = _coverage_data_files([str(tmp_path)])

    assert [os.path.basename(path) for path in found] == \
        [".coverage", ".coverage.host.1"]


def test_a_file_named_directly_is_taken_as_it_is(tmp_path):
    data = tmp_path / "coverage-from-ci"
    data.write_text("")

    assert _coverage_data_files([str(data)]) == [str(data)]


def test_a_path_that_is_not_there_contributes_nothing(tmp_path):
    assert _coverage_data_files([str(tmp_path / "nope")]) == []


def test_folders_and_files_can_be_named_together(tmp_path):
    folder = tmp_path / "shards"
    folder.mkdir()
    (folder / ".coverage").write_text("")
    loose = tmp_path / ".coverage.extra"
    loose.write_text("")

    found = _coverage_data_files([str(folder), str(loose)])

    assert len(found) == 2


# ---------------------------------------------------------------- _pairs ---

def test_build_info_is_split_the_way_the_pytest_flag_splits_it():
    assert _pairs(["branch=main", "team=payments"]) == \
        [("branch", "main"), ("team", "payments")]


def test_the_spacing_somebody_typed_is_not_kept():
    assert _pairs(["  branch = main  "]) == [("branch", "main")]


def test_a_value_holding_an_equals_sign_survives_intact():
    assert _pairs(["url=https://ci/build?a=1"]) == \
        [("url", "https://ci/build?a=1")]


def test_an_entry_with_no_value_is_still_a_row():
    assert _pairs(["branch"]) == [("branch", "")]


def test_blank_entries_are_dropped():
    assert _pairs(["", "   ", "branch=main"]) == [("branch", "main")]


# --------------------------------------------------- merged_logs_notice ---

def test_shards_that_all_captured_the_same_way_say_it_once():
    """Read off each shard's own config: under the shim the merge cannot tell
    that -s was passed, so the column would lose its explanation."""
    notice = "stdout and stderr are not captured while pytest runs with -s"

    assert merged_logs_notice(_Meta([("gw0", notice), ("gw1", notice)])) == notice


def test_shards_that_captured_differently_are_named_one_by_one():
    text = merged_logs_notice(_Meta([("gw0", "no capture"), ("gw1", "logging only")]))

    assert "gw0: no capture" in text
    assert "gw1: logging only" in text


def test_a_matrix_where_every_shard_captured_normally_says_nothing():
    assert merged_logs_notice(_Meta([])) == ""
