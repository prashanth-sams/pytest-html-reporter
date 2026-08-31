"""Screenshot-on-failure wiring for the browser tests.

The reporter builds a test's record from its own ``pytest_runtest_teardown``,
which waits for the fixture finalizers, so ``attach`` can be called from a
fixture's teardown as well as from here. This hook is used instead because it
needs no fixture of its own: the browser is already in ``item.funcargs``.

Hooks are only picked up from conftest files - pytest never registers a test
module as a plugin - so this cannot be moved into the test modules themselves.

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
