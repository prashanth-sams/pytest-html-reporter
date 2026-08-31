from datetime import datetime

from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.util import (
    build_info,
    capture_notice,
    capture_summary,
    count_log_lines,
    custom_title,
    environment_label,
    environment_name,
    escape_report_text,
    format_log_sections,
    merge_log_sections,
    report_attachment_limit,
    report_attachments_mode,
    report_log_limit,
    report_logs_mode,
    report_path,
    trim_log_sections,
)


class _FakeConfig:
    """Just enough of pytest's Config for the option/ini resolution helpers."""

    def __init__(self, options=None, ini=None):
        self._options = options or {}
        self._ini = ini or {}

    def getoption(self, name, default=None):
        return self._options.get(name, default)

    def getini(self, name):
        if name not in self._ini:
            raise ValueError(name)
        return self._ini[name]


def test_environment_name_from_ini():
    assert environment_name(_FakeConfig(ini={"environment": "staging"})) == "staging"


def test_environment_name_cli_beats_ini():
    config = _FakeConfig(options={"environment": "prod"}, ini={"environment": "staging"})
    assert environment_name(config) == "prod"


def test_environment_name_defaults_to_empty():
    assert environment_name(_FakeConfig()) == ""


def test_build_info_merges_cli_and_ini():
    config = _FakeConfig(
        options={"build_info": ["release=2.4.0"]},
        ini={"build_info": ["branch=main", "team=payments"]},
    )
    assert build_info(config) == [
        ("release", "2.4.0"),
        ("branch", "main"),
        ("team", "payments"),
    ]


def test_build_info_skips_blanks_and_keeps_bare_keys():
    config = _FakeConfig(ini={"build_info": ["  ", "branch = main", "note"]})
    assert build_info(config) == [("branch", "main"), ("note", "")]


def test_build_info_keeps_equals_in_the_value():
    config = _FakeConfig(ini={"build_info": ["job=https://ci/run?id=7"]})
    assert build_info(config) == [("job", "https://ci/run?id=7")]


def test_environment_label_keeps_short_names():
    assert environment_label("staging") == ("staging", False)


def test_environment_label_keeps_names_of_exactly_ten():
    assert environment_label("production") == ("production", False)


def test_environment_label_cuts_longer_names_at_ten():
    # No ellipsis: the was_cut flag drives the fade in the UI instead.
    assert environment_label("pre-production") == ("pre-produc", True)


def test_custom_title_keeps_names_up_to_twenty():
    custom_title("FULL REGRESSION RUN")
    assert ConfigVars._title == "FULL REGRESSION RUN"
    assert ConfigVars._title_class == ""


def test_custom_title_cuts_longer_names_at_twenty():
    custom_title("NIGHTLY REGRESSION SUITE")
    assert ConfigVars._title == "NIGHTLY REGRESSION S"
    assert len(ConfigVars._title) == 20
    assert ConfigVars._title_full == "NIGHTLY REGRESSION SUITE"
    assert ConfigVars._title_class == "is-truncated"


# --------------------------------------------------------------------------
# captured output
# --------------------------------------------------------------------------

def test_report_logs_mode_defaults_to_all():
    assert report_logs_mode(_FakeConfig()) == "all"


def test_report_logs_mode_from_ini():
    assert report_logs_mode(_FakeConfig(ini={"report_logs": "failed"})) == "failed"


def test_report_logs_mode_cli_beats_ini():
    config = _FakeConfig(options={"report_logs": "none"}, ini={"report_logs": "failed"})
    assert report_logs_mode(config) == "none"


def test_report_logs_mode_falls_back_on_nonsense():
    assert report_logs_mode(_FakeConfig(ini={"report_logs": "sometimes"})) == "all"


def test_report_log_limit_defaults():
    assert report_log_limit(_FakeConfig()) == 10000


def test_report_log_limit_zero_means_no_limit():
    assert report_log_limit(_FakeConfig(options={"report_log_limit": 0})) == 0


def test_report_log_limit_from_ini():
    assert report_log_limit(_FakeConfig(ini={"report_log_limit": "500"})) == 500


def test_report_log_limit_ignores_a_negative_value():
    assert report_log_limit(_FakeConfig(options={"report_log_limit": -20})) == 0


def test_report_attachments_mode_defaults_to_all():
    assert report_attachments_mode(_FakeConfig()) == "all"


def test_report_attachments_mode_from_ini():
    assert report_attachments_mode(_FakeConfig(ini={"report_attachments": "failed"})) == "failed"


def test_report_attachments_mode_cli_beats_ini():
    config = _FakeConfig(options={"report_attachments": "none"}, ini={"report_attachments": "all"})
    assert report_attachments_mode(config) == "none"


def test_report_attachments_mode_falls_back_on_nonsense():
    assert report_attachments_mode(_FakeConfig(options={"report_attachments": "maybe"})) == "all"


def test_report_attachment_limit_defaults():
    assert report_attachment_limit(_FakeConfig()) == 20000


def test_report_attachment_limit_zero_means_no_limit():
    assert report_attachment_limit(_FakeConfig(options={"report_attachment_limit": 0})) == 0


def test_report_attachment_limit_from_ini():
    assert report_attachment_limit(_FakeConfig(ini={"report_attachment_limit": "500"})) == 500


def test_report_attachment_limit_ignores_a_negative_value():
    assert report_attachment_limit(_FakeConfig(options={"report_attachment_limit": -5})) == 0


def test_merge_log_sections_skips_empty_captures():
    buffer = {}
    merge_log_sections(buffer, [("Captured log call", "hello"), ("Captured stdout call", "")])

    assert buffer == {"Captured log call": "hello"}


def test_merge_log_sections_keeps_the_latest_attempt():
    """report.sections is cumulative, so a retried test hands back the earlier
    attempt's output alongside the current one."""
    buffer = {}
    merge_log_sections(buffer, [("Captured log call", "attempt 1")])
    merge_log_sections(buffer, [("Captured log call", "attempt 1"), ("Captured log call", "attempt 2")])

    assert buffer == {"Captured log call": "attempt 2"}


def test_format_log_sections_replays_the_phases_in_order():
    buffer = {
        "Captured stderr call": "e",
        "Captured stdout teardown": "t",
        "Captured log call": "l",
        "Captured stdout setup": "s",
    }

    assert [section["title"] for section in format_log_sections(buffer, 0)] == [
        "Captured stdout setup",
        "Captured log call",
        "Captured stderr call",
        "Captured stdout teardown",
    ]


def test_trim_log_sections_leaves_output_under_the_limit_alone():
    sections = [{"title": "Captured log call", "text": "short"}]

    assert trim_log_sections(sections, 100) == sections


def test_trim_log_sections_is_a_no_op_without_a_limit():
    sections = [{"title": "Captured log call", "text": "x" * 5000}]

    assert trim_log_sections(sections, 0) == sections


def test_trim_log_sections_keeps_the_tail_and_says_what_went():
    text = "".join("line %d\n" % i for i in range(500))
    trimmed = trim_log_sections([{"title": "Captured log call", "text": text}], 100)

    assert trimmed[0]["title"] == "Trimmed"
    assert "characters dropped" in trimmed[0]["text"]

    # the end of the run survives, and it starts on a whole line
    assert trimmed[1]["text"].endswith("line 499\n")
    assert trimmed[1]["text"].startswith("line ")
    assert len(trimmed[1]["text"]) <= 100


def test_trim_log_sections_spends_the_budget_on_the_last_sections():
    """What is closest to the end of the test is what gets kept, so a chatty
    setup never crowds out the call it was preparing for."""
    sections = [
        {"title": "Captured stdout setup", "text": "setup\n" * 100},
        {"title": "Captured stdout call", "text": "call\n"},
    ]
    trimmed = trim_log_sections(sections, 20)

    assert [section["title"] for section in trimmed] == [
        "Trimmed", "Captured stdout setup", "Captured stdout call",
    ]
    assert trimmed[2]["text"] == "call\n"
    assert trimmed[1]["text"] == "setup\nsetup\n"


def test_trim_log_sections_drops_a_section_the_budget_cannot_reach():
    sections = [
        {"title": "Captured stdout setup", "text": "setup\n" * 100},
        {"title": "Captured stdout call", "text": "call\n"},
    ]
    trimmed = trim_log_sections(sections, 6)

    assert [section["title"] for section in trimmed] == ["Trimmed", "Captured stdout call"]


def test_count_log_lines_covers_every_section():
    sections = [{"title": "a", "text": "one\ntwo"}, {"title": "b", "text": "three\n"}]

    assert count_log_lines(sections) == 3


def test_escape_report_text_defuses_the_template_placeholder_syntax():
    """A log line that looks like a placeholder must be shown, not filled in
    when the page is assembled."""
    escaped = escape_report_text("see %(archive_status)% and <b>this</b>")

    assert "%(" not in escaped
    assert "&#40;" in escaped
    assert "&lt;b&gt;" in escaped


# --------------------------------------------------------------------------
# saying why the Logs column is empty
# --------------------------------------------------------------------------

def test_capture_notice_warns_when_stdout_is_not_captured():
    notice = capture_notice(_FakeConfig(options={"capture": "no"}), "all")

    assert "--capture=no" in notice


def test_capture_notice_is_silent_when_capture_is_on():
    assert capture_notice(_FakeConfig(options={"capture": "fd"}), "all") == ""


def test_capture_notice_is_silent_when_logs_are_switched_off():
    """Nothing is missing that the run asked for, so there is nothing to say."""
    assert capture_notice(_FakeConfig(options={"capture": "no"}), "none") == ""


def test_capture_summary_names_the_streams_that_survive():
    summary = capture_summary(_FakeConfig(options={"capture": "no", "log_level": "INFO"}), "all")

    assert summary == "all tests: logging only (stdout and stderr are off under -s), logging from INFO"


def test_capture_summary_covers_the_failed_only_mode():
    summary = capture_summary(_FakeConfig(options={"capture": "fd", "log_level": "DEBUG"}), "failed")

    assert summary == "failed tests only: stdout, stderr and logging, logging from DEBUG"


def test_capture_summary_says_when_nothing_is_kept():
    assert capture_summary(_FakeConfig(), "none") == "disabled (--report-logs=none)"


def test_capture_summary_falls_back_to_the_root_logger_level():
    """Unset, pytest keeps whatever the root logger is already emitting."""
    summary = capture_summary(_FakeConfig(options={"capture": "fd"}), "all")

    assert summary.endswith("logging from WARNING")


def test_report_path_defaults_to_cwd():
    assert report_path(_FakeConfig()) == "."


def test_report_path_from_ini():
    config = _FakeConfig(ini={"html_report": "./reports/report.html"})
    assert report_path(config) == "./reports/report.html"


def test_report_path_cli_beats_ini():
    config = _FakeConfig(
        options={"path": "./cli/report.html"},
        ini={"html_report": "./ini/report.html"},
    )
    assert report_path(config) == "./cli/report.html"


def test_report_path_expands_time_placeholders():
    now = datetime.now()
    config = _FakeConfig(options={"path": "./reports/%Y%m%d/report_%H%M.html"})

    expected = "./reports/{}/report_{}.html".format(
        now.strftime("%Y%m%d"), now.strftime("%H%M")
    )
    assert report_path(config) == expected


def test_report_path_leaves_a_plain_path_alone():
    config = _FakeConfig(options={"path": "./report/100% coverage.html"})
    assert report_path(config) == "./report/100% coverage.html"


def test_report_path_keeps_an_escaped_percent():
    config = _FakeConfig(options={"path": "./report/%%Y.html"})
    assert report_path(config) == "./report/%Y.html"
