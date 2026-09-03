"""Cover one leg of a sharded run, and the build the legs are merged back into.

A matrix that splits a suite across four machines has four processes that each
know a quarter of the run and none of which can write the report: a build is
one set of totals, one archived output.json, one trend point and one entry in
every per-test history Analytics reconstructs. So a shard writes a bundle of
its records and nothing else, and the merge turns N bundles back into the one
build they describe.

What is pinned down here is the two halves of that, in the order a run meets
them: what a leg leaves on disk - and, just as load-bearing, what it does not -
and then what the merge makes of a folder of those. The merge itself is a pure
function over bundle files, so most of these tests write the bundles by hand
and call it directly; a subprocess is spent only where the point *is* that
several processes agreed on something a single one could have faked.
"""

import json
import os
import subprocess
import sys
import textwrap
import time
from datetime import date

import pytest
from bs4 import BeautifulSoup

from pytest_html_reporter import merge, shards, shim
from pytest_html_reporter.cli import main
from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.merge import MergeError, MergeOptions
from pytest_html_reporter.shards import (
    BundleTooNew,
    ci_run_token,
    normalise_record,
    report_shard_run,
    write_bundle,
)


class _FakePluginManager:
    def hasplugin(self, name):
        return False


class _FakeConfig:
    """Just enough of pytest's Config for the option helpers."""

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


# Every environment variable a leg can derive its run token from, read off the
# module rather than spelled out again. This suite may itself be running on a
# CI server, and a leg started below would then stamp its bundle with that
# job's token and quietly stop merging the hand-written bundles beside it.
_CI_VARIABLES = tuple(name for _, names in shards._CI_RUN_VARIABLES for name in names)


# A one-pixel png. Nothing here decodes it - the merge copies each file by the
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


def _collect(nodeid, status, message=""):
    """A record about a file that yielded no tests, as store_collect_record makes one."""
    record = _record(nodeid, "(collection error)", status, -1, message=message)
    record["nodeid"] = nodeid
    record["collect"] = True

    return record


def _shot(name, step=-1):
    """One entry of a record's `screenshots` list, as collect_screenshots builds it."""
    return {
        "name": name, "suite": "test_a", "test": "test_one",
        "error": "", "label": "attached", "step": step,
    }


def _payload(shard_id, records, label=None, session_start=1000.0, session_end=1100.0,
             hostname="runner", coverage=None, **run):
    """One bundle, in the shape shard_payload builds it.

    The schema string and the version are read off the module rather than
    spelled out, so a format bump makes these fixtures fail by name instead of
    quietly turning into files the merge walks past as "not a bundle".
    """
    fields = {
        "session_start": session_start,
        "session_end": session_end,
        "exitstatus": 0,
        "token": "",
        "collected": len([record for record in records if not record.get("collect")]),
        "hostname": hostname,
        "platform": "Linux 6.5.0",
        "python": "3.11.9",
        "pytest": "9.1.1",
        "plugins": [],
        "arguments": "-k %s" % shard_id,
        "rootdir": "/builds/acme/app",
        "environment": "",
        "build_info": [],
        "capture_row": "all tests: stdout, stderr and logging",
        "capture_notice": "",
        "xdist_workers": [],
    }
    fields.update(run)

    return {
        "schema": shards.SHARD_SCHEMA,
        "version": shards.SHARD_VERSION,
        "generator": "pytest-html-reporter tests",
        "shard": {"id": shard_id, "label": label or shard_id, "assets": "pytest_screenshots"},
        "run": fields,
        "coverage": coverage,
        "counts": {"records": len(records), "collect": 0},
        "records": records,
    }


def _bundle(root, shard_id, records=(), **kwargs):
    """A bundle on disk under `root`, in its own directory, and that directory."""
    directory = os.path.join(str(root), shard_id)
    os.makedirs(directory, exist_ok=True)

    with open(os.path.join(directory, "records.json"), "w", encoding="utf-8") as handle:
        json.dump(_payload(shard_id, list(records), **kwargs), handle)

    return directory


def _png(directory, name, body=PNG):
    """A screenshot inside a bundle, where the shard's own leg would have put it."""
    folder = os.path.join(str(directory), "pytest_screenshots")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name + ".png")

    with open(path, "wb") as handle:
        handle.write(body)

    return path


def _merged(paths, **options):
    """Every bundle under `paths`, merged - the pure half of the command."""
    opts = MergeOptions(**options)

    return merge.merge_bundles(merge.load_bundles([str(path) for path in paths]), opts)


def _render(paths, out, **options):
    """Merge every bundle under `paths` and write the one build they describe."""
    opts = MergeOptions(html_report=str(out), **options)
    result = merge.merge_bundles(merge.load_bundles([str(path) for path in paths]), opts)
    merge.render_merged(result, opts)

    return result


def _built(base):
    """The build one merge or one run left in `base`."""
    with open(os.path.join(str(base), "output.json"), encoding="utf-8") as handle:
        return json.load(handle)


def _tests_in(data):
    """(suite, test, status) for every row of a build."""
    return [
        (suite["suite_name"], test["test_name"], test["status"])
        for suite in data["content"]["suites"].values()
        for test in suite["tests"].values()
    ]


def _rows():
    """Every Test Metrics row of the build just rendered, as a tuple.

    The five cells the table leads with: suite, test, status, duration, reruns.
    """
    soup = BeautifulSoup("<table>" + ConfigVars._test_metrics_content + "</table>", "html.parser")

    return [tuple(cell.text.strip() for cell in row.findAll("td")[:5])
            for row in soup.findAll("tr")]


def _env_rows():
    """The Environment panel of the build just rendered, as (label, value) pairs."""
    soup = BeautifulSoup(ConfigVars._environment_rows, "html.parser")

    return [(item.find("span", class_="env-item__label").text.strip(),
             item.find("span", class_="env-item__value").text.strip())
            for item in soup.findAll("div", class_="env-item")]


# The suite the subprocess runs below execute: seven tests over three files,
# one of each interesting status and one that attaches an image, so a leg can
# be split by -k and the halves put back together.
PNG_SOURCE = """
        PNG = (b"\\x89PNG\\r\\n\\x1a\\n\\x00\\x00\\x00\\rIHDR\\x00\\x00\\x00\\x01\\x00\\x00\\x00"
               b"\\x01\\x08\\x02\\x00\\x00\\x00\\x90wS\\xde\\x00\\x00\\x00\\x0cIDATx\\x9cc```\\x00"
               b"\\x00\\x00\\x04\\x00\\x01\\xf6\\x178U\\x00\\x00\\x00\\x00IEND\\xaeB`\\x82")
"""

SAMPLE = {
    "test_alpha.py": """
        import pytest

        def test_alpha_one_passes(): assert True
        def test_alpha_two_fails(): assert 1 == 2

        @pytest.mark.skip(reason="not today")
        def test_alpha_three_skips(): pass
    """,
    "test_beta.py": """
        import pytest

        @pytest.mark.xfail(reason="known upstream bug")
        def test_beta_one_xfails(): assert 1 == 2

        def test_beta_two_passes(): assert True
    """,
    "test_gamma.py": PNG_SOURCE + """
        from pytest_html_reporter import attach

        def test_gamma_one_attaches_a_screenshot():
            attach(data=PNG)

        def test_gamma_two_passes(): assert True
    """,
}


def _run(tmp_path, *args):
    """Run the sample suite in its own process and return what pytest printed.

    A subprocess rather than an inline run: what these tests are about is what
    several *processes* leave for each other on disk, and it keeps the outer
    run's own reporter out of the way.

    The child is handed an environment with every CI variable removed. A leg
    with no --report-shard-run derives its run token from those, so this suite
    running on a CI server would otherwise stamp the legs below with that job's
    token - and a merging leg would then put every hand-written bundle beside
    them aside as belonging to another run.
    """
    for name, body in SAMPLE.items():
        (tmp_path / name).write_text(textwrap.dedent(body).lstrip())

    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)
    for name in _CI_VARIABLES:
        env.pop(name, None)

    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider"] + list(args),
        cwd=str(tmp_path),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )


def _bundle_of(tmp_path, shard_id, directory="report"):
    """The bundle a leg wrote, read back."""
    path = tmp_path / directory / "shards" / shard_id / "records.json"
    assert path.is_file(), sorted(os.listdir(str(tmp_path)))

    return json.loads(path.read_text())


# --------------------------------------------------------------------------
# writing a shard
# --------------------------------------------------------------------------

def test_a_shard_writes_its_records_and_no_report(tmp_path):
    """The whole point of a leg: records for the merge, and no build.

    Four legs that each wrote a build would leave four trend points, four
    archive files and four Analytics entries behind for one run, with nothing
    on disk afterwards saying which four belonged together.
    """
    result = _run(tmp_path, "--html-report=./report", "--report-shard=1/4", "-k", "alpha")

    bundle = _bundle_of(tmp_path, "1-4")
    assert [record["test_name"] for record in bundle["records"]] == [
        "test_alpha_one_passes", "test_alpha_two_fails", "test_alpha_three_skips",
    ]

    base = tmp_path / "report"
    assert not (base / "pytest_html_report.html").exists(), result.stdout
    assert not (base / "output.json").exists(), result.stdout
    assert not (base / "archive").exists(), result.stdout


def test_a_shard_file_carries_every_record_key(tmp_path):
    """Lossless, because the merge indexes these keys without asking.

    build_report sorts on a hard record['index'] and the row builders index
    eight more, so a bundle that dropped a key would not degrade the merged
    report - it would end the merge in a traceback after every test in the
    matrix had already run.
    """
    _run(tmp_path, "--html-report=./report", "--report-shard=1", "-k", "gamma")

    records = _bundle_of(tmp_path, "1")["records"]
    for record in records:
        assert set(shards.RECORD_DEFAULTS) <= set(record), record["test_name"]

    photographed = [record for record in records if record["screenshots"]]
    assert [record["test_name"] for record in photographed] == \
        ["test_gamma_one_attaches_a_screenshot"]
    assert photographed[0]["phases"], "the phase timings the JUnit xml is built from"


def test_a_parallel_shard_writes_one_bundle_not_one_per_worker(tmp_path):
    """An `-n 2` leg is one leg of the matrix, however many processes it ran in.

    The bundle is written after the xdist worker guard, so the controller -
    which by then holds both workers' records, already merged - writes it once
    rather than each worker writing an eighth of the tests over the top of the
    others.
    """
    pytest.importorskip("xdist")

    _run(tmp_path, "--html-report=./report", "--report-shard=xd-1/2", "-n", "2")

    bundles = list((tmp_path / "report" / "shards").rglob("records.json"))
    assert len(bundles) == 1, [str(path) for path in bundles]

    payload = json.loads(bundles[0].read_text())
    assert len(payload["records"]) == 7
    assert sorted(set(payload["run"]["xdist_workers"])) == ["gw0", "gw1"]


def test_a_parallel_shard_counts_the_tests_it_collected(tmp_path):
    """`collected` is the first number somebody opening a bundle looks at.

    It used to be len(reporter._collected), which is empty on an xdist
    controller because pytest_collection_modifyitems never fires there - the
    workers do the collecting - so an `-n 4` leg wrote 0 beside a bundle
    holding four hundred records.
    """
    pytest.importorskip("xdist")

    _run(tmp_path, "--html-report=./report", "--report-shard=xd-1/2", "-n", "2")

    assert _bundle_of(tmp_path, "xd-1-2")["run"]["collected"] == 7


def test_a_shard_names_its_screenshots_under_its_own_directory(tmp_path):
    """The images travel inside the bundle, because the record only names them.

    collect_screenshots stores a bare name with no path and no extension, so a
    picture that stayed in the report folder would be a picture the merge could
    not find from the artifact it was handed.
    """
    _run(tmp_path, "--html-report=./report", "--report-shard=1/4", "-k", "gamma")

    inside = list((tmp_path / "report" / "shards" / "1-4" / "pytest_screenshots").glob("*.png"))
    assert len(inside) == 1

    record = [record for record in _bundle_of(tmp_path, "1-4")["records"]
              if record["screenshots"]][0]
    assert record["screenshots"][0]["name"] + ".png" == inside[0].name
    assert not (tmp_path / "report" / "pytest_screenshots").exists()


def test_a_second_shard_keeps_the_first_shards_screenshots(tmp_path):
    """Two legs, one --html-report, and neither may sweep the other's images.

    The legs of a sequential run are pointed at one report folder on purpose,
    so a leg that cleaned the folder rather than its own directory would leave
    the merge holding records that name pictures no longer on disk.
    """
    _run(tmp_path, "--html-report=./report", "--report-shard=leg-1", "-k", "gamma")
    _run(tmp_path, "--html-report=./report", "--report-shard=leg-2", "-k", "gamma")

    shards_root = tmp_path / "report" / "shards"
    assert len(list((shards_root / "leg-1" / "pytest_screenshots").glob("*.png"))) == 1
    assert len(list((shards_root / "leg-2" / "pytest_screenshots").glob("*.png"))) == 1


def test_a_shard_refuses_an_empty_id(tmp_path):
    """An id made entirely of separators is a usage error, not a fallback.

    Sanitising "//" leaves nothing, and a shard whose id came out empty would
    file its bundle in the report base and empty the report's own screenshot
    folder on the way.
    """
    result = _run(tmp_path, "--html-report=./report", "--report-shard=//")

    assert result.returncode == 4, result.stdout
    assert "--report-shard takes a name for this shard, not '//'" in result.stdout
    assert not (tmp_path / "report" / "shards").exists()


def test_a_shard_id_containing_html_still_cleans_and_writes_its_own_directory(tmp_path):
    """A leg named v1.html gets the same fresh directory as every other leg.

    The branch used to clean only this directory's pytest_screenshots folder,
    which leaves everything else in it behind - a half-written temp file from a
    killed run, a records.json from a run that collected more tests than this
    one does. A leg owns its whole directory, and everything in it belongs to
    the run starting now, which is also what the CI step that uploads that
    directory as this leg's artifact is entitled to assume.
    """
    stale = tmp_path / "report" / "shards" / "v1.html"
    (stale / "pytest_screenshots").mkdir(parents=True)
    (stale / "pytest_screenshots" / "999-1.png").write_bytes(PNG)
    (stale / ".records-abcd.tmp").write_text("half a bundle from a killed run")

    _run(tmp_path, "--html-report=./report", "--report-shard=v1.html", "-k", "gamma")

    assert sorted(os.listdir(str(stale))) == ["pytest_screenshots", "records.json"]
    assert not (stale / "pytest_screenshots" / "999-1.png").exists()
    assert _bundle_of(tmp_path, "v1.html")["shard"]["label"] == "v1.html"
    assert len(list((stale / "pytest_screenshots").glob("*.png"))) == 1


def test_two_legs_whose_ids_sanitise_alike_are_warned_about(tmp_path, capsys):
    """"1/4" and "1-4" name one directory, and the second leg buries the first.

    Overwriting is the everyday case and is right - the same leg re-runs, and
    the next CI run points the same legs at the same folder. Two *different*
    legs landing on one directory is not, and the report would otherwise show a
    matrix a quarter smaller with nothing anywhere saying a leg had been lost.
    """
    directory = str(tmp_path / "shards" / "1-4")

    write_bundle(directory, _payload("1-4", [_record("tests/test_a.py", "test_one", "PASS", 0)],
                                     label="1/4"))
    capsys.readouterr()

    write_bundle(directory, _payload("1-4", [_record("tests/test_b.py", "test_two", "PASS", 0)],
                                     label="1-4"))

    warning = capsys.readouterr().err
    assert "'1/4'" in warning and "'1-4'" in warning
    assert directory in warning


# --------------------------------------------------------------------------
# reading one shard
# --------------------------------------------------------------------------

def test_a_truncated_bundle_is_reported_rather_than_raising(tmp_path):
    """A killed job's half file must not cost the matrix the other three legs."""
    _bundle(tmp_path, "1", [_record("tests/test_a.py", "test_one", "PASS", 0)])
    broken = _bundle(tmp_path, "2", [_record("tests/test_b.py", "test_two", "PASS", 0)])

    with open(os.path.join(broken, "records.json"), "w", encoding="utf-8") as handle:
        handle.write('{"schema": "pytest-html-reporter/records", "records": [')

    notes = []
    bundles = merge.load_bundles([str(tmp_path)], notes)

    assert [bundle.shard.id for bundle in bundles] == ["1"]
    assert any("records.json" in note and "json" in note for note in notes), notes


def test_a_newer_bundle_format_is_refused_by_name(tmp_path):
    """Named and refused, never read hopefully.

    Silently dropping a quarter of a matrix produces a report that is wrong in
    a way nobody looking at it can see.
    """
    directory = _bundle(tmp_path, "1", [_record("tests/test_a.py", "test_one", "PASS", 0)])
    path = os.path.join(directory, "records.json")

    payload = json.loads(open(path, encoding="utf-8").read())
    payload["version"] = shards.SHARD_VERSION + 5
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)

    with pytest.raises(BundleTooNew) as error:
        merge.load_bundles([str(tmp_path)])

    assert path in str(error.value)
    assert str(shards.SHARD_VERSION) in str(error.value)


def test_a_newer_bundle_beside_a_merging_leg_does_not_end_the_run_in_a_traceback(tmp_path):
    """A stale artifact from a newer release is a message, not an INTERNALERROR.

    merge_into runs from pytest_terminal_summary, after every test has already
    finished, so a raise there costs the run its report, its output.json and
    its verdict - over a file somebody left in a folder.
    """
    directory = _bundle(tmp_path / "report" / "shards", "from-the-future",
                        [_record("tests/test_z.py", "test_new", "PASS", 0)])

    path = os.path.join(directory, "records.json")
    payload = json.loads(open(path, encoding="utf-8").read())
    payload["version"] = shards.SHARD_VERSION + 5
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)

    result = _run(tmp_path, "--html-report=./report", "--report-shard=leg-1",
                  "--report-shard-merge", "-k", "gamma")

    assert result.returncode == 0, result.stdout
    assert "INTERNALERROR" not in result.stdout
    assert "could not be merged" in result.stdout
    assert (tmp_path / "report" / "shards" / "leg-1" / "records.json").is_file()


def test_a_record_missing_keys_is_repaired_not_crashed(tmp_path):
    """A bundle from another release of the plugin still renders.

    build_report sorts on record['index'] and record['worker'] with no get(),
    so a record carrying the index as a string and no worker at all is exactly
    the shape that raises a TypeError in the middle of a merge.
    """
    _bundle(tmp_path / "shards", "1", [{
        "suite_name": "tests/test_a.py",
        "test_name": "test_one",
        "nodeid": "tests/test_a.py::test_one",
        "status": "PASS",
        "index": "3",
        "duration": "0.5",
    }])

    _render([tmp_path / "shards"], tmp_path / "out")

    assert _rows() == [("tests/test_a.py", "test_one", "PASS", "0.5", "0")]


def test_a_record_with_no_nodeid_is_quarantined(tmp_path):
    """Dropped, counted and named, rather than taking the merge down with it.

    A record with no node id cannot be grouped against a duplicate, ordered or
    linked to - and this is found after the whole matrix has finished, which is
    the worst moment there is to raise.
    """
    _bundle(tmp_path / "shards", "1", [
        _record("tests/test_a.py", "test_one", "PASS", 0),
        _record("tests/test_a.py", "test_nameless", "FAIL", 1, nodeid=""),
    ])

    result = _render([tmp_path / "shards"], tmp_path / "out")

    assert _rows() == [("tests/test_a.py", "test_one", "PASS", "0.01", "0")]
    assert len(result.quarantined) == 1
    assert any("test_nameless" in note for note in result.notes), result.notes


def test_an_unknown_key_survives_a_round_trip(tmp_path):
    """A field a newer release added is carried, not dropped.

    The bundle is the interchange format between two installations of this
    plugin, and a merge that discarded what it did not recognise would make
    every upgrade lossy in one direction.
    """
    _bundle(tmp_path / "shards", "1", [
        _record("tests/test_a.py", "test_one", "PASS", 0, flakiness="0.4"),
    ])

    result = _merged([tmp_path / "shards"])

    assert result.tests[0]["flakiness"] == "0.4"
    assert normalise_record({"nodeid": "x", "flakiness": "0.4"})["flakiness"] == "0.4"


# --------------------------------------------------------------------------
# merging shards
# --------------------------------------------------------------------------

def test_shards_are_ordered_by_natural_id_not_by_load_order(tmp_path):
    """The same four artifacts make the same report whatever order they arrive in.

    Two CI jobs downloading the same bundles in different orders have to
    produce the same rows, or the diff between two builds is unreadable - and
    "2-4" has to sort before "10-16", which plain string order does not do.
    """
    one = _bundle(tmp_path / "shards", "1", [_record("tests/test_a.py", "test_one", "PASS", 0)])
    two = _bundle(tmp_path / "shards", "2", [_record("tests/test_b.py", "test_two", "PASS", 0)])
    ten = _bundle(tmp_path / "shards", "10", [_record("tests/test_c.py", "test_ten", "PASS", 0)])

    rendered = []
    for position, order in enumerate(([one, two, ten], [ten, one, two], [two, ten, one])):
        _render(order, tmp_path / ("out-%d" % position))
        rendered.append(_rows())

    assert rendered[0] == [
        ("tests/test_a.py", "test_one", "PASS", "0.01", "0"),
        ("tests/test_b.py", "test_two", "PASS", "0.01", "0"),
        ("tests/test_c.py", "test_ten", "PASS", "0.01", "0"),
    ]
    assert rendered[1] == rendered[0]
    assert rendered[2] == rendered[0]


def test_a_suite_split_across_shards_is_one_suite(tmp_path):
    """One file split over three machines is one row in Suite Metrics.

    A suite counted once per shard would report three suites where the run had
    one, and Suite Highlights and Analytics both count off that.
    """
    _bundle(tmp_path / "shards", "1", [_record("tests/test_a.py", "test_one", "PASS", 0)])
    _bundle(tmp_path / "shards", "2", [_record("tests/test_a.py", "test_two", "FAIL", 0)])
    _bundle(tmp_path / "shards", "3", [_record("tests/test_a.py", "test_three", "PASS", 0)])

    _render([tmp_path / "shards"], tmp_path / "out")
    data = _built(tmp_path / "out")

    assert len(data["content"]["suites"]) == 1
    assert data["content"]["suites"]["0"]["status"]["total_pass"] == 2
    assert ConfigVars._suite_metrics_content.count("<tr>") == 1


def test_collection_errors_sort_ahead_of_every_shards_tests(tmp_path):
    """A file that would not import is read before the tests that did run.

    A collection failure is given a negative index by the plugin for exactly
    this reason, and four shards renumbering from zero would otherwise bury it
    in the middle of the table.
    """
    _bundle(tmp_path / "shards", "1", [_record("tests/test_a.py", "test_one", "PASS", 0)])
    _bundle(tmp_path / "shards", "2", [
        _record("tests/test_b.py", "test_two", "PASS", 0),
        _collect("tests/test_broken.py", "ERROR", "ImportError: no module named app.util"),
    ])

    _render([tmp_path / "shards"], tmp_path / "out")

    assert _rows()[0][:3] == ("tests/test_broken.py", "(collection error)", "ERROR")


def test_one_broken_module_seen_by_four_shards_is_reported_once(tmp_path):
    """Every leg collects the whole suite, so a broken import is in every bundle.

    Four copies of one collection failure is not a matrix that broke four
    times, and counting it four times would put three tests into the totals
    that never existed.
    """
    for shard_id in ("1", "2", "3", "4"):
        _bundle(tmp_path / "shards", shard_id, [
            _record("tests/test_a.py", "test_" + shard_id, "PASS", 0),
            _collect("tests/test_broken.py", "ERROR", "ImportError: cannot import name shim"),
        ])

    _render([tmp_path / "shards"], tmp_path / "out")
    data = _built(tmp_path / "out")

    assert data["status_list"]["error"] == "1"
    assert data["total_tests"] == str(len(_rows()))
    assert [row[0] for row in _rows()].count("tests/test_broken.py") == 1


def test_an_error_beats_a_skip_for_the_same_collector(tmp_path):
    """A file that failed to import on one machine failed to import, full stop.

    Another leg skipping it - a platform marker, a missing optional
    dependency - does not make the import work, so the error is the record
    worth keeping and the reason worth showing.
    """
    _bundle(tmp_path / "shards", "1", [_collect("tests/test_win.py", "SKIP", "skipped on linux")])
    _bundle(tmp_path / "shards", "2", [_collect("tests/test_win.py", "ERROR", "SyntaxError: bad")])

    _render([tmp_path / "shards"], tmp_path / "out")

    assert [row[:3] for row in _rows()] == [
        ("tests/test_win.py", "(collection error)", "ERROR"),
    ]


def test_shards_that_ran_under_different_roots_group_into_one_suite(tmp_path):
    """One test checked out at two paths is one test, once --strip-path-prefix says so.

    A container that built at /src and a runner that used /home/runner/work
    report the same test under two spellings, which is two rows, two Analytics
    histories and two entries in the JUnit file.
    """
    _bundle(tmp_path / "shards", "1", [
        _record("/src/tests/test_a.py", "test_one", "PASS", 0,
                nodeid="/src/tests/test_a.py::test_one"),
    ])
    _bundle(tmp_path / "shards", "2", [
        _record("/home/runner/work/tests/test_a.py", "test_two", "PASS", 0,
                nodeid="/home/runner/work/tests/test_a.py::test_two"),
    ])

    result = _merged([tmp_path / "shards"],
                     strip_path_prefix=["/src/", "/home/runner/work/"])

    assert [record["nodeid"] for record in result.tests] == [
        "tests/test_a.py::test_one", "tests/test_a.py::test_two",
    ]
    # Recomputed from the node id rather than stripped on its own, so grouping
    # follows identity instead of drifting away from it.
    assert {record["suite_name"] for record in result.tests} == {"tests/test_a.py"}


# --------------------------------------------------------------------------
# duplicates
# --------------------------------------------------------------------------

def test_a_duplicate_nodeid_folds_as_a_rerun_by_default(tmp_path):
    """One test that ran in two shards is one row that says it ran twice.

    An overlapping matrix is a mistake worth seeing, and the honest shape of
    it is the row the report already has for a retried test.
    """
    _bundle(tmp_path / "shards", "s1", [_record("tests/test_a.py", "test_flaky", "FAIL", 0)])
    _bundle(tmp_path / "shards", "s2", [_record("tests/test_a.py", "test_flaky", "PASS", 0)])

    result = _render([tmp_path / "shards"], tmp_path / "out")

    assert _rows() == [("tests/test_a.py", "test_flaky", "PASS", "0.01", "1")]
    assert _built(tmp_path / "out")["total_tests"] == "1"
    assert [fold["nodeid"] for fold in result.folds] == ["tests/test_a.py::test_flaky"]


def test_a_duplicate_nodeid_does_not_depend_on_rerunfailures(tmp_path, monkeypatch):
    """The answer is the same whatever happens to be installed on this machine.

    store_test_record folds attempts only when pytest-rerunfailures is loaded,
    which is a decision about the *merging* process and has nothing to do with
    the matrix, so the merge never routes duplicates through it.
    """
    _bundle(tmp_path / "shards", "s1", [_record("tests/test_a.py", "test_flaky", "FAIL", 0)])
    _bundle(tmp_path / "shards", "s2", [_record("tests/test_a.py", "test_flaky", "PASS", 0)])

    _render([tmp_path / "shards"], tmp_path / "without")
    without = _rows()

    monkeypatch.setattr(shim._StubPluginManager, "hasplugin", lambda self, name: True)
    _render([tmp_path / "shards"], tmp_path / "with")

    assert _rows() == without


def test_first_last_and_worst_each_keep_what_they_say(tmp_path):
    """The three policies that keep one attempt keep the one they are named for."""
    _bundle(tmp_path / "shards", "s1", [_record("tests/test_a.py", "test_flaky", "FAIL", 0)])
    _bundle(tmp_path / "shards", "s2", [_record("tests/test_a.py", "test_flaky", "PASS", 0)])

    kept = {}
    for policy in ("first", "last", "worst"):
        result = _merged([tmp_path / "shards"], on_duplicate=policy)
        kept[policy] = [record["status"] for record in result.tests]

    assert kept == {"first": ["FAIL"], "last": ["PASS"], "worst": ["FAIL"]}


def test_on_duplicate_error_names_the_nodeid_and_the_shards(tmp_path):
    """A pipeline that says an overlap is a bug is told which test and which legs.

    "the matrix overlaps" is not an answer anybody can act on; the node id and
    the two shard ids are.
    """
    _bundle(tmp_path / "shards", "s1", [_record("tests/test_a.py", "test_flaky", "FAIL", 0)])
    _bundle(tmp_path / "shards", "s2", [_record("tests/test_a.py", "test_flaky", "PASS", 0)])

    with pytest.raises(MergeError) as error:
        _merged([tmp_path / "shards"], on_duplicate="error")

    assert "tests/test_a.py::test_flaky" in str(error.value)
    assert "s1" in str(error.value) and "s2" in str(error.value)


def test_steps_are_never_concatenated_across_records(tmp_path):
    """The survivor keeps its own step list, not two shards' lists end to end.

    A step is addressed by its position in its own record's list, and both
    attachments and screenshots point at a step by that number - so splicing
    two records' steps together re-points every one of them at the wrong step.
    """
    _bundle(tmp_path / "shards", "s1", [
        _record("tests/test_a.py", "test_flaky", "FAIL", 0,
                steps=[{"title": "log in", "status": "FAIL", "phase": "call"}]),
    ])
    _bundle(tmp_path / "shards", "s2", [
        _record("tests/test_a.py", "test_flaky", "PASS", 0,
                steps=[{"title": "log in again", "status": "PASS", "phase": "call"}]),
    ])

    result = _merged([tmp_path / "shards"])

    assert [step["title"] for step in result.tests[0]["steps"]] == ["log in again"]


# --------------------------------------------------------------------------
# screenshots
# --------------------------------------------------------------------------

def test_screenshots_from_two_machines_do_not_collide(tmp_path):
    """Two legs' first screenshots are both "<ms>-1", and both have to survive.

    screenshot_name() is milliseconds plus a counter that restarts at 1 in
    every process, so a shared folder would leave one machine's picture on the
    other machine's row.
    """
    first = _bundle(tmp_path / "shards", "s1", [
        _record("tests/test_a.py", "test_one", "FAIL", 0, screenshots=[_shot("1788411677983-1")]),
    ])
    second = _bundle(tmp_path / "shards", "s2", [
        _record("tests/test_b.py", "test_two", "FAIL", 0, screenshots=[_shot("1788411677983-1")]),
    ])
    _png(first, "1788411677983-1", PNG)
    _png(second, "1788411677983-1", PNG + b"\x00")

    result = _render([tmp_path / "shards"], tmp_path / "out")

    named = [record["screenshots"][0]["name"] for record in result.tests]
    assert named == ["s1/1788411677983-1", "s2/1788411677983-1"]

    staged = tmp_path / "out" / "pytest_screenshots"
    assert (staged / "s1" / "1788411677983-1.png").read_bytes() == PNG
    assert (staged / "s2" / "1788411677983-1.png").read_bytes() == PNG + b"\x00"


def test_a_screenshot_inherited_from_the_shard_next_door_still_resolves(tmp_path):
    """The picture of the only failure in the matrix is not thrown away.

    Under the default policy the survivor is the last shard's record and its
    empty `screenshots` is back-filled from a loser - so a test photographed
    when it failed on s1 and then passed on s2 becomes an s2 row holding an s1
    image. Looking that up under the *row's* shard finds nothing and drops it
    as missing while it is sitting on disk in the shard next door.
    """
    first = _bundle(tmp_path / "shards", "s1", [
        _record("tests/test_a.py", "test_flaky", "FAIL", 0, screenshots=[_shot("111-1")]),
    ])
    _bundle(tmp_path / "shards", "s2", [_record("tests/test_a.py", "test_flaky", "PASS", 0)])
    _png(first, "111-1")

    result = _render([tmp_path / "shards"], tmp_path / "out")

    assert result.missing_assets == []
    assert result.tests[0]["screenshots"][0]["name"] == "s1/111-1"

    page = (tmp_path / "out" / "pytest_html_report.html").read_text()
    soup = BeautifulSoup(page, "html.parser")
    named = sorted({image["src"] for image in soup.findAll("img")
                    if image.get("src", "").startswith("pytest_screenshots/")})

    assert named == ["pytest_screenshots/s1/111-1.png"]
    assert (tmp_path / "out" / named[0]).is_file()


def test_a_missing_screenshot_is_dropped_rather_than_left_broken(tmp_path):
    """A card with a broken image reads as a bug in the report.

    The note says which file the bundle promised and did not carry, which is
    the only thing that can be acted on.
    """
    _bundle(tmp_path / "shards", "s1", [
        _record("tests/test_a.py", "test_one", "FAIL", 0, screenshots=[_shot("111-1")]),
    ])

    result = _render([tmp_path / "shards"], tmp_path / "out")

    assert result.tests[0]["screenshots"] == []
    assert len(result.missing_assets) == 1
    assert "pytest_screenshots" not in ConfigVars._test_metrics_content
    assert any("111-1" in note for note in result.notes), result.notes


def test_the_merged_name_reaches_all_three_render_sites(tmp_path):
    """One field feeds the row strip, the Screenshots card and the step tree.

    All three build "pytest_screenshots/" + the record's name + ".png" by plain
    concatenation, so a name that was rewritten for one of them and not the
    others would leave two of the three pointing nowhere.
    """
    directory = _bundle(tmp_path / "shards", "s1", [
        _record("tests/test_a.py", "test_one", "FAIL", 0,
                screenshots=[_shot("111-1", step=0)],
                steps=[{"title": "log in", "status": "FAIL", "phase": "call"}]),
    ])
    _png(directory, "111-1")

    _render([tmp_path / "shards"], tmp_path / "out")

    wanted = "pytest_screenshots/s1/111-1.png"
    assert wanted in ConfigVars._test_metrics_content
    assert wanted in ConfigVars._attach_screenshot_details
    assert wanted in ConfigVars._step_store


# --------------------------------------------------------------------------
# one build
# --------------------------------------------------------------------------

def test_merged_totals_equal_the_row_count(tmp_path):
    """The dashboard, the totals and the table have to agree with each other."""
    _bundle(tmp_path / "shards", "1", [
        _record("tests/test_a.py", "test_one", "PASS", 0),
        _record("tests/test_a.py", "test_two", "FAIL", 1),
    ])
    _bundle(tmp_path / "shards", "2", [
        _record("tests/test_b.py", "test_three", "SKIP", 0),
        _record("tests/test_b.py", "test_four", "xFAIL", 1),
        _record("tests/test_b.py", "test_five", "xPASS", 2),
    ])

    _render([tmp_path / "shards"], tmp_path / "out")
    data = _built(tmp_path / "out")

    assert data["total_tests"] == "5"
    assert len(_rows()) == 5
    assert sum(int(count) for status, count in data["status_list"].items()
               if status != "rerun") == 5


def test_merging_twice_in_one_process_does_not_double_the_dashboard(tmp_path):
    """The second build in one process is a build, not the first one doubled.

    generate_json_data accumulates its counters with += and the template
    renders that family rather than the assigned one, so a merge that did not
    reset them would double every number on the dashboard and raise nothing.
    """
    _bundle(tmp_path / "shards", "1", [
        _record("tests/test_a.py", "test_one", "PASS", 0),
        _record("tests/test_a.py", "test_two", "FAIL", 1),
    ])

    _render([tmp_path / "shards"], tmp_path / "first")
    _render([tmp_path / "shards"], tmp_path / "second")

    assert _built(tmp_path / "second")["status_list"] == _built(tmp_path / "first")["status_list"]
    assert _built(tmp_path / "second")["total_tests"] == "2"


def test_a_merge_writes_one_build_not_one_per_shard(tmp_path):
    """Three legs merged twice leave two builds in the history, not six.

    The archive, the trend and Analytics are all counted per build, so a matrix
    that rotated once per shard would show four builds a day where the project
    ran one.
    """
    for shard_id in ("1", "2", "3"):
        _bundle(tmp_path / "shards", shard_id,
                [_record("tests/test_%s.py" % shard_id, "test_one", "PASS", 0)])

    _render([tmp_path / "shards"], tmp_path / "out", start_time="now")
    _render([tmp_path / "shards"], tmp_path / "out", start_time="now")

    archives = list((tmp_path / "out" / "archive").glob("*.json"))
    assert len(archives) == 1, [path.name for path in archives]
    assert len(list((tmp_path / "out").glob("output.json"))) == 1


def test_the_merged_build_is_stamped_with_the_earliest_shard_start(tmp_path):
    """The build is dated when the tests ran, not when somebody merged them.

    That timestamp names the file the next build archives this one as, labels
    the point on the trend chart and orders the builds in Analytics, so a
    matrix that started before midnight and was merged after it must not be
    filed on the wrong day.
    """
    ran = time.time() - 5 * 86400.0

    _bundle(tmp_path / "shards", "1", [_record("tests/test_a.py", "test_one", "PASS", 0)],
            session_start=ran, session_end=ran + 60.0)
    _bundle(tmp_path / "shards", "2", [_record("tests/test_b.py", "test_two", "PASS", 0)],
            session_start=ran + 30.0, session_end=ran + 90.0)

    _render([tmp_path / "shards"], tmp_path / "out")
    data = _built(tmp_path / "out")

    assert data["start_time"] == ran
    assert data["date"] == date.fromtimestamp(ran).strftime("%B %d, %Y")


def test_the_environment_panel_names_every_shards_host(tmp_path):
    """The one panel on a merged report that could otherwise not be honest.

    Filled from the merging machine it would describe a process that ran none
    of the tests, on a platform the suite may never have touched.
    """
    _bundle(tmp_path / "shards", "1", [_record("tests/test_a.py", "test_one", "PASS", 0)],
            label="1/2", hostname="runner-1")
    _bundle(tmp_path / "shards", "2", [_record("tests/test_b.py", "test_two", "PASS", 0)],
            label="2/2", hostname="runner-2")

    _render([tmp_path / "shards"], tmp_path / "out")
    rows = dict(_env_rows())

    assert rows["Merged from"] == "2 shards"
    assert "runner-1" in rows["Shard 1/2"]
    assert "runner-2" in rows["Shard 2/2"]
    assert "Python 3.11.9" in rows["Shard 1/2"]


def test_the_capture_notice_survives_a_shard_that_ran_with_dash_s(tmp_path):
    """The explanation for an empty Logs column comes from the leg that ran with -s.

    The merge asks nothing of its own configuration here: under the shim
    getoption("capture") is None, so this sentence would silently vanish and
    leave a column of dashes with nothing to explain it.
    """
    notice = ("stdout and stderr are not captured while pytest runs with -s / --capture=no, "
              "so only logging output reaches this column")

    _bundle(tmp_path / "shards", "1", [_record("tests/test_a.py", "test_one", "PASS", 0)],
            capture_notice=notice)
    _bundle(tmp_path / "shards", "2", [_record("tests/test_b.py", "test_two", "PASS", 0)])

    _render([tmp_path / "shards"], tmp_path / "out")

    assert "-s / --capture=no" in ConfigVars._logs_notice
    assert "-s / --capture=no" in (tmp_path / "out" / "pytest_html_report.html").read_text()


# --------------------------------------------------------------------------
# coverage
# --------------------------------------------------------------------------

def test_a_merge_without_coverage_records_none_and_says_why(tmp_path):
    """No key at all, so the build reads as "not measured" rather than as zero.

    A zero would be archived, and the trend chart would carry it for as long as
    the archive is kept. Four shards' percentages are never averaged either,
    which is why the notice names `coverage combine`.
    """
    _bundle(tmp_path / "shards", "1", [_record("tests/test_a.py", "test_one", "PASS", 0)])
    _bundle(tmp_path / "shards", "2", [_record("tests/test_b.py", "test_two", "PASS", 0)])

    result = _render([tmp_path / "shards"], tmp_path / "out")

    assert "coverage" not in _built(tmp_path / "out")
    assert "coverage combine" in result.coverage_notice


def test_a_named_coverage_file_is_used(tmp_path):
    """One already-combined artifact, named by the operator, is the whole answer.

    discover_coverage is never called by a merge: it searches the working
    directory and stops at the first hit, so a stale coverage.json on the
    merging machine would become this build's number.
    """
    document = {
        "meta": {"version": "7.16.0", "branch_coverage": False},
        "files": {"src/sample.py": {"summary": {
            "covered_lines": 12, "num_statements": 16, "percent_covered": 75.0,
            "missing_lines": 4, "excluded_lines": 0, "num_branches": 0,
            "num_partial_branches": 0, "covered_branches": 0}, "missing_lines": [3, 4, 5, 6]}},
        "totals": {"covered_lines": 12, "num_statements": 16, "percent_covered": 75.0,
                   "missing_lines": 4, "excluded_lines": 0, "num_branches": 0,
                   "num_partial_branches": 0, "covered_branches": 0},
    }
    combined = tmp_path / "coverage.json"
    combined.write_text(json.dumps(document))

    _bundle(tmp_path / "shards", "1", [_record("tests/test_a.py", "test_one", "PASS", 0)])

    _render([tmp_path / "shards"], tmp_path / "out", report_coverage_file=str(combined))

    assert _built(tmp_path / "out")["coverage"]["percent"] == 75.0


def test_coverage_data_files_are_combined_when_coverage_is_importable(tmp_path):
    """Two legs' data files combined measure more than either one did.

    Each file below covers half of the module, and the same half is not
    counted twice: the merged figure is the union, which is the number an
    average of the two percentages could never arrive at.
    """
    coverage = pytest.importorskip("coverage")

    source = tmp_path / "sample.py"
    source.write_text("def one():\n    return 1\n\n\ndef two():\n    return 2\n")

    for position, lines in enumerate(([1, 2], [1, 5])):
        data_file = str(tmp_path / "data" / (".coverage.%d" % position))
        os.makedirs(os.path.dirname(data_file), exist_ok=True)
        measured = coverage.Coverage(data_file=data_file)
        measured.get_data().add_lines({str(source): lines})
        measured.save()

    _bundle(tmp_path / "shards", "1", [_record("tests/test_a.py", "test_one", "PASS", 0)])

    _render([tmp_path / "shards"], tmp_path / "out", coverage_data=[str(tmp_path / "data")])

    assert _built(tmp_path / "out")["coverage"]["percent"] == 75.0


# --------------------------------------------------------------------------
# telling this run's shards from the last run's
# --------------------------------------------------------------------------

def test_a_run_token_from_the_flag_beats_the_ini_and_the_ci_system(tmp_path):
    """The usual cli-beats-ini pair, for the value that decides what gets merged."""
    config = _FakeConfig(options={"report_shard_run": "run-9"},
                         ini={"report_shard_run": "run-1"})

    assert report_shard_run(config) == "run-9"
    assert report_shard_run(_FakeConfig(ini={"report_shard_run": "run-1"})) == "run-1"


def test_a_leg_on_a_ci_system_takes_its_token_from_the_ci_variables(monkeypatch):
    """Nobody types --report-shard-run on a matrix, so the CI job's own id answers."""
    for name in _CI_VARIABLES:
        monkeypatch.delenv(name, raising=False)

    monkeypatch.setenv("GITHUB_RUN_ID", "4218")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "2")

    assert report_shard_run(_FakeConfig()) == "github:4218-2"


def test_a_leg_off_a_ci_system_carries_no_run_token(monkeypatch):
    """And a leg with no token merges everything, as it always has.

    An empty token says nothing about which run a bundle came from, so refusing
    to merge on the strength of it would break every matrix that does not run
    on a CI system this plugin recognises. That case is --report-shard-reset's.
    """
    for name in _CI_VARIABLES:
        monkeypatch.delenv(name, raising=False)

    assert report_shard_run(_FakeConfig()) == ""
    assert ci_run_token({}) == ""


def test_a_rerun_of_a_matrix_does_not_share_the_first_attempts_token(tmp_path):
    """GITHUB_RUN_ID deliberately survives a re-run, and the attempt number does not.

    Without the attempt the second try would merge the first try's bundles, and
    the tests it re-ran would appear twice.
    """
    first = ci_run_token({"GITHUB_RUN_ID": "4218", "GITHUB_RUN_ATTEMPT": "1"})
    second = ci_run_token({"GITHUB_RUN_ID": "4218", "GITHUB_RUN_ATTEMPT": "2"})

    assert first != second


def test_two_ci_systems_numbering_their_builds_alike_get_different_tokens(tmp_path):
    """Jenkins build 41 and Drone build 41 are not the same run."""
    assert ci_run_token({"BUILD_NUMBER": "41"}) != ci_run_token({"DRONE_BUILD_NUMBER": "41"})


def test_a_stale_bundle_does_not_join_a_token_carrying_build(tmp_path):
    """Yesterday's leg is put aside and named, not counted into today's totals.

    The legs of a sequential run are pointed at one persistent --html-report, so
    <base>/shards accumulates; a leg that was renamed or dropped since the last
    run leaves its bundle sitting there, and the failure it causes is invisible -
    the totals are simply larger than the run was.
    """
    _bundle(tmp_path / "report" / "shards", "yesterday",
            [_record("tests/test_old.py", "test_gone_since", "PASS", 0)],
            token="run-1")

    result = _run(tmp_path, "--html-report=./report", "--report-shard=leg-2",
                  "--report-shard-run=run-2", "--report-shard-merge", "-k", "beta")

    names = [name for _, name, _ in _tests_in(_built(tmp_path / "report"))]
    assert names == ["test_beta_one_xfails", "test_beta_two_passes"], result.stdout

    assert "came from another run" in result.stdout
    assert "run-1" in result.stdout and "run-2" in result.stdout


def test_report_shard_reset_clears_the_shard_directory(tmp_path):
    """The deterministic answer for a run that has no token to filter on.

    The first leg of the run says so, and whatever the last run left behind is
    gone before this one writes a byte. Never implied by --report-shard or by
    --report-shard-merge, because it deletes the other legs' work.
    """
    _bundle(tmp_path / "report" / "shards", "yesterday",
            [_record("tests/test_old.py", "test_gone_since", "PASS", 0)])

    result = _run(tmp_path, "--html-report=./report", "--report-shard=leg-1",
                  "--report-shard-reset", "--report-shard-merge", "-k", "beta")

    assert not (tmp_path / "report" / "shards" / "yesterday").exists(), result.stdout

    names = [name for _, name, _ in _tests_in(_built(tmp_path / "report"))]
    assert names == ["test_beta_one_xfails", "test_beta_two_passes"]


def test_the_provenance_lines_name_every_merged_bundle(tmp_path):
    """Every build says out loud which bundles it was made of, and when they ran.

    There is no honest way to decide from inside a merge that a bundle is
    stale - every bundle beside a merging leg was written before it - so
    nothing is guessed and the times are simply shown. That is what turns a
    leftover leg from two silent extra tests into a line in the CI log.
    """
    _bundle(tmp_path / "report" / "shards", "leg-1",
            [_record("tests/test_old.py", "test_one", "PASS", 0),
             _record("tests/test_old.py", "test_two", "PASS", 1)],
            session_end=time.time() - 86400.0)

    result = _run(tmp_path, "--html-report=./report", "--report-shard=leg-2",
                  "--report-shard-merge", "-k", "beta")

    assert "merged shard leg-1: 2 tests, finished " in result.stdout, result.stdout
    assert "merged shard leg-2: 2 tests, finished " in result.stdout


# --------------------------------------------------------------------------
# end to end
# --------------------------------------------------------------------------

def test_two_shard_processes_then_the_merge_command(tmp_path, capsys):
    """Two machines' artifacts in a folder, one command, one report.

    The shape a CI matrix actually has: each leg uploads its bundle, a final
    job downloads them side by side and merges what it was given.
    """
    _run(tmp_path, "--html-report=./machine1/report", "--report-shard=1/2", "-k", "alpha")
    _run(tmp_path, "--html-report=./machine2/report", "--report-shard=2/2",
         "-k", "beta or gamma")

    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    for machine in ("machine1", "machine2"):
        (tmp_path / machine / "report" / "shards").rename(artifacts / machine)

    code = main(["merge", str(artifacts), "--html-report", str(tmp_path / "merged")])
    assert code == 0, capsys.readouterr().err

    data = _built(tmp_path / "merged")
    assert data["total_tests"] == "7"
    assert sorted(name for _, name, _ in _tests_in(data)) == [
        "test_alpha_one_passes", "test_alpha_three_skips", "test_alpha_two_fails",
        "test_beta_one_xfails", "test_beta_two_passes",
        "test_gamma_one_attaches_a_screenshot", "test_gamma_two_passes",
    ]

    page = (tmp_path / "merged" / "pytest_html_report.html").read_text()
    staged = sorted({image["src"] for image in BeautifulSoup(page, "html.parser").findAll("img")
                     if image.get("src", "").startswith("pytest_screenshots/")})

    # The one image in the matrix was taken on the second machine, so it is
    # filed under that shard and it is there: the merge copies by the name the
    # record holds, and the record travelled from another machine entirely.
    assert staged == ["pytest_screenshots/2-2/%s" % os.path.basename(staged[0])]
    assert (tmp_path / "merged" / staged[0]).is_file()


def test_a_merged_report_matches_a_single_run(tmp_path):
    """Two halves merged say exactly what the whole suite said in one process.

    The sharded sibling of the xdist test that compares a parallel run against
    a serial one: splitting the work must change how long it takes and nothing
    else.
    """
    single = _run(tmp_path, "--html-report=./single", "-p", "no:randomly")
    _run(tmp_path, "--html-report=./sharded", "--report-shard=1-2",
         "-p", "no:randomly", "-k", "alpha")
    _run(tmp_path, "--html-report=./sharded", "--report-shard=2-2",
         "-p", "no:randomly", "-k", "beta or gamma")

    _render([tmp_path / "sharded" / "shards"], tmp_path / "merged")

    assert _tests_in(_built(tmp_path / "merged")) == \
        _tests_in(_built(tmp_path / "single")), single.stdout


def test_sequential_legs_with_shard_merge_render_once(tmp_path):
    """Three commands on one machine, one build - not three, and not four.

    The last leg merges the two beside it and renders, so the sequential flow
    needs no fourth command; the two before it still wrote no build of their
    own, which is what keeps the archive honest.
    """
    _run(tmp_path, "--html-report=./report", "--report-shard=1-unit",
         "--report-shard-reset", "-k", "alpha")
    _run(tmp_path, "--html-report=./report", "--report-shard=2-integration", "-k", "beta")
    result = _run(tmp_path, "--html-report=./report", "--report-shard=3-e2e",
                  "--report-shard-merge", "-k", "gamma")

    data = _built(tmp_path / "report")
    assert data["total_tests"] == "7", result.stdout
    assert len(list((tmp_path / "report").glob("output.json"))) == 1
    assert not (tmp_path / "report" / "archive").exists(), "the first build archives nothing"

    # The legs' own screenshots are still where they were filed, and the merge
    # staged its own copy: a leg that swept the report folder would have taken
    # the others' pictures with it.
    assert (tmp_path / "report" / "shards" / "3-e2e" / "pytest_screenshots").is_dir()
    assert list((tmp_path / "report" / "pytest_screenshots" / "3-e2e").glob("*.png"))
