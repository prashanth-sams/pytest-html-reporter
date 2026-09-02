"""The Playwright flavour of screenshot-on-failure - with nothing wired up.

Same as the Selenium suite beside it, and for the same reason: the reporter
recognises a browser by what it can do rather than by what it is, so
Playwright's ``page.screenshot()`` is found exactly the way Selenium's
``get_screenshot_as_png()`` is. This file is an ordinary Playwright test and
nothing else.

Needs ``pip install pytest-playwright`` and ``playwright install chromium``.
"""

import pytest

pytest.importorskip("playwright.sync_api")


@pytest.fixture(autouse=True)
def example(page):
    """Parks pytest-playwright's own ``page`` on a page the assertions read.

    Navigating from a fixture rather than wrapping ``page`` in a new one keeps
    the name in ``item.funcargs``, which is where conftest.py reaches for it.
    """
    page.goto("https://example.com")


class TestClass:
    def test_heading(self, page):
        assert page.locator("h1").inner_text() == "Example Domain"

    def test_heading_mismatch(self, page):
        # Fails on purpose. Screenshots are only captured for failures, so this
        # is the test that puts one in the report - and it says nothing about
        # screenshots to do it.
        assert page.locator("h1").inner_text() == "Not the heading"
