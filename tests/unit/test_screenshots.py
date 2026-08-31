"""Cover which test an attached screenshot ends up on.

``attach`` hands the reporter an image through a global, so the two things that
can go wrong are timing and ownership: the image has to be attached while the
test that took it is still being recorded, and an image nobody can claim must
not be left lying around for the next test to pick up.
"""

import os
import re
import subprocess
import sys
import textwrap


# A 1x1 png, so the suites below need no browser to have something to attach.
# Indented to match the bodies it is prepended to: _run dedents the two as one.
PNG = """
        PNG = (b"\\x89PNG\\r\\n\\x1a\\n\\x00\\x00\\x00\\rIHDR\\x00\\x00\\x00\\x01\\x00\\x00\\x00"
               b"\\x01\\x08\\x02\\x00\\x00\\x00\\x90wS\\xde\\x00\\x00\\x00\\x0cIDATx\\x9cc```\\x00"
               b"\\x00\\x00\\x04\\x00\\x01\\xf6\\x178U\\x00\\x00\\x00\\x00IEND\\xaeB`\\x82")
"""


def _run(tmp_path, body, conftest=None, *args):
    """Run a generated suite and hand back its report page and pytest's output.

    A hook belongs in `conftest`: pytest only registers conftest files as
    plugins, so a pytest_runtest_makereport defined in a test module is never
    called at all.
    """
    (tmp_path / "test_shots.py").write_text(textwrap.dedent(body).lstrip())

    if conftest is not None:
        (tmp_path / "conftest.py").write_text(textwrap.dedent(conftest).lstrip())

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
    """The test name the report prints under each screenshot in the gallery."""
    return re.findall(r'data-caption="SUITE: .*? :: SCENARIO: (.*?)"', page)


def _tile_captions(page):
    """The line each gallery tile prints under the suite name."""
    return re.findall(r'<strong>.*?</strong><br />\n\s*(.*?)\n\s*</p>', page, re.S)


def _images(tmp_path):
    directory = tmp_path / "report" / "pytest_screenshots"
    return sorted(os.listdir(str(directory))) if directory.is_dir() else []


HOOK = """
    import pytest


    @pytest.hookimpl(tryfirst=True, hookwrapper=True)
    def pytest_runtest_makereport(item, call):
        outcome = yield
        rep = outcome.get_result()
        setattr(item, "rep_" + rep.when, rep)
"""


def test_a_screenshot_attached_from_a_fixture_teardown_reaches_the_report(tmp_path):
    """The recipe everyone writes first: attach from an autouse fixture.

    The reporter builds its record from its own teardown hook, so this only
    works because that hook now waits for the fixture finalizers to run.
    """
    page, _ = _run(tmp_path, PNG + '''
        import pytest
        from pytest_html_reporter import attach


        @pytest.fixture(autouse=True)
        def shot(request):
            yield
            if request.node.rep_call.failed:
                attach(data=PNG)


        def test_fails():
            assert False
    ''', HOOK)

    assert _captions(page) == ["test_fails"]


def test_a_screenshot_attached_from_the_makereport_hook_still_reaches_the_report(tmp_path):
    """The other documented recipe has to keep working."""
    page, _ = _run(tmp_path, PNG + '''
        def test_fails():
            assert False
    ''', PNG + '''
        import pytest
        from pytest_html_reporter import attach


        @pytest.hookimpl(hookwrapper=True)
        def pytest_runtest_makereport(item, call):
            outcome = yield
            rep = outcome.get_result()
            if rep.when == "call" and rep.failed:
                attach(data=PNG)
    ''')

    assert _captions(page) == ["test_fails"]


def test_a_passing_test_keeps_its_screenshot(tmp_path):
    """An attached image is kept whatever the test did, not only on failure."""
    page, _ = _run(tmp_path, PNG + '''
        from pytest_html_reporter import attach


        def test_passes():
            attach(data=PNG)
    ''')

    assert _captions(page) == ["test_passes"]
    assert len(_images(tmp_path)) == 1


def test_a_tile_with_no_error_says_how_the_test_ended(tmp_path):
    """A passing tile would otherwise carry a blank caption.

    The status has to be read out of the tile itself: the word "PASS" is all
    over the page already, in the totals and in every row of the table.
    """
    page, _ = _run(tmp_path, PNG + '''
        from pytest_html_reporter import attach


        def test_passes():
            attach(data=PNG)
    ''')

    assert _tile_captions(page) == ["PASS"]


def test_a_screenshot_is_not_lent_to_the_next_test(tmp_path):
    """Each image belongs to the test that attached it, and to no other.

    The failing test here attaches nothing, so it must show nothing - rather
    than being illustrated with the passing test's picture.
    """
    page, _ = _run(tmp_path, PNG + '''
        from pytest_html_reporter import attach


        def test_shoots():
            attach(data=PNG)


        def test_quiet_fail():
            assert False
    ''')

    assert _captions(page) == ["test_shoots"]
    assert len(_images(tmp_path)) == 1


def test_each_failure_keeps_its_own_screenshot(tmp_path):
    """Two failures, two images - neither test borrowing the other's."""
    page, _ = _run(tmp_path, PNG + '''
        from pytest_html_reporter import attach


        def test_fail_one():
            attach(data=PNG)
            assert False


        def test_fail_two():
            attach(data=PNG)
            assert False
    ''')

    assert sorted(_captions(page)) == ["test_fail_one", "test_fail_two"]
    assert len(_images(tmp_path)) == 2


def test_a_test_that_attached_nothing_gets_no_screenshot(tmp_path):
    """Only the tests that actually attached appear in the gallery."""
    page, _ = _run(tmp_path, PNG + '''
        from pytest_html_reporter import attach


        def test_quiet_pass():
            assert True


        def test_quiet_fail():
            assert False


        def test_shot():
            attach(data=PNG)
            assert False
    ''')

    assert _captions(page) == ["test_shot"]
    assert len(_images(tmp_path)) == 1
