"""Cover the captured output a test carries into the report.

pytest hands stdout, stderr and logging output to the reporter as report
sections, one set per phase. What matters here is that all three phases reach
the page, that a retried test shows the attempt that was reported rather than
the ones it superseded, and that a chatty test cannot run away with the file.
"""

import os
import re
import subprocess
import sys
import textwrap

import pytest


SUITE = """
    import logging
    import sys

    import pytest

    log = logging.getLogger(__name__)


    @pytest.fixture
    def prepared():
        print("setting up")
        yield "ready"
        print("cleaning up")


    def test_talks(prepared):
        print("hello from stdout")
        print("and from stderr", file=sys.stderr)
        log.warning("a warning while the test ran")
        assert prepared == "ready"


    def test_fails_loudly():
        print("about to fail")
        assert 1 == 2


    def test_says_nothing():
        assert True
"""


def _run(tmp_path, body=SUITE, *args):
    (tmp_path / "test_talkative.py").write_text(textwrap.dedent(body).lstrip())

    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--html-report=./report", "-p", "no:cacheprovider",
         "--log-level=INFO"] + list(args),
        cwd=str(tmp_path),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )

    report = tmp_path / "report" / "pytest_html_report.html"
    assert report.is_file(), result.stdout

    return report.read_text()


def _payload(page, test_name):
    """The captured output block the page holds for one test, or None."""
    match = re.search(
        r'<div class="log-payload"[^>]*data-test="%s"[^>]*>(.*?)\n</div>\n(?=<div class="log-payload"|</div>)'
        % re.escape(test_name),
        page, re.S,
    )

    return match.group(1) if match else None


def _sections(payload):
    return re.findall(r'<div class="log-section__head">(.*?)</div>', payload)


def _metrics_table(page):
    """Just the Test Metrics table.

    A test's name is now on an Analytics row as well, and that table comes
    first in the document - so a row matched against the whole page is the
    wrong row, in a table that has none of the cells being asserted on.
    """
    return page.split('id="tm"', 1)[-1].split('</table>', 1)[0]


def _cell(page, test_name):
    """The `data-logs` count on a test's row."""
    # `<tr[^>]*>`: every row now opens with the anchor a link to it points at.
    row = re.search(r'<tr[^>]*>(?:(?!</tr>).)*?%s.*?</tr>' % re.escape(test_name),
                    _metrics_table(page), re.S)
    return re.search(r'<td class="log-cell" data-logs="(\d*)"', row.group(0)).group(1)


def test_every_phase_of_a_test_reaches_the_report(tmp_path):
    page = _run(tmp_path)
    payload = _payload(page, "test_talks")

    assert _sections(payload) == [
        "Captured stdout setup",
        "Captured log call",
        "Captured stdout call",
        "Captured stderr call",
        "Captured stdout teardown",
    ]

    assert "hello from stdout" in payload
    assert "and from stderr" in payload
    assert "a warning while the test ran" in payload

    # teardown output is captured after the record is built, so it is the
    # phase most easily lost
    assert "cleaning up" in payload


def test_a_test_that_captured_nothing_has_no_payload(tmp_path):
    page = _run(tmp_path)

    assert _payload(page, "test_says_nothing") is None
    assert _cell(page, "test_says_nothing") == "0"


def test_the_row_counts_the_lines_it_can_open(tmp_path):
    page = _run(tmp_path)

    assert _cell(page, "test_fails_loudly") == "1"
    assert _cell(page, "test_talks") == "5"


def test_failed_mode_keeps_only_the_failures(tmp_path):
    page = _run(tmp_path, SUITE, "--report-logs=failed")

    assert _payload(page, "test_fails_loudly") is not None
    assert _payload(page, "test_talks") is None


def test_none_mode_keeps_nothing(tmp_path):
    page = _run(tmp_path, SUITE, "--report-logs=none")

    assert '<div class="log-payload"' not in page


def test_output_is_escaped_rather_than_rendered(tmp_path):
    page = _run(tmp_path, """
        def test_prints_markup():
            print("<b>bold</b> and a placeholder %(archive_status)%")
    """)
    payload = _payload(page, "test_prints_markup")

    assert "&lt;b&gt;bold&lt;/b&gt;" in payload
    assert "%&#40;archive_status)%" in payload


def test_a_chatty_test_is_trimmed_to_the_limit(tmp_path):
    page = _run(tmp_path, """
        def test_shouts():
            for i in range(2000):
                print("line %d" % i)
    """, "--report-log-limit=200")
    payload = _payload(page, "test_shouts")

    assert "Trimmed" in _sections(payload)
    assert "line 1999" in payload
    assert "line 0\n" not in payload


def test_the_limit_can_be_lifted(tmp_path):
    page = _run(tmp_path, """
        def test_shouts():
            for i in range(2000):
                print("line %d" % i)
    """, "--report-log-limit=0")
    payload = _payload(page, "test_shouts")

    assert "Trimmed" not in _sections(payload)
    assert "line 0\n" in payload


@pytest.mark.skipif(
    not pytest.importorskip("pytest_rerunfailures", reason="needs pytest-rerunfailures"),
    reason="needs pytest-rerunfailures",
)
def test_a_retried_test_shows_the_attempt_that_was_reported(tmp_path):
    page = _run(tmp_path, """
        attempts = {"n": 0}

        def test_flaky():
            attempts["n"] += 1
            print("attempt %d" % attempts["n"])
            assert attempts["n"] == 2
    """, "--reruns", "2")
    payload = _payload(page, "test_flaky")

    assert "attempt 2" in payload
    assert "attempt 1" not in payload


def test_the_report_says_when_capture_is_switched_off(tmp_path):
    """A column of dashes under -s reads as a broken feature, so the page says
    what is suppressing its own output."""
    page = _run(tmp_path, SUITE, "-s")

    assert "--capture=no" in page
    assert "logging only (stdout and stderr are off under -s)" in page

    # logging survives -s; only stdout and stderr are gone
    assert _payload(page, "test_talks") is not None
    assert "a warning while the test ran" in _payload(page, "test_talks")
    assert "hello from stdout" not in page


def test_no_notice_when_everything_is_being_captured(tmp_path):
    page = _run(tmp_path)

    assert '<div class="metrics-notice">' not in page
    assert "all tests: stdout, stderr and logging" in page
