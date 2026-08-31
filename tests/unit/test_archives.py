"""Cover how long archived builds are kept.

--archive-count keeps a number of builds; --archive-days and --archive-since
keep a stretch of time. A run on a schedule wants the second kind: "the last 30
days" survives a change to how often the run fires, and a build count does not.
Nothing set keeps every build for ever, which is what makes a months-old report
slow to open (#223).
"""

import os
import time

import pytest

from pytest_html_reporter.html_reporter import HTMLReporter
from pytest_html_reporter.util import (
    archive_count,
    archive_cutoff,
    archive_days,
    archive_since,
    archive_timestamp,
    expired_archives,
)


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


DAY = 86400.0


def _archive(directory, age_days, name=None):
    """An archived build that ran `age_days` ago, named the way the plugin names it."""
    stamp = time.time() - age_days * DAY
    path = os.path.join(str(directory), name or ("output_%s.json" % stamp))
    with open(path, "w") as handle:
        handle.write("{}")

    return path


def _reporter(path, count="", **options):
    return HTMLReporter(str(path), count, _FakeConfig(options=options))


# --------------------------------------------------------------------------
# resolving the options
# --------------------------------------------------------------------------

def test_archive_count_defaults_to_no_limit():
    assert archive_count(_FakeConfig()) == ""


def test_archive_count_from_ini():
    assert archive_count(_FakeConfig(ini={"archive_count": "7"})) == "7"


def test_archive_count_cli_beats_ini():
    config = _FakeConfig(options={"archive_count": "3"}, ini={"archive_count": "7"})
    assert archive_count(config) == "3"


def test_archive_count_keeps_zero_apart_from_unset():
    assert archive_count(_FakeConfig(options={"archive_count": "0"})) == "0"


def test_archive_count_rejects_nonsense():
    with pytest.raises(pytest.UsageError):
        archive_count(_FakeConfig(options={"archive_count": "a week"}))


def test_archive_count_rejects_a_negative_count():
    with pytest.raises(pytest.UsageError):
        archive_count(_FakeConfig(options={"archive_count": "-1"}))


def test_archive_days_defaults_to_no_limit():
    assert archive_days(_FakeConfig()) is None


def test_archive_days_from_ini():
    assert archive_days(_FakeConfig(ini={"archive_days": "30"})) == 30.0


def test_archive_days_cli_beats_ini():
    config = _FakeConfig(options={"archive_days": "7"}, ini={"archive_days": "30"})
    assert archive_days(config) == 7.0


def test_archive_days_takes_a_fraction_of_a_day():
    assert archive_days(_FakeConfig(options={"archive_days": "0.5"})) == 0.5


def test_archive_days_rejects_nonsense():
    with pytest.raises(pytest.UsageError):
        archive_days(_FakeConfig(options={"archive_days": "a month"}))


def test_archive_days_rejects_a_negative_age():
    with pytest.raises(pytest.UsageError):
        archive_days(_FakeConfig(options={"archive_days": "-3"}))


def test_archive_since_defaults_to_no_cutoff():
    assert archive_since(_FakeConfig()) is None


def test_archive_since_reads_a_date_as_midnight():
    from datetime import datetime

    cutoff = archive_since(_FakeConfig(options={"archive_since": "2026-06-01"}))
    assert cutoff == datetime(2026, 6, 1).timestamp()


def test_archive_since_reads_a_date_and_a_time():
    from datetime import datetime

    cutoff = archive_since(_FakeConfig(options={"archive_since": "2026-06-01 09:30"}))
    assert cutoff == datetime(2026, 6, 1, 9, 30).timestamp()


def test_archive_since_from_ini():
    from datetime import datetime

    cutoff = archive_since(_FakeConfig(ini={"archive_since": "2026-06-01"}))
    assert cutoff == datetime(2026, 6, 1).timestamp()


def test_archive_since_rejects_nonsense():
    with pytest.raises(pytest.UsageError):
        archive_since(_FakeConfig(options={"archive_since": "01/06/2026"}))


# --------------------------------------------------------------------------
# the cutoff the two age limits make between them
# --------------------------------------------------------------------------

def test_no_age_limit_is_no_cutoff():
    assert archive_cutoff() is None


def test_days_cuts_back_from_now():
    assert archive_cutoff(days=7, now=1000 * DAY) == 993 * DAY


def test_since_is_the_cutoff_on_its_own():
    assert archive_cutoff(since=500 * DAY, now=1000 * DAY) == 500 * DAY


def test_the_two_age_limits_take_the_stricter_of_the_pair():
    # --archive-days 7 reaches back further than --archive-since does, so the
    # date wins; neither limit can widen the other.
    assert archive_cutoff(days=7, since=997 * DAY, now=1000 * DAY) == 997 * DAY
    assert archive_cutoff(days=1, since=997 * DAY, now=1000 * DAY) == 999 * DAY


# --------------------------------------------------------------------------
# reading a build's age off its name
# --------------------------------------------------------------------------

def test_archive_timestamp_reads_the_name():
    assert archive_timestamp("/tmp/archive/output_1788023855.926659.json") == 1788023855.926659


def test_archive_timestamp_ignores_the_mtime_of_a_named_file(tmp_path):
    path = _archive(tmp_path, age_days=0, name="output_1788023855.926659.json")
    os.utime(path, (0, 0))

    assert archive_timestamp(path) == 1788023855.926659


def test_archive_timestamp_falls_back_to_the_mtime(tmp_path):
    path = _archive(tmp_path, age_days=0, name="output.json")
    os.utime(path, (1500, 1500))

    assert archive_timestamp(path) == 1500


# --------------------------------------------------------------------------
# which builds the limits drop
# --------------------------------------------------------------------------

def test_nothing_set_keeps_every_build(tmp_path):
    paths = [_archive(tmp_path, age_days=age) for age in (1, 40, 90)]

    assert expired_archives(paths) == []


def test_a_count_keeps_the_newest(tmp_path):
    old, middle, new = (_archive(tmp_path, age_days=age) for age in (90, 40, 1))

    assert expired_archives([new, old, middle], keep=2) == [old]


def test_a_count_of_zero_keeps_nothing(tmp_path):
    paths = [_archive(tmp_path, age_days=age) for age in (1, 40)]

    assert sorted(expired_archives(paths, keep=0)) == sorted(paths)


def test_a_count_larger_than_the_history_drops_nothing(tmp_path):
    paths = [_archive(tmp_path, age_days=age) for age in (1, 40)]

    assert expired_archives(paths, keep=10) == []


def test_a_cutoff_drops_what_is_older_than_it(tmp_path):
    old, middle, new = (_archive(tmp_path, age_days=age) for age in (90, 40, 1))
    cutoff = time.time() - 30 * DAY

    assert sorted(expired_archives([new, old, middle], cutoff=cutoff)) == sorted([middle, old])


def test_the_limits_intersect(tmp_path):
    # Four builds inside the cutoff, but the count only keeps two of them.
    paths = [_archive(tmp_path, age_days=age) for age in (1, 2, 3, 4, 90)]
    cutoff = time.time() - 30 * DAY

    expired = expired_archives(paths, keep=2, cutoff=cutoff)

    assert sorted(expired) == sorted([paths[4], paths[3], paths[2]])


def test_expired_archives_are_returned_oldest_first(tmp_path):
    paths = [_archive(tmp_path, age_days=age) for age in (10, 90, 40)]

    assert expired_archives(paths, keep=0) == [paths[1], paths[2], paths[0]]


# --------------------------------------------------------------------------
# the reporter applying them to the folder
# --------------------------------------------------------------------------

def _archive_dir(base):
    directory = base / "archive"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _remaining(directory):
    return sorted(os.listdir(str(directory)))


def test_no_limit_leaves_the_folder_alone(tmp_path):
    directory = _archive_dir(tmp_path)
    for age in (1, 90, 200):
        _archive(directory, age_days=age)

    _reporter(tmp_path).remove_old_archives()

    assert len(_remaining(directory)) == 3


def test_a_count_keeps_room_for_the_build_being_reported(tmp_path):
    directory = _archive_dir(tmp_path)
    kept = _archive(directory, age_days=1)
    for age in (40, 90):
        _archive(directory, age_days=age)

    # --archive-count 2: this run is one of the two builds shown, so one
    # archived build is kept beside it.
    _reporter(tmp_path, count="2").remove_old_archives()

    assert _remaining(directory) == [os.path.basename(kept)]


def test_a_count_of_zero_removes_the_folder(tmp_path):
    directory = _archive_dir(tmp_path)
    _archive(directory, age_days=1)

    _reporter(tmp_path, count="0").remove_old_archives()

    assert not os.path.isdir(str(directory))


def test_archive_days_drops_the_builds_that_are_older(tmp_path):
    directory = _archive_dir(tmp_path)
    kept = [_archive(directory, age_days=age) for age in (1, 6)]
    for age in (8, 40, 200):
        _archive(directory, age_days=age)

    _reporter(tmp_path, archive_days="7").remove_old_archives()

    assert _remaining(directory) == sorted(os.path.basename(path) for path in kept)


def test_archive_since_drops_the_builds_from_before_the_date(tmp_path):
    from datetime import datetime, timedelta

    directory = _archive_dir(tmp_path)
    kept = _archive(directory, age_days=1)
    _archive(directory, age_days=40)

    cutoff = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d")
    _reporter(tmp_path, archive_since=cutoff).remove_old_archives()

    assert _remaining(directory) == [os.path.basename(kept)]


def test_an_age_limit_and_a_count_intersect(tmp_path):
    directory = _archive_dir(tmp_path)
    kept = _archive(directory, age_days=1)
    for age in (2, 3, 90):
        _archive(directory, age_days=age)

    _reporter(tmp_path, count="2", archive_days="7").remove_old_archives()

    assert _remaining(directory) == [os.path.basename(kept)]


def test_the_folder_is_found_when_the_path_names_the_html_file(tmp_path):
    # The archive sits beside the report, in the folder - not under a path
    # made of the html file's own name.
    directory = _archive_dir(tmp_path)
    kept = _archive(directory, age_days=1)
    _archive(directory, age_days=90)

    _reporter(tmp_path / "report.html", archive_days="7").remove_old_archives()

    assert _remaining(directory) == [os.path.basename(kept)]


def test_retention_leaves_anything_that_is_not_an_archive_alone(tmp_path):
    directory = _archive_dir(tmp_path)
    _archive(directory, age_days=90)
    (directory / "notes.txt").write_text("kept")

    _reporter(tmp_path, count="1").remove_old_archives()

    assert _remaining(directory) == ["notes.txt"]


def test_retention_survives_an_empty_folder(tmp_path):
    directory = _archive_dir(tmp_path)

    _reporter(tmp_path, archive_days="7").remove_old_archives()

    assert _remaining(directory) == []


def test_retention_survives_a_folder_that_was_never_written(tmp_path):
    _reporter(tmp_path, archive_days="7").remove_old_archives()

    assert not os.path.isdir(str(tmp_path / "archive"))
