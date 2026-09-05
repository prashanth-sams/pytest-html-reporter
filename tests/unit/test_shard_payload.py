"""Cover what one leg of a matrix writes down about itself, and the write itself.

Everything in a bundle's ``run`` block exists because the merge runs somewhere
else - often on a machine that ran none of the tests - so anything the merging
process could answer about itself it would answer wrongly. That makes this the
one place those facts can be captured, and a field quietly going missing here
shows up as a merged report describing the wrong machine rather than as
anything failing.

The write is guarded for a different reason: two *different* legs landing on
one directory is silent data loss. sanitise_id folds punctuation, so "1/4" and
"1-4" are one directory, and the second leg replaces the first's records with a
merge that then reports a matrix a quarter smaller.
"""

import json
import os

from pytest_html_reporter.html_reporter import HTMLReporter
from pytest_html_reporter.shards import (
    SHARD_SCHEMA,
    SHARD_VERSION,
    _Fields,
    describe_run,
    read_bundle,
    shard_payload,
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


def _record(nodeid="tests/test_cart.py::test_add", worker="", collect=False):
    record = {"nodeid": nodeid, "suite_name": "tests/test_cart.py",
              "test_name": "test_add", "status": "PASS", "message": "",
              "duration": 0.01, "rerun": 0, "index": 0, "worker": worker,
              "screenshots": [], "logs": [], "attachments": [], "steps": [],
              "phases": {}}
    if collect:
        record["collect"] = True
    return record


def _reporter(tmp_path, records=None, shard_id="gw0", **options):
    reporter = HTMLReporter(str(tmp_path), "", _FakeConfig(options, str(tmp_path)))
    reporter.shard_id = shard_id
    reporter._records = records if records is not None else [_record()]
    reporter._sessionstarttime = 1725200000.0
    reporter._collected = []
    return reporter


# ------------------------------------------------------------- describe_run ---

def test_the_leg_records_the_machine_that_actually_ran_the_tests(tmp_path):
    run = describe_run(_reporter(tmp_path), 0)

    assert run["hostname"]
    assert run["platform"].strip()
    assert run["python"]
    assert run["pytest"]


def test_the_leg_records_its_own_honest_start(tmp_path):
    """Not ConfigVars._start_execution_time - that is reset by every
    pytest_runtest_setup, so by report time it holds the last test's setup."""
    run = describe_run(_reporter(tmp_path), 0)

    assert run["session_start"] == 1725200000.0
    assert run["session_end"] >= run["session_start"]


def test_the_exit_status_is_kept_as_a_number(tmp_path):
    assert describe_run(_reporter(tmp_path), 1)["exitstatus"] == 1
    assert describe_run(_reporter(tmp_path), None)["exitstatus"] == 0


def test_a_leg_that_collected_nothing_explicitly_counts_its_records(tmp_path):
    """_collected is filled by pytest_collection_modifyitems, which never fires
    on an xdist controller - the workers collect - so an `-n 4` leg would write
    0 beside a bundle holding four hundred records."""
    reporter = _reporter(tmp_path, records=[_record("a"), _record("b")])
    reporter._collected = []

    assert describe_run(reporter, 0)["collected"] == 2


def test_a_collection_error_is_not_counted_as_a_collected_test(tmp_path):
    reporter = _reporter(tmp_path, records=[_record("a"), _record("b", collect=True)])

    assert describe_run(reporter, 0)["collected"] == 1


def test_the_xdist_workers_this_leg_used_are_named(tmp_path):
    reporter = _reporter(tmp_path, records=[_record("a", worker="gw0"),
                                            _record("b", worker="gw1"),
                                            _record("c", worker="")])

    assert describe_run(reporter, 0)["xdist_workers"] == ["gw0", "gw1"]


def test_the_leg_records_the_ci_run_it_belonged_to(tmp_path, monkeypatch):
    """The merge very often runs in a job of its own: a merging step asking its
    own environment which CI run this was would answer with the merge job, and
    one running on a laptop would answer with nothing at all."""
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/app")
    monkeypatch.setenv("GITHUB_RUN_ID", "1717")
    monkeypatch.setenv("GITHUB_RUN_NUMBER", "42")

    ci = describe_run(_reporter(tmp_path), 0)["ci"]

    assert ci["system"] == "github"
    assert ci["build"] == "42"
    assert ci["url"].endswith("/actions/runs/1717")


def test_the_leg_records_the_revision_it_ran(tmp_path, monkeypatch):
    # Cleared rather than assumed absent: this suite runs on GitHub Actions,
    # where a pull request sets GITHUB_HEAD_REF and it outranks GITHUB_REF_NAME.
    monkeypatch.delenv("GITHUB_HEAD_REF", raising=False)
    monkeypatch.setenv("GITHUB_REF_NAME", "main")
    monkeypatch.setenv("GITHUB_SHA", "0123456789abcdef0123456789abcdef01234567")

    assert describe_run(_reporter(tmp_path), 0)["git"] == {"branch": "main",
                                                           "commit": "0123456789ab"}


def test_the_leg_keeps_the_kernel_string_beside_the_os_one(tmp_path):
    """A merge reading an old bundle beside a new one has to put the two legs'
    rows side by side without either going blank, so the key every older bundle
    carries is still written."""
    run = describe_run(_reporter(tmp_path), 0)

    assert run["platform"].strip()
    assert run["os"].strip()
    assert run["python_detail"].startswith(run["python"])
    assert run["interpreter"]


def test_a_leg_lists_no_packages_unless_it_was_asked_to(tmp_path):
    assert describe_run(_reporter(tmp_path), 0)["packages"] == []


def test_a_leg_asked_for_packages_carries_them_into_the_merge(tmp_path):
    """Collected on the shard for the same reason as everything else here - the
    merging machine's site-packages is not the one the tests imported from."""
    packages = describe_run(_reporter(tmp_path, report_packages=True), 0)["packages"]

    assert any(name.startswith("pytest==") for name in packages)


def test_build_info_is_written_as_lists_because_json_has_no_tuples(tmp_path):
    """A merge reading them back as lists and comparing against tuples would
    find no build info anywhere."""
    reporter = _reporter(tmp_path, build_info=["branch=main"])

    info = describe_run(reporter, 0)["build_info"]

    assert info == [["branch", "main"]]
    assert all(isinstance(pair, list) for pair in info)


def test_the_capture_row_is_read_off_this_legs_own_config(tmp_path):
    """Under the merge shim getoption('capture') is None, so the '-s suppressed
    stdout' explanation would silently vanish from a merged report."""
    reporter = _reporter(tmp_path, report_logs="all", capture="no")

    run = describe_run(reporter, 0)

    assert "not captured" in run["capture_notice"]


def test_a_leg_that_captured_normally_carries_no_notice(tmp_path):
    reporter = _reporter(tmp_path, report_logs="all", capture="fd")

    assert describe_run(reporter, 0)["capture_notice"] == ""


# ------------------------------------------------------------ shard_payload ---

def test_the_payload_carries_the_schema_the_reader_checks(tmp_path):
    payload = shard_payload(_reporter(tmp_path), 0)

    assert payload["schema"] == SHARD_SCHEMA
    assert payload["version"] == SHARD_VERSION
    assert "pytest-html-reporter" in payload["generator"]


def test_the_payload_names_this_leg(tmp_path):
    payload = shard_payload(_reporter(tmp_path, shard_id="gw0"), 0)

    assert payload["shard"]["id"] == "gw0"
    assert payload["shard"]["label"] == "gw0"


def test_a_leg_given_a_label_keeps_the_one_it_was_given(tmp_path):
    reporter = _reporter(tmp_path, shard_id="1-4", report_shard="1/4")

    assert shard_payload(reporter, 0)["shard"]["label"] == "1/4"


def test_the_counts_tell_records_and_collection_errors_apart(tmp_path):
    reporter = _reporter(tmp_path, records=[_record("a"), _record("b"),
                                            _record("c", collect=True)])

    assert shard_payload(reporter, 0)["counts"] == {"records": 2, "collect": 1}


def test_the_records_are_handed_over_verbatim(tmp_path):
    """Whatever this version puts in a record is what the next one reads out."""
    records = [_record()]
    reporter = _reporter(tmp_path, records=records)

    assert shard_payload(reporter, 0)["records"] is records


def test_a_leg_that_measured_coverage_carries_it(tmp_path):
    reporter = _reporter(tmp_path)
    reporter.coverage_source = lambda base: ({"percent": 90.0, "html": "htmlcov/index.html"}, "")

    coverage = shard_payload(reporter, 0)["coverage"]

    assert coverage["percent"] == 90.0


def test_the_link_to_the_annotated_html_is_dropped(tmp_path):
    """It is relative to this shard's report base, and the merged report is
    written somewhere else entirely - the link would go nowhere."""
    reporter = _reporter(tmp_path)
    reporter.coverage_source = lambda base: ({"percent": 90.0, "html": "htmlcov/index.html"}, "")

    assert shard_payload(reporter, 0)["coverage"]["html"] == ""


def test_a_leg_whose_coverage_read_raised_still_writes_its_records(tmp_path):
    """Losing the tile is a decoration; failing the leg loses the records."""
    reporter = _reporter(tmp_path)

    def _raises(base):
        raise RuntimeError("coverage data is gone")

    reporter.coverage_source = _raises

    payload = shard_payload(reporter, 0)

    assert payload["coverage"] is None
    assert payload["records"]


def test_a_leg_that_measured_no_coverage_carries_none(tmp_path):
    reporter = _reporter(tmp_path)
    reporter.coverage_source = lambda base: (None, "")

    assert shard_payload(reporter, 0)["coverage"] is None


# ------------------------------------------------------------- write_bundle ---

def test_a_bundle_is_written_where_the_leg_was_told(tmp_path):
    payload = shard_payload(_reporter(tmp_path), 0)

    path = write_bundle(str(tmp_path / "shards" / "gw0"), payload)

    assert os.path.isfile(path)
    assert json.loads(open(path).read())["schema"] == SHARD_SCHEMA


def test_a_written_bundle_reads_back_as_the_same_bundle(tmp_path):
    """The round trip is the whole contract between a leg and the merge."""
    payload = shard_payload(_reporter(tmp_path, shard_id="gw0"), 0)
    path = write_bundle(str(tmp_path / "shards" / "gw0"), payload)

    bundle = read_bundle(path)

    assert bundle.shard.id == "gw0"
    assert len(bundle.records) == 1


def test_rewriting_the_same_leg_is_the_everyday_case(tmp_path, capsys):
    """Three legs point at one --html-report, and the next CI run points the
    same three at it again."""
    directory = str(tmp_path / "shards" / "gw0")
    payload = shard_payload(_reporter(tmp_path, shard_id="gw0"), 0)

    write_bundle(directory, payload)
    capsys.readouterr()
    write_bundle(directory, payload)

    assert "name the directory" not in capsys.readouterr().err


def test_a_second_different_leg_landing_on_one_directory_is_named(tmp_path, capsys):
    """"1/4" and "1-4" both sanitise to "1-4"; without this the second leg
    replaces the first's records and the merge reports a matrix a quarter
    smaller with nothing saying a leg was lost."""
    directory = str(tmp_path / "shards" / "1-4")

    write_bundle(directory, shard_payload(
        _reporter(tmp_path, shard_id="1-4", report_shard="1/4"), 0))
    capsys.readouterr()
    write_bundle(directory, shard_payload(
        _reporter(tmp_path, shard_id="1-4", report_shard="1-4"), 0))

    error = capsys.readouterr().err
    assert "both name the" in error
    assert "differ by more than punctuation" in error


def test_a_directory_holding_something_that_is_not_a_bundle_is_not_this_writes_problem(
        tmp_path, capsys):
    directory = tmp_path / "shards" / "gw0"
    directory.mkdir(parents=True)
    (directory / "records.json").write_text("not json at all")

    write_bundle(str(directory), shard_payload(_reporter(tmp_path), 0))

    assert (directory / "records.json").exists()


# ----------------------------------------------------------------- _Fields ---

def test_a_field_block_hands_back_everything_it_holds():
    fields = _Fields({"id": "gw0"}, {"id": "", "label": "", "assets": "shots"})

    assert fields.as_dict() == {"id": "gw0", "label": "", "assets": "shots"}


def test_a_null_in_the_json_falls_through_to_the_default():
    """A bundle written by a version that had not grown a key yet must answer
    the default rather than raise from inside a comprehension."""
    fields = _Fields({"label": None}, {"label": "unnamed"})

    assert fields.label == "unnamed"


def test_setting_a_field_is_visible_to_everything_reading_it():
    fields = _Fields({}, {"id": ""})
    fields.set("id", "gw3")

    assert fields.id == "gw3"
    assert fields.as_dict()["id"] == "gw3"
