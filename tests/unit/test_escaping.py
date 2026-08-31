"""Cover report text that happens to look like markup.

A test name, a parameter id and an assertion message are all arbitrary text,
and they routinely hold angle brackets - `assert <Foo object at 0x7f> == 3` is
what an ordinary failure looks like. Written into the page as-is, a browser
reads them as tags: the row is mangled, the rows after it are swallowed with
it, and a name like `<script>...` becomes script the page runs. The page is
also assembled by substituting `%(name)%` placeholders, so text shaped like one
has to be defused too.
"""

import json
import os
import subprocess
import sys
import textwrap

import pytest

from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.html_reporter import HTMLReporter
from pytest_html_reporter.util import js_literal


class _FakePluginManager:
    def __init__(self, plugins=()):
        self._plugins = set(plugins)

    def hasplugin(self, name):
        return name in self._plugins


class _FakeConfig:
    def __init__(self, plugins=()):
        self.pluginmanager = _FakePluginManager(plugins)

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


def _reporter():
    return HTMLReporter(".", "", _FakeConfig())


def _record(suite, name, status="FAIL", index=0, message="", **kwargs):
    record = {
        "suite_name": suite,
        "test_name": name,
        "nodeid": suite + "::" + name,
        "status": status,
        "message": message,
        "duration": 0.01,
        "rerun": 0,
        "index": index,
        "worker": "",
        "screenshot": None,
        "logs": [],
        "attachments": [],
    }
    record.update(kwargs)
    return record


# --------------------------------------------------------------------------
# the metrics rows
# --------------------------------------------------------------------------

def test_a_test_name_holding_markup_is_written_as_text():
    reporter = _reporter()
    reporter._records = [_record("tests/test_a.py", "test_p[<script>alert(1)</script>]")]

    reporter.build_report()

    assert "<script>alert(1)</script>" not in ConfigVars._test_metrics_content
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in ConfigVars._test_metrics_content


def test_a_failure_message_holding_a_repr_is_written_as_text():
    # what an ordinary assertion against an object looks like
    reporter = _reporter()
    reporter._records = [
        _record("tests/test_a.py", "test_one", message="assert <Thing object at 0xdead> == 3")
    ]

    reporter.build_report()

    assert "<Thing object" not in ConfigVars._test_metrics_content
    assert "&lt;Thing object at 0xdead&gt;" in ConfigVars._test_metrics_content


def test_a_quote_in_a_name_cannot_end_an_attribute():
    reporter = _reporter()
    reporter._records = [_record('tests/test_a.py', 'test_p["]')]

    reporter.build_report()

    assert '&quot;' in ConfigVars._test_metrics_content


def test_a_suite_name_holding_markup_is_written_as_text():
    reporter = _reporter()
    reporter._records = [_record("tests/<b>test_a</b>.py", "test_one")]

    reporter.build_report()

    assert "<b>test_a</b>" not in ConfigVars._suite_metrics_content
    assert "&lt;b&gt;test_a&lt;/b&gt;" in ConfigVars._suite_metrics_content


def test_text_shaped_like_a_placeholder_is_not_substituted():
    reporter = _reporter()
    reporter._records = [_record("tests/test_a.py", "test_one", message="%(archive_status)% went wrong")]

    reporter.build_report()

    assert "%(archive_status)%" not in ConfigVars._test_metrics_content
    assert "%&#40;archive_status)%" in ConfigVars._test_metrics_content


def test_a_long_message_holding_markup_is_escaped_in_the_modal():
    long_message = "<b>" + "x" * 80 + "</b>"
    reporter = _reporter()
    reporter._records = [_record("tests/test_a.py", "test_one", message=long_message)]

    reporter.build_report()

    assert "<b>" not in ConfigVars._test_metrics_content
    assert "&lt;b&gt;" in ConfigVars._test_metrics_content


def test_the_modal_is_opened_on_the_raw_length_not_the_escaped_one():
    # "<<<..." is 40 characters and needs no modal; escaped it is over 49, and
    # measuring after escaping would open one for a message that fits
    reporter = _reporter()
    reporter._records = [_record("tests/test_a.py", "test_one", message="<" * 40)]

    reporter.build_report()

    assert "myModal-" not in ConfigVars._test_metrics_content


def test_a_screenshot_caption_holding_markup_is_written_as_text():
    shot = {"name": "1234", "suite": "test_a", "test": "test_<b>one</b>", "error": "went <wrong>"}
    reporter = _reporter()
    reporter._records = [_record("tests/test_a.py", "test_one", screenshot=shot)]

    reporter.build_report()

    assert "<b>one</b>" not in ConfigVars._attach_screenshot_details
    assert "&lt;b&gt;one&lt;/b&gt;" in ConfigVars._attach_screenshot_details
    assert "&lt;wrong&gt;" in ConfigVars._attach_screenshot_details


# --------------------------------------------------------------------------
# the chart labels, which are source code rather than markup
# --------------------------------------------------------------------------

def test_js_literal_renders_a_list_of_names():
    assert js_literal(["test_a", "test_b"]) == '["test_a", "test_b"]'


def test_js_literal_quotes_an_apostrophe_rather_than_ending_the_array():
    assert js_literal(["it's"]) == '["it\'s"]'


def test_js_literal_keeps_a_name_from_closing_the_script_tag():
    assert "</script>" not in js_literal(["</script>"])
    assert "\\u003c" in js_literal(["</script>"])


def test_js_literal_defuses_the_template_placeholder_syntax():
    assert "%(archives)%" not in js_literal(["%(archives)%"])


def test_the_chart_labels_survive_a_quote_in_a_suite_name():
    reporter = _reporter()
    reporter._records = [_record("tests/it's_a.py", "test_one")]

    reporter.build_report()
    page = reporter.renew_template_text("logo.png")

    labels = [line for line in page.splitlines() if "labels:" in line and "it" in line]
    assert labels, "the suite label never reached the chart"
    assert "['it" not in labels[0]


# --------------------------------------------------------------------------
# end to end
# --------------------------------------------------------------------------

SAMPLE = {
    "test_nasty.py": """
        import pytest

        class Thing:
            def __repr__(self): return "<Thing object at 0xdead>"

        def test_repr_in_message():
            assert Thing() == 3, "comparing <Thing> & 'stuff'"

        @pytest.mark.parametrize("v", ["<script>alert(1)</script>", "a & b", 'q"h', "%(archives)%"])
        def test_parametrized_names(v):
            assert v == "never"

        def test_long_message():
            assert 0, "<b>" + "x" * 80 + "</b> & a long tail so the modal is used 'here'"
    """,
}

EXPECTED_ROWS = 6


def _page(tmp_path, *args):
    for name, body in SAMPLE.items():
        (tmp_path / name).write_text(textwrap.dedent(body).lstrip())

    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--html-report=./report", "-p", "no:cacheprovider"] + list(args),
        cwd=str(tmp_path),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )

    report = tmp_path / "report" / "pytest_html_report.html"
    assert report.is_file(), result.stdout

    return report.read_text(encoding="utf-8")


def test_every_row_survives_a_name_that_looks_like_a_tag(tmp_path):
    bs4 = pytest.importorskip("bs4")

    soup = bs4.BeautifulSoup(_page(tmp_path), "html.parser")
    rows = soup.find("table", id="tm").find_all("tr")[1:]

    # the markup in one name used to swallow the rows that followed it
    assert len(rows) == EXPECTED_ROWS, [r.get_text(" ", strip=True) for r in rows]


def test_a_test_name_never_becomes_script_the_page_runs(tmp_path):
    bs4 = pytest.importorskip("bs4")

    page = _page(tmp_path)
    soup = bs4.BeautifulSoup(page, "html.parser")

    assert [s for s in soup.find_all("script") if "alert(1)" in (s.string or "")] == []
    assert "<script>alert(1)</script>" not in page


def test_a_name_is_shown_exactly_as_pytest_named_it(tmp_path):
    bs4 = pytest.importorskip("bs4")

    soup = bs4.BeautifulSoup(_page(tmp_path), "html.parser")
    names = [tr.find_all("td")[1].get_text(" ", strip=True) for tr in soup.find("table", id="tm").find_all("tr")[1:]]

    assert "test_parametrized_names[<script>alert(1)</script>]" in names
    assert "test_parametrized_names[a & b]" in names
    assert "test_parametrized_names[%(archives)%]" in names


def test_a_title_holding_markup_is_shown_as_text(tmp_path):
    bs4 = pytest.importorskip("bs4")

    soup = bs4.BeautifulSoup(_page(tmp_path, "--title=<b>My & Title</b>"), "html.parser")
    title = soup.find("span", class_="header__title-text")

    assert title.get_text(strip=True) == "<b>My & Title</b>"
    assert title.find("b") is None


def test_the_json_report_keeps_the_text_unescaped(tmp_path):
    # escaping belongs to the page; output.json is data and is read back by the
    # archive and trend views
    _page(tmp_path)

    data = json.loads((tmp_path / "report" / "output.json").read_text(encoding="utf-8"))
    names = [
        test["test_name"]
        for suite in data["content"]["suites"].values()
        for test in suite["tests"].values()
    ]

    assert "test_parametrized_names[<script>alert(1)</script>]" in names
