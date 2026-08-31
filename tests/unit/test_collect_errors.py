"""Cover the files that never produced a test at all.

A module that fails to import yields no items, so nothing reaches
pytest_runtest_teardown and the whole file - the error and every test in it -
used to be missing from the report while pytest printed it as an error. A
broken import is exactly the case where the report is read to find out what
happened, so it is collected from pytest_collectreport instead.
"""

import json
import os
import subprocess
import sys
import textwrap

import pytest

from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.html_reporter import (
    COLLECT_ERROR_NAME,
    COLLECT_SKIP_NAME,
    HTMLReporter,
)


class _FakePluginManager:
    def __init__(self, plugins=()):
        self._plugins = set(plugins)

    def hasplugin(self, name):
        return name in self._plugins


class _FakeConfig:
    def __init__(self, plugins=(), workerinput=None):
        self.pluginmanager = _FakePluginManager(plugins)
        if workerinput is not None:
            self.workerinput = workerinput

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
    """ConfigVars is class-level state, so hand each test a clean copy."""
    saved = {name: getattr(ConfigVars, name) for name in _TOUCHED}
    for name in _TOUCHED:
        setattr(ConfigVars, name, [] if isinstance(saved[name], list) else type(saved[name])())
    yield
    for name, value in saved.items():
        setattr(ConfigVars, name, value)


def _reporter(**kwargs):
    return HTMLReporter(".", "", _FakeConfig(**kwargs))


def _collect_record(nodeid, status="ERROR", worker="", **kwargs):
    record = {
        "suite_name": nodeid,
        "test_name": COLLECT_ERROR_NAME,
        "nodeid": nodeid,
        "status": status,
        "message": "ImportError while importing test module",
        "duration": 0,
        "rerun": 0,
        "index": -1,
        "worker": worker,
        "screenshot": None,
        "logs": [],
        "attachments": [],
        "collect": True,
    }
    record.update(kwargs)
    return record


def _test_record(suite, name, status, index, worker="", **kwargs):
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


class _CollectReport:
    """Just enough of pytest's CollectReport for the hook to read."""

    def __init__(self, nodeid, outcome, longrepr=None, longreprtext=""):
        self.nodeid = nodeid
        self.outcome = outcome
        self.longrepr = longrepr
        self.longreprtext = longreprtext

    passed = property(lambda self: self.outcome == "passed")
    failed = property(lambda self: self.outcome == "failed")
    skipped = property(lambda self: self.outcome == "skipped")


# --------------------------------------------------------------------------
# what the hook records
# --------------------------------------------------------------------------

def test_a_collector_that_imported_cleanly_is_not_recorded():
    reporter = _reporter()

    reporter.pytest_collectreport(_CollectReport("tests/test_a.py", "passed"))

    assert reporter._records == []


def test_the_session_collector_itself_is_not_recorded():
    reporter = _reporter()

    reporter.pytest_collectreport(_CollectReport("", "failed", longreprtext="boom"))

    assert reporter._records == []


def test_a_module_that_failed_to_import_is_recorded_as_an_error():
    reporter = _reporter()

    reporter.pytest_collectreport(
        _CollectReport("tests/test_a.py", "failed", longrepr=object(), longreprtext="ImportError: no")
    )

    record, = reporter._records
    assert record["suite_name"] == "tests/test_a.py"
    assert record["test_name"] == COLLECT_ERROR_NAME
    assert record["status"] == "ERROR"
    assert record["message"] == "ImportError: no"
    assert record["collect"] is True


def test_a_module_skipped_at_module_level_is_recorded_as_a_skip():
    reporter = _reporter()

    # a skipped collector's longrepr is a (path, lineno, reason) tuple; the
    # reason is what belongs in the report, not the tuple's repr
    reporter.pytest_collectreport(
        _CollectReport("tests/test_a.py", "skipped", longrepr=("/abs/tests/test_a.py", 2, "Skipped: no driver"))
    )

    record, = reporter._records
    assert record["test_name"] == COLLECT_SKIP_NAME
    assert record["status"] == "SKIP"
    assert record["message"] == "Skipped: no driver"


# --------------------------------------------------------------------------
# one record per broken file, however many processes saw it
# --------------------------------------------------------------------------

def test_the_same_broken_file_is_recorded_once():
    reporter = _reporter()

    reporter.store_collect_record(_collect_record("tests/test_a.py", worker="gw0"))
    reporter.store_collect_record(_collect_record("tests/test_a.py", worker="gw1"))

    assert len(reporter._records) == 1


def test_two_broken_files_are_both_recorded():
    reporter = _reporter()

    reporter.store_collect_record(_collect_record("tests/test_a.py"))
    reporter.store_collect_record(_collect_record("tests/test_b.py"))

    assert [r["nodeid"] for r in reporter._records] == ["tests/test_a.py", "tests/test_b.py"]


def test_worker_records_are_routed_by_kind():
    reporter = _reporter()

    reporter.store_record(_collect_record("tests/test_a.py"))
    reporter.store_record(_test_record("tests/test_b.py", "test_one", "PASS", 0))

    assert reporter._collect_slots == {"tests/test_a.py"}
    assert reporter._record_slots == {"tests/test_b.py::test_one": 1}


def test_a_controller_keeps_one_copy_of_every_workers_collect_error():
    workers = []
    for worker_id in ("gw0", "gw1"):
        worker = _reporter(workerinput={"workerid": worker_id})
        worker.pytest_collectreport(
            _CollectReport("tests/test_a.py", "failed", longreprtext="ImportError: no")
        )
        worker.config.workeroutput = {}
        worker.pytest_sessionfinish(session=None)
        workers.append(worker)

    controller = _reporter()
    for worker in workers:
        node = type("Node", (), {"workeroutput": worker.config.workeroutput})()
        controller.pytest_testnodedown(node, error=None)

    assert len(controller._records) == 1


# --------------------------------------------------------------------------
# how it lands in the report
# --------------------------------------------------------------------------

def test_a_broken_file_sorts_ahead_of_the_run():
    reporter = _reporter()
    reporter._records = [
        _test_record("tests/test_b.py", "test_one", "PASS", 0),
        _test_record("tests/test_b.py", "test_two", "PASS", 1),
        _collect_record("tests/test_a.py"),
    ]

    reporter.build_report()

    suites = reporter.json_data["content"]["suites"]
    assert suites[0]["suite_name"] == "tests/test_a.py"
    assert suites[0]["status"]["total_error"] == 1


def test_a_broken_file_is_counted_in_the_totals():
    reporter = _reporter()
    reporter._records = [
        _collect_record("tests/test_a.py"),
        _collect_record("tests/test_b.py", status="SKIP", test_name=COLLECT_SKIP_NAME),
        _test_record("tests/test_c.py", "test_one", "PASS", 0),
    ]

    reporter.build_report()

    assert ConfigVars._total == 3
    assert ConfigVars._error == 1
    assert ConfigVars._skip == 1
    assert ConfigVars._pass == 1


# --------------------------------------------------------------------------
# end to end
# --------------------------------------------------------------------------

SAMPLE = {
    "test_broken.py": """
        import a_module_that_is_not_installed
        def test_never_runs(): assert True
        def test_never_runs_either(): assert True
    """,
    "test_modskip.py": """
        import pytest
        pytest.skip("no driver on this box", allow_module_level=True)
        def test_also_never_runs(): assert True
    """,
    "test_fine.py": """
        def test_passes(): assert True
        def test_fails(): assert 1 == 2
    """,
}


def _run(tmp_path, *args):
    """Run the sample suite in its own process and return the report it wrote."""
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


def test_a_module_that_will_not_import_reaches_the_report(tmp_path):
    data = _run(tmp_path, "--continue-on-collection-errors")

    assert ("test_broken.py", COLLECT_ERROR_NAME, "ERROR") in _flatten(data)
    # the totals agree with what pytest printed: 1 passed, 1 failed, 1 skipped,
    # 1 error - rather than quietly dropping the file that never loaded
    assert data["status_list"]["error"] == "1"
    assert data["status_list"]["skip"] == "1"
    assert data["total_tests"] == "4"


def test_the_import_error_itself_is_kept(tmp_path):
    data = _run(tmp_path, "--continue-on-collection-errors")

    message = [
        test["message"]
        for suite in data["content"]["suites"].values()
        for test in suite["tests"].values()
        if test["test_name"] == COLLECT_ERROR_NAME
    ][0]
    assert "a_module_that_is_not_installed" in message


def test_a_module_level_skip_reaches_the_report_with_its_reason(tmp_path):
    data = _run(tmp_path, "--continue-on-collection-errors")

    message = [
        test["message"]
        for suite in data["content"]["suites"].values()
        for test in suite["tests"].values()
        if test["test_name"] == COLLECT_SKIP_NAME
    ][0]
    assert "no driver on this box" in message


def test_an_interrupted_collection_still_writes_a_report(tmp_path):
    # without --continue-on-collection-errors pytest stops the run outright, and
    # the report used not to be written at all - no file, and no reason given
    data = _run(tmp_path)

    assert ("test_broken.py", COLLECT_ERROR_NAME, "ERROR") in _flatten(data)


def test_a_parallel_run_reports_the_broken_file_once(tmp_path):
    pytest.importorskip("xdist")

    data = _run(tmp_path, "-n", "2", "--continue-on-collection-errors")

    broken = [row for row in _flatten(data) if row[1] == COLLECT_ERROR_NAME]
    assert len(broken) == 1, broken
    assert data["status_list"]["error"] == "1"
