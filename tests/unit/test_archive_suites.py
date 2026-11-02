"""Cover the suite count on each build's card in the Archives tab.

Every build writes how many suites it ran into output.json as total_suite, and
that file is what gets archived, so the count is already there for every build
kept - the card only has to show it. A build archived without one has no count
to show, which is not the same as having run no suites.
"""

import json
import os

import pytest
from bs4 import BeautifulSoup

from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.html_reporter import HTMLReporter


class _FakePluginManager:
    def hasplugin(self, name):
        return False


class _FakeConfig:
    """Just enough of pytest's Config to build a reporter."""

    def __init__(self):
        self.pluginmanager = _FakePluginManager()

    def getoption(self, name, default=None):
        return default

    def getini(self, name):
        raise ValueError(name)


_ARCHIVES = ("_archive_tab_content", "_archive_body_content", "_archive_count", "archives")


@pytest.fixture(autouse=True)
def _isolate_archive_content():
    """The Archives tab is built into class-level state, and these tests fill it in."""
    saved = {name: getattr(ConfigVars, name) for name in _ARCHIVES}
    yield
    for name, value in saved.items():
        setattr(ConfigVars, name, value)


def _build(path, start, fields):
    """One build's output.json, in the shape load_archive reads it.

    No suites in content: suite_highlights tallies those into class-level state
    that nothing here would put back.
    """
    data = {
        "content": {"suites": {}},
        "date": "November 03, 2026",
        "start_time": start,
        "status": "PASS",
        "total_tests": "4",
        "status_list": {
            "pass": "4", "fail": "0", "skip": "0",
            "error": "0", "xpass": "0", "xfail": "0", "rerun": "0",
        },
    }
    data.update(fields)
    with open(path, "w") as handle:
        json.dump(data, handle)


def _suite_lines(tmp_path, current, *archived):
    """The suite line on every card, by build number.

    current is this build's own fields, archived the older builds' oldest first.
    """
    base = str(tmp_path)
    os.makedirs(os.path.join(base, "archive"))
    _build(os.path.join(base, "output.json"), 1793649486.0, current)
    for number, fields in enumerate(archived, 1):
        _build(os.path.join(base, "archive", f"output_{number}.json"), 1793649486.0 - number, fields)

    HTMLReporter(base, "", _FakeConfig()).update_archives_template(base)

    soup = BeautifulSoup(ConfigVars._archive_body_content, "html.parser")
    return {card["id"].replace("list-item-", ""): card.find("div", class_="archive-suites")
            for card in soup.find_all("div", class_="archive-body")}


def test_each_card_says_how_many_suites_its_build_ran(tmp_path):
    lines = _suite_lines(tmp_path, {"total_suite": 81}, {"total_suite": 18}, {"total_suite": 61})

    assert {build: line.text.strip() for build, line in lines.items()} == {
        "3": "81 TEST SUITES", "2": "61 TEST SUITES", "1": "18 TEST SUITES"}
    assert not any(line.has_attr("hidden") for line in lines.values())


def test_one_suite_is_singular(tmp_path):
    assert _suite_lines(tmp_path, {"total_suite": 1})["1"].text.strip() == "1 TEST SUITE"


def test_a_build_archived_without_the_count_leaves_the_line_out(tmp_path):
    """Rather than claim it ran none - which a build that did still says."""
    lines = _suite_lines(tmp_path, {"total_suite": 0}, {})

    assert lines["1"].has_attr("hidden")
    assert not lines["2"].has_attr("hidden")
    assert lines["2"].text.strip() == "0 TEST SUITES"


def test_a_hand_edited_count_is_read_if_it_is_still_a_number(tmp_path):
    lines = _suite_lines(tmp_path, {"total_suite": "61"}, {"total_suite": None})

    assert lines["2"].text.strip() == "61 TEST SUITES"
    assert lines["1"].has_attr("hidden")
