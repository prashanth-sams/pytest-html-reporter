"""Cover the Test Suite chart on the dashboard.

Each suite is one stacked bar and each of the six outcomes is a dataset of its
own, filled from that outcome's count per suite. The XFailed dataset was being
filled from the Failed counts, so every failure was drawn a second time as an
expected failure: a suite with five failures and no xfail at all read "Failed:
5, XFailed: 5" in its tooltip, on a page whose headline said there were none.
The template was always handed the right placeholders - it was the values put
into them that were crossed - so the chart is read here off the rendered page.
"""

import json
import re

import pytest

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
    "_executed", "_step_tree", "_step_store", "_step_state", "_step_named",
    "_step_total",
)


@pytest.fixture(autouse=True)
def _isolate_config_vars():
    saved = {name: getattr(ConfigVars, name) for name in _TOUCHED}
    for name in _TOUCHED:
        setattr(ConfigVars, name, [] if isinstance(saved[name], list) else type(saved[name])())
    yield
    for name, value in saved.items():
        setattr(ConfigVars, name, value)


def _record(suite, name, status, index):
    return {
        "suite_name": suite,
        "test_name": name,
        "nodeid": suite + "::" + name,
        "status": status,
        "message": "",
        "duration": 0.01,
        "rerun": 0,
        "index": index,
        "worker": "",
        "screenshots": [],
        "logs": [],
        "attachments": [],
    }


def _suite_chart(records):
    """The chart's datasets by label, as the page hands them to Chart.js."""
    reporter = HTMLReporter(".", "", _FakeConfig())
    reporter._records = records

    reporter.build_report()
    page = reporter.renew_template_text("logo.png")

    script = page[page.index("getElementById('groupBarChart')"):]
    script = script[:script.index("</script>")]

    return {
        label: json.loads(data)
        for label, data in re.findall(r"label: '(\w+)',.*?data: (\[[^\]]*\])", script, re.S)
    }


def test_a_failure_is_not_drawn_again_as_an_expected_failure():
    chart = _suite_chart([
        _record("tests/test_a.py", "test_one", "FAIL", 0),
        _record("tests/test_a.py", "test_two", "FAIL", 1),
        _record("tests/test_b.py", "test_three", "xFAIL", 2),
    ])

    assert chart["Failed"] == [2, 0]
    assert chart["XFailed"] == [0, 1]


def test_every_outcome_is_drawn_from_its_own_count():
    # A different count for each, so two datasets reading the same list
    # cannot pass for right.
    counts = {"PASS": 1, "FAIL": 2, "SKIP": 3, "xPASS": 4, "xFAIL": 5, "ERROR": 6}
    records = []
    for status, count in counts.items():
        for _ in range(count):
            records.append(_record("tests/test_a.py", "test_" + str(len(records)), status, len(records)))

    assert _suite_chart(records) == {
        "Passed": [1], "Failed": [2], "Skipped": [3],
        "XPassed": [4], "XFailed": [5], "Error": [6],
    }
