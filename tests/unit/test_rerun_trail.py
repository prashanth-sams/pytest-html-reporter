"""Cover the trail a retried test leaves behind it.

The rerun count says a test was attempted more than once. It does not say what
any of those attempts *did* - and on the case that matters most, a test that
fails twice and then passes, the record left standing has no message at all,
because the attempt that stuck did not fail. These tests pin down that the
outcome of every superseded attempt is kept, that it survives the two folds
(a retry in one process, a node id that ran in two shards), and that it reaches
the page as something a reader can open.
"""

import json
import os
import re
import subprocess
import sys
import textwrap

import pytest
from bs4 import BeautifulSoup

from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.html_reporter import HTMLReporter
from pytest_html_reporter.shards import normalise_record
from pytest_html_reporter.util import attempt_seconds, attempt_summary, attempt_trail, status_tone


class _FakePluginManager:
    def __init__(self, plugins=()):
        self._plugins = set(plugins)

    def hasplugin(self, name):
        return name in self._plugins


class _FakeConfig:
    """Just enough of pytest's Config for the reporter to be constructed."""

    def __init__(self, plugins=("rerunfailures",)):
        self.pluginmanager = _FakePluginManager(plugins)

    def getoption(self, name, default=None):
        return default

    def getini(self, name):
        raise ValueError(name)


_TOUCHED = ("_test_metrics_content", "_test_attempts_content")


@pytest.fixture(autouse=True)
def _isolate_config_vars():
    """ConfigVars is class-level state, so hand each test a clean copy."""
    saved = {name: getattr(ConfigVars, name) for name in _TOUCHED}
    for name in _TOUCHED:
        setattr(ConfigVars, name, "")
    yield
    for name, value in saved.items():
        setattr(ConfigVars, name, value)


def _record(name, status, message="", rerun=0, duration=0.01, **kwargs):
    record = {
        "suite_name": "tests/test_a.py",
        "test_name": name,
        "nodeid": "tests/test_a.py::" + name,
        "status": status,
        "message": message,
        "duration": duration,
        "rerun": rerun,
        "attempts": [],
        "index": 0,
        "worker": "",
        "screenshots": [],
        "logs": [],
        "attachments": [],
        "steps": [],
        "phases": {},
        "meta": {},
        "bdd": None,
    }
    record.update(kwargs)
    return record


def _reporter():
    return HTMLReporter(".", "", _FakeConfig())


def _stored(*records):
    """Every record through store_test_record, as the one row list it leaves."""
    reporter = _reporter()
    for record in records:
        reporter.store_test_record(record)

    return reporter._records


# --------------------------------------------------------------------------
# what a fold keeps
# --------------------------------------------------------------------------

def test_a_retry_keeps_what_the_attempt_before_it_failed_with():
    """The case the whole feature exists for.

    A test that fails and then passes is reported as passed, and the record
    left standing carries no message - so without the trail there is nothing
    anywhere in the report that says what it failed with.
    """
    kept, = _stored(
        _record("test_flaky", "FAIL", "connection refused"),
        _record("test_flaky", "PASS"),
    )

    assert kept["status"] == "PASS"
    assert kept["message"] == ""
    assert [(a["status"], a["message"]) for a in kept["attempts"]] == [("FAIL", "connection refused")]


def test_every_attempt_is_kept_in_the_order_it_ran():
    kept, = _stored(
        _record("test_flaky", "FAIL", "first"),
        _record("test_flaky", "FAIL", "second"),
        _record("test_flaky", "PASS"),
    )

    assert [a["message"] for a in kept["attempts"]] == ["first", "second"]


def test_the_trail_is_as_long_as_the_rerun_count_says():
    """The count and the trail are two spellings of one fact, so they agree.

    A row showing three reruns and a panel showing two attempts is worse than
    either alone: it says the report lost one.
    """
    for attempts in range(1, 5):
        # A fresh dict per attempt: store_test_record folds in place, so one
        # record repeated would be the same object arriving back at itself.
        kept, = _stored(*([_record("test_flaky", "FAIL", "boom") for _ in range(attempts)]
                          + [_record("test_flaky", "PASS")]))

        assert kept["rerun"] == attempts
        assert len(kept["attempts"]) == attempts


def test_a_trail_that_arrives_already_folded_is_not_flattened():
    """An xdist worker sends back a record that was folded on the worker.

    Both sides can already stand for several attempts, and the record being
    replaced belongs between the two lists: it ran after its own attempts and
    before the one replacing it.
    """
    superseded = _record("test_flaky", "FAIL", "third", rerun=2, attempts=[
        {"status": "FAIL", "message": "first", "duration": 0.0, "worker": ""},
        {"status": "FAIL", "message": "second", "duration": 0.0, "worker": ""},
    ])
    winner = _record("test_flaky", "PASS", rerun=1, attempts=[
        {"status": "FAIL", "message": "fourth", "duration": 0.0, "worker": ""},
    ])

    kept, = _stored(superseded, winner)

    assert [a["message"] for a in kept["attempts"]] == ["first", "second", "third", "fourth"]
    assert kept["rerun"] == len(kept["attempts"]) == 4


def test_an_attempt_carries_four_fields_and_not_a_whole_record():
    """A shard bundle is the record list as it stands in memory.

    Keeping whole attempts would multiply every bundle a matrix uploads by the
    number of times its flakiest tests were retried, and put a copy of each
    discarded attempt's logs and screenshots in it.
    """
    attempt = attempt_summary(_record(
        "test_flaky", "FAIL", "boom",
        logs=[{"title": "stdout", "text": "x" * 5000}],
        screenshots=[{"name": "shot", "suite": "s", "test": "t", "error": ""}],
        steps=[{"title": "a step"}],
    ))

    assert sorted(attempt) == ["duration", "message", "status", "worker"]


def test_a_test_that_ran_once_has_no_trail():
    """Which is nearly every row, and is what keeps the key from costing anything."""
    kept, = _stored(_record("test_steady", "PASS"))

    assert kept["attempts"] == []
    assert kept["rerun"] == 0


def test_without_rerunfailures_nothing_is_folded_and_nothing_is_trailed():
    """Two records for one node id are two tests - pytest-repeat, not a retry."""
    reporter = HTMLReporter(".", "", _FakeConfig(plugins=()))
    reporter.store_test_record(_record("test_twice", "FAIL", "boom"))
    reporter.store_test_record(_record("test_twice", "PASS"))

    assert [r["status"] for r in reporter._records] == ["FAIL", "PASS"]
    assert all(r["attempts"] == [] for r in reporter._records)


# --------------------------------------------------------------------------
# the pieces the trail is built from
# --------------------------------------------------------------------------

def test_a_duration_that_cannot_be_read_becomes_zero():
    """Tolerant for the reason normalise_record is.

    The attempts inside a bundle are checked as a list and not each one as a
    record, so an unreadable duration is a decoration on a panel and no reason
    to lose the report the tests have already paid for.
    """
    assert attempt_seconds("1.5") == 1.5
    assert attempt_seconds(None) == 0.0
    assert attempt_seconds("twice") == 0.0
    assert attempt_seconds([]) == 0.0


def test_a_status_is_toned_the_way_the_rows_own_pills_are():
    assert status_tone("PASS") == "pass"
    assert status_tone("xFAIL") == "xfail"
    assert status_tone("") == ""


def test_a_bundle_written_before_the_trail_existed_reads_as_no_trail():
    """An older shard artifact is missing the key rather than carrying an empty one."""
    assert normalise_record({"nodeid": "a", "rerun": 2})["attempts"] == []
    assert normalise_record({"nodeid": "a", "attempts": "not a list"})["attempts"] == []


# --------------------------------------------------------------------------
# what reaches the page
# --------------------------------------------------------------------------

def _payload(name):
    """The trail parked in the store for one test."""
    soup = BeautifulSoup(ConfigVars._test_attempts_content, "html.parser")
    node = soup.find("div", class_="attempt-payload", attrs={"data-test": name})

    return node or BeautifulSoup("", "html.parser")


def _lines(payload):
    """(status, message, is_final) for every attempt drawn, in page order."""
    return [(node.find("span", class_="attempt__status").text.strip(),
             node.find("pre", class_="attempt__msg").text.strip(),
             "attempt--final" in node["class"])
            for node in payload.find_all("div", class_="attempt")]


def _render(record):
    reporter = _reporter()
    reporter.append_test_metrics_row(record, "0-0")

    return reporter


def test_the_panel_ends_on_the_attempt_the_row_is_showing():
    """The trail is the superseded attempts *and then the record itself*.

    Stopping at the last attempt that was thrown away would leave a panel whose
    final line disagrees with the row that opened it.
    """
    kept, = _stored(
        _record("test_flaky", "FAIL", "connection refused"),
        _record("test_flaky", "FAIL", "stale cache"),
        _record("test_flaky", "PASS"),
    )
    _render(kept)

    assert _lines(_payload("test_flaky")) == [
        ("FAIL", "connection refused", False),
        ("FAIL", "stale cache", False),
        ("PASS", "", True),
    ]


def test_the_row_says_how_many_attempts_there_are_to_open():
    kept, = _stored(_record("test_flaky", "FAIL", "boom"), _record("test_flaky", "PASS"))
    _render(kept)

    cell = BeautifulSoup(ConfigVars._test_metrics_content, "html.parser").find("td", class_="rerun-cell")

    assert cell["data-attempts"] == "1"
    assert cell.find("button", class_="rerun-btn").text.strip() == "1"


def test_a_row_with_no_trail_parks_nothing_and_offers_nothing():
    _render(_record("test_steady", "PASS"))

    cell = BeautifulSoup(ConfigVars._test_metrics_content, "html.parser").find("td", class_="rerun-cell")

    assert cell["data-attempts"] == "0"
    assert ConfigVars._test_attempts_content == ""


def test_the_count_is_in_the_cell_once():
    """The cell's text is what the search index and every export take.

    Two spellings of the count - a button beside a hidden span - would put the
    number in the CSV, the Excel sheet and the print-out twice.
    """
    kept, = _stored(_record("test_flaky", "FAIL", "boom"), _record("test_flaky", "PASS"))
    _render(kept)

    cell = BeautifulSoup(ConfigVars._test_metrics_content, "html.parser").find("td", class_="rerun-cell")

    assert cell.text.strip() == "1"


def test_a_message_full_of_markup_stays_text_in_the_panel():
    kept, = _stored(
        _record("test_flaky", "FAIL", '<script>alert("x")</script> & %(runt)%'),
        _record("test_flaky", "PASS"),
    )
    _render(kept)

    payload = _payload("test_flaky")

    assert payload.find("script") is None
    assert payload.find("pre", class_="attempt__msg").text.strip() == '<script>alert("x")</script> & %(runt)%'


def test_the_panel_carries_the_whole_message_not_the_cell_s_fifty_characters():
    """This panel is where a superseded attempt's full text is read.

    There is nowhere else left to read it: the row shows the message of the
    attempt that stuck, which on a test that ends up passing is empty.
    """
    long_error = "AssertionError: " + "x" * 400
    kept, = _stored(_record("test_flaky", "FAIL", long_error), _record("test_flaky", "PASS"))
    _render(kept)

    assert _payload("test_flaky").find("pre", class_="attempt__msg").text.strip() == long_error


# --------------------------------------------------------------------------
# through a real run
# --------------------------------------------------------------------------

FLAKY_SUITE = '''
    STATE = {"n": 0}

    def test_settles_on_the_third_go():
        STATE["n"] += 1
        if STATE["n"] == 1:
            raise AssertionError("first attempt: connection refused")
        if STATE["n"] == 2:
            raise ValueError("second attempt: stale cache")

    def test_ran_once():
        assert True
'''


def _run(tmp_path, body=FLAKY_SUITE, *args):
    """Run a generated suite and hand back the report page it wrote."""
    (tmp_path / "test_flaky_ran.py").write_text(textwrap.dedent(body))

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


def test_a_real_retry_reaches_the_page_with_both_failures_on_it(tmp_path):
    pytest.importorskip("pytest_rerunfailures")

    page = _run(tmp_path, FLAKY_SUITE, "--reruns", "3")

    store = re.search(r'<div id="attemptStore" hidden>(.*?)</div>\s*</div>\s*</div>', page, re.S).group(1)
    payload = BeautifulSoup(store, "html.parser").find(
        "div", class_="attempt-payload", attrs={"data-test": "test_settles_on_the_third_go"})

    statuses = [(node.find("span", class_="attempt__status").text.strip(),
                 "attempt--final" in node["class"])
                for node in payload.find_all("div", class_="attempt")]

    assert statuses == [("FAIL", False), ("FAIL", False), ("PASS", True)]

    messages = "\n".join(node.text for node in payload.find_all("pre", class_="attempt__msg"))
    assert "connection refused" in messages
    assert "stale cache" in messages


def test_a_test_that_ran_once_gets_no_payload_in_a_real_run(tmp_path):
    pytest.importorskip("pytest_rerunfailures")

    page = _run(tmp_path, FLAKY_SUITE, "--reruns", "3")

    assert 'data-test="test_ran_once"' not in re.search(
        r'<div id="attemptStore" hidden>(.*?)</div>\s*</div>\s*</div>', page, re.S).group(1)
