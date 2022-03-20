from selenium import webdriver
import unittest
from pytest_html_reporter import attach
import pytest


@pytest.mark.skip(reason="skipping screenshot tests")
class TestClass(unittest.TestCase):
    def __init__(self, driver):
        super().__init__(driver)

    def setUp(self):
        global driver
        self.driver = webdriver.Chrome()

    def test_demo(self):
        self.driver.get("http://devopsqa.wordpress.com/")
        assert 5 == 4

    def test_demo_2(self):
        self.driver.get("http://devopsqa.wordpress.com/")
        assert 5 == 4

    def test_demo_3(self):
        self.driver.get("http://devopsqa.wordpress.com/")
        assert 5 == 4

    def test_demo_4(self):
        self.driver.get("http://devopsqa.wordpress.com/")
        assert 5 == 4

    def test_demo_5(self):
        self.driver.get("http://devopsqa.wordpress.com/")
        assert 5 == 4

    def test_demo_6(self):
        self.driver.get("http://devopsqa.wordpress.com/")
        assert 5 == 4

    def test_demo_7(self):
        self.driver.get("http://devopsqa.wordpress.com/")
        assert 5 == 4

    def test_demo_8(self):
        self.driver.get("http://devopsqa.wordpress.com/")
        assert 5 == 4

    def test_demo_9(self):
        self.driver.get("http://devopsqa.wordpress.com/")
        assert 5 == 4

    def tearDown(self):
        self.screenshot_on_failure()
        self.driver.close()
        self.driver.quit()

    def screenshot_on_failure(self):
        for self._testMethodName, error in self._outcome.errors:
            if error:
                attach(data=self.driver.get_screenshot_as_png())


if __name__ == '__main__':
    unittest.main()