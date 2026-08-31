from pytest_html_reporter.html_reporter import HTMLReporter
from pytest_html_reporter.util import archive_count, clean_screenshots, custom_title, report_path


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
        "report_attachments",
        help="whose attachments to keep in the report: all, failed or none",
        default="",
    )

    parser.addini(
        "report_attachment_limit",
        help="maximum characters kept per attached payload; 0 keeps everything",
        default="",
    )


def pytest_configure(config):
    # Resolved once, and written back, so that anything reading the option
    # later - an xdist worker, which is handed a copy of these options - sees
    # the same expanded path this process settled on.
    path = report_path(config)
    config.option.path = path

    clean_screenshots(path)

    title = config.getoption("title")
    custom_title(title)
    
    config.pluginmanager.register(HTMLReporter(path, archive_count(config), config))
