import re
from datetime import date

from bs4 import BeautifulSoup

from html_page.archive_body import ArchiveBody
from html_page.archive_row import ArchiveRow
from html_page.floating_error import FloatingError
from html_page.screenshot_details import ScreenshotDetails
from html_page.suite_row import SuiteRow
from html_page.template import HtmlTemplate
from html_page.test_row import TestRow
from tests.unit.helper import get_random_number, get_random_string


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
    runt = str(get_random_number())
    full_msg = get_random_string()

    floating_error = FloatingError(runt=runt, full_msg=full_msg)

    soup = BeautifulSoup(str(floating_error), "html.parser")

    error_link = soup.find("a", href=f"#myModal-{runt}")

    assert error_link
    assert error_link.text == "(...)"

    error_container = soup.find("div", id=f"myModal-{runt}")

    assert error_container
    assert soup.find("p").text.strip() == full_msg


def test_screenshot_details():
    screen_name = get_random_string()
    ts = get_random_string()
    tc = get_random_string()
    te = get_random_string()

    screenshot_details = ScreenshotDetails(ts=ts, tc=tc, te=te,
                                           screen_name=screen_name)
    soup = BeautifulSoup(str(screenshot_details), "html.parser")

    screenshot_link = soup.find("a", class_="video")
    screen_path = f"pytest_screenshots/{screen_name}.png"
    assert screenshot_link["href"] == screen_path
    assert screenshot_link["style"] == f"background-image: url('{screen_path}');"
    assert screenshot_link["data-caption"] == f"SUITE: {ts} :: SCENARIO: {tc}"

    tc_row = soup.find(class_="video-hover-desc video-hover-small")
    assert tc_row.findAll("span")[0].text.strip() == tc
    assert tc_row.findAll("span")[1].text.strip() == te

    ts_p = soup.find("p", class_="text-desc")
    assert re.search(f"{ts}[\n\s]+{te}", ts_p.text.strip()), ts_p.text.strip()
    assert ts_p.find("strong").text.strip() == ts

    video_description = soup.find("div", id="Video-desc-01")
    assert video_description.find("h2").text.strip() == tc
    assert re.search(f"{ts}[\n\s]+{te}", video_description.find("p").text.strip())
    assert video_description.find("strong").text.strip() == ts


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
    floating_error_text = get_random_string()

    test_row = TestRow(sname=sname, name=name, stat=stat, dur=dur, msg=msg, floating_error_text=floating_error_text)
    soup = BeautifulSoup(str(test_row), "html.parser")

    cells = soup.findAll("td")

    for node, expected in zip(cells[:-1], [sname, name, stat, dur]):
        assert node.text.strip() == expected

    assert re.search(f"{msg}[\s\n]*{floating_error_text}", cells[-1].text.strip())

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
        attach_screenshot_details=attach_screenshot_details
    )

    soup = BeautifulSoup(str(template_page), "html.parser")

    ### Checking if code-behind parts are really interpolated

    last_style_block = soup.findAll("style")[-1]
    style_block = f""".progress-bar.downloading {{
                    background: -webkit-linear-gradient(left, #fc6665 {max_failure_percent}%,#50597b {max_failure_percent}%); /* Chrome10+,Safari5.1+ */
                    background: -ms-linear-gradient(left, #fc6665 {max_failure_percent}%,#50597b {max_failure_percent}%); /* IE10+ */
                    background: linear-gradient(to right, #fc6665 {max_failure_percent}%,#50597b {max_failure_percent}%); /* W3C */
                }}"""

    assert last_style_block.text.strip() == style_block

    wrimagecard = soup.find("img", id="wrimagecard")
    assert wrimagecard["src"] == custom_logo

    time_taken_label = soup.find("span", class_="time__taken")
    assert time_taken_label.text.strip() == f"Time taken {execution_time}"

    header_title = soup.find("div", class_="header__title")
    assert header_title.text.strip() == title

    header_date = soup.find("span", class_="header__date")
    assert header_date.text.strip() == date

    total_count = soup.find("span", class_="total__count")
    assert total_count.text.strip() == total

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

    attach_screenshot_details_label = soup.find("div", id="main-content").find("div").find("div")
    assert attach_screenshot_details_label.text.strip() == attach_screenshot_details

    scripts = soup.findAll("script")
    assert [script for script in scripts if f"var x = parseInt({total});" in script.text]
    assert [script for script in scripts if f"data: [{_pass}, {fail}, {skip}, {xpass}, {xfail}, {error}]," in script.text]
    assert [script for script in scripts if f"var passPercent = Math.round(({_pass} / {total}) * 100)" in script.text]
    assert [script for script in scripts if f"for(var i=0; i<={archive_count}; i++)" in script.text and f"var archives = {archives};" in script.text]
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
