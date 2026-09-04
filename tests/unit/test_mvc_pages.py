import importlib
import os
import re
from datetime import date

from bs4 import BeautifulSoup

from html_page.archive_body import ArchiveBody
from html_page.archive_row import ArchiveRow
from html_page.attachment_body import AttachmentBody
from html_page.attachment_item import AttachmentItem
from html_page.attachment_meta import AttachmentMeta
from html_page.attachment_part import AttachmentPart
from html_page.coverage_chip import CoverageChip
from html_page.coverage_row import CoverageRow
from html_page.coverage_tile import CoverageTile
from html_page.report_link import ReportLink
from html_page.env_row import EnvRow
from html_page.floating_error import FloatingError
from html_page.screenshot_details import ScreenshotDetails
from html_page.suite_row import SuiteRow
from html_page.template import HtmlTemplate
from html_page.test_log import TestLog
from html_page.test_log_section import TestLogSection
from html_page.test_row import TestRow
from html_page.test_shot import TestShot
from .helper import get_random_number, get_random_string


def test_archive_body():
    acount = str(get_random_number())
    _date = str(date.today())
    iloop = str(get_random_number())
    total_tests = str(get_random_number())
    _pass = str(get_random_number())
    fail = str(get_random_number())
    skip = str(get_random_number())
    xpass = str(get_random_number())
    xfail = str(get_random_number())
    error = str(get_random_number())
    status = get_random_string()

    _archive_body_text = ArchiveBody(
        total_tests=total_tests,
        date=_date,
        _pass=_pass,
        fail=fail,
        skip=skip,
        xpass=xpass,
        xfail=xfail,
        error=error,
        status=status,
        acount=acount,
        iloop=iloop
    )

    soup = BeautifulSoup(str(_archive_body_text), "html.parser")

    acount_s = soup.find("h4", class_="archive-header")
    assert acount_s.text.strip().replace("#", "").replace("Build ", "") == acount

    _date_s = soup.find("div", class_="archive-date")
    assert _date_s.text.strip() == _date

    _pass_s = soup.find(lambda tag: tag.name == "div" and "PASSED" in tag.text, class_="counter")
    assert _pass_s.text.strip().split("\n")[0] == _pass

    fail_s = soup.find(lambda tag: tag.name == "div" and "FAIL" in tag.text, class_="counter")
    assert fail_s.text.strip().split("\n")[0] == fail

    skip_s = soup.find(lambda tag: tag.name == "div" and "SKIPPED" in tag.text, class_="counter")
    assert skip_s.text.strip().split("\n")[0] == skip

    xpass_s = soup.find(lambda tag: tag.name == "div" and "XPASSED" in tag.text, class_="counter")
    assert xpass_s.text.strip().split("\n")[0] == xpass

    xfail_s = soup.find(lambda tag: tag.name == "div" and "XFAILED" in tag.text, class_="counter")
    assert xfail_s.text.strip().split("\n")[0] == xfail

    error_s = soup.find(lambda tag: tag.name == "div" and "ERROR" in tag.text, class_="counter")
    assert error_s.text.strip().split("\n")[0] == error

    status_s = soup.find("section", id="statistic")["class"]
    assert status_s == [f"statistic-section-{status}", "one-page-section"]

    assert soup.find("div", id=f"archive-container-{iloop}")
    assert soup.find("div", id=f"archive-label-{iloop}")
    assert soup.find("canvas", id=f"archive-chart-{iloop}")


def test_archive_row():
    acount = str(get_random_number())
    astate = get_random_string()
    astate_color = f"#{get_random_number()}"
    astatus = get_random_string()
    adate = str(date.today())

    archive_row = ArchiveRow(acount=acount, astate=astate, astate_color=astate_color, astatus=astatus, adate=adate)
    soup = BeautifulSoup(str(archive_row), "html.parser")
    assert soup.find("a", href=f"#list-item-{acount}")
    assert soup.find("i")["class"] == ["fa", f"fa-{astate}"]
    assert soup.findAll("span")[0].text.strip() == astatus
    assert soup.findAll("span")[1].text.strip() == adate


def test_floating_error():
    full_msg = get_random_string(80)
    sname = get_random_string()
    name = get_random_string()

    cmd = "pytest tests/test_a.py::test_one"

    floating_error = FloatingError(full_msg=full_msg, has_full="1", cmd=cmd, sname=sname, name=name)
    soup = BeautifulSoup(str(floating_error), "html.parser")

    actions = soup.find("span", class_="msg-actions")
    assert actions["data-error"] == full_msg
    assert actions["data-cmd"] == cmd
    assert actions["data-suite"] == sname
    assert actions["data-test"] == name
    assert actions["data-full"] == "1"

    # The one button the row rests as, then - once it is pressed - an expand, a
    # copy, the command that runs this one test again and the link that opens
    # the report on this row, in that order. None of them carries any text, so
    # the cluster adds nothing at all to the table's search index or to its CSV,
    # Excel and print exports.
    assert [button["title"] for button in actions.findAll("button")] \
        == ["Show what can be done with this failure",
            "Show the full error", "Copy the full error",
            "Copy the command that runs this test again",
            "Copy a link to this test"]

    # The four that fold away are the four that are marked as folding away.
    folding = [button for button in actions.findAll("button")
               if "msg-btn--action" in button["class"]]
    assert len(folding) == 4
    assert actions.get_text(strip=True) == ""


def test_floating_error_offers_no_expand_when_nothing_was_cut():
    """The message fits in the cell, so there is nothing to open a panel for -
    but it is still worth copying."""
    floating_error = FloatingError(full_msg="boom", has_full="", cmd="pytest s::n", sname="s", name="n")
    soup = BeautifulSoup(str(floating_error), "html.parser")

    actions = soup.find("span", class_="msg-actions")

    # Every button stays in the markup and `data-full` hides the expand one, the
    # same way `data-logs` hides the Logs button on a test that captured nothing.
    assert actions["data-full"] == ""
    assert actions.find("button", class_="msg-open") is not None
    assert actions.find("button", class_="msg-copy") is not None
    assert actions.find("button", class_="msg-rerun") is not None
    assert actions.find("button", class_="msg-link") is not None
    assert actions.find("button", class_="msg-toggle") is not None


def test_screenshot_details():
    screen_name = get_random_string()
    ts = get_random_string()
    tc = get_random_string()
    te = get_random_string()

    screenshot_details = ScreenshotDetails(ts=ts, tc=tc, te=te, status="FAIL",
                                           status_key="fail",
                                           screen_name=screen_name)
    soup = BeautifulSoup(str(screenshot_details), "html.parser")

    screen_path = f"pytest_screenshots/{screen_name}.png"

    # The status is on the card, which is what the filter pills read.
    card = soup.find("figure", class_="shot-card")
    assert card["data-status"] == "fail"

    screenshot_link = card.find("a", class_="shot-card__frame")
    assert screenshot_link["href"] == screen_path
    assert screenshot_link["data-caption"] == f"SUITE: {ts} :: SCENARIO: {tc}"
    assert screenshot_link.find("img")["src"] == screen_path

    status = card.find("span", class_="shot-card__status")
    assert status.text.strip() == "FAIL"
    assert "shot-card__status--fail" in status["class"]

    assert card.find("div", class_="shot-card__test").text.strip() == tc
    assert card.find("div", class_="shot-card__suite").text.strip() == ts
    assert card.find("p", class_="shot-card__note").text.strip() == te


def test_screenshot_details_without_an_error():
    # A test that passed has no error, and its card carries the paragraph
    # empty rather than repeating the status the badge already shows.
    screenshot_details = ScreenshotDetails(ts="s", tc="t", te="", status="PASS",
                                           status_key="pass",
                                           screen_name=get_random_string())
    soup = BeautifulSoup(str(screenshot_details), "html.parser")

    assert soup.find("p", class_="shot-card__note").text.strip() == ""
    assert soup.find("figure", class_="shot-card")["data-status"] == "pass"


def test_suite_row():
    sname = get_random_string()
    spass = str(get_random_number())
    sfail = str(get_random_number())
    sskip = str(get_random_number())
    sxpass = str(get_random_number())
    sxfail = str(get_random_number())
    serror = str(get_random_number())
    srerun = str(get_random_number())

    suite_row = SuiteRow(sname=sname, spass=spass, sfail=sfail, sskip=sskip, sxpass=sxpass, sxfail=sxfail,
                         serror=serror, srerun=srerun)

    soup = BeautifulSoup(str(suite_row), "html.parser")
    for node, expected in zip(soup.findAll("td"), [sname, spass, sfail, sskip, sxpass, sxfail, serror, srerun]):
        assert node.text.strip() == expected


def test_test_row():
    sname = get_random_string()
    name = get_random_string()
    stat = get_random_string()
    dur = str(get_random_number())
    msg = get_random_string()
    msg_tail = get_random_string()
    floating_error_text = get_random_string()
    log_count = str(get_random_number())
    runt = get_random_string()
    rerun = str(get_random_number())

    attach_count = str(get_random_number())
    shot_count = str(get_random_number())

    anchor = "test-" + get_random_string()

    test_row = TestRow(sname=sname, name=name, stat=stat, dur=dur, rerun=rerun, msg=msg,
                       msg_tail=msg_tail, msg_cut="&hellip;",
                       floating_error_text=floating_error_text, log_count=log_count,
                       attach_count=attach_count, shot_count=shot_count, runt=runt,
                       anchor=anchor)
    soup = BeautifulSoup(str(test_row), "html.parser")

    # The row's own address, which is what a link pasted elsewhere lands on.
    assert soup.find("tr")["id"] == anchor

    cells = soup.findAll("td")

    for node, expected in zip(cells, [sname, name, stat, dur, rerun]):
        assert node.text.strip() == expected

    # The message, the few characters of it that fade out, the ellipsis the
    # exports carry in place of that fade, then the buttons.
    assert re.search(rf"{msg}{msg_tail}\u2026[\s\n]*{floating_error_text}", cells[5].text.strip())
    assert cells[5].find("span", class_="msg-fade").text == msg_tail
    assert cells[5].find("span", class_="msg-cut").text == "\u2026"

    log_cell = cells[6]
    assert log_cell["data-logs"] == log_count
    assert log_cell.find("button")["onclick"] == "showLogs('%s')" % runt
    assert log_count in log_cell.find("button").text

    attach_cell = cells[7]
    assert attach_cell["data-logs"] == attach_count
    assert attach_cell.find("button")["onclick"] == "showAttachmentsFor('%s')" % runt
    assert attach_count in attach_cell.find("button").text

    # The pictures are in the cell rather than behind a button, so the count is
    # what the column sorts on: every one of these cells has the same - empty -
    # text, which is what DataTables would otherwise compare.
    shot_cell = cells[9]
    assert shot_cell["data-logs"] == shot_count
    assert shot_cell["data-order"] == shot_count


def test_test_row_without_logs_says_so():
    """The button is left in the row and hidden by `data-logs`, so a test that
    captured nothing shows a dash instead of opening an empty panel."""
    test_row = TestRow(sname="s", name="n", stat="PASS", dur="0.1", rerun="0", msg="",
                       floating_error_text="", log_count="0", attach_count="0",
                       shot_count="0", runt="0-0")
    soup = BeautifulSoup(str(test_row), "html.parser")

    for cell in soup.findAll("td")[6:8] + soup.findAll("td")[9:10]:
        assert cell["data-logs"] == "0"
        assert cell.find("span", class_="log-none") is not None


def test_test_shot():
    """A thumbnail on a Test Metrics row: the picture itself, and a link that
    opens it in the same overlay the gallery uses."""
    screen_name = get_random_string()
    ts = get_random_string()
    tc = get_random_string()

    shot = TestShot(screen_name=screen_name, ts=ts, tc=tc, tip=tc, group="metrics")
    soup = BeautifulSoup(str(shot), "html.parser")

    path = "pytest_screenshots/%s.png" % screen_name

    link = soup.find("a", class_="shot-thumb")
    assert link["href"] == path
    assert link["data-caption"] == "SUITE: %s :: SCENARIO: %s" % (ts, tc)
    # The gallery the arrow keys walk. One thumbnail template serves the table
    # and the Test Steps tree, and each names its own group: arrowing off a row
    # and into a screenshot from a tab the reader is not looking at is not what
    # the arrow keys are for.
    assert link["data-fancybox"] == "metrics"
    assert str(TestShot(screen_name=screen_name, ts=ts, tc=tc, tip=tc,
                        group="steps")).count('data-fancybox="steps"') == 1
    assert link.find("img")["src"] == path
    assert link.find("img")["loading"] == "lazy"


def test_test_log_holds_every_section():
    sections = "".join(str(TestLogSection(title="Captured log call", text="line %d" % i))
                       for i in range(3))
    test_log = TestLog(runt="1-2", sname="tests/test_a.py", name="test_thing", sections=sections)
    soup = BeautifulSoup(str(test_log), "html.parser")

    payload = soup.find("div", class_="log-payload")
    assert payload["id"] == "log-1-2"
    assert payload["data-suite"] == "tests/test_a.py"
    assert payload["data-test"] == "test_thing"
    assert payload.has_attr("hidden")

    bodies = payload.findAll("pre", class_="log-section__body")
    assert [node.text for node in bodies] == ["line 0", "line 1", "line 2"]
    assert bodies[0].find_parent("div", class_="log-section") \
                    .find("div", class_="log-section__head").text == "Captured log call"

def test_attachment_item():
    aid = get_random_string()
    runt = get_random_string()
    title = get_random_string()
    sname = get_random_string()
    name = get_random_string()
    detail = get_random_string()
    search = get_random_string().lower()

    item = AttachmentItem(aid=aid, runt=runt, kind="api", status="4xx", code="422",
                          detail=detail, title=title, sname=sname, name=name,
                          ms="1420", size="640", search=search)
    soup = BeautifulSoup(str(item), "html.parser")

    button = soup.find("button", class_="attach-item")
    assert button["id"] == "attach-item-%s" % aid
    assert button["data-aid"] == aid
    assert button["data-row"] == runt
    assert button["data-kind"] == "api"
    assert button["data-status"] == "4xx"
    assert button["data-ms"] == "1420"
    assert button["data-size"] == "640"
    assert button["data-search"] == search
    assert button["onclick"] == "showAttachment('%s')" % aid

    assert soup.find("span", class_="attach-item__kind").text.strip() == "api"
    assert soup.find("span", class_="attach-item__title").text.strip() == title
    # The test name leads; the suite file follows it, faded.
    assert soup.find("span", class_="attach-item__test").text.strip().startswith(name)
    assert soup.find("span", class_="attach-item__test").find("em").text.strip() == sname
    assert soup.find("span", class_="attach-code").text.strip() == "422"
    assert "attach-code--4xx" in soup.find("span", class_="attach-code")["class"]
    assert soup.find("span", class_="attach-item__detail").text.strip() == detail


def test_attachment_item_without_a_status_leaves_the_pill_empty():
    """CSS hides an empty pill, which is how a plain text entry avoids one."""
    item = AttachmentItem(aid="0-0-0", kind="text", status="", code="", title="Note",
                          sname="s", name="n", detail="12 B", search="note")
    soup = BeautifulSoup(str(item), "html.parser")

    assert soup.find("span", class_="attach-code").text == ""


def test_attachment_part():
    text = get_random_string()

    part = AttachmentPart(title="Response body", format="json", text=text)
    soup = BeautifulSoup(str(part), "html.parser")

    section = soup.find("section", class_="attach-part")
    assert section["data-part"] == "Response body"
    assert section["data-format"] == "json"
    # Every part starts hidden; the viewer reveals the one it opens.
    assert section.has_attr("hidden")
    assert section.find("pre", class_="attach-part__body").text == text


def test_attachment_meta():
    label = get_random_string()
    value = get_random_string()

    meta = AttachmentMeta(label=label, value=value, title=value)
    soup = BeautifulSoup(str(meta), "html.parser")

    assert soup.find("em").text.strip() == label

    node = soup.find("span", class_="attach-meta__value")
    assert node.text.strip() == value
    assert node["title"] == value


def test_attachment_body_holds_its_meta_and_every_part():
    parts = "".join(str(AttachmentPart(title="Part %d" % i, format="text", text="body %d" % i))
                    for i in range(3))
    meta = str(AttachmentMeta(label="Status", value="200 OK", title="200 OK"))

    body = AttachmentBody(aid="1-2-0", sname="tests/test_a.py", name="test_thing",
                          title="GET /orders", filename="test_thing-GET-orders",
                          meta=meta, parts=parts)
    soup = BeautifulSoup(str(body), "html.parser")

    payload = soup.find("div", class_="attach-payload")
    assert payload["id"] == "attach-1-2-0"
    assert payload["data-suite"] == "tests/test_a.py"
    assert payload["data-test"] == "test_thing"
    assert payload["data-title"] == "GET /orders"
    assert payload["data-file"] == "test_thing-GET-orders"
    assert payload.has_attr("hidden")

    assert payload.find("div", class_="attach-meta").find("em").text.strip() == "Status"
    assert [node.text for node in payload.findAll("pre", class_="attach-part__body")] == \
           ["body 0", "body 1", "body 2"]


def test_env_row():
    label = get_random_string()
    value = get_random_string()

    env_row = EnvRow(label=label, value=value, title=value)
    soup = BeautifulSoup(str(env_row), "html.parser")

    assert soup.find("span", class_="env-item__label").text.strip() == label

    value_node = soup.find("span", class_="env-item__value")
    assert value_node.text.strip() == value
    assert value_node["title"] == value


def test_coverage_row():
    name = "src/" + get_random_string() + ".py"

    row = CoverageRow(name=name, statements="42", missing="7", branches="4",
                      branch_cell="3/4", percent="83.33", display="83.3",
                      grade="fair", lines="12-15, 88")
    soup = BeautifulSoup(str(row), "html.parser")
    cells = soup.findAll("td")

    assert cells[0].text.strip() == name
    assert cells[0]["title"] == name
    for node, expected in zip(cells[1:4], ["42", "7", "3/4"]):
        assert node.text.strip() == expected

    # The bar is what the eye reads; data-order is what the table sorts on, so
    # 100 cannot end up between 1 and 2 the way the rendered text would.
    assert cells[3]["data-order"] == "4"
    assert cells[4]["data-order"] == "83.33"
    assert cells[4].find("span", class_="cov-bar__value").text.strip() == "83.3%"

    fill = cells[4].find("span", class_="cov-bar__fill")
    assert "cov-bar__fill--fair" in fill["class"]
    assert fill["style"] == "width:83.33%"

    assert cells[5].text.strip() == "12-15, 88"


def test_coverage_row_for_a_file_with_no_branches():
    """A dash, not a 0: this file has no branches to cover, which is not the
    same statement as none of its branches being covered."""
    row = CoverageRow(name="src/a.py", statements="3", missing="0", branches="0",
                      branch_cell="&mdash;", percent="100.00", display="100",
                      grade="strong", lines="")
    soup = BeautifulSoup(str(row), "html.parser")
    cells = soup.findAll("td")

    assert cells[3].text.strip() == "\u2014"
    assert cells[3]["data-order"] == "0"
    assert cells[5].text.strip() == ""


def test_coverage_tile():
    label = get_random_string()
    value = str(get_random_number())

    soup = BeautifulSoup(str(CoverageTile(label=label, value=value)), "html.parser")

    assert soup.find("div", class_="cov-tile__value").text.strip() == value
    assert soup.find("div", class_="cov-tile__label").text.strip() == label


def test_coverage_chip():
    title = get_random_string()

    soup = BeautifulSoup(str(CoverageChip(grade="strong", display="91.4", title=title)),
                         "html.parser")
    button = soup.find("button")

    assert "cov-trigger--strong" in button["class"]
    assert button["title"] == title
    assert button["onclick"] == "openCoverageTab()"
    assert button.find("span").text.strip() == "Test Coverage 91.4%"


def test_report_link():
    url = "https://ci.example.com/job/42"
    label = get_random_string()

    soup = BeautifulSoup(str(ReportLink(label=label, url=url, title=url)), "html.parser")
    link = soup.find("a")

    assert link["href"] == url
    assert link["title"] == url
    assert link.text.strip() == label
    # A new tab, and no window.opener handed to whatever is at the far end.
    assert link["target"] == "_blank"
    assert link["rel"] == ["noopener", "noreferrer"]
    # It must not look like a tab this page can open, or the hash router
    # would try to route to a page that does not exist.
    assert link["class"] == ["tablink", "tablink--out"]


def _hash_map(page):
    """The hash -> tab id table the page routes #anchors through."""
    block = re.search(r"var hashToPageMap = \{(.*?)\};", page, re.S).group(1)

    return dict(re.findall(r"'([\w-]+)'\s*:\s*'(\w+)'", block))


def test_every_nav_link_routes_to_the_tab_it_opens():
    """The two halves of a tab's identity have to agree.

    Renaming this tab's label and hash silently broke the Test Metrics button
    that jumps to it, because the jump found the nav link by its href. Nothing
    failed - the link was still there, it had just stopped being found.
    """
    page = str(HtmlTemplate())

    links = re.findall(r'<a class="tablink" href="#([\w-]+)" onclick="openPage\(\'(\w+)\'', page)
    tabs = set(re.findall(r'<div class="tabcontent" id="(\w+)"', page))
    hashes = _hash_map(page)

    assert links, "no nav links found - the markup moved"

    for anchor, page_id in links:
        assert page_id in tabs, "%s opens a tab that does not exist" % anchor
        assert hashes.get(anchor) == page_id, "#%s does not route to %s" % (anchor, page_id)


def test_every_routed_hash_lands_on_a_real_tab():
    """Aliases included: #attachments still has to reach the renamed tab."""
    page = str(HtmlTemplate())
    tabs = set(re.findall(r'<div class="tabcontent" id="(\w+)"', page))

    for anchor, page_id in _hash_map(page).items():
        assert page_id in tabs, "#%s routes to a tab that does not exist" % anchor


def test_the_api_logs_tab_is_reachable_by_both_of_its_names():
    """#attachments was the hash before the tab was renamed; links were shared."""
    hashes = _hash_map(str(HtmlTemplate()))

    assert hashes["api-logs"] == "attachments"
    assert hashes["attachments"] == "attachments"


def test_template():
    custom_logo = get_random_string()
    execution_time = str(get_random_number())
    title = get_random_string()
    total = str(get_random_number())
    executed = str(get_random_number())
    _pass = str(get_random_number())
    fail = str(get_random_number())
    skip = str(get_random_number())
    error = str(get_random_number())
    xpass = str(get_random_number())
    xfail = str(get_random_number())
    rerun = str(get_random_number())
    suite_metrics_row = get_random_string()
    test_metrics_row = get_random_string()
    date = str(get_random_number())
    test_suites = str(get_random_number())
    test_suite_length = str(get_random_number())
    test_suite_pass = get_random_string()
    test_suites_fail = get_random_string()
    test_suites_skip = str(get_random_number())
    test_suites_xpass = str(get_random_number())
    test_suites_xfail = str(get_random_number())
    test_suites_error = str(get_random_number())
    archive_status = str(get_random_number())
    archive_body_content = get_random_string()
    archive_count = str(get_random_number())
    archives = str(get_random_number())
    max_failure_suite_name_final = get_random_string()
    max_failure_suite_count = str(get_random_number())
    similar_max_failure_suite_count = str(get_random_number())
    max_failure_total_tests = str(get_random_number())
    max_failure_percent = str(get_random_number())
    trends_label = get_random_string()
    tpass = str(get_random_number())
    tfail = str(get_random_number())
    tskip = str(get_random_number())
    attach_screenshot_details = get_random_string()
    attachment_items = get_random_string()
    attachment_store = get_random_string()
    environment_rows = get_random_string()
    environment = get_random_string()
    title_full = get_random_string()

    template_page = HtmlTemplate(
        custom_logo=custom_logo,
        execution_time=execution_time,
        title=title,
        total=total,
        executed=executed,
        _pass=_pass,
        fail=fail,
        skip=skip,
        error=error,
        xpass=xpass,
        xfail=xfail,
        rerun=rerun,
        suite_metrics_row=suite_metrics_row,
        test_metrics_row=test_metrics_row,
        date=date,
        test_suites=test_suites,
        test_suite_length=test_suite_length,
        test_suite_pass=test_suite_pass,
        test_suites_fail=test_suites_fail,
        test_suites_skip=test_suites_skip,
        test_suites_xpass=test_suites_xpass,
        test_suites_xfail=test_suites_xfail,
        test_suites_error=test_suites_error,
        archive_status=archive_status,
        archive_body_content=archive_body_content,
        archive_count=archive_count,
        archives=archives,
        max_failure_suite_name_final=max_failure_suite_name_final,
        max_failure_suite_count=max_failure_suite_count,
        similar_max_failure_suite_count=similar_max_failure_suite_count,
        max_failure_total_tests=max_failure_total_tests,
        max_failure_percent=max_failure_percent,
        trends_label=trends_label,
        tpass=tpass,
        tfail=tfail,
        tskip=tskip,
        attach_screenshot_details=attach_screenshot_details,
        attachment_items=attachment_items,
        attachment_store=attachment_store,
        environment_rows=environment_rows,
        environment=environment,
        title_full=title_full
    )

    soup = BeautifulSoup(str(template_page), "html.parser")

    ### Checking if code-behind parts are really interpolated

    # Found by what it contains rather than by being the last block: the theme
    # tokens and the vendor dark overrides are style blocks too.
    progress_block = next(b for b in soup.find_all("style") if ".progress-bar.downloading" in b.text)
    style_block = f""".progress-bar.downloading {{
                    background: -webkit-linear-gradient(left, var(--status-fail) {max_failure_percent}%,var(--progress-bar) {max_failure_percent}%); /* Chrome10+,Safari5.1+ */
                    background: -ms-linear-gradient(left, var(--status-fail) {max_failure_percent}%,var(--progress-bar) {max_failure_percent}%); /* IE10+ */
                    background: linear-gradient(to right, var(--status-fail) {max_failure_percent}%,var(--progress-bar) {max_failure_percent}%); /* W3C */
                }}"""

    assert progress_block.text.strip() == style_block

    wrimagecard = soup.find("img", id="wrimagecard")
    assert wrimagecard["src"] == custom_logo

    time_taken_label = soup.find("span", class_="time__taken")
    assert time_taken_label.text.strip() == f"Time taken {execution_time}"

    header_title = soup.find("div", class_="header__title")
    assert header_title.find("span", class_="header__title-text").text.strip() == title
    assert header_title["title"] == title_full
    assert header_title.find("span", class_="env-badge").text.strip() == environment

    header_date = soup.find("span", class_="header__date")
    assert header_date.text.strip() == date


    count_block = soup.find("div", class_="total-count-block")
    total_count = count_block.find("span", class_="total__count")
    assert total_count.text.strip() == total
    assert count_block.find("span", class_="total_count__label").text.strip() == "TEST CASES"

    test_metrics = soup.findAll("div", class_="footer-section__data")
    for metric, val in zip(test_metrics, (_pass, fail, skip, xpass, xfail, error, rerun)):
        assert metric.text.strip() == val

    test_suite_length_label = soup.find("div", class_="col-md-8 card border-right").find("div").find("div")
    assert re.search(f"Test Suite\\n\\s+{test_suite_length}", test_suite_length_label.text.strip())

    max_failure_dashboard = soup.find("div", class_="col-md-4 card border-left")
    assert max_failure_dashboard.find("div", class_="tooltip bs-tooltip-top tooltip-dark").find("div", class_="tooltip-inner").text.strip() == max_failure_suite_name_final
    assert max_failure_dashboard.find("p", class_="percentage").text.strip() == f"{max_failure_suite_count} /{max_failure_total_tests} Times"

    suite_metrics_table = soup.findAll("table", id="sm")

    for tbl in suite_metrics_table:
        assert tbl.find("tbody").text.strip() == suite_metrics_row

    archive_status_label = soup.find("div", id="list-example")
    assert archive_status_label.text.strip() == archive_status

    archive_body_content_label = soup.find("div", id="archives").findAll("div")[-1]
    assert archive_body_content_label.text.strip() == archive_body_content

    # By class, not by position: the gallery is no longer the first child of
    # #main-content now that the tab has a heading above it.
    attach_screenshot_details_label = soup.find("div", id="shotGrid")
    assert attach_screenshot_details_label.text.strip() == attach_screenshot_details

    environment_grid = soup.find("div", class_="env-grid")
    assert environment_grid.text.strip() == environment_rows

    assert soup.find("div", id="attachRail").text.strip().startswith(attachment_items)
    assert soup.find("div", id="attachStore").text.strip() == attachment_store

    scripts = soup.findAll("script")
    assert [script for script in scripts if f"data: [{_pass}, {fail}, {skip}, {xpass}, {xfail}, {error}]," in script.text]
    assert [script for script in scripts if f"var passPercent = Math.round(({_pass} / {total}) * 100)" in script.text]
    assert [script for script in scripts if f"for(var i=0; i<{archive_count}; i++)" in script.text and f"var archives = {archives};" in script.text]
    assert [
        script for script in scripts
        if f"labels: {test_suites}," in script.text
           and f"data: {test_suite_pass}" in script.text
           and f"data: {test_suites_fail}" in script.text
           and f"data: {test_suites_skip}" in script.text
           and f"data: {test_suites_xpass}" in script.text
           and f"data: {test_suites_xfail}" in script.text
           and f"data: {test_suites_error}" in script.text
    ]
    assert [script for script in scripts if f"labels : {trends_label}," in script.text
            and f"data : {tpass}" in script.text
            and f"data : {tfail}" in script.text
            and f"data : {tskip}" in script.text
            ]


def test_every_component_fills_every_placeholder_it_declares():
    """A component that is handed all its fields must leave none behind.

    The substitution is a plain string replace, so a field renamed in the
    template and not in the caller leaves a raw `%(name)%` sitting on the page.
    Nothing fails; the report just shows the placeholder to whoever opens it.
    """
    html_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "html_page", "html")

    for entry in sorted(os.listdir(html_dir)):
        # The page itself is filled from the reporter, field by field, and has
        # its own tests above; these are its parts.
        if not entry.endswith(".html") or entry == "template.html":
            continue

        module = importlib.import_module("html_page." + entry[:-5])
        component = getattr(module, "".join(word.capitalize() for word in entry[:-5].split("_")))

        names = re.findall(r"%\((.+?)\)%", open(os.path.join(html_dir, entry), encoding="utf-8").read())
        rendered = str(component(**{name: "x" for name in names}))

        assert "%(" not in rendered, entry


def test_every_component_template_has_a_class_and_the_other_way_round():
    """The two halves of a component have to exist together.

    A template with no class is dead markup; a class with no template raises
    only when something first tries to render it, which is at the end of a run
    somebody has already waited for.
    """
    package_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "html_page")

    templates = {entry[:-5] for entry in os.listdir(os.path.join(package_dir, "html"))
                 if entry.endswith(".html")}
    classes = {entry[:-3] for entry in os.listdir(package_dir)
               if entry.endswith(".py") and entry not in ("__init__.py", "page_decor.py",
                                                          "assets.py", "icon_styles.py")}

    assert templates == classes
