"""Cover the last branches of the small helpers, module by module.

Nothing here is a feature. These are the fallbacks the rest of the tree leans
on - a value that will not become an int, a name that will not repr, a
timestamp a build was written before the field existed - and each one exists so
that a report is still produced when something is not the shape it should be.
They are worth a test each precisely because none of them is ever reached on a
run that goes well, which is exactly when a regression in one goes unnoticed.
"""

import datetime
import os

import pytest

from pytest_html_reporter.analytics import _label, _to_float, _to_int, exception_type
from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.steps import _steps, _text, step, take_steps
from pytest_html_reporter.time_converter import time_converter
from pytest_html_reporter.util import (
    STEP_LIMIT_DEFAULT,
    archive_timestamp,
    clean_screenshots,
    generate_logs_notice,
    report_step_limit,
    xdist_worker_id,
)


class _FakeConfig:
    """Just enough of pytest's Config for the option/ini resolution helpers."""

    def __init__(self, options=None, ini=None, workerinput=None):
        self._options = options or {}
        self._ini = ini or {}
        if workerinput is not None:
            self.workerinput = workerinput

    def getoption(self, name, default=None):
        return self._options.get(name, default)

    def getini(self, name):
        if name not in self._ini:
            raise ValueError(name)
        return self._ini[name]


# ================================================== time_converter ===========

def test_midnight_is_shown_as_twelve_rather_than_zero():
    """00:xx is 12:xx am on a twelve-hour clock, not 0:xx."""
    assert time_converter("00:30") == "12:30 am"


def test_the_top_of_midnight_hour_keeps_its_two_digit_minutes():
    assert time_converter("00:05") == "12:05 am"


def test_an_ordinary_morning_time_loses_its_leading_zero():
    assert time_converter("09:15") == "9:15 am"


def test_an_afternoon_time_is_shown_on_the_twelve_hour_clock():
    assert time_converter("18:31") == "6:31 pm"


def test_midday_stays_twelve():
    assert time_converter("12:30") == "12:30 pm"


# ================================================== steps ====================

def test_a_value_that_will_not_stringify_does_not_take_the_step_down():
    class Awkward:
        def __str__(self):
            raise RuntimeError("no str for you")

    assert _text(Awkward(), 50) == "<unrepresentable>"


def test_a_long_value_is_cut_to_fit_the_line():
    text = _text("x" * 100, 20)

    assert len(text) == 20
    assert text.endswith("…")


def test_a_string_is_passed_through_without_being_re_stringified():
    assert _text("Add to cart", 50) == "Add to cart"


def test_the_buffer_recovers_if_something_left_a_non_list_behind():
    ConfigVars._steps = "not a list"

    assert _steps() == []
    take_steps()


def test_a_decorated_step_whose_signature_cannot_be_bound_still_records():
    """The argument names are a nicety; the step itself is not."""
    @step("Log in")
    def log_in(*args, **kwargs):
        return "ok"

    assert log_in(1, 2, x=3) == "ok"

    recorded, = take_steps()
    assert recorded["title"] == "Log in"
    assert recorded["status"] == "PASS"


# ================================================== analytics ================

def test_a_dotted_exception_is_cut_to_its_class():
    """'selenium...TimeoutException' and 'TimeoutException' are one group."""
    assert exception_type("selenium.common.exceptions.TimeoutException: gone") \
        == "TimeoutException"


def test_a_bare_assert_is_classified_rather_than_left_unsorted():
    """Far too common a failure to leave sitting in the unclassified pile."""
    assert exception_type("E   assert 1 == 2") == "AssertionError"


def test_a_real_exception_beats_an_assert_seen_first():
    assert exception_type("assert 1 == 2\nValueError: bad input") == "ValueError"


def test_a_name_that_does_not_look_like_an_exception_is_still_offered():
    assert exception_type("Timeout: gone") == "Timeout"


def test_an_exception_wins_over_a_plain_name_whatever_the_order():
    assert exception_type("Timeout: gone\nValueError: bad") == "ValueError"


def test_colour_codes_do_not_hide_the_exception():
    assert exception_type("\x1b[31mValueError\x1b[0m: bad input") == "ValueError"


def test_a_message_that_names_nothing_is_left_unclassified():
    assert exception_type("") == ""
    assert exception_type(None) == ""
    assert exception_type("something went wrong") == ""


@pytest.mark.parametrize("value,expected", [
    ("12", 12), (12.7, 12), ("12.7", 12), (0, 0),
])
def test_a_number_that_can_be_read_as_an_int_is(value, expected):
    assert _to_int(value) == expected


@pytest.mark.parametrize("value", [None, "", "later", [], {}])
def test_a_value_that_is_not_a_number_falls_back(value):
    assert _to_int(value) == 0
    assert _to_int(value, fallback=-1) == -1


@pytest.mark.parametrize("value,expected", [("1.5", 1.5), (2, 2.0)])
def test_a_number_that_can_be_read_as_a_float_is(value, expected):
    assert _to_float(value) == expected


@pytest.mark.parametrize("value", [None, "", "later", []])
def test_a_float_that_cannot_be_read_is_none(value):
    assert _to_float(value) is None


def test_a_build_is_labelled_by_the_clock_it_started_on():
    stamp = datetime.datetime(2024, 9, 1, 14, 18).timestamp()

    assert _label(stamp, "") == "Sep 01 14:18"


def test_a_build_written_before_start_time_existed_still_has_its_date():
    assert _label(None, "01-Sep-2024") == "01-Sep-2024"


def test_a_build_with_neither_is_left_unlabelled():
    assert _label(None, None) == ""


# ================================================== util =====================

def test_the_step_limit_defaults_when_nobody_set_one():
    assert report_step_limit(_FakeConfig()) == STEP_LIMIT_DEFAULT


def test_the_step_limit_defaults_when_what_was_set_is_not_a_number():
    """A typo in an ini file must not stop the run."""
    assert report_step_limit(_FakeConfig(ini={"report_step_limit": "lots"})) \
        == STEP_LIMIT_DEFAULT


def test_a_negative_step_limit_is_read_as_no_limit():
    assert report_step_limit(_FakeConfig(options={"report_step_limit": -5})) == 0


def test_the_flag_wins_over_the_ini_key():
    config = _FakeConfig(options={"report_step_limit": 10},
                         ini={"report_step_limit": 99})

    assert report_step_limit(config) == 10


def test_the_ini_key_is_used_when_the_flag_was_not_given():
    assert report_step_limit(_FakeConfig(ini={"report_step_limit": "25"})) == 25


def test_a_serial_run_has_no_worker_id():
    assert xdist_worker_id(_FakeConfig()) == ""


def test_an_xdist_worker_says_which_one_it_is():
    assert xdist_worker_id(_FakeConfig(workerinput={"workerid": "gw2"})) == "gw2"


def test_the_screenshot_folder_is_removed_when_it_is_there(tmp_path):
    shots = tmp_path / "pytest_screenshots"
    shots.mkdir()
    (shots / "a.png").write_bytes(b"x")

    clean_screenshots(str(tmp_path))

    assert not shots.exists()


def test_cleaning_a_folder_that_was_never_written_is_not_an_error(tmp_path):
    clean_screenshots(str(tmp_path))

    assert not (tmp_path / "pytest_screenshots").exists()


def test_the_notice_is_raised_when_output_is_not_being_captured():
    """-s means stdout never reaches the column, and a blank column with no
    explanation reads as a test that printed nothing."""
    config = _FakeConfig(options={"report_logs": "all", "capture": "no"})

    generate_logs_notice(config)

    assert "not captured" in ConfigVars._logs_notice
    ConfigVars._logs_notice = ""


def test_no_notice_is_raised_on_an_ordinary_run():
    config = _FakeConfig(options={"report_logs": "all", "capture": "fd"})

    generate_logs_notice(config)

    assert ConfigVars._logs_notice == ""


def test_an_archives_time_is_read_from_its_name(tmp_path):
    """The mtime is the moment of the CI clone, so an age limit read from
    mtimes would keep every build for ever."""
    archive = tmp_path / "report_1725200000.0.json"
    archive.write_text("{}")

    assert archive_timestamp(str(archive)) == 1725200000.0


def test_an_archive_named_by_an_older_version_falls_back_to_its_mtime(tmp_path):
    archive = tmp_path / "report.json"
    archive.write_text("{}")

    assert archive_timestamp(str(archive)) == os.path.getmtime(str(archive))


def test_a_name_whose_stamp_is_not_a_bare_number_falls_back_to_the_mtime(tmp_path):
    archive = tmp_path / "report_v2.json"
    archive.write_text("{}")

    assert archive_timestamp(str(archive)) == os.path.getmtime(str(archive))
