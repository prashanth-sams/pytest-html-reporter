"""Cover the merging leg: one shard that also folds in the ones beside it.

This is the sequential flow - four legs pointed at one --html-report, the last
of them carrying --report-shard-merge so that three commands do the work of
four. It is the path where a mistake is least visible, because the folder it
reads is *persistent*: it holds this run's bundles and whatever the last run
left behind, and the two look identical on disk.

So the interesting cases are not "does it merge" but "what does it refuse to
merge, and does it say so". A leg from yesterday folded in silently is two
extra tests in the totals with nothing on the page admitting it, and a build
that says six when four ran is worse than no build at all.
"""

import os

import pytest

from pytest_html_reporter import merge
from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.html_reporter import HTMLReporter
from pytest_html_reporter.shards import (
    SHARD_SCHEMA,
    SHARD_VERSION,
    shards_root,
    write_bundle,
)


class _FakePluginManager:
    def hasplugin(self, name):
        return False

    def list_plugin_distinfo(self):
        return []


class _FakeConfig:
    def __init__(self, options=None, rootpath=""):
        self.pluginmanager = _FakePluginManager()
        self._options = options or {}
        self.rootpath = rootpath

    def getoption(self, name, default=None):
        return self._options.get(name, default)

    def getini(self, name):
        raise ValueError(name)


def _record(nodeid, status="PASS"):
    suite, _, name = nodeid.partition("::")
    return {"nodeid": nodeid, "suite_name": suite, "test_name": name,
            "status": status, "message": "", "duration": 0.01, "rerun": 0,
            "index": 0, "worker": "", "screenshots": [], "logs": [],
            "attachments": [], "steps": [], "phases": {"call": 10}}


def _bundle_payload(shard_id, nodeids, token="", session_end=1725200000.0):
    return {
        "schema": SHARD_SCHEMA,
        "version": SHARD_VERSION,
        "generator": "pytest-html-reporter test",
        "shard": {"id": shard_id, "label": shard_id, "assets": "pytest_screenshots"},
        "run": {
            "session_start": 1725100000.0, "session_end": session_end,
            "exitstatus": 0, "token": token, "collected": len(nodeids),
            "hostname": "runner-" + shard_id, "platform": "Linux 6.1",
            "python": "3.12.0", "pytest": "8.0.0", "plugins": [],
            "arguments": "-q", "rootdir": "/src", "environment": "staging",
            "build_info": [], "capture_row": "enabled", "capture_notice": "",
            "xdist_workers": [],
        },
        "coverage": None,
        "counts": {"records": len(nodeids), "collect": 0},
        "records": [_record(nodeid) for nodeid in nodeids],
    }


def _write(base, shard_id, nodeids, token="", session_end=1725200000.0):
    return write_bundle(os.path.join(shards_root(base), shard_id),
                        _bundle_payload(shard_id, nodeids, token, session_end))


def _reporter(tmp_path, **options):
    """A leg that has already run and is about to merge the ones beside it."""
    base = str(tmp_path)
    reporter = HTMLReporter(base, "", _FakeConfig(options, base))
    reporter._records = []
    reporter._sessionstarttime = 1725200000.0
    reporter._collected = []
    return reporter


@pytest.fixture(autouse=True)
def _isolate():
    saved = {name: getattr(ConfigVars, name, None)
             for name in ("_start_execution_time", "_environment",
                          "_environment_rows", "_logs_notice")}
    yield
    for name, value in saved.items():
        setattr(ConfigVars, name, value)


# --------------------------------------------------------------- merging ---

def test_every_bundle_beside_the_leg_is_folded_in(tmp_path):
    _write(str(tmp_path), "gw0", ["tests/test_a.py::test_one"])
    _write(str(tmp_path), "gw1", ["tests/test_b.py::test_two"])

    result = merge.merge_into(_reporter(tmp_path))

    assert result is not None
    assert sorted(r["nodeid"] for r in result.records) == \
        ["tests/test_a.py::test_one", "tests/test_b.py::test_two"]


def test_the_legs_own_records_are_replaced_rather_than_added_to(tmp_path):
    """This leg has already written its own bundle, so the folder is the whole
    run - adding to _records would count this leg's tests twice."""
    _write(str(tmp_path), "gw0", ["tests/test_a.py::test_one"])

    reporter = _reporter(tmp_path)
    reporter._records = [_record("tests/test_a.py::test_one")]

    merge.merge_into(reporter)

    assert len(reporter._records) == 1


def test_the_reporter_is_handed_the_matrixs_clock(tmp_path):
    _write(str(tmp_path), "gw0", ["tests/test_a.py::test_one"])

    reporter = _reporter(tmp_path)
    merge.merge_into(reporter)

    assert reporter._sessionstarttime == 1725100000.0
    assert ConfigVars._start_execution_time == 1725100000.0


def test_the_environment_panel_is_filled_from_the_shards(tmp_path):
    """The panel on a merged report used to describe the merging machine,
    which ran no tests at all."""
    _write(str(tmp_path), "gw0", ["tests/test_a.py::test_one"])
    _write(str(tmp_path), "gw1", ["tests/test_b.py::test_two"])

    reporter = _reporter(tmp_path)
    merge.merge_into(reporter)

    rows = reporter.environment_source()
    assert "runner-gw0" in rows
    assert "runner-gw1" in rows
    assert "2 shards" in rows


def test_the_junit_options_describe_the_matrix_not_this_leg(tmp_path):
    """So --report-junit on this leg writes the document the merge command
    would have written from the same bundles."""
    _write(str(tmp_path), "gw0", ["tests/test_a.py::test_one"])

    reporter = _reporter(tmp_path)
    merge.merge_into(reporter)

    assert reporter.junit_options is not None


def test_a_folder_with_no_bundles_merges_nothing(tmp_path):
    assert merge.merge_into(_reporter(tmp_path)) is None


def test_every_merged_bundle_is_named_on_stderr(tmp_path, capsys):
    """Said out loud on every merge, not only when something looks wrong: this
    is the only place the build's provenance is ever recorded."""
    _write(str(tmp_path), "gw0", ["tests/test_a.py::test_one"])

    merge.merge_into(_reporter(tmp_path))

    error = capsys.readouterr().err
    assert "merged shard gw0" in error
    assert "1 test" in error


# ------------------------------------------------- bundles from another run ---

def test_a_leg_with_a_token_merges_only_this_runs_bundles(tmp_path):
    """The folder is persistent, so a leg renamed or dropped since the last run
    leaves a bundle the next --report-shard-merge would report as part of this
    build - six tests when four ran."""
    _write(str(tmp_path), "gw0", ["tests/test_a.py::test_one"], token="run-7")
    _write(str(tmp_path), "old", ["tests/test_old.py::test_gone"], token="run-6")

    reporter = _reporter(tmp_path, report_shard_run="run-7")
    result = merge.merge_into(reporter)

    assert [r["nodeid"] for r in result.records] == ["tests/test_a.py::test_one"]


def test_the_bundles_left_behind_are_named_rather_than_dropped_in_silence(
        tmp_path, capsys):
    _write(str(tmp_path), "gw0", ["tests/test_a.py::test_one"], token="run-7")
    _write(str(tmp_path), "old", ["tests/test_old.py::test_gone"], token="run-6")

    merge.merge_into(_reporter(tmp_path, report_shard_run="run-7"))

    error = capsys.readouterr().err
    assert "came from another run" in error
    assert "old" in error
    assert "--report-shard-reset" in error


def test_a_bundle_with_no_token_is_put_aside_by_a_leg_that_has_one(tmp_path, capsys):
    _write(str(tmp_path), "gw0", ["tests/test_a.py::test_one"], token="run-7")
    _write(str(tmp_path), "hand", ["tests/test_x.py::test_hand"])

    result = merge.merge_into(_reporter(tmp_path, report_shard_run="run-7"))

    assert len(result.records) == 1
    assert "no run token" in capsys.readouterr().err


def test_a_folder_holding_only_another_runs_bundles_merges_nothing(tmp_path):
    _write(str(tmp_path), "old", ["tests/test_old.py::test_gone"], token="run-6")

    assert merge.merge_into(_reporter(tmp_path, report_shard_run="run-7")) is None


def test_a_leg_without_a_token_merges_everything_as_it_always_has(tmp_path):
    """The behaviour before tokens existed, and still the default."""
    _write(str(tmp_path), "gw0", ["tests/test_a.py::test_one"], token="run-7")
    _write(str(tmp_path), "old", ["tests/test_old.py::test_gone"], token="run-6")

    result = merge.merge_into(_reporter(tmp_path))

    assert len(result.records) == 2


def test_one_bundle_left_behind_is_reported_in_the_singular(tmp_path, capsys):
    _write(str(tmp_path), "gw0", ["tests/test_a.py::test_one"], token="run-7")
    _write(str(tmp_path), "old", ["tests/test_old.py::test_gone"], token="run-6")

    merge.merge_into(_reporter(tmp_path, report_shard_run="run-7"))

    error = capsys.readouterr().err
    assert "1 bundle under" in error
    assert "was not merged" in error


# --------------------------------------------------------- unreadable files ---

def test_a_file_that_is_not_a_bundle_does_not_stop_the_merge(tmp_path):
    _write(str(tmp_path), "gw0", ["tests/test_a.py::test_one"])
    stray = os.path.join(shards_root(str(tmp_path)), "gw1")
    os.makedirs(stray, exist_ok=True)
    with open(os.path.join(stray, "records.json"), "w") as handle:
        handle.write("not json at all")

    result = merge.merge_into(_reporter(tmp_path))

    assert len(result.records) == 1


def test_a_folder_of_only_unreadable_files_says_why_it_merged_nothing(
        tmp_path, capsys):
    stray = os.path.join(shards_root(str(tmp_path)), "gw0")
    os.makedirs(stray, exist_ok=True)
    with open(os.path.join(stray, "records.json"), "w") as handle:
        handle.write("not json at all")

    assert merge.merge_into(_reporter(tmp_path)) is None
    assert "could not be read as json" in capsys.readouterr().err
