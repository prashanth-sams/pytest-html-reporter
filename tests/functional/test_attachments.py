"""A run that fills the Attachments tab, with no browser and no network.

The browser demos next door need a driver installed; this one needs nothing, so
it is the quickest way to see what the tab does::

    pytest tests/functional/test_attachments.py --html-report=./report

``Api`` below stands in for a real HTTP client. Its responses are shaped the
way ``requests`` and ``httpx`` shape theirs - which is the whole point:
``attach_api`` reads a response by duck typing, so swapping this class for
``requests`` changes nothing else in the file.
"""

import json

import pytest

from pytest_html_reporter import attach_api, attach_file, attach_json, attach_text


class Elapsed:
    def __init__(self, seconds): self.seconds = seconds

    def total_seconds(self): return self.seconds


class Request:
    def __init__(self, method, url, headers, body):
        self.method, self.url, self.headers, self.body = method, url, headers, body


class Response:
    def __init__(self, status_code, reason, body, request, seconds):
        self.status_code, self.reason, self.text = status_code, reason, body
        self.request, self.elapsed = request, Elapsed(seconds)
        self.headers = {"Content-Type": "application/json", "X-Request-Id": "3f9a-11d2"}


class Api:
    """A stand-in for requests.Session, with the same shape and no sockets."""

    BASE = "https://api.example.com/v2"

    # A token in a header and a key in the query string: both are blanked out
    # of the report, which is the behaviour this demo is here to show.
    HEADERS = {
        "Authorization": "Bearer live_sk_9f3c2a77b41e",
        "Content-Type": "application/json",
        "User-Agent": "pytest-html-reporter/demo",
    }

    def __init__(self):
        self.last_response = None

    def call(self, method, path, payload=None, status=200, reason="OK", body=None, seconds=0.184):
        request = Request(method, self.BASE + path + "?api_key=live_pk_88fe10",
                          dict(self.HEADERS), json.dumps(payload) if payload else None)
        self.last_response = Response(status, reason, body, request, seconds)

        return self.last_response


@pytest.fixture
def api(request):
    """The recipe worth copying: attach the last call, but only on a failure.

    The reporter builds a test's record after the fixture finalizers have run,
    so a teardown is a perfectly good place to attach from.
    """
    client = Api()
    yield client

    if getattr(request.node, "rep_call", None) is not None and request.node.rep_call.failed:
        if client.last_response is not None:
            attach_api(client.last_response, name="Last call before the failure")


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    # Here so the file stands alone. pytest calls a hook defined in a test
    # module, but only for that module's tests, so in a real suite this belongs
    # in conftest.py where it covers everything under it.
    outcome = yield
    setattr(item, "rep_" + outcome.get_result().when, outcome.get_result())


ORDER = {"sku": "A-1", "qty": 2, "customer": {"id": 91, "password": "hunter2"}}


def test_an_order_is_created(api):
    """A call that went fine. Attached anyway - a 201 is a baseline worth having."""
    response = api.call("POST", "/orders", ORDER, 201, "Created",
                        '{"id": 4711, "status": "created", "access_token": "tok_live_31f8"}')
    attach_api(response)

    assert response.status_code == 201


def test_the_api_rejects_the_order(api):
    """The case the tab exists for: three attachments explaining one failure."""
    response = api.call("POST", "/orders", ORDER, 422, "Unprocessable Entity",
                        '{"error": "sku unknown", "field": "sku", "trace": "e91c-44a"}',
                        seconds=1.42)
    attach_api(response, name="Create order")

    attach_json({"expected": {"id": 4711, "status": "created"},
                 "got": json.loads(response.text)}, name="Diff")

    attach_text("SELECT id, status FROM orders WHERE sku = 'A-1';",
                name="What the assertion checked", format="sql")

    assert response.status_code == 201, "the order was rejected"


def test_upstream_is_down(api):
    """A call described by hand - no response object anywhere in sight."""
    attach_api(method="GET", url=Api.BASE + "/health", status=503,
               reason="Service Unavailable", duration=3.2,
               response_body="upstream timed out after 3s")

    assert True


def test_the_fixture_attaches_on_failure(api):
    """Nothing is attached here; the `api` fixture's teardown does it."""
    api.call("DELETE", "/orders/4711", status=409, reason="Conflict",
             body='{"error": "order already shipped"}', seconds=0.62)

    assert False, "deleting a shipped order should have been allowed"


def test_a_file_from_disk(tmp_path):
    """Any small text file - a payload, a config, a HAR - can be attached."""
    payload = tmp_path / "order.json"
    payload.write_text(json.dumps(ORDER, indent=2))

    attach_file(str(payload), name="The payload we sent")


def test_a_plain_note():
    attach_text("The third retry is the one that worked; the first two timed out.")


def test_nothing_to_attach():
    """A test that attaches nothing shows a dash in the Data column."""
    assert True
