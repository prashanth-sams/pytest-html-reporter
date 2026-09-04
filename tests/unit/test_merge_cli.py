"""Cover the ``pytest-html-reporter`` command - what it refuses to start, what
it writes, and what it says about both.

Driven through ``cli.main(argv)`` rather than by shelling out. It returns the
exit code instead of raising SystemExit, and every test here is about a code, a
stream or a file on disk, so a subprocess would buy nothing but seconds. One
test does run the command in its own process, and that one is about the entry
point being wired rather than about the merge.

The bundles are written by hand. A merge is a pure function over bundle files,
so the file *is* the fixture, and four real shard runs per test would put
minutes on a fifty-seven second suite; tests/unit/test_shards.py owns the proof
that a real leg writes the shape these fixtures write.
"""

import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

from pytest_html_reporter import cli, html_reporter, shards
from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.util import archive_count


class _FakePluginManager:
    def hasplugin(self, name):
        return False


class _FakeConfig:
    """Just enough of pytest's Config for the retention helpers."""

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


# A one-pixel png. Nothing here decodes it - the merge copies the file by the
# name the record holds - but a fixture that is a real image cannot be mistaken
# for the reason a staging test passed.
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00"
       b"\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc```\x00"
       b"\x00\x00\x04\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82")


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
        "attachments": [],
        "steps": [],
        "phases": {},
        "meta": {},
        "bdd": None,
    }
    record.update(kwargs)
    return record


def _shot(name):
    """One entry of a record's `screenshots` list, as collect_screenshots builds it."""
    return {
        "name": name, "suite": "test_a", "test": "test_one",
        "error": "", "label": "attached", "step": -1,
    }


def _bundle(directory, shard_id, records, label=None, session_start=1788411600.0,
            session_end=1788411642.0, hostname="runner", **run):
    """One shard bundle on disk, in the shape `shards.write_bundle` writes.

    The schema string and the version are read off the module rather than
    spelled out, so that a format bump makes every fixture here fail by name
    instead of quietly turning into a folder of files the merge walks past as
    "not a bundle".
    """
    directory = str(directory)
    os.makedirs(directory, exist_ok=True)

    payload = {
        "schema": shards.SHARD_SCHEMA,
        "version": shards.SHARD_VERSION,
        "generator": "pytest-html-reporter tests",
        "shard": {"id": shard_id, "label": label or shard_id, "assets": "pytest_screenshots"},
        "run": {
            "session_start": session_start,
            "session_end": session_end,
            "exitstatus": 0,
            "collected": len(records),
            "token": "",
            "hostname": hostname,
            "platform": "Linux 6.5.0",
            "python": "3.11.9",
            "pytest": "9.1.1",
            "plugins": [],
            "arguments": "-k %s" % shard_id,
            "rootdir": directory,
            "environment": "",
            "build_info": [],
            "capture_row": "",
            "capture_notice": "",
            "xdist_workers": [],
        },
        "coverage": None,
        "counts": {"records": len(records), "collect": 0},
        "records": records,
    }
    payload["run"].update(run)

    path = os.path.join(directory, "records.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)

    return path


def _png(directory, name):
    """A screenshot inside a bundle, where the shard's own leg would have put it."""
    folder = os.path.join(str(directory), "pytest_screenshots")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name + ".png")

    with open(path, "wb") as handle:
        handle.write(PNG)

    return path


def _tests_in(base):
    """(suite, test, status) for every row of the build `base` holds."""
    with open(os.path.join(str(base), "output.json"), encoding="utf-8") as handle:
        data = json.load(handle)

    return [
        (suite["suite_name"], test["test_name"], test["status"])
        for suite in data["content"]["suites"].values()
        for test in suite["tests"].values()
    ]


def _tree(directory):
    """Every file under `directory`, relative and sorted."""
    found = []

    for root, _, files in os.walk(str(directory)):
        for name in files:
            found.append(os.path.relpath(os.path.join(root, name), str(directory)))

    return sorted(found)


# --------------------------------------------------------------------------
# what the merge refuses to start
# --------------------------------------------------------------------------

def test_html_report_must_not_be_a_path_that_merely_contains_html(tmp_path, capsys):
    """`report_path` reads any path with '.html' in it as a file name, so a
    folder called `my.html.d` would put the report in the current directory
    under that name. Refused before anything is read, because by the time
    somebody goes looking for the report the tests have long since run."""
    _bundle(tmp_path / "artifacts" / "1-4", "1-4",
            [_record("tests/test_a.py", "test_one", "PASS", 0)])

    code = cli.main(["merge", str(tmp_path / "artifacts"),
                     "--html-report", str(tmp_path / "my.html.d")])

    assert code == 2
    assert "my.html.d" in capsys.readouterr().err
    assert not (tmp_path / "my.html.d").exists()


def test_an_html_file_named_outright_is_still_accepted(tmp_path, capsys):
    """The guard is about '.html' in the middle of a path, never about the word:
    naming the file itself is half of what the flag is for, and a check that
    refused it would send everybody who does to --html-report ./somewhere."""
    _bundle(tmp_path / "artifacts" / "1-4", "1-4",
            [_record("tests/test_a.py", "test_one", "PASS", 0)])

    code = cli.main(["merge", str(tmp_path / "artifacts"),
                     "--html-report", str(tmp_path / "report" / "build.html")])

    captured = capsys.readouterr()

    assert code == 0, captured.err
    assert (tmp_path / "report" / "build.html").is_file()
    assert str(tmp_path / "report" / "build.html") in captured.out


def test_no_bundles_found_exits_two_and_says_where_it_looked(tmp_path, capsys):
    """The usual cause is a CI step that unpacked the artifacts one directory
    deeper than the merge was pointed at, so the path it walked is the answer."""
    empty = tmp_path / "artifacts"
    empty.mkdir()

    code = cli.main(["merge", str(empty), "--html-report", str(tmp_path / "report")])

    assert code == 2

    error = capsys.readouterr().err
    assert "no shard bundles under" in error
    assert str(empty) in error
    assert not (tmp_path / "report").exists()


def test_a_bad_archive_count_is_reported_against_the_merge_flag(tmp_path, capsys):
    """The merge spells the retention flags the way a pytest run spells them, so
    it refuses them in the same words - and refuses them up front, because these
    three are read deep inside render() where a UsageError would abort a build
    that had already rotated the archive."""
    _bundle(tmp_path / "artifacts" / "1-4", "1-4",
            [_record("tests/test_a.py", "test_one", "PASS", 0)])

    with pytest.raises(pytest.UsageError) as raised:
        archive_count(_FakeConfig(options={"archive_count": "a week"}))

    code = cli.main(["merge", str(tmp_path / "artifacts"),
                     "--html-report", str(tmp_path / "report"),
                     "--archive-count", "a week"])

    assert code == 2
    assert str(raised.value) in capsys.readouterr().err
    assert not (tmp_path / "report").exists()


# --------------------------------------------------------------------------
# reading what arrived
# --------------------------------------------------------------------------

def test_two_bundles_with_the_same_id_keep_the_newer_one(tmp_path, capsys):
    """A retried CI leg whose artifact landed twice is common and recoverable,
    so the merge keeps the copy that finished later and says which two files it
    was choosing between rather than failing the whole matrix over it."""
    _bundle(tmp_path / "artifacts" / "first", "1-4",
            [_record("tests/test_a.py", "test_from_the_first_try", "FAIL", 0)],
            session_end=1788411642.0)
    _bundle(tmp_path / "artifacts" / "retry", "1-4",
            [_record("tests/test_a.py", "test_from_the_retry", "PASS", 0)],
            session_end=1788411900.0)

    code = cli.main(["merge", str(tmp_path / "artifacts"),
                     "--html-report", str(tmp_path / "report")])

    captured = capsys.readouterr()

    assert code == 0, captured.err
    assert _tests_in(tmp_path / "report") == [
        ("tests/test_a.py", "test_from_the_retry", "PASS"),
    ]
    assert "two bundles claim the shard id 1-4" in captured.err
    assert os.path.join("retry", "records.json") in captured.err
    assert "merged 1 shard: 1 test\n" in captured.out


def test_inspect_lists_every_bundle_without_writing_anything(tmp_path, capsys):
    """The question `inspect` answers is "did all four artifacts arrive, and do
    they overlap" - asked before a merge, and asked again when the totals were
    not the totals somebody expected. It must be safe to ask at any point."""
    artifacts = tmp_path / "artifacts"
    _bundle(artifacts / "1-4", "1-4", [_record("tests/test_a.py", "test_one", "PASS", 0)])
    _bundle(artifacts / "2-4", "2-4", [
        _record("tests/test_b.py", "test_two", "PASS", 0),
        _record("tests/test_b.py", "test_three", "FAIL", 1),
    ])

    before = _tree(tmp_path)

    code = cli.main(["inspect", str(artifacts)])

    output = capsys.readouterr().out

    assert code == 0
    assert _tree(tmp_path) == before

    lines = [line for line in output.splitlines() if "records.json" in line]
    assert len(lines) == 2
    assert lines[0].startswith("1-4")
    assert lines[1].startswith("2-4")
    assert "merged 2 shards: 3 tests" in output


def test_inspect_answers_the_same_totals_as_json(tmp_path, capsys):
    """`--json` exists so a pipeline can check the count of arrived shards
    itself; it is the same merge, reported as a document."""
    artifacts = tmp_path / "artifacts"
    _bundle(artifacts / "1-4", "1-4", [_record("tests/test_a.py", "test_one", "PASS", 0)])
    _bundle(artifacts / "2-4", "2-4", [_record("tests/test_b.py", "test_two", "FAIL", 0)])

    code = cli.main(["inspect", str(artifacts), "--json"])

    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert [bundle["id"] for bundle in payload["bundles"]] == ["1-4", "2-4"]
    assert payload["summary"]["shards"] == 2
    assert payload["summary"]["tests"] == 2
    assert payload["summary"]["statuses"] == {"PASS": 1, "FAIL": 1}


# --------------------------------------------------------------------------
# what is written, and what is not
# --------------------------------------------------------------------------

def test_dry_run_writes_nothing_and_prints_the_summary(tmp_path, capsys):
    """The summary of the build that would have been produced, arrived at by
    the same code - which is what makes it worth running before the real one."""
    artifacts = tmp_path / "artifacts"
    _bundle(artifacts / "1-4", "1-4", [
        _record("tests/test_a.py", "test_one", "PASS", 0),
        _record("tests/test_a.py", "test_two", "FAIL", 1),
    ])

    before = _tree(tmp_path)

    code = cli.main(["merge", str(artifacts), "--html-report", str(tmp_path / "report"),
                     "--junit-xml", str(tmp_path / "junit.xml"), "--dry-run"])

    output = capsys.readouterr().out

    assert code == 0
    assert _tree(tmp_path) == before
    assert not (tmp_path / "report").exists()
    assert not (tmp_path / "junit.xml").exists()
    assert "merged 1 shard: 2 tests" in output
    assert "PASS 1, FAIL 1" in output

    # Nothing was written, so nothing is named: the summary's file lines are
    # what a pipeline copies from, and a promised path is worse than none.
    assert "report:" not in output
    assert "junit:" not in output


def test_the_merge_summary_does_not_name_a_report_it_did_not_write(tmp_path, capsys):
    """render() writes no page for a run that produced no records - the
    `if self._records:` guard a plain pytest run obeys too - and a matrix whose
    shards collected nothing between them lands exactly there. Naming the path
    anyway would send the next step of a pipeline off to publish a file that
    was never written, and it would blame the copy."""
    _bundle(tmp_path / "artifacts" / "1-4", "1-4", [])

    code = cli.main(["merge", str(tmp_path / "artifacts"),
                     "--html-report", str(tmp_path / "report")])

    captured = capsys.readouterr()

    assert code == 0
    assert "merged 1 shard: 0 tests" in captured.out
    assert "report:" not in captured.out
    assert "no report was written" in captured.err
    assert not os.path.isfile(str(tmp_path / "report" / "pytest_html_report.html"))


def test_merging_into_the_shard_directorys_parent_keeps_the_shard_screenshots(tmp_path, capsys):
    """`merge ./report --html-report ./report` is the sequential flow's own
    command, and the shards live under it. The merge owns `<out>/pytest_screenshots`
    and clears it; the sources sit in `<out>/shards/<id>/pytest_screenshots` and
    must still be there afterwards, or a second merge of the same folder finds
    the images it staged the first time gone."""
    report = tmp_path / "report"
    shard = report / "shards" / "1-4"

    _bundle(shard, "1-4", [
        _record("tests/test_a.py", "test_one", "FAIL", 0, screenshots=[_shot("1788411677983-1")]),
    ])
    _png(shard, "1788411677983-1")

    # An image from an earlier build of this same report, which the merge owns
    # and must sweep: it belongs to no record in this build.
    _png(report, "stale-1")

    code = cli.main(["merge", str(report), "--html-report", str(report)])

    captured = capsys.readouterr()

    assert code == 0, captured.err
    assert (shard / "pytest_screenshots" / "1788411677983-1.png").is_file()
    assert (report / "pytest_screenshots" / "1-4" / "1788411677983-1.png").is_file()
    assert not (report / "pytest_screenshots" / "stale-1.png").exists()


def test_the_merge_never_opens_a_browser_by_default(tmp_path, monkeypatch, capsys):
    """A pytest run defaults to 'auto' because somebody is very often sat in
    front of it. A merge is run to look at four downloaded artifacts, or by a
    CI step, and neither wants a tab stolen."""
    opened = []
    monkeypatch.setattr(html_reporter, "open_report",
                        lambda path, mode: opened.append((path, mode)))

    _bundle(tmp_path / "artifacts" / "1-4", "1-4",
            [_record("tests/test_a.py", "test_one", "PASS", 0)])

    code = cli.main(["merge", str(tmp_path / "artifacts"),
                     "--html-report", str(tmp_path / "report")])

    captured = capsys.readouterr()

    assert code == 0, captured.err
    assert [mode for _, mode in opened] == ["none"]


# --------------------------------------------------------------------------
# how the merge answers
# --------------------------------------------------------------------------

def test_strict_exits_one_but_still_writes_the_report(tmp_path, capsys):
    """--strict is a verdict about the merge being complete, not about the
    build being publishable: the page that explains what was folded is exactly
    what somebody reading the failed step needs to open."""
    artifacts = tmp_path / "artifacts"
    _bundle(artifacts / "1-4", "1-4", [_record("tests/test_a.py", "test_one", "FAIL", 0)])
    _bundle(artifacts / "2-4", "2-4", [_record("tests/test_a.py", "test_one", "PASS", 0)])

    code = cli.main(["merge", str(artifacts), "--html-report", str(tmp_path / "report"),
                     "--strict"])

    captured = capsys.readouterr()

    assert code == 1
    assert (tmp_path / "report" / "pytest_html_report.html").is_file()
    assert "duplicates folded: 1" in captured.out
    assert "tests/test_a.py::test_one" in captured.err


def test_exit_code_reflects_failures_only_when_asked(tmp_path, capsys):
    """The two flags answer two different questions. A pipeline that wants the
    step to go red on a failing test says --exit-code; one that only wants to
    know all four artifacts arrived says --strict. A merge that read the tests'
    verdict without being asked would make the second impossible."""
    _bundle(tmp_path / "artifacts" / "1-4", "1-4", [
        _record("tests/test_a.py", "test_one", "PASS", 0),
        _record("tests/test_a.py", "test_two", "FAIL", 1),
    ])

    quiet = cli.main(["merge", str(tmp_path / "artifacts"),
                      "--html-report", str(tmp_path / "quiet")])
    without = capsys.readouterr()

    asked = cli.main(["merge", str(tmp_path / "artifacts"),
                      "--html-report", str(tmp_path / "asked"), "--exit-code"])
    capsys.readouterr()

    assert quiet == 0, without.err
    assert asked == 1
    assert (tmp_path / "quiet" / "pytest_html_report.html").is_file()
    assert (tmp_path / "asked" / "pytest_html_report.html").is_file()


def test_an_unwritable_junit_xml_exits_one_from_merge_but_two_from_junit(tmp_path, capsys):
    """Two codes for one failure, because the two commands produced different
    amounts. `merge` has the report on disk and says so - something was made,
    and 2 is reserved for nothing at all - while the XML is the only thing
    `junit` exists to write."""
    _bundle(tmp_path / "artifacts" / "1-4", "1-4",
            [_record("tests/test_a.py", "test_one", "PASS", 0)])

    # A regular file where a directory would have to be, which is what a path
    # typed one segment short looks like from inside the writer.
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    unwritable = str(blocker / "junit.xml")

    merged = cli.main(["merge", str(tmp_path / "artifacts"),
                       "--html-report", str(tmp_path / "report"),
                       "--junit-xml", unwritable])

    from_merge = capsys.readouterr()

    only_xml = cli.main(["junit", str(tmp_path / "artifacts"), "-o", unwritable])

    from_junit = capsys.readouterr()

    assert merged == 1
    assert "--junit-xml could not write" in from_merge.err
    assert (tmp_path / "report" / "pytest_html_report.html").is_file()
    assert "junit:" not in from_merge.out

    assert only_xml == 2
    assert "-o could not write" in from_junit.err
    assert from_junit.out == ""


# --------------------------------------------------------------------------
# the junit subcommand
# --------------------------------------------------------------------------

def test_a_folded_duplicates_attachment_names_the_shard_that_took_it(tmp_path, capsys):
    """A test that failed and was photographed on one shard and passed on the
    next folds into a row from the second shard holding the first shard's
    images. `junit` copies nothing, so it has to name those files the way a
    merged report holds them - under the shard that took them, never under the
    shard the surviving row came from."""
    artifacts = tmp_path / "artifacts"

    _bundle(artifacts / "s1", "s1", [
        _record("tests/test_a.py", "test_one", "FAIL", 0, screenshots=[_shot("1788411677983-1")]),
    ], session_end=1788411642.0)
    _png(artifacts / "s1", "1788411677983-1")

    _bundle(artifacts / "s2", "s2", [
        _record("tests/test_a.py", "test_one", "PASS", 0),
    ], session_end=1788411900.0)

    code = cli.main(["junit", str(artifacts), "-o", str(tmp_path / "junit.xml")])

    captured = capsys.readouterr()

    assert code == 0, captured.err

    root = ET.parse(str(tmp_path / "junit.xml")).getroot()
    cases = root.findall(".//testcase")

    assert len(cases) == 1

    system_out = cases[0].find("system-out").text

    # The row really is the second shard's - which is the whole of the case:
    # looking the image up under it finds nothing, and the picture of the only
    # failure in the matrix would be named in a folder that never held it.
    assert "shard: s2" in system_out
    assert "[[ATTACHMENT|pytest_screenshots/s1/1788411677983-1.png]]" in system_out
    assert "s2/1788411677983-1" not in system_out


def test_the_junit_subcommand_writes_no_report(tmp_path, capsys):
    """A pipeline that publishes test results into GitLab or Azure and keeps no
    HTML should not have to write a build it will throw away."""
    _bundle(tmp_path / "artifacts" / "1-4", "1-4",
            [_record("tests/test_a.py", "test_one", "PASS", 0)])

    code = cli.main(["junit", str(tmp_path / "artifacts"), "-o", str(tmp_path / "junit.xml")])

    captured = capsys.readouterr()

    assert code == 0, captured.err
    assert _tree(tmp_path / "artifacts") == [os.path.join("1-4", "records.json")]
    assert (tmp_path / "junit.xml").is_file()

    root = ET.parse(str(tmp_path / "junit.xml")).getroot()

    assert root.find("testsuite").get("tests") == "1"


# --------------------------------------------------------------------------
# end to end
# --------------------------------------------------------------------------

def _command():
    """How to run the command in its own process.

    The console script is on PATH only once the package has been installed with
    its entry points, and a checkout under test very often has not been; the
    module alias exists for exactly that reason and runs the same
    ``cli.main``. Whichever is there is what this proves is wired.
    """
    from shutil import which

    script = which("pytest-html-reporter")

    return [script] if script else [sys.executable, "-m", "pytest_html_reporter"]


def _run(tmp_path, *args):
    """Run the command in its own process and hand back what it printed."""
    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)

    return subprocess.run(
        _command() + list(args),
        cwd=str(tmp_path),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )


def test_the_command_merges_bundles_in_its_own_process(tmp_path):
    """The entry point, end to end: the same merge, reached the way CI reaches
    it. Everything above calls main() directly, so without this nothing would
    notice the command had stopped being installable."""
    artifacts = tmp_path / "artifacts"
    _bundle(artifacts / "1-4", "1-4", [_record("tests/test_a.py", "test_one", "PASS", 0)])
    _bundle(artifacts / "2-4", "2-4", [_record("tests/test_b.py", "test_two", "FAIL", 0)])

    result = _run(tmp_path, "merge", "./artifacts", "--html-report", "./report")

    report = tmp_path / "report" / "pytest_html_report.html"

    assert result.returncode == 0, result.stdout
    assert report.is_file(), result.stdout
    assert "merged 2 shards: 2 tests" in result.stdout
    assert sorted(_tests_in(tmp_path / "report")) == [
        ("tests/test_a.py", "test_one", "PASS"),
        ("tests/test_b.py", "test_two", "FAIL"),
    ]
