"""Cover the two controls that sit beside a failure message.

The cell has room for about fifty characters of an error, so a row on its own
has never been enough to triage from: the rest of the message had to be opened,
and then selected by hand before it could be pasted anywhere. The expand button
opens the whole thing in the report's own panel and the copy button puts it on
the clipboard without opening anything at all.
"""

import pytest
from bs4 import BeautifulSoup

from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.html_reporter import HTMLReporter


class _FakePluginManager:
    def hasplugin(self, name):
        return False


class _FakeConfig:
    def __init__(self):
        self.pluginmanager = _FakePluginManager()

    def getoption(self, name, default=None):
        return default

    def getini(self, name):
        raise ValueError(name)


_TOUCHED = (
    "_test_metrics_content", "_suite_metrics_content", "_test_suite_name",
    "_test_pass_list", "_test_fail_list", "_test_skip_list", "_test_xpass_list",
    "_test_xfail_list", "_test_error_list", "_attach_screenshot_details",
    "_pass", "_fail", "_skip", "_error", "_xpass", "_xfail", "_total",
    "_executed",
)


@pytest.fixture(autouse=True)
def _isolate_config_vars():
    saved = {name: getattr(ConfigVars, name) for name in _TOUCHED}
    for name in _TOUCHED:
        setattr(ConfigVars, name, [] if isinstance(saved[name], list) else type(saved[name])())
    yield
    for name, value in saved.items():
        setattr(ConfigVars, name, value)


def _record(suite, name, status="FAIL", message="", index=0):
    return {
        "suite_name": suite,
        "test_name": name,
        "nodeid": suite + "::" + name,
        "status": status,
        "message": message,
        "duration": 0.01,
        "rerun": 0,
        "index": index,
        "worker": "",
        "screenshots": [],
        "logs": [],
        "attachments": [],
    }


def _rows(records):
    reporter = HTMLReporter(".", "", _FakeConfig())
    reporter._records = list(records)
    reporter.build_report()

    return BeautifulSoup("<table>" + ConfigVars._test_metrics_content + "</table>", "html.parser")


def _actions(soup):
    return soup.findAll("span", class_="msg-actions")


LONG = "assert 1 == 2\n" + "".join("  line %d\n" % i for i in range(40))


# --------------------------------------------------------------------------
# what the row carries
# --------------------------------------------------------------------------

def test_the_row_carries_the_whole_error_not_the_preview():
    """The cell shows the first fifty characters; both controls get all of it."""
    soup = _rows([_record("tests/test_a.py", "test_one", message=LONG)])
    actions = _actions(soup)[0]

    assert actions["data-error"] == LONG
    assert len(actions["data-error"]) > 50


def test_the_row_names_the_test_the_panel_will_be_opened_for():
    soup = _rows([_record("tests/test_a.py", "test_one", message=LONG)])
    actions = _actions(soup)[0]

    assert actions["data-suite"] == "tests/test_a.py"
    assert actions["data-test"] == "test_one"


def test_every_failing_row_carries_its_own_error():
    soup = _rows([
        _record("tests/test_a.py", "test_one", message="first " + LONG, index=0),
        _record("tests/test_a.py", "test_two", status="PASS", message="", index=1),
        _record("tests/test_b.py", "test_three", message="third " + LONG, index=2),
    ])

    assert [node["data-error"] for node in _actions(soup)] == ["first " + LONG, "third " + LONG]


# --------------------------------------------------------------------------
# which rows get them
# --------------------------------------------------------------------------

def test_a_passing_row_offers_nothing():
    """Nothing to copy, and a button that copies an empty string reads as a bug."""
    soup = _rows([_record("tests/test_a.py", "test_one", status="PASS", message="")])

    assert _actions(soup) == []


def test_a_message_of_pure_whitespace_counts_as_nothing_to_copy():
    soup = _rows([_record("tests/test_a.py", "test_one", message="  \n\n  ")])

    assert _actions(soup) == []


def test_a_skipped_row_keeps_its_reason():
    soup = _rows([_record("tests/test_a.py", "test_one", status="SKIP",
                          message="Skipped: needs a database")])

    assert _actions(soup)[0]["data-error"] == "Skipped: needs a database"


def test_a_message_that_fits_is_copyable_but_has_nothing_to_expand_to():
    soup = _rows([_record("tests/test_a.py", "test_one", message="boom")])
    actions = _actions(soup)[0]

    assert actions["data-full"] == ""
    assert actions["data-error"] == "boom"


def test_a_message_that_was_cut_offers_the_panel():
    soup = _rows([_record("tests/test_a.py", "test_one", message=LONG)])

    assert _actions(soup)[0]["data-full"] == "1"


# --------------------------------------------------------------------------
# the text stays text
# --------------------------------------------------------------------------

def test_a_message_holding_quotes_cannot_break_out_of_the_attribute():
    message = 'assert "a" == \'b\' <script>alert(1)</script> ' + "x" * 60

    soup = _rows([_record("tests/test_a.py", "test_one", message=message)])

    # Read back through the parser: had the quoting failed there would be no
    # attribute to read, or a stray tag beside it.
    assert _actions(soup)[0]["data-error"] == message
    assert soup.find("script") is None


def test_a_message_shaped_like_a_placeholder_is_not_substituted():
    message = "%(archive_status)% went missing " + "y" * 60

    soup = _rows([_record("tests/test_a.py", "test_one", message=message)])

    assert "%(archive_status)%" not in ConfigVars._test_metrics_content
    assert _actions(soup)[0]["data-error"] == message


def test_the_controls_add_only_an_ellipsis_to_the_cell_the_table_exports():
    """Search, CSV, Excel and print are all built from cell text. The error
    rides in an attribute, so all four get the cut message and the ellipsis
    that says it was cut - not a traceback per row."""
    soup = _rows([_record("tests/test_a.py", "test_one", message=LONG)])
    cell = soup.findAll("td")[5]

    assert _actions(soup)[0].get_text(strip=True) == "…"
    assert LONG not in cell.get_text()
    assert cell.get_text(strip=True).endswith("…")
