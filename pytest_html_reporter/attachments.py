"""Text, JSON and HTTP-call attachments a test can hand to the report.

``attach`` takes a picture. These take the things you actually read when a test
fails against an API: the request that went out, the response that came back,
the headers on both sides, and the curl line that reproduces the call.

Everything an attachment carries is built-in types, for the same reason a test
record is - an xdist worker has to be able to ship it back to the controller
that writes the report.

Nothing here imports requests, httpx or any other client. A response object is
read by duck typing, so the two libraries most people use work out of the box
and a client neither of them resembles can still be described by hand.
"""

import json
import os
import re
from collections import OrderedDict

from pytest_html_reporter.const_vars import ConfigVars


# What the viewer knows how to lay out. Anything else is shown as plain text.
FORMATS = ("text", "json", "xml", "html", "yaml", "sql", "curl", "headers")

# The kinds the Attachments rail can filter by.
KINDS = ("api", "json", "text", "file")

TITLE_MAX = 80
META_VALUE_MAX = 300

REDACTED = "<redacted>"

# Header and field names whose value has no business being in a file that ends
# up as a CI artifact. Matched as a substring of the lower-cased name, so
# "X-Api-Key", "Proxy-Authorization" and "refresh_token" are all covered
# without listing every spelling anyone has ever used.
SECRET_HINTS = (
    "authorization", "cookie", "token", "secret", "password", "passwd",
    "api-key", "apikey", "api_key", "x-auth", "credential", "private-key",
)


def is_secret(name):
    """True when a header or field of this name carries a credential."""
    return any(hint in str(name).lower() for hint in SECRET_HINTS)


def _text(value, limit=None):
    value = "" if value is None else str(value)

    return value[:limit] if (limit and len(value) > limit) else value


def human_size(count):
    """A byte count as something readable on a one-line badge."""
    if count < 1024: return "%d B" % count
    if count < 1024 * 1024: return "%.1f KB" % (count / 1024.0)

    return "%.1f MB" % (count / (1024.0 * 1024.0))


def status_class(code):
    """'2xx', '4xx', ... for an HTTP status, or '' when there is no status.

    The rail colours a call by its class rather than its exact code: what you
    scan for is "which of these went wrong", not "which returned 204".
    """
    try:
        code = int(code)
    except (TypeError, ValueError):
        return ""

    return "%dxx" % (code // 100) if 100 <= code < 600 else ""


# ---------------------------------------------------------------- headers ---

def header_pairs(headers):
    """(name, value) pairs out of whatever shape the client hands over.

    requests uses a CaseInsensitiveDict and httpx a Headers object; both carry
    ``items()``, as does a plain dict, and a list of pairs works too.
    """
    if headers is None: return []

    items = getattr(headers, "items", None)
    if callable(items):
        try:
            return [(key, value) for key, value in items()]
        except Exception:
            return []

    try:
        return [(key, value) for key, value in headers]
    except (TypeError, ValueError):
        return []


def redact_headers(headers, redact=True):
    return [
        (_text(key), REDACTED if (redact and is_secret(key)) else _text(value))
        for key, value in header_pairs(headers)
    ]


def format_headers(pairs):
    """Headers as the block of ``Name: value`` lines a terminal would print."""
    return "\n".join("%s: %s" % (key, value) for key, value in pairs)


def redact_url(url, redact=True):
    """Blank out a credential passed as a query parameter.

    ``?api_key=...`` is as ordinary in an API suite as an Authorization header,
    and it would otherwise reach the report three times over - in the entry's
    title, in the URL on the meta strip, and in the curl line.
    """
    if not redact or "?" not in url: return url

    base, _, query = url.partition("?")

    pairs = []
    for pair in query.split("&"):
        key, sep, _value = pair.partition("=")
        pairs.append((key + sep + REDACTED) if (sep and is_secret(key)) else pair)

    return base + "?" + "&".join(pairs)


def redact_data(value):
    """Blank out the sensitive fields of a decoded JSON body, at any depth.

    A bearer token is at least as likely to be in the body of a login response
    as in a header, and that response is exactly the one someone attaches while
    working out why the login failed.
    """
    if isinstance(value, dict):
        # {"name": "Authorization", "value": "Bearer ..."} - how a HAR, and
        # most API specs, write a header. Keying off the dict's own keys would
        # look at "name" and "value" and find nothing to redact.
        if is_secret(value.get("name", "")) and "value" in value:
            redacted = OrderedDict(value)
            redacted["value"] = REDACTED
            return redacted

        return OrderedDict(
            (key, REDACTED if is_secret(key) else redact_data(item))
            for key, item in value.items()
        )

    if isinstance(value, (list, tuple)):
        return [redact_data(item) for item in value]

    return value


# ------------------------------------------------------------------ bodies ---

def format_for(content_type):
    """The syntax a Content-Type implies."""
    content_type = str(content_type or "").lower()

    for needle, name in (("json", "json"), ("xml", "xml"), ("html", "html"),
                         ("yaml", "yaml"), ("csv", "text")):
        if needle in content_type: return name

    return "text"


def _decode(body):
    if isinstance(body, bytes):
        return body.decode("utf-8", "replace")

    return str(body)


def _as_json(text):
    """The decoded object of a JSON document, or None when it is not one.

    Only text that opens with a brace or a bracket is tried: a body of ``123``
    or ``null`` is valid JSON, and re-serialising it would be a pointless way
    of saying nothing.
    """
    stripped = text.strip()
    if not stripped[:1] in ("{", "["): return None

    try:
        return json.loads(stripped)
    except (ValueError, TypeError):
        return None


def dumps(data):
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


def prepare_body(body, content_type="", redact=True):
    """(text, format) for a request or response body, pretty-printed if JSON.

    A body that arrives already decoded - a dict handed to ``attach_json`` -
    skips the round trip; anything else is decoded, and re-serialised only when
    it really parses as JSON.
    """
    if body is None or body == b"" or body == "": return "", "text"

    if isinstance(body, (dict, list, tuple)):
        return dumps(redact_data(body) if redact else body), "json"

    text = _decode(body)
    parsed = _as_json(text)

    if parsed is not None:
        return dumps(redact_data(parsed) if redact else parsed), "json"

    return text, format_for(content_type)


def curl_command(method, url, headers, body):
    """The curl line that repeats the call, with the same headers redacted.

    Pasting this into a terminal is the first thing anyone does with a failed
    API call, and rebuilding it by hand from a report is the tedious part.
    """
    parts = ["curl -X %s '%s'" % (method or "GET", url or "")]

    for key, value in headers:
        parts.append("  -H '%s: %s'" % (key, value))

    if body:
        parts.append("  --data '%s'" % body.replace("'", "'\\''"))

    return " \\\n".join(parts)


# ------------------------------------------------------------- the buffer ---

def _pending():
    """Attachments made since the last test's record was built."""
    if not isinstance(getattr(ConfigVars, "_attachments", None), list):
        ConfigVars._attachments = []

    return ConfigVars._attachments


def take_attachments():
    """Hand over everything attached so far and empty the buffer.

    Drained by every record, whatever the test did and whatever the mode: an
    attachment nobody claims must not be left lying around for the next test to
    pick up and present as its own.
    """
    pending = _pending()
    ConfigVars._attachments = []

    return pending


def add(kind, title, parts, meta=None, code="", detail="", ms=""):
    """Put one attachment in the buffer, in the shape the report renders."""
    parts = [part for part in parts if part.get("text")]
    if not parts: return None

    record = {
        "kind": kind if kind in KINDS else "text",
        "title": _text(title, TITLE_MAX) or kind.upper(),
        "meta": [[_text(label), _text(value, META_VALUE_MAX)] for label, value in (meta or [])],
        "parts": [
            {
                "title": _text(part["title"]),
                "format": part.get("format") if part.get("format") in FORMATS else "text",
                "text": _decode(part["text"]),
            }
            for part in parts
        ],
        "code": _text(code),
        "status": status_class(code),
        "detail": _text(detail),
        # The rail prints the duration; the summary above it has to add the
        # calls up and find the slowest, which it cannot do from "1.20 s".
        "ms": _text(ms),
    }

    _pending().append(record)

    return record


def trim_parts(parts, limit):
    """Cut each part of an attachment down to `limit` characters.

    The head is what survives, which is the opposite of what a log wants: logs
    read chronologically and the lines by the failure are at the end, while a
    payload puts its status, its error field and its first records at the top.
    """
    if limit <= 0: return parts

    trimmed = []
    for part in parts:
        text = part["text"]
        dropped = len(text) - limit

        if dropped > 0:
            text = (text[:limit].rstrip()
                    + "\n\n... %d more characters - raise --report-attachment-limit to keep them"
                    % dropped)

        trimmed.append({"title": part["title"], "format": part["format"], "text": text})

    return trimmed


def attachment_size(attachment):
    """Characters an attachment holds, for the size shown on its rail entry."""
    return sum(len(part["text"]) for part in attachment["parts"])


# -------------------------------------------------------------- public API ---

def attach_text(data, name=None, format=None):
    """Attach free text to the test that is running.

    ::

        attach_text(response.text, name="Response body", format="json")

    `format` only picks how the viewer lays the text out; it is never used to
    reinterpret what you passed.
    """
    text = _decode(data)
    if not text: return None

    return add(
        "text",
        name or "Text",
        [{"title": name or "Text", "format": format or "text", "text": text}],
        detail=human_size(len(text)),
    )


def attach_json(data, name=None):
    """Attach a dict, a list or a JSON string, pretty-printed.

    Fields that look like credentials are blanked out, the same way they are in
    an attached API call.
    """
    text, _ = prepare_body(data, "application/json")
    if not text: return None

    return add(
        "json",
        name or "JSON",
        [{"title": name or "JSON", "format": "json", "text": text}],
        detail=human_size(len(text)),
    )


def attach_file(path, name=None, format=None, redact=True):
    """Attach the contents of a small text file - a payload, a config, a HAR.

    A file that holds JSON is redacted and pretty-printed like any other body.
    Of everything you can attach, this is the likeliest to be carrying a
    credential: a HAR is a recording of the auth headers. Anything that is not
    structured is kept verbatim - there is nothing to key a redaction off, and
    mangling a config file would be worse than not trying.

    Undecodable bytes are replaced rather than raising: a report that says
    which file could not be read beats a test that fails while reporting.
    """
    with open(path, "rb") as handle:
        text = handle.read().decode("utf-8", "replace")

    if not text: return None

    fmt = format or _format_for_path(path)
    if fmt == "json": text, fmt = prepare_body(text, "application/json", redact)

    return add(
        "file",
        name or os.path.basename(path),
        [{"title": os.path.basename(path), "format": fmt, "text": text}],
        meta=[("File", path), ("Size", human_size(len(text)))],
        detail=human_size(len(text)),
    )


EXTENSION_FORMATS = {
    ".json": "json", ".xml": "xml", ".html": "html", ".htm": "html",
    ".yaml": "yaml", ".yml": "yaml", ".sql": "sql", ".har": "json",
}


def _format_for_path(path):
    return EXTENSION_FORMATS.get(os.path.splitext(str(path))[1].lower(), "text")


def _read(source, *names):
    """The first of `names` the object will part with, or None.

    Every read is guarded: ``response.text`` decodes the body on access and a
    streamed httpx response raises rather than returning it. An attachment
    missing one field is worth having; a test failing inside a reporting call
    is not.
    """
    for name in names:
        try:
            value = getattr(source, name, None)
        except Exception:
            continue

        if value is not None: return value

    return None


def _elapsed_seconds(response):
    """How long the call took, in seconds, if the client kept the timing."""
    elapsed = _read(response, "elapsed")
    if elapsed is None: return None

    total = getattr(elapsed, "total_seconds", None)

    try:
        return total() if callable(total) else float(elapsed)
    except (TypeError, ValueError):
        return None


def attach_api(response=None, name=None, method=None, url=None, status=None,
               reason=None, duration=None, request_headers=None, request_body=None,
               response_headers=None, response_body=None, content_type=None,
               redact=True):
    """Attach an HTTP call: what went out, what came back, and the curl for it.

    Hand it a response object and it reads the rest off that::

        attach_api(requests.get(url))
        attach_api(httpx.post(url, json=payload), name="Create order")

    Every field can also be given directly, and an explicit one always wins, so
    a client neither library resembles - or a call reconstructed from a log -
    still makes a full attachment::

        attach_api(method="POST", url="/orders", status=500,
                   request_body=payload, response_body=body)

    Headers and JSON fields that look like credentials are blanked out. Pass
    ``redact=False`` when the report is not going anywhere and you need the
    real value.
    """
    if response is not None:
        request = _read(response, "request")

        method = method or _read(request, "method")
        url = url or _read(request, "url") or _read(response, "url")
        status = status if status is not None else _read(response, "status_code", "status")
        reason = reason or _read(response, "reason", "reason_phrase")
        duration = duration if duration is not None else _elapsed_seconds(response)

        if request_headers is None: request_headers = _read(request, "headers")
        if request_body is None: request_body = _read(request, "body", "content")
        if response_headers is None: response_headers = _read(response, "headers")
        if response_body is None: response_body = _read(response, "text", "content")

    request_headers = redact_headers(request_headers, redact)
    response_headers = redact_headers(response_headers, redact)

    sent_type = content_type or _header_value(request_headers, "content-type")
    got_type = content_type or _header_value(response_headers, "content-type")

    sent, sent_format = prepare_body(request_body, sent_type, redact)
    got, got_format = prepare_body(response_body, got_type, redact)

    method = _text(method or "GET").upper()
    url = redact_url(_text(url), redact)

    parts = [
        {"title": "Response body", "format": got_format, "text": got},
        {"title": "Request body", "format": sent_format, "text": sent},
        {"title": "Request headers", "format": "headers", "text": format_headers(request_headers)},
        {"title": "Response headers", "format": "headers", "text": format_headers(response_headers)},
        {"title": "cURL", "format": "curl", "text": curl_command(method, url, request_headers, sent)},
    ]

    meta = [("Method", method), ("URL", url)]
    if status is not None: meta.append(("Status", _status_text(status, reason)))
    if duration is not None: meta.append(("Time", _duration_text(duration)))
    if got: meta.append(("Size", human_size(len(got))))
    if got_type: meta.append(("Content-Type", got_type))

    return add(
        "api",
        name or ("%s %s" % (method, _short_url(url))).strip(),
        parts,
        meta=meta,
        code="" if status is None else _text(status),
        detail=_duration_text(duration) if duration is not None else "",
        ms="" if duration is None else _milliseconds(duration),
    )


def _header_value(pairs, wanted):
    for key, value in pairs:
        if str(key).lower() == wanted: return value

    return ""


def _status_text(status, reason):
    return ("%s %s" % (_text(status), _text(reason))).strip()


def _milliseconds(seconds):
    try:
        return "%d" % round(float(seconds) * 1000)
    except (TypeError, ValueError):
        return ""


def _duration_text(seconds):
    """A call's duration, in the unit that keeps it to three or four digits."""
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        return ""

    return "%.2f s" % seconds if seconds >= 1 else "%d ms" % round(seconds * 1000)


def _short_url(url):
    """The path of a URL, which is what tells one call from the next.

    The host is the same for every call in most suites, so leading with it
    would push the part that differs off the end of the rail entry.
    """
    url = _text(url)
    if "://" not in url: return url

    rest = url.split("://", 1)[1]

    return "/" + rest.split("/", 1)[1] if "/" in rest else rest


_SLUG = re.compile(r"[^A-Za-z0-9._-]+")


def filename_for(test_name, title):
    """A download name for an attachment, built from the test and its title."""
    slug = _SLUG.sub("-", "%s-%s" % (test_name, title)).strip("-.")

    return (slug or "attachment")[:80]
