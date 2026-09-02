"""Cover the screenshots nobody asked for.

A browser-driving suite has always had to write a hook of its own to get a
picture of the page a test failed on. It no longer does: the reporter is
already standing in the test's teardown, the browser is still in the test's
fixtures, and everything that hook did can be done from there.

Nothing here drives a real browser. A browser is recognised by what it can do,
so an object that answers ``get_screenshot_as_png`` is one as far as this is
concerned - which is exactly the property worth testing.
"""

import os
import re
import subprocess
import sys
import textwrap

import pytest

from pytest_html_reporter import screenshots


# --------------------------------------------------------------------------
# what counts as a browser
# --------------------------------------------------------------------------

PNG = b"\x89PNG\r\n\x1a\n"


class Selenium:
    def get_screenshot_as_png(self):
        return PNG


class Playwright:
    """A page. Playwright spells the call ``screenshot`` and hands back bytes."""

    def screenshot(self, **kwargs):
        return PNG


class Splinter:
    """A wrapper whose own screenshot() writes a file and returns its path.

    The bytes are behind ``driver``, and reading the return value of the
    wrapper's call as an image would put a file path in the report.
    """

    def __init__(self):
        self.driver = Selenium()

    def screenshot(self, name=None):
        return "/tmp/" + str(name) + ".png"


class Closed:
    """A driver whose session has gone. Every client raises here."""

    def get_screenshot_as_png(self):
        raise RuntimeError("no such session")


class Async:
    """Playwright's async API. The call hands back a coroutine, not an image."""

    async def screenshot(self):
        return PNG


def test_a_selenium_driver_is_photographed():
    assert screenshots.png(Selenium()) == PNG


def test_a_playwright_page_is_photographed():
    assert screenshots.png(Playwright()) == PNG


def test_a_wrapper_is_photographed_through_the_driver_it_wraps():
    """Not through its own screenshot(), which hands back a path."""
    assert screenshots.png(Splinter()) == PNG


def test_a_browser_that_raises_is_not_worth_failing_a_test_over():
    assert screenshots.png(Closed()) is None


def test_an_async_page_is_left_alone(recwarn):
    """There is nowhere here to await one, and an unawaited coroutine would be
    reported against the test as a warning of its own."""
    assert screenshots.png(Async()) is None

    assert [w for w in recwarn if "never awaited" in str(w.message)] == []


def test_a_mock_is_not_mistaken_for_a_browser():
    """A Mock answers every call there is, so it would be photographed on the
    strength of a method it does not have - and calling it records a call the
    test may be asserting on."""
    mock = pytest.importorskip("unittest.mock").MagicMock()

    assert screenshots.can_shoot(mock) is False


def test_a_fixture_that_is_not_a_browser_is_left_alone():
    assert screenshots.png(object()) is None
    assert screenshots.targets(object()) == []


# --------------------------------------------------------------------------
# reaching the page inside a context or a browser
# --------------------------------------------------------------------------

class Context:
    def __init__(self, *pages):
        self.pages = list(pages)


class Browser:
    def __init__(self, *contexts):
        self.contexts = list(contexts)


def test_a_context_is_photographed_through_its_pages():
    page = Playwright()

    assert screenshots.targets(Context(page)) == [page]


def test_a_browser_is_photographed_through_the_pages_inside_it():
    page = Playwright()

    assert screenshots.targets(Browser(Context(page))) == [page]


def test_a_context_holding_no_page_yields_nothing():
    assert screenshots.targets(Context()) == []


# --------------------------------------------------------------------------
# end to end, through a real pytest run
# --------------------------------------------------------------------------

# A fake browser, in the shape a suite would define one. Indented to match the
# bodies it is prepended to: _run dedents the two as one.
FAKE = """
        import pytest

        PNG = (b"\\x89PNG\\r\\n\\x1a\\n\\x00\\x00\\x00\\rIHDR\\x00\\x00\\x00\\x01\\x00\\x00\\x00"
               b"\\x01\\x08\\x02\\x00\\x00\\x00\\x90wS\\xde\\x00\\x00\\x00\\x0cIDATx\\x9cc```\\x00"
               b"\\x00\\x00\\x04\\x00\\x01\\xf6\\x178U\\x00\\x00\\x00\\x00IEND\\xaeB`\\x82")


        class FakeDriver:
            def get_screenshot_as_png(self):
                return PNG


        @pytest.fixture
        def driver():
            return FakeDriver()
"""


def _run(tmp_path, body, *args):
    """Run a generated suite and hand back its report page and pytest's output."""
    (tmp_path / "test_auto.py").write_text(textwrap.dedent(body).lstrip())

    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--html-report=./report", "-p", "no:cacheprovider"]
        + list(args),
        cwd=str(tmp_path),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )

    report = tmp_path / "report" / "pytest_html_report.html"
    assert report.is_file(), result.stdout

    return report.read_text(), result.stdout


def _captions(page):
    """The test behind each card in the gallery."""
    return re.findall(
        r'data-fancybox="images" data-caption="SUITE: .*? :: SCENARIO: (.*?)"', page)


def _images(tmp_path):
    directory = tmp_path / "report" / "pytest_screenshots"
    return sorted(os.listdir(str(directory))) if directory.is_dir() else []


def test_a_failing_test_is_photographed_with_no_hook_at_all(tmp_path):
    """The whole point: a suite that has never heard of this package.

    No conftest, no attach, no fixture of its own - just a browser the test was
    holding when it failed.
    """
    page, _ = _run(tmp_path, FAKE + '''
        def test_fails(driver):
            assert False
    ''')

    assert _captions(page) == ["test_fails"]
    assert len(_images(tmp_path)) == 1


def test_a_passing_test_is_not_photographed_by_default(tmp_path):
    """Photographing a green run is a lot of pictures of pages that were fine,
    and every one of them is a round trip to the browser."""
    page, _ = _run(tmp_path, FAKE + '''
        def test_passes(driver):
            assert True
    ''')

    assert _captions(page) == []
    assert _images(tmp_path) == []


def test_every_test_is_photographed_when_the_run_asks_for_it(tmp_path):
    page, _ = _run(tmp_path, FAKE + '''
        def test_passes(driver):
            assert True
    ''', "--report-screenshots=all")

    assert _captions(page) == ["test_passes"]


def test_nothing_is_photographed_when_the_run_turns_it_off(tmp_path):
    page, _ = _run(tmp_path, FAKE + '''
        def test_fails(driver):
            assert False
    ''', "--report-screenshots=none")

    assert _captions(page) == []
    assert _images(tmp_path) == []


def test_an_image_the_test_attached_is_kept_when_capture_is_off(tmp_path):
    """--report-screenshots is about the pictures nobody asked for. One handed
    to attach() was asked for, and is kept whatever that option says."""
    page, _ = _run(tmp_path, FAKE + '''
        from pytest_html_reporter import attach


        def test_fails(driver):
            attach(data=PNG)
            assert False
    ''', "--report-screenshots=none")

    assert _captions(page) == ["test_fails"]


def test_a_test_that_took_its_own_picture_is_not_photographed_again(tmp_path):
    """A suite that already calls attach() from a hook of its own would
    otherwise get the same page twice, once from each of us."""
    page, _ = _run(tmp_path, FAKE + '''
        from pytest_html_reporter import attach


        def test_fails(driver):
            attach(data=PNG)
            assert False
    ''')

    assert _captions(page) == ["test_fails"]
    assert len(_images(tmp_path)) == 1


def test_a_unittest_driver_is_found_on_the_test_itself(tmp_path):
    """unittest puts the browser on ``self`` in setUp rather than in a fixture,
    so there is no funcarg to find it in."""
    page, _ = _run(tmp_path, FAKE + '''
        import unittest


        class TestClass(unittest.TestCase):
            def setUp(self):
                self.driver = FakeDriver()

            def test_fails(self):
                assert False
    ''')

    assert _captions(page) == ["test_fails"]


def test_a_fixture_that_blew_up_after_the_browser_opened_is_photographed(tmp_path):
    """The test never ran, so nothing it could have written would have helped.

    A login fixture that fails is the ordinary shape of this, and the page the
    browser was left sitting on is the whole answer to why.
    """
    page, _ = _run(tmp_path, FAKE + '''
        @pytest.fixture
        def login(driver):
            raise RuntimeError("the login page never loaded")


        def test_never_runs(driver, login):
            assert True
    ''')

    assert _captions(page) == ["test_never_runs"]


def test_a_browser_named_something_else_is_still_found(tmp_path):
    """The fixture name is a hint, not the test. What makes it a browser is
    that it can hand over a picture."""
    page, _ = _run(tmp_path, FAKE + '''
        @pytest.fixture
        def chrome():
            return FakeDriver()


        def test_fails(chrome):
            assert False
    ''')

    assert _captions(page) == ["test_fails"]


def test_one_page_reached_through_three_fixtures_is_photographed_once(tmp_path):
    """Asking for the page, the context and the browser at once is the ordinary
    way to write a Playwright test, and all three lead to the same picture."""
    page, _ = _run(tmp_path, FAKE + '''
        class FakePage:
            def screenshot(self):
                return PNG


        class FakeContext:
            def __init__(self, page):
                self.pages = [page]


        @pytest.fixture
        def page():
            return FakePage()


        @pytest.fixture
        def context(page):
            return FakeContext(page)


        def test_fails(page, context):
            assert False
    ''')

    assert _captions(page) == ["test_fails"]
    assert len(_images(tmp_path)) == 1


def test_two_browsers_in_one_test_are_both_photographed(tmp_path):
    """A test driving two of them is comparing them, and one picture of the
    pair says nothing about which one went wrong."""
    page, _ = _run(tmp_path, FAKE + '''
        @pytest.fixture
        def other():
            return FakeDriver()


        def test_fails(driver, other):
            assert False
    ''')

    assert _captions(page) == ["test_fails", "test_fails"]
    assert len(_images(tmp_path)) == 2


def test_two_pictures_on_one_row_say_which_browser_each_came_from(tmp_path):
    """Only there. On the ordinary single-picture row the tooltip would say
    what the row already says."""
    page, _ = _run(tmp_path, FAKE + '''
        @pytest.fixture
        def other():
            return FakeDriver()


        def test_fails(driver, other):
            assert False
    ''')

    tips = re.findall(r'<a class="shot-thumb".*?title="(.*?)"', page, re.S)
    assert tips == ["test_fails \u2014 driver", "test_fails \u2014 other"]


def test_one_picture_on_a_row_is_named_by_the_test_alone(tmp_path):
    page, _ = _run(tmp_path, FAKE + '''
        def test_fails(driver):
            assert False
    ''')

    tips = re.findall(r'<a class="shot-thumb".*?title="(.*?)"', page, re.S)
    assert tips == ["test_fails"]


def test_a_browser_that_died_does_not_take_the_report_with_it(tmp_path):
    """The report has no picture of that one. It still has everything else."""
    page, output = _run(tmp_path, FAKE + '''
        class Dead:
            def get_screenshot_as_png(self):
                raise RuntimeError("no such session")


        @pytest.fixture
        def broken():
            return Dead()


        def test_fails(broken):
            assert False
    ''')

    assert _captions(page) == []
    assert "1 failed" in output
    assert "test_fails" in page
