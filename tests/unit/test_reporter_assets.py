"""Cover what the reporter does with a test's images and attachments.

These run at the end of every test, and both are drains: whatever is in the
buffer belongs to the test being recorded and must not still be there for the
next one. That rule is the one worth pinning, because breaking it produces a
report that is wrong rather than a report that fails - somebody else's
screenshot on your row, with nothing anywhere saying so.

The naming is pinned for the same reason. Two shards that name their first
image the same thing overwrite each other's pictures in a shared folder, and
the merge has no way to notice.
"""

import pytest

from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.html_reporter import HTMLReporter
from pytest_html_reporter.attachments import attach_json, take_attachments
from pytest_html_reporter.screenshots import add
from pytest_html_reporter.steps import take_steps


PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00"
       b"\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc```\x00"
       b"\x00\x00\x04\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82")


class _FakePluginManager:
    def hasplugin(self, name):
        return False


class _FakeConfig:
    def __init__(self, options=None):
        self.pluginmanager = _FakePluginManager()
        self._options = options or {}

    def getoption(self, name, default=None):
        return self._options.get(name, default)

    def getini(self, name):
        raise ValueError(name)


_TOUCHED = ("_screenshots", "_attachments", "_attachment_store",
            "_attachment_items", "_suite_name", "_test_name",
            "_current_error", "_steps")


@pytest.fixture(autouse=True)
def _isolate():
    saved = {name: getattr(ConfigVars, name, None) for name in _TOUCHED}
    ConfigVars._screenshots = []
    ConfigVars._attachments = []
    ConfigVars._attachment_store = ""
    ConfigVars._attachment_items = ""
    ConfigVars._suite_name = "tests/test_cart.py"
    ConfigVars._test_name = "test_add"
    ConfigVars._current_error = ""
    take_steps()
    yield
    take_steps()
    for name, value in saved.items():
        setattr(ConfigVars, name, value)


def _reporter(tmp_path, **options):
    return HTMLReporter(str(tmp_path), "", _FakeConfig(options))


# ------------------------------------------------------- screenshot_name ---

def test_two_images_from_one_process_are_never_named_the_same(tmp_path):
    """Milliseconds alone collided - two tests can finish inside one."""
    reporter = _reporter(tmp_path)

    assert reporter.screenshot_name() != reporter.screenshot_name()


def test_the_worker_is_in_the_name_so_two_of_them_cannot_collide(tmp_path):
    reporter = _reporter(tmp_path)
    reporter.worker_id = "gw3"

    assert "-gw3-" in reporter.screenshot_name()


def test_a_serial_run_names_its_images_without_a_worker(tmp_path):
    reporter = _reporter(tmp_path)
    reporter.worker_id = ""

    assert reporter.screenshot_name().count("-") == 1


# ----------------------------------------------------- collect_screenshots ---

def test_a_pending_image_is_written_out_and_described(tmp_path):
    reporter = _reporter(tmp_path)
    add(png=PNG, label="page")

    shots = reporter.collect_screenshots()

    assert len(shots) == 1
    written = tmp_path / "pytest_screenshots" / (shots[0]["name"] + ".png")
    assert written.read_bytes() == PNG


def test_the_description_carries_what_the_row_and_the_card_show(tmp_path):
    reporter = _reporter(tmp_path)
    add(png=PNG, label="driver")

    # Set here rather than in the fixture: this suite runs under the plugin
    # itself, whose own makereport hook rewrites _suite_name as each test goes by.
    ConfigVars._suite_name = "tests/test_cart.py"
    ConfigVars._test_name = "test_add"
    ConfigVars._current_error = "AssertionError: nope"

    shot, = reporter.collect_screenshots()

    assert shot["suite"] == "test_cart"
    assert shot["test"] == "test_add"
    assert shot["error"] == "AssertionError: nope"
    assert shot["label"] == "driver"


def test_an_automatic_capture_is_filed_against_no_step(tmp_path):
    """Every automatic one is taken from teardown, with nothing open."""
    reporter = _reporter(tmp_path)
    add(png=PNG)

    assert reporter.collect_screenshots()[0]["step"] == -1


def test_the_buffer_is_drained_so_the_next_test_cannot_claim_the_image(tmp_path):
    reporter = _reporter(tmp_path)
    add(png=PNG)

    reporter.collect_screenshots()

    assert reporter.collect_screenshots() == []


def test_a_test_that_took_no_picture_describes_none(tmp_path):
    assert _reporter(tmp_path).collect_screenshots() == []


def test_several_images_from_one_test_all_survive(tmp_path):
    reporter = _reporter(tmp_path)
    add(png=PNG, label="page")
    add(png=PNG, label="driver")

    shots = reporter.collect_screenshots()

    assert len(shots) == 2
    assert len({shot["name"] for shot in shots}) == 2


def test_a_shard_files_its_images_under_its_own_directory(tmp_path):
    """Shards sharing one folder would overwrite each other's pictures."""
    reporter = _reporter(tmp_path)
    reporter.shard_id = "gw0"
    add(png=PNG)

    shot, = reporter.collect_screenshots()

    assert (tmp_path / "shards" / "gw0" / "pytest_screenshots"
            / (shot["name"] + ".png")).exists()


# --------------------------------------------------------------- shot_tip ---

def test_a_single_picture_row_says_only_which_test_it_is(tmp_path):
    """Naming the fixture too would be a tooltip repeating the row."""
    reporter = _reporter(tmp_path)

    assert reporter.shot_tip({"test": "test_add", "label": "page"}, 1) == "test_add"


def test_a_row_of_several_pictures_says_which_is_which(tmp_path):
    reporter = _reporter(tmp_path)

    tip = reporter.shot_tip({"test": "test_add", "label": "page"}, 2)

    assert "test_add" in tip
    assert "page" in tip


def test_a_picture_with_no_label_says_only_the_test(tmp_path):
    reporter = _reporter(tmp_path)

    assert reporter.shot_tip({"test": "test_add", "label": ""}, 2) == "test_add"


# ------------------------------------------------------- attach_test_data ---

def _attachment(title="GET /cart", text='{"items": 2}'):
    """Built through the public API, so the shape cannot drift from the real one."""
    take_attachments()
    attach_json(text, name=title)
    record, = take_attachments()
    record["meta"] = [["Method", "GET"], ["Status", "200"]]
    record["code"] = "200"

    return record


def test_a_tests_attachments_are_parked_outside_the_table(tmp_path):
    """A response body in a cell would be swept into the search index and
    into every CSV, Excel and print export."""
    reporter = _reporter(tmp_path)
    record = {"suite_name": "tests/test_cart.py", "test_name": "test_add",
              "attachments": [_attachment()]}

    assert reporter.attach_test_data(record, "row-1") == 1
    assert "GET /cart" in ConfigVars._attachment_store
    assert ConfigVars._attachment_items


def test_every_attachment_gets_an_id_of_its_own(tmp_path):
    reporter = _reporter(tmp_path)
    record = {"suite_name": "s", "test_name": "t",
              "attachments": [_attachment("first"), _attachment("second")]}

    assert reporter.attach_test_data(record, "row-1") == 2
    assert "row-1-0" in ConfigVars._attachment_items
    assert "row-1-1" in ConfigVars._attachment_items


def test_a_payload_cannot_smuggle_markup_into_the_page(tmp_path):
    reporter = _reporter(tmp_path)
    attachment = _attachment(text="<script>alert(1)</script>")
    record = {"suite_name": "s", "test_name": "t", "attachments": [attachment]}

    reporter.attach_test_data(record, "row-1")

    assert "<script>alert(1)</script>" not in ConfigVars._attachment_store


def test_a_test_with_no_attachments_parks_nothing(tmp_path):
    reporter = _reporter(tmp_path)

    assert reporter.attach_test_data({"suite_name": "s", "test_name": "t"}, "row-1") == 0
    assert ConfigVars._attachment_store == ""


# --------------------------------------------------- attachment_search_text ---

def test_the_search_matches_the_test_the_title_and_every_meta_value(tmp_path):
    reporter = _reporter(tmp_path)
    record = {"suite_name": "tests/test_cart.py", "test_name": "test_add"}

    text = reporter.attachment_search_text(record, _attachment())

    assert "test_add" in text
    assert "get /cart" in text
    assert "200" in text


def test_the_payloads_are_not_repeated_into_the_search_attribute(tmp_path):
    """They are thousands of characters each; repeating them would double the
    size of the file to no end."""
    reporter = _reporter(tmp_path)
    record = {"suite_name": "s", "test_name": "t"}

    text = reporter.attachment_search_text(record, _attachment())

    assert "items" not in text


def test_the_search_text_is_lowercased_so_typing_matches_either_way(tmp_path):
    reporter = _reporter(tmp_path)
    record = {"suite_name": "S", "test_name": "TEST_Add"}

    assert reporter.attachment_search_text(record, _attachment()) == \
        reporter.attachment_search_text(record, _attachment()).lower()
