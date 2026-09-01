"""Cover the pieces that let one report survive a pytest-xdist run.

The pure-python half checks how records are merged into suites and totals; the
pytester half actually shells out to `pytest -n 2` and reads the report back.
"""

import json
import os
import subprocess
import sys
import textwrap

import pytest
from bs4 import BeautifulSoup

from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.html_reporter import HTMLReporter
from pytest_html_reporter.util import is_xdist_worker, xdist_worker_id


class _FakePluginManager:
    def __init__(self, plugins=()):
        self._plugins = set(plugins)

    def hasplugin(self, name):
        return name in self._plugins


class _FakeConfig:
    """Just enough of pytest's Config for the reporter to be constructed."""

    def __init__(self, options=None, plugins=(), workerinput=None):
        self._options = options or {}
        self.pluginmanager = _FakePluginManager(plugins)
        if workerinput is not None:
            self.workerinput = workerinput

    def getoption(self, name, default=None):
        return self._options.get(name, default)

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
    """ConfigVars is class-level state, so hand each test a clean copy."""
    saved = {name: getattr(ConfigVars, name) for name in _TOUCHED}
    for name in _TOUCHED:
        setattr(ConfigVars, name, [] if isinstance(saved[name], list) else type(saved[name])())
    yield
    for name, value in saved.items():
        setattr(ConfigVars, name, value)


def _record(suite, name, status, index, worker="", **kwargs):
    record = {
        "suite_name": suite,
        "test_name": name,
        "nodeid": suite + "::" + name,
        "status": status,
        "message": "",
        "duration": 0.01,
        "rerun": 0,
        "index": index,
        "worker": worker,
        "screenshot": None,
    }
    record.update(kwargs)
    return record


def _reporter(**kwargs):
    return HTMLReporter(".", "", _FakeConfig(**kwargs))


# --------------------------------------------------------------------------
# worker detection
# --------------------------------------------------------------------------

def test_a_plain_run_is_not_a_worker():
    assert is_xdist_worker(_FakeConfig()) is False
    assert xdist_worker_id(_FakeConfig()) == ""


def test_a_worker_is_detected_and_named():
    config = _FakeConfig(workerinput={"workerid": "gw3"})
    assert is_xdist_worker(config) is True
    assert xdist_worker_id(config) == "gw3"


# --------------------------------------------------------------------------
# merging records into a report
# --------------------------------------------------------------------------

def test_records_from_several_workers_land_in_collection_order():
    reporter = _reporter()
    # gw0 took the odd tests, gw1 the even ones, and gw1 finished first.
    reporter._records = [
        _record("tests/test_a.py", "test_two", "PASS", 1, worker="gw1"),
        _record("tests/test_b.py", "test_four", "FAIL", 3, worker="gw1"),
        _record("tests/test_a.py", "test_one", "PASS", 0, worker="gw0"),
        _record("tests/test_b.py", "test_three", "SKIP", 2, worker="gw0"),
    ]

    reporter.build_report()

    suites = reporter.json_data["content"]["suites"]
    assert [suites[i]["suite_name"] for i in suites] == ["tests/test_a.py", "tests/test_b.py"]
    assert [t["test_name"] for t in suites[0]["tests"].values()] == ["test_one", "test_two"]
    assert [t["test_name"] for t in suites[1]["tests"].values()] == ["test_three", "test_four"]


def test_a_suite_split_across_workers_is_reported_once():
    reporter = _reporter()
    reporter._records = [
        _record("tests/test_a.py", "test_one", "PASS", 0, worker="gw0"),
        _record("tests/test_a.py", "test_two", "FAIL", 1, worker="gw1"),
        _record("tests/test_a.py", "test_three", "PASS", 2, worker="gw0"),
    ]

    reporter.build_report()

    suites = reporter.json_data["content"]["suites"]
    assert len(suites) == 1
    assert suites[0]["status"]["total_pass"] == 2
    assert suites[0]["status"]["total_fail"] == 1
    assert ConfigVars._suite_metrics_content.count("<tr>") == 1


def test_every_status_is_counted_once():
    reporter = _reporter()
    statuses = ["PASS", "FAIL", "SKIP", "ERROR", "xPASS", "xFAIL"]
    reporter._records = [
        _record("tests/test_a.py", "test_" + s, s, i) for i, s in enumerate(statuses)
    ]

    reporter.build_report()

    assert reporter.json_data["content"]["suites"][0]["status"] == {
        "total_pass": 1, "total_fail": 1, "total_skip": 1,
        "total_error": 1, "total_xpass": 1, "total_xfail": 1, "total_rerun": 0,
    }
    # the dashboard totals have to add up to the number of tests that ran
    assert ConfigVars._total == len(statuses)


def test_reruns_are_summed_per_suite():
    reporter = _reporter()
    reporter._records = [
        _record("tests/test_a.py", "test_one", "FAIL", 0, rerun=2),
        _record("tests/test_a.py", "test_two", "PASS", 1, rerun=1),
    ]

    reporter.build_report()

    assert reporter.json_data["content"]["suites"][0]["status"]["total_rerun"] == 3


def test_each_test_metrics_row_carries_its_own_rerun_count():
    """The suite total says the run retried three times; only the row says
    which test they were spent on."""
    reporter = _reporter()
    reporter._records = [
        _record("tests/test_a.py", "test_one", "FAIL", 0, rerun=2),
        _record("tests/test_a.py", "test_two", "PASS", 1, rerun=1),
        _record("tests/test_a.py", "test_three", "PASS", 2),
    ]

    reporter.build_report()

    soup = BeautifulSoup("<table>" + ConfigVars._test_metrics_content + "</table>", "html.parser")
    rows = [[cell.text.strip() for cell in row.findAll("td")] for row in soup.findAll("tr")]

    assert [(row[1], row[4]) for row in rows] == [
        ("test_one", "2"), ("test_two", "1"), ("test_three", "0"),
    ]


def test_error_modals_get_distinct_ids():
    long_message = "E   assert something quite long went wrong here indeed" * 2
    reporter = _reporter()
    reporter._records = [
        _record("tests/test_a.py", "test_one", "FAIL", 0, message=long_message),
        _record("tests/test_b.py", "test_two", "FAIL", 1, message=long_message),
    ]

    reporter.build_report()

    ids = set(part.split('"')[0] for part in ConfigVars._test_metrics_content.split('id="myModal-')[1:])
    assert len(ids) == 2


def test_a_worker_hands_its_records_to_the_controller():
    worker = _reporter(workerinput={"workerid": "gw0"})
    worker._records = [_record("tests/test_a.py", "test_one", "PASS", 0, worker="gw0")]
    worker.config.workeroutput = {}

    worker.pytest_sessionfinish(session=None)

    controller = _reporter()
    node = type("Node", (), {"workeroutput": worker.config.workeroutput})()
    controller.pytest_testnodedown(node, error=None)

    assert controller._records == worker._records


def test_a_crashed_worker_is_skipped_rather_than_raising():
    controller = _reporter()
    controller.pytest_testnodedown(type("Node", (), {})(), error="boom")

    assert controller._records == []


# --------------------------------------------------------------------------
# end to end
# --------------------------------------------------------------------------

SAMPLE = {
    "test_alpha.py": """
        import pytest

        def test_a_pass(): assert True
        def test_a_fail(): assert 1 == 2
        @pytest.mark.skip(reason="nope")
        def test_a_skip(): pass
    """,
    "test_beta.py": """
        import pytest

        def test_b_pass(): assert True
        def test_b_fail(): assert 1 == 2
        @pytest.mark.xfail(reason="known")
        def test_b_xfail(): assert 1 == 2
    """,
}


def _run(tmp_path, *args):
    """Run the sample suite in its own process and return the report it wrote.

    A subprocess rather than an inline run: the point of these tests is what
    several *processes* agree on, and it keeps the outer run's reporter out of
    the way.
    """
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

    report = tmp_path / "report" / "output.json"
    assert report.is_file(), result.stdout

    return json.loads(report.read_text())


def _flatten(data):
    return [
        (suite["suite_name"], test["test_name"], test["status"])
        for suite in data["content"]["suites"].values()
        for test in suite["tests"].values()
    ]


def test_a_parallel_run_reports_every_test(tmp_path):
    pytest.importorskip("xdist")

    data = _run(tmp_path, "-n", "2")

    assert data["total_tests"] == "6"
    assert data["status_list"]["pass"] == "2"
    assert data["status_list"]["fail"] == "2"
    assert data["status_list"]["skip"] == "1"
    assert data["status_list"]["xfail"] == "1"
    assert len(data["content"]["suites"]) == 2


def test_a_parallel_run_matches_a_serial_one(tmp_path):
    pytest.importorskip("xdist")

    serial = _flatten(_run(tmp_path, "-p", "no:randomly"))
    parallel = _flatten(_run(tmp_path, "-n", "2", "-p", "no:randomly"))

    assert parallel == serial


def test_a_parallel_run_archives_one_build_not_one_per_worker(tmp_path):
    pytest.importorskip("xdist")

    _run(tmp_path, "-n", "4")
    _run(tmp_path, "-n", "4")

    archives = list((tmp_path / "report" / "archive").glob("*.json"))
    assert len(archives) == 1, [a.name for a in archives]


def test_workers_do_not_each_write_a_report(tmp_path):
    pytest.importorskip("xdist")

    data = _run(tmp_path, "-n", "4")

    # four workers, one report: every test is in it exactly once
    names = [name for _, name, _ in _flatten(data)]
    assert sorted(names) == sorted(set(names))
    assert len(names) == 6
