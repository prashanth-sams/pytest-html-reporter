import os
import re

from html_page.icon_styles import icon_styles
from html_page.template import HtmlTemplate

HTML_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "html_page", "html")

# Colours the report is read by. A theme may restate them but must not drop one.
STATUS_TOKENS = (
    "--status-pass",
    "--status-fail",
    "--status-skip",
    "--status-xpass",
    "--status-xfail",
    "--status-error",
    "--status-rerun",
)

_DECLARATION = re.compile(r"^\s*(--[a-z0-9-]+)\s*:\s*(.+?);\s*$", re.M)
# A colour literal that escaped tokenising. `#` also starts a fragment in a
# URL and an id in a selector, so this only looks at declaration values.
_COLOUR = re.compile(
    r"(#[0-9a-fA-F]{3,8}(?![0-9a-fA-F])|rgba?\([^()]*\)|"
    r"(?<![-\w])(?:white|black|dimgrey|dimgray|darkgrey|darkgray|grey|gray|"
    r"whitesmoke|silver|lightgrey|lightgray|gainsboro|slategrey|slategray)(?![-\w]))"
)


def rendered_page():
    return str(HtmlTemplate(icon_styles=icon_styles()))


def theme_blocks(page):
    """The light and dark token declarations, as {token: value} pairs."""
    # Anchored on the token block's own comment: the inlined icon glyphs
    # declare their measurements on `:root` too, and come first.
    start = page.index("Theme tokens.")
    middle = page.index(':root[data-theme="dark"]', start)
    end = page.index("</style>", middle)

    return (
        dict(_DECLARATION.findall(page[start:middle])),
        dict(_DECLARATION.findall(page[middle:end])),
    )


def app_stylesheets(page):
    """Every <style> block the report writes itself, minus the icon glyphs."""
    blocks = re.findall(r"<style>(.*?)</style>", page, re.S)

    return [b for b in blocks if "--fa-" not in b]


def test_the_theme_is_settled_before_the_page_paints():
    page = rendered_page()
    head = page[: page.index("</head>")]

    # The script has to run before the stylesheets so a dark report never shows
    # a white frame first, and before the charts so they can read their colours.
    assert head.index("prefers-color-scheme: dark") < head.index(":root {")
    assert 'document.documentElement.setAttribute("data-theme"' in head.replace("'", '"')


def test_a_stored_choice_outranks_the_system_preference():
    page = rendered_page()

    assert "pytestHtmlReporterTheme" in page
    # Reading storage throws outright on some file:// origins; every read and
    # every write must survive that, falling back to the system preference.
    reads = re.findall(r"localStorage\.getItem\(", page)
    writes = re.findall(r"localStorage\.setItem\(", page)
    assert reads and writes
    for call in re.findall(r"(try \{[^}]*localStorage[^}]*\} catch \(e\) \{\})", page):
        assert "catch (e) {}" in call
    assert len(re.findall(r"try \{[^}]*localStorage[^}]*\} catch", page)) == len(reads) + len(writes)


def test_both_themes_declare_exactly_the_same_tokens():
    light, dark = theme_blocks(rendered_page())

    assert light, "no light tokens found"
    assert set(light) == set(dark)


def test_every_token_the_page_uses_is_declared_in_both_themes():
    page = rendered_page()
    light, dark = theme_blocks(page)

    used = set(re.findall(r"var\(\s*(--[a-z0-9-]+)", page))
    used |= set(re.findall(r"themeValue\('(--[a-z0-9-]+)'\)", page))
    # `--fa-*` are the icon glyphs and `--step-depth` is a layout value set on
    # the element itself; neither is a colour and neither belongs to a theme.
    used -= {name for name in used if name.startswith("--fa-")}
    used -= {"--step-depth"}

    assert used <= set(light)
    assert used <= set(dark)


def test_no_token_is_declared_without_being_used():
    page = rendered_page()
    light, _ = theme_blocks(page)

    used = set(re.findall(r"var\(\s*(--[a-z0-9-]+)", page))
    used |= set(re.findall(r"'(--[a-z0-9-]+)'", page))

    assert set(light) - used == set()


def test_the_status_colours_survive_both_themes():
    light, dark = theme_blocks(rendered_page())

    for token in STATUS_TOKENS:
        assert token in light
        assert token in dark


def test_no_colour_is_left_hard_coded_in_the_app_stylesheets():
    page = rendered_page()

    for block in app_stylesheets(page):
        # The token blocks are where the literals are supposed to live.
        body = block
        if ":root {" in body:
            body = body[: body.index(":root {")]

        for line in body.splitlines():
            declaration = line.split("/*")[0]
            if ":" not in declaration or declaration.strip().startswith("--"):
                continue
            assert not _COLOUR.search(declaration.split(":", 1)[1]), line.strip()


def test_charts_name_their_tokens_so_a_theme_change_can_re_read_them():
    page = rendered_page()

    # Chart.js copies colours into its own model at construction, so every
    # chart is built through themedChart and every colour is named, not typed.
    assert "function themedChart(" in page
    assert "function restyleCharts(" in page
    assert page.count("new Chart(") == 1  # the one inside themedChart itself

    charts = re.findall(r"themedChart\(", page)
    assert len(charts) >= 5


def test_no_chart_colour_is_written_as_a_literal():
    page = rendered_page()
    scripts = re.findall(r"<script>(.*?)</script>", page, re.S)

    for script in scripts:
        for name in ("backgroundColor", "borderColor", "fontColor", "titleFontColor",
                     "bodyFontColor", "hoverBackgroundColor", "pointBackgroundColor"):
            for match in re.finditer(rf"{name}\s*:\s*(['\"][^'\"]*['\"])", script):
                assert not _COLOUR.search(match.group(1)), match.group(0)


def test_icons_carried_as_tokens_are_base64_not_percent_encoded():
    page = rendered_page()
    light, dark = theme_blocks(page)

    # The PDF export serialises the page into an SVG data URL without escaping
    # it, so a %3C inside a token value would be decoded by the URL parser and
    # tear the markup apart.
    for values in (light, dark):
        for name, value in values.items():
            if "data:image/svg+xml" in value:
                assert "base64," in value, name
                assert "%3C" not in value, name


def test_the_switch_is_a_labelled_control_wired_to_the_toggle():
    page = rendered_page()

    assert 'id="themeSwitch"' in page
    assert 'role="switch"' in page
    assert 'aria-checked' in page
    assert "onclick=\"toggleTheme()\"" in page


def test_the_rail_keeps_its_own_colours_in_both_themes():
    light, dark = theme_blocks(rendered_page())

    # The rail is charcoal in both themes; it must not invert into the page.
    assert light["--rail-bg"] != light["--bg-page"]
    assert dark["--rail-bg"] != dark["--bg-page"]
    assert light["--rail-active-text"] == dark["--rail-active-text"]
