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


def pytest_configure(config):
    path = config.getoption("path")
    clean_screenshots(path)

    title = config.getoption("title")
    custom_title(title)
    
    archive_count = config.getoption("archive_count")

    config._html = HTMLReporter(path, archive_count, config)
    config.pluginmanager.register(config._html)


