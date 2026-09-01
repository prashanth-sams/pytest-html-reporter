import os
import re

from html_page.assets import _SCRIPTS, _STYLESHEETS, image, vendor_assets
from html_page.icon_styles import icon_styles
from html_page.template import HtmlTemplate

HTML_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "html_page", "html")
PACKAGE_DIR = os.path.dirname(HTML_DIR)

# The report links out to its own documentation and to its sponsor. Those are
# somewhere to click, not something the page has to fetch to draw itself.
_LINK_OUT = re.compile(r'<a [^>]*href="(https?://[^"]+)"')
# An inline SVG names the SVG namespace by URL; nothing is fetched from it.
_XML_NAMESPACE = "http://www.w3.org/"


def rendered_page():
    return str(
        HtmlTemplate(
            vendor_assets=vendor_assets(),
            icon_styles=icon_styles(),
            favicon=image("favicon.png"),
            loader_image=image("loader.gif"),
            custom_logo=image("logo.png"),
        )
    )


def fetched_urls(page):
    page = _LINK_OUT.sub("", page)

    return sorted(
        set(
            url
            for url in re.findall(r'(?:src|href)="(https?://[^"]+)"', page)
            + re.findall(r"url\(['\"]?(https?://[^)'\"]+)", page)
            if not url.startswith(_XML_NAMESPACE)
        )
    )


def test_the_report_fetches_nothing_to_draw_itself():
    # A run with no way out to the internet used to produce a blank white page:
    # jQuery never arrived and nothing after it ran.
    assert fetched_urls(rendered_page()) == []


def test_the_templates_name_no_cdn():
    for entry in sorted(os.listdir(HTML_DIR)):
        if not entry.endswith(".html"):
            continue

        with open(os.path.join(HTML_DIR, entry), encoding="utf-8") as html:
            assert fetched_urls(html.read()) == [], entry


def test_every_library_the_page_loads_is_shipped_with_it():
    page = rendered_page()

    for name in _STYLESHEETS + _SCRIPTS:
        assert os.path.isfile(os.path.join(PACKAGE_DIR, "vendor", name)), name
        assert f"/* {name} */" in page, name


def test_fancybox_is_not_redistributed():
    # fancyBox 3 is GPLv3 or a paid commercial licence, neither of which an
    # MIT-licensed package can carry. The report has a lightbox of its own.
    assert not [f for f in os.listdir(os.path.join(PACKAGE_DIR, "vendor")) if "fancybox" in f.lower()]
    assert "shot-box" in rendered_page()


def test_the_pictures_the_page_needs_travel_in_it():
    page = rendered_page()

    for name in ("favicon.png", "loader.gif", "logo.png"):
        assert os.path.isfile(os.path.join(PACKAGE_DIR, "images", name)), name
        assert image(name).startswith("data:image/"), name
        assert image(name) in page, name
