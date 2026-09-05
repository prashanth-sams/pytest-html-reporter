"""Cover how the merge decides two rows are the same test, and in what order.

Both questions have the same failure mode, and it is the quiet one. A node id
spelled two ways is two rows, two histories in Analytics and two entries in the
JUnit file, with nothing on the page saying it happened. An ordering that
depends on the order artifacts were downloaded gives two CI jobs two different
reports from identical inputs, and the diff between builds stops being
readable.

Neither is visible in a report that renders successfully, which is exactly why
they are pinned here rather than left to the end-to-end tests.
"""

import time

import pytest

from pytest_html_reporter.merge import (
    MergeError,
    MergeOptions,
    ShardMeta,
    _start_stamp,
    merge_runs,
    merged_environment_rows,
    normalise_nodeid,
    order_bundles,
)
from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.shards import Bundle


def _bundle(shard_id="gw0", path=None, session_end=0.0, label="", records=None):
    return Bundle(
        path or ("/builds/%s/records.json" % shard_id),
        {"shard": {"id": shard_id, "label": label},
         "run": {"session_end": session_end},
         "records": records or []},
    )


class _Shard:
    def __init__(self, label="gw0", summary="linux, python 3.12"):
        self.label = label
        self.summary = summary


class _Meta:
    def __init__(self, environment="", build_info=(), capture_rows=(),
                 shards=(), session_start=1725200000.0, ci="", pipeline="",
                 branch="", commit="", package_rows=()):
        self.environment = environment
        self.build_info = list(build_info)
        self.capture_rows = list(capture_rows)
        self.shards = list(shards)
        self.session_start = session_start

        # What the shards said about the run itself: which CI build, which
        # commit, what was installed. Empty here is a merge of bundles written
        # before any of it was collected, which is the case the panel has to
        # keep rendering.
        self.ci = ci
        self.pipeline = pipeline
        self.branch = branch
        self.commit = commit
        self.package_rows = list(package_rows)


_TOUCHED = ("_environment", "_environment_label", "_environment_class",
            "_environment_rows")


@pytest.fixture(autouse=True)
def _isolate():
    saved = {name: getattr(ConfigVars, name, None) for name in _TOUCHED}
    yield
    for name, value in saved.items():
        setattr(ConfigVars, name, value)


# --------------------------------------------------------- normalise_nodeid ---

def test_a_windows_runners_backslashes_become_the_same_id():
    """The same test under two spellings is two rows and two histories."""
    assert normalise_nodeid("tests\\unit\\test_cart.py::test_add") == \
        "tests/unit/test_cart.py::test_add"


def test_a_doubled_separator_is_collapsed():
    assert normalise_nodeid("tests//unit//test_cart.py::test_add") == \
        "tests/unit/test_cart.py::test_add"


def test_a_leading_dot_slash_is_dropped():
    assert normalise_nodeid("./tests/test_cart.py::test_add") == \
        "tests/test_cart.py::test_add"


def test_repeated_leading_dot_slashes_are_all_dropped():
    assert normalise_nodeid("././tests/test_cart.py::test_add") == \
        "tests/test_cart.py::test_add"


def test_a_named_prefix_is_stripped():
    """A container that checked out at /src and a runner that used
    /home/runner/work ran the same test."""
    assert normalise_nodeid("/src/tests/test_cart.py::test_add", ["/src"]) == \
        "tests/test_cart.py::test_add"


def test_a_prefix_is_typed_the_way_the_path_reads():
    assert normalise_nodeid("./src/tests/test_cart.py::test_add", ["./src"]) == \
        "tests/test_cart.py::test_add"


def test_a_prefix_that_does_not_match_leaves_the_id_alone():
    assert normalise_nodeid("tests/test_cart.py::test_add", ["/src"]) == \
        "tests/test_cart.py::test_add"


def test_a_blank_prefix_is_skipped_rather_than_matching_everything():
    assert normalise_nodeid("tests/test_cart.py::test_add", ["", "  ", None]) == \
        "tests/test_cart.py::test_add"


def test_a_prefix_that_swallows_the_whole_id_is_refused():
    """An empty node id is quarantined; the original is worth more than that."""
    assert normalise_nodeid("/src", ["/src"]) == "/src"


def test_several_prefixes_are_tried_in_turn():
    assert normalise_nodeid("/src/tests/test_cart.py::test_add", ["/build", "/src"]) == \
        "tests/test_cart.py::test_add"


def test_an_id_that_is_nothing_at_all_stays_nothing():
    assert normalise_nodeid(None) == ""
    assert normalise_nodeid("") == ""


# ------------------------------------------------------------ order_bundles ---

def test_the_tenth_shard_is_not_ordered_second():
    bundles = [_bundle("10-16"), _bundle("2-4"), _bundle("1-4")]

    assert [b.shard.id for b in order_bundles(bundles)] == ["1-4", "2-4", "10-16"]


def test_the_order_does_not_depend_on_the_order_they_were_downloaded():
    """Two CI jobs downloading the same four artifacts have to agree."""
    one = [_bundle("gw2"), _bundle("gw0"), _bundle("gw1")]
    other = [_bundle("gw1"), _bundle("gw2"), _bundle("gw0")]

    assert [b.shard.id for b in order_bundles(one)] == \
        [b.shard.id for b in order_bundles(other)]


def test_a_retried_leg_whose_artifact_landed_twice_keeps_the_later_run():
    """The later run is the one whose result the pipeline acted on."""
    first = _bundle("gw0", path="/builds/a/records.json", session_end=100.0)
    retry = _bundle("gw0", path="/builds/b/records.json", session_end=200.0)

    kept = order_bundles([first, retry])

    assert len(kept) == 1
    assert kept[0].path == "/builds/b/records.json"


def test_a_duplicate_that_finished_earlier_does_not_win():
    first = _bundle("gw0", path="/builds/a/records.json", session_end=200.0)
    retry = _bundle("gw0", path="/builds/b/records.json", session_end=100.0)

    assert order_bundles([first, retry])[0].path == "/builds/a/records.json"


def test_every_bundle_is_told_where_it_sits_in_the_order():
    """Read by every step that has to break a tie the same way twice."""
    ordered = order_bundles([_bundle("gw1"), _bundle("gw0")])

    assert [b.ordinal for b in ordered] == sorted(b.ordinal for b in ordered)


def test_ordering_nothing_yields_nothing():
    assert order_bundles([]) == []


# ------------------------------------------------------------- _start_stamp ---

def test_the_earliest_shard_start_is_the_default():
    """It names the file the next build archives this one as, and orders the
    builds in Analytics - so it is asked about rather than assumed."""
    meta = _Meta(session_start=1725200000.0)

    assert _start_stamp(meta, "earliest") == 1725200000.0
    assert _start_stamp(meta, None) == 1725200000.0


def test_now_stamps_the_moment_the_merge_ran():
    stamped = _start_stamp(_Meta(), "now")

    assert abs(stamped - time.time()) < 5


def test_a_unix_timestamp_is_taken_as_it_is():
    assert _start_stamp(_Meta(), "1725300000") == 1725300000.0


def test_a_typo_stops_the_merge_rather_than_stamping_something_wrong():
    with pytest.raises(MergeError) as error:
        _start_stamp(_Meta(), "yesterday")

    assert "earliest, now or a unix timestamp" in str(error.value)


# ------------------------------------------------- merged_environment_rows ---

def test_the_panel_names_every_shards_own_machine():
    """The panel used to be the one part of a merged page that could not be
    honest - it described the merging process, which ran no tests at all."""
    meta = _Meta(shards=[_Shard("gw0", "linux, python 3.12"),
                         _Shard("gw1", "windows, python 3.11")])

    rows = merged_environment_rows(meta, MergeOptions())

    assert "gw0" in rows and "linux" in rows
    assert "gw1" in rows and "windows" in rows


def test_the_panel_counts_the_shards_it_was_built_from():
    meta = _Meta(shards=[_Shard("gw0"), _Shard("gw1")])

    assert "2 shards" in merged_environment_rows(meta, MergeOptions())


def test_one_shard_is_counted_in_the_singular():
    assert "1 shard" in merged_environment_rows(_Meta(shards=[_Shard()]),
                                                MergeOptions())


def test_the_merge_flag_names_the_environment_when_it_was_given():
    rows = merged_environment_rows(_Meta(environment="staging"),
                                   MergeOptions(environment="production"))

    assert "production" in rows
    assert ConfigVars._environment == "production"


def test_the_shards_own_environment_is_used_when_the_flag_was_not():
    rows = merged_environment_rows(_Meta(environment="staging"), MergeOptions())

    assert "staging" in rows


def test_shards_that_captured_output_the_same_way_get_one_row():
    meta = _Meta(capture_rows=[("gw0", "enabled"), ("gw1", "enabled")])

    rows = merged_environment_rows(meta, MergeOptions())

    assert rows.count("Captured output") == 1


def test_a_matrix_where_one_leg_ran_with_s_answers_for_each_leg():
    """One summarised row would be a lie."""
    meta = _Meta(capture_rows=[("gw0", "enabled"), ("gw1", "disabled (-s)")])

    rows = merged_environment_rows(meta, MergeOptions())

    assert "Captured output (gw0)" in rows
    assert "Captured output (gw1)" in rows


def test_the_merge_flags_build_info_wins_over_the_shards():
    meta = _Meta(build_info=[("branch", "from-shard")])

    rows = merged_environment_rows(meta, MergeOptions(build_info=["branch=from-flag"]))

    assert "from-flag" in rows
    assert "from-shard" not in rows


def test_build_info_the_flag_did_not_mention_still_comes_from_the_shards():
    meta = _Meta(build_info=[("commit", "abc123")])

    rows = merged_environment_rows(meta, MergeOptions(build_info=["branch=main"]))

    assert "abc123" in rows
    assert "main" in rows


# --------------------------------------------------- the run's own identity ---

def _leg(shard_id="leg-1", **run):
    """A bundle carrying whatever this test cares about in its run block.

    Everything else falls through to RUN_DEFAULTS, which is exactly what a
    bundle written by an older version of the plugin does.
    """
    return Bundle("/builds/%s/records.json" % shard_id,
                  {"shard": {"id": shard_id, "label": shard_id},
                   "run": run, "records": []})


_GITHUB = {"system": "github", "label": "GitHub Actions", "build": "42",
           "url": "https://github.com/acme/app/actions/runs/1717"}


def test_a_matrix_that_agrees_about_its_build_says_it_once():
    meta = merge_runs([_leg("leg-1", ci=_GITHUB), _leg("leg-2", ci=_GITHUB)])

    assert meta.ci == "GitHub Actions · 42"
    assert meta.pipeline == _GITHUB["url"]


def test_a_matrix_that_names_two_pipelines_links_neither():
    """Two legs from two different builds is a matrix that should not have been
    merged, and a link to the first one would be read as the whole build's."""
    other = dict(_GITHUB, url="https://github.com/acme/app/actions/runs/9999")

    meta = merge_runs([_leg("leg-1", ci=_GITHUB), _leg("leg-2", ci=other)])

    assert meta.pipeline == ""
    assert any("different pipelines" in note for note in meta.notes)


def test_legs_that_ran_different_commits_both_get_named():
    """Smoothing this over would hide the one thing that explains why half the
    matrix failed."""
    meta = merge_runs([_leg("leg-1", git={"branch": "main", "commit": "aaaaaa"}),
                       _leg("leg-2", git={"branch": "main", "commit": "bbbbbb"})])

    assert meta.branch == "main"
    assert meta.commit == "aaaaaa, bbbbbb"


def test_bundles_written_before_any_of_this_existed_still_merge():
    """An older leg carries none of these keys, and reads back as a leg that
    had nothing to say - which is what it is."""
    meta = merge_runs([_leg("leg-1"), _leg("leg-2")])

    assert (meta.ci, meta.pipeline, meta.branch, meta.commit) == ("", "", "", "")
    assert meta.package_rows == []


def test_one_environment_is_described_once_rather_than_per_shard():
    """Eight identical three-hundred entry rows is not a panel, it is a wall."""
    packages = ["attrs==23.2.0", "pytest==8.2.0"]

    meta = merge_runs([_leg("leg-1", packages=packages), _leg("leg-2", packages=packages)])

    assert meta.package_rows == [("", packages)]


def test_legs_with_different_packages_are_listed_separately():
    """This is the case the row is for: the leg that failed had another version
    of something installed."""
    meta = merge_runs([_leg("leg-1", packages=["pytest==8.2.0"]),
                       _leg("leg-2", packages=["pytest==8.3.0"])])

    assert meta.package_rows == [("leg-1", ["pytest==8.2.0"]),
                                 ("leg-2", ["pytest==8.3.0"])]


def test_a_shard_row_prefers_the_os_it_named_over_the_kernel():
    shard = ShardMeta(_leg("leg-1", platform="Linux 5.15.0", os="Ubuntu 22.04.4 LTS (x86_64)"))

    assert "Ubuntu 22.04.4 LTS (x86_64)" in shard.summary
    assert "5.15.0" not in shard.summary


def test_an_older_shard_row_still_names_its_kernel():
    """The fallback that keeps a half-upgraded matrix readable: one leg's
    bundle knows about the os key and the other's does not."""
    shard = ShardMeta(_leg("leg-1", platform="Linux 5.15.0"))

    assert "Linux 5.15.0" in shard.summary


def test_a_shard_row_says_how_many_workers_split_it():
    shard = ShardMeta(_leg("leg-1", xdist_workers=["gw0", "gw1", "gw2", "gw3"]))

    assert "4 workers" in shard.summary


def test_a_serial_shard_row_says_nothing_about_workers():
    assert "workers" not in ShardMeta(_leg("leg-1", xdist_workers=["gw0"])).summary


def test_the_panel_links_the_pipeline_the_shards_came_from():
    rows = merged_environment_rows(_Meta(ci="GitHub Actions · 42",
                                         pipeline="https://ci.acme.dev/42"), MergeOptions())

    assert "GitHub Actions · 42" in rows
    assert 'href="https://ci.acme.dev/42"' in rows


def test_a_shards_own_build_info_still_beats_what_was_detected():
    """A leg that published "commit=..." through --build-info meant that one."""
    meta = _Meta(build_info=[("commit", "stated")], commit="detected")

    rows = merged_environment_rows(meta, MergeOptions())

    assert "stated" in rows
    assert "detected" not in rows


def test_the_packages_are_the_last_thing_on_the_panel():
    """Longest row on the page by two orders of magnitude, and everything above
    it is what somebody opened the panel for."""
    meta = _Meta(shards=[_Shard()], package_rows=[("", ["pytest==8.2.0"])])

    rows = merged_environment_rows(meta, MergeOptions())

    assert "Packages (1)" in rows
    assert rows.index("Packages (1)") > rows.index("Merged from")
