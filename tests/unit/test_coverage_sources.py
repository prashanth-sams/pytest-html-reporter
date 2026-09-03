"""Cover where the Coverage tab's numbers come from, and what it does without any.

There are four sources and they are tried in a fixed order - the file somebody
named, the live pytest-cov session, a report discovered on disk, nothing - and
the order is the whole design: a named file is an instruction, a live session
is this run's own truth, and a file lying about on disk is a guess worth making
only once the other two have come back empty.

Every one of them is read behind a guard, for a reason worth restating: this
runs from pytest_terminal_summary, after the tests are over. A raise here turns
a green run red over a decoration, so a source that cannot be read has to
become a sentence in the tab rather than a traceback in the terminal.
"""

import json
import os
import subprocess
import sys

import pytest

from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.coverage_report import (
    annotated_html,
    collect_coverage,
    generate_coverage_view,
    json_from_coverage,
    live_coverage,
    read_coverage_path,
    summarize_data_file,
)


JSON_REPORT = {
    "totals": {"num_statements": 100, "covered_lines": 90, "missing_lines": 10,
               "excluded_lines": 0, "num_branches": 0, "num_partial_branches": 0,
               "percent_covered": 90.0},
    "files": {"app/a.py": {"summary": {"num_statements": 100, "covered_lines": 90,
                                       "missing_lines": 10, "excluded_lines": 0,
                                       "num_branches": 0, "num_partial_branches": 0,
                                       "percent_covered": 90.0},
                           "missing_lines": [1, 2]}},
}


class _CovConfig:
    def __init__(self, html_dir=""):
        self.html_dir = html_dir


class _Cov:
    """A coverage.Coverage, as much of one as this module ever asks for."""

    def __init__(self, document=JSON_REPORT, html_dir="", raises=False):
        self._document = document
        self._raises = raises
        self.config = _CovConfig(html_dir)

    def json_report(self, outfile=None):
        if self._raises:
            raise Exception("No data to report.")
        with open(outfile, "w", encoding="utf-8") as handle:
            json.dump(self._document, handle)


class _Controller:
    def __init__(self, cov):
        self.cov = cov


class _PluginManager:
    def __init__(self, plugin=None, raises=False):
        self._plugin = plugin
        self._raises = raises

    def hasplugin(self, name):
        if self._raises:
            raise RuntimeError("plugin manager is gone")
        return self._plugin is not None and name == "_cov"

    def getplugin(self, name):
        return self._plugin


class _CovPlugin:
    def __init__(self, controller):
        self.cov_controller = controller


class _Config:
    def __init__(self, options=None, manager=None, rootpath=""):
        self._options = options or {}
        self.rootpath = rootpath
        if manager is not None:
            self.pluginmanager = manager

    def getoption(self, name, default=None):
        return self._options.get(name, default)

    def getini(self, name):
        raise ValueError(name)


def _config_with_cov(cov, **options):
    manager = _PluginManager(_CovPlugin(_Controller(cov)))
    return _Config(options, manager)


_TOUCHED = tuple(name for name in vars(ConfigVars) if name.startswith("_coverage")) + \
    ("tcoverage",)


@pytest.fixture(autouse=True)
def _isolate():
    saved = {name: getattr(ConfigVars, name, None) for name in _TOUCHED}
    yield
    for name, value in saved.items():
        setattr(ConfigVars, name, value)


# ----------------------------------------------------------- live_coverage ---

def test_the_running_pytest_cov_session_is_found():
    """Read rather than raced for: pytest-cov has stopped and combined its
    data - every xdist worker's share included - long before this runs."""
    cov = _Cov()

    assert live_coverage(_config_with_cov(cov)) is cov


def test_a_run_without_pytest_cov_has_no_live_session():
    assert live_coverage(_Config(manager=_PluginManager())) is None


def test_a_config_with_no_plugin_manager_at_all_has_no_session():
    assert live_coverage(_Config()) is None


def test_a_plugin_manager_that_raises_costs_the_tab_and_nothing_else():
    assert live_coverage(_Config(manager=_PluginManager(raises=True))) is None


def test_a_cov_plugin_with_no_controller_yet_has_no_session():
    manager = _PluginManager(_CovPlugin(None))

    assert live_coverage(_Config(manager=manager)) is None


# ------------------------------------------------------ json_from_coverage ---

def test_coverage_pys_own_json_is_read_back():
    assert json_from_coverage(_Cov())["totals"]["num_statements"] == 100


def test_a_session_with_no_data_to_report_is_not_a_failure():
    """'No data to report', a coverage too old to write json, an unreadable
    data file - none of it is worth failing a finished test run over."""
    assert json_from_coverage(_Cov(raises=True)) is None


def test_the_temporary_file_is_not_left_behind(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))

    json_from_coverage(_Cov())

    assert list(tmp_path.iterdir()) == []


def test_the_temporary_file_is_cleaned_up_even_when_the_report_raises(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))

    json_from_coverage(_Cov(raises=True))

    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------- annotated_html ---

def test_a_run_that_wrote_no_html_report_offers_no_link():
    assert annotated_html(_Cov(), ".") == ""


def test_the_link_is_relative_so_the_two_travel_together(tmp_path):
    """It keeps this report one file, and a relative link survives the folder
    being moved or published somewhere else."""
    htmlcov = tmp_path / "htmlcov"
    htmlcov.mkdir()
    (htmlcov / "index.html").write_text("<html/>")

    link = annotated_html(_Cov(html_dir=str(htmlcov)), str(tmp_path))

    assert link == "htmlcov/index.html"


def test_a_named_folder_that_was_never_written_offers_no_link(tmp_path):
    assert annotated_html(_Cov(html_dir=str(tmp_path / "htmlcov")), str(tmp_path)) == ""


def test_an_htmlcov_left_over_from_last_week_is_not_linked(tmp_path):
    """coverage.py names the folder whether or not --cov-report=html was asked
    for, and annotations disagreeing with the summary beside them are worse
    than no link at all."""
    htmlcov = tmp_path / "htmlcov"
    htmlcov.mkdir()
    index = htmlcov / "index.html"
    index.write_text("<html/>")
    os.utime(str(index), (1000, 1000))

    assert annotated_html(_Cov(html_dir=str(htmlcov)), str(tmp_path), since=2000) == ""


def test_an_htmlcov_written_by_this_run_is_linked(tmp_path):
    htmlcov = tmp_path / "htmlcov"
    htmlcov.mkdir()
    (htmlcov / "index.html").write_text("<html/>")

    assert annotated_html(_Cov(html_dir=str(htmlcov)), str(tmp_path), since=1000) \
        == "htmlcov/index.html"


# ------------------------------------------------------ summarize_data_file ---

def test_a_coverage_data_file_is_summarised(tmp_path):
    """The .coverage sqlite file, read through coverage.py itself - the shape
    --coverage-data hands the merge for every shard of a matrix."""
    pytest.importorskip("coverage")

    (tmp_path / "measured.py").write_text("def add(a, b):\n    return a + b\n")
    (tmp_path / "run.py").write_text("import measured\nmeasured.add(1, 2)\n")

    subprocess.run([sys.executable, "-m", "coverage", "run",
                    "--source=measured", "run.py"],
                   cwd=str(tmp_path), check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    summary = summarize_data_file(str(tmp_path / ".coverage"), str(tmp_path))

    assert summary is not None
    assert summary["statements"] > 0
    assert summary["percent"] == 100.0


def test_a_data_file_that_is_not_one_is_not_a_summary(tmp_path):
    pytest.importorskip("coverage")
    broken = tmp_path / ".coverage"
    broken.write_text("not a sqlite database")

    with pytest.raises(Exception):
        summarize_data_file(str(broken))


# ------------------------------------------------------- read_coverage_path ---

def test_a_path_that_cannot_be_read_at_all_is_not_coverage(tmp_path):
    """Guarded as a whole: read_coverage_path is handed whatever somebody
    typed after --report-coverage-file."""
    assert read_coverage_path(str(tmp_path)) is None


def test_a_coverage_json_names_itself_as_the_source(tmp_path):
    report = tmp_path / "coverage.json"
    report.write_text(json.dumps(JSON_REPORT))

    summary = read_coverage_path(str(report))

    assert summary["source"] == "coverage.json"
    assert summary["source_path"] == str(report)


# ---------------------------------------------------------- collect_coverage ---

def test_the_live_session_is_used_when_nothing_was_named(tmp_path):
    summary, notice = collect_coverage(_config_with_cov(_Cov()), str(tmp_path))

    assert summary["source"] == "pytest-cov"
    assert notice == ""


def test_a_named_file_beats_the_live_session(tmp_path):
    """The flag is an instruction; the session is only what this run happened
    to measure."""
    report = tmp_path / "named.json"
    named = dict(JSON_REPORT)
    named["totals"] = dict(JSON_REPORT["totals"], num_statements=42)
    report.write_text(json.dumps(named))

    config = _config_with_cov(_Cov(), report_coverage_file=str(report))
    summary, _ = collect_coverage(config, str(tmp_path))

    assert summary["statements"] == 42


def test_a_live_session_that_measured_nothing_says_why(tmp_path):
    """Almost always --cov names something that is never imported, and telling
    somebody to install pytest-cov when they just did is the least useful
    thing this page could do."""
    empty = {"totals": {"num_statements": 0, "covered_lines": 0, "missing_lines": 0,
                        "excluded_lines": 0, "num_branches": 0,
                        "num_partial_branches": 0}, "files": {}}

    summary, notice = collect_coverage(
        _config_with_cov(_Cov(document=empty)), str(tmp_path))

    assert summary is None
    assert notice


def test_a_run_with_no_coverage_anywhere_says_nothing_at_all(tmp_path):
    """Not every suite measures coverage, and a notice on every one of them
    would be noise."""
    config = _Config(manager=_PluginManager(), rootpath=str(tmp_path))

    assert collect_coverage(config, str(tmp_path)) == (None, "")


# ------------------------------------------------- generate_coverage_view ---

def _summary(percent=90.0, **overrides):
    summary = {"files": [], "files_total": 1, "percent": percent,
               "statements": 100, "covered": 90, "missing": 10, "excluded": 0,
               "branches": 0, "branches_covered": 0, "partial": 0,
               "branch": False, "generated": "", "source": "pytest-cov",
               "html": ""}
    summary.update(overrides)
    return summary


def test_a_run_with_no_coverage_leaves_the_tab_empty():
    ConfigVars._coverage = None

    generate_coverage_view(_Config())

    assert ConfigVars._coverage_state == "is-empty"
    assert ConfigVars._coverage_rows == ""


def test_the_ring_and_the_tiles_are_filled_from_the_summary():
    ConfigVars._coverage = _summary()
    ConfigVars.tcoverage = [90.0]

    generate_coverage_view(_Config())

    assert ConfigVars._coverage_state == "has-coverage"
    assert ConfigVars._coverage_display == "90"
    assert ConfigVars._coverage_grade == "strong"
    assert "Statements" in ConfigVars._coverage_tiles


def test_the_projects_own_target_is_shown_beside_the_ring():
    ConfigVars._coverage = _summary(percent=85.0)
    ConfigVars.tcoverage = [85.0]

    generate_coverage_view(_Config({"cov_fail_under": 80}))

    assert ConfigVars._coverage_target == "target 80%"
    assert ConfigVars._coverage_grade == "strong"


def test_a_build_below_its_target_is_graded_low():
    ConfigVars._coverage = _summary(percent=70.0)
    ConfigVars.tcoverage = [70.0]

    generate_coverage_view(_Config({"cov_fail_under": 80}))

    assert ConfigVars._coverage_grade == "low"


def test_a_build_that_moved_up_says_so_and_is_coloured_for_it():
    ConfigVars._coverage = _summary(percent=90.0)
    ConfigVars.tcoverage = [90.0, 88.0]

    generate_coverage_view(_Config())

    assert "since the last build" in ConfigVars._coverage_delta
    assert ConfigVars._coverage_delta_class == "is-up"


def test_a_build_that_moved_down_is_coloured_for_that():
    ConfigVars._coverage = _summary(percent=88.0)
    ConfigVars.tcoverage = [88.0, 90.0]

    generate_coverage_view(_Config())

    assert ConfigVars._coverage_delta_class == "is-down"


def test_a_build_that_held_level_is_neither():
    ConfigVars._coverage = _summary(percent=90.0)
    ConfigVars.tcoverage = [90.0, 90.0]

    generate_coverage_view(_Config())

    assert ConfigVars._coverage_delta_class == "is-level"


def test_a_first_build_has_no_delta_to_show():
    ConfigVars._coverage = _summary()
    ConfigVars.tcoverage = [90.0]

    generate_coverage_view(_Config())

    assert ConfigVars._coverage_delta == ""


def test_branch_coverage_is_announced_only_when_it_was_measured():
    ConfigVars._coverage = _summary(branch=True, branches=20, branches_covered=15)
    ConfigVars.tcoverage = [90.0]

    generate_coverage_view(_Config())

    assert ConfigVars._coverage_branch == "true"
