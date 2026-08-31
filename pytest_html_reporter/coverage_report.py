"""Read whatever coverage this run produced, for the report's Coverage tab.

Issue #203 asked for two things: the percentage as a ring on the page, and
either the coverage html report embedded or a section of its own. The numbers
are read and rendered natively here rather than ``htmlcov`` being framed into
the page, because an iframe would break the one property this reporter is built
around - the report is a single file that can be mailed, published as a CI
artifact or opened off a stick - and it would break *silently*, showing an
empty frame wherever the folder did not travel with it. The annotated source,
which is the half a summary genuinely cannot replace, is linked to instead, and
only when the folder is actually there to link to.

Nothing here is allowed to take a test run down. Coverage is a decoration on a
report about tests that have already finished, so every path out of this module
either returns data or returns None.
"""

import json
import math
import os
import tempfile
import xml.etree.ElementTree as ElementTree

from html_page.coverage_chip import CoverageChip
from html_page.coverage_row import CoverageRow
from html_page.coverage_tile import CoverageTile
from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.util import _ini, escape_report_text, js_literal

COVERAGE_MODES = ("auto", "none")

# Files listed in the table. A monorepo reports thousands, and each row is
# markup in a file that is meant to stay small enough to mail.
COVERAGE_LIMIT_DEFAULT = 500

# Characters of "12-15, 88, 91-140, ..." kept in a row.
MISSING_LINES_MAX = 90

# What is looked for when nothing names a file. Only deliberate report
# artifacts: a stray .coverage data file is often left over from a run days
# ago, and quietly reporting yesterday's number is worse than reporting none.
COVERAGE_FILENAMES = ("coverage.json", "coverage.xml")

# Where the ring changes colour when the project has not said where its own
# line is. 90 is "this is covered", 75 is "this is watched".
GRADE_BANDS = ((90.0, "strong"), (75.0, "fair"))


# --------------------------------------------------------------------------
# options
# --------------------------------------------------------------------------

def coverage_mode(config):
    """Whether the Coverage tab is built at all: 'auto' or 'none'."""
    mode = str(config.getoption("report_coverage", None)
               or _ini(config, "report_coverage") or "auto").strip().lower()

    return mode if mode in COVERAGE_MODES else "auto"


def coverage_file(config):
    """A coverage report named on the command line, or '' to go looking."""
    value = config.getoption("report_coverage_file", None)
    if value is None or str(value).strip() == "":
        value = _ini(config, "report_coverage_file")

    return str(value or "").strip()


def coverage_limit(config):
    """How many files the table lists; 0 lists every one of them."""
    value = config.getoption("report_coverage_limit", None)
    if value in (None, ""):
        value = _ini(config, "report_coverage_limit")

    try:
        limit = int(value)
    except (TypeError, ValueError):
        return COVERAGE_LIMIT_DEFAULT

    return max(limit, 0)


def coverage_target(config, cov=None):
    """The bar this project set for itself, as a percentage, or None.

    A project that runs with --cov-fail-under has already said where its line
    is, and colouring the ring against a number this plugin picked would put
    the report at odds with the build that just passed or failed on it.
    """
    value = getattr(getattr(cov, "config", None), "fail_under", None)

    if not value:
        try:
            value = config.getoption("cov_fail_under", None)
        except (AttributeError, ValueError):
            value = None

    try:
        target = float(value)
    except (TypeError, ValueError):
        return None

    return target if target > 0 else None


# --------------------------------------------------------------------------
# shaping
# --------------------------------------------------------------------------

def percent_of(covered, total):
    """A percentage, with an empty file counting as covered rather than as 0."""
    if total <= 0:
        return 100.0

    return round((float(covered) / float(total)) * 100.0, 2)


def coverage_grade(percent, target=None):
    """How the percentage is coloured: 'strong', 'fair' or 'low'."""
    if percent is None:
        return "low"

    # A hair of slack, so 79.999999999 against --cov-fail-under=80 does not
    # read as a failure in the report while the build itself passed.
    if target:
        return "strong" if percent + 1e-9 >= float(target) else "low"

    for floor, grade in GRADE_BANDS:
        if percent + 1e-9 >= floor:
            return grade

    return "low"


def format_lines(numbers):
    """Line numbers the way coverage.py writes them: '4, 7' and '12-15, 88'."""
    ranges = []
    start = previous = None

    for number in sorted(set(int(value) for value in numbers)):
        if start is None:
            start = previous = number
        elif number == previous + 1:
            previous = number
        else:
            ranges.append((start, previous))
            start = previous = number

    if start is not None:
        ranges.append((start, previous))

    return ", ".join(str(low) if low == high else "%d-%d" % (low, high)
                     for low, high in ranges)


def trim_lines(text, limit=MISSING_LINES_MAX):
    """Cut a long list of missing lines at a comma, never mid-range.

    "91-14" reads as a line range that does not exist; "91-140, ..." reads as
    a list that carries on, which is what it is.
    """
    if limit <= 0 or len(text) <= limit:
        return text

    kept = text[:limit].rsplit(",", 1)[0]

    return (kept or text[:limit]) + ", ..."


def relative_name(name, root):
    """A measured file's path as it reads in the repository.

    coverage.py reports absolute paths when it was pointed at absolute
    sources, and /home/runner/work/proj/proj/src/api.py is four directories of
    CI checkout in front of the only part that identifies the file.
    """
    name = str(name).replace("\\", "/")

    if not root or not os.path.isabs(name):
        return name

    root = str(root).replace("\\", "/").rstrip("/")

    if name.startswith(root + "/"):
        return name[len(root) + 1:]

    try:
        relative = os.path.relpath(name, root).replace("\\", "/")
    except ValueError:
        # A different drive on Windows: there is no relative path to give.
        return name

    return name if relative.startswith("..") else relative


def build_summary(files, percent, statements, covered, missing, excluded,
                  branches, branches_covered, partial, branch, generated,
                  limit=COVERAGE_LIMIT_DEFAULT):
    """One coverage run, shaped the way the page renders it.

    Files are ordered worst first, which is both the useful default for the
    table and the only defensible way to cut the list: a cap that kept the
    alphabetical head would hide exactly the files the tab is opened to find.
    """
    files = sorted(files, key=lambda entry: (entry["percent"], -entry["missing"], entry["name"]))
    files_total = len(files)

    if limit and files_total > limit:
        files = files[:limit]

    return {
        "percent": round(float(percent), 2),
        "statements": int(statements),
        "covered": int(covered),
        "missing": int(missing),
        "excluded": int(excluded),
        "branch": bool(branch),
        "branches": int(branches),
        "branches_covered": int(branches_covered),
        "partial": int(partial),
        "files": files,
        "files_total": files_total,
        "generated": str(generated or ""),
        "source": "",
        "source_path": "",
        "html": "",
    }


def summarize_json(document, root="", limit=COVERAGE_LIMIT_DEFAULT):
    """coverage.py's own json report, shaped for the page.

    ``percent_covered`` is taken as given rather than recomputed: with branch
    coverage on it already folds branches into the number, and it is the same
    total pytest-cov has just printed to the terminal. A report that disagrees
    with the terminal it was generated beside is a bug report waiting to be
    filed.
    """
    totals = document.get("totals") or {}
    meta = document.get("meta") or {}

    files = []
    for name, entry in (document.get("files") or {}).items():
        summary = entry.get("summary") or {}
        lines = format_lines(entry.get("missing_lines") or [])

        files.append({
            "name": relative_name(name, root),
            "percent": round(float(summary.get("percent_covered") or 0.0), 2),
            "statements": int(summary.get("num_statements") or 0),
            "covered": int(summary.get("covered_lines") or 0),
            "missing": int(summary.get("missing_lines") or 0),
            "excluded": int(summary.get("excluded_lines") or 0),
            "branches": int(summary.get("num_branches") or 0),
            "branches_covered": int(summary["covered_branches"])
            if summary.get("covered_branches") is not None
            else int(summary.get("num_branches") or 0) - int(summary.get("num_partial_branches") or 0),
            "partial": int(summary.get("num_partial_branches") or 0),
            "lines": trim_lines(lines),
        })

    return build_summary(
        files=files,
        percent=totals.get("percent_covered") or 0.0,
        statements=totals.get("num_statements") or 0,
        covered=totals.get("covered_lines") or 0,
        missing=totals.get("missing_lines") or 0,
        excluded=totals.get("excluded_lines") or 0,
        branches=totals.get("num_branches") or 0,
        # Named only by newer coverage; older releases report the branch total
        # and the partial count and leave the covered figure to be worked out.
        branches_covered=totals.get("covered_branches")
        if totals.get("covered_branches") is not None
        else int(totals.get("num_branches") or 0) - int(totals.get("num_partial_branches") or 0),
        partial=totals.get("num_partial_branches") or 0,
        branch=bool(meta.get("branch_coverage")),
        generated=meta.get("timestamp") or "",
        limit=limit,
    )


def _condition_coverage(value):
    """(taken, total) out of a Cobertura condition-coverage="50% (1/2)"."""
    if not value or "(" not in value:
        return 0, 0

    try:
        taken, _, total = value.rsplit("(", 1)[1].rstrip(")").partition("/")
        return int(taken), int(total)
    except (ValueError, IndexError):
        return 0, 0


def summarize_xml(element, root="", limit=COVERAGE_LIMIT_DEFAULT):
    """A Cobertura coverage.xml, shaped for the page.

    This is the one path that needs no coverage.py installed at all, which is
    what makes it the useful one in CI: the xml is already being produced for
    Codecov or SonarQube, and the reporter can read the same artifact.
    """
    files = []
    branch_seen = False

    for node in element.iter("class"):
        statements = covered = branches = branches_covered = partial = 0
        missing_lines = []

        for line in node.iter("line"):
            statements += 1
            number = int(line.get("number") or 0)

            if int(line.get("hits") or 0) > 0:
                covered += 1
            else:
                missing_lines.append(number)

            if str(line.get("branch") or "").lower() != "true":
                continue

            branch_seen = True
            taken, total = _condition_coverage(line.get("condition-coverage"))
            branches += total
            branches_covered += taken
            if 0 < taken < total:
                partial += 1

        files.append({
            "name": relative_name(node.get("filename") or node.get("name") or "", root),
            "percent": percent_of(covered + branches_covered, statements + branches),
            "statements": statements,
            "covered": covered,
            "missing": len(missing_lines),
            "excluded": 0,
            "branches": branches,
            "branches_covered": branches_covered,
            "partial": partial,
            "lines": trim_lines(format_lines(missing_lines)),
        })

    def total(name):
        try:
            return int(element.get(name) or 0)
        except ValueError:
            return 0

    statements = total("lines-valid")
    covered = total("lines-covered")
    branches = total("branches-valid")
    branches_covered = total("branches-covered")

    return build_summary(
        files=files,
        # The same formula coverage.py uses, so a report read from the xml and
        # one read from the live run agree on the headline number.
        percent=percent_of(covered + branches_covered, statements + branches),
        statements=statements,
        covered=covered,
        missing=statements - covered,
        excluded=0,
        branches=branches,
        branches_covered=branches_covered,
        partial=sum(entry["partial"] for entry in files),
        branch=branch_seen or branches > 0,
        generated="",
        limit=limit,
    )


# --------------------------------------------------------------------------
# sources
# --------------------------------------------------------------------------

def live_coverage(config):
    """The Coverage object pytest-cov ran, or None.

    Read rather than raced for. pytest-cov stops, saves and combines its data
    from ``pytest_runtestloop`` - including every xdist worker's share - and
    that is long finished by the time this report is written out of
    ``pytest_terminal_summary``, so no extra hook and no ordering declaration
    is needed to be sure the data is complete.
    """
    manager = getattr(config, "pluginmanager", None)

    try:
        if manager is None or not manager.hasplugin("_cov"):
            return None
        plugin = manager.getplugin("_cov")
    except Exception:
        return None

    controller = getattr(plugin, "cov_controller", None)

    return getattr(controller, "cov", None) if controller is not None else None


def json_from_coverage(cov):
    """coverage.py's own json report for a Coverage object, or None.

    Through the public ``json_report`` API, which writes to a path rather than
    to a file object - hence the temporary file. Reaching into
    ``coverage.jsonreport`` would save the round trip and lose the guarantee
    that matters: these are the numbers coverage.py itself would publish.
    """
    handle, path = tempfile.mkstemp(prefix="pytest-html-reporter-", suffix=".json")
    os.close(handle)

    try:
        cov.json_report(outfile=path)
        with open(path, encoding="utf-8") as report:
            return json.load(report)
    except Exception:
        # "No data to report", a coverage too old to write json, an unreadable
        # data file. None of it is worth failing a finished test run over.
        return None
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def annotated_html(cov, base, since=None):
    """A relative link to coverage.py's own html report, or ''.

    The annotated source is the half of htmlcov a summary cannot replace, so
    it is worth crossing to - as a link, which keeps this report one file. The
    path is relative to where the report is written, so the two travel
    together or the link is simply not offered.

    `since` is when this run started, and the folder has to have been written
    after it. coverage.py names the folder whether or not --cov-report=html
    was asked for, so an htmlcov left over from a run last week is sitting
    there looking exactly like a fresh one - and annotations that disagree
    with the summary beside them are worse than no link at all.
    """
    directory = getattr(getattr(cov, "config", None), "html_dir", "") or ""
    if not directory:
        return ""

    index = os.path.join(directory, "index.html")
    if not os.path.isfile(index):
        return ""

    if since is not None and os.path.getmtime(index) < float(since):
        return ""

    try:
        return os.path.relpath(os.path.abspath(index), os.path.abspath(base)).replace("\\", "/")
    except ValueError:
        return ""


def read_coverage_path(path, root="", limit=COVERAGE_LIMIT_DEFAULT):
    """A coverage report read off disk, or None when it is not one.

    The kind is sniffed from the first byte rather than from the extension:
    CI hands these files whatever name the pipeline felt like, and '<' or '{'
    settles it in a way that '.xml' does not.
    """
    path = os.path.expanduser(os.path.expandvars(str(path)))
    if not os.path.isfile(path):
        return None

    try:
        with open(path, "rb") as handle:
            head = handle.read(4096).lstrip()[:1]

        if head == b"<":
            summary = summarize_xml(ElementTree.parse(path).getroot(), root, limit)
        elif head == b"{":
            with open(path, encoding="utf-8") as handle:
                summary = summarize_json(json.load(handle), root, limit)
        else:
            summary = summarize_data_file(path, root, limit)
    except Exception:
        return None

    if summary is None:
        return None

    summary["source"] = os.path.basename(path)
    summary["source_path"] = path

    return summary


def summarize_data_file(path, root="", limit=COVERAGE_LIMIT_DEFAULT):
    """A .coverage sqlite data file, via coverage.py, or None without it."""
    try:
        import coverage
    except ImportError:
        return None

    cov = coverage.Coverage(data_file=path)
    cov.load()
    document = json_from_coverage(cov)

    return summarize_json(document, root, limit) if document else None


def discover_coverage(directories, root="", limit=COVERAGE_LIMIT_DEFAULT):
    """The first coverage report found beside the report or at the repo root."""
    seen = set()

    for directory in directories:
        directory = os.path.abspath(str(directory or "."))
        if directory in seen:
            continue
        seen.add(directory)

        for name in COVERAGE_FILENAMES:
            summary = read_coverage_path(os.path.join(directory, name), root, limit)
            if summary:
                return summary

    return None


def has_data(summary):
    """Whether a summary describes a run that measured anything at all.

    An empty report is worth nothing and reads as 100%: coverage.py calls a
    file with no statements fully covered, and so a run that measured no files
    would otherwise open a Coverage tab announcing a perfect score.
    """
    return bool(summary) and (summary["statements"] > 0 or summary["files_total"] > 0)


def measured_nothing_notice(cov):
    """Why a run that did measure coverage has none to show.

    Almost always --cov names something that is never imported: a directory
    that does not exist, or an import name that does not match the package.
    coverage.py says so in a warning, which scrolls past with the rest of the
    run; the report says it where the empty tab is being looked at. Telling
    somebody to install pytest-cov and pass --cov when they have just done
    both is the least useful thing this page could do.
    """
    sources = [str(source) for source in
               (getattr(getattr(cov, "config", None), "source", None) or [])]

    advice = ("--cov takes the import name or the path of the code under test - "
              "the package, not the tests and not a folder that is not there.")

    if sources:
        # Echoed back as the flag that was typed, so the sentence names the
        # thing to go and change rather than describing it.
        return ("pytest-cov ran but measured nothing: %s matched nothing that was imported "
                "while the tests ran. %s"
                % (" ".join("--cov=" + source for source in sources), advice))

    return "pytest-cov ran but measured nothing. %s" % advice


def collect_coverage(config, base, since=None):
    """(summary, notice) - what the Coverage tab shows, and why it may be empty.

    A failure to read is reported into the page rather than raised: by the time
    this runs the tests are over, and a UsageError at that point would turn a
    green run red over a decoration. The tab is where somebody is looking for
    the coverage that is missing, so that is where the reason goes.
    """
    if coverage_mode(config) == "none":
        return None, ""

    root = str(getattr(config, "rootpath", "") or getattr(config, "rootdir", "") or "")
    limit = coverage_limit(config)

    named = coverage_file(config)
    if named:
        summary = read_coverage_path(named, root, limit)
        if has_data(summary):
            return summary, ""

        return None, ("--report-coverage-file pointed at %s, and nothing there could be read "
                      "as coverage data." % named)

    cov = live_coverage(config)
    if cov is not None:
        summary = summarize_json(json_from_coverage(cov) or {}, root, limit)
        if has_data(summary):
            summary["source"] = "pytest-cov"
            summary["html"] = annotated_html(cov, base, since)
            return summary, ""

    summary = discover_coverage([base, root, os.getcwd()], root, limit)
    if has_data(summary):
        return summary, ""

    # Only once nothing else has turned any up: a run whose own measurement
    # came back empty may still have a report on disk worth showing.
    if cov is not None:
        return None, measured_nothing_notice(cov)

    return None, ""


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

# The ring is drawn at r=52 in a 120x120 box, and its dash array is worked out
# from the real circumference rather than declared with pathLength: browser
# support for pathLength on a basic shape is younger than the report needs to
# assume, and a ring that silently draws full is worse than no ring.
RING_RADIUS = 52.0
RING_LENGTH = 2.0 * math.pi * RING_RADIUS


def ring_dash(percent):
    """The stroke-dasharray that draws `percent` of the ring."""
    filled = max(0.0, min(100.0, float(percent))) / 100.0 * RING_LENGTH

    return "%.2f %.2f" % (filled, RING_LENGTH)


def format_percent(value):
    """A percentage with one decimal, and none at all when it is round."""
    text = "%.1f" % float(value)

    return text[:-2] if text.endswith(".0") else text


def coverage_delta(percents):
    """This build's coverage against the last build that measured any.

    Read off the same list the trend chart is drawn from - this run first, then
    the archived builds newest first - so the headline and the chart can never
    disagree. A build that ran without coverage is skipped rather than counted
    as a drop to zero.
    """
    if not percents or percents[0] is None:
        return None

    for previous in percents[1:]:
        if previous is not None:
            return round(float(percents[0]) - float(previous), 2)

    return None


def format_delta(delta):
    """'+0.8' / '-1.2' / 'no change' for the chip beside the ring."""
    if delta is None:
        return ""

    if abs(delta) < 0.05:
        return "no change"

    return "%+.1f" % delta


def source_line(summary):
    """One sentence saying where these numbers came from, and when.

    Worth the line: a coverage.json left behind by a run three days ago reads
    exactly like a fresh one until the report says which it is.
    """
    source = summary.get("source") or "coverage"

    if source == "pytest-cov":
        return "Measured by pytest-cov during this run"

    generated = str(summary.get("generated") or "")
    if generated:
        generated = generated.replace("T", " ")[:16]
        return "Read from %s, written %s" % (source, generated)

    return "Read from %s" % source


def coverage_tiles(summary):
    """The stat tiles under the ring, in the order they are worth reading."""
    tiles = [
        ("Statements", summary["statements"]),
        ("Covered", summary["covered"]),
        ("Missing", summary["missing"]),
        ("Files", summary["files_total"]),
    ]

    # Only when branch coverage was actually switched on: a Branches 0/0 tile
    # says nothing except that the reader should have passed --cov-branch.
    if summary["branch"] and summary["branches"]:
        tiles.append(("Branches", "%d/%d" % (summary["branches_covered"], summary["branches"])))
        tiles.append(("Partial", summary["partial"]))

    if summary["excluded"]:
        tiles.append(("Excluded", summary["excluded"]))

    return "".join(str(CoverageTile(label=escape_report_text(label), value=escape_report_text(value)))
                   for label, value in tiles)


def coverage_rows(summary, target=None):
    """One table row per measured file."""
    rows = ""

    for entry in summary["files"]:
        rows += str(CoverageRow(
            name=escape_report_text(entry["name"]),
            statements=str(entry["statements"]),
            missing=str(entry["missing"]),
            branches=str(entry["branches"]),
            # A dash, not a 0: this file has no branches to cover, which is not
            # the same statement as "none of its branches are covered".
            branch_cell=("%d/%d" % (entry["branches_covered"], entry["branches"])
                         if entry["branches"] else "&mdash;"),
            percent="%.2f" % entry["percent"],
            display=format_percent(entry["percent"]),
            grade=coverage_grade(entry["percent"], target),
            lines=escape_report_text(entry["lines"]),
        ))

    return rows


def cap_note(summary, limit):
    """Why the table is shorter than the run, when it is."""
    if not limit or summary["files_total"] <= limit:
        return ""

    return ("Listing %d of %d files, least covered first - pass --report-coverage-limit=0 "
            "to list them all." % (limit, summary["files_total"]))


def generate_coverage_view(config):
    """Fill in everything the Coverage tab and its dashboard chip render.

    Called with ConfigVars._coverage already holding what collect_coverage
    found, and ConfigVars.tcoverage already holding this build's percentage
    followed by the archived builds' - the same list the Trends chart is built
    from.
    """
    summary = ConfigVars._coverage

    ConfigVars._coverage_state = "is-empty"
    ConfigVars._coverage_chip = ""
    ConfigVars._coverage_rows = ""
    ConfigVars._coverage_tiles = ""
    ConfigVars._coverage_display = "0"
    ConfigVars._coverage_dash = ring_dash(0)
    ConfigVars._coverage_grade = "low"
    ConfigVars._coverage_meta = ""
    ConfigVars._coverage_delta = ""
    ConfigVars._coverage_delta_class = ""
    ConfigVars._coverage_target = ""
    ConfigVars._coverage_link = ""
    ConfigVars._coverage_note = ""
    ConfigVars._coverage_branch = "false"
    ConfigVars._coverage_trend_labels = "[]"
    ConfigVars._coverage_trend_values = "[]"
    ConfigVars._coverage_trend_state = "no-trend"

    if not summary:
        return

    target = coverage_target(config, live_coverage(config))
    grade = coverage_grade(summary["percent"], target)
    display = format_percent(summary["percent"])

    ConfigVars._coverage_state = "has-coverage"
    ConfigVars._coverage_display = display
    ConfigVars._coverage_dash = ring_dash(summary["percent"])
    ConfigVars._coverage_grade = grade
    ConfigVars._coverage_tiles = coverage_tiles(summary)
    ConfigVars._coverage_rows = coverage_rows(summary, target)
    ConfigVars._coverage_meta = escape_report_text(source_line(summary))
    ConfigVars._coverage_note = escape_report_text(cap_note(summary, coverage_limit(config)))
    ConfigVars._coverage_branch = "true" if summary["branch"] and summary["branches"] else "false"

    if target:
        ConfigVars._coverage_target = "target %s%%" % format_percent(target)

    delta = coverage_delta(ConfigVars.tcoverage)
    if delta is not None:
        ConfigVars._coverage_delta = escape_report_text(format_delta(delta) + " since the last build")
        ConfigVars._coverage_delta_class = "is-up" if delta > 0.05 else ("is-down" if delta < -0.05 else "is-level")

    if summary["html"]:
        ConfigVars._coverage_link = escape_report_text(summary["html"])

    ConfigVars._coverage_chip = str(CoverageChip(
        grade=grade,
        display=display,
        title=escape_report_text("%s of %d statements covered" % (display + "%", summary["statements"])),
    ))

    # Oldest first, which is the direction a trend is read in. The Trends chart
    # on the dashboard puts this run first; that ordering is its own and is
    # left alone rather than copied into a chart that is about drift over time.
    labels = list(reversed(ConfigVars.trends_label))
    values = list(reversed(ConfigVars.tcoverage))

    if len([value for value in values if value is not None]) > 1:
        ConfigVars._coverage_trend_state = "has-trend"
        ConfigVars._coverage_trend_labels = js_literal(labels)
        ConfigVars._coverage_trend_values = js_literal(values)
