"""Screenshot-on-failure wiring for the browser tests.

The reporter turns a finished test into a record from its own
``pytest_runtest_teardown``, which runs *before* pytest finalizes the test's
fixtures. Attaching from a fixture's teardown is therefore too late - the image
is stored but no record is left to claim it, and the shot silently never
reaches the report. The call phase's report hook is early enough.
"""

import pytest

from pytest_html_reporter import attach


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()

    if report.when != "call" or not report.failed:
        return

    driver = item.funcargs.get("driver")
    if driver is not None:
        attach(data=driver.get_screenshot_as_png())
