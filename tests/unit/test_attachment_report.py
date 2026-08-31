"""Cover what an attachment looks like once it is on the page.

The module tests already pin down what an attachment holds. What matters here
is the trip through a real run: that it lands on the test that made it, that a
test which attached nothing is not offered a button, and that a payload cannot
be turned into markup or into a template placeholder on the way.
"""

import os
import re
import subprocess
import sys
import textwrap

import pytest


CLIENT = textwrap.dedent('''
    class Elapsed:
        def __init__(self, seconds): self.seconds = seconds
        def total_seconds(self): return self.seconds


    class Request:
        def __init__(self, **kwargs): self.__dict__.update(kwargs)


    class Response:
        def __init__(self, **kwargs): self.__dict__.update(kwargs)


    def response(status=200, body='{"id": 7}', seconds=0.128):
        return Response(
            status_code=status, reason="OK", elapsed=Elapsed(seconds), text=body,
            headers={"Content-Type": "application/json"},
            request=Request(method="GET", url="https://api.example.com/v2/orders",
                            headers={"Authorization": "Bearer secret-value"}, body=None),
        )
''')

SUITE = '''
    from pytest_html_reporter import attach_api, attach_json, attach_text


    def test_calls_the_api():
        attach_api(response())
        assert True


    def test_fails_with_evidence():
        attach_api(response(422, '{"error": "sku unknown"}'), name="Create order")
        attach_text("a note", name="Note")
        assert 1 == 2


    def test_attaches_nothing():
        assert True
'''


def _run(tmp_path, body=SUITE, *args):
    """Run a generated suite and hand back the report page it wrote.

    Every suite gets the fake client prepended, so a test body only has to say
    what it attaches.
    """
    (tmp_path / "test_calls.py").write_text(CLIENT + textwrap.dedent(body))

    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--html-report=./report", "-p", "no:cacheprovider"]
        + list(args),
        cwd=str(tmp_path), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        universal_newlines=True,
    )

    report = tmp_path / "report" / "pytest_html_report.html"
    assert report.is_file(), result.stdout

    return report.read_text(encoding="utf-8")


def _items(page):
    """The rail entries, as (test name, kind, title) triples in page order."""
    entries = []
    for item in re.findall(r'<button type="button" class="attach-item".*?</button>', page, re.S):
        entries.append((
            re.search(r'attach-item__test">(.*?)<em>', item, re.S).group(1).strip(),
            re.search(r'data-kind="(.*?)"', item).group(1),
            re.search(r'attach-item__title">(.*?)</span>', item, re.S).group(1).strip(),
        ))

    return entries


def _payload(page, title):
    """The stored block behind one rail entry."""
    pattern = (r'<div class="attach-payload"[^>]*data-title="%s".*?'
               r'(?=<div class="attach-payload"|</div>\s*\n\s*</div>)') % re.escape(title)
    match = re.search(pattern, page, re.S)

    return match.group(0) if match else None


def _cell(page, test_name):
    """The attachment count on a test's row."""
    row = re.search(r'<tr>(?:(?!</tr>).)*?%s.*?</tr>' % re.escape(test_name), page, re.S)

    return re.findall(r'<td class="log-cell" data-logs="(\d*)"', row.group(0))[1]


def test_every_attachment_reaches_the_rail(tmp_path):
    page = _run(tmp_path)

    assert _items(page) == [
        ("test_calls_the_api", "api", "GET /v2/orders"),
        ("test_fails_with_evidence", "api", "Create order"),
        ("test_fails_with_evidence", "text", "Note"),
    ]


def test_the_row_counts_what_it_can_open(tmp_path):
    page = _run(tmp_path)

    assert _cell(page, "test_calls_the_api") == "1"
    assert _cell(page, "test_fails_with_evidence") == "2"
    assert _cell(page, "test_attaches_nothing") == "0"


def test_a_call_carries_its_parts_and_its_status(tmp_path):
    """A GET has no request body, and an empty part earns no tab of its own."""
    page = _run(tmp_path)
    payload = _payload(page, "Create order")

    assert re.findall(r'data-part="(.*?)"', payload) == [
        "Response body", "Request headers", "Response headers", "cURL"]
    assert "sku unknown" in payload
    assert 'class="attach-code attach-code--4xx">422<' in page


def test_a_call_with_a_request_body_keeps_every_part(tmp_path):
    page = _run(tmp_path, """
        from pytest_html_reporter import attach_api

        def test_posts():
            call = response()
            call.request.method = "POST"
            call.request.body = '{"sku": "A-1"}'
            attach_api(call, name="Create")
    """)

    assert re.findall(r'data-part="(.*?)"', _payload(page, "Create")) == [
        "Response body", "Request body", "Request headers", "Response headers", "cURL"]


def test_a_credential_never_reaches_the_file(tmp_path):
    """The report is a build artifact; people paste them into tickets."""
    page = _run(tmp_path)

    assert "secret-value" not in page
    assert "&lt;redacted&gt;" in page


def test_a_payload_is_escaped_rather_than_rendered(tmp_path):
    page = _run(tmp_path, '''
        from pytest_html_reporter import attach_text

        def test_attaches_markup():
            attach_text("<script>alert(1)</script> and %(archive_status)%")
    ''')
    payload = _payload(page, "Text")

    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in payload
    assert "%&#40;archive_status)%" in payload


def test_a_non_ascii_payload_survives_the_write(tmp_path):
    """An API response is far likelier to carry one of these than a log line."""
    page = _run(tmp_path, '''
        from pytest_html_reporter import attach_json

        def test_attaches_unicode():
            attach_json({"city": "Z\\u00fcrich", "emoji": "\\u2713"})
    ''')

    assert "Zürich" in page


def test_failed_mode_keeps_only_the_failures(tmp_path):
    page = _run(tmp_path, SUITE, "--report-attachments=failed")

    assert [item[0] for item in _items(page)] == ["test_fails_with_evidence"] * 2


def test_none_mode_keeps_nothing(tmp_path):
    page = _run(tmp_path, SUITE, "--report-attachments=none")

    assert _items(page) == []
    assert '<div class="attach-payload"' not in page


def test_a_large_payload_is_trimmed_to_the_limit(tmp_path):
    page = _run(tmp_path, '''
        from pytest_html_reporter import attach_text

        def test_attaches_a_lot():
            attach_text("x" * 5000, name="Big")
    ''', "--report-attachment-limit=200")
    payload = _payload(page, "Big")

    assert "4800 more characters" in payload
    assert "x" * 500 not in payload


def test_the_limit_can_be_lifted(tmp_path):
    page = _run(tmp_path, '''
        from pytest_html_reporter import attach_text

        def test_attaches_a_lot():
            attach_text("x" * 5000, name="Big")
    ''', "--report-attachment-limit=0")

    assert "x" * 5000 in _payload(page, "Big")


def test_an_attachment_is_not_handed_to_the_next_test(tmp_path):
    """The bug screenshots had: an unclaimed payload illustrating a test that
    never produced it."""
    page = _run(tmp_path, '''
        from pytest_html_reporter import attach_text

        def test_attaches():
            attach_text("mine", name="Mine")

        def test_attaches_nothing():
            assert True
    ''')

    assert [item[0] for item in _items(page)] == ["test_attaches"]


def test_attaching_from_a_fixture_teardown_still_lands_on_the_test(tmp_path):
    """The recipe most people reach for: capture on failure from an autouse
    fixture, which runs after the test body is done."""
    page = _run(tmp_path, '''
        import pytest

        from pytest_html_reporter import attach_api


        @pytest.fixture(autouse=True)
        def capture_on_failure(request):
            yield
            attach_api(response(500), name="Last call")


        def test_hits_the_api():
            assert True
    ''')

    assert [item[2] for item in _items(page)] == ["Last call"]


def test_the_tab_guides_you_when_nothing_was_attached(tmp_path):
    """An empty tab is the only moment anyone reads setup instructions."""
    page = _run(tmp_path, '''
        def test_quiet():
            assert True
    ''')

    assert _items(page) == []
    assert "No API logs in this run" in page

    # the recipe worth copying, not just the one-liner
    assert "Better: only when the response fails" in page
    assert "request.node.rep_call.failed" in page
    assert "conftest.py" in page


@pytest.mark.skipif(
    not pytest.importorskip("pytest_rerunfailures", reason="needs pytest-rerunfailures"),
    reason="needs pytest-rerunfailures",
)
def test_a_retry_that_attached_nothing_keeps_the_earlier_evidence(tmp_path):
    page = _run(tmp_path, '''
        from pytest_html_reporter import attach_text

        attempts = {"n": 0}

        def test_flaky():
            attempts["n"] += 1
            if attempts["n"] == 1:
                attach_text("the response that failed", name="First attempt")
            assert attempts["n"] == 2
    ''', "--reruns", "2")

    assert [item[2] for item in _items(page)] == ["First attempt"]


def test_attachments_survive_an_xdist_run(tmp_path):
    pytest.importorskip("xdist")

    page = _run(tmp_path, SUITE, "-n", "2")

    assert sorted(item[2] for item in _items(page)) == ["Create order", "GET /v2/orders", "Note"]
