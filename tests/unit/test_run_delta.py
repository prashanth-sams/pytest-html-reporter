"""Cover the "+3 failures since the last build" line on the Dashboard.

The absolute failure count says how bad this build is; the delta says which
way the suite is moving, which is the thing worth acting on. It is read off
the same per-build list the Trends chart is drawn from - this run first, then
the archived builds newest first - so the two can never disagree.
"""

import json
import os

import pytest

from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.html_reporter import HTMLReporter
from pytest_html_reporter.util import (
    format_run_delta,
    generate_run_delta,
    run_delta,
    run_delta_class,
    run_delta_figure,
    run_delta_title,
    run_delta_unit,
)


class _FakePluginManager:
    def hasplugin(self, name):
        return False


class _FakeConfig:
    """Just enough of pytest's Config to build a reporter."""

    def __init__(self):
        self.pluginmanager = _FakePluginManager()

    def getoption(self, name, default=None):
        return default

    def getini(self, name):
        raise ValueError(name)


_TRENDS = ("trends_label", "tpass", "tfail", "tskip", "tcoverage")


@pytest.fixture(autouse=True)
def _isolate_trend_lists():
    """The trend lists are class-level state, and these tests fill them in."""
    saved = {name: getattr(ConfigVars, name) for name in _TRENDS}
    yield
    for name, value in saved.items():
        setattr(ConfigVars, name, value)


def _build(directory, start, passed, failed):
    """One build's output.json, in the shape update_trends reads it."""
    os.makedirs(str(directory), exist_ok=True)
    with open(os.path.join(str(directory), "output.json"), "w") as handle:
        json.dump({
            "date": "September 04, 2026",
            "start_time": start,
            "total_tests": passed + failed,
            "status_list": {
                "pass": str(passed), "fail": str(failed), "skip": "0",
                "error": "0", "xpass": "0", "xfail": "0", "rerun": "0",
            },
        }, handle)

    return str(directory)


# --------------------------------------------------------------------------
# the arithmetic
# --------------------------------------------------------------------------

def test_delta_against_the_previous_build():
    assert run_delta([12, 9, 4]) == 3
    assert run_delta([4, 9]) == -5
    assert run_delta([9, 9]) == 0


def test_delta_reads_the_counts_archived_builds_store_as_strings():
    """status_list holds its counts as strings; tfail mixes both."""
    assert run_delta([12, "9"]) == 3


def test_delta_is_none_on_a_first_build():
    """Nothing to compare against is not the same as no change."""
    assert run_delta([12]) is None
    assert run_delta([]) is None


def test_delta_is_none_when_a_build_did_not_record_the_count():
    assert run_delta([12, None]) is None
    assert run_delta([12, ""]) is None


# --------------------------------------------------------------------------
# how it reads
# --------------------------------------------------------------------------

def test_wording_carries_the_sign():
    assert format_run_delta(3) == "+3 failures since last build"
    assert format_run_delta(-5) == "-5 failures since last build"


def test_wording_is_singular_for_one():
    assert format_run_delta(1) == "+1 failure since last build"
    assert format_run_delta(-1) == "-1 failure since last build"


def test_wording_says_no_change_rather_than_plus_zero():
    """And drops the suffix: "no change" already implies the comparison,
    and the extra words wrap the line onto a second row in this column."""
    assert format_run_delta(0) == "no change in failures"


def test_no_wording_without_a_delta():
    assert format_run_delta(None) == ""


def test_more_failures_than_last_time_is_the_bad_direction():
    """The opposite way round to coverage, where up is the good direction."""
    assert run_delta_class(3) == "is-worse"
    assert run_delta_class(-3) == "is-better"
    assert run_delta_class(0) == "is-level"


def test_no_delta_hides_the_whole_tile():
    """Caption included - a lone "SINCE LAST BUILD" over nothing reads as a bug."""
    assert run_delta_class(None) == "is-empty"


def test_figure_carries_its_sign():
    assert run_delta_figure(3) == "+3"
    assert run_delta_figure(-1) == "-1"


def test_figure_signs_no_change_too():
    """A bare "0 failures" beside "SINCE LAST BUILD" says the opposite of what
    it means - no failures at all, rather than no change in them."""
    assert run_delta_figure(0) == "\u00b10"


def test_unit_agrees_with_the_figure():
    assert run_delta_unit(3) == "failures"
    assert run_delta_unit(1) == "failure"
    assert run_delta_unit(-1) == "failure"
    assert run_delta_unit(0) == "failures"


def test_no_figure_or_unit_without_a_delta():
    assert run_delta_figure(None) == ""
    assert run_delta_unit(None) == ""


def test_tooltip_gives_the_two_counts_behind_the_delta():
    """'+3' reads differently against 3 than against 300."""
    assert run_delta_title([12, 9]) == "12 failures this build, 9 in the build before it"
    assert run_delta_title([1, 3]) == "1 failure this build, 3 in the build before it"
    assert run_delta_title([12]) == ""


# --------------------------------------------------------------------------
# what the page is handed
# --------------------------------------------------------------------------

def test_generate_fills_in_the_placeholders(monkeypatch):
    monkeypatch.setattr(ConfigVars, "tfail", [12, 9, 4], raising=False)
    generate_run_delta()

    assert ConfigVars._failure_delta_class == "is-worse"
    assert ConfigVars._failure_delta_figure == "+3"
    assert ConfigVars._failure_delta_unit == "failures"
    assert ConfigVars._failure_delta == "+3 failures since last build"
    assert ConfigVars._failure_delta_title == (
        "12 failures this build, 9 in the build before it")


def test_generate_leaves_a_first_build_blank(monkeypatch):
    """is-empty hides the tile, and nothing is left over from a previous run."""
    monkeypatch.setattr(ConfigVars, "_failure_delta", "stale", raising=False)
    monkeypatch.setattr(ConfigVars, "_failure_delta_figure", "+9", raising=False)
    monkeypatch.setattr(ConfigVars, "tfail", [12], raising=False)
    generate_run_delta()

    assert ConfigVars._failure_delta_class == "is-empty"
    assert ConfigVars._failure_delta_figure == ""
    assert ConfigVars._failure_delta_unit == ""
    assert ConfigVars._failure_delta == ""
    assert ConfigVars._failure_delta_title == ""


# --------------------------------------------------------------------------
# one render, one trend
# --------------------------------------------------------------------------

def test_a_second_render_in_one_process_starts_the_trend_over(tmp_path):
    """The build at index 0 is this build, whatever rendered before it.

    The lists live on ConfigVars and update_trends appends to them, so a merge
    driven in-process - or anything else that renders twice - used to leave its
    own build sitting where this one's belongs. It was drawn as the newest
    point on the Trends chart, and the delta beside it was measured against it.
    """
    first = _build(tmp_path / "first", 1788411600.0, passed=4, failed=1)
    second = _build(tmp_path / "second", 1788520444.0, passed=17, failed=0)

    reporter = HTMLReporter(first, "", _FakeConfig())
    reporter.update_trends(first)
    reporter.update_trends(second)

    assert ConfigVars.tpass == ["17"]
    assert ConfigVars.tfail == [0]
    assert ConfigVars.tskip == ["0"]
    assert ConfigVars.tcoverage == [None]
    assert len(ConfigVars.trends_label) == 1


def test_a_first_build_is_still_a_first_build_after_an_earlier_render(tmp_path):
    """The bug as it was seen: "+1 failure since last build" over a green run.

    The 1 was the earlier render's failure, and the build it was subtracted
    from was this one. A build with no archive behind it has nothing to compare
    against and the tile stays hidden.
    """
    first = _build(tmp_path / "first", 1788411600.0, passed=4, failed=1)
    second = _build(tmp_path / "second", 1788520444.0, passed=17, failed=0)

    reporter = HTMLReporter(first, "", _FakeConfig())
    reporter.update_trends(first)
    reporter.update_trends(second)
    generate_run_delta()

    assert ConfigVars._failure_delta_class == "is-empty"
    assert ConfigVars._failure_delta_figure == ""
    assert ConfigVars._failure_delta == ""
