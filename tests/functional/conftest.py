"""Screenshot-on-failure wiring for the browser tests.

The reporter turns a finished test into a record from its own
``pytest_runtest_teardown``, which runs *before* pytest finalizes the test's
fixtures. Attaching from a fixture's teardown is therefore too late - the image
is stored but no record is left to claim it, and the shot silently never
reaches the report. The call phase's report hook is early enough.

``attach`` wants PNG bytes, not a browser, so one hook serves every framework:
all that changes is the name the handle goes by and the call that photographs
it.
"""

import pytest

from pytest_html_reporter import attach

CAPTURE = {
    "driver": lambda driver: driver.get_screenshot_as_png(),  # Selenium
    "page": lambda page: page.screenshot(),  # Playwright
}


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()

    if report.when != "call" or not report.failed:
        return

    for name, capture in CAPTURE.items():
        handle = item.funcargs.get(name)
        if handle is not None:
            attach(data=capture(handle))
            return
