"""Cover the three merge subcommands, including what they refuse.

``merge`` writes a report, ``junit`` writes only the xml for a pipeline that
publishes into GitLab or Azure and keeps no HTML, and ``inspect`` writes
nothing at all - it answers "what would this merge come to, and do these
bundles overlap", which is the question asked by hand when the totals on a
merged report were not the totals somebody expected.

Only the commands that render nothing are called in this process. A full merge
render calls reset_config_vars() and builds a whole report out of the same
class-level state this very suite is being reported through, so running one
here would leave the host session rendering a build assembled from these
tests - and it writes an output.json and rotates an archive besides. Those go
through a subprocess, which is what the merge does in real life anyway.
"""

import json
import os
import subprocess
import sys

import pytest

from pytest_html_reporter.cli import main
from pytest_html_reporter.shards import SHARD_SCHEMA, SHARD_VERSION, write_bundle


def _record(nodeid, status="PASS", collect=False):
    suite, _, name = nodeid.partition("::")
    record = {"nodeid": nodeid, "suite_name": suite, "test_name": name,
              "status": status, "message": "", "duration": 0.01, "rerun": 0,
              "index": 0, "worker": "", "screenshots": [], "logs": [],
              "attachments": [], "steps": [], "phases": {"call": 10}}
    if collect:
        record["collect"] = True
    return record


def _write(root, shard_id, records):
    payload = {
        "schema": SHARD_SCHEMA,
        "version": SHARD_VERSION,
        "generator": "pytest-html-reporter test",
        "shard": {"id": shard_id, "label": shard_id, "assets": "pytest_screenshots"},
        "run": {
            "session_start": 1725100000.0, "session_end": 1725200000.0,
            "exitstatus": 0, "token": "", "collected": len(records),
            "hostname": "runner-" + shard_id, "platform": "Linux 6.1",
            "python": "3.12.0", "pytest": "8.0.0", "plugins": [],
            "arguments": "-q", "rootdir": "/src", "environment": "staging",
            "build_info": [], "capture_row": "enabled", "capture_notice": "",
            "xdist_workers": [],
        },
        "coverage": None,
        "counts": {"records": len(records), "collect": 0},
        "records": records,
    }
    return write_bundle(os.path.join(str(root), shard_id), payload)


def _cli(tmp_path, *args):
    """Run the command in its own process, cwd'd well away from this checkout."""
    workspace = tmp_path / "cwd"
    workspace.mkdir(exist_ok=True)

    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)

    return subprocess.run(
        [sys.executable, "-m", "pytest_html_reporter"] + [str(a) for a in args],
        cwd=str(workspace), env=env, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, universal_newlines=True)


@pytest.fixture
def bundles(tmp_path):
    source = tmp_path / "artifacts"
    _write(source, "gw0", [_record("tests/test_a.py::test_one")])
    _write(source, "gw1", [_record("tests/test_b.py::test_two", status="FAIL")])
    return source


# ------------------------------------------------- merge (its own process) ---

def test_a_merge_writes_the_report_it_was_asked_for(tmp_path, bundles):
    out = tmp_path / "report"

    result = _cli(tmp_path, "merge", bundles, "--html-report", out)

    assert result.returncode == 0, result.stderr
    assert (out / "pytest_html_report.html").is_file()


def test_a_merged_build_records_a_status_its_own_archive_loader_can_read(
        tmp_path, bundles):
    """output.json is read back by the next build's archive rail, which does
    data['status'] with no guard - a merged build that wrote none would take
    the following run's whole report down."""
    out = tmp_path / "report"
    _cli(tmp_path, "merge", bundles, "--html-report", out)

    document = json.loads((out / "output.json").read_text())

    assert "status" in document
    assert "status_list" in document


def test_a_merge_can_be_asked_to_fail_on_a_failing_run(tmp_path, bundles):
    """--exit-code is what lets a merge stand in for the run in CI."""
    result = _cli(tmp_path, "merge", bundles, "--html-report",
                  tmp_path / "out", "--exit-code")

    assert result.returncode != 0


def test_a_merge_of_a_passing_run_exits_zero_even_with_exit_code(tmp_path):
    source = tmp_path / "artifacts"
    _write(source, "gw0", [_record("tests/test_a.py::test_one")])

    result = _cli(tmp_path, "merge", source, "--html-report",
                  tmp_path / "out", "--exit-code")

    assert result.returncode == 0, result.stderr


def test_a_report_path_that_cannot_be_written_is_refused_before_the_merge(
        tmp_path, bundles):
    occupied = tmp_path / "report"
    occupied.write_text("not a folder")

    result = _cli(tmp_path, "merge", bundles, "--html-report", occupied)

    assert result.returncode != 0
    assert "not a folder" in result.stderr


# -------------------------------------------- the commands that render none ---

def test_a_merge_that_found_no_bundles_names_where_it_looked(tmp_path, capsys):
    """The usual cause is a CI step that unpacked the artifacts one directory
    deeper than the merge was told."""
    empty = tmp_path / "empty"
    empty.mkdir()

    assert main(["merge", str(empty), "--html-report",
                 str(tmp_path / "out"), "--dry-run"]) != 0
    assert str(empty) in capsys.readouterr().err


def test_a_dry_run_writes_nothing_but_still_reports(tmp_path, bundles, capsys):
    out = tmp_path / "report"

    assert main(["merge", str(bundles), "--html-report", str(out),
                 "--dry-run"]) == 0
    assert not out.exists()
    assert "2" in capsys.readouterr().out


def test_quiet_silences_the_notes(tmp_path, capsys):
    """-q asks for a quiet terminal, not for a merge that stops noticing
    things: the warnings are still collected and --strict still reads them."""
    source = tmp_path / "artifacts"
    _write(source, "gw0", [_record("tests/test_a.py::test_one")])
    stray = source / "gw1"
    stray.mkdir(parents=True)
    (stray / "records.json").write_text("not json at all")

    main(["inspect", str(source)])
    assert "could not be read as json" in capsys.readouterr().err

    main(["inspect", str(source), "-q"])
    assert "could not be read as json" not in capsys.readouterr().err


def test_the_summary_counts_collection_records_when_there_are_some(
        tmp_path, capsys):
    source = tmp_path / "artifacts"
    _write(source, "gw0", [_record("tests/test_a.py::test_one"),
                           _record("tests/test_broken.py", collect=True)])

    main(["merge", str(source), "--html-report", str(tmp_path / "out"),
          "--dry-run"])

    assert "1 collection record" in capsys.readouterr().out


def test_several_collection_records_are_counted_in_the_plural(tmp_path, capsys):
    source = tmp_path / "artifacts"
    _write(source, "gw0", [_record("tests/test_x.py", collect=True),
                           _record("tests/test_y.py", collect=True)])

    main(["merge", str(source), "--html-report", str(tmp_path / "out"),
          "--dry-run"])

    assert "2 collection records" in capsys.readouterr().out


# ---------------------------------------------------------------- junit ---

def test_the_junit_command_writes_only_the_xml(tmp_path, bundles):
    """A pipeline that publishes into GitLab or Azure and keeps no HTML at all
    should not have to write a build it will throw away."""
    out = tmp_path / "results.xml"

    assert main(["junit", str(bundles), "--output", str(out)]) == 0
    assert out.is_file()
    assert "test_one" in out.read_text()
    assert not (tmp_path / "pytest_html_report.html").exists()


def test_the_junit_command_fails_when_there_is_nothing_to_write(tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()

    assert main(["junit", str(empty), "--output", str(tmp_path / "out.xml")]) != 0
    assert capsys.readouterr().err


def test_a_junit_dry_run_writes_no_document(tmp_path, bundles):
    out = tmp_path / "results.xml"

    assert main(["junit", str(bundles), "--output", str(out), "--dry-run"]) == 0
    assert not out.exists()


# -------------------------------------------------------------- inspect ---

def test_inspect_lists_the_bundles_and_writes_nothing(tmp_path, bundles, capsys):
    assert main(["inspect", str(bundles)]) == 0

    out = capsys.readouterr().out
    assert "gw0" in out
    assert "gw1" in out
    assert not (tmp_path / "pytest_html_report.html").exists()


def test_inspect_can_answer_as_json(tmp_path, bundles, capsys):
    """The notes go to stderr precisely so this stays a document."""
    assert main(["inspect", str(bundles), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload


def test_inspect_fails_when_there_are_no_bundles(tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()

    assert main(["inspect", str(empty)]) != 0
    assert capsys.readouterr().err
