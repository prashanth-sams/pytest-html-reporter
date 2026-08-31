"""Cover how the Coverage tab gets its numbers (#203).

The issue asked for the percentage on the page and either the coverage html
report embedded or a section of its own. What ships reads the numbers and
renders them, so these tests are mostly about the reading: the same figures
have to come out of a live pytest-cov run, a coverage.json and a Cobertura
coverage.xml, and none of the three may take a finished test run down when it
turns out to be missing or malformed.
"""

import json
import os
import re
import subprocess
import sys
import textwrap
import xml.etree.ElementTree as ElementTree

import pytest

from pytest_html_reporter.coverage_report import (
    build_summary,
    collect_coverage,
    coverage_delta,
    coverage_file,
    coverage_grade,
    coverage_limit,
    coverage_mode,
    coverage_target,
    discover_coverage,
    format_lines,
    format_percent,
    has_data,
    percent_of,
    read_coverage_path,
    relative_name,
    ring_dash,
    summarize_json,
    summarize_xml,
    trim_lines,
)


class _FakeConfig:
    """Just enough of pytest's Config for the option/ini resolution helpers."""

    def __init__(self, options=None, ini=None, rootpath=""):
        self._options = options or {}
        self._ini = ini or {}
        self.rootpath = rootpath

    def getoption(self, name, default=None):
        return self._options.get(name, default)

    def getini(self, name):
        if name not in self._ini:
            raise ValueError(name)
        return self._ini[name]


JSON_REPORT = {
    "meta": {"version": "7.16.0", "timestamp": "2026-08-31T20:02:25.536875",
             "branch_coverage": True},
    "files": {
        "src/sample.py": {
            "summary": {"covered_lines": 4, "num_statements": 6, "percent_covered": 62.5,
                        "missing_lines": 2, "excluded_lines": 1, "num_branches": 2,
                        "num_partial_branches": 1, "covered_branches": 1},
            "missing_lines": [4, 7],
        },
        "src/clean.py": {
            "summary": {"covered_lines": 8, "num_statements": 8, "percent_covered": 100.0,
                        "missing_lines": 0, "excluded_lines": 0, "num_branches": 0,
                        "num_partial_branches": 0, "covered_branches": 0},
            "missing_lines": [],
        },
    },
    "totals": {"covered_lines": 12, "num_statements": 14, "percent_covered": 81.25,
               "missing_lines": 2, "excluded_lines": 1, "num_branches": 2,
               "num_partial_branches": 1, "covered_branches": 1},
}

XML_REPORT = """<?xml version="1.0" ?>
<coverage lines-valid="6" lines-covered="4" line-rate="0.6667"
          branches-valid="2" branches-covered="1" branch-rate="0.5">
  <packages><package name="src"><classes>
    <class name="sample.py" filename="src/sample.py">
      <lines>
        <line number="1" hits="1"/>
        <line number="2" hits="1" branch="true" condition-coverage="50% (1/2)" missing-branches="4"/>
        <line number="3" hits="1"/>
        <line number="4" hits="0"/>
        <line number="6" hits="1"/>
        <line number="7" hits="0"/>
      </lines>
    </class>
  </classes></package></packages>
</coverage>
"""


# --------------------------------------------------------------------------
# options
# --------------------------------------------------------------------------

def test_coverage_mode_defaults_to_auto():
    assert coverage_mode(_FakeConfig()) == "auto"


def test_coverage_mode_from_ini():
    assert coverage_mode(_FakeConfig(ini={"report_coverage": "none"})) == "none"


def test_coverage_mode_cli_beats_ini():
    config = _FakeConfig(options={"report_coverage": "auto"}, ini={"report_coverage": "none"})
    assert coverage_mode(config) == "auto"


def test_coverage_mode_ignores_a_value_it_does_not_know():
    assert coverage_mode(_FakeConfig(options={"report_coverage": "maybe"})) == "auto"


def test_coverage_file_from_ini():
    assert coverage_file(_FakeConfig(ini={"report_coverage_file": "cov.xml"})) == "cov.xml"


def test_coverage_limit_defaults_and_floors_at_zero():
    assert coverage_limit(_FakeConfig()) == 500
    assert coverage_limit(_FakeConfig(options={"report_coverage_limit": 0})) == 0
    assert coverage_limit(_FakeConfig(options={"report_coverage_limit": -5})) == 0
    assert coverage_limit(_FakeConfig(options={"report_coverage_limit": "nope"})) == 500


def test_coverage_target_reads_cov_fail_under():
    assert coverage_target(_FakeConfig(options={"cov_fail_under": 85})) == 85.0


def test_coverage_target_is_none_when_nothing_set_it():
    assert coverage_target(_FakeConfig()) is None
    assert coverage_target(_FakeConfig(options={"cov_fail_under": 0})) is None


# --------------------------------------------------------------------------
# shaping
# --------------------------------------------------------------------------

def test_percent_of_calls_an_empty_file_covered():
    """coverage.py does, and a file with no statements missing none of them."""
    assert percent_of(0, 0) == 100.0
    assert percent_of(3, 4) == 75.0


def test_coverage_grade_bands():
    assert coverage_grade(96) == "strong"
    assert coverage_grade(80) == "fair"
    assert coverage_grade(51) == "low"


def test_coverage_grade_follows_the_projects_own_target():
    """--cov-fail-under=60 means 62% is a pass, whatever the default bands say."""
    assert coverage_grade(62, target=60) == "strong"
    assert coverage_grade(62, target=90) == "low"


def test_coverage_grade_does_not_fail_a_target_it_exactly_meets():
    assert coverage_grade(79.99999999999999, target=80) == "strong"


def test_format_lines_collapses_runs():
    assert format_lines([4, 7]) == "4, 7"
    assert format_lines([12, 13, 14, 15, 88]) == "12-15, 88"
    assert format_lines([]) == ""


def test_trim_lines_cuts_at_a_comma_never_mid_range():
    text = format_lines(list(range(1, 40, 2)))
    trimmed = trim_lines(text, 20)

    assert trimmed.endswith(", ...")
    assert len(trimmed) <= 25
    # Nothing left half-written: every kept entry is still a whole number.
    for part in trimmed[:-5].split(", "):
        assert part.replace("-", "").isdigit()


def test_trim_lines_leaves_a_short_list_alone():
    assert trim_lines("4, 7", 90) == "4, 7"


def test_relative_name_strips_the_checkout_directory():
    assert relative_name("/build/proj/src/api.py", "/build/proj") == "src/api.py"


def test_relative_name_leaves_a_relative_path_alone():
    """coverage.py already reports these relative; resolving them against the
    working directory would be inventing a path nobody asked about."""
    assert relative_name("src/api.py", "/build/proj") == "src/api.py"


def test_relative_name_keeps_a_file_outside_the_root():
    assert relative_name("/opt/lib/thing.py", "/build/proj") == "/opt/lib/thing.py"


def test_format_percent_drops_a_trailing_zero():
    assert format_percent(100.0) == "100"
    assert format_percent(62.5) == "62.5"
    assert format_percent(81.249) == "81.2"


def test_ring_dash_is_the_fraction_of_the_real_circumference():
    drawn, total = (float(value) for value in ring_dash(25).split())

    assert round(drawn / total, 4) == 0.25


def test_ring_dash_clamps():
    assert ring_dash(-10).split()[0] == "0.00"
    assert ring_dash(140).split()[0] == ring_dash(100).split()[0]


# --------------------------------------------------------------------------
# summaries
# --------------------------------------------------------------------------

def test_summarize_json_takes_the_total_coverage_py_published():
    """Recomputing it would put the report at odds with the terminal beside it:
    with branch coverage on, percent_covered already folds branches in."""
    summary = summarize_json(JSON_REPORT)

    assert summary["percent"] == 81.25
    assert summary["statements"] == 14
    assert summary["covered"] == 12
    assert summary["missing"] == 2
    assert summary["excluded"] == 1
    assert summary["branch"] is True
    assert summary["branches"] == 2
    assert summary["branches_covered"] == 1
    assert summary["partial"] == 1
    assert summary["generated"].startswith("2026-08-31")


def test_summarize_json_lists_files_worst_first():
    summary = summarize_json(JSON_REPORT)

    assert [entry["name"] for entry in summary["files"]] == ["src/sample.py", "src/clean.py"]
    assert summary["files"][0]["lines"] == "4, 7"
    assert summary["files"][0]["branches_covered"] == 1


def test_summarize_json_works_out_covered_branches_for_an_older_coverage():
    """Releases before covered_branches report the total and the partial count."""
    document = json.loads(json.dumps(JSON_REPORT))
    del document["totals"]["covered_branches"]
    del document["files"]["src/sample.py"]["summary"]["covered_branches"]

    summary = summarize_json(document)

    assert summary["branches_covered"] == 1
    assert summary["files"][0]["branches_covered"] == 1


def test_summarize_json_survives_a_report_with_nothing_in_it():
    summary = summarize_json({})

    assert summary["statements"] == 0
    assert summary["files"] == []
    assert has_data(summary) is False


def test_summarize_xml_matches_the_formula_coverage_py_uses():
    """(lines + branches) covered over (lines + branches) valid, so a report
    read from the xml and one read from the live run agree."""
    summary = summarize_xml(ElementTree.fromstring(XML_REPORT))

    assert summary["percent"] == 62.5
    assert summary["statements"] == 6
    assert summary["covered"] == 4
    assert summary["branch"] is True
    assert summary["branches"] == 2
    assert summary["branches_covered"] == 1


def test_summarize_xml_reads_the_lines_of_each_file():
    entry = summarize_xml(ElementTree.fromstring(XML_REPORT))["files"][0]

    assert entry["name"] == "src/sample.py"
    assert entry["statements"] == 6
    assert entry["missing"] == 2
    assert entry["lines"] == "4, 7"
    assert entry["partial"] == 1


def _file(percent, name):
    return {"name": name, "percent": percent, "statements": 10, "covered": 5,
            "missing": 5, "excluded": 0, "branches": 0, "branches_covered": 0,
            "partial": 0, "lines": ""}


def test_build_summary_keeps_the_least_covered_files_when_it_has_to_cut():
    """A cap that kept the alphabetical head would hide exactly the files the
    tab is opened to find."""
    summary = build_summary(
        files=[_file(90, "a.py"), _file(10, "z.py"), _file(50, "m.py")],
        percent=50, statements=30, covered=15, missing=15, excluded=0,
        branches=0, branches_covered=0, partial=0, branch=False, generated="",
        limit=2)

    assert [entry["name"] for entry in summary["files"]] == ["z.py", "m.py"]
    assert summary["files_total"] == 3


def test_build_summary_lists_everything_when_the_limit_is_zero():
    summary = build_summary(
        files=[_file(90, "a.py"), _file(10, "z.py")],
        percent=50, statements=20, covered=10, missing=10, excluded=0,
        branches=0, branches_covered=0, partial=0, branch=False, generated="",
        limit=0)

    assert len(summary["files"]) == 2


def test_has_data_rejects_a_run_that_measured_nothing():
    """An empty report reads as 100%: coverage.py calls a file with no
    statements fully covered, so an empty one would open a tab announcing a
    perfect score."""
    empty = build_summary(files=[], percent=100, statements=0, covered=0, missing=0,
                          excluded=0, branches=0, branches_covered=0, partial=0,
                          branch=False, generated="", limit=0)

    assert has_data(empty) is False
    assert has_data(None) is False


# --------------------------------------------------------------------------
# deltas
# --------------------------------------------------------------------------

def test_coverage_delta_against_the_previous_build():
    assert coverage_delta([81.25, 80.0, 70.0]) == 1.25


def test_coverage_delta_skips_builds_that_measured_nothing():
    """A build that ran without coverage is not a drop to zero."""
    assert coverage_delta([81.25, None, None, 80.0]) == 1.25


def test_coverage_delta_is_none_on_a_first_build():
    assert coverage_delta([81.25]) is None
    assert coverage_delta([]) is None
    assert coverage_delta([None, 80.0]) is None


# --------------------------------------------------------------------------
# reading from disk
# --------------------------------------------------------------------------

def test_read_coverage_path_sniffs_json(tmpdir):
    path = os.path.join(str(tmpdir), "whatever.dat")
    with open(path, "w") as handle:
        json.dump(JSON_REPORT, handle)

    summary = read_coverage_path(path)

    assert summary["percent"] == 81.25
    assert summary["source"] == "whatever.dat"


def test_read_coverage_path_sniffs_xml(tmpdir):
    """The kind comes off the first byte, not the extension: CI names these
    files whatever the pipeline felt like."""
    path = os.path.join(str(tmpdir), "cobertura.txt")
    with open(path, "w") as handle:
        handle.write(XML_REPORT)

    assert read_coverage_path(path)["percent"] == 62.5


def test_read_coverage_path_returns_none_for_something_that_is_not_coverage(tmpdir):
    path = os.path.join(str(tmpdir), "notes.txt")
    with open(path, "w") as handle:
        handle.write("nothing to see")

    assert read_coverage_path(path) is None


def test_read_coverage_path_returns_none_for_a_file_that_is_not_there(tmpdir):
    assert read_coverage_path(os.path.join(str(tmpdir), "gone.json")) is None


def test_read_coverage_path_returns_none_for_broken_json(tmpdir):
    path = os.path.join(str(tmpdir), "coverage.json")
    with open(path, "w") as handle:
        handle.write('{"totals": ')

    assert read_coverage_path(path) is None


def test_discover_coverage_finds_a_report_beside_the_html(tmpdir):
    with open(os.path.join(str(tmpdir), "coverage.json"), "w") as handle:
        json.dump(JSON_REPORT, handle)

    assert discover_coverage([str(tmpdir)])["percent"] == 81.25


def test_discover_coverage_ignores_a_stale_data_file(tmpdir):
    """Only deliberate report artifacts are picked up without being named. A
    .coverage is often left over from a run days ago, and quietly reporting
    yesterday's number is worse than reporting none."""
    with open(os.path.join(str(tmpdir), ".coverage"), "w") as handle:
        handle.write("SQLite format 3")

    assert discover_coverage([str(tmpdir)]) is None


def test_discover_coverage_returns_none_from_an_empty_folder(tmpdir):
    assert discover_coverage([str(tmpdir)]) is None


# --------------------------------------------------------------------------
# collection
# --------------------------------------------------------------------------

def test_collect_coverage_does_nothing_when_it_is_switched_off(tmpdir):
    with open(os.path.join(str(tmpdir), "coverage.json"), "w") as handle:
        json.dump(JSON_REPORT, handle)

    summary, notice = collect_coverage(_FakeConfig(options={"report_coverage": "none"}),
                                       str(tmpdir))

    assert summary is None
    assert notice == ""


def test_collect_coverage_reads_the_file_it_was_given(tmpdir):
    path = os.path.join(str(tmpdir), "given.json")
    with open(path, "w") as handle:
        json.dump(JSON_REPORT, handle)

    summary, notice = collect_coverage(_FakeConfig(options={"report_coverage_file": path}),
                                       str(tmpdir))

    assert summary["percent"] == 81.25
    assert notice == ""


def test_collect_coverage_says_so_when_the_named_file_is_not_coverage(tmpdir):
    """Reported into the page rather than raised: the tests are over by the
    time this runs, and a UsageError would turn a green run red over a
    decoration. The tab is where somebody is looking for the missing numbers."""
    path = os.path.join(str(tmpdir), "notes.txt")
    with open(path, "w") as handle:
        handle.write("nothing to see")

    summary, notice = collect_coverage(_FakeConfig(options={"report_coverage_file": path}),
                                       str(tmpdir))

    assert summary is None
    assert "could be read as coverage data" in notice
    assert path in notice


def test_collect_coverage_finds_nothing_without_complaining(tmpdir):
    summary, notice = collect_coverage(_FakeConfig(), str(tmpdir))

    assert summary is None
    assert notice == ""


def test_measured_nothing_notice_names_the_flag_that_was_typed():
    from pytest_html_reporter.coverage_report import measured_nothing_notice

    class _Cov:
        class config:
            source = ["src", "lib"]

    notice = measured_nothing_notice(_Cov())

    assert "--cov=src --cov=lib" in notice
    assert "measured nothing" in notice


def test_measured_nothing_notice_without_a_named_source():
    from pytest_html_reporter.coverage_report import measured_nothing_notice

    class _Cov:
        class config:
            source = None

    assert "pytest-cov ran but measured nothing." in measured_nothing_notice(_Cov())


# --------------------------------------------------------------------------
# a real run
#
# The live pytest-cov path is the one worth running for real: it depends on
# when pytest-cov finishes and saves its data relative to when this report is
# written, and no amount of shaping a dict in memory says anything about that.
# --------------------------------------------------------------------------

SAMPLE = {
    "src/__init__.py": "",
    "src/calc.py": """
        def add(a, b):
            if a > b:
                return a + b
            return b - a


        def never_called():
            return 1
    """,
    "test_calc.py": """
        from src.calc import add


        def test_add():
            assert add(3, 1) == 4
    """,
}


def _run(tmp_path, *args):
    """A real pytest run in its own process, returning its output.json.

    A subprocess rather than an inline run: coverage measures a process, and
    measuring the one that is already running these tests would report on this
    suite instead of on the sample.
    """
    for name, body in SAMPLE.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(textwrap.dedent(body).lstrip())

    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--html-report=./report", "-p", "no:cacheprovider"]
        + list(args),
        cwd=str(tmp_path),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )

    report = tmp_path / "report" / "output.json"
    assert report.is_file(), result.stdout

    return json.loads(report.read_text()), result.stdout


def _page(tmp_path):
    return (tmp_path / "report" / "pytest_html_report.html").read_text(encoding="utf-8")


def test_a_run_with_pytest_cov_reports_the_total_the_terminal_printed(tmp_path):
    """The one number that must never drift. A report generated beside a
    terminal that says 74% and showing 63% is a bug report waiting to be
    filed, so the figure is coverage.py's own rather than one recomputed here.
    """
    pytest.importorskip("pytest_cov")

    data, output = _run(tmp_path, "--cov=src", "--cov-report=term")

    printed = re.search(r"^TOTAL\s+\d+\s+\d+\s+(\d+)%", output, re.M)
    assert printed, output

    assert round(data["coverage"]["percent"]) == int(printed.group(1))


def test_a_run_with_pytest_cov_fills_in_the_coverage_tab(tmp_path):
    pytest.importorskip("pytest_cov")

    _run(tmp_path, "--cov=src")
    page = _page(tmp_path)

    assert 'cov-page has-coverage' in page
    assert re.search(r'class="cov-ring__value"[^>]*stroke-dasharray="[\d.]+ [\d.]+"', page)
    assert "Measured by pytest-cov during this run" in page
    # A row per measured file, and the chip that crosses to them.
    assert page.count('<td class="th-left suite-cell"') == 2
    assert "cov-trigger" in page


def test_branch_coverage_is_reported_only_when_it_was_measured(tmp_path):
    """A Branches column of dashes says nothing except that --cov-branch was
    not passed, so the column is dropped rather than filled with zeroes."""
    pytest.importorskip("pytest_cov")

    _run(tmp_path, "--cov=src")
    assert "var coverageHasBranches = false;" in _page(tmp_path)

    _run(tmp_path, "--cov=src", "--cov-branch")
    assert "var coverageHasBranches = true;" in _page(tmp_path)


def test_a_parallel_run_reports_the_combined_coverage(tmp_path):
    """Every xdist worker measures its own slice; pytest-cov combines them on
    the controller long before the report is written."""
    pytest.importorskip("pytest_cov")
    pytest.importorskip("xdist")

    serial, _ = _run(tmp_path, "--cov=src")
    parallel, _ = _run(tmp_path, "--cov=src", "-n", "2")

    assert parallel["coverage"]["percent"] == serial["coverage"]["percent"]


def test_a_second_build_shows_what_moved(tmp_path):
    pytest.importorskip("pytest_cov")

    _run(tmp_path, "--cov=src")

    (tmp_path / "test_more.py").write_text(textwrap.dedent("""
        from src.calc import never_called


        def test_never_called():
            assert never_called() == 1
    """).lstrip())

    _run(tmp_path, "--cov=src")
    page = _page(tmp_path)

    assert re.search(r'class="cov-delta is-up">\+[\d.]+ since the last build<', page)
    assert "cov-page has-coverage has-trend" in page


def test_a_run_without_coverage_says_how_to_get_it(tmp_path):
    data, _ = _run(tmp_path)
    page = _page(tmp_path)

    assert "coverage" not in data
    assert "cov-page is-empty" in page
    assert "No coverage in this run" in page
    # The empty tab is the only moment anyone reads setup instructions.
    assert "pip install pytest-cov" in page


def test_a_run_that_measured_nothing_says_so(tmp_path):
    """--cov=src against a project with no src is the easiest mistake to make,
    and the generic setup guide is the least useful answer to it: it tells
    somebody to install pytest-cov and pass --cov when they have just done
    both."""
    pytest.importorskip("pytest_cov")

    _run(tmp_path, "--cov=nosuchpackage")
    page = _page(tmp_path)

    assert "cov-page is-empty" in page
    assert "pytest-cov ran but measured nothing" in page
    assert "--cov=nosuchpackage" in page


def test_a_run_with_no_coverage_at_all_gets_no_such_notice(tmp_path):
    """Nothing measured it, so there is nothing to explain - just the guide."""
    _run(tmp_path)
    page = _page(tmp_path)

    assert 'class="cov-notice"></div>' in page


def test_report_coverage_none_leaves_the_tab_empty(tmp_path):
    pytest.importorskip("pytest_cov")

    data, _ = _run(tmp_path, "--cov=src", "--report-coverage=none")

    assert "coverage" not in data
    assert "cov-page is-empty" in _page(tmp_path)


def test_report_link_adds_side_nav_entries(tmp_path):
    """Issue #203's other half: reach your own pages from the report."""
    _run(tmp_path, "--report-link", "Coverage=htmlcov/index.html",
         "--report-link", "CI=https://ci.example.com/job/42")
    page = _page(tmp_path)

    assert '<a class="tablink tablink--out" href="htmlcov/index.html"' in page
    assert '<a class="tablink tablink--out" href="https://ci.example.com/job/42"' in page


def test_report_link_drops_a_scheme_it_does_not_know(tmp_path):
    """The nav is assembled out of whatever a command line said, and the report
    is a build artifact that gets published and passed round."""
    _run(tmp_path, "--report-link", "Bad=javascript:alert(1)")
    page = _page(tmp_path)

    assert 'tablink--out' not in page
    assert 'href="javascript' not in page
    # It is still echoed, escaped, in the Environment panel's record of the
    # command line - which is text about the run, not a link out of the page.
    assert "javascript:alert(1)" in page
