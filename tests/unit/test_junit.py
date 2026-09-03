"""Cover the JUnit XML the reporter writes for a CI server to read.

--report-junit builds the document from the same records the html report is
built from, rather than handing the job to pytest's own --junitxml, so these
tests are mostly about the mapping: every status this plugin can store has to
land on the element its consumers expect, the counts in the header have to be
the elements underneath it, and nothing a failing test can put in a message may
make the file unparseable.

The last group runs real pytest processes, because the two questions a mapping
test cannot answer are whether the file is written at all - a shard leg owes
one to nobody, a run that collected nothing still owes CI a document - and
whether the names in it are the names pytest itself would have written.
"""

import os
import subprocess
import sys
import textwrap
import xml.etree.ElementTree as ElementTree
from io import StringIO

import pytest

from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.junit import (
    JunitOptions,
    junit_xml,
    junit_xpass,
    write_junit,
)


class _FakePluginManager:
    def hasplugin(self, name):
        return False


class _FakeConfig:
    """Just enough of pytest's Config for the option helpers.

    Both halves of an option are answered - the flag and the ini key - because
    every option in this plugin has both and the pair is what has to be tested.
    """

    def __init__(self, options=None, ini=None):
        self._options = options or {}
        self._ini = ini or {}
        self.pluginmanager = _FakePluginManager()

    def getoption(self, name, default=None):
        return self._options.get(name, default)

    def getini(self, name):
        if name not in self._ini:
            raise ValueError(name)
        return self._ini[name]


_TOUCHED = (
    "_test_metrics_content", "_suite_metrics_content", "_test_suite_name",
    "_test_pass_list", "_test_fail_list", "_test_skip_list", "_test_xpass_list",
    "_test_xfail_list", "_test_error_list", "_attach_screenshot_details",
    "_pass", "_fail", "_skip", "_error", "_xpass", "_xfail", "_total",
    "_executed",
)


@pytest.fixture(autouse=True)
def _isolate_config_vars():
    """ConfigVars is class-level state, so hand each test a clean copy."""
    saved = {name: getattr(ConfigVars, name) for name in _TOUCHED}
    for name in _TOUCHED:
        setattr(ConfigVars, name, [] if isinstance(saved[name], list) else type(saved[name])())
    yield
    for name, value in saved.items():
        setattr(ConfigVars, name, value)


def _record(suite, name, status, index, worker="", **kwargs):
    record = {
        "suite_name": suite,
        "test_name": name,
        "nodeid": suite + "::" + name,
        "status": status,
        "message": "",
        "duration": 0.01,
        "rerun": 0,
        "index": index,
        "worker": worker,
        "screenshots": [],
        "logs": [],
        "phases": {},
    }
    record.update(kwargs)
    return record


def _collect_record(path, status, message="", test_name="(collection error)"):
    """The record store_collect_record writes for a module that would not load."""
    return _record(path, test_name, status, -1, nodeid=path, collect=True, message=message)


def _document(records, **kwargs):
    """The document as a parser sees it, never the element tree as it was built.

    Going through the serialised text is the whole point of these assertions:
    the escaping, the declaration and every attribute value are only real once
    they have been written out, and a test that read the tree back in memory
    would happily pass on a document no CI server can parse.
    """
    return ElementTree.fromstring(junit_xml(records, **kwargs))


def _cases(records, **kwargs):
    return _document(records, **kwargs).findall("testsuite/testcase")


def _one_case(records, **kwargs):
    cases = _cases(records, **kwargs)
    assert len(cases) == 1, [case.attrib for case in cases]

    return cases[0]


def _properties(document):
    return {node.get("name"): node.get("value")
            for node in document.findall("testsuite/properties/property")}


# --------------------------------------------------------------------------
# resolving the options
# --------------------------------------------------------------------------

def test_the_xpass_mode_accepts_pass_fail_and_skip():
    """All three, from the flag and from the ini key, with the flag winning.

    The plan's own flag table says {pass,fail} - what ships is the wider set,
    because a team whose policy is that an xfail marker left on a passing test
    is a defect wants it out of the pass column without turning the build red.
    """
    assert junit_xpass(_FakeConfig()) == "pass"

    for mode in ("pass", "fail", "skip"):
        assert junit_xpass(_FakeConfig(options={"report_junit_xpass": mode})) == mode
        assert junit_xpass(_FakeConfig(ini={"report_junit_xpass": mode})) == mode

    config = _FakeConfig(options={"report_junit_xpass": "skip"}, ini={"report_junit_xpass": "fail"})
    assert junit_xpass(config) == "skip"


def test_the_xpass_mode_refuses_anything_else():
    """Rather than falling back to the default, which is the one answer the
    team setting it was trying to avoid."""
    with pytest.raises(pytest.UsageError):
        junit_xpass(_FakeConfig(options={"report_junit_xpass": "ignore"}))


# --------------------------------------------------------------------------
# one record, one element
# --------------------------------------------------------------------------

def test_a_passing_test_is_a_bare_testcase():
    case = _one_case([_record("tests/test_login.py", "test_admin_can_sign_in", "PASS", 0)])

    assert case.get("classname") == "tests.test_login"
    assert case.get("name") == "test_admin_can_sign_in"
    assert list(case) == []


def test_a_failure_carries_the_first_line_as_the_message_and_the_body_as_text():
    """The attribute is the assertion that failed; the body is everything.

    The leading blank line is not decoration: a captured longrepr very often
    starts with one, and a message attribute holding nothing but whitespace is
    what every consumer would then show in its summary column.
    """
    message = "\nassert 401 == 200\n +  where 401 = <Response 401>.status_code\n"
    case = _one_case([_record("tests/test_pay.py", "test_checkout", "FAIL", 0, message=message)])

    failure = case.find("failure")
    assert failure.get("message") == "assert 401 == 200"
    assert failure.text == message


def test_a_setup_error_says_so_and_a_teardown_error_says_so():
    """Which phase broke is read off ``phases``: a record that never got as far
    as a call never ran the test at all."""
    broke = "ConnectionRefusedError: [Errno 111] Connection refused"

    setup = _one_case([_record("tests/test_db.py", "test_needs_pool", "ERROR", 0, message=broke)])
    teardown = _one_case([_record("tests/test_db.py", "test_returns_pool", "ERROR", 0,
                                  message=broke, phases={"setup": 1.0, "call": 5.0, "teardown": 2.0})])

    assert setup.find("error").get("message") == 'failed on setup with "%s"' % broke
    assert setup.find("error").text == broke
    assert teardown.find("error").get("message") == 'failed on teardown with "%s"' % broke


def test_a_skip_reports_the_reason_not_the_tuple_repr():
    """pytest hands the location over as a (path, lineno, reason) tuple and the
    record stores the repr of it, which is not what anyone opening the build
    wants to read in an attribute already called ``message``."""
    case = _one_case([_record("tests/test_slow.py", "test_nightly_only", "SKIP", 0,
                              message="('/app/tests/test_slow.py', 14, 'Skipped: not today')")])

    skipped = case.find("skipped")
    assert skipped.get("type") == "pytest.skip"
    assert skipped.get("message") == "not today"
    assert skipped.text == "/app/tests/test_slow.py:14: not today"


def test_an_xfail_is_a_skipped_with_the_pytest_xfail_type_and_an_empty_body():
    """Never a failure. Azure DevOps reads any failure or error as a failed
    run, so mapping a documented known bug onto one turns every suite that
    documents its known bugs red across three CI systems at once."""
    case = _one_case([_record("tests/test_bugs.py", "test_known_upstream", "xFAIL", 0,
                              message="reason: upstream bug 4412")])

    skipped = case.find("skipped")
    assert skipped.get("type") == "pytest.xfail"
    assert skipped.get("message") == "upstream bug 4412"
    assert skipped.text is None


def test_an_xpass_is_a_passing_testcase_by_default_and_a_failure_on_request():
    """pytest's own writer emits a plain passing testcase for a non-strict
    XPASS, and non-strict is the only kind that can reach here, so the default
    is parity - and the two other modes are there for the teams who disagree."""
    records = [_record("tests/test_bugs.py", "test_fixed_upstream", "xPASS", 0)]

    assert list(_one_case(records)) == []

    failed = _one_case(records, xpass="fail")
    assert failed.find("failure").get("message") == "unexpectedly passed"

    skipped = _one_case(records, xpass="skip")
    assert skipped.find("skipped").get("type") == "pytest.xpass"
    assert skipped.find("skipped").get("message") == "unexpectedly passed"


def test_a_collection_error_keeps_a_dotted_classname():
    """A deliberate divergence from pytest, whose own mangling leaves a
    collection record's classname empty - and GitLab groups by classname in
    practice, so every broken module in the repository would be filed together
    under one nameless heading."""
    case = _one_case([_collect_record("tests/test_broken.py", "ERROR",
                                      message="ImportError: cannot import name 'shim'")])

    assert case.get("classname") == "tests.test_broken"
    assert case.get("name") == "(collection error)"

    error = case.find("error")
    assert error.get("message") == "collection failure"
    assert error.text == "ImportError: cannot import name 'shim'"


def test_a_collection_skip_says_the_module_was_skipped():
    """A module skipped whole is not an error, and a build that reported it as
    one would be red for a file the run was told not to look at."""
    case = _one_case([_collect_record("tests/test_windows_only.py", "SKIP",
                                      test_name="(module skipped)",
                                      message="('tests/test_windows_only.py', 1, 'Skipped: win32')")])

    skipped = case.find("skipped")
    assert skipped.get("type") == "pytest.skip"
    assert skipped.get("message") == "collection skipped"


def test_an_unrecognised_status_becomes_an_error_and_is_reported():
    """Loudly, and never absorbed. A shard written by a newer release than the
    one merging it is how this happens, and both other places that map a status
    turn an unknown one into something plausible instead of saying so."""
    options = JunitOptions(stream=StringIO())
    case = _one_case([_record("tests/test_odd.py", "test_from_the_future", "Frobbed", 0)],
                     options=options)

    assert case.find("error").get("message") == "unrecognised status 'Frobbed' from pytest-html-reporter"
    assert options.warnings == [
        "unrecognised status 'Frobbed' for tests/test_odd.py::test_from_the_future; written as an error"
    ]
    assert "unrecognised status" in options.stream.getvalue()


# --------------------------------------------------------------------------
# the document
# --------------------------------------------------------------------------

def test_the_counts_match_the_elements():
    """Recomputed from what was emitted, never summed from what an input
    claimed: Jenkins recounts the children regardless and would then silently
    contradict the header of the same file."""
    document = _document([
        _record("tests/test_a.py", "test_one", "PASS", 0),
        _record("tests/test_a.py", "test_two", "PASS", 1),
        _record("tests/test_a.py", "test_three", "FAIL", 2),
        _record("tests/test_b.py", "test_four", "SKIP", 3),
        _record("tests/test_b.py", "test_five", "xFAIL", 4),
        _record("tests/test_b.py", "test_six", "xPASS", 5),
        _record("tests/test_b.py", "test_seven", "ERROR", 6),
        _collect_record("tests/test_broken.py", "ERROR"),
    ])

    cases = document.findall("testsuite/testcase")
    emitted = [child.tag for case in cases for child in case if child.tag != "system-out"]
    suite = document.find("testsuite")

    assert suite.get("tests") == "8"
    assert suite.get("failures") == str(emitted.count("failure")) == "1"
    assert suite.get("errors") == str(emitted.count("error")) == "2"
    assert suite.get("skipped") == str(emitted.count("skipped")) == "2"

    # passed is not an attribute of its own, so it is the tests left over - and
    # the four numbers adding up to the total is the property being asserted.
    assert len([case for case in cases if list(case) == []]) == 3

    # The root repeats the suite's numbers because the consumers disagree about
    # which of the two they read, and two headers that contradict each other
    # are worse than one that says the same thing twice.
    for name in ("tests", "failures", "errors", "skipped"):
        assert document.get(name) == suite.get(name)


def test_time_comes_from_phases_not_from_duration():
    """duration is measured from setup to the start of teardown and rounded to
    two decimals, so it drops the teardown and quantises anything quick to 0.0
    - and Azure derives the end of the run from the sum of these numbers."""
    case = _one_case([_record("tests/test_a.py", "test_one", "PASS", 0, duration=0.0,
                              phases={"setup": 30.0, "call": 1200.0, "teardown": 4.0})])

    assert case.get("time") == "1.234"


def test_a_rerun_is_one_testcase_with_the_count_in_system_out():
    """One element per nodeid, never one per attempt: an extra element inflates
    the count, and a duplicate is read as failed by GitLab and passed by
    Jenkins for the same build. The count goes in system-out as well as in the
    properties, because GitLab ignores properties outright."""
    document = _document([_record("tests/test_flaky.py", "test_eventually_settles", "PASS", 0, rerun=2)])

    cases = document.findall("testsuite/testcase")
    assert len(cases) == 1
    assert cases[0].find("system-out").text.splitlines() == ["reruns: 2"]
    assert _properties(document)["reruns"] == "2"


def test_control_characters_do_not_break_the_document():
    """A record's message is stored raw - the page escapes it only at render
    time - so a terminal control byte written by a failing test would otherwise
    go straight into the file the whole pipeline parses."""
    document = junit_xml([_record("tests/test_a.py", "test_one", "FAIL", 0,
                                  message="boom \x07 and \x00 too")])

    assert "\x07" not in document
    assert "\x00" not in document

    case = ElementTree.fromstring(document).find("testsuite/testcase")
    assert case.find("failure").text == "boom #x07 and #x00 too"


def test_two_records_that_mangle_alike_get_distinct_names():
    """Two shards that both ran a test, or two ids that differ only in a
    character the mangling drops. An emitted duplicate is worse than a renamed
    test: the same build is then reported with two different outcomes
    depending on which CI server is looking at it."""
    options = JunitOptions(stream=StringIO())
    cases = _cases([
        _record("tests/test_a.py", "test_one", "PASS", 0, _shard="1-4"),
        _record("tests/test_a.py", "test_one", "FAIL", 1, _shard="2-4"),
    ], options=options)

    assert [case.get("name") for case in cases] == ["test_one", "test_one [2]"]
    assert options.warnings == [
        "two tests share the JUnit name tests.test_a.test_one; the later one is written as test_one [2]"
    ]


def test_attachment_lines_are_relative_to_the_xml(tmp_path):
    """A collector resolves the path against the file it read it from, which is
    not where the screenshots live whenever CI is told to put the xml
    somewhere of its own."""
    record = _record("tests/test_gamma.py", "test_shoots", "FAIL", 0,
                     screenshots=[{"name": "3-4/1788411677983-1"}])

    path = write_junit(str(tmp_path / "xml" / "junit.xml"), [record],
                       report_base=str(tmp_path / "report"))

    case = ElementTree.parse(path).getroot().find("testsuite/testcase")
    assert case.find("system-out").text.splitlines() == [
        "[[ATTACHMENT|../report/pytest_screenshots/3-4/1788411677983-1.png]]"
    ]


def test_stderr_sections_go_to_system_err_and_there_is_one_of_each():
    """At most one of each element per testcase. pytest's own writer emits
    system-out twice for a skipped test, and a document with two of them is one
    whose second some parsers drop and others concatenate."""
    case = _one_case([_record("tests/test_a.py", "test_one", "FAIL", 0, logs=[
        {"title": "Captured stdout call", "text": "on the way out"},
        {"title": "Captured stderr call", "text": "on the way wrong"},
        {"title": "Captured log call", "text": "WARNING something"},
    ])], logging="all")

    assert [child.tag for child in case] == ["failure", "system-out", "system-err"]

    out = case.find("system-out").text
    assert "on the way out" in out
    assert "WARNING something" in out
    assert "on the way wrong" not in out

    assert case.find("system-err").text == "--- Captured stderr call ---\non the way wrong"


# --------------------------------------------------------------------------
# end to end
# --------------------------------------------------------------------------

SAMPLE = {
    "test_alpha.py": """
        import pytest

        def test_a_pass(): assert True
        def test_a_fail(): assert 1 == 2
        @pytest.mark.skip(reason="nope")
        def test_a_skip(): pass
    """,
    "test_beta.py": """
        import pytest

        def test_b_pass(): assert True
        def test_b_fail(): assert 1 == 2
        @pytest.mark.xfail(reason="known")
        def test_b_xfail(): assert 1 == 2
    """,
}


def _run(tmp_path, *args, **options):
    """Run a suite in its own process and return the finished process.

    A subprocess rather than an inline run: what is being tested is what a real
    pytest process leaves on disk on its way out, and it keeps the outer run's
    own reporter out of the way.

    `expect_report` is the one thing this helper cannot assume, because two of
    these tests are about a run that deliberately writes no report at all.
    """
    files = options.pop("files", SAMPLE)
    expect_report = options.pop("expect_report", True)
    assert not options, sorted(options)

    for name, body in files.items():
        (tmp_path / name).write_text(textwrap.dedent(body).lstrip())

    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--html-report=./report", "-p", "no:cacheprovider"] + list(args),
        cwd=str(tmp_path),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )

    if expect_report:
        report = tmp_path / "report" / "output.json"
        assert report.is_file(), result.stdout

    return result


def _addresses(path):
    return set((case.get("classname"), case.get("name"))
               for case in ElementTree.parse(str(path)).getroot().iter("testcase"))


def test_a_plain_run_writes_a_junit_file(tmp_path):
    """And writes the same test names pytest's own --junitxml would.

    The two writers run over the same suite in turn and their (classname, name)
    sets are compared, because the mangling is a port of pytest's own and the
    whole reason to port it rather than invent one is that a file written here
    stays diffable against a file written there.
    """
    result = _run(tmp_path, "--report-junit=./report/junit.xml")
    _run(tmp_path, "--junitxml=./pytest.xml")

    ours = tmp_path / "report" / "junit.xml"
    theirs = tmp_path / "pytest.xml"
    assert ours.is_file(), result.stdout
    assert theirs.is_file()

    assert _addresses(ours) == _addresses(theirs)
    assert len(_addresses(ours)) == 6


def test_an_xdist_run_writes_one_junit_file(tmp_path):
    """One document from the controller, not one per worker: four files that
    each hold a quarter of the suite are four runs to every CI server that
    globs for them."""
    pytest.importorskip("xdist")

    _run(tmp_path, "-n", "2", "--report-junit=./report/junit.xml")

    written = sorted((tmp_path / "report").rglob("*.xml"))
    assert [path.name for path in written] == ["junit.xml"]

    document = ElementTree.parse(str(written[0])).getroot()
    assert document.get("tests") == "6"
    assert len(document.findall("testsuite/testcase")) == 6


def test_a_shard_run_refuses_to_write_one(tmp_path):
    """A leg that is not also merging renders nothing, so an xml from it would
    be a quarter of the run - and a CI glob would ingest four of those plus the
    merged one and count every test twice."""
    result = _run(tmp_path, "--report-shard=1/2", "--report-junit=./report/junit.xml",
                  expect_report=False)

    assert not (tmp_path / "report" / "junit.xml").exists(), result.stdout
    assert (tmp_path / "report" / "shards" / "1-2" / "records.json").is_file(), result.stdout
    assert "--report-junit is ignored on a shard" in result.stdout


def test_a_run_that_collected_nothing_still_writes_a_valid_document(tmp_path):
    """A missing file reads as "the job never ran", which is the one thing a
    run that finished cleanly is not. The page has nothing to show and is not
    written; the document says tests="0" and is."""
    files = {"test_nothing.py": '"""A module with no tests in it at all."""'}
    result = _run(tmp_path, "--report-junit=./report/junit.xml", files=files, expect_report=False)

    written = tmp_path / "report" / "junit.xml"
    assert written.is_file(), result.stdout

    document = ElementTree.parse(str(written)).getroot()
    assert document.get("tests") == "0"
    assert document.findall("testsuite/testcase") == []


def test_a_mistyped_junit_path_does_not_cost_the_report(tmp_path):
    """The xml is written before the page - deliberately, so an empty run still
    gets one - which is exactly why it may not raise: a bad path would
    otherwise take the html report, output.json and the archived build with it,
    over a typo, in the one hook that runs after every test has finished."""
    files = dict(SAMPLE)
    files["blocker.txt"] = "a file where a directory was asked for"

    result = _run(tmp_path, "--report-junit=./blocker.txt/junit.xml", files=files)

    assert (tmp_path / "report" / "pytest_html_report.html").is_file(), result.stdout
    assert (tmp_path / "report" / "output.json").is_file(), result.stdout
    assert "--report-junit could not write" in result.stdout
