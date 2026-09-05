import hashlib
import json
import logging
import os
import platform
import re
import shutil
import sys
import time
from collections import Counter
from datetime import datetime
from html import escape
from urllib.parse import quote

import pytest

from html_page.env_link import EnvLink
from html_page.env_row import EnvRow
from html_page.logs_notice import LogsNotice
from html_page.report_link import ReportLink
from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.environment import (
    ci_run,
    git_revision,
    installed_packages,
    interpreter_path,
    os_summary,
    packages_row,
    python_summary,
    worker_summary,
)
from pytest_html_reporter.markers import (
    OWNER_MARKER,
    OWNER_MARKER_KIND,
    SEVERITY_MARKER,
    SEVERITY_MARKER_KIND,
    severity_rank,
    severity_value,
)
from pytest_html_reporter.screenshots import MODES as SCREENSHOT_MODES

# Re-exported: the package publishes this as ``attach``, and it was defined
# here before the automatic captures gave it a module of its own. Anything that
# already imports ``util.screenshot`` keeps working, and keeps getting the very
# same function ``pytest_html_reporter.attach`` is.
from pytest_html_reporter.screenshots import attach as screenshot  # noqa: F401


def suite_highlights(data):
    for i in data['content']['suites']:
        if data['content']['suites'][i]['status']['total_fail'] == 0:
            l = data['content']['suites'][i]['suite_name']
            if l not in ConfigVars.p_highlights:
                ConfigVars.p_highlights[l] = 1
            else:
                ConfigVars.p_highlights[l] += 1
        else:
            k = data['content']['suites'][i]['suite_name']

            if k not in ConfigVars.highlights:
                ConfigVars.highlights[k] = 1
            else:
                ConfigVars.highlights[k] += 1


def generate_suite_highlights():
    if ConfigVars.highlights == {}:
        ConfigVars.max_failure_suite_name_final = 'No failures in History'
        ConfigVars.max_failure_suite_count = 0
        ConfigVars.max_failure_percent = '0'
        return

    ConfigVars.max_failure_suite_name = max(ConfigVars.highlights, key=ConfigVars.highlights.get)
    ConfigVars.max_failure_suite_count = ConfigVars.highlights[ConfigVars.max_failure_suite_name]

    if ConfigVars.max_failure_suite_name in ConfigVars.p_highlights:
        ConfigVars.max_failure_total_tests = ConfigVars.p_highlights[ConfigVars.max_failure_suite_name] + ConfigVars.max_failure_suite_count
    else:
        ConfigVars.max_failure_total_tests = ConfigVars.max_failure_suite_count

    ConfigVars.max_failure_percent = (ConfigVars.max_failure_suite_count / ConfigVars.max_failure_total_tests) * 100

    if ConfigVars.max_failure_suite_name.__len__() > 25:
        ConfigVars.max_failure_suite_name_final = ".." + ConfigVars.max_failure_suite_name[-23:]
    else:
        ConfigVars.max_failure_suite_name_final = ConfigVars.max_failure_suite_name

    res = Counter(ConfigVars.highlights.values())
    if max(res.values()) > 1: ConfigVars.similar_max_failure_suite_count = max(res.values())


def is_xdist_worker(config):
    """True when this process is one of pytest-xdist's workers (gw0, gw1, ...).

    xdist hands every worker a ``workerinput`` dict; the controller never has
    one, and neither does a plain serial run.
    """
    return hasattr(config, "workerinput")


def xdist_worker_id(config):
    """The worker's id, or '' on the controller and on serial runs."""
    return str(getattr(config, "workerinput", {}).get("workerid", ""))


def clean_screenshots(path):
    screenshot_dir = os.path.abspath(os.path.expanduser(os.path.expandvars(path))) + '/pytest_screenshots'
    if os.path.isdir(screenshot_dir):
        shutil.rmtree(screenshot_dir)


TITLE_MAX = 20
ENVIRONMENT_LABEL_MAX = 10


def _fit(value, limit):
    """(text, was_cut) for a value hard-cut at `limit` characters.

    No ellipsis: the UI fades the tail instead, and `was_cut` is what tells it
    to.
    """
    value = str(value)

    return value[:limit], len(value) > limit


def custom_title(title):
    ConfigVars._title_full = str(title)
    ConfigVars._title, was_cut = _fit(title, TITLE_MAX)
    ConfigVars._title_class = "is-truncated" if was_cut else ""


def _plugin_versions(config):
    """Names and versions of the pytest plugins active for this run."""
    plugins = []

    for _, dist in config.pluginmanager.list_plugin_distinfo():
        name = getattr(dist, "project_name", None) or getattr(dist, "name", "")
        if not name:
            continue

        version = getattr(dist, "version", "")
        name = name.replace("pytest-", "")
        plugins.append(name + "-" + version if version else name)

    return sorted(set(plugins))


def _invocation_args(config):
    """The command line pytest was started with, minus the executable."""
    params = getattr(config, "invocation_params", None)
    args = getattr(params, "args", None) if params is not None else None

    return " ".join(args) if args else " ".join(sys.argv[1:])


def _ini(config, name):
    """An ini value, tolerating pytest builds where the key is unregistered."""
    try:
        return config.getini(name)
    except (AttributeError, ValueError, KeyError):
        return None


REPORT_PATH_DEFAULT = "."


def report_path(config):
    """Where the report is written. --html-report wins over the html_report ini key.

    The value is run through strftime, so date and time placeholders (%Y, %m,
    %d, %H, %M, ...) can name a folder or a file per run:

        --html-report=./reports/%Y%m%d/report_%H%M.html

    They are expanded once, while the run is being configured, so every process
    of an xdist run - and a run that crosses a minute boundary - writes to the
    same place.
    """
    path = str(config.getoption("path", None) or "").strip()

    if not path:
        path = str(_ini(config, "html_report") or "").strip()

    return expand_time(path or REPORT_PATH_DEFAULT)


# The directives strftime is documented to understand. Anything else after a
# % is left alone, so a path that simply happens to hold one - "100% pass" -
# survives being expanded.
TIME_DIRECTIVES = "aAbBcdfGHIjmMpSuUVwWxXyYzZ"

_DIRECTIVE = re.compile("%(.)", re.DOTALL)


def expand_time(path):
    """strftime `path` against now, leaving text that is not a directive alone.

    %% is the way to write a literal percent that sits in front of a letter.
    """
    if "%" not in path:
        return path

    now = datetime.now()

    def expand(match):
        directive = match.group(1)

        if directive == "%":
            return "%"

        if directive not in TIME_DIRECTIVES:
            return match.group(0)

        return now.strftime("%" + directive)

    return _DIRECTIVE.sub(expand, path)


def environment_name(config):
    """The environment under test. --environment wins over the ini key."""
    return str(config.getoption("environment", None) or _ini(config, "environment") or "").strip()


def environment_label(name):
    """(badge text, was_cut) for an environment name."""
    return _fit(name, ENVIRONMENT_LABEL_MAX)


def build_info(config):
    """(label, value) pairs from --build-info and the build_info ini key."""
    entries = list(config.getoption("build_info", None) or [])
    entries += list(_ini(config, "build_info") or [])

    pairs = []
    for entry in entries:
        entry = str(entry).strip()
        if not entry:
            continue

        key, _, value = entry.partition("=")
        pairs.append((key.strip(), value.strip()))

    return pairs


# A scheme of two characters or more, so a Windows drive letter - C:/reports -
# is read as the path it is rather than as a scheme this does not know.
_URL_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]+:")

SAFE_SCHEMES = ("http://", "https://", "mailto:")


def safe_link(url):
    """A url fit to put in the report's nav, or '' when it is not one.

    The nav is assembled out of whatever a command line said, and the report is
    a build artifact that gets published and passed round. A scheme this does
    not know - javascript:, data: - is dropped rather than rendered, so a nav
    entry cannot become a way to run something in whoever opens the page.
    Relative paths are left alone: linking ./htmlcov/index.html beside the
    report is the whole point of the option.
    """
    url = str(url).strip()

    if not url:
        return ""

    if _URL_SCHEME.match(url) and not url.lower().startswith(SAFE_SCHEMES):
        return ""

    return url


def report_links(config):
    """(label, url) pairs from --report-link and the report_link ini key.

    Issue #203 asked for the coverage html report inside this one. The answer
    to the general form of that - "let me reach my own pages from here" - is a
    link in the nav rather than a frame in the page: a frame would quietly
    empty itself the moment the report is mailed or published on its own,
    while a link that does not resolve at least says so in the address bar.
    """
    entries = list(config.getoption("report_link", None) or [])
    entries += list(_ini(config, "report_link") or [])

    links = []
    for entry in entries:
        label, _, url = str(entry).strip().partition("=")
        label = label.strip()
        url = safe_link(url)

        if label and url:
            links.append((label, url))

    return links


def link_patterns(config):
    """{marker name: url template} from --report-link-pattern and the ini key.

    This is what turns a marker into traceability. ``@pytest.mark.jira`` is
    already collected and already shown - it has been since markers landed -
    but as a flat badge, because nothing in the report knows that `PROJ-123`
    is an issue rather than a word. A pattern is that missing half::

        report_link_pattern =
            jira = https://acme.atlassian.net/browse/{}
            testcase = https://acme.testrail.io/index.php?/cases/view/{}

    Deliberately not a Jira client. The report is a static file that gets
    mailed, published and opened off a disk months later, and a badge that
    needs a token and a network to render is a badge that is blank in exactly
    those cases. A url template needs neither and never goes stale in a way
    that lies - a dead link says so in the address bar.

    A marker with no pattern keeps the badge it has today, so this is opt-in
    per marker and nothing changes for a suite that sets none.
    """
    entries = list(config.getoption("report_link_pattern", None) or [])
    entries += list(_ini(config, "report_link_pattern") or [])

    return parse_link_patterns(entries)


def parse_link_patterns(entries):
    """{marker name: url template} from MARKER=URL entries.

    Split from link_patterns because the merge command holds these as a list of
    strings off its own argv and never builds a config to ask.
    """
    patterns = {}

    for entry in entries:
        marker, _, template = str(entry).strip().partition("=")
        marker = marker.strip()

        # Through the same sieve the nav links go through, for the same reason
        # and then some: this one is built per test out of whatever a marker
        # said, so a report is only ever as safe as the schemes it will render.
        template = safe_link(template)

        if marker and template:
            patterns[marker] = template

    return patterns


def trace_markers(patterns):
    """The marker names that say what a test traces to rather than what it is.

    ``owner`` plus whatever report_link_pattern named. This is the set the
    JUnit xml writes as testcase properties: Xray, Zephyr and TestRail read a
    test's issue key from a property and none of them opens an html report, so
    an id that only ever reaches a badge is an id those tools cannot see.

    Sorted so that two runs of one suite differ by their results and not by the
    order a dict happened to hand back.
    """
    return [OWNER_MARKER, SEVERITY_MARKER] + sorted(patterns or {})


def marker_url(patterns, marker):
    """Where one marker points, or '' when it points nowhere.

    ``{}`` is where the marker's first argument goes, percent-encoded - an id
    is pasted from a tracker and arrives with whatever the tracker allows in
    one. A template with no ``{}`` is a fixed destination that the marker's
    presence links to, which is what ``docs = https://wiki/testing`` means; it
    is not an error and not a placeholder somebody forgot.

    Substituted rather than formatted. ``str.format`` reads every brace in the
    string, and a url is a place people put braces - a Confluence page id, a
    templated query - so formatting one throws KeyError on somebody's link
    rather than rendering it.
    """
    if not patterns: return ''

    template = patterns.get(marker.get('name'))
    if not template: return ''

    if '{}' not in template: return template

    args = marker.get('args') or []
    value = str(args[0]).strip() if args else ''

    # A bare ``@pytest.mark.jira`` with no id has nothing to put in the url,
    # and half a url is worse than none: it opens the tracker's front page and
    # looks like the link worked.
    if not value: return ''

    return template.replace('{}', quote(value, safe=''))


def record_owners(record):
    """Who owns one finished test, in the order the markers were written.

    Read off the record rather than off the item because everything that needs
    it runs long after the test did - the rail's filter, output.json, and the
    Analytics roll-up that reads that file back a build later.

    A test can have more than one owner and often does without anyone meaning
    it: ``pytestmark = pytest.mark.owner("platform")`` on the module and a
    second on the test itself both survive, because they are two different
    things to say and the report has never picked between two markers.
    """
    owners = []

    for marker in ((record.get('meta') or {}).get('markers') or []):
        if marker.get('kind') != OWNER_MARKER_KIND: continue

        args = marker.get('args') or []
        name = str(args[0]).strip() if args else ''

        if name and name not in owners: owners.append(name)

    return owners


def record_severity(record):
    """How much this test failing matters, or '' when nobody said.

    One value, unlike owners, because severity is a ladder and a test cannot be
    two heights at once - so where owners stack, severities have to be picked
    between. **The nearest one wins**: a class marked `critical` inside a module
    marked `normal` means somebody looked at that class and said it was worse
    than the rest of the file, and the outer word is the one being corrected.

    Two written at the same scope is the case with no obvious answer - nothing
    is nearer than anything else - so the worse of them is taken. Reading a
    `blocker` down to `minor` because of the order two decorators happen to sit
    in is the one mistake here that hides work.

    Nothing is invented when the marker is absent. Allure defaults an unmarked
    test to `normal`; this does not, because a suite where four tests are
    marked and six hundred are not is a suite with six hundred *unrated* tests,
    not six hundred normal ones, and drawing them as rated would bury the four.
    """
    levels = []

    for marker in ((record.get('meta') or {}).get('markers') or []):
        if marker.get('kind') != SEVERITY_MARKER_KIND: continue

        level = severity_value(marker)
        if level: levels.append((str(marker.get('scope') or ''), level))

    if not levels: return ''

    # The markers arrive nearest first, so the first scope seen is the nearest
    # one that said anything at all.
    nearest = levels[0][0]

    return min((level for scope, level in levels if scope == nearest), key=severity_rank)


def generate_link_patterns(config):
    """Resolve the patterns once, where the render can reach them.

    Left on ConfigVars rather than passed down because the Test Steps tab is
    built from ``build_report``, which runs before the render has a config in
    its hands, and the badge is drawn several frames below that. Same reason
    ``_step_limit`` lives there.
    """
    ConfigVars._link_patterns = link_patterns(config)


def generate_report_links(config):
    ConfigVars._report_links = "".join(
        str(ReportLink(label=escape_report_text(label), url=escape_report_text(url),
                       title=escape_report_text(url)))
        for label, url in report_links(config)
    )


# ini values that mean yes, for the flags whose command-line half is a
# store_true and whose ini half is whatever somebody typed.
_TRUTHY = ("1", "true", "yes", "on")


def report_packages_enabled(config):
    """Whether to list every installed distribution in the Environment panel.

    Off unless asked for. It is the only row that is three hundred entries
    long, and the only one that publishes a full dependency inventory into a
    file that gets attached to tickets and passed round - which is a fine thing
    to do deliberately and a poor thing to do to everybody by default.
    """
    if config.getoption("report_packages", None):
        return True

    return str(_ini(config, "report_packages") or "").strip().lower() in _TRUTHY


def env_rows(entries):
    """The Environment panel's rows, from (label, value[, url]) entries.

    An entry with a url renders as a link rather than as text, and the url goes
    through safe_link first: most of what this panel shows now comes from
    environment variables, and a CI system - or anything that can set one -
    must not be able to put a javascript: href into a report somebody opens.
    """
    rows = ""

    for entry in entries:
        label, value = entry[0], entry[1]
        url = safe_link(entry[2]) if len(entry) > 2 else ""
        value = str(value).strip() or "-"

        if url:
            rows += str(EnvLink(label=escape_report_text(label),
                                value=escape_report_text(value),
                                url=escape_report_text(url),
                                title=escape_report_text(url)))
        else:
            rows += str(EnvRow(label=escape_report_text(label),
                               value=escape_report_text(value),
                               title=escape_report_text(value)))

    return rows


def environment_entries(config, records=None):
    """Every (label, value[, url]) the panel shows for a run on this machine.

    Split out of generate_environment_info so that a shard can be described
    with the same answers the panel would have shown, and so the order of the
    rows is decided in one place: what ran (environment, build info, the CI run
    and the commit), then what it ran on (host, os, interpreter, workers), then
    what it was told to do (arguments, root) and finally what was installed.
    """
    plugins = _plugin_versions(config)
    root = getattr(config, "rootpath", None) or getattr(config, "rootdir", "")

    entries = []
    environment = environment_name(config)
    if environment:
        entries.append(("Environment", environment))

    named = build_info(config)
    entries += named

    # The build info is somebody's own answer about this run, so it wins: a
    # team that already publishes "branch=..." through --build-info gets one
    # Branch row, not that one and a second one from git disagreeing with it.
    given = {str(label).strip().lower() for label, _ in named}

    run = ci_run()
    if run and "ci" not in given:
        entries.append(("CI", run.summary))
    if run.url and "pipeline" not in given:
        entries.append(("Pipeline", run.url, run.url))

    branch, commit = git_revision(str(root))
    if branch and "branch" not in given:
        entries.append(("Branch", branch))
    if commit and "commit" not in given:
        entries.append(("Commit", commit))

    entries += [
        ("Captured output", capture_summary(config, report_logs_mode(config))),
        ("Host", platform.uname().node),
        ("Platform", os_summary()),
        ("Python", python_summary()),
        ("Interpreter", interpreter_path()),
        ("pytest", pytest.__version__),
        ("Plugins", ", ".join(plugins)),
    ]

    # Only under xdist. On a serial run there is one process and saying "1
    # worker" about it is a row that answers a question nobody asked.
    workers = worker_summary(config, records)
    if workers:
        entries.append(("Workers", workers))

    entries += [
        ("Arguments", _invocation_args(config)),
        ("Root", str(root)),
    ]

    if report_packages_enabled(config):
        packages = packages_row(installed_packages())
        if packages:
            entries.append(packages)

    entries.append(("Generated", datetime.now().strftime("%b %d %Y, %H:%M:%S")))

    return entries


def generate_environment_info(config, records=None):
    """Fill the Environment panel for a run that happened in this process.

    `records` is the reporter's own list, passed in only so the worker count is
    the number of processes that actually reported results rather than the
    number ``-n`` asked for. A caller that has none - the shim, a test - gets
    every other row unchanged.
    """
    ConfigVars._environment = environment_name(config)
    ConfigVars._environment_label, was_cut = environment_label(ConfigVars._environment)
    ConfigVars._environment_class = "is-truncated" if was_cut else ""

    ConfigVars._environment_rows = env_rows(environment_entries(config, records))

    return ConfigVars._environment_rows


LOG_PHASE_ORDER = ("setup", "call", "teardown")
LOG_KIND_ORDER = ("log", "stdout", "stderr")
LOG_MODES = ("all", "failed", "none")
LOG_LIMIT_DEFAULT = 10000


def report_logs_mode(config):
    """Which tests keep their captured output: 'all', 'failed' or 'none'."""
    mode = str(config.getoption("report_logs", None) or _ini(config, "report_logs") or "all").strip().lower()

    return mode if mode in LOG_MODES else "all"


def report_log_limit(config):
    """Characters of captured output kept per test; 0 means no limit."""
    value = config.getoption("report_log_limit", None)
    if value in (None, ""):
        value = _ini(config, "report_log_limit")

    try:
        limit = int(value)
    except (TypeError, ValueError):
        return LOG_LIMIT_DEFAULT

    return max(limit, 0)


ATTACHMENT_MODES = ("all", "failed", "none")
ATTACHMENT_LIMIT_DEFAULT = 20000


def report_attachments_mode(config):
    """Which tests keep their attachments: 'all', 'failed' or 'none'."""
    mode = str(config.getoption("report_attachments", None)
               or _ini(config, "report_attachments") or "all").strip().lower()

    return mode if mode in ATTACHMENT_MODES else "all"


def report_attachment_limit(config):
    """Characters kept per attached part; 0 means no limit."""
    value = config.getoption("report_attachment_limit", None)
    if value in (None, ""):
        value = _ini(config, "report_attachment_limit")

    try:
        limit = int(value)
    except (TypeError, ValueError):
        return ATTACHMENT_LIMIT_DEFAULT

    return max(limit, 0)


def report_screenshots_mode(config):
    """When the reporter photographs a browser by itself: 'failed', 'all', 'none'.

    Not what is kept. An image handed to ``attach`` is kept whatever this says
    - it was asked for - and this only governs the ones nobody asked for: the
    picture taken of a live Selenium driver or Playwright page at the end of a
    test that never mentioned screenshots at all.

    'failed' by default, which is the shape almost every suite writes by hand:
    photographing a run that passed is a lot of pictures of pages that were
    fine, and every one of them costs a round trip to the browser.
    """
    mode = str(config.getoption("report_screenshots", None)
               or _ini(config, "report_screenshots") or "failed").strip().lower()

    return mode if mode in SCREENSHOT_MODES else "failed"


STEP_MODES = ("all", "failed", "none")
STEP_LIMIT_DEFAULT = 500


def report_steps_mode(config):
    """Which tests keep their steps: 'all', 'failed' or 'none'.

    'all' rather than 'failed', unlike a log: the steps of a test that passed
    are what a later failure is read against, and they cost a line each.
    """
    mode = str(config.getoption("report_steps", None)
               or _ini(config, "report_steps") or "all").strip().lower()

    return mode if mode in STEP_MODES else "all"


def report_step_limit(config):
    """Steps kept per test; 0 means no limit.

    A test that loops a step over ten thousand rows would otherwise write ten
    thousand lines into the page, and the tree stops being readable long before
    it stops being generated.
    """
    value = config.getoption("report_step_limit", None)
    if value in (None, ""):
        value = _ini(config, "report_step_limit")

    try:
        limit = int(value)
    except (TypeError, ValueError):
        return STEP_LIMIT_DEFAULT

    return max(limit, 0)


def _log_section_rank(title):
    """Sort key that replays a test's output in the order it was produced.

    pytest names a section "Captured <kind> <phase>", so the phase orders the
    sections and the kind settles the ties within one phase.
    """
    parts = title.split()
    kind = parts[1] if len(parts) == 3 else ""
    phase = parts[-1] if parts else ""

    def rank(value, order):
        return order.index(value) if value in order else len(order)

    return rank(phase, LOG_PHASE_ORDER), rank(kind, LOG_KIND_ORDER), title


def merge_log_sections(buffer, sections):
    """Keep the latest capture of each of one test's sections.

    ``report.sections`` is cumulative - it carries every section pytest has
    recorded for the item so far - so a test retried by pytest-rerunfailures
    hands back the earlier attempts' output alongside the current one. Keying
    by section title and letting the last write win leaves the attempt that is
    actually being reported.
    """
    for title, content in sections:
        if content:
            buffer[str(title)] = str(content)


def trim_log_sections(sections, limit):
    """Cut a test's captured output down to `limit` characters in total.

    The tail is what survives: logs read chronologically, so the lines next to
    the failure matter more than the ones that opened the run. Without a cap a
    single chatty test can outweigh the rest of the report put together.
    """
    if limit <= 0:
        return sections

    total = sum(len(section["text"]) for section in sections)
    if total <= limit:
        return sections

    kept = []
    budget = limit
    for section in reversed(sections):
        text = section["text"]

        if len(text) <= budget:
            kept.append({"title": section["title"], "text": text})
            budget -= len(text)
            continue

        # The limit falls inside this section, so nothing before it survives.
        # Its tail is cut back to a line boundary: half a log line reads as
        # corruption rather than as a trim.
        text = text[-budget:] if budget > 0 else ""
        break_at = text.find("\n")
        if break_at != -1: text = text[break_at + 1:]

        if text: kept.append({"title": section["title"], "text": text})
        break

    kept.reverse()

    dropped = total - sum(len(section["text"]) for section in kept)
    if dropped:
        kept.insert(0, {
            "title": "Trimmed",
            "text": "%d earlier characters dropped - raise --report-log-limit to keep them." % dropped,
        })

    return kept


def format_log_sections(buffer, limit):
    """One test's captured output as ordered, trimmed [{'title', 'text'}]."""
    sections = [
        {"title": title, "text": buffer[title]}
        for title in sorted(buffer, key=_log_section_rank)
    ]

    return trim_log_sections(sections, limit)


def escape_report_text(value):
    """HTML-escape text on its way into the report page.

    ``%(`` is broken up as well: the page is assembled by substituting
    ``%(name)%`` placeholders, so a log line that happens to look like one
    would otherwise be filled in instead of shown. The entity renders as the
    character it replaces, so nothing changes on screen.
    """
    return escape(str(value)).replace("%(", "%&#40;")


# A node id made only of these characters can be pasted into a shell as it
# stands. Anything else is quoted: a parametrised id can hold a space, and the
# brackets one always holds are a glob pattern to zsh, which is the shell most
# of these get pasted into.
_BARE_NODEID = re.compile(r"^[A-Za-z0-9_@%+=:,./-]+$")


def rerun_command(nodeid):
    """The shell line that runs one test again, ready to paste.

    Built from the node id rather than from the suite and test names the row
    shows: those are what a person reads, and a test inside a class is listed
    as ``test_login`` where pytest wants ``TestAuth::test_login``.
    """
    target = str(nodeid or "").strip()
    if not target:
        return ""

    if not _BARE_NODEID.match(target):
        target = "'" + target.replace("'", "'\\''") + "'"

    return "pytest " + target


# Everything a URL fragment would have to escape - `::`, `[`, `]`, `/`, a space
# in a parameter - flattened to a dash. What is left is the part of a node id
# worth reading in a link, and it is what a chat window, a ticket and a shell
# all hand on unaltered.
_ANCHOR_UNSAFE = re.compile(r"[^a-z0-9]+")

# The readable half is cut here. A parametrised node id can run to hundreds of
# characters, and past a point none of them tell the reader anything the digits
# on the end do not. Set where a nested path and a sentence-long test name still
# both fit: the slug exists to be read, and a limit that cuts almost every one
# of them back to the directory it lives in would be no better than a bare hash.
_ANCHOR_SLUG_LIMIT = 72


def row_anchor(nodeid, suite="", name=""):
    """The id one test's row carries, for the ``#`` end of a link to it.

    Built from the node id, not from the row's place in the table: a link is
    pasted into a chat window and opened hours later, against whatever report
    is at that address by then. A positional anchor would still resolve - to
    whichever test has since taken that place - and open a different failure
    with no sign that it had.

    The six hex digits are taken from the whole node id rather than from the
    slug in front of them, so two tests whose slugs are cut to the same string,
    or that differ only in the punctuation the slug drops, keep anchors of
    their own.

    Named ``row_anchor`` rather than ``test_anchor`` because a test module
    importing it would have pytest collect the import itself as a test.
    """
    identity = str(nodeid or "").strip() or "::".join(
        part for part in (str(suite or "").strip(), str(name or "").strip()) if part
    )

    if not identity:
        return ""

    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:6]
    slug = _ANCHOR_UNSAFE.sub("-", identity.lower()).strip("-")

    # Cut back to a whole word, so the tail of a slug is never half a name.
    if len(slug) > _ANCHOR_SLUG_LIMIT:
        slug = slug[:_ANCHOR_SLUG_LIMIT].rsplit("-", 1)[0]

    return "-".join(part for part in ("test", slug, digest) if part)


def js_literal(value):
    """Render a value as a literal for the chart scripts inside the page.

    The dashboard charts are handed their labels as source code, so a suite
    named with an apostrophe used to end the array early and take the rest of
    that script block down with it - charts blank, and nothing to say why.
    ``<`` is written as an escape so a name cannot close the script tag either,
    and ``%(`` is broken up because the page is assembled by substituting
    ``%(name)%`` placeholders.
    """
    return (
        json.dumps(value)
        .replace("<", "\\u003c")
        .replace("%(", "%\\u0028")
    )


def _capture_is_off(config):
    """True when pytest is running with -s / --capture=no.

    Nothing the reporter can do brings stdout and stderr back: pytest never
    takes them in the first place, they go straight to the terminal.
    """
    return str(config.getoption("capture", None) or "") == "no"


def _log_level_name(config):
    """The level logging output has to reach to be captured at all.

    Unset, pytest's report handler takes everything the root logger emits -
    which is WARNING and above until something raises it.
    """
    level = config.getoption("log_level", None) or _ini(config, "log_level")
    if level:
        return str(level).upper()

    return logging.getLevelName(logging.getLogger().getEffectiveLevel())


def capture_summary(config, mode):
    """What this run keeps of each test's output - for the Environment panel."""
    if mode == "none":
        return "disabled (--report-logs=none)"

    scope = "all tests" if mode == "all" else "failed tests only"

    if _capture_is_off(config):
        streams = "logging only (stdout and stderr are off under -s)"
    else:
        streams = "stdout, stderr and logging"

    return "%s: %s, logging from %s" % (scope, streams, _log_level_name(config))


def capture_notice(config, mode):
    """Why the Logs column may be empty, or '' when there is nothing to say.

    A column of dashes reads as a broken feature. Almost always the cause is
    -s / --capture=no, and the only useful thing the report can do is say so
    where the empty column is being looked at.
    """
    if mode == "none" or not _capture_is_off(config):
        return ""

    return ("stdout and stderr are not captured while pytest runs with -s / --capture=no, "
            "so only logging output reaches this column")


def generate_logs_notice(config):
    ConfigVars._logs_notice = ""

    text = capture_notice(config, report_logs_mode(config))
    if text:
        ConfigVars._logs_notice = str(LogsNotice(text=escape_report_text(text)))


def count_log_lines(sections):
    """Lines of captured output, for the count shown on the row's button."""
    return sum(len(section["text"].splitlines()) for section in sections)


# --------------------------------------------------------------------------
# the rerun trail
# --------------------------------------------------------------------------


def attempt_seconds(value):
    """One attempt's duration as a number, from whatever the record carries.

    Tolerant rather than strict, for the reason normalise_record is: the
    attempts inside a bundle are checked as a list and not each one as a
    record, so a duration that cannot be read is a decoration on a panel and no
    reason to lose the report the tests have already paid for.
    """
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def attempt_summary(record):
    """One superseded attempt, reduced to what the trail shows.

    A fold keeps the attempt that stuck and nothing else, so the outcome of
    every attempt before it - which is the whole question a flaky test raises -
    has to be copied out before the survivor replaces it.

    Four fields rather than the record: a record carries its logs, screenshots,
    steps and attachments, and a shard bundle is the record list exactly as it
    stands in memory, so keeping whole attempts would multiply the size of
    every bundle a matrix uploads by the number of times its flakiest tests
    were retried. The panel renders these four and nothing else.
    """
    return {
        "status": str(record.get("status") or ""),
        "message": str(record.get("message") or ""),
        "duration": attempt_seconds(record.get("duration")),
        "worker": str(record.get("worker") or ""),
    }


def status_tone(status):
    """The class suffix a status is drawn with.

    The rule the table's own status pills are built with in the page's
    javascript - lowercased, letters only - repeated here so an attempt in the
    trail is the same colour as the row it belongs to. A status this version
    has never heard of reduces to something no rule matches, which is the
    neutral pill rather than an unstyled one.
    """
    return re.sub(r"[^a-z]", "", str(status or "").lower())


def attempt_trail(superseded, record):
    """The attempts behind one fold, oldest first.

    Either side may already stand for several - an xdist worker sends back a
    record folded on the worker, and a shard artifact carries one folded in the
    run that produced it - so both lists are kept and the record being replaced
    goes between them: it ran after its own attempts and before the one that is
    replacing it now.
    """
    return (list(superseded.get("attempts") or [])
            + [attempt_summary(superseded)]
            + list(record.get("attempts") or []))


# --------------------------------------------------------------------------
# delta vs the previous build
# --------------------------------------------------------------------------


def run_delta(counts):
    """This build's count against the build before it.

    Read off the same list the Trends chart is drawn from - this run first,
    then the archived builds newest first - so the headline on the summary
    card and the line on the chart beside it can never disagree. A first build
    has nothing to compare against and gets no delta rather than a delta of
    zero: "no change" would claim a previous build that does not exist.
    """
    if len(counts) < 2:
        return None

    try:
        return int(counts[0]) - int(counts[1])
    except (TypeError, ValueError):
        # An archived build written by a version that did not record this
        # count. Better to say nothing than to read the gap as a number.
        return None


def format_run_delta(delta, noun="failure"):
    """The whole line: '+3 failures since last build' / 'no change in failures'.

    The two cases are not one phrase plus a suffix. "no change" already says
    what it is being compared against, and the column the line sits in is
    narrow enough that spelling it out again wraps it onto a second row.
    """
    if delta is None:
        return ""

    if delta == 0:
        return "no change in %ss" % noun

    return "%+d %s since last build" % (
        delta, noun if abs(delta) == 1 else noun + "s")


def run_delta_class(delta):
    """Which direction is the good one. Fewer failures than last time is better.

    A first build has no delta and gets is-empty, which hides the whole tile:
    caption included, so there is no stray "SINCE LAST BUILD" over nothing.
    """
    if delta is None:
        return "is-empty"

    if delta > 0:
        return "is-worse"

    return "is-better" if delta < 0 else "is-level"


def run_delta_figure(delta):
    """The figure on the tile: '+3', '-1', or the words 'No change'.

    A moved count is written with its sign, because the tile is read as a
    delta rather than a total. A count that did not move is not written as a
    number at all: any figure here takes the unit beside it, and every way of
    pairing zero with "failures" - "0 failures", "\u00b10 failures" - says the
    opposite of what it means, that the build had no failures rather than no
    more than last time. The words carry no unit and cannot be misread.
    """
    if delta is None:
        return ""

    return "No change" if delta == 0 else "%+d" % delta


def run_delta_unit(delta, noun="failure"):
    """The word beside the figure, agreeing with it.

    Empty at no change: the figure there is already a whole phrase, and the
    noun is exactly the half that misleads - see run_delta_figure().
    """
    if delta is None or delta == 0:
        return ""

    return noun if abs(delta) == 1 else noun + "s"


def run_delta_title(counts, noun="failure"):
    """The two raw counts behind the delta, for the chip's tooltip.

    "+3 failures" reads very differently against 3 and against 300, and the
    figure it is a delta of is not the total count shown above it.
    """
    if run_delta(counts) is None:
        return ""

    current, previous = int(counts[0]), int(counts[1])

    return "%d %s this build, %d in the build before it" % (
        current, noun if current == 1 else noun + "s", previous)


def generate_run_delta():
    """Fill in the failure delta shown under the total count on the Dashboard.

    Failures here are what the Trends chart calls Failed - failures and errors
    together - because the two sit inches apart on the same page.
    """
    delta = run_delta(ConfigVars.tfail)

    ConfigVars._failure_delta_class = run_delta_class(delta)
    ConfigVars._failure_delta_figure = escape_report_text(run_delta_figure(delta))
    ConfigVars._failure_delta_unit = escape_report_text(run_delta_unit(delta))

    # The whole sentence, for the tile's tooltip alongside the two raw counts:
    # the tile itself is three fragments, and one of them read aloud on its own
    # says very little.
    ConfigVars._failure_delta = escape_report_text(format_run_delta(delta))
    ConfigVars._failure_delta_title = escape_report_text(
        run_delta_title(ConfigVars.tfail))


# --------------------------------------------------------------------------
# archive retention
# --------------------------------------------------------------------------

# Every archived build is named for the moment its run started -
# output_1788023855.926659.json - which is what makes an age limit possible.
ARCHIVE_STAMP = re.compile(r"_(\d+(?:\.\d+)?)\.json$")

SINCE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d")

DAY_SECONDS = 86400.0


def archive_count(config):
    """How many builds to keep, as text; '' when no limit is set.

    Text, not a number, because '' - keep everything - and '0' - keep nothing,
    not even the Archives section - are different answers, and both are asked
    about later.
    """
    value = config.getoption("archive_count", None)
    if value is None or str(value).strip() == "":
        value = _ini(config, "archive_count")

    if value is None:
        return ""

    value = str(value).strip()
    if value == "":
        return ""

    try:
        count = int(value)
    except ValueError:
        raise pytest.UsageError(
            "--archive-count takes a number of builds to keep, not %r" % value)

    if count < 0:
        raise pytest.UsageError(
            "--archive-count cannot be negative, got %r" % value)

    return str(count)


def archive_days(config):
    """Days of history to keep; None when no age limit is set."""
    value = config.getoption("archive_days", None)
    if value is None or str(value).strip() == "":
        value = _ini(config, "archive_days")

    if value is None or str(value).strip() == "":
        return None

    try:
        days = float(str(value).strip())
    except ValueError:
        raise pytest.UsageError(
            "--archive-days takes a number of days to keep, not %r" % value)

    if days < 0:
        raise pytest.UsageError(
            "--archive-days cannot be negative, got %r" % value)

    return days


def archive_since(config):
    """The oldest moment to keep, as an epoch; None when no date is set.

    Written as a date - 2026-06-01, meaning midnight local time that day - or
    as a date and a time, for a schedule that runs often enough to care.
    """
    value = config.getoption("archive_since", None)
    if value is None or str(value).strip() == "":
        value = _ini(config, "archive_since")

    if value is None:
        return None

    value = str(value).strip()
    if value == "":
        return None

    for fmt in SINCE_FORMATS:
        try:
            return datetime.strptime(value, fmt).timestamp()
        except ValueError:
            continue

    raise pytest.UsageError(
        "--archive-since takes a date, YYYY-MM-DD or 'YYYY-MM-DD HH:MM', not %r" % value)


def archive_cutoff(days=None, since=None, now=None):
    """The oldest moment kept, or None when neither age limit is set.

    Both set is the stricter of the two, so neither can widen the other.
    """
    cutoffs = []

    if days is not None:
        cutoffs.append((time.time() if now is None else now) - days * DAY_SECONDS)

    if since is not None:
        cutoffs.append(since)

    return max(cutoffs) if cutoffs else None


def archive_timestamp(path):
    """When the run that produced an archived build started.

    Read from the file's name, so the time survives a checkout into a CI
    workspace - where every file's mtime is the moment of the clone, and an
    age limit read from mtimes would keep everything for ever. The mtime is
    the fallback, for a file named by a version that named them differently.
    """
    match = ARCHIVE_STAMP.search(os.path.basename(path))

    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass

    return os.path.getmtime(path)


def expired_archives(paths, keep=None, cutoff=None):
    """Which of `paths` the retention limits do not keep, oldest first.

    The limits intersect: an archive has to be no older than `cutoff` *and*
    among the newest `keep` to survive. `keep` counts files on disk, so the
    caller subtracts the build being reported now, which is displayed
    alongside them.
    """
    stamped = sorted(((archive_timestamp(path), path) for path in paths),
                     key=lambda pair: pair[0])

    kept = stamped if cutoff is None else [pair for pair in stamped if pair[0] >= cutoff]

    if keep is not None:
        kept = kept[-keep:] if keep > 0 else []

    survivors = set(path for _, path in kept)

    return [path for _, path in stamped if path not in survivors]
