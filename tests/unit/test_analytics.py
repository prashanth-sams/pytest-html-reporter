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
import os
import re

from pytest_html_reporter.analytics import (
    FAULT_TYPES,
    MOVEMENT_NAMES,
    OTHER,
    UNOWNED,
    UNRATED,
    _duration_text,
    _owner_headline,
    _severity_headline,
    duration_buckets,
    exception_type,
    failure_headline,
    failure_types,
    generate_analytics,
    histories,
    movements,
    outcome,
    owner_totals,
    read_builds,
    severity_totals,
    stability_score,
)
from pytest_html_reporter.const_vars import ConfigVars

TEMPLATE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "html_page", "html", "template.html",
)


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


def test_a_duration_that_cannot_be_one_is_read_as_unmeasured(tmp_path):
    """An epoch stamp written where a duration belongs is not a duration.

    Reports written before the duration came from pytest's own phase timings
    billed a test that merged a shard bundle mid-run with every second since
    1970, and those archives are still on disk. Summed, one of them is the
    whole "time in tests" tile; drawn, it is the only bar the slowest-tests
    chart has room for.
    """
    base = _history(tmp_path, _build(1000.0, [("sane", "PASS", 0, 0.4),
                                              ("epoch", "PASS", 0, 1788535128.1),
                                              ("negative", "PASS", 0, -3.0)]))
    build = read_builds(base)[0]
    tests = build["tests"]

    assert tests["tests/test_thing.py::epoch"]["duration"] is None
    assert tests["tests/test_thing.py::negative"]["duration"] is None
    assert build["duration"] == 0.4


def test_a_long_run_is_read_in_hours():
    """Minutes stop being a unit somewhere, and "608889402m 03s" is past it."""
    assert _duration_text(0.25) == "250ms"
    assert _duration_text(9.4) == "9.4s"
    assert _duration_text(125) == "2m 05s"
    assert _duration_text(3600 * 3 + 60 * 7) == "3h 07m"


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
# grouping failures by the exception they came out of
# --------------------------------------------------------------------------

def _failed(stamp, *messages, **kwargs):
    """One build whose tests all failed, each with the message it failed with."""
    build = _build(stamp, [("test_%d" % i, kwargs.get("status", "FAIL"), 0, 0.1)
                           for i, _ in enumerate(messages)])

    for i, message in enumerate(messages):
        build["content"]["suites"]["0"]["tests"][str(i)]["message"] = message

    return build


def _types(tmp_path, *builds):
    """The failure groups of the last build, against the one before it.

    Read off disk rather than out of the dict, so what is grouped here is what
    survives a round trip through an archive - which is the only form the
    older builds are ever in.
    """
    read = read_builds(_history(tmp_path, *builds))

    return failure_types(read[-1], read[-2] if len(read) > 1 else None)


def _grouped(tmp_path, *builds):
    return {entry["name"]: entry["count"] for entry in _types(tmp_path, *builds)}


def test_the_exception_is_read_off_the_line_it_is_raised_on():
    assert exception_type("   ValueError: bad input\n") == "ValueError"
    assert exception_type("TimeoutException: Message: waited 10s") == "TimeoutException"


def test_a_dotted_exception_groups_with_its_bare_name():
    """Which of the two a message carries is down to how the traceback was
    rendered, not to what went wrong."""
    dotted = "selenium.common.exceptions.TimeoutException: Message: gone"

    assert exception_type(dotted) == exception_type("TimeoutException: gone")


def test_a_bare_assert_is_read_as_an_assertion():
    """pytest prints these with no type name at all, and they are far too
    common a failure to leave in the unclassified pile."""
    assert exception_type("   assert 1 == 2\n") == "AssertionError"


def test_an_error_keeps_its_whole_traceback_and_is_still_read():
    """A failure is stored as pytest's E-lines with the marker taken off; an
    error is stored as the traceback exactly as printed."""
    traceback = ("@pytest.fixture\n"
                 "    def broken():\n"
                 ">       raise RuntimeError('boom')\n"
                 "E       RuntimeError: boom\n")

    assert exception_type(traceback) == "RuntimeError"


def test_the_exception_that_surfaced_wins_over_the_one_it_came_from():
    """A chained failure prints the original traceback first and the exception
    that actually came out last - which is the one pytest itself reports."""
    chained = ("   ValueError: bad\n\n"
               "During handling of the above exception, another exception occurred:\n\n"
               "   RuntimeError: worse\n")

    assert exception_type(chained) == "RuntimeError"


def test_a_diff_line_is_not_mistaken_for_a_raised_exception():
    """An assertion prints what it compared, and that can be anything at all -
    including the text of somebody else's exception."""
    diff = ("   AssertionError: assert '- ValueError: nope' == '+ KeyError: x'\n"
            "     - + KeyError: x\n"
            "     + - ValueError: nope\n")

    assert exception_type(diff) == "AssertionError"


def test_colour_written_into_the_message_does_not_hide_the_exception():
    assert exception_type("   \x1b[31mValueError\x1b[0m: bad") == "ValueError"


def test_a_message_naming_nothing_is_left_unclassified():
    """Saying more than the message supports is how a report stops being
    believed: a fixture that could not be found names no exception."""
    assert exception_type("file /x/test_a.py, line 3\n"
                          "E       fixture 'missing' not found\n") == ""
    assert exception_type("") == ""


def test_only_the_failures_are_grouped(tmp_path):
    """A pass carries no message, and an expected failure is an outcome the
    suite asked for rather than one anybody is triaging."""
    build = _build(1000.0, [("a", "PASS", 0, 0.1), ("b", "xFAIL", 0, 0.1),
                            ("c", "FAIL", 0, 0.1)])
    build["content"]["suites"]["0"]["tests"]["2"]["message"] = "   ValueError: no\n"

    assert _grouped(tmp_path, build) == {"ValueError": 1}


def test_an_error_is_grouped_beside_the_failures(tmp_path):
    """It failed for a reason worth grouping, and the reason is in the same
    field - the tab reads ERROR with FAIL everywhere else too."""
    build = _failed(1000.0, "   ValueError: no\n", status="ERROR")

    assert _grouped(tmp_path, build) == {"ValueError": 1}


def test_the_largest_group_leads_and_carries_its_share(tmp_path):
    entries = _types(tmp_path, _failed(
        1000.0,
        "   TimeoutException: a\n", "   TimeoutException: b\n",
        "   TimeoutException: c\n", "   ValueError: d\n"))

    assert [(entry["name"], entry["count"], entry["share"]) for entry in entries] == [
        ("TimeoutException", 3, 75), ("ValueError", 1, 25)]


def test_the_unclassified_pile_is_held_at_the_bottom_however_large_it_is(tmp_path):
    """A list headed by "Unclassified: 3" is a list that has answered nothing."""
    entries = _types(tmp_path, _failed(
        1000.0, "no exception here", "nor here", "or here", "   ValueError: d\n"))

    assert [entry["name"] for entry in entries] == ["ValueError", OTHER]


def test_a_group_is_compared_against_the_build_before(tmp_path):
    before = _failed(1000.0, "   TimeoutException: a\n", "   TimeoutException: b\n",
                     "   ValueError: c\n")
    after = _failed(1001.0, "   TimeoutException: a\n", "   KeyError: b\n")

    entries = {entry["name"]: entry for entry in _types(tmp_path, before, after)}

    assert entries["TimeoutException"]["delta"] == -1
    # A failure mode the last build did not have at all, not two more of one it
    # already had.
    assert entries["KeyError"]["delta"] == entries["KeyError"]["count"] == 1


def test_a_first_build_has_no_movement_to_report(tmp_path):
    """Which is not the same as a group that has not moved, and reads
    differently on the page."""
    entries = _types(tmp_path, _failed(1000.0, "   ValueError: a\n"))

    assert entries[0]["delta"] is None


def test_the_headline_says_where_to_start(tmp_path):
    build = _failed(1000.0, "   TimeoutException: a\n", "   TimeoutException: b\n",
                    "   ValueError: c\n")

    assert failure_headline(_types(tmp_path, build)) == "3 failures, 2 are TimeoutException"


def test_the_headline_says_so_when_every_failure_is_the_same_thing(tmp_path):
    build = _failed(1000.0, "   TimeoutException: a\n", "   TimeoutException: b\n")

    assert failure_headline(_types(tmp_path, build)) == "all 2 failures are TimeoutException"


def test_the_headline_says_so_when_nothing_groups_with_anything(tmp_path):
    """Naming the first of twelve one-offs reads as a lead. That a run failed
    twelve different ways is the finding."""
    build = _failed(1000.0, "   ValueError: a\n", "   KeyError: b\n", "   IndexError: c\n")

    assert failure_headline(_types(tmp_path, build)) == \
        "3 failures, every one a different exception"


def test_a_green_run_has_no_headline_at_all(tmp_path):
    assert failure_headline(_types(tmp_path, _build(1000.0, [("a", "PASS", 0, 0.1)]))) == ""


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
    assert "%(archives)%" not in ConfigVars._analytics_faults


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


def test_the_failure_panel_names_the_tests_under_each_exception(tmp_path):
    """"9 TimeoutException" says what broke; the names say whether it is one
    page object nine tests go through or nine unrelated waits."""
    _generate(tmp_path, _failed(1000.0, "   TimeoutException: a\n",
                                "   TimeoutException: b\n", "   ValueError: c\n"))

    assert "TimeoutException" in ConfigVars._analytics_faults
    assert "test_0" in ConfigVars._analytics_faults
    assert ConfigVars._analytics_fault_note == "3 failures, 2 are TimeoutException"
    assert ConfigVars._analytics_fault_state == ""


def test_the_failure_panel_is_answerable_on_a_first_run(tmp_path):
    """Every other longitudinal panel is blank until there are two builds.
    This one reads the current build alone, and a first run that is red is
    exactly when somebody wants it."""
    _generate(tmp_path, _failed(1000.0, "   ValueError: a\n"))

    assert ConfigVars._analytics_state == "is-solo"
    assert ConfigVars._analytics_fault_state == ""
    assert "ValueError" in ConfigVars._analytics_faults


def test_a_green_run_has_no_failure_panel(tmp_path):
    """A card standing empty over a passing run is a card that gets ignored
    when it does have something to say."""
    _generate(tmp_path, _build(1000.0, [("a", "PASS", 0, 0.1)]))

    assert ConfigVars._analytics_fault_state == "is-empty"
    assert ConfigVars._analytics_faults == ""
    assert ConfigVars._analytics_fault_note == ""


def test_a_test_named_under_a_failure_group_reaches_the_page_escaped(tmp_path):
    """The names listed under each exception are the same arbitrary text as
    everywhere else - a parametrized case can be called anything at all."""
    build = _failed(1000.0, "   ValueError: x\n")
    build["content"]["suites"]["0"]["tests"]["0"]["test_name"] = "test_x[<script>alert(1)</script>]"

    _generate(tmp_path, build)

    assert "<script>" not in ConfigVars._analytics_faults
    assert "&lt;script&gt;" in ConfigVars._analytics_faults


def test_a_truncated_list_is_written_out_in_full_behind_the_card(tmp_path):
    """The overlay shows the card's own items with the hiding taken off, so
    what a card lists and what opening it shows cannot drift apart - and no
    test name is written into the page twice to make that work."""
    failures = _failed(1000.0, *["   TimeoutException: %d\n" % i for i in range(9)])
    _generate(tmp_path, failures)

    names = re.findall(r'class="fault__test[^"]*"[^>]*>([^<]+)<', ConfigVars._analytics_faults)

    assert len(names) == 9
    # Everything past the first few is in the page but not shown in the card.
    assert ConfigVars._analytics_faults.count("is-extra") == 9 - 4
    assert 'and 5 more' in ConfigVars._analytics_faults


def test_a_truncated_list_opens_rather_than_ending_at_a_count(tmp_path):
    _generate(tmp_path, _failed(1000.0, *["   ValueError: %d\n" % i for i in range(6)]))

    assert 'class="more-link"' in ConfigVars._analytics_faults
    assert 'onclick="showMore(this)"' in ConfigVars._analytics_faults
    # The dialog is titled with the group it was opened from.
    assert 'data-title="ValueError"' in ConfigVars._analytics_faults


def test_a_movement_card_opens_the_same_way(tmp_path):
    """The four cards under the charts truncate the same list the same way."""
    _generate(tmp_path,
              _build(1000.0, [("a", "PASS", 0, 0.1)]),
              _build(1001.0, [("a", "PASS", 0, 0.1)]
                     + [("new_%d" % i, "PASS", 0, 0.1) for i in range(9)]))

    assert 'class="more-link"' in ConfigVars._analytics_movement
    assert 'data-title="New tests"' in ConfigVars._analytics_movement
    assert ConfigVars._analytics_movement.count("is-extra") == 9 - MOVEMENT_NAMES


def test_a_card_short_enough_to_show_everything_offers_nothing_to_open(tmp_path):
    _generate(tmp_path, _failed(1000.0, "   ValueError: a\n", "   ValueError: b\n"))

    assert "more-link" not in ConfigVars._analytics_faults
    assert "is-extra" not in ConfigVars._analytics_faults


def test_the_exception_types_past_the_panel_open_too(tmp_path):
    """The tail of that list is one-offs, and it is counted rather than
    dropped: a run whose failures are all different is itself the finding."""
    _generate(tmp_path, _failed(1000.0, *["   Type%dError: x\n" % i for i in range(11)]))

    rest = ConfigVars._analytics_faults.split('class="fault__rest"')[-1]

    assert 'data-noun="types"' in rest
    assert 'and 3 more types, 3 failures between them' in rest
    # The types themselves ride in the page beside the line, hidden, so the
    # dialog has something to open.
    assert rest.count("fault__rest-item") == 11 - FAULT_TYPES


def test_the_dialog_a_truncated_list_opens_is_on_the_page(tmp_path):
    """One dialog serves every "and N more" on the tab: it copies the card's
    own items across, so it has to search and scroll rather than assume the
    list is short."""
    with open(TEMPLATE, encoding="utf-8") as handle:
        page = handle.read()

    assert 'id="moreOverlay"' in page
    assert 'id="moreOverlaySearch"' in page
    assert "function showMore(trigger)" in page
    assert "function filterMore(text)" in page

    # The card's items, with the hiding taken off - not a second copy of them.
    assert "copy.classList.remove('is-extra');" in page

    # A filtered row is hidden with the attribute, and the list styles the rows
    # with `display`, which would otherwise win over it.
    assert ".more-overlay__body li[hidden] { display: none; }" in page

    body = page.split(".more-overlay__body {", 1)[1].split("}", 1)[0]
    assert "overflow-y: auto;" in body

    escape = page.split("if (e.key !== 'Escape') return;", 1)[1].split("});", 1)[0]
    assert "toggleMore(false);" in escape


def test_a_run_with_nothing_on_disk_is_left_alone(tmp_path):
    """No output.json is not a crash - it is a report that was never written."""
    generate_analytics(str(tmp_path))


# --------------------------------------------------------------------------
# the owner roll-up
# --------------------------------------------------------------------------

def _owned_build(stamp, tests, suite="tests/test_thing.py"):
    """A build whose tests carry owners, as this version writes output.json."""
    build = _build(stamp, [(name, status, 0, duration)
                           for name, status, _owner, duration in tests], suite=suite)

    entries = build["content"]["suites"]["0"]["tests"]
    for position, (_name, _status, owner, _duration) in enumerate(tests):
        entries[str(position)]["owner"] = list(owner)

    return build


def _totals(tmp_path, *builds):
    return owner_totals(histories(read_builds(_history(tmp_path, *builds))))


def test_an_owner_row_counts_the_tests_that_team_holds(tmp_path):
    rows = _totals(tmp_path, _owned_build(1000.0, [
        ("test_a", "PASS", ["payments"], 0.5),
        ("test_b", "FAIL", ["payments"], 0.25),
        ("test_c", "PASS", ["checkout"], 0.1),
    ]))

    by_owner = {row["owner"]: row for row in rows}

    assert by_owner["payments"]["tests"] == 2
    assert by_owner["payments"]["failing"] == 1
    assert by_owner["checkout"]["tests"] == 1
    assert by_owner["checkout"]["failing"] == 0


def test_a_test_with_two_owners_counts_for_both(tmp_path):
    """Picking one would take a team off the hook for a test they signed."""
    rows = _totals(tmp_path, _owned_build(1000.0, [
        ("test_a", "FAIL", ["platform", "payments"], 0.1),
    ]))

    assert sorted(row["owner"] for row in rows) == ["payments", "platform"]
    assert all(row["tests"] == 1 and row["failing"] == 1 for row in rows)


def test_a_test_nobody_claimed_is_a_row_rather_than_a_gap(tmp_path):
    rows = _totals(tmp_path, _owned_build(1000.0, [
        ("test_a", "PASS", ["payments"], 0.1),
        ("test_b", "FAIL", [], 0.1),
    ]))

    unowned = [row for row in rows if row["owner"] == UNOWNED]

    assert len(unowned) == 1
    assert unowned[0]["tests"] == 1
    assert unowned[0]["failing"] == 1


def test_unowned_sorts_last_however_bad_it_is(tmp_path):
    """It is not a team, and reading it among them invites somebody to go and
    find out who Unowned is."""
    rows = _totals(tmp_path, _owned_build(1000.0, [
        ("test_a", "FAIL", [], 0.1),
        ("test_b", "PASS", ["payments"], 0.1),
    ]))

    assert [row["owner"] for row in rows] == ["payments", UNOWNED]


def test_the_worst_team_is_at_the_top(tmp_path):
    rows = _totals(tmp_path, _owned_build(1000.0, [
        ("test_a", "PASS", ["calm"], 0.1),
        ("test_b", "FAIL", ["busy"], 0.1),
    ]))

    assert [row["owner"] for row in rows] == ["busy", "calm"]


def test_ownership_is_read_from_the_most_recent_build_that_named_one(tmp_path):
    """A test that moved teams should page the team that has it today."""
    rows = _totals(tmp_path,
                   _owned_build(1000.0, [("test_a", "PASS", ["old-team"], 0.1)]),
                   _owned_build(2000.0, [("test_a", "FAIL", ["new-team"], 0.1)]))

    assert [row["owner"] for row in rows] == ["new-team"]


def test_a_build_archived_before_ownership_existed_reads_as_unowned(tmp_path):
    """Older archives simply have no key, and inventing one would be worse."""
    rows = _totals(tmp_path, _build(1000.0, [("test_a", "PASS", 0, 0.1)]))

    assert [row["owner"] for row in rows] == [UNOWNED]


def test_a_test_this_run_no_longer_has_is_nobodys_morning(tmp_path):
    """Leaving a deleted test in makes a team's numbers unfixable."""
    rows = _totals(tmp_path,
                   _owned_build(1000.0, [("test_gone", "FAIL", ["payments"], 0.1),
                                         ("test_here", "PASS", ["payments"], 0.1)]),
                   _owned_build(2000.0, [("test_here", "PASS", ["payments"], 0.1)]))

    assert [row["tests"] for row in rows] == [1]
    assert rows[0]["failing"] == 0


def test_the_pass_rate_is_the_mean_of_the_tests_own_rates(tmp_path):
    """One test with two hundred runs must not decide a team's number."""
    rows = _totals(tmp_path,
                   _owned_build(1000.0, [("test_a", "PASS", ["t"], 0.1),
                                         ("test_b", "FAIL", ["t"], 0.1)]),
                   _owned_build(2000.0, [("test_a", "PASS", ["t"], 0.1),
                                         ("test_b", "FAIL", ["t"], 0.1)]))

    # test_a passed both builds (100), test_b failed both (0).
    assert rows[0]["pass_rate"] == 50.0


def test_the_share_bar_is_drawn_against_the_busiest_owner(tmp_path):
    """Against the whole suite every bar would be a stub."""
    rows = _totals(tmp_path, _owned_build(1000.0, [
        ("test_a", "PASS", ["big"], 0.1),
        ("test_b", "PASS", ["big"], 0.1),
        ("test_c", "PASS", ["big"], 0.1),
        ("test_d", "PASS", ["small"], 0.1),
    ]))

    by_owner = {row["owner"]: row for row in rows}

    assert by_owner["big"]["share"] == 100
    assert by_owner["small"]["share"] == 33


def test_the_headline_says_how_much_of_the_suite_is_unclaimed(tmp_path):
    rows = _totals(tmp_path, _owned_build(1000.0, [
        ("test_a", "PASS", ["payments"], 0.1),
        ("test_b", "PASS", [], 0.1),
    ]))

    named = [row for row in rows if row["owner"] != UNOWNED]

    assert _owner_headline(named, rows) == "1 owner, and 1 of 2 tests unclaimed"


def test_the_headline_says_so_when_every_test_is_claimed(tmp_path):
    rows = _totals(tmp_path, _owned_build(1000.0, [
        ("test_a", "PASS", ["payments"], 0.1),
    ]))

    assert _owner_headline(rows, rows) == "1 owner, every test claimed"


def test_a_suite_that_named_no_owner_gets_no_panel(tmp_path):
    """A table of one row called Unowned is a table saying nothing."""
    base = _history(tmp_path, _build(1000.0, [("test_a", "PASS", 0, 0.1)]))
    generate_analytics(base)

    assert ConfigVars._analytics_owner_state == "is-empty"
    assert ConfigVars._analytics_owners == ""
    assert ConfigVars._analytics_owner_note == ""


def test_a_suite_that_named_one_gets_the_panel(tmp_path):
    base = _history(tmp_path, _owned_build(1000.0, [
        ("test_a", "PASS", ["payments"], 0.1),
    ]))
    generate_analytics(base)

    assert ConfigVars._analytics_owner_state == ""
    assert "payments" in ConfigVars._analytics_owners
    assert ConfigVars._analytics_owner_note == "1 owner, every test claimed"


def test_the_panel_the_template_asks_for_is_the_one_that_is_filled():
    """The placeholders and the ConfigVars behind them, kept in step."""
    template = open(TEMPLATE, encoding="utf-8").read()

    for name in ("analytics_owners", "analytics_owner_note", "analytics_owner_state"):
        assert "%%(%s)%%" % name in template
        assert hasattr(ConfigVars, "_" + name)


# --------------------------------------------------------------------------
# the severity roll-up
# --------------------------------------------------------------------------

def _rated_build(stamp, tests, suite="tests/test_thing.py"):
    """A build whose tests carry a severity, as this version writes output.json."""
    build = _build(stamp, [(name, status, 0, duration)
                           for name, status, _severity, duration in tests], suite=suite)

    entries = build["content"]["suites"]["0"]["tests"]
    for position, (_name, _status, severity, _duration) in enumerate(tests):
        entries[str(position)]["severity"] = severity

    return build


def _severities(tmp_path, *builds):
    return severity_totals(histories(read_builds(_history(tmp_path, *builds))))


def test_a_severity_row_counts_the_tests_rated_at_it(tmp_path):
    rows = _severities(tmp_path, _rated_build(1000.0, [
        ("test_a", "PASS", "blocker", 0.5),
        ("test_b", "FAIL", "blocker", 0.25),
        ("test_c", "PASS", "minor", 0.1),
    ]))

    by_level = {row["severity"]: row for row in rows}

    assert by_level["blocker"]["tests"] == 2
    assert by_level["blocker"]["failing"] == 1
    assert by_level["minor"]["tests"] == 1
    assert by_level["minor"]["failing"] == 0


def test_a_test_counts_once_because_it_has_one_severity(tmp_path):
    """Unlike an owner. record_severity has already picked between the markers."""
    rows = _severities(tmp_path, _rated_build(1000.0, [
        ("test_a", "PASS", "critical", 0.1),
    ]))

    assert sum(row["tests"] for row in rows) == 1


def test_the_rows_are_the_ladder_rather_than_the_worst_numbers(tmp_path):
    """A table that put trivial over blocker would argue with the words in it."""
    rows = _severities(tmp_path, _rated_build(1000.0, [
        ("test_a", "FAIL", "trivial", 0.1),
        ("test_b", "FAIL", "trivial", 0.1),
        ("test_c", "PASS", "blocker", 0.1),
        ("test_d", "PASS", "normal", 0.1),
    ]))

    assert [row["severity"] for row in rows] == ["blocker", "normal", "trivial"]


def test_unrated_sorts_last_however_many_tests_are_in_it(tmp_path):
    rows = _severities(tmp_path, _rated_build(1000.0, [
        ("test_a", "PASS", "", 0.1),
        ("test_b", "PASS", "", 0.1),
        ("test_c", "PASS", "", 0.1),
        ("test_d", "PASS", "trivial", 0.1),
    ]))

    assert [row["severity"] for row in rows] == ["trivial", UNRATED]


def test_a_word_nobody_recognises_sorts_after_the_five(tmp_path):
    """A typo is not a sixth level and must not outrank blocker."""
    rows = _severities(tmp_path, _rated_build(1000.0, [
        ("test_a", "PASS", "high", 0.1),
        ("test_b", "PASS", "blocker", 0.1),
    ]))

    assert [row["severity"] for row in rows] == ["blocker", "high"]


def test_a_severity_is_read_from_the_most_recent_build_that_named_one(tmp_path):
    """A test raised to blocker this month is a blocker, not an average."""
    rows = _severities(tmp_path,
                       _rated_build(1000.0, [("test_a", "PASS", "minor", 0.1)]),
                       _rated_build(2000.0, [("test_a", "PASS", "blocker", 0.1)]))

    assert [row["severity"] for row in rows] == ["blocker"]


def test_a_build_archived_before_severity_existed_reads_as_unrated(tmp_path):
    rows = severity_totals(histories(read_builds(_history(
        tmp_path, _build(1000.0, [("test_a", "PASS", 0, 0.1)])))))

    assert [row["severity"] for row in rows] == [UNRATED]


def test_the_headline_leads_with_what_is_red_at_the_worst_level(tmp_path):
    rows = _severities(tmp_path, _rated_build(1000.0, [
        ("test_a", "FAIL", "critical", 0.1),
        ("test_b", "FAIL", "minor", 0.1),
        ("test_c", "PASS", "blocker", 0.1),
    ]))

    assert _severity_headline(rows) == "1 critical test failing"


def test_the_headline_falls_back_to_how_much_is_unrated(tmp_path):
    rows = _severities(tmp_path, _rated_build(1000.0, [
        ("test_a", "PASS", "blocker", 0.1),
        ("test_b", "PASS", "", 0.1),
    ]))

    assert _severity_headline(rows) == "1 level in use, and 1 of 2 tests unrated"


def test_the_headline_says_so_when_every_test_is_rated(tmp_path):
    rows = _severities(tmp_path, _rated_build(1000.0, [
        ("test_a", "PASS", "blocker", 0.1),
    ]))

    assert _severity_headline(rows) == "1 level in use, every test rated"


def test_a_suite_that_rated_nothing_gets_no_severity_panel(tmp_path):
    """A table whose only row is Unrated is a table saying nothing."""
    base = _history(tmp_path, _build(1000.0, [("test_a", "PASS", 0, 0.1)]))
    generate_analytics(base)

    assert ConfigVars._analytics_severity_state == "is-empty"
    assert ConfigVars._analytics_severities == ""
    assert ConfigVars._analytics_severity_note == ""


def test_a_suite_that_rated_one_test_gets_the_panel(tmp_path):
    base = _history(tmp_path, _rated_build(1000.0, [
        ("test_a", "PASS", "blocker", 0.1),
    ]))
    generate_analytics(base)

    assert ConfigVars._analytics_severity_state == ""
    assert "blocker" in ConfigVars._analytics_severities
    assert ConfigVars._analytics_severity_note == "1 level in use, every test rated"


def test_the_severity_panel_the_template_asks_for_is_the_one_that_is_filled():
    template = open(TEMPLATE, encoding="utf-8").read()

    for name in ("analytics_severities", "analytics_severity_note", "analytics_severity_state"):
        assert "%%(%s)%%" % name in template
        assert hasattr(ConfigVars, "_" + name)
