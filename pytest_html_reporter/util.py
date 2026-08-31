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
from io import BytesIO

import pytest
from PIL import Image

from html_page.env_row import EnvRow
from html_page.logs_notice import LogsNotice
from html_page.report_link import ReportLink
from pytest_html_reporter.const_vars import ConfigVars


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


def screenshot(data=None):
    from pytest_html_reporter.html_reporter import HTMLReporter

    # Pillow fails on a string with "cannot identify image file", which says
    # nothing about the mistake actually made now that the package also has
    # helpers that do take text.
    if isinstance(data, str):
        raise TypeError(
            "attach() takes the bytes of an image; to attach text use "
            "attach_text(), attach_json() or attach_api() instead"
        )

    ConfigVars.screen_base = HTMLReporter.base_path
    ConfigVars.screen_img = Image.open(BytesIO(data))


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


def generate_report_links(config):
    ConfigVars._report_links = "".join(
        str(ReportLink(label=escape_report_text(label), url=escape_report_text(url),
                       title=escape_report_text(url)))
        for label, url in report_links(config)
    )


def generate_environment_info(config):
    uname = platform.uname()
    plugins = _plugin_versions(config)
    root = getattr(config, "rootpath", None) or getattr(config, "rootdir", "")

    ConfigVars._environment = environment_name(config)
    ConfigVars._environment_label, was_cut = environment_label(ConfigVars._environment)
    ConfigVars._environment_class = "is-truncated" if was_cut else ""

    entries = []
    if ConfigVars._environment:
        entries.append(("Environment", ConfigVars._environment))
    entries += build_info(config)

    entries += [
        ("Captured output", capture_summary(config, report_logs_mode(config))),
        ("Host", uname.node),
        ("Platform", (uname.system + " " + uname.release).strip()),
        ("Python", platform.python_version()),
        ("pytest", pytest.__version__),
        ("Plugins", ", ".join(plugins)),
        ("Arguments", _invocation_args(config)),
        ("Root", str(root)),
        ("Generated", datetime.now().strftime("%b %d %Y, %H:%M:%S")),
    ]

    rows = ""
    for label, value in entries:
        value = str(value).strip() or "-"
        rows += str(EnvRow(label=escape_report_text(label), value=escape_report_text(value),
                           title=escape_report_text(value)))

    ConfigVars._environment_rows = rows


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
