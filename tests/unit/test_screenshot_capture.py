"""Cover the automatic half: finding a browser and photographing it.

test_screenshots.py and test_auto_screenshots.py drive real suites and prove
that a picture reaches the report. What they cannot reach is the recognition
itself, which is written entirely in terms of what an object *can do* - and so
is only really exercised by handing it objects that can do some of it: a driver
whose session has gone, an async page that returns a coroutine, a splinter
browser whose screenshot() writes a file, a Mock that answers every call.

Nothing here imports selenium or playwright, for the same reason the module
does not: the fakes below are the whole point.
"""

import pytest

from pytest_html_reporter import screenshots
from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.screenshots import (
    SHOT_MAX,
    add,
    can_shoot,
    capture,
    handles,
    pending_count,
    png,
    resolved,
    save,
    take_screenshots,
    targets,
)
from pytest_html_reporter.steps import start, stop, take_steps


# A 1x1 png, so nothing here needs a browser to have something to hand over.
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00"
       b"\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc```\x00"
       b"\x00\x00\x04\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82")


@pytest.fixture(autouse=True)
def drained():
    take_screenshots()
    take_steps()
    yield
    take_screenshots()
    take_steps()


# ------------------------------------------------------------- the fakes ---

class Driver:
    """A Selenium driver: get_screenshot_as_png, and it works."""

    def __init__(self, data=PNG):
        self._data = data
        self.calls = 0

    def get_screenshot_as_png(self):
        self.calls += 1
        return self._data


class DeadDriver:
    """A driver whose session has gone - every call raises."""

    def get_screenshot_as_png(self):
        raise RuntimeError("invalid session id")


class Page:
    """A Playwright page: screenshot() returns the bytes."""

    def __init__(self, data=PNG):
        self._data = data

    def screenshot(self):
        return self._data


class AsyncPage:
    """An async page: screenshot() hands back a coroutine nobody can await."""

    def screenshot(self):
        async def _shot():
            return PNG
        return _shot()


class SplinterBrowser:
    """screenshot() writes a file and returns its path; the driver has bytes."""

    def __init__(self):
        self.driver = Driver()

    def screenshot(self):
        return "/tmp/shot.png"


class Context:
    def __init__(self, *pages):
        self.pages = list(pages)


class Browser:
    def __init__(self, *contexts):
        self.contexts = list(contexts)


class Hostile:
    """Attribute access itself raises - a handle already torn down."""

    def __getattribute__(self, name):
        raise RuntimeError("session closed")


class FixtureDef:
    def __init__(self, cached_result):
        self.cached_result = cached_result


class Request:
    def __init__(self, defs):
        self._fixture_defs = defs


class Item:
    """Just enough of a pytest Item for the fixture-reading helpers."""

    def __init__(self, funcargs=None, fixture_defs=None, instance=None):
        self.funcargs = funcargs if funcargs is not None else {}
        self._request = Request(fixture_defs if fixture_defs is not None else {})
        self.instance = instance


# ------------------------------------------------------------ the buffer ---

def test_the_buffer_starts_empty_even_if_something_left_a_non_list_behind():
    ConfigVars._screenshots = "not a list"

    assert pending_count() == 0
    assert take_screenshots() == []


def test_add_files_the_image_against_the_step_that_was_open():
    """The Test Steps tab shows a picture under the step it was taken in."""
    frame = start("Open the cart")
    add(png=PNG, label="page")
    stop()

    entry, = take_screenshots()
    assert entry["step"] == frame["id"]
    assert entry["label"] == "page"
    assert entry["png"] == PNG


def test_add_outside_any_step_is_filed_against_no_step():
    """-1 is every automatic capture: teardown has nothing open by then."""
    add(png=PNG, label="driver")

    entry, = take_screenshots()
    assert entry["step"] == -1


def test_add_stringifies_whatever_label_it_was_given():
    add(png=PNG, label=7)

    assert take_screenshots()[0]["label"] == "7"


def test_taking_the_screenshots_empties_the_buffer():
    """An image nobody claims must not be picked up by the next test."""
    add(png=PNG)

    assert len(take_screenshots()) == 1
    assert take_screenshots() == []
    assert pending_count() == 0


def test_pending_count_is_what_the_running_test_has_produced():
    add(png=PNG)
    add(png=PNG)

    assert pending_count() == 2


# -------------------------------------------------------------- saving ---

def test_save_writes_the_bytes_a_browser_handed_over(tmp_path):
    """Already a png - decoding it only to encode it again is time wasted."""
    path = tmp_path / "shot.png"
    save({"png": PNG}, str(path))

    assert path.read_bytes() == PNG


def test_save_encodes_an_image_that_arrived_decoded(tmp_path):
    from PIL import Image

    path = tmp_path / "shot.png"
    save({"png": None, "image": Image.new("RGB", (1, 1))}, str(path))

    assert path.read_bytes().startswith(b"\x89PNG")


# -------------------------------------------------------------- attach() ---

def test_attach_decodes_the_bytes_it_was_given():
    screenshots.attach(data=PNG)

    entry, = take_screenshots()
    assert entry["label"] == "attached"
    assert entry["image"] is not None


def test_attach_says_which_helper_text_belongs_in():
    """Pillow's 'cannot identify image file' says nothing about the mistake."""
    with pytest.raises(TypeError) as error:
        screenshots.attach(data="a string")

    assert "attach_text()" in str(error.value)
    assert take_screenshots() == []


# ------------------------------------------------------------ reading ---

def test_reading_an_attribute_that_raises_is_not_a_failure():
    assert screenshots._attr(Hostile(), "driver") is None


def test_a_screenshot_call_that_raises_produces_no_picture():
    """A crashed browser is not worth failing a test that already ran over."""
    assert png(DeadDriver()) is None


def test_a_coroutine_is_closed_rather_than_left_to_warn():
    """Unawaited, it prints a warning against the test; the report says nothing."""
    assert png(AsyncPage()) is None


def test_a_coroutine_that_will_not_close_is_still_not_a_picture():
    """Closing it is a courtesy; failing to is not worth raising over."""
    class Stubborn:
        def __await__(self):  # pragma: no cover - never awaited
            yield

        def close(self):
            raise RuntimeError("cannot close")

    class StubbornPage:
        def screenshot(self):
            return Stubborn()

    assert png(StubbornPage()) is None


def test_a_screenshot_call_returning_a_path_is_not_a_picture():
    """splinter's browser.screenshot() writes a file and returns its name."""
    class PathOnly:
        def screenshot(self):
            return "/tmp/shot.png"

    assert png(PathOnly()) is None


def test_empty_bytes_are_not_a_picture():
    assert png(Driver(data=b"")) is None


def test_a_missing_screenshot_method_produces_no_picture():
    assert png(object()) is None


# ------------------------------------------------------------ png() order ---

def test_selenium_is_asked_first():
    driver = Driver()

    assert png(driver) == PNG
    assert driver.calls == 1


def test_the_driver_under_a_wrapper_is_preferred_to_the_wrappers_own_call():
    """splinter's own screenshot() returns a path; its driver returns bytes."""
    assert png(SplinterBrowser()) == PNG


def test_playwright_style_screenshot_is_the_last_resort():
    assert png(Page()) == PNG


def test_a_wrapper_whose_driver_is_itself_is_not_asked_twice():
    class SelfWrapping:
        def __init__(self):
            self.driver = self

        def screenshot(self):
            return PNG

    assert png(SelfWrapping()) == PNG


# ----------------------------------------------------------- can_shoot ---

def test_a_mock_is_never_photographed():
    """It answers every call, so it would be shot on a method it lacks - and
    the call it records may be the very thing the test asserts on."""
    from unittest.mock import MagicMock

    assert can_shoot(MagicMock()) is False


def test_something_with_a_screenshot_call_can_be_shot():
    assert can_shoot(Driver()) is True
    assert can_shoot(Page()) is True


def test_a_wrapper_around_a_driver_can_be_shot():
    class Wrapper:
        def __init__(self):
            self.driver = Driver()

    assert can_shoot(Wrapper()) is True


def test_an_ordinary_value_cannot_be_shot():
    assert can_shoot("a string") is False
    assert can_shoot(None) is False


# ------------------------------------------------------------- targets ---

def test_a_page_is_its_own_target():
    page = Page()

    assert targets(page) == [page]


def test_the_pages_inside_a_context_are_found():
    """A suite driving a context rather than a page never asks for one."""
    first, second = Page(), Page()

    assert targets(Context(first, second)) == [first, second]


def test_the_pages_inside_a_browsers_contexts_are_found():
    page = Page()

    assert targets(Browser(Context(page))) == [page]


def test_nothing_photographable_yields_nothing():
    assert targets(None) == []
    assert targets("a string") == []
    assert targets(Browser()) == []


def test_a_context_holding_something_unphotographable_yields_nothing():
    assert targets(Context("not a page")) == []


def test_the_search_stops_rather_than_descending_for_ever():
    deep = Browser(Context(Page()))

    assert targets(deep, depth=3) == []


# ------------------------------------------------------------ resolved ---

def test_a_fixture_that_already_ran_is_read_out_of_the_request_cache():
    """A pytest-bdd test takes no fixtures at all - the steps ask as they run."""
    page = Page()
    item = Item(fixture_defs={"page": FixtureDef((page, None, None))})

    assert resolved(item) == {"page": page}


def test_a_fixture_that_raised_has_no_value_to_photograph():
    item = Item(fixture_defs={"page": FixtureDef((None, None, RuntimeError("boom")))})

    assert resolved(item) == {}


def test_a_fixture_that_never_ran_is_not_built_to_be_photographed():
    """getfixturevalue would start a browser at teardown just to shoot it."""
    item = Item(fixture_defs={"page": FixtureDef(None)})

    assert resolved(item) == {}


def test_a_cached_result_of_the_wrong_shape_is_ignored():
    item = Item(fixture_defs={"page": FixtureDef(("value", None))})

    assert resolved(item) == {}


def test_an_item_with_no_request_resolves_nothing():
    class Bare:
        pass

    assert resolved(Bare()) == {}


# ------------------------------------------------------------- handles ---

def test_the_known_fixture_names_come_first():
    """page before the rest: it is the one worth photographing."""
    page, driver = Page(), Driver()
    item = Item(funcargs={"tmp_path": "/tmp", "driver": driver, "page": page})

    assert [name for name, _ in handles(item)][:2] == ["page", "driver"]


def test_everything_else_the_test_was_handed_is_offered_too():
    """A suite whose browser fixture is called something else is covered."""
    item = Item(funcargs={"my_browser": Driver()})

    assert [name for name, _ in handles(item)] == ["my_browser"]


def test_the_same_page_named_and_cached_is_offered_once():
    page = Page()
    item = Item(funcargs={"page": page},
                fixture_defs={"page": FixtureDef((page, None, None))})

    assert [name for name, _ in handles(item)] == ["page"]


def test_a_unittest_driver_on_self_is_found():
    """setUp puts it on the instance rather than in a fixture."""
    class Suite:
        def __init__(self):
            self.driver = Driver()

    item = Item(instance=Suite())

    assert [name for name, _ in handles(item)] == ["driver"]


def test_an_item_holding_nothing_offers_nothing():
    assert handles(Item()) == []


def test_funcargs_of_the_wrong_type_are_ignored():
    item = Item()
    item.funcargs = "not a dict"

    assert handles(item) == []


# ------------------------------------------------------------- capture ---

def test_capture_photographs_the_browser_the_test_was_holding():
    taken = capture(Item(funcargs={"driver": Driver()}))

    assert taken == 1
    entry, = take_screenshots()
    assert entry["png"] == PNG
    assert entry["label"] == "driver"


def test_a_page_reached_through_three_fixtures_is_photographed_once():
    """Asking for page, context and browser is the ordinary Playwright test."""
    page = Page()
    context = Context(page)
    item = Item(funcargs={"page": page, "context": context,
                          "browser": Browser(context)})

    assert capture(item) == 1
    assert len(take_screenshots()) == 1


def test_capture_stops_at_the_limit():
    """A row of thumbnails stops being readable long before it stops growing."""
    item = Item(funcargs={"a": Driver(), "b": Driver(), "c": Driver(),
                          "d": Driver(), "e": Driver(), "f": Driver()})

    assert capture(item) == SHOT_MAX
    assert len(take_screenshots()) == SHOT_MAX


def test_capture_honours_a_lower_limit():
    item = Item(funcargs={"a": Driver(), "b": Driver(), "c": Driver()})

    assert capture(item, limit=2) == 2


def test_a_browser_that_cannot_be_photographed_produces_nothing():
    assert capture(Item(funcargs={"driver": DeadDriver()})) == 0
    assert take_screenshots() == []


def test_a_test_holding_no_browser_produces_nothing():
    assert capture(Item(funcargs={"tmp_path": "/tmp", "count": 2})) == 0
    assert take_screenshots() == []
