"""Cover opening the finished report in a browser.

A local run ends with the reader going to find the file that was just written,
so the plugin opens it for them. The whole risk of that lives in the cases
where nobody is there to see it: a build agent, a cron job, a headless box
where ``webbrowser`` would fall through to a console browser and take over the
terminal the run just finished in. Most of what follows is about those.
"""

import os
import sys

import pytest

from pytest_html_reporter.report_opener import (
    has_display,
    in_ci,
    is_interactive,
    open_mode,
    open_report,
    report_url,
    should_open,
)


class _FakeConfig:
    """Just enough of pytest's Config for the option/ini resolution helpers."""

    def __init__(self, options=None, ini=None):
        self._options = options or {}
        self._ini = ini or {}

    def getoption(self, name, default=None):
        return self._options.get(name, default)

    def getini(self, name):
        if name not in self._ini:
            raise ValueError(name)
        return self._ini[name]


class _FakeStream:
    def __init__(self, tty):
        self._tty = tty

    def isatty(self):
        return self._tty


class _ClosedStream:
    def isatty(self):
        raise ValueError("I/O operation on closed file")


class _UnusablePath:
    """A path that cannot be turned into one - a run whose cwd has been deleted."""

    def __fspath__(self):
        raise OSError("cwd is gone")


class _Opener:
    """Stands in for webbrowser.open, remembering what it was handed."""

    def __init__(self, result=True, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def __call__(self, url, new=0):
        self.calls.append((url, new))
        if self.error is not None:
            raise self.error
        return self.result


# A desktop nobody is building on: a tty, a display, no CI variables.
DESKTOP = {"DISPLAY": ":0"}


def _open(path, mode, env=DESKTOP, platform="linux", stream=None, opener=None):
    return open_report(path, mode, env=env, platform=platform,
                       stream=_FakeStream(True) if stream is None else stream,
                       opener=opener)


# --------------------------------------------------------------------------
# resolving the option
# --------------------------------------------------------------------------

def test_open_mode_defaults_to_auto():
    assert open_mode(_FakeConfig()) == "auto"


def test_open_mode_from_ini():
    assert open_mode(_FakeConfig(ini={"report_open": "none"})) == "none"


def test_open_mode_cli_beats_ini():
    config = _FakeConfig(options={"report_open": "always"}, ini={"report_open": "none"})
    assert open_mode(config) == "always"


def test_open_mode_ignores_blank_option():
    """An unset option must not shadow the ini key that was set."""
    config = _FakeConfig(options={"report_open": ""}, ini={"report_open": "none"})
    assert open_mode(config) == "none"


def test_open_mode_tolerates_case_and_spacing():
    assert open_mode(_FakeConfig(ini={"report_open": " None "})) == "none"


def test_open_mode_rejects_anything_else():
    """`report_open = off` is somebody asking for no browser. Do not open one."""
    with pytest.raises(pytest.UsageError) as error:
        open_mode(_FakeConfig(ini={"report_open": "off"}))

    assert "auto, always or none" in str(error.value)
    assert "off" in str(error.value)


# --------------------------------------------------------------------------
# is anybody there?
# --------------------------------------------------------------------------

def test_in_ci_reads_the_generic_variable():
    assert in_ci({"CI": "true"}) is True


def test_in_ci_reads_a_system_specific_variable():
    assert in_ci({"JENKINS_URL": "https://ci.example.com/"}) is True


def test_not_in_ci_on_a_bare_environment():
    assert in_ci({}) is False


def test_not_in_ci_when_the_variable_says_so():
    """CI=false is a real thing to write, and means the opposite of CI=true."""
    assert in_ci({"CI": "false"}) is False
    assert in_ci({"CI": "0"}) is False
    assert in_ci({"CI": ""}) is False


def test_every_known_ci_variable_is_recognised():
    for name in ("CI", "GITHUB_ACTIONS", "GITLAB_CI", "TEAMCITY_VERSION",
                 "TF_BUILD", "CIRCLECI", "TRAVIS", "BUILDKITE", "DRONE"):
        assert in_ci({name: "1"}) is True, name


def test_display_is_assumed_on_macos_and_windows():
    assert has_display({}, "darwin") is True
    assert has_display({}, "win32") is True


def test_display_is_read_from_the_environment_elsewhere():
    assert has_display({"DISPLAY": ":0"}, "linux") is True
    assert has_display({"WAYLAND_DISPLAY": "wayland-0"}, "linux") is True


def test_no_display_on_a_headless_box():
    assert has_display({}, "linux") is False


def test_interactive_follows_the_stream():
    assert is_interactive(_FakeStream(True)) is True
    assert is_interactive(_FakeStream(False)) is False


def test_not_interactive_without_a_stream_at_all():
    """pythonw and friends have no stdout to ask."""
    assert is_interactive(None) is False


def test_not_interactive_on_a_closed_stream():
    assert is_interactive(_ClosedStream()) is False


# The three above are handed an environment in the tests. In a real run they
# read this process's, which is the version that has to work.

def test_in_ci_reads_the_real_environment(monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert in_ci() is True


def test_has_display_reads_the_real_environment(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert has_display() is False

    monkeypatch.setenv("DISPLAY", ":0")
    assert has_display() is True


def test_is_interactive_reads_the_original_stdout(monkeypatch):
    """pytest replaced sys.stdout with a capture long before the report is written."""
    monkeypatch.setattr(sys, "__stdout__", _FakeStream(False))
    assert is_interactive() is False

    monkeypatch.setattr(sys, "__stdout__", _FakeStream(True))
    assert is_interactive() is True


# --------------------------------------------------------------------------
# the decision
# --------------------------------------------------------------------------

def test_auto_opens_on_a_desktop_run():
    assert should_open("auto", DESKTOP, "linux", _FakeStream(True)) is True


def test_auto_stays_quiet_in_ci():
    env = dict(DESKTOP, GITHUB_ACTIONS="true")
    assert should_open("auto", env, "linux", _FakeStream(True)) is False


def test_auto_stays_quiet_on_a_macos_build_agent():
    """The one case only the tty check catches: a desktop OS with nobody on it."""
    assert should_open("auto", {}, "darwin", _FakeStream(False)) is False


def test_auto_stays_quiet_when_output_is_redirected():
    assert should_open("auto", DESKTOP, "linux", _FakeStream(False)) is False


def test_auto_stays_quiet_on_a_headless_box():
    assert should_open("auto", {}, "linux", _FakeStream(True)) is False


def test_always_opens_where_auto_would_not():
    """The escape hatch for a setup the guesswork reads wrongly."""
    env = dict(DESKTOP, CI="true")
    assert should_open("always", env, "linux", _FakeStream(False)) is True


def test_none_never_opens():
    assert should_open("none", DESKTOP, "linux", _FakeStream(True)) is False


# --------------------------------------------------------------------------
# opening it
# --------------------------------------------------------------------------

def test_open_report_hands_the_file_to_the_browser(tmpdir):
    report = tmpdir.join("pytest_html_report.html")
    report.write("<html></html>")
    opener = _Opener()

    assert _open(str(report), "auto", opener=opener) is True
    assert opener.calls == [(report_url(str(report)), 2)]


def test_open_report_percent_encodes_the_path(tmpdir):
    """A raw path with a space in it loses everything after the space."""
    folder = tmpdir.mkdir("my reports")
    report = folder.join("pytest_html_report.html")
    report.write("<html></html>")
    opener = _Opener()

    _open(str(report), "auto", opener=opener)
    url, _ = opener.calls[0]

    assert url.startswith("file://")
    assert " " not in url
    assert "my%20reports" in url


def test_open_report_asks_for_a_tab(tmpdir):
    """A run in a loop should not bury the desktop under one window per run."""
    opener = _Opener()
    _open(str(tmpdir.join("report.html")), "auto", opener=opener)

    assert opener.calls[0][1] == 2


def test_open_report_absolutises_a_relative_path(tmpdir):
    cwd = os.getcwd()
    os.chdir(str(tmpdir))
    try:
        opener = _Opener()
        _open("report.html", "auto", opener=opener)
    finally:
        os.chdir(cwd)

    assert opener.calls[0][0].endswith("/report.html")
    assert opener.calls[0][0].startswith("file://")


def test_open_report_does_nothing_when_switched_off(tmpdir):
    opener = _Opener()

    assert _open(str(tmpdir.join("report.html")), "none", opener=opener) is False
    assert opener.calls == []


def test_open_report_does_nothing_in_ci(tmpdir):
    opener = _Opener()
    env = dict(DESKTOP, CI="true")

    assert _open(str(tmpdir.join("report.html")), "auto", env=env, opener=opener) is False
    assert opener.calls == []


def test_open_report_survives_a_browser_that_blows_up(tmpdir):
    """The tests are over and the report is written; a missing browser is not a failure."""
    opener = _Opener(error=RuntimeError("no browser"))

    assert _open(str(tmpdir.join("report.html")), "always", opener=opener) is False
    assert len(opener.calls) == 1


def test_open_report_reports_a_browser_that_declined(tmpdir):
    """webbrowser.open returns False when it found nothing to run."""
    opener = _Opener(result=False)

    assert _open(str(tmpdir.join("report.html")), "auto", opener=opener) is False


def test_report_url_gives_up_on_a_path_it_cannot_resolve():
    assert report_url(_UnusablePath()) is None


def test_open_report_gives_up_on_a_path_it_cannot_resolve():
    """Still no browser and still no exception, with the run already over."""
    opener = _Opener()

    assert _open(_UnusablePath(), "always", opener=opener) is False
    assert opener.calls == []
