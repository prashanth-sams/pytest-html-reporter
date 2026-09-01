import base64
import os
import re

# The report used to pull Font Awesome 4.7 off a CDN, which meant a report
# opened offline (or behind a proxy) lost every icon. The same glyphs now ship
# as SVGs under html_page/icons and are inlined into the page as CSS masks, so
# a report file stays self-contained and the icons still take their colour from
# `currentcolor` the way the font did.

_ICON_DIR_NAME = "icons"
_XML_DECLARATION = re.compile(r"<\?xml.*?\?>", re.DOTALL)
_VIEW_BOX = re.compile(r'viewBox="(-?[\d.]+) (-?[\d.]+) ([\d.]+) ([\d.]+)"')

# Font Awesome 4.7 drew its glyphs on a 1792-unit em with the baseline 1536
# units down, and gave every icon that whole em box to stand in - which is what
# set the height of the lines they sit on. Each SVG is cropped to its own
# outline but still carries the glyph's coordinates in those units, so the box
# can be rebuilt here and the outline dropped back into the corner of it the
# font drew it in.
_EM = 1792.0
_DESCENT = 256.0

_cached_styles = None


def _icon_dir():
    package_dir = os.path.dirname(os.path.abspath(__file__))

    # Icons ship inside the package (html_page/icons); fall back to the
    # repository layout where they live alongside the package.
    candidates = [
        os.path.join(package_dir, _ICON_DIR_NAME),
        os.path.join(os.path.dirname(package_dir), _ICON_DIR_NAME),
    ]

    return next((path for path in candidates if os.path.isdir(path)), candidates[0])


def _em(units):
    value = f"{units / _EM:.4f}".rstrip("0").rstrip(".")
    return "0" if value in ("", "-0") else value


def _icon(path):
    with open(path, encoding="utf-8") as svg:
        markup = _XML_DECLARATION.sub("", svg.read()).strip()

    _, top, width, height = (float(n) for n in _VIEW_BOX.search(markup).groups())
    encoded = base64.b64encode(markup.encode("utf-8")).decode("ascii")

    return {
        "uri": f'url("data:image/svg+xml;base64,{encoded}")',
        "width": _em(width),
        "height": _em(height),
        # How far down its em box the outline starts, which is the difference
        # between a chart's axis sitting on the line and a calendar hanging off
        # the bottom of it.
        "top": _em(top),
    }


def _icons():
    icon_dir = _icon_dir()

    if not os.path.isdir(icon_dir):
        return {}

    names = sorted(f[:-4] for f in os.listdir(icon_dir) if f.endswith(".svg"))
    return {name: _icon(os.path.join(icon_dir, f"{name}.svg")) for name in names}


def icon_styles():
    """Inline <style> block that renders every `fa fa-*` icon from local SVGs."""
    global _cached_styles

    if _cached_styles is not None:
        return _cached_styles

    icons = _icons()

    if not icons:
        _cached_styles = ""
        return _cached_styles

    # Each glyph publishes its picture and its measurements, so a rule elsewhere
    # in the page can adopt one - the tick a copy button turns into, the file in
    # front of a suite's name - by name rather than by copying its numbers.
    variables = "\n".join(
        f"                    --fa-{name}: {icon['uri']};\n"
        f"                    --fa-{name}-w: {icon['width']}em;\n"
        f"                    --fa-{name}-h: {icon['height']}em;\n"
        f"                    --fa-{name}-y: {icon['top']}em;"
        for name, icon in icons.items()
    )
    classes = "\n".join(
        f"                .fa-{name} {{ --fa-icon: var(--fa-{name});"
        f" --fa-icon-w: var(--fa-{name}-w);"
        f" --fa-icon-h: var(--fa-{name}-h);"
        f" --fa-icon-y: var(--fa-{name}-y); }}"
        for name in icons
    )

    _cached_styles = f"""<style>
                /* Font Awesome 4.7 glyphs, inlined from html_page/icons so the
                   report renders without a CDN. Icons: CC BY 4.0. */
                :root {{
{variables}
                }}

                .fa {{
                    display: inline-block;
                    /* No font-size of its own: Font Awesome's `.fa` ended in
                       `font-size: inherit`, so an icon has always taken the size
                       of the text it sits in. The box is the glyph's em box -
                       one em tall - with the outline painted into its place
                       inside it. */
                    width: var(--fa-icon-w);
                    height: 1em;
                    /* The glyph used to be the element's own content, so a flex
                       row could not squeeze an icon narrower than itself. There
                       is no content to hold the width open now. */
                    flex: none;
                    line-height: 0;
                    background-color: currentcolor;
                    -webkit-mask-image: var(--fa-icon);
                    mask-image: var(--fa-icon);
                    -webkit-mask-repeat: no-repeat;
                    mask-repeat: no-repeat;
                    -webkit-mask-position: 0 var(--fa-icon-y);
                    mask-position: 0 var(--fa-icon-y);
                    -webkit-mask-size: 100% var(--fa-icon-h);
                    mask-size: 100% var(--fa-icon-h);
                }}

                /* An icon has to sit on the line the way the font's own glyph
                   did. A box with nothing in it takes its baseline from its
                   bottom margin edge instead, which drops a line's height by
                   whatever margin the icon carries, so it is given a strut of
                   no width standing {_DESCENT / _EM:.4f}em under the baseline to take one
                   from - the em box's own footing, and the font's. */
                .fa::after {{
                    content: "";
                    display: inline-block;
                    width: 0;
                    height: 1em;
                    vertical-align: -{_DESCENT / _EM:.4f}em;
                }}

{classes}
            </style>"""

    return _cached_styles
