"""Cover the "+3 failures since the last build" line on the Dashboard.

The absolute failure count says how bad this build is; the delta says which
way the suite is moving, which is the thing worth acting on. It is read off
the same per-build list the Trends chart is drawn from - this run first, then
the archived builds newest first - so the two can never disagree.
"""

from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.util import (
    format_run_delta,
    generate_run_delta,
    run_delta,
    run_delta_class,
    run_delta_title,
)


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
    assert run_delta_class(None) == ""


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

    assert ConfigVars._failure_delta == "+3 failures since last build"
    assert ConfigVars._failure_delta_class == "is-worse"
    assert ConfigVars._failure_delta_title == (
        "12 failures this build, 9 in the build before it")


def test_generate_leaves_a_first_build_blank(monkeypatch):
    """The span collapses on empty, so a first build shows no chip at all."""
    monkeypatch.setattr(ConfigVars, "_failure_delta", "stale", raising=False)
    monkeypatch.setattr(ConfigVars, "_failure_delta_class", "is-worse", raising=False)
    monkeypatch.setattr(ConfigVars, "tfail", [12], raising=False)
    generate_run_delta()

    assert ConfigVars._failure_delta == ""
    assert ConfigVars._failure_delta_class == ""
    assert ConfigVars._failure_delta_title == ""
