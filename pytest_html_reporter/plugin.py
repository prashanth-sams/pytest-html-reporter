import pytest
import time
import os

from _pytest.runner import pytest_runtest_setup
from _pytest.runner import pytest_runtest_teardown
from pytest_html_reporter.template import html_template

_total = 0
_executed = 0
_pass = _fail = 0
_skip = _error = 0
_xpass = _xfail = 0
_current_error = ""
_suite_name = None
_test_name = None
_test_status = None
_test_start_time = None
_excution_time = 0
_test_metrics_content = ""
_suite_metrics_content = ""
_duration = 0
_previous_suite_name = "None"
_initial_trigger = True
_spass_tests = 0
_sfail_tests = 0
_sskip_tests = 0
_serror_tests = 0
_sxfail_tests = 0
_sxpass_tests = 0


def pytest_addoption(parser):
    group = parser.getgroup("report generator")
    group.addoption(
        "--html",
        action="store",
        dest="htmlpath",
        default=["."],
        help="path to generate html report",
    )


def pytest_configure(config):
    htmlpath = config.getoption("htmlpath")

    if htmlpath:
        HTMLReporter._report_location(htmlpath)
    else:
        pass


class HTMLReporter:

    def __init__(self, htmlpath):
        pass

    def _report_location(htmlpath):
        pass


    @pytest.hookimpl(hookwrapper=True)
    def pytest_terminal_summary(self, terminalreporter, exitstatus, config):
        yield

        report_file_name = "pytest_report.html"
        live_logs_file = open(report_file_name, 'w')
        message = self.get_updated_template_text('https://i.imgur.com/OdZIPpg.png')
        live_logs_file.write(message)
        live_logs_file.close()


    def get_updated_template_text(logo_url):
        template_text = html_template()
        template_text = template_text.replace("__custom_logo__", logo_url)
        template_text = template_text.replace("__execution_time__", str(round(_excution_time, 2)))
        # template_text = template_text.replace("__executed_by__", str(platform.uname()[1]))
        # template_text = template_text.replace("__os_name__", str(platform.uname()[0]))
        # template_text = template_text.replace("__python_version__", str(sys.version.split(' ')[0]))
        # template_text = template_text.replace("__generated_date__", str(datetime.datetime.now().strftime("%b %d %Y, %H:%M")))
        template_text = template_text.replace("__total__", str(_total))
        template_text = template_text.replace("__executed__", str(_executed))
        template_text = template_text.replace("__pass__", str(_pass))
        template_text = template_text.replace("__fail__", str(_fail))
        template_text = template_text.replace("__skip__", str(_skip))
        # template_text = template_text.replace("__error__", str(_error))
        template_text = template_text.replace("__xpass__", str(_xpass))
        template_text = template_text.replace("__xfail__", str(_xfail))
        template_text = template_text.replace("__suite_metrics_row__", str(_suite_metrics_content))
        template_text = template_text.replace("__test_metrics_row__", str(_test_metrics_content))
        return template_text