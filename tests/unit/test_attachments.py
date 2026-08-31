"""Cover what an attachment carries before any of it reaches the page.

The two things worth pinning down here are that a credential never survives
the trip - a report is a build artifact, and people paste them around - and
that a response object is read by duck typing, so requests, httpx and a client
neither of them resembles all end up with the same attachment.
"""

import json

import pytest

from pytest_html_reporter.attachments import (
    REDACTED,
    add,
    attach_api,
    attach_file,
    attach_json,
    attach_text,
    curl_command,
    filename_for,
    format_for,
    header_pairs,
    human_size,
    is_secret,
    prepare_body,
    redact_data,
    redact_headers,
    redact_url,
    status_class,
    take_attachments,
    trim_parts,
)
from pytest_html_reporter.const_vars import ConfigVars


@pytest.fixture(autouse=True)
def empty_buffer():
    """The buffer is a module global, so a leftover would land on the next test."""
    ConfigVars._attachments = []
    yield
    ConfigVars._attachments = []


# --------------------------------------------------------------- redaction ---

@pytest.mark.parametrize("name", [
    "Authorization", "proxy-authorization", "Cookie", "Set-Cookie", "X-Api-Key",
    "api_key", "access_token", "refresh_token", "password", "client_secret",
])
def test_credential_names_are_recognised(name):
    assert is_secret(name)


@pytest.mark.parametrize("name", [
    "Content-Type", "Accept", "User-Agent", "X-Request-Id", "Content-Length",
])
def test_ordinary_headers_are_left_alone(name):
    assert not is_secret(name)


def test_headers_are_redacted_by_name():
    pairs = redact_headers({"Authorization": "Bearer abc", "Accept": "application/json"})

    assert dict(pairs) == {"Authorization": REDACTED, "Accept": "application/json"}


def test_redaction_can_be_switched_off():
    pairs = redact_headers({"Authorization": "Bearer abc"}, redact=False)

    assert dict(pairs) == {"Authorization": "Bearer abc"}


def test_a_body_is_redacted_at_any_depth():
    """The token in a login response is the one people attach while debugging."""
    data = {"user": {"name": "sam", "password": "hunter2"},
            "sessions": [{"access_token": "abc", "device": "mac"}]}

    assert redact_data(data) == {
        "user": {"name": "sam", "password": REDACTED},
        "sessions": [{"access_token": REDACTED, "device": "mac"}],
    }


def test_a_credential_in_the_query_string_is_blanked_out():
    """It would otherwise land in the title, the meta strip and the curl line."""
    url = redact_url("https://api/x?api_key=abc&page=2&access_token=def")

    assert url == "https://api/x?api_key=%s&page=2&access_token=%s" % (REDACTED, REDACTED)


def test_a_url_without_a_query_is_untouched():
    assert redact_url("https://api/x") == "https://api/x"


def test_a_bare_query_flag_is_left_alone():
    assert redact_url("https://api/x?verbose") == "https://api/x?verbose"


def test_query_redaction_can_be_switched_off():
    assert redact_url("https://api/x?api_key=abc", redact=False) == "https://api/x?api_key=abc"


def test_a_har_shaped_header_list_is_redacted():
    """{"name": ..., "value": ...} is how a HAR - and most specs - write one."""
    data = {"headers": [{"name": "Authorization", "value": "Bearer abc"},
                        {"name": "Accept", "value": "application/json"}]}

    assert redact_data(data) == {"headers": [
        {"name": "Authorization", "value": REDACTED},
        {"name": "Accept", "value": "application/json"},
    ]}


def test_header_pairs_reads_a_case_insensitive_mapping():
    class Headers(dict):
        pass

    assert header_pairs(Headers({"A": "1"})) == [("A", "1")]
    assert header_pairs([("A", "1")]) == [("A", "1")]
    assert header_pairs(None) == []


# ------------------------------------------------------------------ bodies ---

def test_a_json_body_is_pretty_printed():
    text, fmt = prepare_body('{"id":1,"nested":{"a":2}}', "application/json")

    assert fmt == "json"
    assert text == '{\n  "id": 1,\n  "nested": {\n    "a": 2\n  }\n}'


def test_a_body_that_is_not_json_is_left_as_it_is():
    text, fmt = prepare_body("plain trouble", "text/plain")

    assert (text, fmt) == ("plain trouble", "text")


def test_a_scalar_is_not_treated_as_json():
    """`123` parses as JSON, but re-serialising it says nothing at all."""
    assert prepare_body("123", "text/plain") == ("123", "text")


def test_a_malformed_json_body_survives_verbatim():
    """Half a response is exactly what you want to see when a call is cut off."""
    text, fmt = prepare_body('{"id": 1, "trunc', "application/json")

    assert (text, fmt) == ('{"id": 1, "trunc', "json")


def test_bytes_are_decoded_without_raising_on_bad_utf8():
    text, _ = prepare_body(b"caf\xff", "text/plain")

    assert text.startswith("caf")


def test_a_decoded_body_skips_the_round_trip():
    text, fmt = prepare_body({"token": "abc"}, "application/json")

    assert (json.loads(text), fmt) == ({"token": REDACTED}, "json")


@pytest.mark.parametrize("content_type,expected", [
    ("application/json", "json"),
    ("application/problem+json; charset=utf-8", "json"),
    ("text/xml", "xml"),
    ("text/html", "html"),
    ("application/x-yaml", "yaml"),
    ("text/plain", "text"),
    ("", "text"),
])
def test_the_content_type_picks_the_syntax(content_type, expected):
    assert format_for(content_type) == expected


# -------------------------------------------------------------------- curl ---

def test_curl_repeats_the_call_with_the_redaction_intact():
    command = curl_command("POST", "https://api/x", [("Authorization", REDACTED)], '{"a": 1}')

    assert "curl -X POST 'https://api/x'" in command
    assert "-H 'Authorization: %s'" % REDACTED in command
    assert """--data '{"a": 1}'""" in command


def test_curl_escapes_a_quote_in_the_body():
    """An unescaped quote makes the line something the shell will not run."""
    command = curl_command("POST", "https://api/x", [], "it's")

    assert command.endswith("""--data 'it'\\''s'""")


# ------------------------------------------------------------------- sizes ---

@pytest.mark.parametrize("count,expected", [
    (12, "12 B"), (1536, "1.5 KB"), (2 * 1024 * 1024, "2.0 MB"),
])
def test_sizes_read_in_the_unit_that_stays_short(count, expected):
    assert human_size(count) == expected


@pytest.mark.parametrize("code,expected", [
    (200, "2xx"), ("301", "3xx"), (404, "4xx"), (503, "5xx"),
    (None, ""), ("", ""), (999, ""), ("oops", ""),
])
def test_a_status_is_grouped_by_its_class(code, expected):
    assert status_class(code) == expected


def test_trimming_keeps_the_head_and_says_what_went():
    """The opposite of a log: a payload puts its status and error at the top."""
    parts = trim_parts([{"title": "Response body", "format": "json", "text": "x" * 500}], 100)

    assert parts[0]["text"].startswith("x" * 100)
    assert "400 more characters" in parts[0]["text"]


def test_a_part_under_the_limit_is_untouched():
    parts = trim_parts([{"title": "t", "format": "text", "text": "short"}], 100)

    assert parts[0]["text"] == "short"


def test_the_limit_can_be_lifted():
    parts = trim_parts([{"title": "t", "format": "text", "text": "x" * 500}], 0)

    assert parts[0]["text"] == "x" * 500


def test_filename_is_safe_to_write_to_disk():
    """A parametrised test name carries brackets and slashes into the download."""
    assert filename_for("test_it[a/b]", "GET /v2/orders") == "test_it-a-b--GET-v2-orders"


# -------------------------------------------------------------- the buffer ---

def test_attach_text_lands_in_the_buffer():
    attach_text("hello", name="Note")
    pending = take_attachments()

    assert len(pending) == 1
    assert pending[0]["kind"] == "text"
    assert pending[0]["title"] == "Note"
    assert pending[0]["parts"][0]["text"] == "hello"


def test_taking_the_attachments_empties_the_buffer():
    attach_text("hello")

    assert take_attachments()
    assert take_attachments() == []


def test_empty_text_attaches_nothing():
    """An empty payload would put a rail entry there with nothing behind it."""
    assert attach_text("") is None
    assert take_attachments() == []


def test_a_part_with_no_text_is_dropped():
    assert add("text", "t", [{"title": "a", "format": "text", "text": ""}]) is None


def test_an_unknown_format_falls_back_to_text():
    attach_text("x", format="klingon")

    assert take_attachments()[0]["parts"][0]["format"] == "text"


def test_attach_json_takes_an_object():
    attach_json({"b": 2, "secret": "s"}, name="Payload")
    attachment = take_attachments()[0]

    assert attachment["kind"] == "json"
    assert json.loads(attachment["parts"][0]["text"]) == {"b": 2, "secret": REDACTED}


def test_attach_file_reads_the_file_and_names_it(tmp_path):
    path = tmp_path / "payload.json"
    path.write_text('{"a": 1}')

    attach_file(str(path))
    attachment = take_attachments()[0]

    assert attachment["kind"] == "file"
    assert attachment["title"] == "payload.json"
    assert attachment["parts"][0]["format"] == "json"
    assert dict(attachment["meta"])["File"] == str(path)


def test_a_json_file_is_redacted_like_any_other_body(tmp_path):
    """Of everything you can attach, a saved payload is the likeliest to hold one."""
    path = tmp_path / "payload.json"
    path.write_text('{"sku": "A-1", "customer": {"password": "hunter2"}}')

    attach_file(str(path))
    text = take_attachments()[0]["parts"][0]["text"]

    assert "hunter2" not in text
    assert json.loads(text) == {"sku": "A-1", "customer": {"password": REDACTED}}


def test_a_har_file_keeps_none_of_its_auth_headers(tmp_path):
    path = tmp_path / "trace.har"
    path.write_text(json.dumps({"log": {"entries": [{"request": {"headers": [
        {"name": "Authorization", "value": "Bearer live_sk_1"}]}}]}}))

    attach_file(str(path))

    assert "live_sk_1" not in take_attachments()[0]["parts"][0]["text"]


def test_file_redaction_can_be_switched_off(tmp_path):
    path = tmp_path / "payload.json"
    path.write_text('{"password": "hunter2"}')

    attach_file(str(path), redact=False)

    assert "hunter2" in take_attachments()[0]["parts"][0]["text"]


def test_a_file_that_is_not_structured_is_kept_verbatim(tmp_path):
    """Nothing to key a redaction off, and mangling a config would be worse."""
    path = tmp_path / "app.conf"
    path.write_text("timeout = 30\nretries = 2\n")

    attach_file(str(path))
    attachment = take_attachments()[0]

    assert attachment["parts"][0]["format"] == "text"
    assert attachment["parts"][0]["text"] == "timeout = 30\nretries = 2\n"


# --------------------------------------------------------------------- api ---

class _Elapsed:
    def __init__(self, seconds): self.seconds = seconds

    def total_seconds(self): return self.seconds


class _Request:
    def __init__(self, **kwargs): self.__dict__.update(kwargs)


class _Response:
    def __init__(self, **kwargs): self.__dict__.update(kwargs)


def _response(**overrides):
    fields = dict(
        status_code=201,
        reason="Created",
        elapsed=_Elapsed(0.128),
        text='{"id": 7, "access_token": "leaky"}',
        headers={"Content-Type": "application/json"},
        request=_Request(
            method="post",
            url="https://api.example.com/v2/orders",
            headers={"Authorization": "Bearer abc", "Content-Type": "application/json"},
            body='{"sku": "A-1"}',
        ),
    )
    fields.update(overrides)

    return _Response(**fields)


def test_a_response_object_fills_in_the_whole_attachment():
    attach_api(_response())
    attachment = take_attachments()[0]
    meta = dict(attachment["meta"])

    assert attachment["kind"] == "api"
    assert attachment["code"] == "201"
    assert attachment["status"] == "2xx"
    assert meta["Method"] == "POST"
    assert meta["Status"] == "201 Created"
    assert meta["Time"] == "128 ms"
    assert attachment["ms"] == "128"


def test_a_query_credential_does_not_survive_a_call(tmp_path=None):
    attach_api(method="GET", url="https://api/x?api_key=abc", status=200,
               response_body="{}")
    attachment = take_attachments()[0]
    payload = attachment["title"] + str(attachment["meta"]) + \
              "".join(part["text"] for part in attachment["parts"])

    assert "abc" not in payload
    assert REDACTED in payload


def test_the_title_leads_with_the_path_not_the_host():
    """The host is the same for every call in most suites; the path is not."""
    attach_api(_response())

    assert take_attachments()[0]["title"] == "POST /v2/orders"


def test_every_part_of_a_call_is_kept():
    attach_api(_response())
    parts = [part["title"] for part in take_attachments()[0]["parts"]]

    assert parts == ["Response body", "Request body", "Request headers",
                     "Response headers", "cURL"]


def test_neither_a_header_nor_a_body_credential_survives():
    attach_api(_response())
    attachment = take_attachments()[0]
    payload = "".join(part["text"] for part in attachment["parts"])

    assert "Bearer abc" not in payload
    assert "leaky" not in payload
    assert payload.count(REDACTED) == 3


def test_httpx_spelling_is_read_too():
    """httpx says reason_phrase and content where requests says reason and body."""
    response = _Response(
        status_code=404,
        reason_phrase="Not Found",
        content=b'{"detail": "gone"}',
        headers={"Content-Type": "application/json"},
        request=_Request(method="GET", url="https://api/x",
                         headers={}, content=b""),
    )

    attach_api(response)
    attachment = take_attachments()[0]

    assert dict(attachment["meta"])["Status"] == "404 Not Found"
    assert attachment["status"] == "4xx"
    assert '"detail": "gone"' in attachment["parts"][0]["text"]


def test_a_property_that_raises_does_not_take_the_test_down_with_it():
    """A streamed response raises on .text; the attachment loses that one field."""
    class Awkward:
        status_code = 200
        request = _Request(method="GET", url="https://api/x", headers={}, body=None)

        @property
        def text(self): raise RuntimeError("streamed")

        @property
        def headers(self): return {}

    attach_api(Awkward())
    attachment = take_attachments()[0]

    assert attachment["code"] == "200"
    assert [part["title"] for part in attachment["parts"]] == ["cURL"]


def test_a_call_can_be_described_without_any_response_object():
    attach_api(method="delete", url="/orders/7", status=204, duration=2.5,
               response_body="", request_body="{}")
    attachment = take_attachments()[0]

    assert attachment["title"] == "DELETE /orders/7"
    assert dict(attachment["meta"])["Time"] == "2.50 s"
    assert attachment["detail"] == "2.50 s"


def test_an_explicit_field_beats_the_response_object():
    """A proxy in front of the client is the reason the override exists."""
    attach_api(_response(), url="https://gateway/v2/orders", status=500)
    meta = dict(take_attachments()[0]["meta"])

    assert meta["URL"] == "https://gateway/v2/orders"
    assert meta["Status"].startswith("500")


def test_a_call_with_no_timing_shows_no_time():
    attach_api(_response(elapsed=None))
    attachment = take_attachments()[0]

    assert "Time" not in dict(attachment["meta"])
    assert attachment["ms"] == ""
