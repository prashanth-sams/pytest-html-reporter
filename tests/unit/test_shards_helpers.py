"""Cover the shard helpers that decide where things go and what they are called.

test_shards.py runs real legs and merges them, and every test in it is worth
having. It also means the helpers underneath are only ever reached with the
values a healthy run produces - so the ones written specifically for values a
*downloaded artifact* produces are the untested half.

That is the half worth pinning. A bundle is a file that arrived from CI, and
these are what stand between a name inside it and a file written outside the
report folder: an id that folds to a directory, a screenshot name carrying a
'..', an ordering that has to be the same twice running or the merge stops
being reproducible.
"""

import os

import pytest

from pytest_html_reporter.shards import (
    NOT_A_BUNDLE,
    ci_run_token,
    natural_key,
    normalise_record,
    report_shard_reset,
    report_shard_run,
    reset_shard_dir,
    safe_shot_name,
    sanitise_id,
    shard_dir,
    shards_root,
)


class _FakeConfig:
    def __init__(self, options=None, ini=None):
        self._options = options or {}
        self._ini = ini or {}

    def getoption(self, name, default=None):
        return self._options.get(name, default)

    def getini(self, name):
        if name not in self._ini:
            raise ValueError(name)
        return self._ini[name]


# ------------------------------------------------------------ NOT_A_BUNDLE ---

def test_not_a_bundle_is_falsey_and_says_what_it_is():
    """The one test that cannot be confused with a bundle holding no records."""
    assert not NOT_A_BUNDLE
    assert repr(NOT_A_BUNDLE) == "NOT_A_BUNDLE"


# ------------------------------------------------------------- ci_run_token ---

def test_a_github_actions_run_is_named_by_its_run_and_attempt():
    token = ci_run_token({"GITHUB_RUN_ID": "42", "GITHUB_RUN_ATTEMPT": "2"})

    assert token == "github:42-2"


def test_a_runner_too_old_for_the_second_variable_still_gets_a_token():
    """Otherwise it falls through and picks up somebody else's variable."""
    assert ci_run_token({"GITHUB_RUN_ID": "42"}) == "github:42"


def test_the_identifying_variable_is_the_one_that_has_to_be_there():
    assert ci_run_token({"GITHUB_RUN_ATTEMPT": "2"}) == ""


def test_a_blank_variable_does_not_count_as_being_on_that_system():
    assert ci_run_token({"GITHUB_RUN_ID": "   "}) == ""


def test_a_machine_that_is_not_a_ci_runner_has_no_token():
    assert ci_run_token({}) == ""
    assert ci_run_token({"HOME": "/home/amy"}) == ""


# --------------------------------------------------------- report_shard_run ---

def test_the_flag_beats_the_ini_key_and_the_ci_variables():
    config = _FakeConfig(options={"report_shard_run": "run-7"},
                         ini={"report_shard_run": "run-6"})

    assert report_shard_run(config) == "run-7"


def test_the_ini_key_is_used_when_the_flag_was_not_typed():
    assert report_shard_run(_FakeConfig(ini={"report_shard_run": "run-6"})) == "run-6"


def test_a_blank_flag_falls_through_rather_than_winning():
    config = _FakeConfig(options={"report_shard_run": "  "},
                         ini={"report_shard_run": "run-6"})

    assert report_shard_run(config) == "run-6"


def test_what_was_typed_is_stripped_before_it_is_compared():
    config = _FakeConfig(options={"report_shard_run": "  run-7  "})

    assert report_shard_run(config) == "run-7"


# ------------------------------------------------------- report_shard_reset ---

def test_the_reset_flag_is_honoured_when_it_was_typed():
    assert report_shard_reset(_FakeConfig(options={"report_shard_reset": True})) is True


@pytest.mark.parametrize("value", ["true", "True", "1", "yes", "on"])
def test_the_ini_key_accepts_the_usual_spellings_of_yes(value):
    assert report_shard_reset(_FakeConfig(ini={"report_shard_reset": value})) is True


@pytest.mark.parametrize("value", ["false", "0", "no", "", "maybe"])
def test_anything_else_leaves_the_other_legs_work_alone(value):
    assert report_shard_reset(_FakeConfig(ini={"report_shard_reset": value})) is False


def test_a_reset_is_never_implied_by_anything_else():
    """It deletes the other legs' work, so it has to be the flag the user typed."""
    config = _FakeConfig(options={"report_shard": "1/4", "report_shard_merge": True})

    assert report_shard_reset(config) is False


# ------------------------------------------------------------- sanitise_id ---

def test_an_ordinary_shard_id_is_left_alone():
    assert sanitise_id("gw0") == "gw0"


def test_a_separator_is_folded_so_the_id_cannot_become_a_directory():
    assert "/" not in sanitise_id("1/4")
    assert "\\" not in sanitise_id("ubuntu\\22.04")


def test_a_walk_out_of_the_tree_does_not_survive():
    """This id becomes a directory component under the report base."""
    cleaned = sanitise_id("../../etc")

    assert not cleaned.startswith("..")
    assert "/" not in cleaned


def test_asking_for_nothing_gives_nothing():
    assert sanitise_id("") == ""
    assert sanitise_id(None) == ""


# ------------------------------------------------------- the shard folders ---

def test_the_shards_live_in_a_subtree_of_the_report_folder():
    """A merge written back into the same folder must not delete its sources."""
    root = shards_root(os.path.join("out", "report"))

    assert root == os.path.join("out", "report", "shards")


def test_one_shards_folder_sits_under_that_root():
    assert shard_dir("out", "gw0") == os.path.join("out", "shards", "gw0")


def test_resetting_a_folder_that_was_never_written_is_not_an_error(tmp_path):
    reset_shard_dir(str(tmp_path / "shards"))


def test_resetting_removes_what_the_last_run_left(tmp_path):
    folder = tmp_path / "shards"
    (folder / "gw0").mkdir(parents=True)
    (folder / "gw0" / "bundle.json").write_text("{}")

    reset_shard_dir(str(folder))

    assert not folder.exists()


# ------------------------------------------------------------- natural_key ---

def test_the_tenth_shard_does_not_sort_second():
    """Plain string order puts '10-16' before '2-4'."""
    assert sorted(["10-16", "2-4", "1-4"], key=natural_key) == ["1-4", "2-4", "10-16"]


def test_a_number_is_never_compared_against_a_word():
    """Each part says which kind it is, so this cannot raise on any Python."""
    assert sorted(["gw2", "gw10", "ubuntu"], key=natural_key) == \
        ["gw2", "gw10", "ubuntu"]


def test_an_id_that_is_only_digits_still_sorts_as_a_number():
    assert sorted(["10", "9", "1"], key=natural_key) == ["1", "9", "10"]


def test_an_empty_id_has_a_key_of_its_own():
    assert natural_key("") == ()


# ---------------------------------------------------------- safe_shot_name ---

def test_an_ordinary_screenshot_name_survives():
    assert safe_shot_name("1725200000-gw0-1") == "1725200000-gw0-1"


def test_an_absolute_name_cannot_take_over_the_join():
    """It would land the copy outside the report directory entirely."""
    assert safe_shot_name("/etc/passwd") == "passwd"


def test_a_walk_out_of_the_folder_is_flattened():
    assert safe_shot_name("../../secrets") == "secrets"


def test_a_windows_separator_is_flattened_too():
    assert safe_shot_name("..\\..\\secrets") == "secrets"


@pytest.mark.parametrize("value", ["..", ".", "", None, "/", "../"])
def test_a_name_that_is_only_a_walk_is_refused_outright(value):
    assert safe_shot_name(value) == ""


# -------------------------------------------------------- normalise_record ---

def test_a_duration_that_arrived_as_text_is_read_rather_than_dropped():
    """It is a decoration on a row, and no reason to lose the row."""
    assert normalise_record({"nodeid": "a", "duration": "1.2"})["duration"] == 1.2


@pytest.mark.parametrize("value", [None, "", "soon", []])
def test_a_duration_that_cannot_be_read_becomes_zero(value):
    assert normalise_record({"nodeid": "a", "duration": value})["duration"] == 0.0


def test_a_rerun_count_that_cannot_be_read_becomes_zero():
    assert normalise_record({"nodeid": "a", "rerun": "twice"})["rerun"] == 0


def test_a_list_field_that_arrived_as_something_else_becomes_empty():
    record = normalise_record({"nodeid": "a", "screenshots": "one of them"})

    assert record["screenshots"] == []


def test_a_tuple_is_accepted_where_a_list_was_expected():
    record = normalise_record({"nodeid": "a", "screenshots": ({"name": "x"},)})

    assert record["screenshots"] == [{"name": "x"}]
