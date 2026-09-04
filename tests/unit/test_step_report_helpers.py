"""Cover the arithmetic behind the Test Steps tab.

test_step_report.py drives real suites and reads the rendered page, which is
the right way to prove a step reaches the tab at all. These are the helpers
underneath it: how a duration is chosen, how wide a bar is drawn, which step a
failure is blamed on, and where a screenshot taken outside every step is filed.

Each is a small decision with a rule behind it - a bar measured against this
test's slowest step rather than the run's, a failure blamed on the innermost
step rather than the last - and a rule is only pinned by the case that would
break if it changed.
"""

import pytest

from pytest_html_reporter.step_report import (
    _attach_chip,
    _kind_badge,
    _params_text,
    _pluralise,
    _scenario,
    _short,
    _shots_by_step,
    _test_ms,
    _threw,
    _widths,
    duration,
)


def _step(**overrides):
    step = {"title": "a step", "kind": "step", "phase": "call", "depth": 0,
            "status": "PASS", "ms": 0, "params": [], "error": "", "id": 0}
    step.update(overrides)
    return step


# ---------------------------------------------------------------- duration ---

def test_a_sub_millisecond_step_is_not_shown_as_nothing():
    """0 reads as a step that never ran; '0 ms' reads as one that was fast."""
    assert duration(0) == "0 ms"
    assert duration(0.4) == "0 ms"


def test_milliseconds_stay_milliseconds_while_they_are_short():
    assert duration(1) == "1 ms"
    assert duration(999) == "999 ms"


def test_a_second_or_more_is_said_in_seconds():
    """Three or four digits, so the column stays readable."""
    assert duration(1000) == "1.00 s"
    assert duration(1500) == "1.50 s"
    assert duration(65000) == "65.00 s"


def test_a_duration_that_is_not_a_number_says_nothing():
    assert duration(None) == ""
    assert duration("soon") == ""


def test_a_numeric_string_is_still_a_duration():
    assert duration("1500") == "1.50 s"


# ----------------------------------------------------------------- _test_ms ---

def test_a_test_faster_than_the_time_column_can_show_is_not_flat_zero():
    """duration is rounded to two places for a column headed 'Time (s)', so
    every test under 5ms reaches this tab as 0. The phases are whole ms."""
    record = {"duration": 0.0, "phases": {"setup": 1, "call": 3, "teardown": 1}}

    assert _test_ms(record) == 5


def test_the_record_duration_wins_when_it_is_the_larger_of_the_two():
    record = {"duration": 2.0, "phases": {"call": 100}}

    assert _test_ms(record) == 2000


def test_a_record_with_neither_takes_no_time():
    assert _test_ms({}) == 0


# ------------------------------------------------------------------- _short ---

def test_a_suite_is_named_by_its_file():
    """The directories repeat down the whole rail and crowd out what differs."""
    assert _short("tests/unit/test_cart.py") == "test_cart.py"


def test_a_windows_path_is_split_the_same_way():
    assert _short("tests\\unit\\test_cart.py") == "test_cart.py"


def test_a_bare_name_is_left_alone():
    assert _short("test_cart.py") == "test_cart.py"


def test_a_path_that_ends_in_a_separator_falls_back_to_the_whole_thing():
    assert _short("tests/unit/") == "tests/unit/"


# --------------------------------------------------------------- _pluralise ---

def test_one_of_something_is_singular():
    assert _pluralise(1, "attachment") == "1 attachment"


def test_anything_else_is_plural():
    assert _pluralise(0, "attachment") == "0 attachments"
    assert _pluralise(2, "attachment") == "2 attachments"


# ------------------------------------------------------------------ _widths ---

def test_the_bars_are_measured_against_this_tests_slowest_step():
    """Scaled to the run's slowest, every test but one draws a flat line."""
    steps = [_step(ms=100), _step(ms=50), _step(ms=25)]

    assert _widths(steps) == [100, 50, 25]


def test_a_test_where_nothing_took_any_time_draws_no_bars():
    steps = [_step(ms=0), _step(ms=0)]

    assert _widths(steps) == [0, 0]


def test_a_test_with_no_steps_draws_nothing():
    assert _widths([]) == []


def test_a_step_with_no_time_recorded_counts_as_none():
    steps = [_step(ms=None), _step(ms=200)]

    assert _widths(steps) == [0, 100]


# -------------------------------------------------------------- _kind_badge ---

@pytest.mark.parametrize("kind", ["given", "when", "then", "and", "but"])
def test_a_gherkin_step_carries_its_word_as_a_badge(kind):
    badge = _kind_badge(_step(kind=kind))

    assert kind.title() in badge


def test_a_plain_step_carries_no_gherkin_badge():
    """Every ordinary pytest step would otherwise wear one that says nothing."""
    assert _kind_badge(_step(kind="step")) == ""


def test_a_step_with_no_kind_at_all_carries_no_badge():
    assert _kind_badge({}) == ""


# ------------------------------------------------------------- _params_text ---

def test_the_parameters_read_as_the_call_that_was_made():
    assert _params_text([["count", "2"], ["name", "amy"]]) == "count=2, name=amy"


def test_a_step_called_with_nothing_says_nothing():
    assert _params_text([]) == ""
    assert _params_text(None) == ""


# ------------------------------------------------------------- _attach_chip ---

def test_the_chip_counts_only_what_was_attached_inside_this_step():
    attachments = [{"step": 0}, {"step": 0}, {"step": 1}]

    chip = _attach_chip(_step(id=0), attachments)
    assert ">2<" in chip
    assert "2 attachments" in chip


def test_one_attachment_is_counted_in_the_singular():
    assert "1 attachment attached here" in _attach_chip(_step(id=0), [{"step": 0}])


def test_a_step_nothing_was_attached_in_carries_no_chip():
    assert _attach_chip(_step(id=1), [{"step": 0}]) == ""
    assert _attach_chip(_step(id=0), []) == ""


# ------------------------------------------------------------------ _threw ---

def test_the_step_carrying_the_message_is_the_one_that_threw():
    """The exception walks out through every step it was inside, and each is
    marked failed - but only the innermost one is given the text."""
    steps = [_step(status="FAIL", error=""), _step(status="FAIL", error="boom")]

    assert _threw(steps) == 1


def test_failing_deeper_beats_failing_later():
    steps = [_step(status="FAIL", error="boom"), _step(status="FAIL", error="")]

    assert _threw(steps) == 0


def test_a_test_that_managed_to_fail_twice_is_blamed_on_the_last():
    steps = [_step(status="FAIL", error="first"), _step(status="FAIL", error="second")]

    assert _threw(steps) == 1


def test_a_failure_with_no_message_anywhere_falls_back_to_the_status():
    steps = [_step(status="PASS"), _step(status="FAIL", error="")]

    assert _threw(steps) == 1


def test_an_errored_step_counts_as_having_thrown():
    assert _threw([_step(status="ERROR", error="")]) == 0


def test_a_test_where_nothing_failed_blames_no_step():
    assert _threw([_step(status="PASS"), _step(status="PASS")]) is None
    assert _threw([]) is None


# ----------------------------------------------------------- _shots_by_step ---

def test_a_picture_taken_inside_a_step_is_filed_under_it():
    record = {"status": "PASS", "steps": [_step(id=0), _step(id=1)],
              "screenshots": [{"name": "a", "step": 1}]}

    assert list(_shots_by_step(record)) == [1]


def test_an_automatic_capture_is_filed_against_the_step_that_threw():
    """It runs from teardown with nothing open, and a photograph of the browser
    at the end of a failing test is a photograph of what that step left."""
    record = {
        "status": "FAIL",
        "steps": [_step(id=0, status="PASS"), _step(id=1, status="FAIL", error="boom")],
        "screenshots": [{"name": "a", "step": -1}],
    }

    assert list(_shots_by_step(record)) == [1]


def test_a_picture_from_a_test_that_passed_is_filed_under_the_phase():
    """None is the phase - there is no failing step to hang it on."""
    record = {"status": "PASS", "steps": [_step(id=0)],
              "screenshots": [{"name": "a", "step": -1}]}

    assert list(_shots_by_step(record)) == [None]


def test_a_failure_that_named_no_step_files_its_picture_under_the_phase():
    record = {"status": "FAIL", "steps": [_step(id=0, status="PASS")],
              "screenshots": [{"name": "a", "step": -1}]}

    assert list(_shots_by_step(record)) == [None]


def test_a_step_index_pointing_past_the_end_is_not_trusted():
    record = {"status": "PASS", "steps": [_step(id=0)],
              "screenshots": [{"name": "a", "step": 9}]}

    assert list(_shots_by_step(record)) == [None]


def test_a_step_index_that_is_not_a_number_is_not_trusted():
    record = {"status": "PASS", "steps": [_step(id=0)],
              "screenshots": [{"name": "a", "step": "second"}]}

    assert list(_shots_by_step(record)) == [None]


def test_a_test_with_no_pictures_files_nothing():
    assert _shots_by_step({"status": "PASS", "steps": [], "screenshots": []}) == {}


# --------------------------------------------------------------- _scenario ---

def test_a_gherkin_test_names_the_feature_it_came_from():
    record = {"bdd": {"feature": "Shopping cart", "scenario": "Add 2 items",
                      "file": "features/cart.feature"}}

    rendered = _scenario(record)
    assert "Shopping cart" in rendered
    assert "Add 2 items" in rendered


def test_a_plain_pytest_test_names_no_scenario():
    """This is what the tab keys off to show a scenario as a scenario."""
    assert _scenario({"bdd": None}) == ""
    assert _scenario({}) == ""
