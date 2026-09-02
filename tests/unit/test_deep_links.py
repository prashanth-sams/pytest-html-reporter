"""Cover the anchor every test row carries, and the link that points at it.

A failure is read in the report and then talked about somewhere else - a chat
window, a ticket, a stand-up note - and until now the only address anyone could
paste was the report itself, leaving whoever opened it to find the test again by
hand. Every row now has an address of its own, the fourth button beside a
failure copies it, and opening one lands on that row whatever page of the table
it has ended up on.
"""

import os
import re

import pytest
from bs4 import BeautifulSoup

from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.html_reporter import HTMLReporter
from pytest_html_reporter.util import row_anchor

TEMPLATE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "html_page", "html", "template.html",
)


class _FakePluginManager:
    def hasplugin(self, name):
        return False


class _FakeConfig:
    def __init__(self):
        self.pluginmanager = _FakePluginManager()

    def getoption(self, name, default=None):
        return default

    def getini(self, name):
        raise ValueError(name)


_TOUCHED = (
    "_test_metrics_content", "_suite_metrics_content", "_test_suite_name",
    "_test_pass_list", "_test_fail_list", "_test_skip_list", "_test_xpass_list",
    "_test_xfail_list", "_test_error_list", "_attach_screenshot_details",
    "_pass", "_fail", "_skip", "_error", "_xpass", "_xfail", "_total",
    "_executed",
)


@pytest.fixture(autouse=True)
def _isolate_config_vars():
    saved = {name: getattr(ConfigVars, name) for name in _TOUCHED}
    for name in _TOUCHED:
        setattr(ConfigVars, name, [] if isinstance(saved[name], list) else type(saved[name])())
    yield
    for name, value in saved.items():
        setattr(ConfigVars, name, value)


def _record(suite, name, status="PASS", message="", index=0, nodeid=None):
    return {
        "suite_name": suite,
        "test_name": name,
        "nodeid": suite + "::" + name if nodeid is None else nodeid,
        "status": status,
        "message": message,
        "duration": 0.01,
        "rerun": 0,
        "index": index,
        "worker": "",
        "screenshots": [],
        "logs": [],
        "attachments": [],
    }


def _rows(records):
    # Rows are appended to one string on the class, and a test here builds two
    # reports to compare them - so the second starts where the first left off
    # unless the string is put back first.
    ConfigVars._test_metrics_content = ""

    reporter = HTMLReporter(".", "", _FakeConfig())
    reporter._records = list(records)
    reporter.build_report()

    return BeautifulSoup("<table>" + ConfigVars._test_metrics_content + "</table>", "html.parser")


def _anchors(soup):
    return [row["id"] for row in soup.findAll("tr")]


def _template():
    with open(TEMPLATE, encoding="utf-8") as page:
        return page.read()


# --------------------------------------------------------------------------
# what a row is addressed by
# --------------------------------------------------------------------------

def test_every_row_carries_an_anchor():
    """Passing rows included: the link is the row's address, not a failure's."""
    soup = _rows([
        _record("tests/test_a.py", "test_one", index=0),
        _record("tests/test_a.py", "test_two", status="FAIL", message="boom", index=1),
    ])

    assert all(anchor for anchor in _anchors(soup))


def test_the_anchor_survives_a_test_being_added_in_front_of_it():
    """The whole point: a link is opened against whatever report is at that
    address by now, and a positional anchor would still resolve - to whichever
    test has since taken that place."""
    before = _anchors(_rows([_record("tests/test_a.py", "test_two", index=0)]))[0]

    after = _anchors(_rows([
        _record("tests/test_a.py", "test_one", index=0),
        _record("tests/test_a.py", "test_two", index=1),
    ]))[1]

    assert after == before


def test_two_tests_of_the_same_name_in_different_files_are_told_apart():
    soup = _rows([
        _record("tests/test_a.py", "test_login", index=0),
        _record("tests/test_b.py", "test_login", index=1),
    ])

    assert len(set(_anchors(soup))) == 2


def test_the_anchor_comes_from_the_node_id_not_from_the_names_on_show():
    """A test inside a class is listed under its own name, which two classes in
    one file can share; the node id is what has the class in front of it."""
    first = _record("tests/test_a.py", "test_login", index=0)
    first["nodeid"] = "tests/test_a.py::TestAdmin::test_login"

    second = _record("tests/test_a.py", "test_login", index=1)
    second["nodeid"] = "tests/test_a.py::TestGuest::test_login"

    assert len(set(_anchors(_rows([first, second])))) == 2


def test_a_row_with_no_node_id_is_still_addressable():
    """A file that failed to import has no node id. Falling back to the two
    names is worse than a node id and better than a row nothing can link to."""
    record = _record("tests/test_a.py", "test_one")
    del record["nodeid"]

    assert _anchors(_rows([record]))[0]


def test_the_same_test_twice_over_gets_an_anchor_each():
    """`pytest-repeat` runs one node id as many rows. Two rows carrying one id
    is invalid HTML and, worse, silent: the link would open the first of them
    whichever was meant."""
    soup = _rows([
        _record("tests/test_a.py", "test_one", index=0),
        _record("tests/test_a.py", "test_one", index=1),
    ])

    assert len(set(_anchors(soup))) == 2


# --------------------------------------------------------------------------
# what the anchor is made of
# --------------------------------------------------------------------------

def test_an_anchor_is_letters_digits_and_dashes():
    """It travels as the `#` end of a URL through a chat window and a ticket.
    `::`, `/` and the brackets round a parameter would all have to be escaped,
    and a fragment full of `%5B` is not a link anyone wants to read."""
    anchor = row_anchor("tests/api/test_a.py::TestAuth::test_login[user one-chrome]")

    assert re.match(r"^test-[a-z0-9-]+$", anchor)


def test_a_long_parametrised_node_id_is_cut_but_stays_its_own_address():
    """The readable half is cut back to a whole word; the digits after it are
    taken from the whole node id, so two ids that agree until their last few
    characters are still told apart."""
    stem = ("tests/integration/api/test_checkout.py::TestPayments::"
            "test_a_declined_card_is_reported_on_the_step_that_failed[visa-")

    first = row_anchor(stem + "expired]")
    second = row_anchor(stem + "declined]")

    assert first != second
    assert len(first) < len(stem)
    assert not first.endswith("-")
    # Cut at a dash, so the tail of the slug is a whole word rather than half a
    # name - `...test-a-declin` says less than `...test-a` and looks like damage.
    assert first.split("-")[-2] in stem.lower().replace("_", "-")


def test_the_same_node_id_always_gives_the_same_anchor():
    """A link pasted from yesterday's report opens today's on the same test."""
    assert row_anchor("tests/test_a.py::test_one") == row_anchor("tests/test_a.py::test_one")


def test_punctuation_alone_never_makes_two_tests_one_address():
    """The slug drops what the two ids differ by; the digits are taken from the
    node id itself, which still has it."""
    assert row_anchor("tests/test_a.py::test_one[a-b]") != row_anchor("tests/test_a.py::test_one[a_b]")


def test_a_record_with_nothing_to_identify_it_has_no_anchor_of_its_own():
    assert row_anchor("", "", "") == ""


# --------------------------------------------------------------------------
# the button that hands the link out
# --------------------------------------------------------------------------

def test_a_failure_offers_the_link_beside_the_error_and_the_command():
    soup = _rows([_record("tests/test_a.py", "test_one", status="FAIL", message="boom")])

    assert soup.find("button", class_="msg-link") is not None


def test_the_link_is_built_from_the_row_rather_than_carried_beside_it():
    """One id, read off the <tr> the button sits in, so the address the link
    points at and the id the row answers to cannot drift apart."""
    page = _template()

    assert "function rowLink(actions)" in page
    assert "actions.closest('tr')" in page
    assert "window.location.href.split('#')[0] + '#' + row.id" in page


# --------------------------------------------------------------------------
# what opening one does
# --------------------------------------------------------------------------

def test_the_page_routes_a_row_anchor_to_the_row():
    page = _template()

    assert "function scrollToTestRow(id)" in page
    assert "if (hash.indexOf('test-') === 0) {" in page


def test_the_tabs_whose_hash_starts_the_same_way_are_still_tabs():
    """#test-metrics and #test-steps begin with the four letters every row
    anchor begins with. The map is read first, and its two entries are what
    keep those two links opening tabs rather than searching for a row."""
    page = _template()

    routes = page.index("var hashToPageMap")
    rows = page.index("if (hash.indexOf('test-') === 0) {")

    assert routes < rows
    assert "'test-metrics': 'testMetrics'" in page
    assert "'test-steps': 'testSteps'" in page


def test_a_row_is_found_through_the_table_rather_than_by_its_id():
    """DataTables keeps only the current page in the document, so a row on page
    four is not there for getElementById to find - and the table has to be paged
    to it before it is anywhere at all."""
    page = _template()

    assert "table.row('#' + id).index()" in page
    assert "function pageToTestRow(table, index)" in page


def test_every_filter_hiding_the_row_is_cleared_first():
    """A filtered-out row is on no page at all, and landing on "No matching
    records found" is not what the link was pasted for. The status chips over
    the table are a column search of their own, and "show me the failures" is
    the likeliest of the three to be hiding the row - so the chip state goes
    with the searches, or the counts stay those of a filter that is off."""
    body = _template().split("function pageToTestRow(table, index) {", 1)[1] \
                      .split("function markTestRow", 1)[0]

    assert "table.search('').columns().search('').draw(false);" in body
    assert "testStatusFilter = '';" in body
    assert ".dataTables_filter input').val('');" in body
