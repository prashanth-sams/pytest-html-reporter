"""Cover the reading helpers in attachments.py and junit.py.

Both modules read objects somebody else built - an http client's response, a
record that came out of a shard bundle - and both are written so that reading
one badly costs a decoration rather than the file. The tests that drive real
suites never produce the bad shapes, so the guards are only reachable by
handing them over directly.

The junit half matters twice over: the xml is what a CI collector parses, and a
document that fails to write is a build with no test results at all.
"""

import pytest

from pytest_html_reporter.attachments import (
    _duration_text,
    _elapsed_seconds,
    _milliseconds,
    attachment_size,
    header_pairs,
    redact_headers,
)
from pytest_html_reporter.junit import (
    JunitOptions,
    _bin_xml_escape,
    _first_line,
    testcase_time as _testcase_time,
    _options,
)


class _Elapsed:
    """requests keeps a timedelta; httpx keeps a float."""

    def __init__(self, seconds):
        self._seconds = seconds

    def total_seconds(self):
        return self._seconds


class _Response:
    def __init__(self, elapsed=None):
        if elapsed is not None:
            self.elapsed = elapsed


# ------------------------------------------------------------ header_pairs ---

def test_a_plain_dict_of_headers_is_read():
    assert header_pairs({"Accept": "application/json"}) == \
        [("Accept", "application/json")]


def test_a_list_of_pairs_is_read_too():
    """Not every client hands over something with items()."""
    assert header_pairs([("Accept", "application/json")]) == \
        [("Accept", "application/json")]


def test_no_headers_at_all_is_not_an_error():
    assert header_pairs(None) == []


def test_an_items_call_that_raises_costs_the_headers_and_nothing_else():
    class Hostile:
        def items(self):
            raise RuntimeError("connection already released")

    assert header_pairs(Hostile()) == []


def test_something_that_is_not_headers_at_all_is_read_as_none():
    assert header_pairs(42) == []
    assert header_pairs("Accept: application/json") == []


# ---------------------------------------------------------- redact_headers ---

def test_a_secret_is_hidden_by_default():
    pairs = redact_headers([("Authorization", "Bearer abc123")])

    assert "abc123" not in str(pairs)


def test_redaction_can_be_switched_off():
    pairs = redact_headers([("Authorization", "Bearer abc123")], redact=False)

    assert "abc123" in str(pairs)


def test_an_ordinary_header_is_left_alone():
    assert redact_headers([("Accept", "application/json")]) == \
        [("Accept", "application/json")]


# --------------------------------------------------------- _elapsed_seconds ---

def test_a_timedelta_style_elapsed_is_read_through_total_seconds():
    assert _elapsed_seconds(_Response(_Elapsed(1.5))) == 1.5


def test_a_plain_number_elapsed_is_read_as_it_is():
    assert _elapsed_seconds(_Response(0.25)) == 0.25


def test_a_client_that_kept_no_timing_reports_none():
    assert _elapsed_seconds(_Response()) is None


def test_an_elapsed_that_is_neither_is_not_guessed_at():
    assert _elapsed_seconds(_Response("about a second")) is None


# --------------------------------------------------- the duration formats ---

def test_milliseconds_are_rounded_to_a_whole_number():
    assert _milliseconds(1.5) == "1500"
    assert _milliseconds(0.0004) == "0"


def test_a_duration_that_is_not_a_number_has_no_milliseconds():
    assert _milliseconds(None) == ""
    assert _milliseconds("soon") == ""


def test_a_call_under_a_second_is_shown_in_milliseconds():
    assert _duration_text(0.25) == "250 ms"


def test_a_call_of_a_second_or_more_is_shown_in_seconds():
    assert _duration_text(1.5) == "1.50 s"
    assert _duration_text(1) == "1.00 s"


def test_a_call_with_no_timing_says_nothing():
    assert _duration_text(None) == ""
    assert _duration_text("soon") == ""


# -------------------------------------------------------- attachment_size ---

def test_the_size_is_the_characters_of_every_part():
    attachment = {"parts": [{"text": "12345"}, {"text": "678"}]}

    assert attachment_size(attachment) == 8


def test_an_attachment_with_no_parts_holds_nothing():
    assert attachment_size({"parts": []}) == 0


# ========================================================== junit ===========

# ------------------------------------------------------------- _options ---

def test_keywords_build_the_options_when_none_were_given():
    """Callers that never need the warnings back just pass keywords."""
    assert _options({"suite_name": "payments"}).suite_name == "payments"


def test_options_given_whole_are_used_as_they_are():
    given = JunitOptions(suite_name="payments")

    assert _options({"options": given}) is given


def test_options_and_keywords_together_are_refused_rather_than_merged():
    """A merge leg's options already carry the matrix's clock and its shards;
    silently letting a keyword overwrite one drops the shards on the floor."""
    with pytest.raises(TypeError) as error:
        _options({"options": JunitOptions(), "suite_name": "payments"})

    assert "suite_name" in str(error.value)


# ------------------------------------------------------- testcase_time ---

def test_a_records_time_is_the_sum_of_its_phases():
    """The phases are whole milliseconds from pytest's own report."""
    record = {"phases": {"setup": 100, "call": 400, "teardown": 100}}

    assert _testcase_time(record) == 0.6


def test_a_record_whose_phases_are_unreadable_falls_back_to_its_duration():
    record = {"phases": {"call": "a while"}, "duration": 1.5}

    assert _testcase_time(record) == 1.5


def test_a_record_with_no_phases_uses_its_own_duration():
    assert _testcase_time({"duration": 2.0}) == 2.0


def test_a_record_with_nothing_readable_took_no_time():
    assert _testcase_time({"duration": "a while"}) == 0.0
    assert _testcase_time({}) == 0.0


# --------------------------------------------------------- _first_line ---

def test_the_first_line_with_anything_in_it_is_the_message():
    assert _first_line("\n\n  AssertionError: nope  \nmore") == "AssertionError: nope"


def test_a_message_that_is_all_blank_lines_says_nothing():
    assert _first_line("\n\n   \n") == ""
    assert _first_line("") == ""


# ----------------------------------------------------- _bin_xml_escape ---

def test_a_control_character_is_escaped_rather_than_written_raw():
    """A raw one makes the document unparseable, and a CI collector that
    cannot parse the xml reports the build as having run no tests at all."""
    escaped = _bin_xml_escape("before\x00after")

    assert "\x00" not in escaped
    assert "#x00" in escaped


def test_a_higher_illegal_codepoint_is_escaped_in_four_digits():
    escaped = _bin_xml_escape("before￾after")

    assert "￾" not in escaped
    assert "#xFFFE" in escaped


def test_ordinary_text_passes_through_untouched():
    assert _bin_xml_escape("AssertionError: nope") == "AssertionError: nope"


def test_the_whitespace_xml_does_allow_is_kept():
    assert _bin_xml_escape("a\tb\nc\rd") == "a\tb\nc\rd"


def test_something_that_is_not_text_is_stringified_first():
    assert _bin_xml_escape(42) == "42"
