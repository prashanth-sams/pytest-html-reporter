"""Hand the finished report to a browser when the run ends.

A local run ends with the reader going to find the file that was just written,
so the plugin opens it for them. A build agent is the opposite case: nobody is
sat there to look at it, and a browser launched into a headless session is at
best noise and at worst a console browser taking over the terminal the run
finished in.

So the default is ``auto`` - open it when somebody is plainly sat at the run,
and stay quiet otherwise. ``always`` is for the setups that guesswork gets
wrong, and ``none`` turns it off outright.

Nothing here is allowed to take a run down. The tests are over and the report
is written by the time any of it runs: a machine with no browser on it is not
a failed build.
"""

import os
import sys
import webbrowser
from pathlib import Path

import pytest

from pytest_html_reporter.util import _ini

OPEN_MODES = ("auto", "always", "none")

# Set by a build agent, not by a person. The generic two come first because
# most systems set one of them; the rest are the ones that set neither.
CI_ENV_VARS = (
    "CI",
    "CONTINUOUS_INTEGRATION",
    "BUILD_ID",
    "BUILD_NUMBER",
    "GITHUB_ACTIONS",
    "GITLAB_CI",
    "JENKINS_URL",
    "HUDSON_URL",
    "TEAMCITY_VERSION",
    "TF_BUILD",
    "CIRCLECI",
    "TRAVIS",
    "BUILDKITE",
    "APPVEYOR",
    "DRONE",
    "BITBUCKET_BUILD_NUMBER",
    "CODEBUILD_BUILD_ID",
)

# A variable set to one of these is there to say "no". CI=false is a real
# thing to write, and reading it as "this is CI" gets it exactly backwards.
FALSEY = ("", "0", "false", "no", "off")

# Platforms where a graphical session is always there to open into. Everything
# else is an X11 or Wayland desktop that has to say so in the environment.
GUI_PLATFORMS = ("darwin", "win", "cygwin", "msys")


# --------------------------------------------------------------------------
# options
# --------------------------------------------------------------------------

def open_mode(config):
    """Whether the finished report is opened: 'auto', 'always' or 'none'.

    A value that is none of those fails the run rather than being ignored:
    somebody who wrote ``report_open = off`` in their ini file has said they
    do not want a browser, and silently opening one anyway is the one outcome
    they were trying to avoid.
    """
    value = config.getoption("report_open", None)
    if value is None or str(value).strip() == "":
        value = _ini(config, "report_open")

    mode = str(value or "auto").strip().lower()

    if mode not in OPEN_MODES:
        raise pytest.UsageError(
            "--report-open takes auto, always or none, not %r" % mode)

    return mode


# --------------------------------------------------------------------------
# is anybody there?
# --------------------------------------------------------------------------

def _is_falsey(value):
    return str(value).strip().lower() in FALSEY


def in_ci(env=None):
    """Whether this looks like a build agent's run rather than a person's."""
    env = os.environ if env is None else env

    return any(not _is_falsey(env.get(name, "")) for name in CI_ENV_VARS)


def has_display(env=None, platform=None):
    """Whether there is a graphical session to open a browser into.

    Without this, ``webbrowser`` on a headless Linux box falls through to
    whatever console browser it can find and opens the report *in the
    terminal*, on top of the summary the run just printed.
    """
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform

    if platform.startswith(GUI_PLATFORMS):
        return True

    return bool(env.get("DISPLAY") or env.get("WAYLAND_DISPLAY"))


def is_interactive(stream=None):
    """Whether a person is sat at the terminal the run was started from.

    The *original* stdout, because pytest has long since replaced ``sys.stdout``
    with a capture of its own by the time the report is written. A run whose
    output is piped into a file or a log collector - cron, nohup, a build
    system nobody here has heard of - is not one to open a window on.
    """
    stream = sys.__stdout__ if stream is None else stream

    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError):
        # No stdout at all, or one that has already been closed.
        return False


def should_open(mode, env=None, platform=None, stream=None):
    """Whether the report is opened, for this mode in this environment."""
    if mode == "none":
        return False

    if mode == "always":
        return True

    return (is_interactive(stream)
            and not in_ci(env)
            and has_display(env, platform))


# --------------------------------------------------------------------------
# opening it
# --------------------------------------------------------------------------

def report_url(path):
    """The written report as a file:// URL, or None if it cannot be one.

    ``as_uri`` is what gets a space or an accent in the path percent-encoded;
    handing the raw path to a browser drops everything after the space.
    """
    try:
        return Path(path).absolute().as_uri()
    except (ValueError, OSError):
        return None


def open_report(path, mode, env=None, platform=None, stream=None, opener=None):
    """Open the finished report, returning whether a browser was asked to."""
    if not should_open(mode, env=env, platform=platform, stream=stream):
        return False

    url = report_url(path)
    if url is None:
        return False

    opener = webbrowser.open if opener is None else opener

    try:
        # new=2 asks for a tab rather than a window, so a run in a loop does
        # not bury the desktop under one window per run.
        return bool(opener(url, new=2))
    except Exception:
        return False
