from pytest_html_reporter.html_reporter import HTMLReporter
from pytest_html_reporter.util import clean_screenshots, custom_title


def pytest_addoption(parser):
    group = parser.getgroup("report generator")

    group.addoption(
        "--html-report",
        action="store",
        dest="path",
        default=".",
        help="path to generate html report",
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


def pytest_configure(config):
    path = config.getoption("path")
    clean_screenshots(path)

    title = config.getoption("title")
    custom_title(title)
    
    archive_count = config.getoption("archive_count")

    config._html = HTMLReporter(path, archive_count, config)
    config.pluginmanager.register(config._html)


