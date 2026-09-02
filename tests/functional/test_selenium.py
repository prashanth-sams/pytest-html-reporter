"""The plain-pytest flavour of screenshot-on-failure - with nothing wired up.

There is no conftest here, no hook and no call to ``attach``: the reporter
photographs the driver itself when a test fails, because the driver is in the
test's own fixtures and the reporter is already standing in its teardown.

Needs ``pip install selenium`` and a local Chrome; Selenium Manager
resolves the matching chromedriver itself.
"""

import pytest

pytest.importorskip("selenium")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By


@pytest.fixture
def driver():
    """A headless Chrome parked on a page the assertions below can read.

    Selenium Manager resolves the matching chromedriver itself, so this needs
    nothing installed beyond Chrome.
    """
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1280,800")

    driver = webdriver.Chrome(options=options)
    driver.get("https://example.com")

    yield driver

    driver.quit()


class TestClass:
    def test_heading(self, driver):
        assert driver.find_element(By.CSS_SELECTOR, "h1").text == "Example Domain"

    def test_heading_mismatch(self, driver):
        # Fails on purpose. Screenshots are only captured for failures, so this
        # is the test that puts one in the report - and it says nothing about
        # screenshots to do it.
        assert driver.find_element(By.CSS_SELECTOR, "h1").text == "Not the heading"
