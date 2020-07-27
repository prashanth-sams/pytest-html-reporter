import pytest
import os, time
from datetime import date
from pytest_html_reporter.template import html_template

_total = _executed = 0
_pass = _fail = 0
_skip = _error = 0
_xpass = _xfail = 0
_current_error = ""
_suite_name = _test_name = None
_test_suite_name = []
_test_pass_list = []
_test_fail_list = []
_test_skip_list = []
_test_xpass_list = []
_test_xfail_list = []
_test_error_list = []
_test_status = None
_test_start_time = None
_execution_time = _duration = 0
_test_metrics_content = _suite_metrics_content = ""
_previous_suite_name = "None"
_initial_trigger = True
_spass_tests = 0
_sfail_tests = 0
_sskip_tests = 0
_serror_tests = 0
_sxfail_tests = 0
_sxpass_tests = 0
_suite_length = 0


def pytest_addoption(parser):
    group = parser.getgroup("report generator")
    group.addoption(
        "--html",
        action="store",
        dest="path",
        default=".",
        help="path to generate html report",
    )


def pytest_configure(config):
    path = config.getoption("path")

    config._html = HTMLReporter(path, config)
    config.pluginmanager.register(config._html)


class HTMLReporter:

    def __init__(self, path, config):
        self.path = path
        self.config = config

    def pytest_runtest_teardown(self, item, nextitem):
        global _test_name
        _test_name = item.name

        self.append_test_metrics_row()


    def pytest_sessionfinish(self, session):
        self.append_suite_metrics_row(_suite_name)
        self.reset_counts()

    def report_path(self):
        logfile = os.path.expanduser(os.path.expandvars(self.path))
        return os.path.abspath(logfile)

    @pytest.hookimpl(hookwrapper=True)
    def pytest_terminal_summary(self, terminalreporter, exitstatus, config):
        yield

        global _execution_time
        _execution_time = time.time() - terminalreporter._sessionstarttime

        global _total
        _total = _pass + _fail + _xpass + _xfail + _skip + _error

        report_filename = "pytest_report.html"
        path = os.path.join(self.report_path(), report_filename)
        os.makedirs(self.report_path(), exist_ok=True)
        live_logs_file = open(path, 'w')
        message = self.renew_template_text('https://i.imgur.com/LRSRHJO.png')
        live_logs_file.write(message)
        live_logs_file.close()

    @pytest.hookimpl(tryfirst=True, hookwrapper=True)
    def pytest_runtest_makereport(self, item, call):
        outcome = yield
        rep = outcome.get_result()

        global _suite_name
        _suite_name = rep.nodeid.split("::")[0]

        if _initial_trigger:
            self.update_previous_suite_name()
            self.set_initial_trigger()

        if str(_previous_suite_name) != str(_suite_name):
            self.append_suite_metrics_row(_previous_suite_name)
            self.update_previous_suite_name()
            self.reset_counts()
        else:
            self.update_counts(rep)

        if rep.when == "call" and rep.passed:
            if hasattr(rep, "wasxfail"):
                self.increment_xpass()
                self.update_test_status("xPASS")
                global _current_error
                self.update_test_error("")
            else:
                self.increment_pass()
                self.update_test_status("PASS")
                self.update_test_error("")

        if rep.failed:
            if getattr(rep, "when", None) == "call":
                if hasattr(rep, "wasxfail"):
                    self.increment_xpass()
                    self.update_test_status("xPASS")
                    self.update_test_error("")
                else:
                    self.increment_fail()
                    self.update_test_status("FAIL")
                    if rep.longrepr:
                        for line in rep.longreprtext.splitlines():
                            exception = line.startswith("E   ")
                            if exception:
                                self.update_test_error(line.replace("E    ", ""))
            else:
                self.increment_error()
                self.update_test_status("ERROR")
                if rep.longrepr:
                    for line in rep.longreprtext.splitlines():
                        self.update_test_error(line)

        if rep.skipped:
            if hasattr(rep, "wasxfail"):
                self.increment_xfail()
                self.update_test_status("xFAIL")
                if rep.longrepr:
                    for line in rep.longreprtext.splitlines():
                        exception = line.startswith("E   ")
                        if exception:
                            self.update_test_error(line.replace("E    ", ""))
            else:
                self.increment_skip()
                self.update_test_status("SKIP")
                if rep.longrepr:
                    for line in rep.longreprtext.splitlines():
                        self.update_test_error(line)


    def append_test_metrics_row(self):
        test_row_text = """
            <tr>
                <td style="word-wrap: break-word;max-width: 200px; white-space: normal; text-align:left">__sname__</td>
                <td style="word-wrap: break-word;max-width: 200px; white-space: normal; text-align:left">__name__</td>
                <td>__stat__</td>
                <td>__dur__</td>
                <td style="word-wrap: break-word;max-width: 200px; white-space: normal; text-align:left"">__msg__</td>
            </tr>
        """
        test_row_text = test_row_text.replace("__sname__", str(_suite_name))
        test_row_text = test_row_text.replace("__name__", str(_test_name))
        test_row_text = test_row_text.replace("__stat__", str(_test_status))
        test_row_text = test_row_text.replace("__dur__", str(round(_duration, 2)))
        test_row_text = test_row_text.replace("__msg__", str(_current_error))

        global _test_metrics_content
        _test_metrics_content += test_row_text

    def append_suite_metrics_row(self, name):
        self._test_suites(name)
        self._test_passed(int(_spass_tests))
        self._test_failed(int(_sfail_tests))
        self._test_skipped(int(_sskip_tests))
        self._test_xpassed(int(_sxpass_tests))
        self._test_xfailed(int(_sxfail_tests))
        self._test_error(int(_serror_tests))

        suite_row_text = """
            <tr>
                <td style="word-wrap: break-word;max-width: 200px; white-space: normal; text-align:left">__sname__</td>
                <td>__spass__</td>
                <td>__sfail__</td>
                <td>__sskip__</td>
                <td>__sxpass__</td>
                <td>__sxfail__</td>
                <td>__serror__</td>
            </tr>
        """
        suite_row_text = suite_row_text.replace("__sname__", str(name))
        suite_row_text = suite_row_text.replace("__spass__", str(_spass_tests))
        suite_row_text = suite_row_text.replace("__sfail__", str(_sfail_tests))
        suite_row_text = suite_row_text.replace("__sskip__", str(_sskip_tests))
        suite_row_text = suite_row_text.replace("__sxpass__", str(_sxpass_tests))
        suite_row_text = suite_row_text.replace("__sxfail__", str(_sxfail_tests))
        suite_row_text = suite_row_text.replace("__serror__", str(_serror_tests))

    def set_initial_trigger(self):
        global _initial_trigger
        _initial_trigger = False

    def update_previous_suite_name(self):
        global _previous_suite_name
        _previous_suite_name = _suite_name

    def update_counts(self, rep):
        global _sfail_tests, _spass_tests, _sskip_tests, _serror_tests, _sxfail_tests, _sxpass_tests

        if rep.when == "call" and rep.passed:
            if hasattr(rep, "wasxfail"):
                _sxpass_tests += 1
            else:
                _spass_tests += 1

        if rep.failed:
            if getattr(rep, "when", None) == "call":
                if hasattr(rep, "wasxfail"):
                    _sxpass_tests += 1
                else:
                    _sfail_tests += 1
            else:
                _serror_tests += 1

        if rep.skipped:
            if hasattr(rep, "wasxfail"):
                _sxfail_tests += 1
            else:
                _sskip_tests += 1

    def reset_counts(self):
        global _sfail_tests, _spass_tests, _sskip_tests, _serror_tests, _sxfail_tests, _sxpass_tests
        _spass_tests = 0
        _sfail_tests = 0
        _sskip_tests = 0
        _serror_tests = 0
        _sxfail_tests = 0
        _sxpass_tests = 0

    def update_test_error(self, msg):
        global _current_error
        _current_error = msg

    def update_test_status(self, status):
        global _test_status
        _test_status = status

    def increment_xpass(self):
        global _xpass
        _xpass += 1

    def increment_xfail(self):
        global _xfail
        _xfail += 1

    def increment_pass(self):
        global _pass
        _pass += 1

    def increment_fail(self):
        global _fail
        _fail += 1

    def increment_skip(self):
        global _skip
        _skip += 1

    def increment_error(self):
        global _error, _serror_tests
        _error += 1
        _serror_tests += 1

    def _date(self):
        return date.today().strftime("%B %d, %Y")

    def _test_suites(self, name):
        global _test_suite_name
        _test_suite_name.append(name.split('/')[-1].replace('.py', ''))

    def _test_passed(self, value):
        global _test_pass_list
        _test_pass_list.append(value)

    def _test_failed(self, value):
        global _test_fail_list
        _test_fail_list.append(value)

    def _test_skipped(self, value):
        global _test_skip_list
        _test_skip_list.append(value)

    def _test_xpassed(self, value):
        global _test_xpass_list
        _test_xpass_list.append(value)

    def _test_xfailed(self, value):
        global _test_xfail_list
        _test_xfail_list.append(value)

    def _test_error(self, value):
        global _test_error_list
        _test_error_list.append(value)

    def renew_template_text(self, logo_url):
        template_text = html_template()
        template_text = template_text.replace("__custom_logo__", logo_url)
        template_text = template_text.replace("__execution_time__", str(round(_execution_time, 2)))
        # template_text = template_text.replace("__executed_by__", str(platform.uname()[1]))
        # template_text = template_text.replace("__os_name__", str(platform.uname()[0]))
        # template_text = template_text.replace("__python_version__", str(sys.version.split(' ')[0]))
        # template_text = template_text.replace("__generated_date__", str(datetime.datetime.now().strftime("%b %d %Y, %H:%M")))
        template_text = template_text.replace("__total__", str(_total))
        template_text = template_text.replace("__executed__", str(_executed))
        template_text = template_text.replace("__pass__", str(_pass))
        template_text = template_text.replace("__fail__", str(_fail))
        template_text = template_text.replace("__skip__", str(_skip))
        template_text = template_text.replace("__error__", str(_error))
        template_text = template_text.replace("__xpass__", str(_xpass))
        template_text = template_text.replace("__xfail__", str(_xfail))
        template_text = template_text.replace("__suite_metrics_row__", str(_suite_metrics_content))
        template_text = template_text.replace("__test_metrics_row__", str(_test_metrics_content))
        template_text = template_text.replace("__date__", str(self._date()))
        template_text = template_text.replace("__test_suites__", str(_test_suite_name))
        template_text = template_text.replace("__test_suite_length__", str(len(_test_suite_name)))
        template_text = template_text.replace("__test_suite_pass__", str(_test_pass_list))
        template_text = template_text.replace("__test_suites_fail__", str(_test_fail_list))
        template_text = template_text.replace("__test_suites_skip__", str(_test_skip_list))
        template_text = template_text.replace("__test_suites_xpass__", str(_test_xpass_list))
        template_text = template_text.replace("__test_suites_xfail__", str(_test_xfail_list))
        template_text = template_text.replace("__test_suites_error__", str(_test_error_list))
        return template_text