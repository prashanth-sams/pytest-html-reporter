import base64
import mimetypes
import os

# Everything the report draws with used to be fetched from a CDN, so a run on a
# machine with no way out to the internet produced a blank white page: jQuery
# never arrived, and nothing after it ran. The libraries and images now ship
# with the plugin and are written into the report itself, which is what lets a
# report be opened anywhere - offline, off a locked-down network, or out of an
# archive years after the CDN stopped serving that version.

_VENDOR_DIR_NAME = "vendor"
_IMAGE_DIR_NAME = "images"

# Order is load order, and it matters: jQuery has to be defined before the
# plugins that extend it, and JSZip before the Excel export that reaches for it.
_STYLESHEETS = (
    "jquery.dataTables.min.css",
    "buttons.dataTables.min.css",
    "bootstrap.min.css",
)
_SCRIPTS = (
    "jquery.min.js",
    "jspdf.min.js",
    "dom-to-image.min.js",
    "bootstrap.min.js",
    "jquery.dataTables.min.js",
    "dataTables.buttons.min.js",
    "jszip.min.js",
    "buttons.html5.min.js",
    "buttons.print.min.js",
    "buttons.colVis.min.js",
    "chart.min.js",
)

_cache = {}


def _package_path(*parts):
    package_dir = os.path.dirname(os.path.abspath(__file__))

    # Assets ship inside the package; fall back to the repository layout where
    # they live alongside it.
    candidates = [
        os.path.join(package_dir, *parts),
        os.path.join(os.path.dirname(package_dir), *parts),
    ]

    return next((path for path in candidates if os.path.exists(path)), candidates[0])


def _read(*parts):
    path = _package_path(*parts)

    if not os.path.isfile(path):
        return ""

    with open(path, encoding="utf-8") as handle:
        return handle.read()


def image(name):
    """A packaged image as a data URI, so the page carries its own artwork."""
    if name in _cache:
        return _cache[name]

    path = _package_path(_IMAGE_DIR_NAME, name)

    if not os.path.isfile(path):
        _cache[name] = ""
        return _cache[name]

    with open(path, "rb") as handle:
        encoded = base64.b64encode(handle.read()).decode("ascii")

    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
    _cache[name] = f"data:{mime};base64,{encoded}"

    return _cache[name]


def vendor_assets():
    """Every third-party stylesheet and script, inlined in load order."""
    if "vendor" in _cache:
        return _cache["vendor"]

    blocks = ["            <!-- Bundled from html_page/vendor; see its README for versions and licences. -->"]

    for name in _STYLESHEETS:
        blocks.append(f"            <style>/* {name} */\n{_read(_VENDOR_DIR_NAME, name)}\n            </style>")

    for name in _SCRIPTS:
        # A library that printed the closing tag of the very block it sits in
        # would end the script early; none of these do, and this keeps it so.
        source = _read(_VENDOR_DIR_NAME, name).replace("</script", "<\\/script")
        blocks.append(f"            <script>/* {name} */\n{source}\n            </script>")

    _cache["vendor"] = "\n".join(blocks)

    return _cache["vendor"]
