"""Cover the dashboard's status counters as a way into Test Metrics.

The dashboard says a run had four failures and the table that lists them is
two clicks and a filter away, so the figure was read and then the work of
getting to what it counted was done by hand. Each counter is now the link to
its own rows: it opens Test Metrics, filters the table to that outcome, and
says so in the URL - #test-metrics?status=FAIL - so the address of "the
failures in this run" can be pasted somewhere else. The way back out is a
clear control beside the chips, for the filter nobody clicked into.
"""

import os

from bs4 import BeautifulSoup

TEMPLATE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "html_page", "html", "template.html",
)

STATUSES = ("pass", "fail", "skip", "xpass", "xfail", "error")


def _template():
    with open(TEMPLATE, encoding="utf-8") as page:
        return page.read()


def _footer():
    soup = BeautifulSoup(_template(), "html.parser")
    return soup.find("div", class_="card__footer")


def _body(start, end):
    """The one function under discussion, so a phrase found in it is found in
    it rather than somewhere else in eleven thousand lines."""
    return _template().split(start, 1)[1].split(end, 1)[0]


# --------------------------------------------------------------------------
# what a counter is
# --------------------------------------------------------------------------

def test_every_outcome_a_test_can_end_on_is_a_button():
    counters = _footer().findAll("button", class_="stat-jump")

    assert [counter["data-status"] for counter in counters] == list(STATUSES)
    assert all(counter["type"] == "button" for counter in counters)


def test_rerun_stays_a_figure():
    """Rerun is not a status a row carries, so there is no filter to send
    anyone to - and a control that goes nowhere is worse than a number."""
    footer = _footer()

    rerun = footer.findAll("div", class_="card__footer-section")
    assert len(rerun) == 1
    assert rerun[0].find("div", class_="footer-section__label").text.strip() == "rerun"
    assert rerun[0].find("button") is None


def test_a_counter_still_shows_the_count_it_always_did():
    """The markup around the figure changed; the figure did not."""
    counters = _footer().findAll("button", class_="stat-jump")
    placeholders = [counter.find("span", class_="footer-section__data").text.strip()
                    for counter in counters]

    assert placeholders == ["%(_pass)%", "%(fail)%", "%(skip)%",
                            "%(xpass)%", "%(xfail)%", "%(error)%"]


def test_a_counter_standing_at_zero_is_not_pressable():
    """It would open the table on "No matching records found", which is not
    what the figure it was read off said. Disabled rather than styled flat, so
    it is not a tab stop either."""
    body = _body("function disableEmptyStatJumps() {", "\n            }")

    assert ".footer-section__data" in body
    assert ".prop('disabled', !count)" in body


# --------------------------------------------------------------------------
# what clicking one does
# --------------------------------------------------------------------------

def test_a_counter_opens_the_tab_filters_the_table_and_says_so_in_the_url():
    body = _body("$(document).on('click', '.stat-jump'", "});")

    assert "showTestMetricsTab();" in body
    assert "applyTestStatusFilter(status);" in body
    assert "window.location.hash = '#test-metrics?status=' + status.toUpperCase();" in body


def test_the_click_does_the_work_rather_than_leaving_it_to_the_hash():
    """Clicking FAIL, going back to the dashboard and clicking FAIL again sets
    the hash to what it already is, and no hashchange fires for that."""
    template = _template()
    handler = template.index("$(document).on('click', '.stat-jump'")
    tab = template.index("showTestMetricsTab();", handler)
    hash_set = template.index("window.location.hash = '#test-metrics?status='", handler)

    assert tab < hash_set


def test_the_filter_is_anchored_so_pass_does_not_pull_in_xpass():
    body = _body("function applyTestStatusFilter(status) {", "\n            }")

    assert ".search(status ? '^' + status + '$' : '', true, false)" in body


def test_a_filter_that_is_already_on_is_not_drawn_again():
    """A draw re-renders the whole table, and the hashchange the click causes
    asks for the same filter a second time."""
    body = _body("function applyTestStatusFilter(status) {", "\n            }")

    assert "if (status === testStatusFilter) { return; }" in body


# --------------------------------------------------------------------------
# what the URL carries
# --------------------------------------------------------------------------

def test_a_tab_hash_can_carry_options_behind_a_question_mark():
    body = _body("function parseHash(raw) {", "\n                return route;")

    assert "var cut = raw.indexOf('?');" in body
    assert "cut === -1 ? raw : raw.slice(0, cut)" in body


def test_test_metrics_is_opened_rather_than_clicked_into():
    """The nav link's href is a bare #test-metrics, so following it would
    throw away the ?status= the hash was opened with."""
    body = _body("var pageId = hashToPageMap[hash];", "if (pageId) {")

    assert "if (pageId === 'testMetrics') {" in body
    assert "showTestMetricsTab();" in body
    assert "applyTestStatusFilter(route.params.status);" in body


def test_a_status_the_report_does_not_know_filters_nothing():
    """?status=NOPE shows the whole table; filtering it down to no rows at all
    is the one reading nobody wanted."""
    body = _body("function testStatus(value) {", "\n            }")

    assert "TEST_STATUSES.indexOf(status) === -1 ? '' : status" in body
    assert "var TEST_STATUSES = ['pass', 'fail', 'skip', 'xpass', 'xfail', 'error'];" in _template()


def test_the_chips_keep_the_url_in_step_with_the_table():
    """Half the ways into the filter are the chips over the table, and a URL
    still saying status=FAIL over a table showing the passes is worse than one
    saying nothing at all."""
    template = _template()

    assert template.count("syncTestStatusHash();") >= 2
    body = _body("function syncTestStatusHash() {", "\n            }")
    assert "window.history.replaceState(null, '', hash);" in body


def test_toggling_a_chip_is_one_place_to_leave_rather_than_four():
    """replaceState, not a new entry per click: back should go back to the
    dashboard, not walk out through every chip that was tried."""
    body = _body("function syncTestStatusHash() {", "\n            }")

    assert "pushState" not in body


def test_the_url_is_only_rewritten_while_test_metrics_is_the_open_tab():
    body = _body("function syncTestStatusHash() {", "\n            }")

    assert "document.getElementById('testMetrics')" in body
    assert "page.style.display !== 'block'" in body


# --------------------------------------------------------------------------
# the way out
# --------------------------------------------------------------------------

def test_a_filter_offers_a_way_out_of_itself():
    """Clicking the chip that is holding clears it too, but that is only
    discoverable once you know it - and a link opened on ?status=FAIL was
    never clicked into a chip at all."""
    body = _body("renderMetricsChips($('#testSummary'), testStatusChips);", "\n            }")

    assert "if (testStatusFilter) {" in body
    assert "metric-chip metric-chip--clear" in body
    assert "Clear filter" in body


def test_the_way_out_clears_the_filter_and_the_url_with_it():
    body = _body("$(document).on('click', '#testSummary .metric-chip--clear'", "});")

    assert "applyTestStatusFilter('');" in body
    assert "syncTestStatusHash();" in body
