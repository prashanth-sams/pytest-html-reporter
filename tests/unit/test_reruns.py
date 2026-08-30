"""Cover how a retried test is reported.

pytest-rerunfailures runs the whole setup/call/teardown protocol again for every
retry, so the reporter sees a retried test once per attempt. Only the attempt
that stuck belongs in the report; the rest are the rerun count. The budget can
come from --reruns, the ini key or @pytest.mark.flaky(reruns=n) - and
--only-rerun can cut the retries short - so the reporter counts attempts rather
than trusting any one of those numbers.
"""

import json
import os
import subprocess
import sys
import textwrap

import pytest

from pytest_html_reporter.html_reporter import HTMLReporter

pytest.importorskip("pytest_rerunfailures")


class _FakePluginManager:
    def __init__(self, plugins=()):
        self._plugins = set(plugins)

    def hasplugin(self, name):
        return name in self._plugins


class _FakeConfig:
    def __init__(self, plugins=("rerunfailures",)):
        self.pluginmanager = _FakePluginManager(plugins)

    def getoption(self, name, default=None):
        return default

    def getini(self, name):
        raise ValueError(name)


def _reporter(**kwargs):
    return HTMLReporter(".", "", _FakeConfig(**kwargs))


def _record(name, status, index=0, worker="", **kwargs):
    record = {
        "suite_name": "tests/test_a.py",
        "test_name": name,
        "nodeid": "tests/test_a.py::" + name,
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


# --------------------------------------------------------------------------
# collapsing attempts
# --------------------------------------------------------------------------

def test_a_test_that_never_ran_twice_is_stored_as_is():
    reporter = _reporter()

    reporter.store_test_record(_record("test_one", "PASS"))
    reporter.store_test_record(_record("test_two", "FAIL", index=1))

    assert [(r["test_name"], r["rerun"]) for r in reporter._records] == [
        ("test_one", 0), ("test_two", 0),
    ]


def test_every_attempt_of_a_failing_test_collapses_into_one_record():
    reporter = _reporter()

    # One test, six attempts: the original and five retries.
    for _ in range(6):
        reporter.store_test_record(_record("test_one", "FAIL"))

    assert len(reporter._records) == 1
    assert reporter._records[0]["status"] == "FAIL"
    assert reporter._records[0]["rerun"] == 5


def test_the_attempt_that_stuck_is_the_one_reported():
    reporter = _reporter()

    reporter.store_test_record(_record("test_one", "FAIL", message="first"))
    reporter.store_test_record(_record("test_one", "FAIL", message="second"))
    reporter.store_test_record(_record("test_one", "PASS"))

    assert [(r["status"], r["rerun"]) for r in reporter._records] == [("PASS", 2)]


def test_a_retry_keeps_the_screenshot_of_the_attempt_it_replaces():
    reporter = _reporter()
    shot = {"name": "1", "suite": "test_a", "test": "test_one", "error": "boom"}

    reporter.store_test_record(_record("test_one", "FAIL", screenshot=shot))
    reporter.store_test_record(_record("test_one", "PASS"))

    assert reporter._records[0]["screenshot"] == shot


def test_a_retry_that_took_its_own_screenshot_keeps_that_one():
    reporter = _reporter()
    first = {"name": "1", "suite": "test_a", "test": "test_one", "error": "boom"}
    second = {"name": "2", "suite": "test_a", "test": "test_one", "error": "boom again"}

    reporter.store_test_record(_record("test_one", "FAIL", screenshot=first))
    reporter.store_test_record(_record("test_one", "FAIL", screenshot=second))

    assert reporter._records[0]["screenshot"] == second


def test_a_retried_test_keeps_its_place_in_collection_order():
    reporter = _reporter()

    reporter.store_test_record(_record("test_one", "FAIL", index=0))
    reporter.store_test_record(_record("test_two", "PASS", index=1))
    reporter.store_test_record(_record("test_one", "PASS", index=0))

    assert [r["test_name"] for r in reporter._records] == ["test_one", "test_two"]
    assert reporter._records[0]["index"] == 0


def test_without_rerunfailures_a_repeated_nodeid_is_never_swallowed():
    # Nothing else should silently lose a test just for sharing a nodeid.
    reporter = _reporter(plugins=())

    reporter.store_test_record(_record("test_one", "PASS"))
    reporter.store_test_record(_record("test_one", "PASS"))

    assert len(reporter._records) == 2


def test_records_merged_from_a_worker_keep_the_reruns_they_arrived_with():
    controller = _reporter()
    controller.store_test_record(_record("test_one", "FAIL", worker="gw0", rerun=2))

    # The same test finished elsewhere after two attempts of its own.
    controller.store_test_record(_record("test_one", "PASS", worker="gw1", rerun=1))

    assert len(controller._records) == 1
    # 2 superseded + 1 superseded + the attempt that was itself replaced.
    assert controller._records[0]["rerun"] == 4


# --------------------------------------------------------------------------
# end to end
# --------------------------------------------------------------------------

def _run(tmp_path, body, *args):
    (tmp_path / "test_flaky.py").write_text(textwrap.dedent(body).lstrip())

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


MARKER = """
    import pytest, unittest

    class MainTest(unittest.TestCase):
        @pytest.mark.flaky(reruns=5, reruns_delay=0)
        def test_001(self):
            assert 1 == 2
"""


def test_the_flaky_marker_is_counted_as_reruns_not_failures(tmp_path):
    # https://github.com/prashanth-sams/pytest-html-reporter/issues/212
    data = _run(tmp_path, MARKER)

    assert data["status_list"]["fail"] == "1"
    assert data["status_list"]["rerun"] == "5"


def test_the_reruns_option_is_counted_as_reruns(tmp_path):
    data = _run(tmp_path, """
        def test_001(): assert 1 == 2
    """, "--reruns", "5")

    assert data["status_list"]["fail"] == "1"
    assert data["status_list"]["rerun"] == "5"


def test_a_marker_that_disagrees_with_the_option_still_adds_up(tmp_path):
    # The marker wins over --reruns, so the report must not assume either.
    data = _run(tmp_path, MARKER, "--reruns", "1")

    assert data["status_list"]["fail"] == "1"
    assert data["status_list"]["rerun"] == "5"


def test_a_test_that_passes_on_a_retry_is_reported_as_passed(tmp_path):
    data = _run(tmp_path, """
        import pytest

        attempts = []

        @pytest.mark.flaky(reruns=5, reruns_delay=0)
        def test_001():
            attempts.append(1)
            assert len(attempts) >= 3
    """)

    assert data["status_list"]["pass"] == "1"
    assert data["status_list"]["fail"] == "0"
    assert data["status_list"]["rerun"] == "2"
