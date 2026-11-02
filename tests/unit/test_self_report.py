"""Cover the report this suite writes about itself.

Many of these tests drive the plugin in-process and put back what they touched
on ConfigVars as their fixtures are finalized - after the running reporter has
written the test's own status, name and suite there, and before it reads them
back to build the record. conftest.py puts the reporter's values back in
between. Nothing a test asserts about itself could catch that going wrong: every
assertion still passed while the page filed the test under another test's name
and outcome. So the second test here reads the record the running reporter
built for the first.
"""

import pytest

from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.html_reporter import HTMLReporter

# What the test before is made certain to have left, rather than whatever the
# suite happened to run last: a pass with no error would hide a status put back.
_LEFT_BEFORE = {
    "_suite_name": "tests/unit/test_before.py",
    "_test_name": "test_before",
    "_test_status": "FAIL",
    "_current_error": "AssertionError: the test before",
    "_duration": 99.0,
}


@pytest.fixture
def _puts_back_what_the_test_before_left():
    """The suite's isolation fixtures, reduced to what they do to the running
    reporter: on the way out, they put back what was there on the way in."""
    yield
    for name, value in _LEFT_BEFORE.items():
        setattr(ConfigVars, name, value)


def test_drives_the_plugin_and_puts_its_state_back(_puts_back_what_the_test_before_left):
    ConfigVars._test_status = "ERROR"


def test_the_test_before_is_still_recorded_as_itself(request):
    reporter = next((plugin for plugin in request.config.pluginmanager.get_plugins()
                     if isinstance(plugin, HTMLReporter)), None)
    if reporter is None:
        pytest.skip("the plugin is not reporting on this run")

    nodeid = request.node.parent.nodeid + "::test_drives_the_plugin_and_puts_its_state_back"
    records = [record for record in reporter._records if record["nodeid"] == nodeid]
    if not records:
        pytest.skip("the test before did not run in this process")

    record, = records
    assert record["suite_name"] == request.node.parent.nodeid
    assert record["test_name"] == "test_drives_the_plugin_and_puts_its_state_back"
    assert record["status"] == "PASS"
    assert record["message"] == ""
    assert record["duration"] != _LEFT_BEFORE["_duration"]
