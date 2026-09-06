"""Named configuration profiles - one name for a set of report settings.

A profile is not a new way to report on anything. It is a new way to *say* the
same options, so almost everything worth pinning down here is about agreement:
that a profile's value lands on the very option the flag lands on, that the
layers above and below it win in the documented order, and that a profile
which says something the command line would have refused fails the run rather
than being quietly dropped - because a run that quietly kept every log because
somebody wrote ``logs = "fail"`` is the exact failure profiles exist to stop.

The layers, highest first, and each of them has a test below:

    the command line > the environment > the profile > the shared table >
    the plain ini key > the option's own default
"""

import os
import subprocess
import sys
import textwrap

import pytest

from pytest_html_reporter import plugin, profiles
from pytest_html_reporter.coverage_report import coverage_limit, coverage_mode
from pytest_html_reporter.junit import junit_path
from pytest_html_reporter.profiles import (
    KEYS,
    NO_PROFILE,
    ProfileError,
    apply_profile,
    environment_values,
    load_sources,
    lookup,
    requested_name,
    resolve,
)
from pytest_html_reporter.report_opener import open_mode
from pytest_html_reporter.shards import report_shard_merge
from pytest_html_reporter.util import (
    build_info,
    link_patterns,
    report_logs_mode,
    report_step_limit,
)


class _Options(object):
    """config.option, holding whatever pytest_addoption's defaults would."""

    def __init__(self, given=None):
        for key in KEYS:
            # A fresh list per instance: the option helpers merge into these,
            # and a shared default would leak one test's entries into the next.
            default = list(key.default) if isinstance(key.default, list) else key.default
            setattr(self, key.dest, default)

        self.report_profile = ""

        for name, value in (given or {}).items():
            setattr(self, name, value)


class _FakeConfig:
    """Just enough of pytest's Config for the option helpers and apply_profile."""

    def __init__(self, rootpath, options=None, ini=None, inipath=None):
        self.rootpath = str(rootpath)
        self.rootdir = self.rootpath
        self.inipath = inipath
        self.option = _Options(options)
        self._ini = ini or {}

    def getoption(self, name, default=None):
        value = getattr(self.option, name, default)

        return default if value is None else value

    def getini(self, name):
        if name not in self._ini:
            raise ValueError(name)
        return self._ini[name]


def _project(tmp_path, pyproject=None, ini=None, ini_name="pytest.ini"):
    """Write a project's config files and hand back a config that reads them."""
    if pyproject is not None:
        (tmp_path / "pyproject.toml").write_text(textwrap.dedent(pyproject).lstrip())

    inipath = None
    if ini is not None:
        inipath = tmp_path / ini_name
        inipath.write_text(textwrap.dedent(ini).lstrip())

    return inipath


def _config(tmp_path, pyproject=None, ini=None, options=None, ini_keys=None,
            ini_name="pytest.ini"):
    inipath = _project(tmp_path, pyproject, ini, ini_name)

    return _FakeConfig(tmp_path, options=options, ini=ini_keys, inipath=inipath)


SAMPLE_TOML = """
    [tool.pytest-html-reporter.profiles.local]
    open = "auto"
    logs = "all"
    screenshots = "failed"
    archive_count = 10

    [tool.pytest-html-reporter.profiles.ci]
    open = "none"
    logs = "failed"
    screenshots = "failed"
    junit = "report/junit.xml"
    archive_days = 30
"""


@pytest.fixture(autouse=True)
def _no_profile_environment(monkeypatch):
    """No PYTEST_HTML_REPORTER_* left over from whoever started this suite.

    They are an override layer by design, so one exported in the shell that
    ran pytest would sit above every profile these tests write and quietly
    decide half of them.
    """
    for name in list(os.environ):
        if name.startswith(profiles.ENV_PREFIX):
            monkeypatch.delenv(name, raising=False)


# --------------------------------------------------------------------------
# the table of settings, against the flags it mirrors
# --------------------------------------------------------------------------

class _RecordingParser:
    """A parser that only writes down what pytest_addoption asks it for."""

    def __init__(self):
        self.options = {}
        self.ini_keys = []

    def getgroup(self, name):
        return self

    def addoption(self, *names, **kwargs):
        self.options[kwargs["dest"]] = kwargs

    def addini(self, name, **kwargs):
        self.ini_keys.append(name)


def _registered_options():
    parser = _RecordingParser()
    plugin.pytest_addoption(parser)

    return parser


def test_every_profile_key_names_an_option_that_exists():
    """A key whose dest nothing parses into is a setting that does nothing.

    It would be written onto config.option and read by no one, and the only
    symptom is a profile that appears to be ignored.
    """
    registered = _registered_options().options

    missing = [key.name for key in KEYS if key.dest not in registered]

    assert missing == []


def test_every_profile_key_carries_the_default_its_flag_was_registered_with():
    """The drift this guards against is silent and goes both ways.

    "Did the command line say this?" is answered by comparing the option
    against the default it would hold if nobody had. A default that drifts
    from the flag's own makes a profile either stop overriding anything - the
    option never looks unset - or start overriding a value somebody typed.
    """
    registered = _registered_options().options

    mismatched = [
        (key.name, key.default, registered[key.dest].get("default"))
        for key in KEYS
        if key.dest in registered and registered[key.dest].get("default") != key.default
    ]

    assert mismatched == []


def test_every_choice_key_offers_exactly_the_choices_its_flag_does():
    """Same drift, one layer down.

    argparse refuses a bad choice on the command line and cannot see one in a
    profile, so the profile checks the value itself - against a list that has
    to stay the flag's list, or a profile starts refusing something the flag
    accepts.
    """
    registered = _registered_options().options

    mismatched = [
        (key.name, key.choices, tuple(registered[key.dest].get("choices") or ()))
        for key in KEYS
        if key.kind == "choice"
        and tuple(registered[key.dest].get("choices") or ()) != key.choices
    ]

    assert mismatched == []


def test_a_flag_and_its_ini_key_both_reach_the_same_setting():
    """`logs` and `report_logs` are one setting under two spellings.

    A profile is very often a block of ini keys moved under a name, so the ini
    spelling has to work; the short one is what the documented examples use.
    """
    assert lookup("logs") is lookup("report_logs")
    assert lookup("REPORT-LOGS") is lookup("logs")
    assert lookup("nonsense") is None


# --------------------------------------------------------------------------
# reading the files
# --------------------------------------------------------------------------

def test_a_toml_profile_lands_on_the_options_the_flags_land_on(tmp_path):
    """The whole mechanism, end to end and in one test.

    Every helper below reads its option exactly the way it did before profiles
    existed. That they answer the ci profile is the proof that nothing else in
    the tree needs to know profiles are there.
    """
    config = _config(tmp_path, pyproject=SAMPLE_TOML,
                     options={"report_profile": "ci"})

    assert apply_profile(config, environ={}) == "ci"

    assert open_mode(config) == "none"
    assert report_logs_mode(config) == "failed"
    assert junit_path(config) == "report/junit.xml"
    assert config.getoption("archive_days") == "30"


def test_an_ini_profile_is_read_from_the_file_pytest_chose(tmp_path):
    """pytest.ini gets profiles too, as a section per name.

    A repository with a pytest.ini and no pyproject.toml should not have to
    grow one to say "ci" in a single word.
    """
    config = _config(tmp_path, ini="""
        [pytest]
        addopts = -q

        [pytest-html-reporter.profiles.ci]
        open = none
        logs = failed
        junit = report/junit.xml
    """, options={"report_profile": "ci"})

    apply_profile(config, environ={})

    assert open_mode(config) == "none"
    assert report_logs_mode(config) == "failed"
    assert junit_path(config) == "report/junit.xml"


def test_a_dated_path_in_an_ini_profile_survives_being_read(tmp_path):
    """The documented html_report value has a % in every segment of it.

    ConfigParser's default interpolation raises on those, so reading these
    sections with it would fail every project that writes a dated report path
    - and fail it at configure time, before a single test ran.
    """
    config = _config(tmp_path, ini="""
        [pytest-html-reporter.profiles.dated]
        path = ./reports/%Y%m%d/report_%H%M.html
    """, options={"report_profile": "dated"})

    apply_profile(config, environ={})

    assert config.getoption("path") == "./reports/%Y%m%d/report_%H%M.html"


def test_the_ini_file_wins_a_name_the_toml_file_also_defines(tmp_path):
    """And wins it whole, rather than key by key.

    The ini file is the one pytest itself picked as this run's configuration.
    Half a profile from each file would be a shape nobody composed, and which
    half came from where would depend on which file pytest happened to pick.
    """
    config = _config(tmp_path, pyproject="""
        [tool.pytest-html-reporter.profiles.ci]
        open = "auto"
        logs = "all"
        junit = "from-toml.xml"
    """, ini="""
        [pytest-html-reporter.profiles.ci]
        open = none
    """, options={"report_profile": "ci"})

    apply_profile(config, environ={})

    assert open_mode(config) == "none"
    # Not "all", and not "from-toml.xml": the toml profile is not consulted at
    # all for a name the ini file already answered.
    assert report_logs_mode(config) == "all"
    assert junit_path(config) == ""


def test_both_spellings_of_the_tool_table_are_read(tmp_path):
    """The hyphen is the real name; the underscore is what people type."""
    config = _config(tmp_path, pyproject="""
        [tool.pytest_html_reporter.profiles.ci]
        open = "none"
    """, options={"report_profile": "ci"})

    apply_profile(config, environ={})

    assert open_mode(config) == "none"


def test_a_project_with_no_config_files_at_all_is_left_alone(tmp_path):
    """The run everybody has: no profile asked for, nothing to read."""
    config = _config(tmp_path)

    assert apply_profile(config, environ={}) == ""
    assert report_logs_mode(config) == "all"
    assert open_mode(config) == "auto"


# --------------------------------------------------------------------------
# which profile, and the layers around it
# --------------------------------------------------------------------------

def test_the_command_line_beats_the_environment_which_beats_the_ini_key(tmp_path):
    """Three ways to name a profile, in the order they are documented in."""
    config = _config(tmp_path, pyproject=SAMPLE_TOML,
                     options={"report_profile": "ci"},
                     ini_keys={"report_profile": "local"})

    sources = load_sources(config)

    assert requested_name(config, sources, {"PYTEST_HTML_REPORTER_PROFILE": "local"}) == "ci"

    config.option.report_profile = ""
    assert requested_name(config, sources, {"PYTEST_HTML_REPORTER_PROFILE": "local"}) == "local"

    assert requested_name(config, sources, {}) == "local"


def test_the_tool_table_can_pin_the_profile_a_bare_pytest_run_uses(tmp_path):
    """So that `pytest` on its own is already the shape this repo agreed on."""
    config = _config(tmp_path, pyproject="""
        [tool.pytest-html-reporter]
        profile = "ci"

        [tool.pytest-html-reporter.profiles.ci]
        open = "none"
    """)

    assert apply_profile(config, environ={}) == "ci"
    assert open_mode(config) == "none"


def test_none_uses_no_profile_however_the_default_was_pinned(tmp_path):
    """The way out of a pinned default, for the one run that wants none of it.

    Spelled 'none' rather than as an empty --report-profile= because argparse
    cannot tell an empty value from an option nobody passed.
    """
    config = _config(tmp_path, pyproject="""
        [tool.pytest-html-reporter]
        profile = "ci"

        [tool.pytest-html-reporter.profiles.ci]
        open = "none"
        logs = "failed"
    """, options={"report_profile": NO_PROFILE})

    assert apply_profile(config, environ={}) == ""
    assert open_mode(config) == "auto"
    assert report_logs_mode(config) == "all"


def test_a_profile_cannot_be_called_none(tmp_path):
    """Because that word already means "no profile" on the command line."""
    config = _config(tmp_path, pyproject="""
        [tool.pytest-html-reporter.profiles.none]
        open = "auto"
    """, options={"report_profile": "none"})

    with pytest.raises(ProfileError) as error:
        apply_profile(config, environ={})

    assert "reserved" in str(error.value)


def test_a_profile_found_in_another_case_is_reported_as_it_was_written(tmp_path):
    """--report-profile=CI should not fail over a capital.

    And what the report then shows is the name in the file, not the one typed:
    the file is where somebody goes to read what the run was shaped by.
    """
    config = _config(tmp_path, pyproject=SAMPLE_TOML,
                     options={"report_profile": "CI"})

    assert apply_profile(config, environ={}) == "ci"
    assert config.option.report_profile == "ci"


def test_the_settled_profile_name_is_written_back_onto_the_options(tmp_path):
    """For the same reason the resolved path and shard id are.

    An xdist worker is handed a copy of these options rather than a chance to
    work the answer out again, and the Environment panel reads the name from
    here to say which shape produced the report.
    """
    config = _config(tmp_path, pyproject=SAMPLE_TOML,
                     ini_keys={"report_profile": "local"})

    apply_profile(config, environ={})

    assert config.option.report_profile == "local"


# --------------------------------------------------------------------------
# precedence, setting by setting
# --------------------------------------------------------------------------

def test_a_flag_on_the_command_line_beats_the_profile(tmp_path):
    """Whoever typed the flag meant this run, and this run is the smaller scope.

    addopts counts as typed, deliberately: it is a line somebody wrote for this
    repository about every run of it, and a profile quietly overriding it would
    make two config files disagree with nothing on the page saying so.
    """
    config = _config(tmp_path, pyproject=SAMPLE_TOML,
                     options={"report_profile": "ci", "report_logs": "all"})

    apply_profile(config, environ={})

    assert report_logs_mode(config) == "all"
    # The settings the command line said nothing about still come from the
    # profile - it is overridden key by key, not discarded whole.
    assert open_mode(config) == "none"


def test_an_environment_variable_beats_the_profile(tmp_path):
    """What an override is for: one job, one machine, one debugging session.

    Above the profile because the profile is what the repository committed and
    the variable is somebody saying otherwise without editing a file everybody
    else reads.
    """
    config = _config(tmp_path, pyproject=SAMPLE_TOML,
                     options={"report_profile": "ci"})

    apply_profile(config, environ={"PYTEST_HTML_REPORTER_LOGS": "all"})

    assert report_logs_mode(config) == "all"
    assert open_mode(config) == "none"


def test_the_profile_beats_the_plain_ini_key(tmp_path):
    """Because it is the more specific answer, and the selected one."""
    config = _config(tmp_path, pyproject=SAMPLE_TOML,
                     options={"report_profile": "ci"},
                     ini_keys={"report_logs": "all", "report_open": "always"})

    apply_profile(config, environ={})

    assert report_logs_mode(config) == "failed"
    assert open_mode(config) == "none"


def test_a_setting_no_layer_mentions_keeps_its_ini_value(tmp_path):
    """A profile is a set of overrides, not a replacement configuration.

    Everything the profile is silent about goes on being answered the way it
    was before profiles existed, which is what makes adopting one cheap.
    """
    config = _config(tmp_path, pyproject=SAMPLE_TOML,
                     options={"report_profile": "ci"},
                     ini_keys={"report_step_limit": "25"})

    apply_profile(config, environ={})

    assert report_step_limit(config) == 25


def test_the_shared_table_is_what_every_profile_starts_from(tmp_path):
    """The reuse half of reusable profiles.

    What is true of every shape of this run - the title, the coverage tab -
    is written once, and a profile says only what it changes.
    """
    config = _config(tmp_path, pyproject="""
        [tool.pytest-html-reporter]
        title = "PAYMENTS"
        coverage = "auto"
        coverage_limit = 40

        [tool.pytest-html-reporter.profiles.ci]
        coverage_limit = 500
    """, options={"report_profile": "ci"})

    apply_profile(config, environ={})

    assert config.getoption("title") == "PAYMENTS"
    assert coverage_mode(config) == "auto"
    assert coverage_limit(config) == 500


def test_the_shared_table_applies_to_a_run_that_names_no_profile(tmp_path):
    """Otherwise it would be a layer that only sometimes exists.

    A base that switched itself off when nobody passed --report-profile would
    make a bare `pytest` and `pytest --report-profile=ci` differ in ways
    neither file mentions.
    """
    config = _config(tmp_path, pyproject="""
        [tool.pytest-html-reporter]
        logs = "none"
    """)

    assert apply_profile(config, environ={}) == ""
    assert report_logs_mode(config) == "none"


def test_an_ini_file_can_hold_the_shared_table_too(tmp_path):
    """Same layer, same name, in the file that project happens to keep."""
    config = _config(tmp_path, ini="""
        [pytest-html-reporter]
        profile = ci
        title = PAYMENTS

        [pytest-html-reporter.profiles.ci]
        open = none
    """)

    assert apply_profile(config, environ={}) == "ci"
    assert config.getoption("title") == "PAYMENTS"
    assert open_mode(config) == "none"


# --------------------------------------------------------------------------
# the lists, which add up rather than replace
# --------------------------------------------------------------------------

def test_a_profiles_list_entries_are_added_to_the_ones_already_set(tmp_path):
    """build_info, report_link and report_link_pattern all work this way.

    They are documented as adding to the ini file's rather than replacing it,
    and a profile is one more place the same list is written from. Replacing
    would mean a profile that wants to add one row has to restate every row
    the repository already had.
    """
    config = _config(tmp_path, pyproject="""
        [tool.pytest-html-reporter]
        build_info = ["team=payments"]

        [tool.pytest-html-reporter.profiles.ci]
        build_info = ["lane=ci"]
    """, options={"report_profile": "ci", "build_info": ["run=7"]},
        ini_keys={"build_info": ["branch=main"]})

    apply_profile(config, environ={})

    assert build_info(config) == [
        ("run", "7"), ("team", "payments"), ("lane", "ci"), ("branch", "main")]


def test_a_toml_table_is_the_natural_way_to_write_link_patterns(tmp_path):
    """`jira = "..."` under a table, rather than a list of "jira=..." strings.

    It is what anybody writing TOML reaches for first, and the ini file's
    indented block is what anybody writing ini reaches for; both mean the same
    MARKER=URL pairs.
    """
    config = _config(tmp_path, pyproject="""
        [tool.pytest-html-reporter.profiles.ci.link_patterns]
        jira = "https://acme.atlassian.net/browse/{}"
    """, options={"report_profile": "ci"})

    apply_profile(config, environ={})

    assert link_patterns(config) == {
        "jira": "https://acme.atlassian.net/browse/{}"}


def test_an_ini_profiles_indented_block_is_read_as_one_entry_per_line(tmp_path):
    config = _config(tmp_path, ini="""
        [pytest-html-reporter.profiles.ci]
        build_info =
            team=payments
            lane=ci
    """, options={"report_profile": "ci"})

    apply_profile(config, environ={})

    assert build_info(config) == [("team", "payments"), ("lane", "ci")]


def test_a_list_can_be_overridden_from_the_environment_a_line_at_a_time(tmp_path):
    """One commit sha per job is the case this exists for."""
    config = _config(tmp_path, pyproject=SAMPLE_TOML,
                     options={"report_profile": "ci"})

    apply_profile(config, environ={
        "PYTEST_HTML_REPORTER_BUILD_INFO": "commit=abc123\nlane=ci"})

    assert build_info(config) == [("commit", "abc123"), ("lane", "ci")]


# --------------------------------------------------------------------------
# the switches, which a profile can turn on
# --------------------------------------------------------------------------

def test_a_switch_a_profile_turns_on_reads_as_on(tmp_path):
    config = _config(tmp_path, pyproject="""
        [tool.pytest-html-reporter.profiles.ci]
        shard_merge = true
    """, options={"report_profile": "ci"})

    apply_profile(config, environ={})

    assert report_shard_merge(config) is True


def test_a_switch_takes_the_words_an_ini_file_would_have_used(tmp_path):
    """An ini profile has no booleans, only the text somebody typed."""
    config = _config(tmp_path, ini="""
        [pytest-html-reporter.profiles.ci]
        packages = yes
        shard_reset = off
    """, options={"report_profile": "ci"})

    apply_profile(config, environ={})

    assert config.option.report_packages is True
    assert config.option.report_shard_reset is False


def test_a_switch_that_is_neither_fails_the_run(tmp_path):
    config = _config(tmp_path, pyproject="""
        [tool.pytest-html-reporter.profiles.ci]
        packages = "sometimes"
    """, options={"report_profile": "ci"})

    with pytest.raises(ProfileError) as error:
        apply_profile(config, environ={})

    assert "true or false" in str(error.value)


# --------------------------------------------------------------------------
# what a profile is not allowed to say
# --------------------------------------------------------------------------

def test_an_unknown_profile_names_the_ones_there_are(tmp_path):
    """The only discovery path that exists at the moment somebody needs it."""
    config = _config(tmp_path, pyproject=SAMPLE_TOML,
                     options={"report_profile": "prod"})

    with pytest.raises(ProfileError) as error:
        apply_profile(config, environ={})

    assert "Defined: ci, local" in str(error.value)


def test_a_near_miss_is_offered_the_name_it_nearly_typed(tmp_path):
    config = _config(tmp_path, pyproject=SAMPLE_TOML,
                     options={"report_profile": "loca"})

    with pytest.raises(ProfileError) as error:
        apply_profile(config, environ={})

    assert "Did you mean 'local'?" in str(error.value)


def test_asking_for_a_profile_where_none_are_defined_says_how_to_write_one(tmp_path):
    config = _config(tmp_path, options={"report_profile": "ci"})

    with pytest.raises(ProfileError) as error:
        apply_profile(config, environ={})

    assert "no profiles are defined" in str(error.value)
    assert "[tool.pytest-html-reporter.profiles.ci]" in str(error.value)


def test_an_unknown_setting_in_a_profile_fails_the_run_and_names_the_file(tmp_path):
    """A typo'd key is a setting that silently does nothing, which is worse.

    Naming the file matters because the run that fails may be a CI job and the
    file may be one of two that could have held it.
    """
    config = _config(tmp_path, pyproject="""
        [tool.pytest-html-reporter.profiles.ci]
        logz = "failed"
    """, options={"report_profile": "ci"})

    with pytest.raises(ProfileError) as error:
        apply_profile(config, environ={})

    message = str(error.value)
    assert "unknown setting 'logz'" in message
    assert "Did you mean 'logs'?" in message
    assert "pyproject.toml" in message


def test_an_unknown_setting_with_no_near_miss_lists_what_there_is(tmp_path):
    config = _config(tmp_path, pyproject="""
        [tool.pytest-html-reporter.profiles.ci]
        wibble = "failed"
    """, options={"report_profile": "ci"})

    with pytest.raises(ProfileError) as error:
        apply_profile(config, environ={})

    assert "Known settings:" in str(error.value)


def test_a_value_the_flag_would_have_refused_fails_rather_than_being_dropped(tmp_path):
    """The failure this whole feature exists to prevent, in one test.

    argparse refuses `--report-logs=fail` outright. A profile bypasses argparse
    entirely, so without this check the value would land on the option, fail
    the helper's own `in LOG_MODES` test, and fall through to 'all' - a run
    that kept every log because somebody typed six letters instead of seven.
    """
    config = _config(tmp_path, pyproject="""
        [tool.pytest-html-reporter.profiles.ci]
        logs = "fail"
    """, options={"report_profile": "ci"})

    with pytest.raises(ProfileError) as error:
        apply_profile(config, environ={})

    assert "logs takes all, failed, none, not 'fail'" in str(error.value)


@pytest.mark.parametrize("value, expected", [
    ('"ten"', "takes a number"),
    ("-1", "cannot be negative"),
])
def test_a_count_that_is_not_one_fails_the_run(tmp_path, value, expected):
    config = _config(tmp_path, pyproject="""
        [tool.pytest-html-reporter.profiles.ci]
        archive_count = %s
    """ % value, options={"report_profile": "ci"})

    with pytest.raises(ProfileError) as error:
        apply_profile(config, environ={})

    assert expected in str(error.value)


def test_a_profile_that_is_not_a_table_says_so(tmp_path):
    config = _config(tmp_path, pyproject="""
        [tool.pytest-html-reporter]
        profiles = { ci = "none" }
    """, options={"report_profile": "ci"})

    with pytest.raises(ProfileError) as error:
        apply_profile(config, environ={})

    assert "must be a table of settings" in str(error.value)


def test_unparseable_toml_that_names_this_plugin_fails_the_run(tmp_path):
    """Because "no such profile" about a file that is right there is a bad hour."""
    (tmp_path / "pyproject.toml").write_text("[tool.pytest-html-reporter.profiles.ci\n")
    config = _FakeConfig(tmp_path, options={"report_profile": "ci"})

    with pytest.raises(ProfileError) as error:
        apply_profile(config, environ={})

    assert "could not be read as TOML" in str(error.value)


def test_a_broken_pyproject_that_says_nothing_about_this_plugin_is_not_our_business(tmp_path):
    """A project configured by pytest.ini may keep one pytest never opens.

    Refusing to start over a file this plugin has no stake in would be breaking
    runs that were working - so it is remembered rather than raised, and only
    surfaces if a profile then cannot be found.
    """
    (tmp_path / "pyproject.toml").write_text("[project\nname = broken\n")
    config = _FakeConfig(tmp_path)

    assert apply_profile(config, environ={}) == ""
    assert report_logs_mode(config) == "all"

    asked = _FakeConfig(tmp_path, options={"report_profile": "ci"})
    with pytest.raises(ProfileError) as error:
        apply_profile(asked, environ={})

    assert "pyproject.toml" in str(error.value)


def test_an_ini_file_configparser_chokes_on_is_named_by_the_profile_error(tmp_path):
    """pytest reads these files more forgivingly than configparser does.

    A file this cannot parse is not by itself an error - the run started off it
    - but a --report-profile that then cannot be found has to say where to
    look, or the profile sitting in that very file reads as missing.
    """
    inipath = tmp_path / "pytest.ini"
    inipath.write_text("this line belongs to no section\n")
    config = _FakeConfig(tmp_path, options={"report_profile": "ci"}, inipath=inipath)

    with pytest.raises(ProfileError) as error:
        apply_profile(config, environ={})

    assert "could not be parsed" in str(error.value)
    assert "pytest.ini" in str(error.value)


# --------------------------------------------------------------------------
# the environment layer on its own
# --------------------------------------------------------------------------

def test_both_spellings_of_a_setting_have_a_variable():
    values = environment_values({
        "PYTEST_HTML_REPORTER_LOGS": "failed",
        "PYTEST_HTML_REPORTER_REPORT_STEPS": "none",
    })

    assert values == {"logs": "failed", "steps": "none"}


def test_a_variable_set_to_nothing_is_not_an_answer():
    """`PYTEST_HTML_REPORTER_JUNIT=` in a matrix leg means "I am not saying".

    Reading it as "write no junit" would let an unset variable override a file
    that does say something, which is the opposite of an override.
    """
    assert environment_values({"PYTEST_HTML_REPORTER_JUNIT": "  "}) == {}


def test_a_variable_this_version_does_not_know_is_left_alone():
    """It is a namespace anybody can write into, and a guess is a poor reason
    to fail somebody's CI run."""
    assert environment_values({"PYTEST_HTML_REPORTER_WIBBLE": "1"}) == {}
    assert environment_values({"PYTEST_HTML_REPORTER_PROFILE": "ci"}) == {}


def test_the_environment_alone_shapes_a_run_with_no_profile_at_all(tmp_path):
    """No file, no --report-profile: the variables are still an override."""
    config = _config(tmp_path)

    apply_profile(config, environ={"PYTEST_HTML_REPORTER_OPEN": "none"})

    assert open_mode(config) == "none"


# --------------------------------------------------------------------------
# resolve, without applying
# --------------------------------------------------------------------------

def test_resolve_says_where_every_value_came_from(tmp_path):
    """Which is what every error message above is built out of."""
    config = _config(tmp_path, pyproject=SAMPLE_TOML)
    sources = load_sources(config)

    resolved = resolve(sources, "ci", environ={"PYTEST_HTML_REPORTER_LOGS": "all"})
    where = dict((key.name, origin) for key, (_value, origin) in resolved.items())

    assert where["open"].startswith("profile 'ci' in ")
    assert where["open"].endswith("pyproject.toml")
    assert where["logs"] == "the environment"


# --------------------------------------------------------------------------
# and in a real pytest
# --------------------------------------------------------------------------

SUITE = '''
    def test_pass():
        print("stdout-of-a-passing-test")
        assert True
'''


def _run(tmp_path, *args, **kwargs):
    (tmp_path / "test_sample.py").write_text(textwrap.dedent(SUITE).lstrip())

    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)
    for name in list(env):
        if name.startswith(profiles.ENV_PREFIX):
            env.pop(name)
    env.update(kwargs.get("env") or {})

    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider"] + list(args),
        cwd=str(tmp_path),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )


def test_a_real_run_is_shaped_by_the_profile_it_names(tmp_path):
    """One pytest, one --report-profile, and the report shows all of it.

    The unit tests above drive apply_profile directly, which proves the
    resolution. This proves the wiring: that it happens early enough in
    pytest_configure for the settings to be in force by the time anything
    reads them, and that the report says which shape it was built in.
    """
    (tmp_path / "pyproject.toml").write_text(textwrap.dedent("""
        [tool.pytest-html-reporter.profiles.ci]
        open = "none"
        logs = "failed"
        junit = "out/junit.xml"
        title = "PAYMENTS CI"
    """).lstrip())

    result = _run(tmp_path, "--report-profile=ci", "--html-report=out")

    assert result.returncode == 0, result.stdout

    page = (tmp_path / "out" / "pytest_html_report.html").read_text()

    assert (tmp_path / "out" / "junit.xml").is_file()
    assert "PAYMENTS CI" in page
    # logs = failed, so the passing test's stdout is not in the page - which
    # is the setting having been in force during collection, not just at the
    # end of the run.
    assert "stdout-of-a-passing-test" not in page
    # And the report says which profile it was built with, for whoever opens
    # it three months later wondering where the logs went.
    assert ">Profile</span>" in page
    assert '>ci</span>' in page


def test_a_real_run_takes_its_override_from_the_environment(tmp_path):
    (tmp_path / "pyproject.toml").write_text(textwrap.dedent("""
        [tool.pytest-html-reporter]
        profile = "ci"

        [tool.pytest-html-reporter.profiles.ci]
        open = "none"
        logs = "failed"
    """).lstrip())

    result = _run(tmp_path, "--html-report=out",
                  env={"PYTEST_HTML_REPORTER_LOGS": "all"})

    assert result.returncode == 0, result.stdout
    assert "stdout-of-a-passing-test" in (tmp_path / "out" / "pytest_html_report.html").read_text()


def test_a_real_run_stops_before_collection_on_a_profile_that_is_not_there(tmp_path):
    """At configure time, with one line, the way a bad --archive-count does."""
    (tmp_path / "pyproject.toml").write_text(textwrap.dedent("""
        [tool.pytest-html-reporter.profiles.ci]
        open = "none"
    """).lstrip())

    result = _run(tmp_path, "--report-profile=prod", "--html-report=out")

    assert result.returncode != 0
    assert "no such profile" in result.stdout
    assert "Defined: ci" in result.stdout
    assert not (tmp_path / "out").exists()


def test_report_profile_is_registered_as_an_ini_key():
    """Without the addini, `report_profile = ci` in a pytest.ini reads as unset.

    getini raises, _ini turns that into None, and the profile everybody thinks
    is pinned silently is not.
    """
    assert "report_profile" in _registered_options().ini_keys


def test_applying_the_same_profile_twice_does_not_double_its_lists(tmp_path):
    """Because an xdist worker is configured from a copy of the controller's.

    How much of that copy survives the trip is xdist's business rather than
    something to depend on: a worker that started with the controller's
    already-extended list and then extended it again would put every
    build-info row in the report twice.
    """
    config = _config(tmp_path, pyproject="""
        [tool.pytest-html-reporter.profiles.ci]
        build_info = ["lane=ci"]
        links = ["Coverage=htmlcov/index.html"]
    """, options={"report_profile": "ci"})

    apply_profile(config, environ={})
    apply_profile(config, environ={})

    assert config.option.build_info == ["lane=ci"]
    assert config.option.report_link == ["Coverage=htmlcov/index.html"]


def test_every_worker_of_an_xdist_run_is_shaped_by_the_same_profile(tmp_path):
    """The controller renders the report, but the workers run the tests.

    Which is where the settings that change what is collected in the first
    place - screenshots, steps, logs - are actually in force, so a profile
    that reached the controller alone would be a report shaped by one set of
    answers over records gathered under another.
    """
    (tmp_path / "pyproject.toml").write_text(textwrap.dedent("""
        [tool.pytest-html-reporter.profiles.ci]
        open = "none"
        build_info = ["lane=ci"]
    """).lstrip())

    (tmp_path / "conftest.py").write_text(textwrap.dedent('''
        import os

        def pytest_collection_modifyitems(session, config, items):
            worker = getattr(config, "workerinput", {}).get("workerid", "controller")
            path = os.path.join(str(config.rootpath), "seen-%s.txt" % worker)
            with open(path, "w") as handle:
                handle.write(repr(list(config.option.build_info)))
    ''').lstrip())

    result = _run(tmp_path, "--report-profile=ci", "--html-report=out", "-n", "2")

    assert result.returncode == 0, result.stdout

    # The controller delegates collection to the workers under xdist, so the
    # two workers are the whole of it.
    seen = sorted(path.name for path in tmp_path.glob("seen-*.txt"))
    assert seen == ["seen-gw0.txt", "seen-gw1.txt"]

    for name in seen:
        assert (tmp_path / name).read_text() == "['lane=ci']", name

    # And once each, not twice: a worker configured from a copy of the
    # controller's options must not add the profile's entries a second time.
    assert "lane" in (tmp_path / "out" / "pytest_html_report.html").read_text()


def test_a_setup_cfg_may_spell_the_sections_the_way_it_spells_pytests(tmp_path):
    """`[tool:pytest]` is how a setup.cfg names pytest's own section.

    Somebody keeping their profiles there will reach for `[tool:...]` first,
    and a section that reads exactly right and does nothing is a bad hour.
    """
    config = _config(tmp_path, ini="""
        [tool:pytest]
        addopts = -q

        [tool:pytest-html-reporter]
        profile = CI

        [tool:pytest-html-reporter.profiles.CI]
        open = none
        logs = failed
    """, ini_name="setup.cfg")

    assert apply_profile(config, environ={}) == "CI"
    assert open_mode(config) == "none"
    assert report_logs_mode(config) == "failed"
