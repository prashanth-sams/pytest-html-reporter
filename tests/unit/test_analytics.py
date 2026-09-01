"""Cover the Analytics tab - the one view that reads across builds.

Every other tab is one run seen from a different angle. This one is every
retained build seen from the test's angle, so what is worth pinning down here
is the reading of a history: which sequences count as flaky, which count as
broken, what a skip does and does not say, and what happens on the first run,
when there is no history at all.

The builds are written as archive files rather than driven through pytest:
that is exactly the shape the plugin leaves on disk, and it lets a five-build
history be a few lines instead of five subprocess runs.
"""

import json
import re

from pytest_html_reporter.analytics import (
    duration_buckets,
    generate_analytics,
    histories,
    movements,
    outcome,
    read_builds,
    stability_score,
)
from pytest_html_reporter.const_vars import ConfigVars


# --------------------------------------------------------------------------
# building a history on disk
# --------------------------------------------------------------------------

def _build(stamp, tests, suite="tests/test_thing.py"):
    """One build, in the shape output.json is written in."""
    return {
        "date": "September 01, 2026",
        "start_time": stamp,
        "total_suite": 1,
        "status": "PASS",
        "total_tests": str(len(tests)),
        "content": {
            "suites": {
                "0": {
                    "suite_name": suite,
                    "tests": {
                        str(i): {
                            "status": status,
                            "message": "",
                            "test_name": name,
                            "rerun": str(rerun),
                            "duration": duration,
                        }
                        for i, (name, status, rerun, duration) in enumerate(tests)
                    },
                    "status": {},
                }
            }
        },
    }


def _history(tmp_path, *builds):
    """Lay builds out the way the plugin does: the newest is output.json."""
    archive = tmp_path / "archive"
    archive.mkdir(parents=True)

    for build in builds[:-1]:
        path = archive / ("output_%s.json" % build["start_time"])
        path.write_text(json.dumps(build), encoding="utf-8")

    (tmp_path / "output.json").write_text(json.dumps(builds[-1]), encoding="utf-8")

    return str(tmp_path)


def _run(name, statuses, rerun=0, duration=0.1):
    """One test's statuses, oldest build first, as a build per status."""
    return [_build(1000.0 + i, [(name, status, rerun, duration)])
            for i, status in enumerate(statuses)]


def _read(tmp_path, name, statuses, **kwargs):
    base = _history(tmp_path, *_run(name, statuses, **kwargs))

    return histories(read_builds(base))["tests/test_thing.py::%s" % name]


# --------------------------------------------------------------------------
# what a status means
# --------------------------------------------------------------------------

def test_only_a_failure_counts_as_a_failure():
    assert outcome("FAIL") == "fail"
    assert outcome("ERROR") == "fail"


def test_an_expected_outcome_is_not_a_failure():
    """xfail is the suite working as declared, not a test misbehaving.

    Counting it as a failure would put every xfail-marked test at the top of
    the "always failing" list, where nothing is wrong.
    """
    assert outcome("xFAIL") == "pass"
    assert outcome("xPASS") == "pass"
    assert outcome("PASS") == "pass"


def test_a_skip_is_its_own_thing():
    assert outcome("SKIP") == "skip"


def test_an_unknown_status_is_not_read_as_a_failure():
    """An archive from a newer version must not invent failures here."""
    assert outcome("") == "pass"
    assert outcome(None) == "pass"


# --------------------------------------------------------------------------
# reading one test's history
# --------------------------------------------------------------------------

def test_a_test_that_always_passed_is_stable(tmp_path):
    history = _read(tmp_path, "test_ok", ["PASS"] * 4)

    assert history["pass_rate"] == 100
    assert history["flips"] == 0
    assert history["flaky"] is False
    assert history["broken"] is False
    assert history["streak"] == 4


def test_a_test_that_alternates_is_flaky(tmp_path):
    history = _read(tmp_path, "test_flip", ["PASS", "FAIL", "PASS", "FAIL"])

    assert history["flips"] == 3
    assert history["pass_rate"] == 50
    assert history["flaky"] is True
    assert history["broken"] is False


def test_a_test_that_never_passed_is_broken_not_flaky(tmp_path):
    """The distinction is the whole point of the table.

    A test that only ever fails is a bug with an owner; sending it to the top
    of a flakiness list sends somebody hunting a race that is not there.
    """
    history = _read(tmp_path, "test_down", ["FAIL"] * 5)

    assert history["broken"] is True
    assert history["flaky"] is False
    assert history["streak"] == 5
    assert history["pass_rate"] == 0


def test_one_failing_build_is_not_yet_a_standing_failure(tmp_path):
    """One failure is a failure; a standing one is a different conversation."""
    history = _read(tmp_path, "test_new_fail", ["FAIL"])

    assert history["broken"] is False
    assert history["pass_rate"] == 0


def test_a_retry_inside_one_build_is_enough_to_be_flaky(tmp_path):
    """The least ambiguous evidence there is: same build, two answers."""
    history = _read(tmp_path, "test_retried", ["PASS"], rerun=2)

    assert history["reruns"] == 2
    assert history["flips"] == 0
    assert history["flaky"] is True


def test_skips_do_not_count_as_flipping(tmp_path):
    """A test skipped between two passes has not changed its mind twice."""
    history = _read(tmp_path, "test_gap", ["PASS", "SKIP", "SKIP", "PASS"])

    assert history["flips"] == 0
    assert history["pass_rate"] == 100
    assert history["flaky"] is False
    assert history["runs"] == 4
    assert history["skips"] == 2


def test_a_test_only_ever_skipped_has_no_pass_rate(tmp_path):
    """Nothing was decided, which is not the same as a rate of zero."""
    history = _read(tmp_path, "test_never_ran", ["SKIP"] * 3)

    assert history["pass_rate"] is None
    assert history["streak"] == 0


def test_the_streak_is_counted_from_the_newest_build(tmp_path):
    history = _read(tmp_path, "test_recent", ["PASS", "PASS", "FAIL", "FAIL"])

    assert history["streak"] == 2
    assert history["outcome"] == "fail"


def test_a_test_missing_from_the_latest_build_is_marked(tmp_path):
    base = _history(tmp_path,
                    _build(1000.0, [("test_kept", "PASS", 0, 0.1),
                                    ("test_dropped", "PASS", 0, 0.1)]),
                    _build(1001.0, [("test_kept", "PASS", 0, 0.1)]))
    tests = histories(read_builds(base))

    assert tests["tests/test_thing.py::test_kept"]["current"] is True
    assert tests["tests/test_thing.py::test_dropped"]["current"] is False


# --------------------------------------------------------------------------
# reading the builds
# --------------------------------------------------------------------------

def test_builds_are_ordered_oldest_first_with_this_run_last(tmp_path):
    base = _history(tmp_path,
                    _build(1000.0, [("a", "PASS", 0, 0.1)]),
                    _build(1002.0, [("b", "PASS", 0, 0.1)]),
                    _build(1003.0, [("c", "PASS", 0, 0.1)]))
    builds = read_builds(base)

    assert [list(b["tests"])[0].split("::")[1] for b in builds] == ["a", "b", "c"]


def test_builds_sort_on_the_stamp_not_the_file_name(tmp_path):
    """The name carries the same number, but as text.

    "1788194287.2" sorts after "1788194287.271306" as a string and before it
    as a number, which would silently shuffle the history.
    """
    base = _history(tmp_path,
                    _build(1788194287.271306, [("first", "PASS", 0, 0.1)]),
                    _build(1788194287.9, [("second", "PASS", 0, 0.1)]),
                    _build(1788194288.0, [("third", "PASS", 0, 0.1)]))
    builds = read_builds(base)

    assert [list(b["tests"])[0].split("::")[1] for b in builds] == ["first", "second", "third"]


def test_a_broken_archive_is_skipped_not_fatal(tmp_path):
    """One unreadable file must not cost the whole tab."""
    base = _history(tmp_path,
                    _build(1000.0, [("a", "PASS", 0, 0.1)]),
                    _build(1001.0, [("b", "PASS", 0, 0.1)]))
    (tmp_path / "archive" / "output_broken.json").write_text("{not json", encoding="utf-8")

    assert len(read_builds(base)) == 2


def test_builds_inside_one_minute_are_still_told_apart(tmp_path):
    """A pipeline that reruns the suite produces same-minute builds.

    Three identical ticks on an x axis is a chart nobody can read.
    """
    base = _history(tmp_path,
                    _build(1000.0, [("a", "PASS", 0, 0.1)]),
                    _build(1001.0, [("a", "PASS", 0, 0.1)]),
                    _build(1002.0, [("a", "PASS", 0, 0.1)]))
    labels = [build["label"] for build in read_builds(base)]

    assert len(set(labels)) == 3


def test_an_archive_without_durations_is_read_as_unmeasured(tmp_path):
    """Builds predating the duration key must not be drawn as instant."""
    build = _build(1000.0, [("a", "PASS", 0, 0.1)])
    del build["content"]["suites"]["0"]["tests"]["0"]["duration"]

    base = _history(tmp_path, build, _build(1001.0, [("a", "PASS", 0, 0.4)]))
    builds = read_builds(base)

    assert builds[0]["duration"] is None
    assert builds[1]["duration"] == 0.4


# --------------------------------------------------------------------------
# what moved between builds
# --------------------------------------------------------------------------

def test_movement_names_what_changed(tmp_path):
    base = _history(tmp_path,
                    _build(1000.0, [("broke", "PASS", 0, 0.1),
                                    ("mended", "FAIL", 0, 0.1),
                                    ("gone", "PASS", 0, 0.1)]),
                    _build(1001.0, [("broke", "FAIL", 0, 0.1),
                                    ("mended", "PASS", 0, 0.1),
                                    ("fresh", "PASS", 0, 0.1)]))
    step = movements(read_builds(base))[-1]

    assert [k.split("::")[1] for k in step["regressed"]] == ["broke"]
    assert [k.split("::")[1] for k in step["fixed"]] == ["mended"]
    assert [k.split("::")[1] for k in step["added"]] == ["fresh"]
    assert [k.split("::")[1] for k in step["removed"]] == ["gone"]


def test_a_first_build_has_nothing_to_have_moved_from(tmp_path):
    base = _history(tmp_path, _build(1000.0, [("a", "PASS", 0, 0.1)]))

    assert movements(read_builds(base)) == []


# --------------------------------------------------------------------------
# the aggregate numbers
# --------------------------------------------------------------------------

def test_durations_land_in_their_bands(tmp_path):
    base = _history(tmp_path, _build(1000.0, [
        ("quick", "PASS", 0, 0.05),
        ("brisk", "PASS", 0, 0.3),
        ("slow", "PASS", 0, 3.0),
        ("crawling", "PASS", 0, 120.0),
    ]))
    counts = duration_buckets(histories(read_builds(base)))

    # < 100ms, 100-500ms, 0.5-1s, 1-5s, 5-10s, 10-30s, 30s+
    assert counts == [1, 1, 0, 1, 0, 0, 1]


def test_a_run_that_measured_nothing_draws_no_histogram(tmp_path):
    """An empty list, not seven zero bars claiming every test was instant."""
    build = _build(1000.0, [("a", "PASS", 0, 0.1)])
    del build["content"]["suites"]["0"]["tests"]["0"]["duration"]

    assert duration_buckets(histories(read_builds(_history(tmp_path, build)))) == []


def test_a_clean_suite_scores_full_marks(tmp_path):
    base = _history(tmp_path, *_run("test_ok", ["PASS"] * 4))

    assert stability_score(histories(read_builds(base))) == 100


def test_flipping_scores_worse_than_failing_outright(tmp_path):
    """Both pass half the time; only one of them tells you anything.

    A test that alternates has the same pass rate as one the team already
    knows is broken, and is the more expensive of the two to live with.
    """
    flipping = _history(tmp_path / "flip", *_run("t", ["PASS", "FAIL", "PASS", "FAIL"]))
    settled = _history(tmp_path / "settled", *_run("t", ["PASS", "PASS", "FAIL", "FAIL"]))

    assert (stability_score(histories(read_builds(flipping)))
            < stability_score(histories(read_builds(settled))))


# --------------------------------------------------------------------------
# what reaches the page
# --------------------------------------------------------------------------

def _generate(tmp_path, *builds):
    generate_analytics(_history(tmp_path, *builds))


def test_the_first_run_says_so_rather_than_drawing_empty_axes(tmp_path):
    _generate(tmp_path, _build(1000.0, [("a", "PASS", 0, 0.1)]))

    assert ConfigVars._analytics_state == "is-solo"
    assert ConfigVars._analytics_builds == "1"
    assert "this run only" in ConfigVars._analytics_scope


def test_a_second_run_opens_the_trends(tmp_path):
    _generate(tmp_path,
              _build(1000.0, [("a", "PASS", 0, 0.1)]),
              _build(1001.0, [("a", "FAIL", 0, 0.1)]))

    assert ConfigVars._analytics_state == ""
    assert ConfigVars._analytics_builds == "2"
    assert json.loads(ConfigVars._analytics_pass_rate) == [100.0, 0.0]


def test_a_build_that_decided_nothing_leaves_a_gap_not_a_zero(tmp_path):
    """Drawing an all-skipped build as 0% invents a cliff that never happened."""
    _generate(tmp_path,
              _build(1000.0, [("a", "PASS", 0, 0.1)]),
              _build(1001.0, [("a", "SKIP", 0, 0.1)]),
              _build(1002.0, [("a", "PASS", 0, 0.1)]))

    assert json.loads(ConfigVars._analytics_pass_rate) == [100.0, None, 100.0]


def test_the_page_is_handed_valid_arrays_for_every_series(tmp_path):
    _generate(tmp_path,
              _build(1000.0, [("a", "PASS", 0, 0.1)]),
              _build(1001.0, [("a", "PASS", 0, 0.1), ("b", "FAIL", 0, 0.2)]))

    for series in (ConfigVars._analytics_labels,
                   ConfigVars._analytics_growth,
                   ConfigVars._analytics_flow_labels,
                   ConfigVars._analytics_flow_fixed,
                   ConfigVars._analytics_flow_regressed,
                   ConfigVars._analytics_flow_added,
                   ConfigVars._analytics_flow_removed,
                   ConfigVars._analytics_buckets,
                   ConfigVars._analytics_bucket_labels):
        assert isinstance(json.loads(series), list)

    assert json.loads(ConfigVars._analytics_growth) == [1, 2]


def test_a_test_name_never_reaches_the_page_as_source_code(tmp_path):
    """The slowest-tests names ride on an attribute, escaped, and are parsed
    back - so a parametrized case can be called anything at all without
    landing anywhere the browser is willing to run it."""
    _generate(tmp_path, _build(1000.0, [("test_x[<script>alert(1)</script>]", "PASS", 0, 5.0)]))

    assert "<script>" not in ConfigVars._analytics_slowest
    assert "&lt;script&gt;" in ConfigVars._analytics_slowest


def test_a_name_that_looks_like_a_placeholder_is_not_filled_in(tmp_path):
    """The page is assembled by substituting %(name)% - a test named like one
    would otherwise be replaced instead of shown."""
    _generate(tmp_path, _build(1000.0, [("test_x[%(archives)%]", "FAIL", 0, 0.1)]))

    assert "%(archives)%" not in ConfigVars._analytics_rows
    assert "%(archives)%" not in ConfigVars._analytics_movement


def test_the_worst_behaved_tests_are_at_the_top(tmp_path):
    """The table is sortable, but what it opens on should already be the list
    to work through."""
    _generate(tmp_path,
              _build(1000.0, [("fine", "PASS", 0, 0.1), ("down", "FAIL", 0, 0.1),
                              ("flips", "PASS", 0, 0.1)]),
              _build(1001.0, [("fine", "PASS", 0, 0.1), ("down", "FAIL", 0, 0.1),
                              ("flips", "FAIL", 0, 0.1)]))
    rows = ConfigVars._analytics_rows

    assert rows.index("down") < rows.index("flips") < rows.index("fine")


def test_the_history_strip_carries_a_sort_value(tmp_path):
    """The strip is markup with no text in it, so without an explicit order
    every row ties and clicking the History header does nothing."""
    _generate(tmp_path,
              _build(1000.0, [("fine", "PASS", 0, 0.1), ("down", "FAIL", 0, 0.1),
                              ("gone", "SKIP", 0, 0.1)]),
              _build(1001.0, [("fine", "PASS", 0, 0.1), ("down", "FAIL", 0, 0.1),
                              ("gone", "SKIP", 0, 0.1)]))

    pairs = re.findall(r'an-name__test">(\w+)<.*?an-spark" data-order="([-\d.]+)"',
                       ConfigVars._analytics_rows, re.S)
    order = {name: float(value) for name, value in pairs}

    assert order["down"] < order["fine"]

    # A strip of nothing but skips has decided nothing, so it sits below both.
    assert order["gone"] < order["down"]


def test_a_run_with_nothing_on_disk_is_left_alone(tmp_path):
    """No output.json is not a crash - it is a report that was never written."""
    generate_analytics(str(tmp_path))
