import unittest

import pytest

pytest.importorskip("selenium")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

from pytest_html_reporter import attach


class TestClass(unittest.TestCase):
    """The ``unittest`` flavour of screenshot-on-failure.

    ``tearDown`` is where a unittest suite attaches: unittest runs it as part
    of the test call itself, so the driver is still open. The plain-pytest
    tests capture theirs from a hook instead - see conftest.py.

    Has to be run through pytest: ``attach`` writes relative to a base path
    that only exists once the reporter plugin has been configured.
    """

    def setUp(self):
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1280,800")

        self.driver = webdriver.Chrome(options=options)
        self.driver.get("https://example.com")

    def test_heading(self):
        heading = self.driver.find_element(By.CSS_SELECTOR, "h1").text
        self.assertEqual(heading, "Example Domain")

    def test_heading_mismatch(self):
        # Fails on purpose: screenshots are only captured for failures.
        heading = self.driver.find_element(By.CSS_SELECTOR, "h1").text
        self.assertEqual(heading, "Not the heading")

    def tearDown(self):
        # Before quitting - a closed driver has nothing left to photograph.
        if self._test_failed():
            attach(data=self.driver.get_screenshot_as_png())

        self.driver.quit()

    def _test_failed(self):
        outcome = self._outcome

        # Python < 3.11 collected this test's exceptions on the outcome itself.
        if hasattr(outcome, "errors"):
            return any(error for _, error in outcome.errors)

        # From 3.11 on tearDown runs inside its own part executor, which resets
        # outcome.success to True before this is reached - so it is the result
        # object, not the outcome, that still knows the test went wrong. Under
        # pytest that object is its own TestCaseFunction.
        return bool(getattr(outcome.result, "_excinfo", None))
