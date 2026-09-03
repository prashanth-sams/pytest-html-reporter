"""Cover how a pytest report becomes one of the statuses the report shows.

Every other test of this decision drives a real suite in a subprocess and reads
the page at the end, which proves the common cases and is slow enough that the
uncommon ones are never asked for: an xfail that passed anyway, a failure in a
fixture rather than in the test, a skip carrying a reason, an error whose text
has to survive being cut down to the "E   " lines.

pytest_runtest_makereport is a hookwrapper, so it is driven here the way pytest
drives it - started, then handed the outcome - which is the only way to reach
the classification without a subprocess around it.
"""

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


class _Report:
    """A pytest TestReport, as much of one as the hook reads."""

    def __init__(self, when="call", outcome="passed", longreprtext="",
                 nodeid="tests/test_cart.py::test_add", duration=0.01,
                 wasxfail=None, longrepr=None, sections=()):
        self.when = when
        self.nodeid = nodeid
        self.duration = duration
        self.sections = list(sections)
        self.longreprtext = longreprtext
        self.longrepr = longrepr if longrepr is not None else (longreprtext or None)

        self.passed = outcome == "passed"
        self.failed = outcome == "failed"
        self.skipped = outcome == "skipped"

        if wasxfail is not None:
            self.wasxfail = wasxfail


class _Outcome:
    def __init__(self, report):
        self._report = report

    def get_result(self):
        return self._report


@pytest.fixture(autouse=True)
def _isolate():
    saved = (ConfigVars._test_status, ConfigVars._current_error,
             ConfigVars._suite_name, ConfigVars._xfail_reason)
    yield
    (ConfigVars._test_status, ConfigVars._current_error,
     ConfigVars._suite_name, ConfigVars._xfail_reason) = saved


def _classify(report):
    """Drive the hookwrapper the way pytest does, and read what it decided."""
    reporter = HTMLReporter(".", "", _FakeConfig())

    ConfigVars._test_status = None
    ConfigVars._current_error = None

    hook = reporter.pytest_runtest_makereport(item=None, call=None)
    next(hook)
    try:
        hook.send(_Outcome(report))
    except StopIteration:
        pass

    return ConfigVars._test_status, ConfigVars._current_error, reporter


# ------------------------------------------------------------------ passing ---

def test_a_test_that_passed_is_a_pass_carrying_no_error():
    status, error, _ = _classify(_Report(when="call", outcome="passed"))

    assert status == "PASS"
    assert error == ""


def test_an_xfail_that_passed_anyway_is_an_xpass():
    """The marker said it would fail and it did not, which is worth its own
    colour - a green row would hide that the marker is now wrong."""
    status, error, _ = _classify(
        _Report(when="call", outcome="passed", wasxfail="known bug #12"))

    assert status == "xPASS"
    assert error == ""


def test_a_passing_setup_does_not_overwrite_the_tests_own_status():
    """Only the call phase says how a test went; setup passing says nothing."""
    status, _, _ = _classify(_Report(when="setup", outcome="passed"))

    assert status is None


# ------------------------------------------------------------------ failing ---

def test_a_failed_call_is_a_failure_carrying_the_assertion():
    report = _Report(when="call", outcome="failed",
                     longreprtext="def test_add():\n>       assert 1 == 2\n"
                                  "E       assert 1 == 2")

    status, error, _ = _classify(report)

    assert status == "FAIL"
    assert "assert 1 == 2" in error


def test_only_the_e_lines_of_a_traceback_are_kept():
    """The source and the frames are noise on a row; the raised line is not."""
    report = _Report(when="call", outcome="failed",
                     longreprtext="tests/test_cart.py:4: in test_add\n"
                                  "    cart.add()\n"
                                  "E   ValueError: no such item")

    _, error, _ = _classify(report)

    assert "ValueError: no such item" in error
    assert "cart.add()" not in error


def test_a_failure_with_no_representation_carries_no_error():
    status, error, _ = _classify(
        _Report(when="call", outcome="failed", longrepr=None, longreprtext=""))

    assert status == "FAIL"
    assert error is None


def test_an_xfail_marker_on_a_test_that_failed_the_call_is_an_xpass():
    """wasxfail on a failed call is pytest reporting the strict-xfail case."""
    status, _, _ = _classify(
        _Report(when="call", outcome="failed", wasxfail="known bug #12",
                longreprtext="E   assert 1 == 2"))

    assert status == "xPASS"


# ------------------------------------------------------------------- errors ---

def test_a_failure_outside_the_call_phase_is_an_error_not_a_failure():
    """A fixture that blew up did not run the test at all, and a row that says
    FAIL sends people reading a test that never executed."""
    report = _Report(when="setup", outcome="failed",
                     longreprtext="ERROR at setup of test_add\n"
                                  "E   RuntimeError: no database")

    status, error, _ = _classify(report)

    assert status == "ERROR"
    assert "RuntimeError: no database" in error


def test_an_error_keeps_the_whole_traceback_rather_than_the_e_lines():
    """A fixture failure is usually explained by the frames above it."""
    report = _Report(when="teardown", outcome="failed",
                     longreprtext="conftest.py:9: in _db\n"
                                  "    connect()\n"
                                  "E   RuntimeError: gone")

    _, error, _ = _classify(report)

    assert "connect()" in error
    assert "RuntimeError: gone" in error


def test_an_error_with_nothing_to_show_is_still_an_error():
    status, error, _ = _classify(
        _Report(when="setup", outcome="failed", longrepr=None, longreprtext=""))

    assert status == "ERROR"
    assert error is None


# -------------------------------------------------------------------- skips ---

def test_a_skipped_test_is_a_skip_carrying_its_reason():
    report = _Report(when="setup", outcome="skipped",
                     longreprtext="Skipped: needs a database")

    status, error, _ = _classify(report)

    assert status == "SKIP"
    assert "needs a database" in error


def test_a_known_bug_that_failed_as_expected_is_an_xfail():
    report = _Report(when="call", outcome="skipped", wasxfail="known bug #12",
                     longreprtext="E   assert 1 == 2")

    status, error, _ = _classify(report)

    assert status == "xFAIL"
    assert "assert 1 == 2" in error


def test_an_xfail_keeps_only_the_e_lines_the_way_a_failure_does():
    report = _Report(when="call", outcome="skipped", wasxfail="bug",
                     longreprtext="tests/test_cart.py:4: in test_add\n"
                                  "    cart.add()\n"
                                  "E   ValueError: nope")

    _, error, _ = _classify(report)

    assert "ValueError: nope" in error
    assert "cart.add()" not in error


def test_an_xfail_with_nothing_to_show_is_still_an_xfail():
    status, error, _ = _classify(
        _Report(when="call", outcome="skipped", wasxfail="bug",
                longrepr=None, longreprtext=""))

    assert status == "xFAIL"
    assert error is None


def test_a_skip_with_no_reason_recorded_is_still_a_skip():
    status, error, _ = _classify(
        _Report(when="setup", outcome="skipped", longrepr=None, longreprtext=""))

    assert status == "SKIP"
    assert error is None


# ------------------------------------------------------- what else it reads ---

def test_the_suite_is_taken_from_the_nodeid():
    _classify(_Report(nodeid="tests/unit/test_cart.py::TestCart::test_add"))

    assert ConfigVars._suite_name == "tests/unit/test_cart.py"


def test_the_reason_a_known_bug_was_expected_to_fail_is_kept_for_the_xml():
    """The page shows the assertion; a JUnit collector shows the reason."""
    _classify(_Report(when="call", outcome="skipped", wasxfail="known bug #12"))

    assert ConfigVars._xfail_reason == "known bug #12"


def test_an_imperative_xfail_with_no_reason_leaves_the_field_empty():
    _classify(_Report(when="call", outcome="skipped", wasxfail=""))

    assert ConfigVars._xfail_reason == ""


@pytest.mark.parametrize("phase", ["setup", "call", "teardown"])
def test_each_phase_records_its_own_time(phase):
    """A test with no steps of its own still says where its time went."""
    _, _, reporter = _classify(_Report(when=phase, duration=0.25))

    assert reporter._phase_ms[phase] == 250


def test_a_phase_pytest_does_not_time_is_not_recorded():
    _, _, reporter = _classify(_Report(when="collect", duration=0.25))

    assert reporter._phase_ms == {}


def test_captured_output_is_collected_as_the_phases_go_by():
    """Setup, call and teardown each report their own, so no single report has
    the whole picture."""
    _, _, reporter = _classify(
        _Report(when="call", sections=[("Captured stdout call", "hello")]))

    assert reporter._log_sections
