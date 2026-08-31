=====================
pytest-html-reporter
=====================

.. image:: https://badges.gitter.im/prashanth-sams/pytest-html-reporter.svg
   :alt: Join the chat at https://gitter.im/prashanth-sams/pytest-html-reporter
   :target: https://gitter.im/prashanth-sams/pytest-html-reporter?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge

.. image:: https://badge.fury.io/py/pytest-html-reporter.svg
    :target: https://badge.fury.io/py/pytest-html-reporter
    :alt: PyPI version

.. image:: https://coveralls.io/repos/github/prashanth-sams/pytest-html-reporter/badge.svg?branch=master
    :target: https://coveralls.io/github/prashanth-sams/pytest-html-reporter?branch=master

.. image:: https://pepy.tech/badge/pytest-html-reporter
    :target: https://pepy.tech/project/pytest-html-reporter
    :alt: Downloads


..

        Generates a light-weight static html report based on ``pytest`` framework


.. image:: https://i.imgur.com/4TYia5j.png
   :alt: pytest-html-reporter

Features
------------
* Generic information

  - Overview
  - Environment
  - Trends
  - Suite Highlights
  - Test suite details
* Archives / History
* Screenshots - works with Selenium, Playwright, or anything else that can produce a PNG
* Attachments - Logs API events/calls, JSON and free text kept against the test that produced them
* Captured logs per test (stdout, stderr and ``logging``)
* Test Rerun support
* Parallel run support (``pytest-xdist``)

Installation
------------

.. code-block:: console

    $ pip3 install pytest-html-reporter


Usage
------------

By default, the filename used is ``pytest_html_reporter.html`` and path chosen is ``report``; you can skip both or
either one of them if not needed::

    $ pytest tests/


..

        Custom path, filename, and title

Add ``--html-report`` tag followed by path location and filename to customize the report location and filename::

    $ pytest tests/ --html-report=./report
    $ pytest tests/ --html-report=./report/report.html

The path is run through ``strftime``, so date and time placeholders (``%Y``, ``%m``, ``%d``, ``%H``, ``%M``, ...) give
each run a folder or a filename of its own::

    $ pytest tests/ --html-report=./reports/%Y%m%d/report_%H%M.html

They are expanded once, when the run starts, so a parallel run and a run that crosses a minute boundary still write a
single report. Write ``%%`` for a literal percent sign in front of a letter; a ``%`` that is not a placeholder, as in
``100% pass``, is left as it is.

Add ``--title`` tag followed by the report title; it is capped at 20 characters and the cut tail fades out, with the
full title kept as the heading's tooltip::

    $ pytest tests/ --html-report=./report --title='PYTEST REPORT'

Add ``--archive-count`` tag followed by an integer to limit showing the number of builds in the ``Archives`` section::

    $ pytest tests/ --archive-count 7
    $ pytest tests/ --html-report=./report --archive-count 7

..

        Environment and build details

Add ``--environment`` tag followed by the environment under test; it shows as a badge beside the report title. The
badge is capped at 10 characters and the cut tail fades out, with the full name kept in the ``Environment`` panel and
in the badge's tooltip::

    $ pytest tests/ --environment=staging

Add ``--build-info`` tag followed by ``key=value`` to add any other detail to the ``Environment`` panel; repeat it as
often as you like::

    $ pytest tests/ --environment=prod --build-info branch=main --build-info sha=$GITHUB_SHA

..

        Captured logs

Everything ``pytest`` captures while a test runs - ``stdout``, ``stderr`` and ``logging`` output, from setup, call and
teardown alike - is kept against that test. The ``Test Metrics`` table gains a ``Logs`` column showing how many lines a
test produced; clicking it opens the output, section by section, with a ``Copy`` button. Tests that produced nothing
show a dash.

This is on by default. No flag is needed - the command you already run is enough::

    $ pytest tests/ --html-report=./report

Three things a test writes end up in that column, and two things that look like they should do not:

=========================================  ===========================================================
What the test does                         Where it shows up
=========================================  ===========================================================
``print(...)``                             ``Captured stdout`` section
``sys.stderr.write(...)``                  ``Captured stderr`` section
``log.info(...)``, ``log.warning(...)``    ``Captured log`` section, subject to ``--log-level`` below
an assertion failure or traceback          **not here** - the ``Error Message`` column already has it
``warnings.warn(...)``                     **not here** - ``pytest`` keeps its own warnings summary
=========================================  ===========================================================

So a test that only asserts has nothing to show and correctly gets a dash, even when it fails. If you are seeing
``stdout`` sections and nothing else, it is because nothing in the suite is calling a logger - not because ``logging``
is being dropped.

``--report-logs`` narrows what is kept, which is worth doing when a large suite would otherwise make the report file
big:

=========================  ==============================================================================
``--report-logs``          What is kept
=========================  ==============================================================================
``all`` *(default)*        Every test's captured output
``failed``                 Only tests that failed or errored; everything else shows a dash
``none``                   Nothing - no ``Logs`` column content and no size cost at all
=========================  ==============================================================================

::

    $ pytest tests/ --report-logs=failed
    $ pytest tests/ --report-logs=none
    $ pytest tests/ --report-logs=all # default

``--report-log-limit`` caps how much of one test's output is kept, so a single chatty test cannot outweigh the rest of
the report. What survives is the **end** of the output - the lines next to the failure - cut back to a whole line, with
a note saying how much was dropped:

=========================  ==============================================================================
``--report-log-limit``     What it means
=========================  ==============================================================================
``10000`` *(default)*      Characters per test
any positive integer       Characters per test
``0``                      No limit; keep everything the test produced
=========================  ==============================================================================

::

    $ pytest tests/ --report-log-limit=50000
    $ pytest tests/ --report-log-limit=0

what pytest itself has to be capturing
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The reporter can only keep what ``pytest`` hands it, and two of ``pytest``'s own options decide that. Neither needs
setting for the defaults to work - but if the ``Logs`` column is emptier than expected, one of these is why.

**Capture.** ``-s`` (short for ``--capture=no``) sends ``stdout`` and ``stderr`` straight to the terminal, so
``pytest`` never takes them in and no reporter can show them. ``logging`` output is unaffected and still appears:

=========================  ==============================================================================
``--capture``              Effect on the ``Logs`` column
=========================  ==============================================================================
``fd`` *(default)*         Everything, including output written by subprocesses and C extensions
``sys``                    Everything Python itself writes; a subprocess's output is **not** captured
``tee-sys``                As ``sys``, and it still prints live to the terminal
``no`` (same as ``-s``)    **logging only** - stdout and stderr are gone
=========================  ==============================================================================

**Log level.** ``logging`` output is captured from ``WARNING`` up unless told otherwise, so ``log.info(...)`` and
``log.debug(...)`` calls will not be in the report until the level is lowered:

=========================  ==============================================================================
``--log-level``            Logging captured
=========================  ==============================================================================
unset *(default)*          Whatever the root logger emits - ``WARNING`` and above
``DEBUG``                  Everything
``INFO``                   ``INFO`` and above
``WARNING``                ``WARNING`` and above
``ERROR`` / ``CRITICAL``   Only the levels named and above
=========================  ==============================================================================

::

    $ pytest tests/ --log-level=INFO

**Already running with** ``-s``? Just remove it. Capture is on by default, so nothing needs to be added in its
place::

    [pytest]
    addopts = -v

The one thing ``-s`` gave you that plain capture does not is seeing output in the terminal *while* the tests run - with
capture on, ``pytest`` only replays it afterwards, for the tests that failed. If you want both, ``--capture=tee-sys``
streams it live *and* keeps it for the report::

    [pytest]
    addopts = -v --capture=tee-sys

(Stay on ``-s`` if you drop into ``pdb``. And note ``tee-sys`` only tees Python's own ``sys.stdout`` / ``sys.stderr``,
so if the output you want comes from a subprocess or a C extension, plain ``fd`` capture is the one that keeps it.)

the Logs column is empty
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Work down this list; the first one that applies is the answer:

1. **Is the run using** ``-s`` **or** ``--capture=no``? Check ``addopts`` in ``pytest.ini`` / ``pyproject.toml`` /
   ``tox.ini``, not just the command you typed - a flag set there applies to every run. This is the most common cause,
   and the report says so above the ``Test Metrics`` table when it is happening. Removing the flag is the whole fix;
   there is no replacement flag to add.
2. **Are you on** ``--report-logs=failed`` **while the tests that produce output are passing?** That mode keeps output
   for failed and errored tests only; a passing test shows a dash however much it printed.
3. **Is the output** ``logging`` **below** ``WARNING``? ``log.info(...)`` and ``log.debug(...)`` are not recorded
   until you pass ``--log-level=INFO`` or ``--log-level=DEBUG``.
4. **Do the tests actually produce any output?** A suite of plain assertions prints nothing, and a dash is then the
   correct answer - a failed test included, since its message is in the ``Error Message`` column, not here. Add a
   ``print(...)`` to one test and re-run to confirm the column is working.

The ``Environment`` panel states what the run kept and from which log level - e.g.
``all tests: stdout, stderr and logging, logging from WARNING`` - so you can always tell which of these you are in.

..

        pytest.ini

Alternate option is to add this snippet in the ``pytest.ini`` file::

    [pytest]
    addopts = -v -rf --capture=tee-sys --title='PYTEST REPORT'
    html_report = ./reports/%Y%m%d/report_%H%M.html
    environment = staging
    build_info =
        branch=main
        team=payments
    report_logs = all
    report_log_limit = 10000
    report_attachments = all
    report_attachment_limit = 20000

``report_logs`` takes the same values as ``--report-logs`` (``all`` / ``failed`` / ``none``) and ``report_log_limit``
the same as ``--report-log-limit`` (a character count, or ``0`` for no limit). ``report_attachments`` and
``report_attachment_limit`` mirror ``--report-attachments`` and ``--report-attachment-limit`` the same way.

``html_report`` takes the same value as ``--html-report``, placeholders included, and is the way to set the report
location without going through ``addopts``.

**Note:** ``--html-report`` overrides the ``html_report`` ini value; ``--environment`` overrides the ``environment``
ini value; ``--build-info`` entries are added to the ones set in the ini file rather than replacing them;
``--report-logs``, ``--report-log-limit``, ``--report-attachments`` and ``--report-attachment-limit`` override their
ini values

**Note:** If you fail to provide ``--html-report`` tag, it consider your project's home directory as the base

screenshots
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Import ``attach`` from the library and hand it the PNG bytes of a screenshot. It takes the image itself rather than a
browser, so it works with Selenium, Playwright, or anything else that can produce a PNG::

    from pytest_html_reporter import attach

    attach(data=self.driver.get_screenshot_as_png())   # Selenium
    attach(data=page.screenshot())                     # Playwright
    attach(data=await page.screenshot())               # Playwright, async API

**Note:** every image you attach is kept, whatever the test did - a screenshot of a pass is a baseline worth having.
Only the tests that actually called ``attach`` appear in the gallery, so capturing on failure alone is a matter of
deciding when to call it.

``attach`` can be called from anywhere in the test's lifecycle: the test body, a ``unittest`` ``tearDown``, a pytest
fixture's teardown, or a ``pytest_runtest_makereport`` hook. Capturing on failure only - the usual want - is the
``rep_call.failed`` test in the fixture below; drop it to photograph every test::

    # conftest.py
    import pytest
    from pytest_html_reporter import attach

    @pytest.fixture(autouse=True)
    def screenshot_on_failure(page, request):
        yield
        if request.node.rep_call.failed:
            attach(data=page.screenshot())

    @pytest.hookimpl(tryfirst=True, hookwrapper=True)
    def pytest_runtest_makereport(item, call):
        outcome = yield
        rep = outcome.get_result()
        setattr(item, "rep_" + rep.when, rep)

Or skip the fixture and attach straight from the hook, which already has the browser in ``item.funcargs``::

    # conftest.py
    import pytest
    from pytest_html_reporter import attach

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(item, call):
        outcome = yield
        rep = outcome.get_result()

        if rep.when == "call" and rep.failed:
            driver = item.funcargs.get("driver")
            if driver is not None:
                attach(data=driver.get_screenshot_as_png())

**Note:** put the hook in ``conftest.py``. pytest does pick one up from a test module as well, but only for that
module's own tests - a conftest covers every test under it, which is almost always what you want.

The same hook covers Playwright by reaching for ``pytest-playwright``'s ``page`` fixture instead::

    page = item.funcargs.get("page")
    if page is not None:
        attach(data=page.screenshot())

**Note:** the hook is synchronous, so Playwright's async API cannot be photographed from it - there is nowhere to
``await``. With ``async`` tests, call ``attach`` from the test body instead.

.. image:: https://img.shields.io/badge/Attach_screenshot_snippet-000?style=for-the-badge&logo=ko-fi&logoColor=white
   :target: https://gist.github.com/prashanth-sams/f0cc2102fc3619b11748e0cbda22598b


.. image:: https://i.imgur.com/1HSYkdC.gif


api logs / attachments
^^^^^^^^^^^^^^^^^^^^^^^^^^^

See it before you wire anything up - the bundled demo needs no browser and no network::

    $ pytest tests/functional/test_attachments.py --html-report=./report

A picture is no use when the thing under test is an API. ``attach_text``, ``attach_json``, ``attach_api`` and
``attach_file`` take the payloads instead, and everything a test hands over is kept against that test and opened from
the new ``API Logs`` tab. The ``Test Metrics`` table gains a ``Data`` column counting what each test attached;
clicking it crosses to the tab with the list already narrowed to that one test.

.. code-block:: python

    from pytest_html_reporter import attach_api, attach_file, attach_json, attach_text

    attach_api(requests.get(url))                         # the whole call
    attach_json({"expected": order, "got": response})     # pretty-printed, secrets blanked
    attach_text(query, name="Query", format="sql")        # any text at all
    attach_file("payloads/order.json")                    # a small file from disk


For example, attaching the JSON response body

.. code-block:: python

    attach_json(requests.get("https://reqres.in/api/users/2").json())


api calls
"""""""""""""""""""""""""""

``attach_api`` is the one to reach for when a test talks HTTP. Hand it a response object and it takes the call apart::

    def test_creates_an_order():
        response = requests.post(url, json=payload, headers=headers)
        attach_api(response)

        assert response.status_code == 201

**Attach on failure, not on every call.** Keeping every response buries the one that matters and grows the report for
no reason; the payload worth having is the one behind a failure. Attach from a fixture's teardown and let the outcome
decide - the reporter builds a test's record after the finalizers have run, which is what makes this work::

    # conftest.py
    import pytest
    from pytest_html_reporter import attach_api

    @pytest.fixture
    def api(request):
        client = ApiClient()
        yield client

        if request.node.rep_call.failed:
            attach_api(client.last_response)

    # lets the fixture above see how the test ended
    @pytest.hookimpl(tryfirst=True, hookwrapper=True)
    def pytest_runtest_makereport(item, call):
        outcome = yield
        setattr(item, "rep_" + outcome.get_result().when, outcome.get_result())

The same guidance is printed on the ``API Logs`` tab itself whenever a run attaches nothing, so it is there when you
go looking for it.

The attachment holds the response body, the request body, both sets of headers, and the **curl command that repeats
the call** - which is the first thing anyone does with a failed request, and the tedious thing to rebuild by hand from
a report. The rail entry carries the method, the path, the status code (coloured by class) and how long it took.

Nothing is imported to read the response, so ``requests`` and ``httpx`` both work out of the box - and so does the
async one, since it is the returned response that is passed, not the client::

    attach_api(httpx.get(url))                     # httpx
    attach_api(await client.get(url))              # httpx, async API

Every field can also be given directly, and an explicit one always wins over the response object. That is what makes
the helper usable from a client neither library resembles, from a call reconstructed out of a log, or through a proxy
that rewrites the URL::

    attach_api(method="POST", url="/orders", status=500,
               request_body=payload, response_body=body, duration=1.4)

    attach_api(response, url=upstream_url)         # override just the one field

=========================  ==============================================================================
Argument                   What it is
=========================  ==============================================================================
``response``               a response object to read the rest off; optional
``name``                   the title in the rail *(default:* ``METHOD /path`` *)*
``method`` ``url``         the request line
``status`` ``reason``      the response line, e.g. ``422`` and ``Unprocessable Entity``
``duration``               how long the call took, **in seconds**
``request_headers``        a dict, a list of pairs, or any headers object with ``items()``
``request_body``           ``str``, ``bytes``, or a ``dict`` / ``list`` to be serialised
``response_headers``       as above
``response_body``          as above
``content_type``           forces the syntax when there is no ``Content-Type`` header to read
``redact``                 ``False`` keeps credentials in the report - see below
=========================  ==============================================================================

**Note:** a body that parses as JSON is pretty-printed, whichever way it arrived. One that does not is kept exactly as
it came, so half a response - the interesting case when a call is cut off - is still readable.

credentials are blanked out
"""""""""""""""""""""""""""

A report is a build artifact. It gets published by CI, attached to tickets and pasted into chat, so ``attach_api`` and
``attach_json`` replace anything that looks like a credential with ``<redacted>`` - in the headers, in the curl
command, and in the fields of a JSON body at any depth. ``Authorization``, ``Cookie``, ``Set-Cookie``, any name
containing ``token``, ``secret``, ``password``, ``api-key`` or ``x-auth``, and their underscore spellings, are all
covered - in a query string as well, since ``?api_key=`` is as ordinary in an API suite as the header is.

::

    Authorization: <redacted>
    Content-Type: application/json

Pass ``redact=False`` when the report is not leaving your machine and you need the real value::

    attach_api(response, redact=False)

text, json and files
"""""""""""""""""""""""""""

``attach_text`` takes anything at all. ``format`` only picks how the viewer lays the text out - it is never used to
reinterpret what you passed - and understands ``text`` *(default)*, ``json``, ``xml``, ``html``, ``yaml``, ``sql`` and
``curl``::

    attach_text(response.text, name="Response body", format="json")
    attach_text(cursor.query, name="Query", format="sql")
    attach_text("the third retry is the one that worked")

``attach_json`` takes a ``dict``, a ``list`` or a JSON string and pretty-prints it, with the same redaction applied::

    attach_json({"expected": {"id": 4711}, "got": {"error": "sku unknown"}}, name="Diff")

``attach_file`` reads a small text file - a payload, a config, a HAR - and names it after the file. The syntax is
guessed from the extension unless ``format`` says otherwise::

    attach_file("payloads/order.json")
    attach_file(har_path, name="Network trace")

A file holding JSON is redacted and pretty-printed like any other body - of everything you can attach this is the
likeliest to be carrying a credential, since a HAR is a recording of the auth headers. A file that is not structured
is kept verbatim: there is nothing to key a redaction off, and mangling a config file would be worse than not trying.

when to call them
"""""""""""""""""""""""""""

Like ``attach``, these can be called from anywhere in the test's lifecycle: the test body, a ``unittest``
``tearDown``, a pytest fixture's teardown or a ``pytest_runtest_makereport`` hook. Attaching the last call only when a
test fails is a fixture away::

    # conftest.py
    import pytest
    from pytest_html_reporter import attach_api

    @pytest.fixture
    def api(request):
        client = Client()
        yield client
        if request.node.rep_call.failed and client.last_response is not None:
            attach_api(client.last_response)

    @pytest.hookimpl(tryfirst=True, hookwrapper=True)
    def pytest_runtest_makereport(item, call):
        outcome = yield
        rep = outcome.get_result()
        setattr(item, "rep_" + rep.when, rep)

**Note:** put the hook in ``conftest.py``. pytest does pick one up from a test module as well, but only for that
module's own tests - a conftest covers every test under it, which is almost always what you want.

A test that is retried by ``pytest-rerunfailures`` and attaches nothing on the attempt that finally passed keeps what
the failing attempt attached, rather than losing the evidence by succeeding.

keeping the file down
"""""""""""""""""""""""""""

Attachments are held outside the metrics table, so they are never swept into its search box or into the CSV, Excel and
print exports. Two options decide how much of them is kept at all.

``--report-attachments`` narrows whose attachments survive:

=========================  ==============================================================================
Value                      Kept
=========================  ==============================================================================
``all`` *(default)*        Every test's
``failed``                 Only ``FAIL`` and ``ERROR`` tests'
``none``                   Nothing - the tab and the ``Data`` column go quiet
=========================  ==============================================================================

``--report-attachment-limit`` caps the characters kept per payload. What survives is the **start** of it - which is
the opposite of the log limit, because a response puts its status, its error field and its first records at the top -
with a note saying how much was dropped:

=========================  ==============================================================================
Value                      Kept
=========================  ==============================================================================
``20000`` *(default)*      20,000 characters per payload
any positive integer       Characters per payload
``0``                      Everything
=========================  ==============================================================================

::

    $ pytest --html-report=./report --report-attachments=failed --report-attachment-limit=5000


parallel runs
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Runs distributed with ``pytest-xdist`` are gathered into a single report. Every worker sends its results back to the
controller, which merges them and writes one report - one build in ``Archives``, one set of totals, one row per test -
whichever way the tests were distributed::

    $ pytest tests/ -n 2 --html-report=./report
    $ pytest tests/ -n auto --dist loadfile --html-report=./report

Tests are listed in collection order rather than the order the workers happened to finish them in, so a parallel report
reads the same as a serial one. Nothing needs to be configured, and running without ``-n`` is unaffected.

**Note:** results are handed over when a worker finishes, so tests from a worker that crashes outright (rather than
failing) are not in the report - pytest reports the crash itself


Is there a demo available for this gem?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Yes, you can use this demo as an example, https://github.com/prashanth-sams/pytest-html-reporter::

    $ pytest tests/functional/