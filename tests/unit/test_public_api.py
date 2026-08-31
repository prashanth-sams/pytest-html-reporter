"""Guards the package's public surface.

`attach` and its text-carrying siblings are the only names users import from
the package itself, and they live in a two-line `__init__.py`. The functional
suite that uses `attach` needs a browser and does not run in CI, so without
these the exports could break unnoticed (see issue #240).
"""

import pytest
import pytest_html_reporter
from pytest_html_reporter import attachments
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


@pytest.mark.parametrize("name", ["attach_text", "attach_json", "attach_api", "attach_file"])
def test_the_attachment_helpers_are_importable_from_the_package(name):
    assert callable(getattr(pytest_html_reporter, name))
    assert name in pytest_html_reporter.__all__


@pytest.mark.parametrize("name", ["attach_text", "attach_json", "attach_api", "attach_file"])
def test_the_attachment_helpers_are_the_module_ones(name):
    assert getattr(pytest_html_reporter, name) is getattr(attachments, name)


def test_attach_names_the_right_helper_for_a_string():
    """Pillow's own error - "cannot identify image file" - says nothing about
    the mistake, which is now an easy one to make."""
    with pytest.raises(TypeError, match="attach_text"):
        pytest_html_reporter.attach(data="not a picture")
