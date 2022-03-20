import glob
import json
import os
import time
from datetime import date, datetime
from os.path import isfile, join

import pytest

from html_page.archive_body import ArchiveBody
from html_page.archive_row import ArchiveRow
from html_page.floating_error import FloatingError
from html_page.screenshot_details import ScreenshotDetails
from html_page.suite_row import SuiteRow
from html_page.template import HtmlTemplate
from html_page.test_row import TestRow
from pytest_html_reporter.util import suite_highlights, generate_suite_highlights, max_rerun
from pytest_html_reporter.time_converter import time_converter
from pytest_html_reporter import const_vars

class HTMLReporter(object):
    def __init__(self, path, config):
        self.json_data = {'content': {'suites': {0: {'status': {}, 'tests': {0: {}}, }, }}}
        self.path = path
        self.config = config
        has_rerun = config.pluginmanager.hasplugin("rerunfailures")
        self.rerun = 0 if has_rerun else None

    def pytest_runtest_teardown(self, item, nextitem):
        const_vars._test_name = item.name

        _test_end_time = time.time()
        const_vars._duration = _test_end_time - const_vars._start_execution_time

        if (self.rerun is not None) and (max_rerun() is not None): self.previous_test_name(const_vars._test_name)
        self._test_names(const_vars._test_name)
        self.append_test_metrics_row()

    def previous_test_name(self, _test_name):

        if const_vars._previous_test_name == _test_name:
            self.rerun += 1
        else:
            const_vars._scenario.append(_test_name)
            self.rerun = 0
            const_vars._previous_test_name = _test_name

    def pytest_runtest_setup(item):
        const_vars._start_execution_time = time.time()

    def pytest_sessionfinish(self, session):

        if const_vars._suite_name is not None: self.append_suite_metrics_row(const_vars._suite_name)

    def archive_data(self, base, filename):

        path = os.path.join(base, filename)

        if os.path.isfile(path) is True:
            os.makedirs(base + '/archive', exist_ok=True)
            f = 'output.json'

            if isfile(join(base, f)):
                fname = os.path.splitext(f)
                os.rename(base + '/' + f, os.path.join(base + '/archive', fname[0] + '_' +
                                                       str(const_vars._start_execution_time) + fname[1]))

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
        _execution_time = time.time() - terminalreporter._sessionstarttime

        if const_vars._execution_time < 60:
            const_vars._execution_time = str(round(_execution_time, 2)) + " secs"
        else:
            _execution_time = str(time.strftime("%H:%M:%S", time.gmtime(round(_execution_time)))) + " Hrs"
        const_vars._total = const_vars._pass + const_vars._fail + const_vars._xpass + const_vars._xfail + const_vars._skip + const_vars._error

        if const_vars._suite_name is not None:
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
        const_vars._suite_name = rep.nodeid.split("::")[0]

        if const_vars._initial_trigger:
            self.update_previous_suite_name()
            self.set_initial_trigger()

        if str(const_vars._previous_suite_name) != str(const_vars._suite_name):
            self.append_suite_metrics_row(const_vars._previous_suite_name)
            self.update_previous_suite_name()
        else:
            self.update_counts(rep)

        if rep.when == "call" and rep.passed:
            if hasattr(rep, "wasxfail"):
                self.increment_xpass()
                self.update_test_status("xPASS")
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

        test_row_text = TestRow()

        floating_error_text = FloatingError()

        if (self.rerun is not None) and (max_rerun() is not None):
            if (const_vars._test_status == 'FAIL') or (const_vars._test_status == 'ERROR'): const_vars._pvalue += 1

            if (const_vars._pvalue == max_rerun() + 1) or (const_vars._test_status == 'PASS'):
                if ((const_vars._test_status == 'FAIL') or (const_vars._test_status == 'ERROR')) and (
                        const_vars.screen_base != ''): self.generate_screenshot_data()

                test_row_text = test_row_text.replace("__sname__", str(const_vars._suite_name))
                test_row_text = test_row_text.replace("__name__", str(const_vars._test_name))
                test_row_text = test_row_text.replace("__stat__", str(const_vars._test_status))
                test_row_text = test_row_text.replace("__dur__", str(round(const_vars._duration, 2)))
                test_row_text = test_row_text.replace("__msg__", str(const_vars._current_error[:50]))
                floating_error_text = floating_error_text.replace("__runt__", str(time.time()).replace('.', ''))

                if len(const_vars._current_error) < 49:
                    test_row_text = test_row_text.replace("__floating_error_text__", str(''))
                else:
                    test_row_text = test_row_text.replace("__floating_error_text__", str(floating_error_text))
                    test_row_text = test_row_text.replace("__full_msg__", str(const_vars._current_error))

                const_vars._test_metrics_content += test_row_text
                const_vars._pvalue = 0
            elif (self.rerun is not None) and (
                    (const_vars._test_status == 'xFAIL') or (const_vars._test_status == 'xPASS') or (const_vars._test_status == 'SKIP')):
                test_row_text = test_row_text.replace("__sname__", str(const_vars._suite_name))
                test_row_text = test_row_text.replace("__name__", str(const_vars._test_name))
                test_row_text = test_row_text.replace("__stat__", str(const_vars._test_status))
                test_row_text = test_row_text.replace("__dur__", str(round(const_vars._duration, 2)))
                test_row_text = test_row_text.replace("__msg__", str(const_vars._current_error[:50]))
                floating_error_text = floating_error_text.replace("__runt__", str(time.time()).replace('.', ''))

                if len(const_vars._current_error) < 49:
                    test_row_text = test_row_text.replace("__floating_error_text__", str(''))
                else:
                    test_row_text = test_row_text.replace("__floating_error_text__", str(floating_error_text))
                    test_row_text = test_row_text.replace("__full_msg__", str(const_vars._current_error))

                const_vars._test_metrics_content += test_row_text

        elif (self.rerun is None) or (max_rerun() is None):
            if ((const_vars._test_status == 'FAIL') or (const_vars._test_status == 'ERROR')) and (
                    const_vars.screen_base != ''): self.generate_screenshot_data()

            test_row_text = test_row_text.replace("__sname__", str(const_vars._suite_name))
            test_row_text = test_row_text.replace("__name__", str(const_vars._test_name))
            test_row_text = test_row_text.replace("__stat__", str(const_vars._test_status))
            test_row_text = test_row_text.replace("__dur__", str(round(const_vars._duration, 2)))
            test_row_text = test_row_text.replace("__msg__", str(const_vars._current_error[:50]))
            floating_error_text = floating_error_text.replace("__runt__", str(time.time()).replace('.', ''))

            if len(const_vars._current_error) < 49:
                test_row_text = test_row_text.replace("__floating_error_text__", str(''))
            else:
                test_row_text = test_row_text.replace("__floating_error_text__", str(floating_error_text))
                test_row_text = test_row_text.replace("__full_msg__", str(const_vars._current_error))

            const_vars._test_metrics_content += test_row_text

        self.json_data['content']['suites'].setdefault(len(const_vars._test_suite_name), {})['suite_name'] = str(const_vars._suite_name)
        self.json_data['content']['suites'].setdefault(len(const_vars._test_suite_name), {}).setdefault('tests', {}).setdefault(
            len(const_vars._scenario) - 1, {})['status'] = str(const_vars._test_status)
        self.json_data['content']['suites'].setdefault(len(const_vars._test_suite_name), {}).setdefault('tests', {}).setdefault(
            len(const_vars._scenario) - 1, {})['message'] = str(const_vars._current_error)
        self.json_data['content']['suites'].setdefault(len(const_vars._test_suite_name), {}).setdefault('tests', {}).setdefault(
            len(const_vars._scenario) - 1, {})['test_name'] = str(const_vars._test_name)

        if (self.rerun is not None) and (max_rerun() is not None):
            self.json_data['content']['suites'].setdefault(len(const_vars._test_suite_name), {}).setdefault('tests',
                                                                                                 {}).setdefault(
                len(const_vars._scenario) - 1, {})['rerun'] = str(self.rerun)
        else:
            self.json_data['content']['suites'].setdefault(len(const_vars._test_suite_name), {}).setdefault('tests',
                                                                                                 {}).setdefault(
                len(const_vars._scenario) - 1, {})['rerun'] = '0'

    def generate_screenshot_data(self):

        os.makedirs(const_vars.screen_base + '/pytest_screenshots', exist_ok=True)

        _screenshot_name = round(time.time())
        _screenshot_suite_name = const_vars._suite_name.split('/')[-1:][0].replace('.py', '')
        _screenshot_test_name = const_vars._test_name
        if len(const_vars._test_name) >= 19: const_vars._screenshot_test_name = const_vars._test_name[-17:]
        _screenshot_error = const_vars._current_error

        const_vars.screen_img.save(
            const_vars.screen_base + '/pytest_screenshots/' + str(_screenshot_name) + '.png'
        )

        # attach screenshots
        self.attach_screenshots(_screenshot_name, _screenshot_suite_name, _screenshot_test_name, _screenshot_error)
        _screenshot_name = ''
        _screenshot_suite_name = ''
        _screenshot_test_name = ''
        _screenshot_error = ''

    def append_suite_metrics_row(self, name):
        self._test_names(const_vars._test_name, clear='yes')
        self._test_suites(name)

        self.json_data['content']['suites'].setdefault(len(const_vars._test_suite_name) - 1, {}).setdefault('status', {})[
            'total_pass'] = int(const_vars._spass_tests)
        self.json_data['content']['suites'].setdefault(len(const_vars._test_suite_name) - 1, {}).setdefault('status', {})[
            'total_skip'] = int(const_vars._sskip_tests)
        self.json_data['content']['suites'].setdefault(len(const_vars._test_suite_name) - 1, {}).setdefault('status', {})[
            'total_xpass'] = int(const_vars._sxpass_tests)
        self.json_data['content']['suites'].setdefault(len(const_vars._test_suite_name) - 1, {}).setdefault('status', {})[
            'total_xfail'] = int(const_vars._sxfail_tests)

        if (self.rerun is not None) and (max_rerun() is not None):
            _base_suite = self.json_data['content']['suites'].setdefault(len(const_vars._test_suite_name) - 1, {})['tests']
            for i in _base_suite:
                const_vars._srerun_tests += int(_base_suite[int(i)]['rerun'])

            self.json_data['content']['suites'].setdefault(len(const_vars._test_suite_name) - 1, {}).setdefault('status', {})[
                'total_rerun'] = int(const_vars._srerun_tests)
        else:
            self.json_data['content']['suites'].setdefault(len(const_vars._test_suite_name) - 1, {}).setdefault('status', {})[
                'total_rerun'] = 0

        for i in self.json_data['content']['suites'].setdefault(len(const_vars._test_suite_name) - 1, {})['tests']:
            if 'ERROR' in self.json_data['content']['suites'].setdefault(len(const_vars._test_suite_name) - 1, {})['tests'][i]['status']:
                const_vars._suite_error += 1
            elif 'FAIL' == self.json_data['content']['suites'].setdefault(len(const_vars._test_suite_name) - 1, {})['tests'][i][
                'status']:
                const_vars._suite_fail += 1

        self.json_data['content']['suites'].setdefault(len(const_vars._test_suite_name) - 1, {}).setdefault('status', {})[
            'total_fail'] = const_vars._suite_fail
        self.json_data['content']['suites'].setdefault(len(const_vars._test_suite_name) - 1, {}).setdefault('status', {})[
            'total_error'] = const_vars._suite_error

        suite_row_text = SuiteRow()
        suite_row_text = suite_row_text.replace("__sname__", str(name))
        suite_row_text = suite_row_text.replace("__spass__", str(const_vars._spass_tests))
        suite_row_text = suite_row_text.replace("__sfail__", str(const_vars._suite_fail))
        suite_row_text = suite_row_text.replace("__sskip__", str(const_vars._sskip_tests))
        suite_row_text = suite_row_text.replace("__sxpass__", str(const_vars._sxpass_tests))
        suite_row_text = suite_row_text.replace("__sxfail__", str(const_vars._sxfail_tests))
        suite_row_text = suite_row_text.replace("__serror__", str(const_vars._suite_error))
        suite_row_text = suite_row_text.replace("__srerun__", str(const_vars._srerun_tests))

        const_vars._suite_metrics_content += suite_row_text

        self._test_passed(int(const_vars._spass_tests))
        self._test_failed(int(const_vars._suite_fail))
        self._test_skipped(int(const_vars._sskip_tests))
        self._test_xpassed(int(const_vars._sxpass_tests))
        self._test_xfailed(int(const_vars._sxfail_tests))
        self._test_error(int(const_vars._suite_error))

        const_vars._spass_tests = 0
        const_vars._sfail_tests = 0
        const_vars._sskip_tests = 0
        const_vars._sxpass_tests = 0
        const_vars._sxfail_tests = 0
        const_vars._serror_tests = 0
        const_vars._srerun_tests = 0
        const_vars._suite_fail = 0
        const_vars._suite_error = 0

    def set_initial_trigger(self):
        const_vars._initial_trigger = False

    def update_previous_suite_name(self):
        const_vars._previous_suite_name = const_vars._suite_name

    def update_counts(self, rep):
        if rep.when == "call" and rep.passed:
            if hasattr(rep, "wasxfail"):
                const_vars._sxpass_tests += 1
            else:
                const_vars._spass_tests += 1

        if rep.failed:
            if getattr(rep, "when", None) == "call":
                if hasattr(rep, "wasxfail"):
                    const_vars._sxpass_tests += 1
                else:
                    const_vars._sfail_tests += 1
            else:
                pass

        if rep.skipped:
            if hasattr(rep, "wasxfail"):
                const_vars._sxfail_tests += 1
            else:
                const_vars._sskip_tests += 1

    def update_test_error(self, msg):
        const_vars._current_error = msg

    def update_test_status(self, status):
        const_vars._test_status = status

    def increment_xpass(self):
        const_vars._xpass += 1

    def increment_xfail(self):
        const_vars._xfail += 1

    def increment_pass(self):
        const_vars._pass += 1

    def increment_fail(self):
        const_vars._fail += 1

    def increment_skip(self):
        const_vars._skip += 1

    def increment_error(self):
        const_vars._error += 1
        const_vars._serror_tests += 1

    def _date(self):
        return date.today().strftime("%B %d, %Y")

    def _test_suites(self, name):
        const_vars._test_suite_name.append(name.split('/')[-1].replace('.py', ''))

    def _test_names(self, name, **kwargs):
        if (self.rerun is None) or (max_rerun() is None): const_vars._scenario.append(name)
        try:
            if kwargs['clear'] == 'yes': const_vars._scenario = []
        except Exception:
            pass

    def _test_passed(self, value):
        const_vars._test_pass_list.append(value)

    def _test_failed(self, value):
        const_vars._test_fail_list.append(value)

    def _test_skipped(self, value):
        const_vars._test_skip_list.append(value)

    def _test_xpassed(self, value):
        const_vars._test_xpass_list.append(value)

    def _test_xfailed(self, value):
        const_vars._test_xfail_list.append(value)

    def _test_error(self, value):
        const_vars._test_error_list.append(value)

    def renew_template_text(self, logo_url):
        template_text = HtmlTemplate()
        template_text = template_text.replace("__custom_logo__", logo_url)
        template_text = template_text.replace("__execution_time__", str(const_vars._execution_time))
        template_text = template_text.replace("__title__", const_vars._title)
        # template_text = template_text.replace("__executed_by__", str(platform.uname()[1]))
        # template_text = template_text.replace("__os_name__", str(platform.uname()[0]))
        # template_text = template_text.replace("__python_version__", str(sys.version.split(' ')[0]))
        # template_text = template_text.replace("__generated_date__", str(datetime.datetime.now().strftime("%b %d %Y, %H:%M")))
        template_text = template_text.replace("__total__",
                                              str(const_vars._aspass + const_vars._asfail + const_vars._asskip + const_vars._aserror + const_vars._asxpass + const_vars._asxfail))
        template_text = template_text.replace("__executed__", str(const_vars._executed))
        template_text = template_text.replace("__pass__", str(const_vars._aspass))
        template_text = template_text.replace("__fail__", str(const_vars._asfail))
        template_text = template_text.replace("__skip__", str(const_vars._asskip))
        template_text = template_text.replace("__error__", str(const_vars._aserror))
        template_text = template_text.replace("__xpass__", str(const_vars._asxpass))
        template_text = template_text.replace("__xfail__", str(const_vars._asxfail))
        template_text = template_text.replace("__rerun__", str(const_vars._asrerun))
        template_text = template_text.replace("__suite_metrics_row__", str(const_vars._suite_metrics_content))
        template_text = template_text.replace("__test_metrics_row__", str(const_vars._test_metrics_content))
        template_text = template_text.replace("__date__", str(self._date()))
        template_text = template_text.replace("__test_suites__", str(const_vars._test_suite_name))
        template_text = template_text.replace("__test_suite_length__", str(len(const_vars._test_suite_name)))
        template_text = template_text.replace("__test_suite_pass__", str(const_vars._test_pass_list))
        template_text = template_text.replace("__test_suites_fail__", str(const_vars._test_fail_list))
        template_text = template_text.replace("__test_suites_skip__", str(const_vars._test_skip_list))
        template_text = template_text.replace("__test_suites_xpass__", str(const_vars._test_xpass_list))
        template_text = template_text.replace("__test_suites_xfail__", str(const_vars._test_xfail_list))
        template_text = template_text.replace("__test_suites_error__", str(const_vars._test_error_list))
        template_text = template_text.replace("__archive_status__", str(const_vars._archive_tab_content))
        template_text = template_text.replace("__archive_body_content__", str(const_vars._archive_body_content))
        template_text = template_text.replace("__archive_count__", str(const_vars._archive_count))
        template_text = template_text.replace("__archives__", str(const_vars.archives))
        template_text = template_text.replace("__max_failure_suite_name_final__", str(const_vars.max_failure_suite_name_final))
        template_text = template_text.replace("__max_failure_suite_count__", str(const_vars.max_failure_suite_count))
        template_text = template_text.replace("__similar_max_failure_suite_count__",
                                              str(const_vars.similar_max_failure_suite_count))
        template_text = template_text.replace("__max_failure_total_tests__", str(const_vars.max_failure_total_tests))
        template_text = template_text.replace("__max_failure_percent__", str(const_vars.max_failure_percent))
        template_text = template_text.replace("__trends_label__", str(const_vars.trends_label))
        template_text = template_text.replace("__tpass__", str(const_vars.tpass))
        template_text = template_text.replace("__tfail__", str(const_vars.tfail))
        template_text = template_text.replace("__tskip__", str(const_vars.tskip))
        template_text = template_text.replace("__attach_screenshot_details__", str(const_vars._attach_screenshot_details))
        return template_text

    def generate_json_data(self, base):
        self.json_data['date'] = self._date()
        self.json_data['start_time'] = const_vars._start_execution_time
        self.json_data['total_suite'] = len(const_vars._test_suite_name)

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
                if len(const_vars._test_suite_name) == i + 1: self.json_data['status'] = "PASS"

        for i in suite:
            for k in self.json_data['content']['suites'][i]['status']:
                if k == 'total_pass':
                    const_vars._aspass += self.json_data['content']['suites'][i]['status'][k]
                elif k == 'total_fail':
                    const_vars._asfail += self.json_data['content']['suites'][i]['status'][k]
                elif k == 'total_skip':
                    const_vars._asskip += self.json_data['content']['suites'][i]['status'][k]
                elif k == 'total_error':
                    const_vars._aserror += self.json_data['content']['suites'][i]['status'][k]
                elif k == 'total_xpass':
                    const_vars._asxpass += self.json_data['content']['suites'][i]['status'][k]
                elif k == 'total_xfail':
                    const_vars._asxfail += self.json_data['content']['suites'][i]['status'][k]
                elif k == 'total_rerun':
                    const_vars._asrerun += self.json_data['content']['suites'][i]['status'][k]

        const_vars._astotal = const_vars._aspass + const_vars._asfail + const_vars._asskip + const_vars._aserror + const_vars._asxpass + const_vars._asxfail

        self.json_data.setdefault('status_list', {})['pass'] = str(const_vars._aspass)
        self.json_data.setdefault('status_list', {})['fail'] = str(const_vars._asfail)
        self.json_data.setdefault('status_list', {})['skip'] = str(const_vars._asskip)
        self.json_data.setdefault('status_list', {})['error'] = str(const_vars._aserror)
        self.json_data.setdefault('status_list', {})['xpass'] = str(const_vars._asxpass)
        self.json_data.setdefault('status_list', {})['xfail'] = str(const_vars._asxfail)
        self.json_data.setdefault('status_list', {})['rerun'] = str(const_vars._asrerun)
        self.json_data['total_tests'] = str(const_vars._astotal)

        with open(base + '/output.json', 'w') as outfile:
            json.dump(self.json_data, outfile)

    def update_archives_template(self, base):

        f = glob.glob(base + '/archive/*.json')
        cf = glob.glob(base + '/output.json')
        if len(f) > 0:
            const_vars._archive_count = len(f) + 1
            self.load_archive(cf, value='current')

            f.sort(reverse=True)
            self.load_archive(f, value='history')
        else:
            const_vars._archive_count = 1
            self.load_archive(cf, value='current')

    def load_archive(self, f, value):

        def state(data):
            if data == 'fail':
                return 'times', '#fc6766'
            elif data == 'pass':
                return 'check', '#98cc64'

        for i, val in enumerate(f):
            with open(val) as json_file:
                data = json.load(json_file)

                suite_highlights(data)
                archive_row_text = ArchiveRow()
                archive_row_text = archive_row_text.replace("__astate__", state(data['status'].lower())[0])
                archive_row_text = archive_row_text.replace("__astate_color__", state(data['status'].lower())[1])
                if value == "current":
                    archive_row_text = archive_row_text.replace("__astatus__", 'build #' + str(const_vars._archive_count))
                    archive_row_text = archive_row_text.replace("__acount__", str(const_vars._archive_count))
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
                const_vars._archive_tab_content += archive_row_text

                _archive_body_text = ArchiveBody()

                if value == "current":
                    _archive_body_text = _archive_body_text.replace("__iloop__", str(i))
                    const_vars._archive_body_text = _archive_body_text.replace("__acount__", str(const_vars._archive_count))
                else:
                    const_vars._archive_body_text = _archive_body_text.replace("__iloop__", str(i + 1))
                    const_vars._archive_body_text = _archive_body_text.replace("__acount__", str(len(f) - i))

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
                const_vars.archives.setdefault(str(index), {})['pass'] = data['status_list']['pass']
                const_vars.archives.setdefault(str(index), {})['fail'] = data['status_list']['fail']
                const_vars.archives.setdefault(str(index), {})['skip'] = data['status_list']['skip']
                const_vars.archives.setdefault(str(index), {})['xpass'] = data['status_list']['xpass']
                const_vars.archives.setdefault(str(index), {})['xfail'] = data['status_list']['xfail']
                const_vars.archives.setdefault(str(index), {})['error'] = data['status_list']['error']

                try:
                    const_vars.archives.setdefault(str(index), {})['rerun'] = data['status_list']['rerun']
                except KeyError:
                    const_vars.archives.setdefault(str(index), {})['rerun'] = '0'

                const_vars.archives.setdefault(str(index), {})['total'] = data['total_tests']
                const_vars._archive_body_content += _archive_body_text

    def update_trends(self, base):

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
            const_vars.trends_label.append(str(time_converter(atime)).upper() + ' | ' + str(adate.date().strftime("%b")) + ' '
                                + str(adate.date().strftime("%d")))

            const_vars.tpass.append(data['status_list']['pass'])
            const_vars.tfail.append(int(data['status_list']['fail']) + int(data['status_list']['error']))
            const_vars.tskip.append(data['status_list']['skip'])

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
                const_vars.trends_label.append(str(time_converter(atime)).upper() + ' | ' + str(adate.date().strftime("%b")) + ' '
                                    + str(adate.date().strftime("%d")))

                const_vars.tpass.append(data['status_list']['pass'])
                const_vars.tfail.append(int(data['status_list']['fail']) + int(data['status_list']['error']))
                const_vars.tskip.append(data['status_list']['skip'])

                if i == 4: break

    def attach_screenshots(self, screen_name, test_suite, test_case, test_error):

        _screenshot_details = ScreenshotDetails()

        if len(test_case) == 17: test_case = '..' + test_case

        _screenshot_details = _screenshot_details.replace("__screen_name__", str(screen_name))
        _screenshot_details = _screenshot_details.replace("__ts__", str(test_suite))
        _screenshot_details = _screenshot_details.replace("__tc__", str(test_case))
        _screenshot_details = _screenshot_details.replace("__te__", str(test_error))
        _screenshot_details = _screenshot_details.replace("__screenshot_base__", str(const_vars.screen_base))

        const_vars._attach_screenshot_details += _screenshot_details