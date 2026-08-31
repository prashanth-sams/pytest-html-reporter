"""Guards the package's public surface.

`attach` is the only name users import from the package itself, and it lives in
a one-line `__init__.py`. The functional suite that uses it needs a browser and
does not run in CI, so without these the export could break unnoticed
(see issue #240).
"""

import pytest_html_reporter
from pytest_html_reporter.util import screenshot


def test_attach_is_importable_from_package():
    from pytest_html_reporter import attach

    assert callable(attach)


def test_attach_is_the_screenshot_helper():
    assert pytest_html_reporter.attach is screenshot


def test_attach_is_advertised_as_public():
    assert "attach" in pytest_html_reporter.__all__


def test_package_is_a_regular_package():
    # A namespace package (no __init__.py shipped) is what turns a missing
    # export into "cannot import name 'attach' ... (unknown location)".
    assert getattr(pytest_html_reporter, "__file__", None) is not None
