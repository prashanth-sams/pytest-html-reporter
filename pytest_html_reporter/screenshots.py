"""Screenshots: the ones a test hands over, and the ones nobody asked for.

``attach`` is the explicit half - the test takes the picture and gives it to
the report. The rest of this module is the automatic half: when a test is over
the reporter looks for a browser the test was still holding and photographs it
itself, so a suite that has never heard of this package still gets a picture of
the page its assertion failed on.

Nothing here imports selenium or playwright. A browser is recognised by what it
can do rather than by what it is, which is why the two everybody uses work out
of the box - and why appium, splinter, or a driver wrapper written in-house
work for the same reason.

The buffer lives on ConfigVars beside the attachments and the steps, and is
drained by every finished test whatever the mode: an image nobody claims must
not be left lying around for the next test to pick up and present as its own.
"""

import inspect
from io import BytesIO

from PIL import Image

from pytest_html_reporter.const_vars import ConfigVars


# When the reporter takes a picture nobody asked for.
MODES = ("failed", "all", "none")

# How many browsers one test is photographed through. A test driving more than
# a handful at once is doing something unusual, and a row of thumbnails stops
# being readable long before it stops being generated.
SHOT_MAX = 4

# The fixture names looked at first, in this order. A Playwright test is
# usually handed the page, the context and the browser at once, and the page is
# the one worth photographing; every other fixture the test named is looked at
# after these, so a suite whose browser fixture is called something else is
# covered too.
FIXTURES = (
    "page",             # pytest-playwright
    "driver",           # the name almost every Selenium suite uses
    "browser",          # splinter, playwright
    "context",          # playwright
    "selenium",         # pytest-selenium
    "sb",               # seleniumbase
    "webdriver",
    "session_browser",  # pytest-splinter
)

# What a screenshot call is spelled, in the order they are tried.
SHOTS = ("get_screenshot_as_png", "screenshot")

# The one thing ruled out by what it is rather than by what it can do. A Mock
# answers every call ever made to it, screenshot calls included, so it would be
# photographed on the strength of a method it does not have - and calling it
# records a call the test may well be asserting on afterwards.
MOCKS = ("unittest.mock", "mock")


# ------------------------------------------------------------- the buffer ---

def _pending():
    """Screenshots taken since the last test's record was built."""
    if not isinstance(getattr(ConfigVars, "_screenshots", None), list):
        ConfigVars._screenshots = []

    return ConfigVars._screenshots


def take_screenshots():
    """Hand over every image taken so far and empty the buffer."""
    pending = _pending()
    ConfigVars._screenshots = []

    return pending


def pending_count():
    """How many images the running test has produced already."""
    return len(_pending())


def add(image=None, png=None, label=""):
    """Put one image in the buffer.

    Either half: `image` is what ``attach`` decoded, `png` the bytes a browser
    handed over. Bytes are kept as bytes on purpose - they are already a png,
    and decoding one only to encode it again is time spent on every screenshot
    of every test to arrive back where it started.
    """
    _pending().append({"image": image, "png": png, "label": str(label)})


def save(entry, path):
    """Write one buffered image out as a png."""
    if entry.get("png") is not None:
        with open(path, "wb") as handle:
            handle.write(entry["png"])
        return

    entry["image"].save(path)


# -------------------------------------------------------------- attach() ---

def attach(data=None):
    """Attach the bytes of an image to the test that is running.

    ::

        attach(data=driver.get_screenshot_as_png())   # Selenium
        attach(data=page.screenshot())                # Playwright

    Every image attached this way is kept, whatever the test did and whatever
    ``--report-screenshots`` says: that option is about the pictures nobody
    asked for, and this one was asked for.
    """
    # Pillow fails on a string with "cannot identify image file", which says
    # nothing about the mistake actually made now that the package also has
    # helpers that do take text.
    if isinstance(data, str):
        raise TypeError(
            "attach() takes the bytes of an image; to attach text use "
            "attach_text(), attach_json() or attach_api() instead"
        )

    add(image=Image.open(BytesIO(data)), label="attached")


# --------------------------------------------------- photographing a browser ---

def _attr(source, name):
    """`source.name`, or None - reading it must not be able to fail a test.

    Attribute access on a live browser handle runs whatever the client put
    behind the name, and a driver whose session has already gone raises rather
    than answering.
    """
    try:
        return getattr(source, name, None)
    except Exception:
        return None


def _shot(target, name):
    """Call one screenshot method and hand back png bytes, or None."""
    method = _attr(target, name)
    if not callable(method): return None

    try:
        data = method()
    except Exception:
        # A page already closed, a driver whose session is gone, a browser that
        # crashed on its way out. None of it is worth failing a test over: the
        # report simply has no picture of that one.
        return None

    # The async APIs hand back a coroutine. Nothing here can await it, and
    # leaving it unawaited prints a warning against the test - so it is closed
    # and the report says nothing rather than saying that. An async suite
    # attaches from the test body, where there is somewhere to await.
    if inspect.isawaitable(data):
        try:
            data.close()
        except Exception:
            pass
        return None

    if isinstance(data, (bytes, bytearray)) and data:
        return bytes(data)

    # splinter's screenshot() writes a file and returns its path. Anything that
    # is not the image itself is treated the same way: not a screenshot.
    return None


def png(target):
    """A png of whatever `target` is looking at, or None.

    Selenium's call first, and the driver underneath a wrapper before the
    wrapper's own: splinter's Browser carries a ``screenshot()`` that writes a
    file and hands back its path, while the driver it wraps returns the bytes.
    """
    data = _shot(target, "get_screenshot_as_png")
    if data: return data

    driver = _attr(target, "driver")
    if (driver is not None) and (driver is not target):
        data = _shot(driver, "get_screenshot_as_png")
        if data: return data

    return _shot(target, "screenshot")


def _is_mock(handle):
    module = str(getattr(type(handle), "__module__", "") or "")

    return any(module == name or module.startswith(name + ".") for name in MOCKS)


def can_shoot(handle):
    """True when `handle` looks like something that can be photographed."""
    if _is_mock(handle): return False
    if any(callable(_attr(handle, name)) for name in SHOTS): return True

    return callable(_attr(_attr(handle, "driver"), "get_screenshot_as_png"))


def targets(handle, depth=0):
    """The things inside one fixture value that can actually be photographed.

    Usually the value itself. A suite that drives a Playwright ``context`` or
    ``browser`` rather than a page never asks for one, though - the pages are
    inside them, and this is what reaches them.
    """
    if (handle is None) or (depth > 2): return []
    if can_shoot(handle): return [handle]

    pages = _attr(handle, "pages")  # a BrowserContext
    if isinstance(pages, (list, tuple)):
        return [page for page in pages if can_shoot(page)]

    contexts = _attr(handle, "contexts")  # a Browser
    if not isinstance(contexts, (list, tuple)): return []

    found = []
    for context in contexts:
        found += targets(context, depth + 1)

    return found


def handles(item):
    """(label, object) for everything this test was holding that may be a browser.

    The fixtures named above come first, then whatever else the test was
    handed, and last the test class's own attributes - a ``unittest`` suite
    puts its driver on ``self`` in ``setUp`` rather than in a fixture.
    """
    found = []
    funcargs = _attr(item, "funcargs")
    funcargs = funcargs if isinstance(funcargs, dict) else {}

    for name in FIXTURES:
        if name in funcargs: found.append((name, funcargs[name]))

    for name, value in funcargs.items():
        if name not in FIXTURES: found.append((name, value))

    instance = _attr(item, "instance")
    if instance is not None:
        for name in FIXTURES:
            value = _attr(instance, name)
            if value is not None: found.append((name, value))

    return found


def capture(item, limit=SHOT_MAX):
    """Photograph every browser this test was still holding. Returns how many.

    Called while the test's fixtures are still alive - the finalizer that quits
    the browser has not run yet - which is the whole reason this is the
    reporter's job rather than a hook everybody has to write for themselves.

    A page reached through two fixtures at once is photographed once: asking
    for the page, the context and the browser is the ordinary way to write a
    Playwright test, and all three lead to the same picture.
    """
    seen = set()
    taken = 0

    for label, handle in handles(item):
        for target in targets(handle):
            if id(target) in seen: continue
            seen.add(id(target))

            data = png(target)
            if not data: continue

            add(png=data, label=label)

            taken += 1
            if taken >= limit: return taken

    return taken
