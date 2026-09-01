import os
import re

from html_page.icon_styles import icon_styles
from html_page.template import HtmlTemplate

HTML_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "html_page", "html")

# `fa fa-%(astate)%` in archive_row.html: the archive rail picks its glyph at
# report time, so the template cannot name these two.
DYNAMIC_ICONS = {"check", "times"}


def used_icons():
    names = set(DYNAMIC_ICONS)

    for entry in sorted(os.listdir(HTML_DIR)):
        if not entry.endswith(".html"):
            continue

        with open(os.path.join(HTML_DIR, entry), encoding="utf-8") as html:
            body = html.read()

        names.update(re.findall(r"fa fa-([a-z0-9-]+)", body))
        names.update(re.findall(r"fillOverlay\('fa-([a-z0-9-]+)'", body))
        # `var(--fa-file-w)` and friends name a glyph's measurements, not a
        # glyph: the icon they belong to is what has to be shipped.
        names.update(
            re.sub(r"-[why]$", "", name)
            for name in re.findall(r"var\(--fa-([a-z0-9-]+)\)", body)
        )

    return names


def test_every_icon_the_report_asks_for_is_shipped_as_an_svg():
    styles = icon_styles()

    missing = sorted(name for name in used_icons() if f"--fa-{name}:" not in styles)
    assert missing == [], f"no SVG under html_page/icons for: {missing}"


def test_every_icon_publishes_the_measurements_its_box_is_built_from():
    styles = icon_styles()

    for name in used_icons():
        for measurement in ("w", "h", "y"):
            assert f"--fa-{name}-{measurement}:" in styles
        assert f".fa-{name} {{" in styles


def test_an_icon_takes_its_size_from_the_text_around_it():
    # Font Awesome's own rule ended in `font-size: inherit`; pinning a size here
    # would shrink every icon that sits in bigger text than the default.
    rule = icon_styles().split(".fa {")[1].split("}")[0]
    declarations = re.sub(r"/\*.*?\*/", "", rule, flags=re.DOTALL)

    assert "font-size" not in declarations
    assert "height: 1em;" in rule


def test_icons_are_inlined_rather_than_fetched():
    styles = icon_styles()

    assert styles.startswith("<style>")
    assert 'url("data:image/svg+xml;base64,' in styles
    assert "http" not in styles


def test_template_carries_the_icons_and_no_font_awesome_request():
    page = str(HtmlTemplate(icon_styles=icon_styles()))

    assert "font-awesome" not in page
    assert "FontAwesome" not in page
    assert "%(icon_styles)%" not in page
    shipped = [f for f in os.listdir(os.path.join(os.path.dirname(HTML_DIR), "icons")) if f.endswith(".svg")]
    assert page.count('url("data:image/svg+xml;base64,') == len(shipped)


def test_every_icon_takes_its_colour_from_the_text_around_it():
    styles = icon_styles()

    assert "background-color: currentcolor;" in styles
    assert "mask-image: var(--fa-icon);" in styles
