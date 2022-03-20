import pytest
import os, time
import sys
from datetime import date, datetime
from pytest_html_reporter.template import html_template
from pytest_html_reporter.time_converter import time_converter
from os.path import isfile, join
import json
import glob
from collections import Counter
from PIL import Image
from io import BytesIO
import shutil

_total = _executed = 0
_pass = _fail = 0
_skip = _error = 0
_xpass = _xfail = 0
_apass = _afail = 0
_askip = _aerror = 0
_axpass = _axfail = 0
_astotal = 0
_aspass = 0
_asfail = 0
_asskip = 0
_aserror = 0
_asxpass = 0
_asxfail = 0
_asrerun = 0
_current_error = ""
_suite_name = _test_name = None
_scenario = []
_test_suite_name = []
_test_pass_list = []
_test_fail_list = []
_test_skip_list = []
_test_xpass_list = []
_test_xfail_list = []
_test_error_list = []
_test_status = None
_start_execution_time = 0
_execution_time = _duration = 0
_test_metrics_content = _suite_metrics_content = ""
_previous_suite_name = "None"
_initial_trigger = True
_spass_tests = 0
_sfail_tests = 0
_sskip_tests = 0
_serror_tests = 0
_srerun_tests = 0
_sxfail_tests = 0
_sxpass_tests = 0
_suite_length = 0
_archive_tab_content = ""
_archive_body_content = ""
_archive_count = ""
archive_pass = 0
archive_fail = 0
archive_skip = 0
archive_xpass = 0
archive_xfail = 0
archive_error = 0
archives = {}
highlights = {}
p_highlights = {}
max_failure_suite_name = ''
max_failure_suite_name_final = ''
max_failure_suite_count = 0
similar_max_failure_suite_count = 0
max_failure_total_tests = 0
max_failure_percent = ''
trends_label = []
tpass = []
tfail = []
tskip = []
_previous_test_name = ''
_suite_error = 0
_suite_fail = 0
_pvalue = 0
screen_base = ''
screen_img = None
_attach_screenshot_details = ''
_title = 'PYTEST REPORT'


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


def pytest_configure(config):
    path = config.getoption("path")
    clean_screenshots(path)

    title = config.getoption("title")
    custom_title(title)

    config._html = HTMLReporter(path, config)
    config.pluginmanager.register(config._html)


def suite_highlights(data):
    global highlights, p_highlights

    for i in data['content']['suites']:
        if data['content']['suites'][i]['status']['total_fail'] == 0:
            l = data['content']['suites'][i]['suite_name']
            if l not in p_highlights:
                p_highlights[l] = 1
            else:
                p_highlights[l] += 1
        else:
            k = data['content']['suites'][i]['suite_name']

            if k not in highlights:
                highlights[k] = 1
            else:
                highlights[k] += 1


def generate_suite_highlights():
    global max_failure_suite_name, max_failure_suite_count, similar_max_failure_suite_count, max_failure_total_tests
    global max_failure_percent, max_failure_suite_name_final

    if highlights == {}:
        max_failure_suite_name_final = 'No failures in History'
        max_failure_suite_count = 0
        max_failure_percent = '0'
        return

    max_failure_suite_name = max(highlights, key=highlights.get)
    max_failure_suite_count = highlights[max_failure_suite_name]

    if max_failure_suite_name in p_highlights:
        max_failure_total_tests = p_highlights[max_failure_suite_name] + max_failure_suite_count
    else:
        max_failure_total_tests = max_failure_suite_count

    max_failure_percent = (max_failure_suite_count / max_failure_total_tests) * 100

    if max_failure_suite_name.__len__() > 25:
        max_failure_suite_name_final = ".." + max_failure_suite_name[-23:]
    else:
        max_failure_suite_name_final = max_failure_suite_name

    res = Counter(highlights.values())
    if max(res.values()) > 1: similar_max_failure_suite_count = max(res.values())


def max_rerun():
    indices = [i for i, s in enumerate(sys.argv) if 'reruns' in s]

    try:
        if "=" in sys.argv[int(indices[0])]:
            return int(sys.argv[int(indices[0])].split('=')[1])
        else:
            return int(sys.argv[int(indices[0]) + 1])
    except IndexError:
        return None


def screenshot(data=None):
    global screen_base, screen_img

    screen_base = HTMLReporter.base_path
    screen_img = Image.open(BytesIO(data))


def clean_screenshots(path):
    screenshot_dir = os.path.abspath(os.path.expanduser(os.path.expandvars(path))) + '/pytest_screenshots'
    if os.path.isdir(screenshot_dir):
        shutil.rmtree(screenshot_dir)


def custom_title(title):
    global _title
    
    _title = title[:26] + '...' if title.__len__() > 29 else title


class HTMLReporter(object):
    def __init__(self, path, config):
        self.json_data = {'content': {'suites': {0: {'status': {}, 'tests': {0: {}}, }, }}}
        self.path = path
        self.config = config
        has_rerun = config.pluginmanager.hasplugin("rerunfailures")
        self.rerun = 0 if has_rerun else None

    def pytest_runtest_teardown(self, item, nextitem):
        global _test_name, _duration
        _test_name = item.name

        _test_end_time = time.time()
        _duration = _test_end_time - _start_execution_time

        if (self.rerun is not None) and (max_rerun() is not None): self.previous_test_name(_test_name)
        self._test_names(_test_name)
        self.append_test_metrics_row()

    def previous_test_name(self, _test_name):
        global _previous_test_name

        if _previous_test_name == _test_name:
            self.rerun += 1
        else:
            _scenario.append(_test_name)
            self.rerun = 0
            _previous_test_name = _test_name

    def pytest_runtest_setup(item):
        global _start_execution_time
        _start_execution_time = time.time()

    def pytest_sessionfinish(self, session):
        if _suite_name is not None: self.append_suite_metrics_row(_suite_name)

    def archive_data(self, base, filename):
        path = os.path.join(base, filename)

        if os.path.isfile(path) is True:
            os.makedirs(base + '/archive', exist_ok=True)
            f = 'output.json'

            if isfile(join(base, f)):
                fname = os.path.splitext(f)
                os.rename(base + '/' + f, os.path.join(base + '/archive', fname[0] + '_' +
                                                       str(_start_execution_time) + fname[1]))

    @property
    def report_path(self):
        if '.html' in self.path:
            path = '.' if '.html' in self.path.rsplit('/', 1)[0] else self.path.rsplit('/', 1)[0]
            if path == '': path = '.'
            logfile = os.path.expanduser(os.path.expandvars(path))
            HTMLReporter.base_path = os.path.abspath(logfile)
            return os.path.abspath(logfile), self.path.split('/')[-1]
        else:
            logfile = os.path.expanduser(os.path.expandvars(self.path))
            HTMLReporter.base_path = os.path.abspath(logfile)
            return os.path.abspath(logfile), 'pytest_html_report.html'

    @pytest.hookimpl(hookwrapper=True)
    def pytest_terminal_summary(self, terminalreporter, exitstatus, config):
        yield

        global _execution_time
        _execution_time = time.time() - terminalreporter._sessionstarttime

        if _execution_time < 60:
            _execution_time = str(round(_execution_time, 2)) + " secs"
        else:
            _execution_time = str(time.strftime("%H:%M:%S", time.gmtime(round(_execution_time)))) + " Hrs"

        global _total
        _total = _pass + _fail + _xpass + _xfail + _skip + _error

        if _suite_name is not None:
            base = self.report_path[0]
            path = os.path.join(base, self.report_path[1])

            os.makedirs(base, exist_ok=True)
            self.archive_data(base, self.report_path[1])

            # generate json file
            self.generate_json_data(base)

            # generate trends
            self.update_trends(base)

            # generate archive template
            self.update_archives_template(base)

            # generate suite highlights
            generate_suite_highlights()

            # generate html report
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
                        longerr = ""
                        for line in rep.longreprtext.splitlines():
                            exception = line.startswith("E   ")
                            if exception:
                                longerr += line + "\n"
                        self.update_test_error(longerr.replace("E    ", ""))
            else:
                self.increment_error()
                self.update_test_status("ERROR")
                if rep.longrepr:
                    longerr = ""
                    for line in rep.longreprtext.splitlines():
                        longerr += line + "\n"
                    self.update_test_error(longerr)

        if rep.skipped:
            if hasattr(rep, "wasxfail"):
                self.increment_xfail()
                self.update_test_status("xFAIL")
                if rep.longrepr:
                    longerr = ""
                    for line in rep.longreprtext.splitlines():
                        exception = line.startswith("E   ")
                        if exception:
                            longerr += line + "\n"
                    self.update_test_error(longerr.replace("E    ", ""))
            else:
                self.increment_skip()
                self.update_test_status("SKIP")
                if rep.longrepr:
                    longerr = ""
                    for line in rep.longreprtext.splitlines():
                        longerr += line + "\n"
                    self.update_test_error(longerr)

    def append_test_metrics_row(self):
        global _test_metrics_content, _pvalue, _duration

        test_row_text = """
            <tr>
                <td style="word-wrap: break-word;max-width: 200px; white-space: normal; text-align:left">__sname__</td>
                <td style="word-wrap: break-word;max-width: 200px; white-space: normal; text-align:left">__name__</td>
                <td>__stat__</td>
                <td>__dur__</td>
                <td style="word-wrap: break-word;max-width: 200px; white-space: normal; text-align:left"">
                    __msg__
                    __floating_error_text__
                </td>
            </tr>
        """

        floating_error_text = """
            <a data-toggle="modal" href="#myModal-__runt__" class="">(...)</a>
            <div class="modal fade in" id="myModal-__runt__" tabindex="-1" role="dialog" aria-labelledby="myModalLabel" aria-hidden="true">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-body">
                            <p>
                                <svg xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false" width="1.12em" height="1em" style="-ms-transform: rotate(360deg); -webkit-transform: rotate(360deg); transform: rotate(360deg);" preserveAspectRatio="xMidYMid meet" viewBox="0 0 1856 1664"><path d="M1056 1375v-190q0-14-9.5-23.5t-22.5-9.5H832q-13 0-22.5 9.5T800 1185v190q0 14 9.5 23.5t22.5 9.5h192q13 0 22.5-9.5t9.5-23.5zm-2-374l18-459q0-12-10-19q-13-11-24-11H818q-11 0-24 11q-10 7-10 21l17 457q0 10 10 16.5t24 6.5h185q14 0 23.5-6.5t10.5-16.5zm-14-934l768 1408q35 63-2 126q-17 29-46.5 46t-63.5 17H160q-34 0-63.5-17T50 1601q-37-63-2-126L816 67q17-31 47-49t65-18t65 18t47 49z" fill="#DC143C"/></svg>
                                __full_msg__
                            </p>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-primary" data-dismiss="modal">Close</button>
                        </div>
                    </div>
                </div>
            </div>
        """

        if (self.rerun is not None) and (max_rerun() is not None):
            if (_test_status == 'FAIL') or (_test_status == 'ERROR'): _pvalue += 1

            if (_pvalue == max_rerun() + 1) or (_test_status == 'PASS'):
                if ((_test_status == 'FAIL') or (_test_status == 'ERROR')) and (
                        screen_base != ''): self.generate_screenshot_data()

                test_row_text = test_row_text.replace("__sname__", str(_suite_name))
                test_row_text = test_row_text.replace("__name__", str(_test_name))
                test_row_text = test_row_text.replace("__stat__", str(_test_status))
                test_row_text = test_row_text.replace("__dur__", str(round(_duration, 2)))
                test_row_text = test_row_text.replace("__msg__", str(_current_error[:50]))
                floating_error_text = floating_error_text.replace("__runt__", str(time.time()).replace('.', ''))

                if len(_current_error) < 49:
                    test_row_text = test_row_text.replace("__floating_error_text__", str(''))
                else:
                    test_row_text = test_row_text.replace("__floating_error_text__", str(floating_error_text))
                    test_row_text = test_row_text.replace("__full_msg__", str(_current_error))


                _test_metrics_content += test_row_text
                _pvalue = 0
            elif (self.rerun is not None) and (
                    (_test_status == 'xFAIL') or (_test_status == 'xPASS') or (_test_status == 'SKIP')):
                test_row_text = test_row_text.replace("__sname__", str(_suite_name))
                test_row_text = test_row_text.replace("__name__", str(_test_name))
                test_row_text = test_row_text.replace("__stat__", str(_test_status))
                test_row_text = test_row_text.replace("__dur__", str(round(_duration, 2)))
                test_row_text = test_row_text.replace("__msg__", str(_current_error[:50]))
                floating_error_text = floating_error_text.replace("__runt__", str(time.time()).replace('.', ''))

                if len(_current_error) < 49:
                    test_row_text = test_row_text.replace("__floating_error_text__", str(''))
                else:
                    test_row_text = test_row_text.replace("__floating_error_text__", str(floating_error_text))
                    test_row_text = test_row_text.replace("__full_msg__", str(_current_error))

                _test_metrics_content += test_row_text

        elif (self.rerun is None) or (max_rerun() is None):
            if ((_test_status == 'FAIL') or (_test_status == 'ERROR')) and (
                    screen_base != ''): self.generate_screenshot_data()

            test_row_text = test_row_text.replace("__sname__", str(_suite_name))
            test_row_text = test_row_text.replace("__name__", str(_test_name))
            test_row_text = test_row_text.replace("__stat__", str(_test_status))
            test_row_text = test_row_text.replace("__dur__", str(round(_duration, 2)))
            test_row_text = test_row_text.replace("__msg__", str(_current_error[:50]))
            floating_error_text = floating_error_text.replace("__runt__", str(time.time()).replace('.', ''))

            if len(_current_error) < 49:
                test_row_text = test_row_text.replace("__floating_error_text__", str(''))
            else:
                test_row_text = test_row_text.replace("__floating_error_text__", str(floating_error_text))
                test_row_text = test_row_text.replace("__full_msg__", str(_current_error))

            _test_metrics_content += test_row_text

        self.json_data['content']['suites'].setdefault(len(_test_suite_name), {})['suite_name'] = str(_suite_name)
        self.json_data['content']['suites'].setdefault(len(_test_suite_name), {}).setdefault('tests', {}).setdefault(
            len(_scenario) - 1, {})['status'] = str(_test_status)
        self.json_data['content']['suites'].setdefault(len(_test_suite_name), {}).setdefault('tests', {}).setdefault(
            len(_scenario) - 1, {})['message'] = str(_current_error)
        self.json_data['content']['suites'].setdefault(len(_test_suite_name), {}).setdefault('tests', {}).setdefault(
            len(_scenario) - 1, {})['test_name'] = str(_test_name)

        if (self.rerun is not None) and (max_rerun() is not None):
            self.json_data['content']['suites'].setdefault(len(_test_suite_name), {}).setdefault('tests',
                                                                                                 {}).setdefault(
                len(_scenario) - 1, {})['rerun'] = str(self.rerun)
        else:
            self.json_data['content']['suites'].setdefault(len(_test_suite_name), {}).setdefault('tests',
                                                                                                 {}).setdefault(
                len(_scenario) - 1, {})['rerun'] = '0'

    def generate_screenshot_data(self):
        os.makedirs(screen_base + '/pytest_screenshots', exist_ok=True)

        _screenshot_name = round(time.time())
        _screenshot_suite_name = _suite_name.split('/')[-1:][0].replace('.py', '')
        _screenshot_test_name = _test_name
        if len(_test_name) >= 19: _screenshot_test_name = _test_name[-17:]
        _screenshot_error = _current_error

        screen_img.save(
            screen_base + '/pytest_screenshots/' + str(_screenshot_name) + '.png'
        )

        # attach screenshots
        self.attach_screenshots(_screenshot_name, _screenshot_suite_name, _screenshot_test_name, _screenshot_error)
        _screenshot_name = ''
        _screenshot_suite_name = ''
        _screenshot_test_name = ''
        _screenshot_error = ''

    def append_suite_metrics_row(self, name):
        global _spass_tests, _sfail_tests, _sskip_tests, _sxpass_tests, _sxfail_tests, _serror_tests, _srerun_tests, \
            _error, _suite_error, _suite_fail

        self._test_names(_test_name, clear='yes')
        self._test_suites(name)

        self.json_data['content']['suites'].setdefault(len(_test_suite_name) - 1, {}).setdefault('status', {})[
            'total_pass'] = int(_spass_tests)
        self.json_data['content']['suites'].setdefault(len(_test_suite_name) - 1, {}).setdefault('status', {})[
            'total_skip'] = int(_sskip_tests)
        self.json_data['content']['suites'].setdefault(len(_test_suite_name) - 1, {}).setdefault('status', {})[
            'total_xpass'] = int(_sxpass_tests)
        self.json_data['content']['suites'].setdefault(len(_test_suite_name) - 1, {}).setdefault('status', {})[
            'total_xfail'] = int(_sxfail_tests)

        if (self.rerun is not None) and (max_rerun() is not None):
            _base_suite = self.json_data['content']['suites'].setdefault(len(_test_suite_name) - 1, {})['tests']
            for i in _base_suite:
                _srerun_tests += int(_base_suite[int(i)]['rerun'])

            self.json_data['content']['suites'].setdefault(len(_test_suite_name) - 1, {}).setdefault('status', {})[
                'total_rerun'] = int(_srerun_tests)
        else:
            self.json_data['content']['suites'].setdefault(len(_test_suite_name) - 1, {}).setdefault('status', {})[
                'total_rerun'] = 0

        for i in self.json_data['content']['suites'].setdefault(len(_test_suite_name) - 1, {})['tests']:
            if 'ERROR' in self.json_data['content']['suites'].setdefault(len(_test_suite_name) - 1, {})['tests'][i][
                'status']:
                _suite_error += 1
            elif 'FAIL' == self.json_data['content']['suites'].setdefault(len(_test_suite_name) - 1, {})['tests'][i][
                'status']:
                _suite_fail += 1

        self.json_data['content']['suites'].setdefault(len(_test_suite_name) - 1, {}).setdefault('status', {})[
            'total_fail'] = _suite_fail
        self.json_data['content']['suites'].setdefault(len(_test_suite_name) - 1, {}).setdefault('status', {})[
            'total_error'] = _suite_error

        suite_row_text = """
            <tr>
                <td style="word-wrap: break-word;max-width: 200px; white-space: normal; text-align:left">__sname__</td>
                <td>__spass__</td>
                <td>__sfail__</td>
                <td>__sskip__</td>
                <td>__sxpass__</td>
                <td>__sxfail__</td>
                <td>__serror__</td>
                <td>__srerun__</td>
            </tr>
        """
        suite_row_text = suite_row_text.replace("__sname__", str(name))
        suite_row_text = suite_row_text.replace("__spass__", str(_spass_tests))
        suite_row_text = suite_row_text.replace("__sfail__", str(_suite_fail))
        suite_row_text = suite_row_text.replace("__sskip__", str(_sskip_tests))
        suite_row_text = suite_row_text.replace("__sxpass__", str(_sxpass_tests))
        suite_row_text = suite_row_text.replace("__sxfail__", str(_sxfail_tests))
        suite_row_text = suite_row_text.replace("__serror__", str(_suite_error))
        suite_row_text = suite_row_text.replace("__srerun__", str(_srerun_tests))

        global _suite_metrics_content
        _suite_metrics_content += suite_row_text

        self._test_passed(int(_spass_tests))
        self._test_failed(int(_suite_fail))
        self._test_skipped(int(_sskip_tests))
        self._test_xpassed(int(_sxpass_tests))
        self._test_xfailed(int(_sxfail_tests))
        self._test_error(int(_suite_error))

        _spass_tests = 0
        _sfail_tests = 0
        _sskip_tests = 0
        _sxpass_tests = 0
        _sxfail_tests = 0
        _serror_tests = 0
        _srerun_tests = 0
        _suite_fail = 0
        _suite_error = 0

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
                pass

        if rep.skipped:
            if hasattr(rep, "wasxfail"):
                _sxfail_tests += 1
            else:
                _sskip_tests += 1

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

    def _test_names(self, name, **kwargs):
        global _scenario
        if (self.rerun is None) or (max_rerun() is None): _scenario.append(name)
        try:
            if kwargs['clear'] == 'yes': _scenario = []
        except Exception:
            pass

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
        template_text = template_text.replace("__execution_time__", str(_execution_time))
        template_text = template_text.replace("__title__", _title)
        # template_text = template_text.replace("__executed_by__", str(platform.uname()[1]))
        # template_text = template_text.replace("__os_name__", str(platform.uname()[0]))
        # template_text = template_text.replace("__python_version__", str(sys.version.split(' ')[0]))
        # template_text = template_text.replace("__generated_date__", str(datetime.datetime.now().strftime("%b %d %Y, %H:%M")))
        template_text = template_text.replace("__total__",
                                              str(_aspass + _asfail + _asskip + _aserror + _asxpass + _asxfail))
        template_text = template_text.replace("__executed__", str(_executed))
        template_text = template_text.replace("__pass__", str(_aspass))
        template_text = template_text.replace("__fail__", str(_asfail))
        template_text = template_text.replace("__skip__", str(_asskip))
        template_text = template_text.replace("__error__", str(_aserror))
        template_text = template_text.replace("__xpass__", str(_asxpass))
        template_text = template_text.replace("__xfail__", str(_asxfail))
        template_text = template_text.replace("__rerun__", str(_asrerun))
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
        template_text = template_text.replace("__archive_status__", str(_archive_tab_content))
        template_text = template_text.replace("__archive_body_content__", str(_archive_body_content))
        template_text = template_text.replace("__archive_count__", str(_archive_count))
        template_text = template_text.replace("__archives__", str(archives))
        template_text = template_text.replace("__max_failure_suite_name_final__", str(max_failure_suite_name_final))
        template_text = template_text.replace("__max_failure_suite_count__", str(max_failure_suite_count))
        template_text = template_text.replace("__similar_max_failure_suite_count__",
                                              str(similar_max_failure_suite_count))
        template_text = template_text.replace("__max_failure_total_tests__", str(max_failure_total_tests))
        template_text = template_text.replace("__max_failure_percent__", str(max_failure_percent))
        template_text = template_text.replace("__trends_label__", str(trends_label))
        template_text = template_text.replace("__tpass__", str(tpass))
        template_text = template_text.replace("__tfail__", str(tfail))
        template_text = template_text.replace("__tskip__", str(tskip))
        template_text = template_text.replace("__attach_screenshot_details__", str(_attach_screenshot_details))
        return template_text

    def generate_json_data(self, base):
        global _asskip, _aserror, _aspass, _asfail, _asxpass, _asxfail, _asrerun

        self.json_data['date'] = self._date()
        self.json_data['start_time'] = _start_execution_time
        self.json_data['total_suite'] = len(_test_suite_name)

        suite = self.json_data['content']['suites']
        for i in suite:
            for k in self.json_data['content']['suites'][i]['status']:
                if (k == 'total_fail' or k == 'total_error') and self.json_data['content']['suites'][i]['status'][
                    k] != 0:
                    self.json_data['status'] = "FAIL"
                    break
                else:
                    continue

            try:
                if self.json_data['status'] == "FAIL": break
            except KeyError:
                if len(_test_suite_name) == i + 1: self.json_data['status'] = "PASS"

        for i in suite:
            for k in self.json_data['content']['suites'][i]['status']:
                if k == 'total_pass':
                    _aspass += self.json_data['content']['suites'][i]['status'][k]
                elif k == 'total_fail':
                    _asfail += self.json_data['content']['suites'][i]['status'][k]
                elif k == 'total_skip':
                    _asskip += self.json_data['content']['suites'][i]['status'][k]
                elif k == 'total_error':
                    _aserror += self.json_data['content']['suites'][i]['status'][k]
                elif k == 'total_xpass':
                    _asxpass += self.json_data['content']['suites'][i]['status'][k]
                elif k == 'total_xfail':
                    _asxfail += self.json_data['content']['suites'][i]['status'][k]
                elif k == 'total_rerun':
                    _asrerun += self.json_data['content']['suites'][i]['status'][k]

        _astotal = _aspass + _asfail + _asskip + _aserror + _asxpass + _asxfail

        self.json_data.setdefault('status_list', {})['pass'] = str(_aspass)
        self.json_data.setdefault('status_list', {})['fail'] = str(_asfail)
        self.json_data.setdefault('status_list', {})['skip'] = str(_asskip)
        self.json_data.setdefault('status_list', {})['error'] = str(_aserror)
        self.json_data.setdefault('status_list', {})['xpass'] = str(_asxpass)
        self.json_data.setdefault('status_list', {})['xfail'] = str(_asxfail)
        self.json_data.setdefault('status_list', {})['rerun'] = str(_asrerun)
        self.json_data['total_tests'] = str(_astotal)

        with open(base + '/output.json', 'w') as outfile:
            json.dump(self.json_data, outfile)

    def update_archives_template(self, base):
        global _archive_count

        f = glob.glob(base + '/archive/*.json')
        cf = glob.glob(base + '/output.json')
        if len(f) > 0:
            _archive_count = len(f) + 1
            self.load_archive(cf, value='current')

            f.sort(reverse=True)
            self.load_archive(f, value='history')
        else:
            _archive_count = 1
            self.load_archive(cf, value='current')

    def load_archive(self, f, value):
        global archive_pass, archive_fail, archive_skip, archive_xpass, archive_xfail, archive_error, archives

        def state(data):
            if data == 'fail':
                return 'times', '#fc6766'
            elif data == 'pass':
                return 'check', '#98cc64'

        for i, val in enumerate(f):
            with open(val) as json_file:
                data = json.load(json_file)

                suite_highlights(data)
                archive_row_text = """
                    <a class ="list-group-item list-group-item-action" href="#list-item-__acount__" style="font-size: 1.1rem; color: dimgray; margin-bottom: -7%;">
                        <i class="fa fa-__astate__" aria-hidden="true" style="color: __astate_color__"></i>
                        <span>__astatus__</span></br>
                        <span style="font-size: 0.81rem; color: gray; padding-left: 12%;">__adate__</span>
                    </a>
                    """
                archive_row_text = archive_row_text.replace("__astate__", state(data['status'].lower())[0])
                archive_row_text = archive_row_text.replace("__astate_color__", state(data['status'].lower())[1])
                if value == "current":
                    archive_row_text = archive_row_text.replace("__astatus__", 'build #' + str(_archive_count))
                    archive_row_text = archive_row_text.replace("__acount__", str(_archive_count))
                else:
                    archive_row_text = archive_row_text.replace("__astatus__", 'build #' + str(len(f) - i))
                    archive_row_text = archive_row_text.replace("__acount__", str(len(f) - i))

                adate = datetime.strptime(
                    data['date'].split(None, 1)[0][:1 + 2:] + ' ' +
                    data['date'].split(None, 1)[1].replace(',', ''), "%b %d %Y"
                )

                atime = \
                    "".join(list(filter(lambda x: ':' in x, time.ctime(float(data['start_time'])).split(' ')))).rsplit(
                        ':',
                        1)[0]
                archive_row_text = archive_row_text.replace("__adate__",
                                                            str(adate.date()) + ' | ' + str(time_converter(atime)))

                global _archive_tab_content
                _archive_tab_content += archive_row_text

                _archive_body_text = """
                    <div id="list-item-__acount__" class="archive-body">
                        <div>
                            <h4 class="archive-header">
                                Build #__acount__
                            </h4>
                            <div class="archive-date">
                                <i class="fa fa-calendar-check-o" aria-hidden="true"></i>&nbsp;&nbsp;&nbsp;
                                __date__
                            </div>
                        </div>
                        <div style="margin-top: -5%;">
                            <div id="archive-container-__iloop__" style="padding-top: 5%; position: absolute;">
                                <div style="">
                                    <span class="total__tests">__total_tests__</span>
                                </div>
                                <div id="archive-label-__iloop__">
                                    <span class="archive__label">TEST CASES</span>
                                </div>
                            </div>
                            <div class="archive-chart-container">
                                <canvas id="archive-chart-__iloop__" style="margin-top: 10%; padding-left: 25%; margin-right: -16%; float: right;"></canvas>
                            </div>
                        </div>
                        <div class="archive__bar">
                            <section id="statistic" class="statistic-section-__status__ one-page-section">
                                <div class="container" style="margin-top: -2%;">
                                    <div class="row text-center">
                                        <div class="col-xs-12 col-md-3" style="max-width: 14.2%;">
                                            <div class="counter">
                                                <h2 class="timer count-title count-number">__pass__</h2>
                                                <p class="stats-text">PASSED</p>
                                            </div>
                                        </div>
                                        <div class="col-xs-12 col-md-3" style="max-width: 14.2%;">
                                            <div class="counter">
                                                <h2 class="timer count-title count-number">__fail__
                                                </h2>
                                                <p class="stats-text">FAILED</p>
                                            </div>
                                        </div>
                                        <div class="col-xs-12 col-md-3" style="max-width: 14.2%;"v>
                                            <div class="counter">
                                                <h2 class="timer count-title count-number">__skip__</h2>
                                                <p class="stats-text">SKIPPED</p>
                                            </div>
                                        </div>
                                        <div class="col-xs-12 col-md-3" style="max-width: 14.2%;">
                                            <div class="counter">
                                                <h2 class="timer count-title count-number">__xpass__</h2>
                                                <p class="stats-text">XPASSED</p>
                                            </div>
                                        </div>
                                        <div class="col-xs-12 col-md-3" style="max-width: 14.2%;">
                                            <div class="counter">
                                                <h2 class="timer count-title count-number">__xfail__</h2>
                                                <p class="stats-text">XFAILED</p>
                                            </div>
                                        </div>
                                        <div class="col-xs-12 col-md-3" style="max-width: 14.2%;">
                                            <div class="counter">
                                                <h2 class="timer count-title count-number">__error__</h2>
                                                <p class="stats-text">ERROR</p>
                                            </div>
                                        </div>
                                        <div class="col-xs-12 col-md-3" style="max-width: 14.2%;">
                                            <div class="counter">
                                                <h2 class="timer count-title count-number">__rerun__</h2>
                                                <p class="stats-text">RERUN</p>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </section>
                        </div>
                    </div>
                """

                if value == "current":
                    _archive_body_text = _archive_body_text.replace("__iloop__", str(i))
                    _archive_body_text = _archive_body_text.replace("__acount__", str(_archive_count))
                else:
                    _archive_body_text = _archive_body_text.replace("__iloop__", str(i + 1))
                    _archive_body_text = _archive_body_text.replace("__acount__", str(len(f) - i))

                _archive_body_text = _archive_body_text.replace("__total_tests__", data['total_tests'])
                _archive_body_text = _archive_body_text.replace("__date__", data['date'].upper())
                _archive_body_text = _archive_body_text.replace("__pass__", data['status_list']['pass'])
                _archive_body_text = _archive_body_text.replace("__fail__", data['status_list']['fail'])
                _archive_body_text = _archive_body_text.replace("__skip__", data['status_list']['skip'])
                _archive_body_text = _archive_body_text.replace("__xpass__", data['status_list']['xpass'])
                _archive_body_text = _archive_body_text.replace("__xfail__", data['status_list']['xfail'])
                _archive_body_text = _archive_body_text.replace("__error__", data['status_list']['error'])

                try:
                    _archive_body_text = _archive_body_text.replace("__rerun__", data['status_list']['rerun'])
                except KeyError:
                    _archive_body_text = _archive_body_text.replace("__rerun__", '0')

                _archive_body_text = _archive_body_text.replace("__status__", data['status'].lower())

                index = i
                if value != "current": index = i + 1
                archives.setdefault(str(index), {})['pass'] = data['status_list']['pass']
                archives.setdefault(str(index), {})['fail'] = data['status_list']['fail']
                archives.setdefault(str(index), {})['skip'] = data['status_list']['skip']
                archives.setdefault(str(index), {})['xpass'] = data['status_list']['xpass']
                archives.setdefault(str(index), {})['xfail'] = data['status_list']['xfail']
                archives.setdefault(str(index), {})['error'] = data['status_list']['error']

                try:
                    archives.setdefault(str(index), {})['rerun'] = data['status_list']['rerun']
                except KeyError:
                    archives.setdefault(str(index), {})['rerun'] = '0'

                archives.setdefault(str(index), {})['total'] = data['total_tests']

                global _archive_body_content
                _archive_body_content += _archive_body_text

    def update_trends(self, base):
        global tpass, tfail, tskip

        f2 = glob.glob(base + '/output.json')
        with open(f2[0]) as json_file:
            data = json.load(json_file)
            adate = datetime.strptime(
                data['date'].split(None, 1)[0][:1 + 2:] + ' ' +
                data['date'].split(None, 1)[1].replace(',', ''), "%b %d %Y"
            )
            atime = \
                "".join(list(filter(lambda x: ':' in x, time.ctime(float(data['start_time'])).split(' ')))).rsplit(
                    ':',
                    1)[0]
            trends_label.append(str(time_converter(atime)).upper() + ' | ' + str(adate.date().strftime("%b")) + ' '
                                + str(adate.date().strftime("%d")))

            tpass.append(data['status_list']['pass'])
            tfail.append(int(data['status_list']['fail']) + int(data['status_list']['error']))
            tskip.append(data['status_list']['skip'])

        f = glob.glob(base + '/archive' + '/*.json')
        f.sort(reverse=True)

        for i, val in enumerate(f):
            with open(val) as json_file:
                data = json.load(json_file)

                adate = datetime.strptime(
                    data['date'].split(None, 1)[0][:1 + 2:] + ' ' +
                    data['date'].split(None, 1)[1].replace(',', ''), "%b %d %Y"
                )
                atime = \
                    "".join(list(filter(lambda x: ':' in x, time.ctime(float(data['start_time'])).split(' ')))).rsplit(
                        ':',
                        1)[0]
                trends_label.append(str(time_converter(atime)).upper() + ' | ' + str(adate.date().strftime("%b")) + ' '
                                    + str(adate.date().strftime("%d")))

                tpass.append(data['status_list']['pass'])
                tfail.append(int(data['status_list']['fail']) + int(data['status_list']['error']))
                tskip.append(data['status_list']['skip'])

                if i == 4: break

    def attach_screenshots(self, screen_name, test_suite, test_case, test_error):
        global _attach_screenshot_details

        _screenshot_details = """
            <div class="img-hover col-md-6 col-xl-3 p-3">
              <div>
                <a class="video" href="__screenshot_base__/pytest_screenshots/__screen_name__.png" data-toggle="lightbox" style="background-image: url('__screenshot_base__/pytest_screenshots/__screen_name__.png');" data-fancybox="images" data-caption="SUITE: __ts__ :: SCENARIO: __tc__">
                    <span class="video-hover-desc video-hover-small"> <span style="font-size:23px;display: block;margin-bottom: 15px;"> __tc__</span>
                    <span>__te__</span> </span>
                </a>
                <p class="text-desc"><strong>__ts__</strong><br />
                 __te__</p>
              </div>
            </div>
            <div class="desc-video-none">
              <div class="desc-video" id="Video-desc-01">
                <h2>__tc__</h2>

                <p><strong>__ts__</strong><br />
                  __te__</p>
              </div>
            </div>
        """

        if len(test_case) == 17: test_case = '..' + test_case

        _screenshot_details = _screenshot_details.replace("__screen_name__", str(screen_name))
        _screenshot_details = _screenshot_details.replace("__ts__", str(test_suite))
        _screenshot_details = _screenshot_details.replace("__tc__", str(test_case))
        _screenshot_details = _screenshot_details.replace("__te__", str(test_error))
        _screenshot_details = _screenshot_details.replace("__screenshot_base__", str(screen_base))

        _attach_screenshot_details += _screenshot_details
