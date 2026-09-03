"""Cover reading a bundle off disk, and the three answers that reading gives.

A bundle is the one file in this project that arrives from somewhere else - a
CI artifact, downloaded and unpacked by a step nobody here wrote - so every
question about it has to be answered without trusting it: is this even one of
ours, was it written by a version that knows more than we do, does its id name
a directory we own.

Three outcomes rather than two, because they need three reactions: skip it and
say so, stop the merge, or merge it. Getting the middle one wrong is the
expensive case - a bundle from the future read hopefully is a build whose
numbers are quietly incomplete.
"""

import json
import os

import pytest

from pytest_html_reporter.shards import (
    NOT_A_BUNDLE,
    SHARD_SCHEMA,
    SHARD_VERSION,
    Bundle,
    BundleTooNew,
    find_bundles,
    read_bundle,
)


def _payload(version=None, **overrides):
    payload = {
        "schema": SHARD_SCHEMA,
        "version": SHARD_VERSION if version is None else version,
        "shard": {"id": "gw0", "label": "ubuntu"},
        "run": {"session_end": 1725200000.0},
        "records": [{"nodeid": "tests/test_cart.py::test_add"}],
    }
    payload.update(overrides)
    return payload


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))
    return str(path)


# ------------------------------------------------------------- read_bundle ---

def test_a_bundle_this_version_wrote_is_read(tmp_path):
    bundle = read_bundle(_write(tmp_path / "gw0" / "records.json", _payload()))

    assert bundle.shard.id == "gw0"
    assert bundle.shard.label == "ubuntu"
    assert len(bundle.records) == 1


def test_a_file_that_is_not_json_is_skipped_and_named(tmp_path):
    """One of the twenty other files sitting in an artifact folder."""
    path = tmp_path / "notes.txt"
    path.write_text("not json at all")
    notes = []

    assert read_bundle(str(path), notes) is NOT_A_BUNDLE
    assert "could not be read as json" in notes[0]
    assert str(path) in notes[0]


def test_a_file_that_is_not_there_is_skipped_rather_than_raising(tmp_path):
    notes = []

    assert read_bundle(str(tmp_path / "nope.json"), notes) is NOT_A_BUNDLE
    assert notes


def test_json_that_is_not_one_of_ours_is_skipped_and_named(tmp_path):
    path = _write(tmp_path / "coverage.json", {"totals": {}})
    notes = []

    assert read_bundle(path, notes) is NOT_A_BUNDLE
    assert "not a bundle" in notes[0]


def test_json_that_is_not_even_an_object_is_skipped(tmp_path):
    path = tmp_path / "list.json"
    path.write_text("[1, 2, 3]")

    assert read_bundle(str(path), []) is NOT_A_BUNDLE


def test_notes_are_optional(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("not json")

    assert read_bundle(str(path)) is NOT_A_BUNDLE


def test_a_bundle_from_the_future_stops_the_merge_rather_than_being_guessed_at(tmp_path):
    """Read hopefully, it is a build whose numbers are quietly incomplete."""
    path = _write(tmp_path / "gw0" / "records.json",
                  _payload(version=SHARD_VERSION + 5))

    with pytest.raises(BundleTooNew) as error:
        read_bundle(path)

    assert str(SHARD_VERSION + 5) in str(error.value)
    assert str(SHARD_VERSION) in str(error.value)


def test_a_version_that_is_not_a_number_is_read_as_the_oldest(tmp_path):
    """Better than refusing: an unreadable version is not a version from the
    future, and the upgrades walk it forward from the start."""
    path = _write(tmp_path / "gw0" / "records.json", _payload(version="one"))

    assert read_bundle(path) is not NOT_A_BUNDLE


def test_a_bundle_with_no_version_at_all_is_still_read(tmp_path):
    payload = _payload()
    del payload["version"]

    assert read_bundle(_write(tmp_path / "gw0" / "records.json", payload)) \
        is not NOT_A_BUNDLE


# ------------------------------------------------------------------ Bundle ---

def test_a_bundle_with_no_id_is_named_after_its_own_directory():
    """An id is what every ordering and every screenshot path is keyed on, so
    two anonymous bundles must not collapse into one."""
    bundle = Bundle(os.path.join(os.sep, "artifacts", "leg-3", "records.json"),
                    {"shard": {}, "run": {}, "records": []})

    assert bundle.shard.id == "leg-3"


def test_an_id_that_would_escape_the_report_folder_is_sanitised_on_the_way_in():
    """A leg sanitises its own id before it writes; a bundle is a file that
    arrived from CI and was never asked to."""
    bundle = Bundle(os.path.join(os.sep, "artifacts", "leg", "records.json"),
                    {"shard": {"id": "../../etc"}, "run": {}, "records": []})

    assert ".." not in bundle.shard.id
    assert "/" not in bundle.shard.id


def test_a_bundle_says_where_its_pictures_are():
    bundle = Bundle(os.path.join(os.sep, "artifacts", "gw0", "records.json"),
                    {"shard": {"id": "gw0"}, "run": {}, "records": []})

    assert bundle.assets_dir == os.path.join(
        os.sep, "artifacts", "gw0", "pytest_screenshots")


def test_a_bundle_naming_its_own_asset_folder_is_believed():
    bundle = Bundle(os.path.join(os.sep, "artifacts", "gw0", "records.json"),
                    {"shard": {"id": "gw0", "assets": "shots"}, "run": {},
                     "records": []})

    assert bundle.assets_dir.endswith("shots")


def test_a_bundle_describes_itself_readably():
    bundle = Bundle(os.path.join(os.sep, "a", "records.json"),
                    {"shard": {"id": "gw0"}, "run": {},
                     "records": [{"nodeid": "a"}]})

    assert repr(bundle) == "<Bundle gw0 (1 records)>"


def test_a_key_this_version_never_heard_of_survives_being_read():
    """Kept whole rather than picked apart, so a newer field is not lost."""
    bundle = Bundle(os.path.join(os.sep, "a", "records.json"),
                    {"shard": {"id": "gw0"}, "run": {}, "records": [],
                     "something_new": 42})

    assert bundle.payload["something_new"] == 42


def test_a_field_a_bundle_does_not_carry_answers_its_default():
    """A bundle written before a key existed must answer, not raise from
    inside a comprehension."""
    bundle = Bundle(os.path.join(os.sep, "a", "records.json"),
                    {"shard": {"id": "gw0"}, "run": {}, "records": []})

    assert bundle.shard.label == ""
    assert bundle.run.session_end is not None


def test_a_field_that_exists_nowhere_is_an_attribute_error():
    bundle = Bundle(os.path.join(os.sep, "a", "records.json"),
                    {"shard": {"id": "gw0"}, "run": {}, "records": []})

    with pytest.raises(AttributeError):
        bundle.shard.no_such_field


# ----------------------------------------------------------- find_bundles ---

def test_a_folder_of_artifacts_is_walked(tmp_path):
    _write(tmp_path / "gw0" / "records.json", _payload())
    _write(tmp_path / "gw1" / "records.json", _payload())

    assert len(find_bundles([str(tmp_path)])) == 2


def test_a_bundle_named_directly_is_taken(tmp_path):
    """A CI step that unpacks one artifact knows where it put it."""
    path = _write(tmp_path / "gw0" / "records.json", _payload())

    assert find_bundles([path]) == [path]


def test_the_same_bundle_named_twice_is_read_once(tmp_path):
    path = _write(tmp_path / "gw0" / "records.json", _payload())

    assert find_bundles([path, str(tmp_path)]) == [path]


def test_the_walk_yields_the_same_order_twice_running(tmp_path):
    for name in ("gw2", "gw0", "gw1"):
        _write(tmp_path / name / "records.json", _payload())

    assert find_bundles([str(tmp_path)]) == find_bundles([str(tmp_path)])


def test_a_folder_holding_no_bundles_yields_nothing(tmp_path):
    (tmp_path / "empty").mkdir()

    assert find_bundles([str(tmp_path)]) == []


def test_a_path_that_is_not_there_yields_nothing(tmp_path):
    assert find_bundles([str(tmp_path / "nope")]) == []
