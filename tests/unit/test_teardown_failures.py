"""Cover a test whose fixture blew up while cleaning up after it.

A record is built from the teardown hook, so that a screenshot attached by a
fixture finalizer still has somewhere to go. That hook runs before pytest has
finished reporting the teardown phase, so the phase's own outcome has to be
folded back into the stored record: without it a test whose teardown raised
stood in the report as a plain pass, pytest counted it as an error, and a
failing run could read as green.
"""

import json
import os
import subprocess
import sys
import textwrap

import pytest

from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.html_reporter import HTMLReporter


class _FakePluginManager:
    def __init__(self, plugins=()):
        self._plugins = set(plugins)

    def hasplugin(self, name):
        return name in self._plugins


class _FakeConfig:
    def __init__(self, options=None, plugins=()):
        self._options = options or {}
        self.pluginmanager = _FakePluginManager(plugins)

    def getoption(self, name, default=None):
        return self._options.get(name, default)

    def getini(self, name):
        raise ValueError(name)


@pytest.fixture(autouse=True)
def _isolate_config_vars():
    saved = (ConfigVars._test_status, ConfigVars._current_error)
    yield
    ConfigVars._test_status, ConfigVars._current_error = saved


def _reporter(**kwargs):
    return HTMLReporter(".", "", _FakeConfig(**kwargs))


def _stored(reporter, status):
    record = {
        "suite_name": "tests/test_a.py",
        "test_name": "test_one",
        "nodeid": "tests/test_a.py::test_one",
        "status": status,
        "message": "the real failure" if status == "FAIL" else "",
        "duration": 0.01,
        "rerun": 0,
        "index": 0,
        "worker": "",
        "screenshot": None,
        "logs": [],
        "attachments": [],
    }
    reporter.store_test_record(record)
    return record


# --------------------------------------------------------------------------
# folding the teardown phase back in
# --------------------------------------------------------------------------

def test_a_teardown_that_raised_turns_a_pass_into_an_error():
    reporter = _reporter()
    record = _stored(reporter, "PASS")

    ConfigVars._test_status = "ERROR"
    ConfigVars._current_error = "RuntimeError: teardown blew up"
    reporter.refresh_record("tests/test_a.py::test_one")

    assert record["status"] == "ERROR"
    assert record["message"] == "RuntimeError: teardown blew up"


def test_a_test_that_already_failed_keeps_its_own_failure():
    # pytest lists this one as a failure with an error beside it; the assertion
    # that broke is the headline, not the fixture that tripped on the way out
    reporter = _reporter()
    record = _stored(reporter, "FAIL")

    ConfigVars._test_status = "ERROR"
    ConfigVars._current_error = "RuntimeError: teardown blew up"
    reporter.refresh_record("tests/test_a.py::test_one")

    assert record["status"] == "FAIL"
    assert record["message"] == "the real failure"


def test_a_test_that_errored_in_setup_is_left_alone():
    reporter = _reporter()
    record = _stored(reporter, "ERROR")
    record["message"] = "RuntimeError: setup blew up"

    ConfigVars._test_status = "ERROR"
    ConfigVars._current_error = "RuntimeError: teardown blew up"
    reporter.refresh_record("tests/test_a.py::test_one")

    assert record["message"] == "RuntimeError: setup blew up"


def test_a_clean_teardown_changes_nothing():
    reporter = _reporter()
    record = _stored(reporter, "PASS")

    ConfigVars._test_status = "PASS"
    ConfigVars._current_error = ""
    reporter.refresh_record("tests/test_a.py::test_one")

    assert record["status"] == "PASS"


def test_a_skipped_test_is_not_promoted_by_a_clean_teardown():
    reporter = _reporter()
    record = _stored(reporter, "SKIP")

    ConfigVars._test_status = "SKIP"
    reporter.refresh_record("tests/test_a.py::test_one")

    assert record["status"] == "SKIP"


def test_an_unknown_nodeid_is_a_no_op():
    reporter = _reporter()

    reporter.refresh_record("tests/test_a.py::never_stored")

    assert reporter._records == []


def test_the_attempt_that_stuck_is_the_one_refreshed():
    # with reruns the slot holds the latest attempt, and that is the record the
    # teardown phase belongs to
    reporter = _reporter(plugins=("rerunfailures",))
    _stored(reporter, "FAIL")
    kept = _stored(reporter, "PASS")

    ConfigVars._test_status = "ERROR"
    ConfigVars._current_error = "RuntimeError: teardown blew up"
    reporter.refresh_record("tests/test_a.py::test_one")

    assert reporter._records == [kept]
    assert kept["status"] == "ERROR"


# --------------------------------------------------------------------------
# end to end
# --------------------------------------------------------------------------

SAMPLE = {
    "test_teardown.py": """
        import pytest

        @pytest.fixture
        def bad_teardown():
            yield
            print("OUTPUT FROM THE TEARDOWN")
            raise RuntimeError("teardown blew up")

        def test_passes_but_teardown_fails(bad_teardown): assert True
        def test_fails_and_teardown_fails(bad_teardown): assert 1 == 2, "the real failure"
        def test_plain_pass(): print("quiet pass")
    """,
}


def _run(tmp_path, *args):
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


def _by_name(data):
    return {
        test["test_name"]: test
        for suite in data["content"]["suites"].values()
        for test in suite["tests"].values()
    }


def test_a_failing_teardown_is_not_reported_as_a_pass(tmp_path):
    tests = _by_name(_run(tmp_path))

    assert tests["test_passes_but_teardown_fails"]["status"] == "ERROR"
    assert "teardown blew up" in tests["test_passes_but_teardown_fails"]["message"]


def test_a_test_that_failed_before_its_teardown_keeps_that_failure(tmp_path):
    tests = _by_name(_run(tmp_path))

    assert tests["test_fails_and_teardown_fails"]["status"] == "FAIL"
    assert "the real failure" in tests["test_fails_and_teardown_fails"]["message"]


def test_a_clean_test_is_untouched(tmp_path):
    tests = _by_name(_run(tmp_path))

    assert tests["test_plain_pass"]["status"] == "PASS"


def test_the_totals_no_longer_hide_the_error(tmp_path):
    data = _run(tmp_path)

    assert data["status_list"]["error"] == "1"
    assert data["status_list"]["pass"] == "1"
    assert data["total_tests"] == "3"


def test_teardown_output_is_kept_for_a_teardown_only_failure(tmp_path):
    # --report-logs failed reads the record's status, so the status has to be
    # settled before the output is collected
    _run(tmp_path, "--report-logs=failed")

    report = (tmp_path / "report" / "pytest_html_report.html").read_text(encoding="utf-8")
    assert "OUTPUT FROM THE TEARDOWN" in report
    assert "quiet pass" not in report
