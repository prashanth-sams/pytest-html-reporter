import pytest
import os, time
from datetime import date, datetime
from pytest_html_reporter.template import html_template
from pytest_html_reporter.time_converter import time_converter
from os.path import isfile, join
import json
import glob
from collections import Counter

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


class HTMLReporter:

    def __init__(self, path, config):
        self.json_data = {'content': {'suites': {0: {'status': {}, 'tests': {0: {}}, }, }}}
        self.path = path
        self.config = config

    def pytest_runtest_teardown(self, item, nextitem):
        global _test_name
        _test_name = item.name

        self._test_names(_test_name)
        self.append_test_metrics_row()

    def pytest_runtest_setup(item):
        global _start_execution_time
        _start_execution_time = round(time.time())

    def pytest_sessionfinish(self, session):
        self.append_suite_metrics_row(_suite_name)
        self.reset_counts()

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
            return os.path.abspath(logfile), self.path.split('/')[-1]
        else:
            logfile = os.path.expanduser(os.path.expandvars(self.path))
            return os.path.abspath(logfile), 'pytest_html_report.html'

    @pytest.hookimpl(hookwrapper=True)
    def pytest_terminal_summary(self, terminalreporter, exitstatus, config):
        yield

        global _execution_time
        _execution_time = time.time() - terminalreporter._sessionstarttime

        global _total
        _total = _pass + _fail + _xpass + _xfail + _skip + _error

        base = self.report_path[0]
        path = os.path.join(base, self.report_path[1])

        self.archive_data(base, self.report_path[1])
        os.makedirs(base, exist_ok=True)

        # generate json file
        self.generate_json_data(base)

        # generate archive template
        if len(glob.glob(base + '/archive/*.json')) > 0: self.update_archives_template(base)

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

        self.json_data['content']['suites'].setdefault(len(_test_suite_name), {})['suite_name'] = str(_suite_name)
        self.json_data['content']['suites'].setdefault(len(_test_suite_name), {}).setdefault('tests', {}).setdefault(
            len(_scenario) - 1, {})['status'] = str(_test_status)
        self.json_data['content']['suites'].setdefault(len(_test_suite_name), {}).setdefault('tests', {}).setdefault(
            len(_scenario) - 1, {})['message'] = str(_current_error)
        self.json_data['content']['suites'].setdefault(len(_test_suite_name), {}).setdefault('tests', {}).setdefault(
            len(_scenario) - 1, {})['test_name'] = str(_test_name)

        global _test_metrics_content
        _test_metrics_content += test_row_text

    def append_suite_metrics_row(self, name):
        self._test_names(_test_name, clear='yes')
        self._test_suites(name)
        self._test_passed(int(_spass_tests))
        self._test_failed(int(_sfail_tests))
        self._test_skipped(int(_sskip_tests))
        self._test_xpassed(int(_sxpass_tests))
        self._test_xfailed(int(_sxfail_tests))
        self._test_error(int(_serror_tests))

        self.json_data['content']['suites'].setdefault(len(_test_suite_name) - 1, {}).setdefault('status', {})[
            'total_pass'] = int(_spass_tests)
        self.json_data['content']['suites'].setdefault(len(_test_suite_name) - 1, {}).setdefault('status', {})[
            'total_fail'] = int(_sfail_tests)
        self.json_data['content']['suites'].setdefault(len(_test_suite_name) - 1, {}).setdefault('status', {})[
            'total_skip'] = int(_sskip_tests)
        self.json_data['content']['suites'].setdefault(len(_test_suite_name) - 1, {}).setdefault('status', {})[
            'total_xpass'] = int(_sxpass_tests)
        self.json_data['content']['suites'].setdefault(len(_test_suite_name) - 1, {}).setdefault('status', {})[
            'total_xfail'] = int(_sxfail_tests)
        self.json_data['content']['suites'].setdefault(len(_test_suite_name) - 1, {}).setdefault('status', {})[
            'total_error'] = int(_serror_tests)

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

    def _test_names(self, name, **kwargs):
        global _scenario
        _scenario.append(name)
        try:
            if kwargs['clear'] == 'yes': _scenario = []
        except Exception:
            print('skip clear')

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
        template_text = template_text.replace("__archive_status__", str(_archive_tab_content))
        template_text = template_text.replace("__archive_body_content__", str(_archive_body_content))
        template_text = template_text.replace("__archive_count__", str(_archive_count))
        template_text = template_text.replace("__archives__", str(archives))
        template_text = template_text.replace("__max_failure_suite_name_final__", str(max_failure_suite_name_final))
        template_text = template_text.replace("__max_failure_suite_count__", str(max_failure_suite_count))
        template_text = template_text.replace("__similar_max_failure_suite_count__", str(similar_max_failure_suite_count))
        template_text = template_text.replace("__max_failure_total_tests__", str(max_failure_total_tests))
        template_text = template_text.replace("__max_failure_percent__", str(max_failure_percent))
        return template_text

    def generate_json_data(self, base):
        global _asskip, _aserror, _aspass, _asfail, _asxpass, _asxfail
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

        _astotal = _aspass + _asfail + _asskip + _aserror + _asxpass + _asxfail

        self.json_data.setdefault('status_list', {})['pass'] = str(_aspass)
        self.json_data.setdefault('status_list', {})['fail'] = str(_asfail)
        self.json_data.setdefault('status_list', {})['skip'] = str(_asskip)
        self.json_data.setdefault('status_list', {})['error'] = str(_aserror)
        self.json_data.setdefault('status_list', {})['xpass'] = str(_asxpass)
        self.json_data.setdefault('status_list', {})['xfail'] = str(_asxfail)
        self.json_data['total_tests'] = str(_astotal)

        with open(base + '/output.json', 'w') as outfile:
            json.dump(self.json_data, outfile)

    def update_archives_template(self, base):
        global _archive_count, archive_pass, archive_fail, archive_skip, archive_xpass, archive_xfail, archive_error, archives

        def state(data):
            if data == 'fail':
                return 'times', '#fc6766'
            elif data == 'pass':
                return 'check', '#98cc64'

        f = glob.glob(base + '/archive' + '/*.json')
        f.sort(reverse=True)
        _archive_count = len(f)
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
                                    <span style="font-size: 10.3rem; font-family: sans-serif; color: black; padding-top: 8%;">__total_tests__</span>
                                </div>
                                <div id="archive-label-__iloop__">
                                    <span style="font-size: 1.8rem; font-family: sans-serif; color: darkgray;">TEST CASES</span>
                                </div>
                            </div>
                            <div class="archive-chart-container">
                                <canvas id="archive-chart-__iloop__" width="240px" height="240px" style="width: 60%; height: 80%; float: right;"></canvas>
                            </div>
                        </div>
                        <div style="padding-top: 8.5%;">
                            <section id="statistic" class="statistic-section-__status__ one-page-section">
                                <div class="container" style="margin-top: -2%;">
                                    <div class="row text-center">
                                        <div class="col-xs-12 col-md-3" style="max-width: 16.6%;">
                                            <div class="counter">
                                                <h2 class="timer count-title count-number">__pass__</h2>
                                                <p class="stats-text">PASSED</p>
                                            </div>
                                        </div>
                                        <div class="col-xs-12 col-md-3" style="max-width: 16.6%;">
                                            <div class="counter">
                                                <h2 class="timer count-title count-number">__fail__
                                                </h2>
                                                <p class="stats-text">FAILED</p>
                                            </div>
                                        </div>
                                        <div class="col-xs-12 col-md-3" style="max-width: 16.6%;"v>
                                            <div class="counter">
                                                <h2 class="timer count-title count-number">__skip__</h2>
                                                <p class="stats-text">SKIPPED</p>
                                            </div>
                                        </div>
                                        <div class="col-xs-12 col-md-3" style="max-width: 16.6%;">
                                            <div class="counter">
                                                <h2 class="timer count-title count-number">__xpass__</h2>
                                                <p class="stats-text">XPASSED</p>
                                            </div>
                                        </div>
                                        <div class="col-xs-12 col-md-3" style="max-width: 16.6%;">
                                            <div class="counter">
                                                <h2 class="timer count-title count-number">__xfail__</h2>
                                                <p class="stats-text">XFAILED</p>
                                            </div>
                                        </div>
                                        <div class="col-xs-12 col-md-3" style="max-width: 16.6%;">
                                            <div class="counter">
                                                <h2 class="timer count-title count-number">__error__</h2>
                                                <p class="stats-text">ERROR</p>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </section>
                        </div>
                    </div>
                """
                _archive_body_text = _archive_body_text.replace("__iloop__", str(i))
                _archive_body_text = _archive_body_text.replace("__acount__", str(len(f) - i))
                _archive_body_text = _archive_body_text.replace("__total_tests__", data['total_tests'])
                _archive_body_text = _archive_body_text.replace("__date__", data['date'].upper())
                _archive_body_text = _archive_body_text.replace("__pass__", data['status_list']['pass'])
                _archive_body_text = _archive_body_text.replace("__fail__", data['status_list']['fail'])
                _archive_body_text = _archive_body_text.replace("__skip__", data['status_list']['skip'])
                _archive_body_text = _archive_body_text.replace("__xpass__", data['status_list']['xpass'])
                _archive_body_text = _archive_body_text.replace("__xfail__", data['status_list']['xfail'])
                _archive_body_text = _archive_body_text.replace("__error__", data['status_list']['error'])
                _archive_body_text = _archive_body_text.replace("__status__", data['status'].lower())

                archives.setdefault(str(i), {})['pass'] = data['status_list']['pass']
                archives.setdefault(str(i), {})['fail'] = data['status_list']['fail']
                archives.setdefault(str(i), {})['skip'] = data['status_list']['skip']
                archives.setdefault(str(i), {})['xpass'] = data['status_list']['xpass']
                archives.setdefault(str(i), {})['xfail'] = data['status_list']['xfail']
                archives.setdefault(str(i), {})['error'] = data['status_list']['error']
                archives.setdefault(str(i), {})['total'] = data['total_tests']

                global _archive_body_content
                _archive_body_content += _archive_body_text
