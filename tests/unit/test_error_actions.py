"""Cover the controls that sit beside a failure message.

The cell has room for about fifty characters of an error, so a row on its own
has never been enough to triage from: the rest of the message had to be opened,
and then selected by hand before it could be pasted anywhere. The expand button
opens the whole thing in the report's own panel and the copy button puts it on
the clipboard without opening anything at all. The third button copies the
`pytest` line that runs that one test again, which is the step that followed
reading the error often enough to be worth a click of its own, and the fourth
copies a link to the row itself.

Whichever was pressed says so twice: a tick where its icon was, and a word in
the middle of the page naming which of the three things is now on the clipboard
- because the tick is the same tick for all of them, and it is 22 pixels wide at
the end of a row somebody is reading the other end of.

All four fold behind the `...`, and come back out along the row when it is
pressed: forty rows of four buttons is 160 of them on screen for the one
somebody wants.
"""

import os

import pytest
from bs4 import BeautifulSoup

from html_page.floating_error import FloatingError
from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.html_reporter import HTMLReporter

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


def _record(suite, name, status="FAIL", message="", index=0):
    return {
        "suite_name": suite,
        "test_name": name,
        "nodeid": suite + "::" + name,
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


def _actions(soup):
    return soup.findAll("span", class_="msg-actions")


def _template():
    with open(TEMPLATE, encoding="utf-8") as page:
        return page.read()


LONG = "assert 1 == 2\n" + "".join("  line %d\n" % i for i in range(40))


# --------------------------------------------------------------------------
# what the row carries
# --------------------------------------------------------------------------

def test_the_row_carries_the_whole_error_not_the_preview():
    """The cell shows the first fifty characters; both controls get all of it."""
    soup = _rows([_record("tests/test_a.py", "test_one", message=LONG)])
    actions = _actions(soup)[0]

    assert actions["data-error"] == LONG
    assert len(actions["data-error"]) > 50


def test_the_row_names_the_test_the_panel_will_be_opened_for():
    soup = _rows([_record("tests/test_a.py", "test_one", message=LONG)])
    actions = _actions(soup)[0]

    assert actions["data-suite"] == "tests/test_a.py"
    assert actions["data-test"] == "test_one"


def test_every_failing_row_carries_its_own_error():
    soup = _rows([
        _record("tests/test_a.py", "test_one", message="first " + LONG, index=0),
        _record("tests/test_a.py", "test_two", status="PASS", message="", index=1),
        _record("tests/test_b.py", "test_three", message="third " + LONG, index=2),
    ])

    assert [node["data-error"] for node in _actions(soup)] == ["first " + LONG, "third " + LONG]


# --------------------------------------------------------------------------
# the command that runs the row again
# --------------------------------------------------------------------------

def test_the_row_carries_the_command_that_runs_that_test_again():
    soup = _rows([_record("tests/test_a.py", "test_one", message=LONG)])

    assert _actions(soup)[0]["data-cmd"] == "pytest tests/test_a.py::test_one"


def test_the_command_comes_from_the_node_id_not_from_the_two_names_on_show():
    """A test inside a class is listed under its own name; pytest wants the
    class in front of it, and the node id is the only place that has it."""
    record = _record("tests/test_a.py", "test_one", message=LONG)
    record["nodeid"] = "tests/test_a.py::TestAuth::test_one"

    soup = _rows([record])

    assert _actions(soup)[0]["data-cmd"] == "pytest tests/test_a.py::TestAuth::test_one"


def test_a_parametrised_test_is_quoted_so_a_shell_cannot_read_its_brackets():
    """Pasted bare, `test_one[a b]` is two arguments to bash and a glob that
    matches nothing to zsh."""
    record = _record("tests/test_a.py", "test_one[a b]", message=LONG)
    record["nodeid"] = "tests/test_a.py::test_one[a b]"

    soup = _rows([record])

    assert _actions(soup)[0]["data-cmd"] == "pytest 'tests/test_a.py::test_one[a b]'"


def test_a_row_with_no_node_id_offers_no_command():
    """`pytest` on its own runs everything, which is not what the button says."""
    record = _record("tests/test_a.py", "test_one", message=LONG)
    del record["nodeid"]

    soup = _rows([record])

    assert _actions(soup)[0]["data-cmd"] == ""


# --------------------------------------------------------------------------
# which rows get them
# --------------------------------------------------------------------------

def test_a_passing_row_offers_nothing():
    """Nothing to copy, and a button that copies an empty string reads as a bug."""
    soup = _rows([_record("tests/test_a.py", "test_one", status="PASS", message="")])

    assert _actions(soup) == []


def test_a_message_of_pure_whitespace_counts_as_nothing_to_copy():
    soup = _rows([_record("tests/test_a.py", "test_one", message="  \n\n  ")])

    assert _actions(soup) == []


def test_a_skipped_row_keeps_its_reason():
    soup = _rows([_record("tests/test_a.py", "test_one", status="SKIP",
                          message="Skipped: needs a database")])

    assert _actions(soup)[0]["data-error"] == "Skipped: needs a database"


def test_a_message_that_fits_is_copyable_but_has_nothing_to_expand_to():
    soup = _rows([_record("tests/test_a.py", "test_one", message="boom")])
    actions = _actions(soup)[0]

    assert actions["data-full"] == ""
    assert actions["data-error"] == "boom"


def test_a_message_that_was_cut_offers_the_panel():
    soup = _rows([_record("tests/test_a.py", "test_one", message=LONG)])

    assert _actions(soup)[0]["data-full"] == "1"


# --------------------------------------------------------------------------
# the text stays text
# --------------------------------------------------------------------------

def test_a_message_holding_quotes_cannot_break_out_of_the_attribute():
    message = 'assert "a" == \'b\' <script>alert(1)</script> ' + "x" * 60

    soup = _rows([_record("tests/test_a.py", "test_one", message=message)])

    # Read back through the parser: had the quoting failed there would be no
    # attribute to read, or a stray tag beside it.
    assert _actions(soup)[0]["data-error"] == message
    assert soup.find("script") is None


def test_a_message_shaped_like_a_placeholder_is_not_substituted():
    message = "%(archive_status)% went missing " + "y" * 60

    soup = _rows([_record("tests/test_a.py", "test_one", message=message)])

    assert "%(archive_status)%" not in ConfigVars._test_metrics_content
    assert _actions(soup)[0]["data-error"] == message


def test_the_controls_add_nothing_at_all_to_the_cell_the_table_exports():
    """Search, CSV, Excel and print are all built from cell text. The error
    rides in an attribute and every button is an icon, so all four get the cut
    message and the marker that says it was cut - not a traceback per row."""
    soup = _rows([_record("tests/test_a.py", "test_one", message=LONG)])
    cell = soup.findAll("td")[5]

    assert _actions(soup)[0].get_text(strip=True) == ""
    assert LONG not in cell.get_text()
    assert cell.get_text(strip=True).endswith("…")


# --------------------------------------------------------------------------
# saying what the click did
# --------------------------------------------------------------------------

def test_each_button_names_which_of_the_three_things_it_copied():
    """The tick that replaces the icon is the same tick for all three, and it
    is 22 pixels wide at the end of a row somebody is reading the other end of.
    The word in the middle of the page is what says which one landed."""
    page = _template()

    assert "'Error copied'" in page
    assert "'Command copied'" in page
    assert "'Link copied'" in page


def test_a_browser_that_refused_the_clipboard_says_what_to_press_instead():
    """Otherwise a reader is left with a button that did nothing and no idea
    why - which is what happens to the file:// clipboard in some browsers."""
    assert "'Press Ctrl+C to copy'" in _template()


def test_the_panel_shows_what_went_onto_the_clipboard():
    """The click is confirmed by the thing itself rather than by a word about
    it - the error, the command or the link, in the face it was written in."""
    page = _template()

    assert 'id="copyToastBody"' in page
    assert "body.textContent = preview.slice(0, COPY_TOAST_PREVIEW);" in page
    # `text` is what was put on the clipboard, so the panel and the clipboard
    # cannot end up showing two different things.
    assert "showCopyToast(copied ? (label || 'Copied') : 'Press Ctrl+C to copy', copied, text);" in page


def test_more_than_fits_fades_out_rather_than_stopping_flat():
    """A traceback cut off square reads as the end of the message. The panel
    holds four lines and dissolves the rest - the same thing a cut error message
    does in the table it was copied from."""
    page = _template()
    rule = page.split(".copy-toast__body {", 1)[1].split("}", 1)[0]

    assert "max-height: 5.9em;" in rule
    assert "overflow: hidden;" in rule
    assert "mask-image: linear-gradient(to bottom, #000 55%, transparent 100%);" in page
    # Whether it overran is a question only the laid-out box can answer.
    assert "body.scrollHeight > body.clientHeight + 1" in page


def test_the_traceback_is_not_read_out_over_the_news():
    """The panel is a live region: "Error copied" is what a screen reader should
    announce, not the forty lines that follow it."""
    page = _template()

    assert '<pre class="copy-toast__body" id="copyToastBody" aria-hidden="true">' in page


def test_a_failed_copy_shows_no_content_at_all():
    """Nothing reached the clipboard, so showing what did not go there beside
    "Press Ctrl+C" would say two opposite things at once."""
    page = _template()

    assert "var preview = copied ? String(content || '').replace(/\\s+$/, '') : '';" in page


def test_the_message_takes_itself_away_and_a_second_copy_restarts_it():
    """Two of these stacking would cover the table, and a message left up would
    claim the clipboard still holds what that row put there."""
    body = _template().split("function showCopyToast", 1)[1].split("function copyFromRow", 1)[0]

    assert "window.clearTimeout(copyToastTimer);" in body
    assert "classList.remove('is-on');" in body


def test_the_message_is_announced_as_well_as_drawn():
    """`role="status"` is what has a screen reader read the copy out; the tick
    on the button never said anything to anyone not looking at it."""
    assert 'id="copyToast" role="status" aria-live="polite"' in _template()


def test_the_message_cannot_be_clicked_and_cannot_be_clicked_through():
    """It sits over the middle of the table for a moment, and the row
    underneath has to stay live the whole time."""
    rule = _template().split(".copy-toast {", 1)[1].split("}", 1)[0]

    assert "pointer-events: none;" in rule


# --------------------------------------------------------------------------
# folded away until they are asked for
# --------------------------------------------------------------------------

def test_the_row_rests_as_one_button():
    """A table of forty failures would otherwise carry 160 buttons for the one
    somebody wants."""
    soup = _rows([_record("tests/test_a.py", "test_one", message=LONG)])
    actions = _actions(soup)[0]

    folded = actions.findAll("button", class_="msg-btn--action")

    assert actions.find("button", class_="msg-toggle") is not None
    assert [button["title"] for button in folded] == [
        "Show the full error", "Copy the full error",
        "Copy the command that runs this test again", "Copy a link to this test"]


def test_the_four_are_in_the_markup_the_whole_time():
    """Hidden by width and opacity rather than by `display`, which cannot be
    transitioned - and a button with no box has no width to animate."""
    rule = _template().split(".msg-actions .msg-btn--action {", 1)[1].split("}", 1)[0]

    assert "width: 0;" in rule
    assert "opacity: 0;" in rule
    assert "display: none" not in rule
    # And nothing to tab into or click while they are folded away.
    assert "pointer-events: none;" in rule


def test_the_strip_travels_to_the_next_line_rather_than_reappearing_on_it():
    """Four buttons wider than the line has left, and the strip wraps - which is
    the right thing to do and a jump to watch happen. The widths settle in one
    step, so the move is known before it is made and can be animated."""
    page = _template()

    assert "function slideRowActions(actions, from) {" in page
    assert "var dx = from.left - to.left;" in page
    assert "actions.style.transform = 'translate(' + dx + 'px, ' + dy + 'px)';" in page
    # A layout read between the two writes, or the browser coalesces them and
    # the strip is simply where it ended up.
    assert "void actions.offsetWidth;" in page


def test_the_widths_are_taken_in_one_step_so_the_line_only_wraps_once():
    """Growing them reflowed the cell on every frame, so a strip with no room
    left jumped to the next line part-way through the animation, at whichever
    frame it stopped fitting."""
    rule = _template().split(".msg-actions .msg-btn--action {", 1)[1].split("}", 1)[0]
    transition = rule.split("transition:", 1)[1]

    assert "opacity" in transition
    assert "transform" in transition
    assert "width" not in transition


def test_they_come_out_one_after_another():
    """Four buttons appearing together under the pointer reads as a flicker; a
    strip unfolding reads as one movement."""
    page = _template()

    assert ".msg-actions.is-open .msg-btn--action:nth-of-type(3) { transition-delay: 0.03s; }" in page
    assert ".msg-actions.is-open .msg-btn--action:nth-of-type(5) { transition-delay: 0.09s; }" in page


def test_only_one_row_is_ever_open():
    """Four strips left open down a page is the clutter they were folded away to
    avoid. A click anywhere else, or Escape, shuts them all."""
    page = _template()
    body = page.split("function toggleRowActions(actions) {", 1)[1].split("function closeRowActions", 1)[0]

    assert "closeRowActions();" in body
    assert "if (!near) closeRowActions();" in page
    assert "toggleLogs(false);\n                        closeRowActions();" in page


def test_the_toggle_says_whether_it_is_open():
    """A button that changes what is on screen has to say so to a reader who
    cannot see the change."""
    page = _template()

    assert 'aria-expanded="false"' in str(FloatingError(full_msg="boom", has_full="", cmd="", sname="s", name="n"))
    assert "setAttribute('aria-expanded', 'true')" in page
    assert "setAttribute('aria-expanded', 'false')" in page


# --------------------------------------------------------------------------
# a message that was cut says so by fading out
# --------------------------------------------------------------------------

def test_the_tail_of_a_cut_message_is_split_off_to_be_faded():
    """A gradient can only be painted onto an element, so the characters that
    fade have to be one of their own."""
    soup = _rows([_record("tests/test_a.py", "test_one", message=LONG)])
    cell = soup.findAll("td")[5]

    faded = cell.find("span", class_="msg-fade").text

    assert len(faded) == HTMLReporter.FADE_TAIL
    # Head and tail are the fifty characters the cell has always held, split -
    # nothing is dropped between them and nothing is shown twice.
    assert cell.get_text().split("…")[0].strip() == LONG[:50].strip()


def test_a_message_that_fits_fades_nowhere():
    """Nothing was cut, so there is nothing to say has been."""
    soup = _rows([_record("tests/test_a.py", "test_one", message="boom")])
    cell = soup.findAll("td")[5]

    assert cell.find("span", class_="msg-fade").text == ""
    assert cell.find("span", class_="msg-cut").text == ""
    assert "…" not in cell.get_text()


def test_the_exports_still_carry_a_marker_the_fade_cannot_travel_as():
    """A CSV and a print-out hold the cell's text, and a message cut short with
    nothing to say so is a trap in a file somebody reads a week later."""
    soup = _rows([_record("tests/test_a.py", "test_one", message=LONG)])
    marker = soup.findAll("td")[5].find("span", class_="msg-cut")

    assert marker.text == "…"
    # Text for the exports, never drawn: the fade is what says it on screen.
    assert ".metrics-card td .msg-cut {\n                    display: none;" in _template()


def test_the_fade_and_the_expand_button_agree_on_what_was_cut():
    """Or a message fades out and then opens the panel on the same fifty
    characters it was already showing."""
    fits = _rows([_record("tests/test_a.py", "test_one", message="x" * 40)])
    cut = _rows([_record("tests/test_a.py", "test_one", message="x" * 400)])

    assert fits.findAll("td")[5].find("span", class_="msg-fade").text == ""
    assert _actions(fits)[0]["data-full"] == ""

    assert cut.findAll("td")[5].find("span", class_="msg-fade").text != ""
    assert _actions(cut)[0]["data-full"] == "1"


def test_the_gradient_names_its_colour_rather_than_saying_currentcolor():
    """Painting text with a background means `color: transparent`, and
    `currentcolor` inside the gradient then resolves to exactly that - a fade
    from nothing to nothing, which is a message that stops eight characters
    early with no sign it was ever cut."""
    rule = _template().split(".metrics-card td .msg-fade {", 1)[1].split("}", 1)[0]

    assert "var(--text-body)" in rule
    assert "currentcolor" not in rule
    assert "background-clip: text;" in rule
