"""A Gherkin scenario that fails in front of a browser.

Run it and open the Test Steps tab::

    $ pytest tests/functional/test_gherkin_screenshot.py --html-report=./report

The `Then` step fails, the reporter photographs the page it was still holding,
and the picture is filed against that step rather than against the test as a
whole - so the tree answers "where did this go wrong" and "what did it look
like when it did" in the same place.

Nothing here says any of that. There is no screenshot code, no hook and no
conftest: a step function asks for pytest-playwright's ``page`` and the rest is
the reporter's own doing.

Its feature lives in ``ui_features/`` rather than beside the checkout one,
because ``scenarios("features")`` in test_gherkin.py binds every feature in
that folder to *that* module - and these steps are not defined there.
"""

import pytest

pytest.importorskip("pytest_bdd", reason="the Gherkin demo needs pytest-bdd")
pytest.importorskip("playwright.sync_api", reason="this scenario needs a browser")

from pytest_bdd import given, parsers, scenarios, then, when  # noqa: E402


scenarios("ui_features")


@given("the example page is open")
def _open(page):
    page.goto("https://example.com")


@when("the heading is read", target_fixture="heading")
def _read(page):
    return page.locator("h1").inner_text()


@then(parsers.parse('it reads "{expected}"'))
def _reads(heading, expected):
    # Fails on purpose: this is the step the screenshot has to land on.
    assert heading == expected
