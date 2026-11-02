"""Keep the report this suite writes about itself true to what ran.

The plugin reports on its own test run, and a good many of these tests drive
that same plugin in-process. Both keep the test in progress on ConfigVars, so
the tests isolate what they touch with fixtures that save it on the way in and
put it back on the way out. That is right for everything except what the
running reporter has already written about the test by then: it sets the test's
status, error and suite as the call is reported, and its name and duration as
teardown starts, then reads them back to build the record only after the test's
fixtures have been finalized. Put back in between, they handed the record
whatever the test before had left - one failure just ahead of
test_teardown_failures.py listed all twelve of its tests as failed, and all
twenty tests in test_reporter_assets.py were filed under the name of the test
that ran before them.
"""

import pytest

from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.html_reporter import HTMLReporter

# The record reads _xfail_reason too, but that one is the reporter's before the
# test runs rather than after: it is cleared as the test is set up, before any
# fixture saves it, and set again only for a test expected to fail. Guarded
# here, a test driving an xfail through the plugin in-process would hand its
# own record that test's reason.
_WRITTEN_ABOUT_THE_TEST = ("_suite_name", "_test_name", "_test_status", "_current_error", "_duration")


@pytest.hookimpl(hookwrapper=True, trylast=True)
def pytest_runtest_teardown(item):
    # trylast makes this the innermost wrapper, so it starts after the
    # reporter's own has named and timed the test, and finishes before that one
    # builds the record.
    written = {name: getattr(ConfigVars, name) for name in _WRITTEN_ABOUT_THE_TEST}

    yield

    # Only while a reporter is building records from them: without one, the
    # fixtures putting these back is exactly the isolation they were written for.
    if any(isinstance(plugin, HTMLReporter) for plugin in item.config.pluginmanager.get_plugins()):
        for name, value in written.items():
            setattr(ConfigVars, name, value)
