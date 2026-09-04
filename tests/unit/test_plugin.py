import sys
import os

import pytest

from pytest_html_reporter import plugin
from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.junit import junit_path, junit_xpass
from pytest_html_reporter.shards import (
    _CI_RUN_VARIABLES,
    report_shard,
    report_shard_merge,
    report_shard_reset,
    report_shard_run,
)

myPath = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, myPath + '/../../')
from pytest_html_reporter.html_reporter import HTMLReporter


class _FakePluginManager:
    def hasplugin(self, name):
        return False


class _FakeConfig:
    """Just enough of pytest's Config for the option helpers and pytest_configure."""

    def __init__(self, options=None, ini=None):
        self._options = options or {}
        self._ini = ini or {}
        self.pluginmanager = _FakePluginManager()
        # pytest_configure resolves the path, the shard id and the run token
        # once and writes each of them back onto config.option, so that an
        # xdist worker handed a copy of the options answers what the
        # controller settled on. Without somewhere to write, the hook raises
        # an AttributeError long before it reaches what these tests are about.
        self.option = type("Options", (), {})()

    def getoption(self, name, default=None):
        return self._options.get(name, default)

    def getini(self, name):
        if name not in self._ini:
            raise ValueError(name)
        return self._ini[name]


class _RecordingParser:
    """A parser that only writes down what pytest_addoption asks it for."""

    def __init__(self):
        self.ini_keys = []

    def getgroup(self, name):
        return self

    def addoption(self, *names, **kwargs):
        pass

    def addini(self, name, **kwargs):
        self.ini_keys.append(name)


def _registered_ini_keys():
    """The ini keys pytest_addoption actually registers with pytest.

    Resolving an ini value is only half of the promise. The other half is that
    pytest knows the key at all, and a missing addini does not fail: getini
    raises ValueError, util._ini turns that into None, and the option silently
    reads as unset for everybody who set it in their pytest.ini rather than on
    the command line.
    """
    parser = _RecordingParser()
    plugin.pytest_addoption(parser)

    return parser.ini_keys


# Every environment variable a run token can be derived from, taken from the
# table itself rather than listed again here, so that a test cannot go on
# passing while the plugin learns about a CI system the fixture below has
# never heard of and leaves set.
_CI_VARIABLES = tuple(name for _, names in _CI_RUN_VARIABLES for name in names)


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


@pytest.fixture
def _no_ci_environment(monkeypatch):
    """Answer the token tests as if this process were nobody's CI job.

    This suite is itself run on CI, where several of these are already set, so
    a test about what the plugin reads out of the environment has to say what
    the whole environment is rather than only what it adds to it.
    """
    for name in _CI_VARIABLES:
        monkeypatch.delenv(name, raising=False)


def test_report_path():
    HTMLReporter.path = "."
    assert len(HTMLReporter.report_path.__get__(HTMLReporter)[0]) >= 5
    assert HTMLReporter.report_path.__get__(HTMLReporter)[1] == "pytest_html_report.html"

    HTMLReporter.path = "./report/test.html"
    assert len(HTMLReporter.report_path.__get__(HTMLReporter)[0]) >= 5
    assert HTMLReporter.report_path.__get__(HTMLReporter)[1] == "test.html"


# --------------------------------------------------------------------------
# the shard options
# --------------------------------------------------------------------------

def test_nothing_is_switched_on_when_nothing_asks_for_it():
    """Every one of these options is new, so the run that sets none of them
    has to behave exactly as it did before they existed."""
    config = _FakeConfig()

    assert report_shard(config) == ""
    assert report_shard_merge(config) is False
    assert report_shard_reset(config) is False
    assert junit_path(config) == ""
    assert junit_xpass(config) == "pass"


def test_the_shard_id_can_be_set_in_the_ini():
    assert "report_shard" in _registered_ini_keys()
    assert report_shard(_FakeConfig(ini={"report_shard": "1/4"})) == "1/4"


def test_the_shard_flag_beats_the_ini():
    config = _FakeConfig(options={"report_shard": "2/4"}, ini={"report_shard": "1/4"})
    assert report_shard(config) == "2/4"


def test_the_shard_merge_flag_can_be_set_in_the_ini():
    assert "report_shard_merge" in _registered_ini_keys()
    assert report_shard_merge(_FakeConfig(ini={"report_shard_merge": "true"})) is True


def test_the_shard_merge_flag_beats_an_ini_that_switches_it_off():
    """A store_true flag has no "off" to pass, so the only way it can lose to
    an ini key is by not being asked about at all."""
    config = _FakeConfig(options={"report_shard_merge": True}, ini={"report_shard_merge": "no"})
    assert report_shard_merge(config) is True


def test_the_shard_run_token_can_be_set_in_the_ini():
    assert "report_shard_run" in _registered_ini_keys()
    assert report_shard_run(_FakeConfig(ini={"report_shard_run": "nightly-41"})) == "nightly-41"


def test_the_shard_run_token_flag_beats_the_ini():
    config = _FakeConfig(options={"report_shard_run": "rerun-2"}, ini={"report_shard_run": "nightly-41"})
    assert report_shard_run(config) == "rerun-2"


def test_the_shard_reset_flag_can_be_set_in_the_ini():
    assert "report_shard_reset" in _registered_ini_keys()
    assert report_shard_reset(_FakeConfig(ini={"report_shard_reset": "yes"})) is True


def test_the_shard_reset_flag_beats_an_ini_that_switches_it_off():
    config = _FakeConfig(options={"report_shard_reset": True}, ini={"report_shard_reset": "off"})
    assert report_shard_reset(config) is True


# --------------------------------------------------------------------------
# the junit options
# --------------------------------------------------------------------------

def test_the_junit_path_can_be_set_in_the_ini():
    assert "report_junit" in _registered_ini_keys()
    assert junit_path(_FakeConfig(ini={"report_junit": "./reports/junit.xml"})) == "./reports/junit.xml"


def test_the_junit_path_flag_beats_the_ini():
    config = _FakeConfig(options={"report_junit": "./cli.xml"}, ini={"report_junit": "./ini.xml"})
    assert junit_path(config) == "./cli.xml"


def test_the_junit_xpass_mode_can_be_set_in_the_ini():
    assert "report_junit_xpass" in _registered_ini_keys()
    assert junit_xpass(_FakeConfig(ini={"report_junit_xpass": "fail"})) == "fail"


def test_the_junit_xpass_flag_beats_the_ini():
    config = _FakeConfig(options={"report_junit_xpass": "skip"}, ini={"report_junit_xpass": "fail"})
    assert junit_xpass(config) == "skip"


# --------------------------------------------------------------------------
# what a run is refused for
# --------------------------------------------------------------------------

def test_shard_merge_without_a_shard_is_a_usage_error():
    """There is nothing sensible to do with the ask: the leg that merges is
    the last leg of the run, and a process that is not a shard has no records
    of its own to add to what it would be merging."""
    config = _FakeConfig(options={"report_shard_merge": True})

    with pytest.raises(pytest.UsageError):
        plugin.pytest_configure(config)


def test_a_shard_id_that_sanitises_to_nothing_is_a_usage_error():
    """A value of "///" is not empty, but nothing of it survives being made
    fit for a directory name, and a shard whose id came out empty would write
    over the report base itself."""
    config = _FakeConfig(options={"report_shard": "///"})

    with pytest.raises(pytest.UsageError):
        plugin.pytest_configure(config)


def test_an_unknown_junit_xpass_value_is_a_usage_error():
    """The flag itself is answered by argparse's choices, so this is the ini
    half - where nothing gates the value - and the run stops rather than
    quietly handing back the default the team set the key to get away from."""
    with pytest.raises(pytest.UsageError):
        junit_xpass(_FakeConfig(ini={"report_junit_xpass": "maybe"}))


# --------------------------------------------------------------------------
# which run a leg belongs to
# --------------------------------------------------------------------------

def test_the_run_token_is_taken_from_the_ci_environment(_no_ci_environment, monkeypatch):
    """Nobody types --report-shard-run on a matrix, so the everyday answer has
    to come from the CI system itself; the attempt travels with the id because
    a re-run of a matrix must not answer the token the first attempt's bundles
    are already stamped with."""
    monkeypatch.setenv("GITHUB_RUN_ID", "41")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "2")

    assert report_shard_run(_FakeConfig()) == "github:41-2"


def test_the_run_token_flag_beats_the_ci_environment(_no_ci_environment, monkeypatch):
    monkeypatch.setenv("GITHUB_RUN_ID", "41")

    assert report_shard_run(_FakeConfig(options={"report_shard_run": "nightly"})) == "nightly"


def test_the_run_token_ini_beats_the_ci_environment(_no_ci_environment, monkeypatch):
    monkeypatch.setenv("GITHUB_RUN_ID", "41")

    assert report_shard_run(_FakeConfig(ini={"report_shard_run": "nightly"})) == "nightly"


def test_the_run_token_is_empty_off_a_ci_system(_no_ci_environment):
    """An empty token is not a failure: a merging leg without one merges every
    bundle beside it, which is what --report-shard-reset is for."""
    assert report_shard_run(_FakeConfig()) == ""
