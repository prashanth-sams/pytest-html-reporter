"""The JUnit XML a CI server reads, built from the very records the report is.

The file is generated from the record list rather than by merging the XMLs of
several shards, and rather than by handing the job to ``pytest --junitxml``,
because every merging tool available gets one of four things wrong:

* ``junitparser`` and ``junit-merge`` *sum* the ``tests``/``failures`` counts
  they find in their inputs, so a test that ran on two machines is counted
  twice while only one element survives - the header and the body of the same
  file then disagree.
* A duplicate ``<testcase>`` is read differently by every consumer: GitLab
  keeps the first one it sees and Jenkins keeps the last, so a flaky test that
  failed and then passed is reported red by one and green by the other.
* Azure DevOps derives the end of the run from ``timestamp + SUM(testcase
  @time)``, so a per-test time that is short by a teardown - or rounded to
  ``0.0`` - makes a forty-minute matrix read as instantaneous.
* ``<properties>`` are invisible to two of the four consumers - GitLab ignores
  them outright and Jenkins reads them only with ``keepProperties`` turned on -
  so anything that has to survive the trip (which shard ran a test, how many
  times it was retried) has to be in ``<system-out>`` as well.

Building from records answers all four at once: there is exactly one element
per nodeid, every count is recomputed from the elements actually emitted, the
per-test time comes from the phase milliseconds, and the shard and rerun facts
are written twice on purpose.

Nothing here reads a report, a template or a ``ConfigVars``: it is a pure
function over the record dicts ``html_reporter`` builds, so the plugin and the
merge command produce the same document from the same input.
"""

import os
import platform
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from tempfile import NamedTemporaryFile

import pytest

from pytest_html_reporter import __version__
from pytest_html_reporter.util import _ini, expand_time


# How an unexpectedly passing test is written down. 'pass' is pytest's own
# answer and the default here: this plugin's xPASS is only ever the non-strict
# kind, and a strict xfail that passes never reaches it as xPASS at all - pytest
# reports that as a plain failure with "[XPASS(strict)]" in the text. The other
# two exist for the teams whose policy is that a test marked xfail and passing
# is a test whose marker was not removed.
JUNIT_XPASS_MODES = ("pass", "fail", "skip")

# Which tests carry their captured output into the XML. The spelling and the
# default are pytest's own ``junit_logging`` ini key, so a team moving off
# ``--junitxml`` does not have to learn a second vocabulary.
JUNIT_LOGGING_MODES = ("no", "all", "failed")

# The names of the two statuses a failure-shaped record can carry, used to
# decide what 'failed' means for --report-junit-logging.
FAILED_STATUSES = ("FAIL", "ERROR")

DEFAULT_SUITE_NAME = "pytest"

# The characters XML 1.0 allows in a document, as the inverse set. Anything
# outside it is rendered visually rather than escaped - see _bin_xml_escape.
_ILLEGAL_XML = re.compile(
    "[^\\u0009\\u000a\\u000d\\u0020-\\u007e\\u0080-\\ud7ff\\ue000-\\ufffd\\U00010000-\\U0010ffff]")


# A skipped collector's - and a skipped test's - message is the repr of the
# (path, lineno, reason) tuple pytest puts in ``longrepr``. Either quote is
# accepted around the reason because a reason with an apostrophe in it - "can't
# run here" - is repr'd with double quotes, and that is the everyday case, not
# an exotic one. DOTALL because a reason written across two lines is still one
# reason.
_SKIP_LOCATION = re.compile(r"""^\((.+), (\d+), (['"])(.*)\3\)$""", re.S)

# pytest writes an xfail reason as "reason: <what the marker said>". The prefix
# is noise in an attribute that is already called ``message``.
_XFAIL_PREFIX = "reason: "


# --------------------------------------------------------------------------
# options
# --------------------------------------------------------------------------

def junit_path(config):
    """Where the JUnit XML goes, or '' when nothing asked for one.

    Expanded through strftime like ``--html-report`` is, so a file per run can
    be named with the same placeholders the report already understands.
    """
    value = config.getoption("report_junit", None)
    if value is None or str(value).strip() == "":
        value = _ini(config, "report_junit")

    path = str(value or "").strip()

    return expand_time(path) if path else ""


def junit_xpass(config):
    """How an xPASS is written down: 'pass', 'fail' or 'skip'.

    A value that is none of those fails the run rather than falling back to the
    default: the whole point of setting it is that the team disagrees with the
    default, and quietly giving them the default is the one answer they were
    trying to avoid.
    """
    value = config.getoption("report_junit_xpass", None)
    if value is None or str(value).strip() == "":
        value = _ini(config, "report_junit_xpass")

    mode = str(value or "pass").strip().lower()

    if mode not in JUNIT_XPASS_MODES:
        raise pytest.UsageError(
            "--report-junit-xpass takes pass, fail or skip, not %r" % mode)

    return mode


class JunitOptions(object):
    """Everything the document needs that the records themselves do not carry.

    A plain object rather than a dict so a typo in a caller's keyword is a
    TypeError at the call rather than a silently missing ``hostname`` in a file
    a build server has already ingested.

    ``warnings`` is the record of everything that was written down as a
    compromise - an unrecognised status, a name that had to be made unique -
    so a caller with a ``--strict`` flag can fail the run on it without having
    to parse the stderr it also produced.
    """

    def __init__(self, suite_name=DEFAULT_SUITE_NAME, hostname=None, xpass="pass",
                 logging="no", attachments=True, timestamp=None, time=None,
                 shards=None, reruns=None, duplicates=None, properties=(),
                 report_base="", xml_dir="", stream=None):
        self.suite_name = str(suite_name or DEFAULT_SUITE_NAME)

        # The machine the tests ran on, which is only this machine when this
        # process is also the one that ran them. The merge command always says
        # so explicitly, because the box doing the merging ran nothing and
        # Azure reads this attribute as the name of the agent.
        self.hostname = platform.node() if hostname is None else str(hostname)

        self.xpass = str(xpass or "pass").strip().lower()
        self.logging = str(logging or "no").strip().lower()
        self.attachments = bool(attachments)

        # When the run started, as epoch seconds. Azure reads the ISO stamp
        # built from it as the beginning of the run, so a merged file must
        # carry the earliest shard's start and not the merge's own clock.
        self.timestamp = _now() if timestamp is None else float(timestamp)

        # The wall span of the run in seconds. None means "add up the tests",
        # which is right for a serial run and wrong for anything parallel, so
        # both the plugin and the merge pass a measured value.
        self.time = None if time is None else float(time)

        # {shard id: (label, hostname)} for the runs the records came from.
        # Empty off sharding, and then no shard line is written at all.
        self.shards = dict(shards or {})

        self.reruns = reruns
        self.duplicates = duplicates
        self.properties = list(properties or [])

        # The directory ``pytest_screenshots`` sits in, and the directory the
        # XML itself is written to. Both are needed to turn a record's bare
        # image name into a path a collector can resolve; without them the
        # attachment line falls back to the same relative path the HTML uses.
        self.report_base = str(report_base or "")
        self.xml_dir = str(xml_dir or "")

        self.stream = sys.stderr if stream is None else stream
        self.warnings = []

    def warn(self, message):
        """Say something out loud and remember having said it."""
        self.warnings.append(message)

        try:
            self.stream.write("pytest-html-reporter: %s\n" % message)
        except Exception:
            # The tests are over and the XML is what matters; a closed or
            # captured stderr is not a reason to lose the file.
            pass


def _now():
    """The clock, behind a name.

    ``JunitOptions`` takes a keyword called ``time`` - the attribute the XML
    itself calls it - which shadows the module inside ``__init__``, so the
    default timestamp has to be fetched from out here.
    """
    return time.time()


def _options(kw):
    """The JunitOptions for a call, whether it was handed one or keywords.

    Callers that need the warnings back - the merge, under ``--strict`` - build
    the options themselves and pass ``options=``; callers that do not just pass
    keywords and never see the object.
    """
    options = kw.pop("options", None)

    if options is None:
        return JunitOptions(**kw)

    if kw:
        raise TypeError("junit: options= takes the place of %s" % ", ".join(sorted(kw)))

    return options


# --------------------------------------------------------------------------
# addressing a testcase
# --------------------------------------------------------------------------

def mangle_test_address(nodeid):
    """A nodeid as the dotted name segments JUnit consumers expect.

    A verbatim port of ``_pytest.junitxml.mangle_test_address`` - split on
    ``::``, dot the file part, drop the ``.py``, put any ``[params]`` back on
    the last segment - so a file written here is diffable against one written
    by ``pytest --junitxml`` for the same suite. Porting rather than importing:
    the function is private to pytest and has been moved between modules
    before, and this file is also used by a merge that never loaded pytest's
    own plugin.
    """
    path, possible_open_bracket, params = str(nodeid).partition("[")
    names = path.split("::")

    names[0] = names[0].replace("/", ".")
    names[0] = re.sub(r"\.py$", "", names[0])

    names[-1] += possible_open_bracket + params

    return names


def testcase_address(record):
    """The (classname, name) pair one record is filed under.

    Deliberately not pytest's answer for a collection record. Its nodeid is a
    *file*, so pytest's own code produces an empty classname for it, and every
    consumer that groups by classname - GitLab does, in practice - then files
    every broken module in the repository together under one nameless heading.
    Here the classname is the dotted path of the file that would not load and
    the name says which of the two things happened to it.
    """
    names = mangle_test_address(record.get("nodeid") or "")

    if record.get("collect"):
        return ".".join(names), str(record.get("test_name") or "")

    return ".".join(names[:-1]), names[-1]


def testcase_time(record):
    """How long one test took, in seconds.

    The sum of the phase milliseconds, *not* ``duration``. ``duration`` is
    measured from setup to the start of teardown and then rounded to two
    decimals, so it both omits the teardown and quantises anything quick to
    ``0.0`` - and Azure computes the end of the run as the timestamp plus the
    sum of these numbers, which would report a long matrix as having taken no
    time at all. ``duration`` is still the fallback, for a record whose phases
    never arrived.
    """
    phases = record.get("phases") or {}

    if phases:
        try:
            return sum(float(value) for value in phases.values()) / 1000.0
        except (TypeError, ValueError):
            pass

    try:
        return float(record.get("duration") or 0.0)
    except (TypeError, ValueError):
        return 0.0


# --------------------------------------------------------------------------
# text
# --------------------------------------------------------------------------

def _first_line(text):
    """The first line of a message with anything in it, stripped.

    What goes in a ``message`` attribute: the assertion that failed rather than
    the traceback under it. Leading blank lines are skipped because a captured
    ``longrepr`` very often starts with one.
    """
    for line in str(text or "").splitlines():
        line = line.strip()
        if line: return line

    return ""


def _skip_reason(message):
    """A skip message parsed into (path, lineno, reason).

    pytest hands a skipped test's location over as a ``(path, lineno, reason)``
    tuple and the record stores the *repr* of it, so writing the message
    straight into the XML would put ``('/app/tests/test_x.py', 14, 'Skipped:
    not today')`` in front of whoever opens the build. Anything that does not
    look like that tuple is returned as-is with no location, which is what a
    reason set by hand - or by a future pytest - looks like.
    """
    text = str(message or "").strip()

    match = _SKIP_LOCATION.match(text)
    if match is None:
        return "", "", text

    path = match.group(1).strip()

    # The path arrives as a repr, so it is quoted. The quotes are pytest's, not
    # part of the file name.
    if len(path) >= 2 and path[0] == path[-1] and path[0] in ("'", '"'):
        path = path[1:-1]

    reason = match.group(4)

    # "Skipped: " is how pytest words it for itself; the attribute is already
    # called ``message`` on an element already called ``skipped``.
    if reason.startswith("Skipped: "):
        reason = reason[len("Skipped: "):]

    return path, match.group(2), reason


def _bin_xml_escape(text):
    r"""Render the characters XML cannot hold, visibly rather than as escapes.

    A port of ``_pytest.junitxml.bin_xml_escape``: ``'hello\aworld'`` becomes
    ``'hello#x07world'``. The ``#xAB`` is deliberately *not* an XML entity -
    there is no leading ampersand - because the point is to show the reader
    what the byte was, not to round-trip it.

    Not optional here. A record's ``message`` is stored raw - the report
    escapes it only at render time - so a terminal control byte written by a
    failing test would go straight into the document and make the canonical
    file the whole CI pipeline reads unparseable.
    """
    def repl(match):
        i = ord(match.group())
        if i <= 0xFF: return "#x%02X" % i
        return "#x%04X" % i

    return _ILLEGAL_XML.sub(repl, str(text))


# --------------------------------------------------------------------------
# system-out and system-err
# --------------------------------------------------------------------------

def _attachment_lines(record, opts):
    """``[[ATTACHMENT|path]]`` lines for the images a record kept.

    The one attachment convention GitLab and Azure both understand. The path is
    relative to the XML rather than to the report, because that is what a
    collector resolves it against; with no idea where either file lives it
    falls back to the same relative path the HTML page uses, which is right
    whenever the two sit side by side.
    """
    lines = []

    for entry in record.get("screenshots") or []:
        name = str((entry or {}).get("name") or "")
        if not name: continue

        path = os.path.join("pytest_screenshots", name + ".png")

        if opts.report_base and opts.xml_dir:
            path = os.path.relpath(os.path.join(opts.report_base, path), opts.xml_dir)

        # Collectors read these as URLs, and the build agent reading a file
        # written on Windows is very often not itself on Windows.
        lines.append("[[ATTACHMENT|%s]]" % path.replace(os.sep, "/"))

    return lines


def _shard_line(record, opts):
    """Which shard ran this test, for the consumers that ignore properties."""
    shard = record.get("_shard")
    if not shard: return ""

    label, host = opts.shards.get(shard, (shard, ""))

    if host:
        return "shard: %s (%s)" % (label or shard, host)

    return "shard: %s" % (label or shard)


def _log_sections(record, opts):
    """The captured output this record contributes, honouring --junit-logging.

    'failed' means what it means everywhere else in this plugin: a test that
    ended FAIL or ERROR. A skipped test has nothing worth a log section and an
    xfail's output is the output of a known bug.
    """
    if opts.logging == "no": return []

    if opts.logging == "failed" and str(record.get("status") or "") not in FAILED_STATUSES:
        return []

    return [section for section in (record.get("logs") or []) if section]


def _system_streams(record, opts):
    """The <system-out> and <system-err> bodies for one record, as two strings.

    At most one of each, which is the whole reason this is a function rather
    than a handful of appends: pytest's own writer emits ``<system-out>``
    *twice* for a skipped test - once from ``append_skipped`` and once from its
    teardown branch - and a document with two of them is a document whose
    second one some parsers drop and others concatenate. That is a bug in
    pytest, not a convention worth copying.

    The order inside ``<system-out>`` is fixed: attachments first, because a
    collector scans for them; then the shard, then the rerun count, because
    those are the two facts that would otherwise only live in properties nobody
    reads; then the captured output, which is the longest and least
    machine-read part.
    """
    out = []
    err = []

    if opts.attachments:
        out.extend(_attachment_lines(record, opts))

    shard = _shard_line(record, opts)
    if shard: out.append(shard)

    reruns = record.get("rerun") or 0
    if reruns: out.append("reruns: %s" % reruns)

    for section in _log_sections(record, opts):
        title = str(section.get("title") or "")
        block = "--- %s ---\n%s" % (title, str(section.get("text") or ""))

        # pytest names a section "Captured stderr call", so the stream it came
        # from is in its title and nowhere else in the record.
        if "stderr" in title.lower():
            err.append(block)
        else:
            out.append(block)

    return "\n".join(out), "\n".join(err)


# --------------------------------------------------------------------------
# one record, one outcome element
# --------------------------------------------------------------------------

def _element(tag, text=None, **attrib):
    """An element whose attributes and body are already escaped for XML."""
    node = ET.Element(tag, dict((name, _bin_xml_escape(value))
                                for name, value in attrib.items()))

    if text is not None:
        node.text = _bin_xml_escape(text)

    return node


def _case_pass(record, opts):
    return None, "passed"


def _case_xpass(record, opts):
    """An unexpectedly passing test, written down the way the team asked.

    A bare passing testcase by default, which is exactly what pytest's own
    writer does with a non-strict XPASS - and non-strict is the only kind that
    can reach here, because a strict xfail that passes is reported by pytest as
    a failure and stored by this plugin as FAIL.
    """
    if opts.xpass == "fail":
        message = _first_line(record.get("message")) or "unexpectedly passed"
        return _element("failure", str(record.get("message") or ""), message=message), "failures"

    if opts.xpass == "skip":
        # There is no such type in pytest's own vocabulary, because pytest has
        # no way to spell this. The name is chosen to read as the obvious
        # sibling of pytest.xfail to anyone looking at the file.
        return _element("skipped", type="pytest.xpass", message="unexpectedly passed"), "skipped"

    return None, "passed"


def _case_fail(record, opts):
    message = _first_line(record.get("message")) or "test failed"

    return _element("failure", str(record.get("message") or ""), message=message), "failures"


def _case_error(record, opts):
    """A test that broke outside its own body, in the phase that broke.

    Which phase is read off ``phases``: a record that never got as far as a
    call never ran the test, so this is a setup error; anything else got
    through the body and fell over on the way out. There is no double-counting
    to correct for here - ``refresh_record`` already folds a call failure and a
    teardown error into a single record - so one record is always exactly one
    testcase.
    """
    when = "teardown" if "call" in (record.get("phases") or {}) else "setup"

    first = _first_line(record.get("message"))
    message = 'failed on %s with "%s"' % (when, first) if first else "failed on %s" % when

    return _element("error", str(record.get("message") or ""), message=message), "errors"


def _case_skip(record, opts):
    path, lineno, reason = _skip_reason(record.get("message"))

    body = "%s:%s: %s" % (path, lineno, reason) if path else reason

    return _element("skipped", body, type="pytest.skip", message=reason), "skipped"


def _case_xfail(record, opts):
    """A known bug that behaved like a known bug.

    ``skipped``, never ``failure``. Azure DevOps' outcome model is
    failed-if-failure-or-error, so mapping an expected failure onto ``failure``
    turns every suite that documents its known bugs red across Jenkins, GitLab
    and Azure at once - and the whole reason to mark a test xfail is that its
    failure is not news. The body is empty, as pytest's own writer leaves it:
    the reason is the message and there is nothing else to say.
    """
    # The reason pytest itself recorded, in preference to the message. An
    # xFAIL record's message is the assertion that failed - which is what the
    # page shows, and is the right thing there - but a collector renders this
    # attribute as the reason the test was skipped, and "assert 1 == 2" is not
    # a reason. Falls back to the message for a record built by hand, or by a
    # producer old enough not to carry the key.
    reason = _first_line(record.get("xfail_reason")) or _first_line(record.get("message"))

    if reason.startswith(_XFAIL_PREFIX):
        reason = reason[len(_XFAIL_PREFIX):]

    return _element("skipped", type="pytest.xfail", message=reason), "skipped"


# Every status this plugin can store, and the element it becomes. Explicit and
# closed on purpose: the two places that already map a status - ``_keys.get``
# in append_suite_metrics_row and update_counts' residual "errors are whatever
# is left over" arithmetic - both turn an unrecognised value into something
# plausible, and a canonical CI file is the last place that should be guessing.
STATUS = {
    "PASS": _case_pass,
    "xPASS": _case_xpass,
    "FAIL": _case_fail,
    "ERROR": _case_error,
    "SKIP": _case_skip,
    "xFAIL": _case_xfail,
}

# The two a collection record can carry. A file that would not import produced
# no test to attribute the failure to, so the message is about the collector
# rather than about anything a person wrote.
COLLECT_STATUS = {
    "SKIP": ("skipped", "collection skipped", "skipped", {"type": "pytest.skip"}),
    "ERROR": ("error", "collection failure", "errors", {}),
}


def _outcome(record, opts):
    """The outcome element for one record, and the count it belongs to."""
    status = str(record.get("status") or "")

    if record.get("collect"):
        tag, message, counted, extra = COLLECT_STATUS.get(status, COLLECT_STATUS["ERROR"])
        attrib = dict(extra)
        attrib["message"] = message

        return _element(tag, str(record.get("message") or ""), **attrib), counted

    handler = STATUS.get(status)
    if handler is not None:
        return handler(record, opts)

    # Loudly, and as an error. A shard written by a newer version of this
    # plugin than the one doing the merging is the way this happens, and the
    # honest answer is a document that says so rather than a green build.
    opts.warn("unrecognised status %r for %s; written as an error"
              % (status, record.get("nodeid") or "?"))

    message = "unrecognised status %r from pytest-html-reporter" % status

    return _element("error", str(record.get("message") or ""), message=message), "errors"


# --------------------------------------------------------------------------
# the document
# --------------------------------------------------------------------------

def _deduplicate_addresses(cases, opts):
    """Make every (classname, name) pair in the document unique.

    Two records can mangle to one address - a nodeid stripped down to the same
    name by a merge, or two parametrisations whose ids differ only in a
    character the mangling drops. An emitted duplicate is worse than a renamed
    test: GitLab keeps the first and Jenkins keeps the last, so the same build
    is reported with two different outcomes depending on who is looking.
    """
    seen = {}

    for case in cases:
        address = (case.get("classname", ""), case.get("name", ""))

        seen[address] = seen.get(address, 0) + 1
        if seen[address] == 1: continue

        opts.warn("two tests share the JUnit name %s.%s; the later one is written as %s [%d]"
                  % (address[0], address[1], address[1], seen[address]))

        case.set("name", "%s [%d]" % (address[1], seen[address]))

    return cases


def _properties(records, opts):
    """The <properties> block, or None when there is nothing worth saying.

    Everything in here is also written somewhere a consumer that ignores
    properties can see it. This is the machine-readable copy, not the only one.
    """
    pairs = [("pytest-html-reporter", __version__)]

    if opts.shards:
        ids = sorted(opts.shards)
        pairs.append(("shards", str(len(ids))))
        pairs.append(("shard.ids", ",".join(ids)))

        hosts = [opts.shards[key][1] for key in ids if opts.shards[key][1]]
        if hosts: pairs.append(("shard.hosts", ",".join(hosts)))

    reruns = opts.reruns
    if reruns is None:
        reruns = sum(int(record.get("rerun") or 0) for record in records)
    pairs.append(("reruns", str(reruns)))

    if opts.duplicates is not None:
        pairs.append(("duplicates-folded", str(opts.duplicates)))

    pairs.extend((str(name), str(value)) for name, value in opts.properties)

    element = ET.Element("properties")
    for name, value in pairs:
        element.append(_element("property", name=name, value=value))

    return element


def junit_document(records, **kw):
    """The whole document as an ElementTree Element.

    One ``<testcase>`` per record and one ``<testsuite>`` for the lot of them.
    Not one suite per shard: Azure's run-level timing across several suites is
    ambiguous, and every other consumer flattens them anyway - so shard identity
    lives in the properties and in each testcase's ``<system-out>`` instead.
    """
    opts = _options(kw)

    cases = []
    counts = {"passed": 0, "failures": 0, "errors": 0, "skipped": 0}
    total_time = 0.0

    for record in records:
        classname, name = testcase_address(record)
        seconds = testcase_time(record)
        total_time += seconds

        case = _element("testcase", classname=classname, name=name, time="%.3f" % seconds)

        outcome, counted = _outcome(record, opts)
        if outcome is not None: case.append(outcome)
        counts[counted] += 1

        # After the outcome, as pytest orders them: a reader scanning the file
        # wants to know what happened before they are shown the output.
        out, err = _system_streams(record, opts)
        if out: case.append(_element("system-out", out))
        if err: case.append(_element("system-err", err))

        cases.append(case)

    _deduplicate_addresses(cases, opts)

    # Recomputed from the elements that were actually emitted, never summed
    # from what an input file claimed. Jenkins' SuiteResult recounts the
    # children regardless and would silently contradict a summed attribute, and
    # by construction passed + failures + errors + skipped == tests here.
    # Built as a list of pairs rather than a dict literal because the order the
    # attributes are written in is the order they are inserted, and two runs of
    # the same suite should differ by their numbers and by nothing else.
    totals = [
        ("tests", str(len(cases))),
        ("failures", str(counts["failures"])),
        ("errors", str(counts["errors"])),
        ("skipped", str(counts["skipped"])),
        ("time", "%.3f" % (total_time if opts.time is None else opts.time)),
    ]

    suite = ET.Element("testsuite", dict([("name", _bin_xml_escape(opts.suite_name))] + totals))
    suite.set("timestamp", datetime.fromtimestamp(opts.timestamp).isoformat(timespec="seconds"))
    suite.set("hostname", _bin_xml_escape(opts.hostname))

    suite.append(_properties(records, opts))
    for case in cases:
        suite.append(case)

    # The same numbers again on the root, because the consumers disagree about
    # which of the two elements they read them from and a document whose two
    # headers contradict each other is worse than one that repeats itself.
    name = _bin_xml_escape("%s tests" % opts.suite_name)
    root = ET.Element("testsuites", dict([("name", name)] + totals))
    root.append(suite)

    return root


def junit_xml(records, **kw):
    """The document as text, declaration and all, ready to be written."""
    root = junit_document(records, **kw)

    # Only from 3.9, and the package still has to import on older ones. The
    # indentation is cosmetic - it is there because a canonical CI file is also
    # a file people read and diff - so its absence is not worth a failure.
    indent = getattr(ET, "indent", None)
    if indent is not None: indent(root, space="  ")

    body = ET.tostring(root, encoding="unicode")

    # Written by hand rather than asked of ElementTree, which only emits a
    # declaration when it is serialising to bytes with a named encoding - and
    # then writes the encoding in a case some older readers do not expect.
    return '<?xml version="1.0" encoding="utf-8"?>\n%s\n' % body


def write_junit(path, records, **kw):
    """Write the JUnit XML for `records` to `path`, and return the path.

    Written atomically - a temporary file beside the target, then a rename -
    because a CI collector very often watches the directory it is going to read
    from, and half a document is worse than no document at all: it is a parse
    error attributed to the tests rather than to the reporting.
    """
    path = os.path.abspath(str(path))
    directory = os.path.dirname(path) or "."

    os.makedirs(directory, exist_ok=True)

    # The XML's own directory is what attachment paths are made relative to, so
    # a caller that did not say where the file was going still gets it right.
    options = kw.get("options")
    if options is None:
        kw.setdefault("xml_dir", directory)
    elif not options.xml_dir:
        options.xml_dir = directory

    document = junit_xml(records, **kw)

    handle = NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".xml",
                                dir=directory, delete=False)
    try:
        handle.write(document)
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        os.replace(handle.name, path)
    except Exception:
        handle.close()
        if os.path.exists(handle.name): os.remove(handle.name)
        raise

    return path
