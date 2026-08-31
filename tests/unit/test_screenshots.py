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


def test_a_passing_test_does_not_lend_its_screenshot_to_the_next_failure(tmp_path):
    """An image nobody can claim is dropped rather than left in the global.

    Kept, it would be handed to the next failing test - which would then be
    illustrated by a screenshot of a test it never ran.
    """
    page, _ = _run(tmp_path, PNG + '''
        from pytest_html_reporter import attach


        def test_passes_and_attaches():
            attach(data=PNG)


        def test_fails_and_attaches_nothing():
            assert False
    ''')

    assert _captions(page) == []
    assert _images(tmp_path) == []


def test_dropping_a_screenshot_says_so(tmp_path):
    """Silence is what sent people looking for the bug in their own code."""
    _, output = _run(tmp_path, PNG + '''
        from pytest_html_reporter import attach


        def test_passes_and_attaches():
            attach(data=PNG)
    ''')

    assert "attached a screenshot but did not fail" in output


def test_the_drop_warning_is_raised_once(tmp_path):
    """A suite that attaches unconditionally must not drown in warnings."""
    _, output = _run(tmp_path, PNG + '''
        from pytest_html_reporter import attach


        def test_one():
            attach(data=PNG)


        def test_two():
            attach(data=PNG)


        def test_three():
            attach(data=PNG)
    ''')

    assert output.count("attached a screenshot but did not fail") == 1


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


def test_a_failure_that_attached_nothing_gets_no_screenshot(tmp_path):
    """The failing test attaches nothing; the passing one before it did."""
    page, _ = _run(tmp_path, PNG + '''
        from pytest_html_reporter import attach


        def test_passes_and_attaches():
            attach(data=PNG)


        def test_fails_quietly():
            assert False


        def test_shot():
            attach(data=PNG)
            assert False
    ''')

    assert _captions(page) == ["test_shot"]
