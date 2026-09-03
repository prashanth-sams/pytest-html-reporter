"""Cover the screenshot arriving on the step it was taken for.

A failing test's picture used to be reachable from two places, and neither of
them said *where* in the test it was taken: the Screens column names the row,
and the gallery names the test. The Test Steps tab is the page that knows the
difference between one step and the next, so that is where the picture belongs
- on the step that threw, beside the error it explains.
"""

import os
import re
import subprocess
import sys
import textwrap


# A browser that costs nothing to drive. Anything answering
# get_screenshot_as_png() is one, which is the whole of the reporter's test for
# what can be photographed.
FAKE = '''
    import pytest
    from pytest_html_reporter import attach, step

    PNG = (b"\\x89PNG\\r\\n\\x1a\\n\\x00\\x00\\x00\\rIHDR\\x00\\x00\\x00\\x01\\x00\\x00\\x00"
           b"\\x01\\x08\\x02\\x00\\x00\\x00\\x90wS\\xde\\x00\\x00\\x00\\x0cIDATx\\x9cc```\\x00"
           b"\\x00\\x00\\x04\\x00\\x01\\xf6\\x178U\\x00\\x00\\x00\\x00IEND\\xaeB`\\x82")


    class FakeDriver:
        def get_screenshot_as_png(self):
            return PNG


    @pytest.fixture
    def driver():
        return FakeDriver()
'''


def _run(tmp_path, body, *args):
    """Run a generated suite and hand back the report page it wrote."""
    # Dedented apart: the preamble and the body are written at different
    # indentations here, and dedenting them together leaves the deeper one
    # indented by the difference.
    suite = textwrap.dedent(FAKE).lstrip() + textwrap.dedent(body)
    (tmp_path / "test_shots_in_steps.py").write_text(suite)

    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--html-report=./report", "-p", "no:cacheprovider"]
        + list(args),
        cwd=str(tmp_path), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        universal_newlines=True,
    )

    report = tmp_path / "report" / "pytest_html_report.html"
    assert report.is_file(), result.stdout

    return report.read_text(encoding="utf-8")


def _payload(page, test_name):
    """The step tree parked in the store for one test."""
    match = re.search(
        r'<div class="step-payload"[^>]*data-test="%s"[^>]*>(.*?)'
        r'(?=<div class="step-payload"|</div>\s*</div>\s*</div>\s*</div>)'
        % re.escape(test_name), page, re.S)

    return match.group(1) if match else ""


def _carrying(payload):
    """The title of every step that has a picture under it."""
    lines = re.findall(
        r'class="step-line step-line--\w+".*?class="step-line__title">(.*?)</span>(.*?)'
        r'(?=<div class="step-line |<div class="step-phase__none|</section>)',
        payload, re.S)

    return [re.sub(r"<[^>]+>", "", title).strip()
            for title, rest in lines if "step-shots" in rest]


def _phase(payload, phase):
    """One phase block of the tree."""
    match = re.search(r'data-phase="%s".*?(?=<section class="step-phase|$)' % phase, payload, re.S)

    return match.group(0) if match else ""


# --------------------------------------------------------------------------
# where the picture lands
# --------------------------------------------------------------------------

def test_the_picture_lands_on_the_step_that_threw(tmp_path):
    """The automatic capture runs from the teardown hook, with no step open at
    all - so the tree files it against the step carrying the error."""
    page = _run(tmp_path, '''
        def test_fails(driver):
            with step("Sign in"):
                pass
            with step("Check out"):
                with step("Charge the card"):
                    raise AssertionError("card declined")
    ''')

    assert _carrying(_payload(page, "test_fails")) == ["Charge the card"]


def test_the_message_and_the_picture_end_up_on_the_same_step(tmp_path):
    """They are two halves of one answer: what went wrong, and what it looked
    like when it did."""
    payload = _payload(_run(tmp_path, '''
        def test_fails(driver):
            with step("Charge the card"):
                raise AssertionError("card declined")
    '''), "test_fails")

    charge = payload[payload.index("Charge the card"):]

    assert "step-line__error" in charge
    assert "step-shots" in charge


def test_a_test_that_named_no_steps_shows_it_under_the_body(tmp_path):
    """Which is most tests. The body is where the test ran, and a picture with
    nowhere better to go is still worth having on the page."""
    payload = _payload(_run(tmp_path, '''
        def test_fails(driver):
            assert False
    '''), "test_fails")

    assert "step-shots" in _phase(payload, "call")
    assert "step-shots" not in _phase(payload, "setup")
    assert "step-shots" not in _phase(payload, "teardown")


def test_a_picture_taken_inside_a_step_says_so_itself(tmp_path):
    """`attach` mid-test knows which step is open, so this one needs no guess -
    and it works for a test that passed, where nothing threw."""
    payload = _payload(_run(tmp_path, '''
        def test_passes(driver):
            with step("Sign in"):
                pass
            with step("Look at the basket"):
                attach(data=driver.get_screenshot_as_png())
    '''), "test_passes")

    assert _carrying(payload) == ["Look at the basket"]


def test_the_tree_and_the_table_are_different_galleries(tmp_path):
    """The tab shows one test at a time, so arrowing across its pictures should
    stay inside the test being read rather than travel the whole run."""
    page = _run(tmp_path, '''
        def test_fails(driver):
            assert False
    ''')
    payload = _payload(page, "test_fails")

    assert 'data-fancybox="steps"' in payload
    assert 'data-fancybox="metrics"' not in payload
    assert 'data-fancybox="metrics"' in page


# --------------------------------------------------------------------------
# finding the browser at all
# --------------------------------------------------------------------------

def test_a_browser_the_test_never_named_is_still_photographed(tmp_path):
    """A pytest-bdd scenario takes no fixtures of its own: every step asks for
    what it needs while it runs, so the page never reaches `funcargs` and the
    capture had nothing to look at. Nothing said so - the run simply produced
    no picture. This is that shape without the dependency."""
    page = _run(tmp_path, '''
        def test_fails(request):
            request.getfixturevalue("driver")
            assert False
    ''')

    assert "pytest_screenshots/" in page
    assert "step-shots" in _phase(_payload(page, "test_fails"), "call")


def test_the_same_browser_is_not_photographed_twice(tmp_path):
    """It arrives twice now - named by the test and cached by the request - and
    two of one picture on a row is not two pictures."""
    page = _run(tmp_path, '''
        def test_fails(driver):
            assert False
    ''')

    assert len(re.findall(r'data-fancybox="metrics"', page)) == 1
