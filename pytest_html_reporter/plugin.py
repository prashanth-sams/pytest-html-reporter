import os
import sys

import pytest

from pytest_html_reporter.html_reporter import HTMLReporter
from pytest_html_reporter.junit import junit_path
from pytest_html_reporter.shards import (
    report_shard,
    report_shard_merge,
    report_shard_reset,
    report_shard_run,
    reset_shard_dir,
    sanitise_id,
    shard_dir,
    shards_root,
)
from pytest_html_reporter.markers import OWNER_MARKER, SEVERITY_LEVELS, SEVERITY_MARKER
from pytest_html_reporter.util import (
    archive_count,
    clean_screenshots,
    custom_title,
    link_patterns,
    report_path,
)


def report_base(path):
    """The folder a --html-report value writes into, before there is a reporter.

    pytest_configure has to know where a shard's own directory goes, and it has
    to settle it before HTMLReporter is even constructed. This mirrors the
    directory half of HTMLReporter.report_path deliberately line for line,
    oddities included - including the `'.html' in path` test that treats a
    folder called ./my.html.d as a file - because the two answers naming
    different folders is far worse than either of them being surprising: the
    shard would clean one directory and then write its screenshots into
    another, and the merge would find a bundle whose images were not there.
    """
    if '.html' in path:
        folder = '.' if '.html' in path.rsplit('/', 1)[0] else path.rsplit('/', 1)[0]
        if folder == '': folder = '.'
    else:
        folder = path

    return os.path.abspath(os.path.expanduser(os.path.expandvars(folder)))


def pytest_addoption(parser):
    group = parser.getgroup("report generator")

    group.addoption(
        "--html-report",
        action="store",
        dest="path",
        default="",
        help="path to generate html report; date and time placeholders (%%Y, %%m, "
             "%%d, %%H, %%M, ...) are expanded, e.g. ./reports/%%Y%%m%%d/report_%%H%%M.html",
    )

    group.addoption(
        "--title",
        action="store",
        dest="title",
        default="PYTEST REPORT",
        help="customize report title",
    )

    group.addoption(
        "--archive-count",
        action="store",
        dest="archive_count",
        default="",
        help="set maximum build count to display in the archives section",
    )

    group.addoption(
        "--archive-days",
        action="store",
        dest="archive_days",
        default="",
        metavar="DAYS",
        help="keep only the builds run in the last DAYS days; older archived "
             "builds are deleted",
    )

    group.addoption(
        "--archive-since",
        action="store",
        dest="archive_since",
        default="",
        metavar="DATE",
        help="delete every archived build older than DATE, given as 2026-06-01 "
             "or '2026-06-01 09:00'",
    )

    group.addoption(
        "--environment",
        action="store",
        dest="environment",
        default=None,
        help="name the environment under test, e.g. staging or prod",
    )

    group.addoption(
        "--build-info",
        action="append",
        dest="build_info",
        default=[],
        metavar="KEY=VALUE",
        help="extra key=value detail to show in the report; repeat for more",
    )

    group.addoption(
        "--report-logs",
        action="store",
        dest="report_logs",
        default=None,
        choices=("all", "failed", "none"),
        help="whose captured stdout, stderr and logging output to keep in the report: "
             "all (default), failed or none",
    )

    group.addoption(
        "--report-log-limit",
        action="store",
        dest="report_log_limit",
        default=None,
        type=int,
        help="maximum characters of captured output kept per test; 0 keeps everything "
             "(default: 10000)",
    )

    group.addoption(
        "--report-attachments",
        action="store",
        dest="report_attachments",
        default=None,
        choices=("all", "failed", "none"),
        help="whose attachments - text, json and API calls handed to attach_text(), "
             "attach_json() or attach_api() - to keep in the report: all (default), "
             "failed or none",
    )

    group.addoption(
        "--report-attachment-limit",
        action="store",
        dest="report_attachment_limit",
        default=None,
        type=int,
        help="maximum characters kept per attached payload; 0 keeps everything "
             "(default: 20000)",
    )

    group.addoption(
        "--report-screenshots",
        action="store",
        dest="report_screenshots",
        default=None,
        choices=("failed", "all", "none"),
        help="when to photograph a live Selenium driver or Playwright page "
             "without the suite asking: failed (default), all or none; images "
             "handed to attach() are always kept",
    )

    group.addoption(
        "--report-steps",
        action="store",
        dest="report_steps",
        default=None,
        choices=("all", "failed", "none"),
        help="whose test steps - the pieces named with step(), and the "
             "Given/When/Then of a pytest-bdd scenario - to keep in the "
             "report: all (default), failed or none",
    )

    group.addoption(
        "--report-step-limit",
        action="store",
        dest="report_step_limit",
        default=None,
        type=int,
        help="maximum steps kept per test; 0 keeps every one (default: 500)",
    )

    group.addoption(
        "--report-coverage",
        action="store",
        dest="report_coverage",
        default=None,
        choices=("auto", "none"),
        help="whether to build the Coverage tab from whatever coverage this run "
             "produced: auto (default) or none",
    )

    group.addoption(
        "--report-coverage-file",
        action="store",
        dest="report_coverage_file",
        default=None,
        metavar="PATH",
        help="read coverage from this file - a coverage.json, a Cobertura "
             "coverage.xml or a .coverage data file - instead of looking for one",
    )

    group.addoption(
        "--report-coverage-limit",
        action="store",
        dest="report_coverage_limit",
        default=None,
        type=int,
        help="maximum files listed on the Coverage tab, least-covered first; "
             "0 lists every one (default: 500)",
    )

    group.addoption(
        "--report-link",
        action="append",
        dest="report_link",
        default=[],
        metavar="LABEL=URL",
        help="add a link to the report's side nav, e.g. "
             "'Coverage=htmlcov/index.html'; repeat for more",
    )

    group.addoption(
        "--report-link-pattern",
        action="append",
        dest="report_link_pattern",
        default=[],
        metavar="MARKER=URL",
        help="turn a marker into a link on the test it is written on, e.g. "
             "'jira=https://acme.atlassian.net/browse/{}'; {} is where the "
             "marker's argument goes; repeat for more",
    )

    group.addoption(
        "--report-open",
        action="store",
        dest="report_open",
        default=None,
        choices=("auto", "always", "none"),
        help="whether to open the finished report in a browser: auto (default - "
             "on an interactive run with a desktop to open into), always or none",
    )

    group.addoption(
        "--report-shard",
        action="store",
        dest="report_shard",
        default="",
        metavar="ID",
        help="name this process as one leg of a sharded run, e.g. 1/4; it writes "
             "its records to <report>/shards/<ID> and no report of its own, for "
             "'pytest-html-reporter merge' to turn into one build",
    )

    group.addoption(
        "--report-shard-merge",
        action="store_true",
        dest="report_shard_merge",
        default=False,
        help="after writing this leg's shard, merge every shard beside it and "
             "render one report; for sequential legs on one machine, so three "
             "runs need three commands rather than four",
    )

    group.addoption(
        "--report-shard-run",
        action="store",
        dest="report_shard_run",
        default="",
        metavar="TOKEN",
        help="name the CI run this leg belongs to, so that a --report-shard-merge "
             "leg merges only the shards of this run; taken from the CI system's "
             "own variables when it is not given",
    )

    group.addoption(
        "--report-shard-reset",
        action="store_true",
        dest="report_shard_reset",
        default=False,
        help="delete <report>/shards before this leg writes into it, so a leg that "
             "was renamed or removed since the last run cannot leave a bundle "
             "behind for this run to merge; for the first leg of a sequential run",
    )

    group.addoption(
        "--report-junit",
        action="store",
        dest="report_junit",
        default="",
        metavar="PATH",
        help="also write a JUnit xml of this run to PATH, for a CI system that "
             "reads xml; date and time placeholders (%%Y, %%m, %%d, %%H, %%M, "
             "...) are expanded",
    )

    group.addoption(
        "--report-junit-xpass",
        action="store",
        dest="report_junit_xpass",
        default=None,
        choices=("pass", "fail", "skip"),
        help="how an xpassed test is written to the JUnit xml: pass (default, "
             "which is what pytest's own --junitxml does), fail or skip",
    )

    group.addoption(
        "--report-packages",
        action="store_true",
        dest="report_packages",
        default=False,
        help="list every installed distribution and its version in the "
             "Environment panel, the way pip freeze would; off by default "
             "because it is a few hundred entries nobody reads until the day "
             "the report is the only record of what was installed",
    )

    parser.addini(
        "html_report",
        help="path to generate html report; date and time placeholders (%Y, %m, "
             "%d, %H, %M, ...) are expanded, e.g. ./reports/%Y%m%d/report_%H%M.html",
        default="",
    )

    parser.addini(
        "archive_count",
        help="maximum build count to display in the archives section",
        default="",
    )

    parser.addini(
        "archive_days",
        help="keep only the builds run in the last N days",
        default="",
    )

    parser.addini(
        "archive_since",
        help="delete every archived build older than this date, e.g. 2026-06-01",
        default="",
    )

    parser.addini(
        "environment",
        help="name the environment under test, e.g. staging or prod",
        default="",
    )

    parser.addini(
        "build_info",
        type="linelist",
        help="extra key=value details to show in the report, one per line",
    )

    parser.addini(
        "report_logs",
        help="whose captured output to keep in the report: all, failed or none",
        default="",
    )

    parser.addini(
        "report_log_limit",
        help="maximum characters of captured output kept per test; 0 keeps everything",
        default="",
    )

    parser.addini(
        "report_coverage",
        help="whether to build the Coverage tab: auto or none",
        default="",
    )

    parser.addini(
        "report_coverage_file",
        help="read coverage from this file instead of looking for one",
        default="",
    )

    parser.addini(
        "report_coverage_limit",
        help="maximum files listed on the Coverage tab; 0 lists every one",
        default="",
    )

    parser.addini(
        "report_link",
        type="linelist",
        help="extra links to show in the report's side nav, one LABEL=URL per line",
    )

    parser.addini(
        "report_link_pattern",
        type="linelist",
        help="turn a marker into a link on the test it is written on, one "
             "MARKER=URL per line, where {} is the marker's argument",
    )

    parser.addini(
        "report_open",
        help="whether to open the finished report in a browser: auto, always or none",
        default="",
    )

    parser.addini(
        "report_screenshots",
        help="when to photograph a live browser without the suite asking: "
             "failed, all or none",
        default="",
    )

    parser.addini(
        "report_steps",
        help="whose test steps to keep in the report: all, failed or none",
        default="",
    )

    parser.addini(
        "report_step_limit",
        help="maximum steps kept per test; 0 keeps every one",
        default="",
    )

    parser.addini(
        "report_attachments",
        help="whose attachments to keep in the report: all, failed or none",
        default="",
    )

    parser.addini(
        "report_attachment_limit",
        help="maximum characters kept per attached payload; 0 keeps everything",
        default="",
    )

    parser.addini(
        "report_shard",
        help="name this run as one leg of a sharded run, e.g. 1/4; it writes its "
             "records under the report folder and no report of its own",
        default="",
    )

    parser.addini(
        "report_shard_merge",
        help="whether this leg also merges every shard beside it and renders one "
             "report: 1, true, yes or on",
        default="",
    )

    parser.addini(
        "report_shard_run",
        help="name the CI run this leg belongs to, so that a merging leg merges "
             "only the shards of this run",
        default="",
    )

    parser.addini(
        "report_shard_reset",
        help="whether this leg deletes <report>/shards before writing into it: "
             "1, true, yes or on",
        default="",
    )

    parser.addini(
        "report_junit",
        help="also write a JUnit xml of this run to this path",
        default="",
    )

    parser.addini(
        "report_junit_xpass",
        help="how an xpassed test is written to the JUnit xml: pass, fail or skip",
        default="",
    )

    parser.addini(
        "report_packages",
        help="list every installed distribution in the Environment panel (true/false)",
        default="",
    )


def register_markers(config):
    """Tell pytest about the markers this plugin gives a meaning to.

    Without this, ``--strict-markers`` rejects a suite for using the very
    markers the report was configured to read, and every run without it prints
    a PytestUnknownMarkWarning per test per marker - which is the plugin
    telling somebody their working configuration is a typo.

    The pattern markers are registered from the configuration rather than from
    a list here, because which names mean something is the user's decision:
    they named them in report_link_pattern.
    """
    config.addinivalue_line(
        "markers", "%s(name): who to tell when this test fails" % OWNER_MARKER)
    config.addinivalue_line(
        "markers", "%s(level): how much a failure here matters - one of %s"
                   % (SEVERITY_MARKER, ", ".join(SEVERITY_LEVELS)))

    for marker in link_patterns(config):
        config.addinivalue_line(
            "markers", "%s(id): link this test to %s" % (marker, marker))


def pytest_configure(config):
    # Named before anything is collected, so that a suite using them is not
    # warned about - or, under --strict-markers, refused - for markers this
    # plugin asked it to write.
    register_markers(config)

    # Resolved once, and written back, so that anything reading the option
    # later - an xdist worker, which is handed a copy of these options - sees
    # the same expanded path this process settled on.
    path = report_path(config)
    config.option.path = path

    # Settled here, before the reporter exists, because the answer decides
    # which folder gets emptied below - and getting that wrong empties a
    # sibling shard's screenshots. sanitise_id is called for its usage error:
    # an id made entirely of separators comes out empty, and a shard with an
    # empty id would write over the report base itself.
    shard = report_shard(config)
    shard_id = sanitise_id(shard)

    # Written back for the same reason as the path above: an xdist worker is
    # handed a copy of these options and has to file its screenshots in this
    # shard's folder. The raw value is what travels, not the sanitised one -
    # sanitising is deterministic, so the worker derives the same directory
    # either way, while the raw value is also the label the merged report
    # shows for this leg, and "1/4" reads better there than "1-4".
    config.option.report_shard = shard
    config.option.report_shard_merge = report_shard_merge(config)

    # Resolved and written back for the same reason again, and once: the token
    # is written into this leg's bundle and compared against every other
    # bundle's by a merging leg, so every process of this run has to answer the
    # same one - including an xdist worker, which is a separate process with a
    # separate environment handed a copy of these options.
    config.option.report_shard_run = report_shard_run(config)

    if config.option.report_shard_merge and not shard_id:
        raise pytest.UsageError(
            "--report-shard-merge needs --report-shard to name this shard")

    # Before the leg's own directory is dealt with, because this takes that
    # directory with it. Asked for on the first leg of a sequential run and
    # nowhere else: the legs of one run are pointed at one persistent
    # --html-report, so <base>/shards accumulates, and a leg that was renamed
    # or dropped since the last run leaves a bundle behind that the next
    # --report-shard-merge would report as part of this build - six tests when
    # four ran. Not implied by --report-shard or --report-shard-merge, and
    # deliberately not: it deletes the other legs' work.
    if report_shard_reset(config):
        reset_shard_dir(shards_root(report_base(path)))

    if shard_id:
        # Only this leg's own directory, never the whole report folder: the
        # legs of one matrix are told to write into one --html-report, and a
        # second leg that swept the folder clean would take the first leg's
        # screenshots with it and leave the merge with records naming pictures
        # that are no longer there.
        #
        # The whole directory rather than clean_screenshots' pytest_screenshots
        # subfolder, because the bundle is in there too: a records.json from a
        # previous run of this same leg would otherwise survive, and if that
        # run collected more tests than this one does, its records are what the
        # merge reads.
        reset_shard_dir(shard_dir(report_base(path), shard_id))

        # A shard that is not also the merge leg renders nothing, so it would
        # write no xml either - said out loud rather than silently, because
        # the alternative a CI author expects is four shard xmls plus the
        # merged one, and a `**/*.xml` glob that found all five would count
        # every test in the matrix twice.
        if junit_path(config) and not config.option.report_shard_merge:
            sys.stderr.write(
                "pytest-html-reporter: --report-junit is ignored on a shard; "
                "pass --junit-xml to `pytest-html-reporter merge`, or run this "
                "leg with --report-shard-merge\n")
    else:
        clean_screenshots(path)

    title = config.getoption("title")
    custom_title(title)
    
    config.pluginmanager.register(HTMLReporter(path, archive_count(config), config))
