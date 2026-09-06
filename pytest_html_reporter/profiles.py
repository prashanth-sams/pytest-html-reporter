"""Named configuration profiles - one name for a set of report settings.

A suite is run in more than one shape. On a laptop you want the browser to
open, every log kept and a handful of builds in the archive; on CI you want no
browser, logs only where something failed, a JUnit xml beside the report and a
month of history. Today that is two long command lines kept in two places -
a Makefile target and a workflow file - that drift the moment one of them is
edited, and the drift is invisible until somebody reads a report that is
missing the thing they went looking for.

A profile is that pair of shapes written down once, under a name::

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

and then ``pytest --report-profile=ci``.

How a profile reaches the run
-----------------------------
By writing its values onto ``config.option``, which is where the command line
parses into and where every option helper in this package already reads from.
Nothing else in the tree learns that profiles exist: ``report_logs_mode`` asks
for the ``report_logs`` option exactly as it did before and gets the profile's
answer, an xdist worker is handed a copy of those same options and so agrees
with the process that resolved them, and a suite that names no profile is byte
for byte the run it was yesterday.

That also settles the precedence, because ``config.option`` already sits above
the ini file for every one of these settings. Highest first:

1. a flag on the command line - including one reached through ``addopts``
2. a ``PYTEST_HTML_REPORTER_*`` environment variable
3. the selected profile
4. the ``[tool.pytest-html-reporter]`` table, which every profile shares
5. the plain ini key in ``[pytest]``
6. the option's own default

The environment sits above the profile rather than below it because that is
what an override is for: the profile is what the repository committed, and the
variable is one job, one machine or one debugging session saying otherwise
without editing a file that everyone else reads.

Where profiles are written
--------------------------
In the ini file pytest chose for this run - ``pytest.ini``, ``tox.ini``,
``setup.cfg`` - as a section per profile::

    [pytest-html-reporter.profiles.ci]
    open = none
    logs = failed
    junit = report/junit.xml

and in ``pyproject.toml`` as a table per profile, which is the same path with
``tool.`` in front of it. Both files are read, the ini file first, and the
first one that defines a name provides it whole: a profile is a shape somebody
composed deliberately, and half of it from one file and half from another is
not a shape anybody wrote.
"""

import configparser
import difflib
import os

import pytest


# The table a profile lives under, in either spelling of the distribution's
# name. The hyphen is the real one - it is what the project is called on PyPI
# and what `[tool.pytest-html-reporter]` reads as - and the underscore is
# accepted because it is the import name, which is what half of everybody
# types first.
TOOL_NAMES = ("pytest-html-reporter", "pytest_html_reporter")

# The ini section holding what the pyproject table holds, so that a repository
# with a pytest.ini and no pyproject.toml is not asked to grow one.
INI_SECTION = "pytest-html-reporter"
INI_PROFILE_PREFIX = INI_SECTION + ".profiles."

# What a setup.cfg puts in front of pytest's own section, and so the thing
# anybody keeping their profiles in one will put in front of these.
INI_TOOL_PREFIX = "tool:"

# The key inside either of those that names the profile to use when the command
# line and the environment say nothing.
DEFAULT_KEY = "profile"

# Reserved inside the tool table: they shape the profiles rather than being
# settings themselves.
RESERVED = (DEFAULT_KEY, "profiles")

ENV_PREFIX = "PYTEST_HTML_REPORTER_"
PROFILE_ENV = ENV_PREFIX + "PROFILE"

# What `--report-profile=none` means: this run uses no profile, whatever the
# ini file pinned as the default. Spelled the way the rest of the plugin
# spells "off" - --report-open=none, --report-logs=none - rather than as an
# empty value, because an empty --report-profile= on a command line cannot be
# told apart from one that was never passed.
NO_PROFILE = "none"

_TRUTHY = ("1", "true", "yes", "on")
_FALSEY = ("0", "false", "no", "off")

_MISSING = object()


# --------------------------------------------------------------------------
# the settings a profile may name
# --------------------------------------------------------------------------

class Key(object):
    """One setting a profile can carry, and the option it is written onto.

    ``dest`` is the argparse destination the flag already parses into. That is
    the whole mechanism - see the module docstring - and ``default`` is the
    default that flag was registered with, which is how a value that came from
    the command line is told apart from one nobody passed.

    ``name`` is the short spelling a profile is written in (``logs``), and
    ``aliases`` hold the longer ones somebody may reach for instead - the ini
    key (``report_logs``) first among them, because a profile is very often a
    block of ini keys moved under a name.
    """

    def __init__(self, name, dest, flag, kind, default, choices=(), aliases=()):
        self.name = name
        self.dest = dest
        self.flag = flag
        self.kind = kind
        self.default = default
        self.choices = tuple(choices)
        self.aliases = tuple(aliases)

    @property
    def names(self):
        return (self.name,) + self.aliases

    def __repr__(self):
        return "Key(%r)" % self.name


LOG_MODES = ("all", "failed", "none")
OPEN_MODES = ("auto", "always", "none")
COVERAGE_MODES = ("auto", "none")
SCREENSHOT_MODES = ("failed", "all", "none")
XPASS_MODES = ("pass", "fail", "skip")


# Every option this plugin registers, in the order --help lists them. The
# defaults are the ones pytest_addoption registers and are pinned against it by
# a test, because a default that drifts from the flag it mirrors is how a
# profile silently stops overriding - or starts overriding a value somebody
# typed.
KEYS = (
    Key("path", "path", "--html-report", "text", "",
        aliases=("html_report", "report")),
    Key("title", "title", "--title", "text", "PYTEST REPORT"),
    Key("archive_count", "archive_count", "--archive-count", "count", ""),
    Key("archive_days", "archive_days", "--archive-days", "text", ""),
    Key("archive_since", "archive_since", "--archive-since", "text", ""),
    Key("environment", "environment", "--environment", "text", None),
    Key("build_info", "build_info", "--build-info", "list", []),
    Key("logs", "report_logs", "--report-logs", "choice", None,
        choices=LOG_MODES, aliases=("report_logs",)),
    Key("log_limit", "report_log_limit", "--report-log-limit", "count", None,
        aliases=("report_log_limit",)),
    Key("attachments", "report_attachments", "--report-attachments", "choice", None,
        choices=LOG_MODES, aliases=("report_attachments",)),
    Key("attachment_limit", "report_attachment_limit", "--report-attachment-limit",
        "count", None, aliases=("report_attachment_limit",)),
    Key("screenshots", "report_screenshots", "--report-screenshots", "choice", None,
        choices=SCREENSHOT_MODES, aliases=("report_screenshots",)),
    Key("steps", "report_steps", "--report-steps", "choice", None,
        choices=LOG_MODES, aliases=("report_steps",)),
    Key("step_limit", "report_step_limit", "--report-step-limit", "count", None,
        aliases=("report_step_limit",)),
    Key("coverage", "report_coverage", "--report-coverage", "choice", None,
        choices=COVERAGE_MODES, aliases=("report_coverage",)),
    Key("coverage_file", "report_coverage_file", "--report-coverage-file", "text", None,
        aliases=("report_coverage_file",)),
    Key("coverage_limit", "report_coverage_limit", "--report-coverage-limit",
        "count", None, aliases=("report_coverage_limit",)),
    Key("links", "report_link", "--report-link", "list", [],
        aliases=("report_link", "link")),
    Key("link_patterns", "report_link_pattern", "--report-link-pattern", "list", [],
        aliases=("report_link_pattern", "link_pattern")),
    Key("open", "report_open", "--report-open", "choice", None,
        choices=OPEN_MODES, aliases=("report_open",)),
    Key("shard", "report_shard", "--report-shard", "text", "",
        aliases=("report_shard",)),
    Key("shard_merge", "report_shard_merge", "--report-shard-merge", "flag", False,
        aliases=("report_shard_merge",)),
    Key("shard_run", "report_shard_run", "--report-shard-run", "text", "",
        aliases=("report_shard_run",)),
    Key("shard_reset", "report_shard_reset", "--report-shard-reset", "flag", False,
        aliases=("report_shard_reset",)),
    Key("junit", "report_junit", "--report-junit", "text", "",
        aliases=("report_junit",)),
    Key("junit_xpass", "report_junit_xpass", "--report-junit-xpass", "choice", None,
        choices=XPASS_MODES, aliases=("report_junit_xpass",)),
    Key("packages", "report_packages", "--report-packages", "flag", False,
        aliases=("report_packages",)),
)


def _key_index():
    """{spelling: Key} over every name and alias, checked for collisions."""
    index = {}

    for key in KEYS:
        for name in key.names:
            if index.get(name, key) is not key:
                raise AssertionError("two profile keys answer to %r" % name)
            index[name] = key

    return index


KEY_INDEX = _key_index()

KEY_NAMES = tuple(key.name for key in KEYS)


def lookup(name):
    """The Key a profile key names, or None."""
    return KEY_INDEX.get(str(name).strip().lower().replace("-", "_"))


# --------------------------------------------------------------------------
# reading the files
# --------------------------------------------------------------------------

class ProfileError(pytest.UsageError):
    """A profile that cannot be read or does not say what it means.

    A pytest.UsageError so that a broken profile stops the run at configure
    time with one line, the way a bad --archive-count does. The alternative -
    ignoring what cannot be read - is a run that quietly reports under the
    wrong settings, which is the failure this feature exists to prevent.
    """


class Sources(object):
    """Everything the files said, before a profile has been chosen.

    ``profiles`` is {name: {key: value}}, ``base`` is the table every profile
    shares, ``default`` is the profile to use when nothing on the command line
    or in the environment names one, and ``origins`` remembers which file each
    profile came out of so an error can say where to go and fix it.
    """

    def __init__(self):
        self.profiles = {}
        self.base = {}
        self.default = ""
        self.origins = {}
        self.base_origin = ""
        self.unreadable = []

    def add(self, name, values, origin):
        # First file wins, whole. Merging one profile out of two files would
        # make the shape depend on which file pytest happened to pick as the
        # ini file for this run, and a half-and-half profile is not a shape
        # anybody composed.
        if name in self.profiles:
            return

        self.profiles[name] = values
        self.origins[name] = origin

    def names(self):
        return sorted(self.profiles)


def _toml_tool_table(path):
    """(the [tool.pytest-html-reporter] table, why it could not be read).

    Never raises. Whether an unreadable pyproject.toml is worth failing a run
    over is not this function's call to make: a project whose ini file is a
    pytest.ini can have a broken or exotic pyproject.toml sitting beside it
    that pytest itself never opens, and a reporting plugin that refused to
    start over it would be breaking runs it has no business in.
    """
    loader = _toml_loader()

    if loader is None:
        # tomllib is stdlib from 3.11 and pytest itself depends on tomli below
        # that, so this is close to unreachable.
        return {}, "no TOML reader is available on this interpreter (install tomli)"

    try:
        with open(path, "rb") as handle:
            data = loader(handle)
    except OSError as error:
        return {}, str(error)
    except Exception as error:
        return {}, "could not be read as TOML: %s" % error

    tool = data.get("tool")
    if not isinstance(tool, dict):
        return {}, ""

    for name in TOOL_NAMES:
        table = tool.get(name)
        if isinstance(table, dict):
            return table, ""

    return {}, ""


def _toml_loader():
    """tomllib.load, tomli.load, or None where there is neither."""
    try:
        import tomllib
        return tomllib.load
    except ImportError:
        pass

    try:
        import tomli
        return tomli.load
    except ImportError:
        return None


def _mentions_tool(path):
    try:
        with open(path, "rb") as handle:
            text = handle.read()
    except OSError:
        return False

    return any(name.encode() in text for name in TOOL_NAMES)


def _read_toml(sources, path):
    table, problem = _toml_tool_table(path)

    if problem:
        # A file that names this plugin and then cannot be read is a run under
        # settings nobody can see, which is the failure profiles exist to
        # prevent - so that one is fatal. One that does not mention it is
        # somebody else's file: remembered, in case a profile then cannot be
        # found, and otherwise left alone.
        if _mentions_tool(path):
            raise ProfileError("%s %s" % (path, problem))

        sources.unreadable.append((str(path), problem))
        return

    if not table:
        return

    origin = str(path)

    profiles = table.get("profiles") or {}
    if not isinstance(profiles, dict):
        raise ProfileError(
            "%s: [tool.pytest-html-reporter.profiles] must be a table of named "
            "profiles" % origin)

    for name, values in profiles.items():
        if not isinstance(values, dict):
            raise ProfileError(
                "%s: profile %r must be a table of settings, not %s"
                % (origin, name, type(values).__name__))
        sources.add(_profile_name(name, origin), dict(values), origin)

    base = dict((k, v) for k, v in table.items() if k not in RESERVED)
    if base and not sources.base:
        sources.base = base
        sources.base_origin = "[tool.pytest-html-reporter] in %s" % origin

    if not sources.default:
        sources.default = str(table.get(DEFAULT_KEY) or "").strip()


def _read_ini(sources, path):
    parser = configparser.ConfigParser(
        # No interpolation: an html_report of ./reports/%Y%m%d/report.html is
        # the documented way to write a dated path, and ConfigParser's default
        # interpolation raises on the % rather than passing it through.
        # strict=False for the same reason pytest reads these files
        # forgivingly - a duplicate key elsewhere in somebody's setup.cfg is
        # not this plugin's business to refuse.
        interpolation=None, strict=False)

    try:
        with open(path, "r", encoding="utf-8") as handle:
            parser.read_file(handle)
    except OSError:
        return
    except configparser.Error as error:
        # Not fatal by itself: pytest read this file happily enough to start
        # the run, and configparser is stricter than pytest's own reader. Kept
        # rather than dropped, so that a --report-profile that then cannot be
        # found is told where to look instead of being told it does not exist.
        sources.unreadable.append(
            (str(path), "could not be parsed: %s" % str(error).splitlines()[0]))
        return

    origin = str(path)

    for section in parser.sections():
        # A setup.cfg spells pytest's own section [tool:pytest], so somebody
        # keeping their profiles there will write [tool:pytest-html-reporter...]
        # first. Both are read, and either is read in any case: a section name
        # is typed by hand and failing over a capital would be a bad hour spent
        # looking at a file that says exactly what it should.
        name = section.strip()
        if name.lower().startswith(INI_TOOL_PREFIX):
            name = name[len(INI_TOOL_PREFIX):]

        lowered = name.lower()

        if lowered.startswith(INI_PROFILE_PREFIX):
            sources.add(
                _profile_name(name[len(INI_PROFILE_PREFIX):], origin),
                dict(parser.items(section)), origin)

        elif lowered == INI_SECTION:
            table = dict(parser.items(section))
            default = str(table.pop(DEFAULT_KEY, "") or "").strip()

            if table and not sources.base:
                sources.base = table
                sources.base_origin = "[%s] in %s" % (section, origin)

            if default and not sources.default:
                sources.default = default


def _profile_name(name, origin):
    name = str(name).strip()

    if not name:
        raise ProfileError("%s: a profile needs a name" % origin)

    if name.lower() == NO_PROFILE:
        raise ProfileError(
            "%s: %r is reserved - it is how --report-profile=%s says this run "
            "uses no profile - so a profile cannot be called that"
            % (origin, name, NO_PROFILE))

    return name


def _ini_path(config):
    """The config file pytest chose for this run, as a str, or ''."""
    for attribute in ("inipath", "inifile"):
        value = getattr(config, attribute, None)
        if value:
            return str(value)

    return ""


def _root_path(config):
    root = getattr(config, "rootpath", None) or getattr(config, "rootdir", "")

    return str(root or os.getcwd())


def load_sources(config):
    """Every profile this run can see, from the ini file and pyproject.toml.

    The ini file first: it is the one pytest itself picked as this run's
    configuration, so when both files answer to a name that is the answer the
    run is already being shaped by.
    """
    sources = Sources()

    seen = []
    for path in (_ini_path(config), os.path.join(_root_path(config), "pyproject.toml")):
        if not path or path in seen or not os.path.isfile(path):
            continue

        seen.append(path)

        if path.lower().endswith(".toml"):
            _read_toml(sources, path)
        else:
            _read_ini(sources, path)

    return sources


# --------------------------------------------------------------------------
# choosing one
# --------------------------------------------------------------------------

def _ini(config, name):
    """An ini value, tolerating a pytest build where the key is unregistered."""
    try:
        return config.getini(name)
    except (AttributeError, ValueError, KeyError):
        return None


def requested_name(config, sources=None, environ=None):
    """The profile this run asked for, before it is known to exist.

    ``--report-profile`` beats PYTEST_HTML_REPORTER_PROFILE, which beats the
    report_profile ini key, which beats whatever the tool table pinned as its
    default. '' means no profile was asked for at all, and NO_PROFILE means
    one was asked for and it is "none of them".
    """
    environ = os.environ if environ is None else environ

    value = str(config.getoption("report_profile", None) or "").strip()

    if not value:
        value = str(environ.get(PROFILE_ENV) or "").strip()

    if not value:
        value = str(_ini(config, "report_profile") or "").strip()

    if not value and sources is not None:
        value = str(sources.default or "").strip()

    return value


def find(sources, name):
    """(name as defined, its values), or a UsageError naming what there is.

    The name is handed back rather than echoed because it is what the report
    goes on to show, and a profile found through the case-insensitive match
    below should be shown as it was written down, not as it was typed.
    """
    if name in sources.profiles:
        return name, sources.profiles[name]

    # Case-insensitively too: a profile is typed on a command line, and
    # --report-profile=CI failing over a capital is a bad five minutes.
    lowered = dict((key.lower(), key) for key in sources.profiles)
    if name.lower() in lowered:
        defined = lowered[name.lower()]
        return defined, sources.profiles[defined]

    available = sources.names()
    unreadable = _unreadable_note(sources)

    if not available:
        raise ProfileError(
            "--report-profile=%s: no profiles are defined.%s Write one as "
            "[tool.pytest-html-reporter.profiles.%s] in pyproject.toml or as "
            "[%s%s] in pytest.ini"
            % (name, unreadable, name, INI_PROFILE_PREFIX, name))

    close = difflib.get_close_matches(name.lower(), lowered, n=1)
    hint = " Did you mean %r?" % lowered[close[0]] if close else ""

    raise ProfileError(
        "--report-profile=%s: no such profile. Defined: %s.%s%s"
        % (name, ", ".join(available), hint, unreadable))


def _unreadable_note(sources):
    """A sentence about a config file that could not be parsed, or ''.

    Only ever said as part of a profile that could not be found: a file
    configparser chokes on is not by itself this plugin's business - pytest
    started the run off it happily enough - but "no such profile" about a
    profile that is sitting right there in an unreadable file is a bad half
    hour, and naming the file is the whole fix.
    """
    if not sources.unreadable:
        return ""

    return " (%s %s)" % sources.unreadable[0]


# --------------------------------------------------------------------------
# turning what was written into what the options hold
# --------------------------------------------------------------------------

def _entries(value, where):
    """A list of KEY=VALUE strings, from however the file spelled the list.

    Three spellings, because three files are in play and each has its own
    natural one: a toml array, a toml table - which is what anybody writing
    link_patterns reaches for first - and the indented block an ini file
    already uses for build_info and report_link.
    """
    if isinstance(value, dict):
        return ["%s=%s" % (k, _scalar(v, where)) for k, v in value.items()]

    if isinstance(value, (list, tuple)):
        return [_scalar(item, where) for item in value if str(item).strip()]

    return [line.strip() for line in str(value).splitlines() if line.strip()]


def _scalar(value, where):
    if isinstance(value, bool):
        return "true" if value else "false"

    if isinstance(value, (list, tuple, dict)):
        raise ProfileError("%s: expected a single value, got %r" % (where, value))

    return str(value).strip()


def coerce(key, value, where):
    """`value`, as the option's own parser would have left it on config.option.

    Every check the command line would have made is made here, because a
    profile bypasses argparse entirely: an unknown choice written into
    config.option does not fail, it falls through to the helper's default, and
    a run that quietly kept every log because the profile said `logs = "fail"`
    rather than "failed" is the silent misconfiguration this whole feature
    exists to remove.
    """
    if key.kind == "list":
        return _entries(value, where)

    if key.kind == "flag":
        if isinstance(value, bool):
            return value

        text = _scalar(value, where).lower()
        if text in _TRUTHY:
            return True
        if text in _FALSEY or text == "":
            return False

        raise ProfileError(
            "%s: %s takes true or false, not %r" % (where, key.name, value))

    text = _scalar(value, where)

    if key.kind == "choice":
        lowered = text.lower()
        if lowered not in key.choices:
            raise ProfileError(
                "%s: %s takes %s, not %r"
                % (where, key.name, ", ".join(key.choices), text))
        return lowered

    if key.kind == "count":
        if text == "":
            return text

        try:
            number = int(text)
        except ValueError:
            raise ProfileError(
                "%s: %s takes a number, not %r" % (where, key.name, text))

        if number < 0:
            raise ProfileError(
                "%s: %s cannot be negative, got %r" % (where, key.name, text))

        # As text, because that is what the flag it stands for parses to for
        # archive_count - where '' and '0' are different answers - and every
        # reader of these goes through int() anyway.
        return str(number)

    return text


def _layer(collected, values, where):
    """Fold one file's or one environment's worth of settings into `collected`.

    `collected` is {Key: [(value, where), ...]} in the order the layers were
    applied, so a scalar can take the last word and a list can take all of
    them.
    """
    for name, value in values.items():
        key = lookup(name)

        if key is None:
            raise ProfileError(
                "%s: unknown setting %r.%s"
                % (where, name, _suggest(name)))

        collected.setdefault(key, []).append((value, where))


def _suggest(name):
    close = difflib.get_close_matches(
        str(name).strip().lower().replace("-", "_"), KEY_INDEX, n=1)

    if close:
        return " Did you mean %r?" % lookup(close[0]).name

    return " Known settings: %s" % ", ".join(KEY_NAMES)


def environment_values(environ=None):
    """{key name: value} from the PYTEST_HTML_REPORTER_* variables.

    Every spelling a profile accepts has a variable - both
    PYTEST_HTML_REPORTER_LOGS and PYTEST_HTML_REPORTER_REPORT_LOGS reach the
    same setting - so somebody who knows the ini key does not have to learn
    the short name to override it for one job.

    A variable set to nothing is left out rather than read as an empty
    setting: `PYTEST_HTML_REPORTER_JUNIT=` in a shell profile or a CI matrix
    that left one leg's value blank means "I am not saying", and taking it as
    "write no junit" would let an unset variable override the file.
    """
    environ = os.environ if environ is None else environ

    values = {}
    for name, value in environ.items():
        if not name.startswith(ENV_PREFIX) or name == PROFILE_ENV:
            continue

        if not str(value).strip():
            continue

        key = lookup(name[len(ENV_PREFIX):])
        if key is None:
            # Not an error. This is a namespace anybody can write into and a
            # variable this version does not know is a variable a later one
            # might; failing a CI run over it would be a poor trade for a
            # typo it is only a guess about anyway.
            continue

        values[key.name] = value

    return values


def resolve(sources, name, environ=None):
    """Every setting this run's profile decides, as {Key: (value, where)}.

    The layers, lowest first: the shared table, the profile, the environment.
    A list-valued setting keeps every layer's entries - the same way
    --build-info adds to the ini file's rather than replacing it - and
    everything else takes the highest layer that said anything.
    """
    collected = {}

    if sources.base:
        _layer(collected, sources.base, sources.base_origin or "the shared table")

    if name and name.lower() != NO_PROFILE:
        defined, values = find(sources, name)
        where = "profile %r" % defined
        if sources.origins.get(defined):
            where += " in %s" % sources.origins[defined]
        _layer(collected, values, where)

    _layer(collected, environment_values(environ), "the environment")

    resolved = {}
    for key, layers in collected.items():
        if key.kind == "list":
            entries = []
            for value, where in layers:
                entries += coerce(key, value, where)
            resolved[key] = (entries, layers[-1][1])
        else:
            value, where = layers[-1]
            resolved[key] = (coerce(key, value, where), where)

    return resolved


# --------------------------------------------------------------------------
# applying it
# --------------------------------------------------------------------------

def given_on_command_line(config, key):
    """Whether this option already holds something other than its default.

    Which is as close as argparse lets anybody get to "did they type it".
    ``addopts`` counts as typed, deliberately: it is a line somebody wrote for
    this repository about every run of it, and a profile quietly overriding it
    would make the two config files disagree in a way neither of them shows.
    """
    current = getattr(getattr(config, "option", None), key.dest, _MISSING)

    if current is _MISSING:
        return False

    return current != key.default


def apply_profile(config, environ=None):
    """Settle this run's profile and write it onto the options. Returns its name.

    Called first thing in pytest_configure, before anything reads an option -
    including the marker registration, which reads report_link_pattern.

    The name is written back onto config.option.report_profile for the same
    reason the resolved path and shard id are: an xdist worker is handed a copy
    of these options rather than a chance to work it out again, and the
    Environment panel shows the name so that a report found on a CI server
    months later says which shape produced it.
    """
    sources = load_sources(config)
    name = requested_name(config, sources, environ)

    # Settled here rather than inside resolve so that a name typed in another
    # case is reported - and shown in the report - as the profile was written.
    if name and name.lower() != NO_PROFILE:
        name = find(sources, name)[0]

    resolved = resolve(sources, name, environ)

    for key, (value, _where) in resolved.items():
        if key.kind == "list":
            # Added to, never replaced: --build-info, --report-link and
            # --report-link-pattern are documented to add to what the ini file
            # set rather than override it, and a profile is another place the
            # same list is written from.
            #
            # An entry that is already there is not added twice, which is what
            # makes this safe to run more than once against one set of options.
            # An xdist worker is configured from a copy of the controller's,
            # and how much of that copy survives the trip is xdist's business
            # rather than something to depend on: today a worker starts with
            # an empty list and re-resolves the profile itself, and if a
            # version hands it the controller's list instead, the profile's
            # entries are already in it and this adds nothing. Either way the
            # worker ends up with one copy, rather than one report carrying
            # every build-info row twice.
            current = list(getattr(config.option, key.dest, None) or [])
            setattr(config.option, key.dest,
                    current + [entry for entry in value if entry not in current])
            continue

        if given_on_command_line(config, key):
            continue

        setattr(config.option, key.dest, value)

    settled = "" if name.lower() == NO_PROFILE else name
    config.option.report_profile = settled

    return settled
