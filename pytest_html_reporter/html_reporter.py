import glob
import json
import os
import time
import shutil
from collections import OrderedDict
from datetime import date, datetime
from os.path import isfile, join

import pytest

from html_page.archive_body import ArchiveBody
from html_page.archive_row import ArchiveRow
from html_page.floating_error import FloatingError
from html_page.screenshot_details import ScreenshotDetails
from html_page.suite_row import SuiteRow
from html_page.template import HtmlTemplate
from html_page.test_log import TestLog
from html_page.test_log_section import TestLogSection
from html_page.test_row import TestRow
from pytest_html_reporter.util import (
    suite_highlights,
    generate_suite_highlights,
    generate_environment_info,
    generate_logs_notice,
    is_xdist_worker,
    xdist_worker_id,
    report_logs_mode,
    report_log_limit,
    merge_log_sections,
    format_log_sections,
    escape_log_text,
    count_log_lines,
)
from pytest_html_reporter.time_converter import time_converter
from pytest_html_reporter.const_vars import ConfigVars


class HTMLReporter(object):
    def __init__(self, path, archive_count, config):
        self.json_data = {'content': {'suites': {}}}
        self.path = path
        self.archive_count = archive_count
        self.config = config
        self.rerun_plugin = config.pluginmanager.hasplugin("rerunfailures")
        self._sessionstarttime = None

        # What pytest captured for the test currently running, keyed by the
        # section title it gave the capture ("Captured log call", ...). Emptied
        # at the start of every attempt so nothing leaks into the next test.
        self._log_sections = {}
        self.logs_mode = report_logs_mode(config)
        self.log_limit = report_log_limit(config)

        # One record per finished test. In a serial run this process fills the
        # list on its own; under xdist every worker fills its own copy and the
        # controller merges them all before anything is rendered.
        self._records = []

        # Where each test's record sits in that list, so a retry can replace the
        # attempt it superseded instead of being reported as another test.
        self._record_slots = {}
        self._collected = {}
        self.worker_id = xdist_worker_id(config)

        # attach() needs somewhere to write long before the report is built,
        # and each xdist worker saves its own screenshots.
        HTMLReporter.base_path = self.report_path[0]

    def pytest_sessionstart(self, session):
        self._sessionstarttime = time.time()

        # The controller of an xdist run never executes a test, so it would
        # otherwise stamp the report - and its archive file name - with 0.
        ConfigVars._start_execution_time = self._sessionstarttime

    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self, session, config, items):
        # Every xdist worker collects the whole suite, so a test sits at the
        # same position in every process. Remembering that position is what
        # lets the controller put the workers' results back in collection
        # order, whatever order they actually ran in.
        self._collected = {item.nodeid: index for index, item in enumerate(items)}

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_teardown(self, item, nextitem):
        ConfigVars._test_name = item.name

        _test_end_time = time.time()
        ConfigVars._duration = _test_end_time - ConfigVars._start_execution_time

        # A test's fixtures are finalized by the implementations this wraps, so
        # the record is built after them. That is what lets a screenshot
        # attached from a fixture's teardown - the recipe most people reach for
        # first - reach the report at all: built any earlier, there would be no
        # record left for the image to be attached to. The duration is read
        # before yielding, so time spent cleaning up is not billed to the test.
        yield

        self.append_test_record(item)

    def pytest_runtest_setup(self, item):
        ConfigVars._start_execution_time = time.time()
        self._log_sections = {}

    def pytest_sessionfinish(self, session):
        # A worker cannot write the report - it only ever saw its own slice of
        # the run - so it ships its records back to the controller instead.
        if is_xdist_worker(self.config):
            self.config.workeroutput['pytest_html_reporter'] = {'records': self._records}

    @pytest.hookimpl(optionalhook=True)
    def pytest_testnodedown(self, node, error):
        """Collect one finished xdist worker's records on the controller."""
        payload = getattr(node, 'workeroutput', {}).get('pytest_html_reporter')
        if payload:
            for record in payload['records']:
                self.store_test_record(record)

    def archive_data(self, base, filename):
        path = os.path.join(base, filename)

        if os.path.isfile(path) is True:
            os.makedirs(base + '/archive', exist_ok=True)
            f = 'output.json'

            if isfile(join(base, f)):
                fname = os.path.splitext(f)
                os.rename(base + '/' + f, os.path.join(base + '/archive', fname[0] + '_' +
                                                       str(ConfigVars._start_execution_time) + fname[1]))

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

    def remove_old_archives(self):
        archive_dir = os.path.abspath(os.path.expanduser(os.path.expandvars(self.path))) + '/archive'

        if self.archive_count != '':
            if int(self.archive_count) == 0:
                if os.path.isdir(archive_dir):
                    shutil.rmtree(archive_dir)
                return

            archive_count = int(self.archive_count) - 1
            if os.path.isdir(archive_dir):
                archives = os.listdir(archive_dir)
                archives.sort(key=lambda f: os.path.getmtime(os.path.join(archive_dir, f)))
                for i in range(0, len(archives) - archive_count):
                    os.remove(os.path.join(archive_dir, archives[i]))

    @pytest.hookimpl(hookwrapper=True)
    def pytest_terminal_summary(self, terminalreporter, exitstatus, config):

        yield

        # Workers already handed their records to the controller. Letting them
        # write as well is what produced a report - and an archived "build" -
        # per worker, each holding only that worker's share of the tests.
        if is_xdist_worker(self.config): return

        _execution_time = time.time() - self._sessionstarttime

        if _execution_time < 60:
            ConfigVars._execution_time = str(round(_execution_time, 2)) + " secs"
        else:
            ConfigVars._execution_time = str(time.strftime("%H:%M:%S", time.gmtime(round(_execution_time)))) + " Hrs"

        if self._records:
            # rows, suite totals and json, built once from every process's records
            self.build_report()

            base = self.report_path[0]
            path = os.path.join(base, self.report_path[1])

            os.makedirs(base, exist_ok=True)
            self.archive_data(base, self.report_path[1])

            # generate json file
            self.generate_json_data(base)

            # generate trends
            self.update_trends(base)

            # generate archive template
            self.remove_old_archives()
            self.update_archives_template(base) if self.archive_count != '0' else None

            # generate suite highlights
            generate_suite_highlights()

            # collect host, interpreter and invocation details
            generate_environment_info(self.config)

            # say why the Logs column is empty, when something is suppressing it
            generate_logs_notice(self.config)

            # generate html report
            live_logs_file = open(path, 'w')
            message = self.renew_template_text('https://i.imgur.com/LRSRHJO.png')
            live_logs_file.write(message)
            live_logs_file.close()

    @pytest.hookimpl(tryfirst=True, hookwrapper=True)
    def pytest_runtest_makereport(self, item, call):

        outcome = yield
        rep = outcome.get_result()
        ConfigVars._suite_name = rep.nodeid.split("::")[0]

        # Setup, call and teardown each report their own captured output, so
        # the sections are collected as the phases go by rather than read off
        # any single report.
        if self.logs_mode != 'none':
            merge_log_sections(self._log_sections, rep.sections)

            # A record is built from the teardown hook, which runs before
            # pytest has finished capturing that phase. Folding the last
            # sections in here is what puts fixture teardown output - the
            # output of the code that cleans up after a failure - in the
            # report at all.
            if rep.when == 'teardown': self.refresh_record_logs(rep.nodeid)

        # Only the outcome of this one test is tracked here. Suite grouping and
        # every total are worked out at the end, from the merged records, so
        # that tests arriving interleaved from several workers still add up.
        if rep.when == "call" and rep.passed:
            if hasattr(rep, "wasxfail"):
                self.update_test_status("xPASS")
                self.update_test_error("")
            else:
                self.update_test_status("PASS")
                self.update_test_error("")

        if rep.failed:
            if getattr(rep, "when", None) == "call":
                if hasattr(rep, "wasxfail"):
                    self.update_test_status("xPASS")
                    self.update_test_error("")
                else:
                    self.update_test_status("FAIL")
                    if rep.longrepr:
                        longerr = ""
                        for line in rep.longreprtext.splitlines():
                            exception = line.startswith("E   ")
                            if exception:
                                longerr += line + "\n"
                        self.update_test_error(longerr.replace("E    ", ""))
            else:
                self.update_test_status("ERROR")
                if rep.longrepr:
                    longerr = ""
                    for line in rep.longreprtext.splitlines():
                        longerr += line + "\n"
                    self.update_test_error(longerr)

        if rep.skipped:
            if hasattr(rep, "wasxfail"):
                self.update_test_status("xFAIL")
                if rep.longrepr:
                    longerr = ""
                    for line in rep.longreprtext.splitlines():
                        exception = line.startswith("E   ")
                        if exception:
                            longerr += line + "\n"
                    self.update_test_error(longerr.replace("E    ", ""))
            else:
                self.update_test_status("SKIP")
                if rep.longrepr:
                    longerr = ""
                    for line in rep.longreprtext.splitlines():
                        longerr += line + "\n"
                    self.update_test_error(longerr)

    def append_test_record(self, item):
        """Store one finished test as a plain dict.

        Nothing is rendered yet. Records are dicts of built-in types on purpose:
        that is what lets an xdist worker send its results back to the
        controller, which merges every worker's list and renders once.
        """
        record = {
            'suite_name': str(ConfigVars._suite_name),
            'test_name': str(ConfigVars._test_name),
            'nodeid': str(item.nodeid),
            'status': str(ConfigVars._test_status),
            'message': str(ConfigVars._current_error),
            'duration': round(ConfigVars._duration, 2),
            'rerun': 0,
            'index': self._collected.get(item.nodeid, len(self._collected) + len(self._records)),
            'worker': self.worker_id,
            'screenshot': None,
            'logs': self.collect_logs(str(ConfigVars._test_status)),
        }

        # Whatever the test did. A screenshot of a pass is a baseline, and one
        # of a skip says why it was skipped; keeping only the failures threw
        # away images that had been deliberately attached. Every record claims
        # the pending image, so none is left behind for a later test to pick up
        # and present as its own.
        if ConfigVars.screen_img is not None:
            record['screenshot'] = self.generate_screenshot_data()

        self.store_test_record(record)

    def refresh_record_logs(self, nodeid):
        """Re-read the captured output of the record already stored for a test."""
        slot = self._record_slots.get(str(nodeid))
        if slot is None: return

        record = self._records[slot]
        record['logs'] = self.collect_logs(record['status'])

    def collect_logs(self, status):
        """What pytest captured while this test ran, ready to be rendered.

        Plain lists and strings, like the rest of a record, so an xdist worker
        can ship them back to the controller that writes the report.
        """
        if self.logs_mode == 'none': return []
        if (self.logs_mode == 'failed') and (status not in ('FAIL', 'ERROR')): return []

        return format_log_sections(self._log_sections, self.log_limit)

    def store_test_record(self, record):
        """Keep one record per test, however many times it was attempted.

        pytest-rerunfailures runs the whole setup/call/teardown protocol again
        for every retry, so a retried test arrives here once per attempt. Only
        the attempt that stuck belongs in the report - the ones it superseded
        are what the rerun count is there to say.

        Counting attempts is the only reliable signal: --reruns, the ini key and
        @pytest.mark.flaky(reruns=n) can each set a different budget, and
        --only-rerun can stop the retries early, so no single number says how
        many attempts a given test will take.
        """
        slot = self._record_slots.get(record['nodeid'])

        if (slot is None) or (not self.rerun_plugin):
            self._record_slots[record['nodeid']] = len(self._records)
            self._records.append(record)
            return

        superseded = self._records[slot]

        # Both records may already stand for several attempts - that is what a
        # worker sends back - and the one being replaced is an attempt itself.
        record['rerun'] = int(superseded['rerun']) + int(record['rerun']) + 1

        # A retry that attached no screenshot of its own keeps the one from the
        # attempt it replaces, rather than dropping it from the report.
        if record['screenshot'] is None: record['screenshot'] = superseded['screenshot']

        record['index'] = superseded['index']
        self._records[slot] = record

    def build_report(self):
        """Turn every collected record into rows, totals and json data - once.

        Records come from this process and, on an xdist run, from each worker.
        Sorting them by collection position and then grouping by suite means a
        parallel report reads exactly like a serial one, no matter which worker
        happened to pick up which test.
        """
        records = sorted(self._records, key=lambda r: (r['index'], r['worker']))

        suites = OrderedDict()
        for record in records:
            suites.setdefault(record['suite_name'], []).append(record)

        for suite_index, suite_name in enumerate(suites):
            suite_records = suites[suite_name]

            for row_id, record in enumerate(suite_records):
                self.append_test_metrics_row(record, str(suite_index) + '-' + str(row_id))

            self.append_suite_metrics_row(suite_index, suite_name, suite_records)

        self.update_counts(records)

    def append_test_metrics_row(self, record, row_id):
        test_row_text = TestRow(
            sname=str(record['suite_name']),
            name=str(record['test_name']),
            stat=str(record['status']),
            dur=str(record['duration']),
            msg=str(record['message'][:50]),
            runt=row_id,
            log_count=str(self.attach_test_logs(record, row_id))
        )

        if len(record['message']) < 49:
            test_row_text.floating_error_text = ''
        else:
            test_row_text.floating_error_text = str(
                FloatingError(full_msg=str(record['message']), runt=row_id)
            )
            test_row_text.full_msg = str(record['message'])

        ConfigVars._test_metrics_content += str(test_row_text)

        if record['screenshot'] is not None:
            self.attach_screenshots(
                record['screenshot']['name'],
                record['screenshot']['suite'],
                record['screenshot']['test'],
                record['screenshot']['error'],
            )

    def attach_test_logs(self, record, row_id):
        """Park a test's captured output outside the table, return its size.

        The text is kept in a hidden block rather than in the row itself: a
        cell holding a few thousand lines would be swept into the table's
        search index and into every CSV, Excel and print export. The row only
        needs the line count, which is what the button shows and what tells the
        page whether there is anything to open at all.
        """
        sections = record.get('logs') or []
        if not sections: return 0

        body = ''
        for section in sections:
            body += str(TestLogSection(
                title=escape_log_text(section['title']),
                text=escape_log_text(section['text'])
            ))

        ConfigVars._test_logs_content += str(TestLog(
            runt=row_id,
            sname=escape_log_text(record['suite_name']),
            name=escape_log_text(record['test_name']),
            sections=body
        ))

        return count_log_lines(sections)

    def generate_screenshot_data(self):
        """Save the attached image and describe it for the report.

        The png is written by whichever process ran the test - workers share the
        filesystem with the controller - but the markup is left to the
        controller so every screenshot lands in the one report.
        """
        os.makedirs(ConfigVars.screen_base + '/pytest_screenshots', exist_ok=True)

        # Two workers failing in the same second must not overwrite each other's
        # image, so the name carries milliseconds and the worker id.
        _screenshot_name = str(round(time.time() * 1000))
        if self.worker_id: _screenshot_name += '-' + self.worker_id

        _screenshot_suite_name = ConfigVars._suite_name.split('/')[-1:][0].replace('.py', '')
        _screenshot_test_name = ConfigVars._test_name
        if len(ConfigVars._test_name) >= 19: _screenshot_test_name = ConfigVars._test_name[-17:]

        ConfigVars.screen_img.save(
            ConfigVars.screen_base + '/pytest_screenshots/' + _screenshot_name + '.png'
        )

        # Consumed: without this the same image is saved again for every later
        # failure that did not attach one of its own.
        ConfigVars.screen_img = None

        return {
            'name': _screenshot_name,
            'suite': _screenshot_suite_name,
            'test': _screenshot_test_name,
            # Blank for anything that passed, so the tile says how the test
            # ended rather than showing an empty caption.
            'error': ConfigVars._current_error or str(ConfigVars._test_status),
        }

    def append_suite_metrics_row(self, suite_index, name, records):
        self._test_suites(name)

        _status = {
            'total_pass': 0,
            'total_fail': 0,
            'total_skip': 0,
            'total_error': 0,
            'total_xpass': 0,
            'total_xfail': 0,
            'total_rerun': 0,
        }
        _keys = {
            'PASS': 'total_pass',
            'FAIL': 'total_fail',
            'SKIP': 'total_skip',
            'ERROR': 'total_error',
            'xPASS': 'total_xpass',
            'xFAIL': 'total_xfail',
        }

        _tests = {}
        for i, record in enumerate(records):
            _status[_keys.get(record['status'], 'total_error')] += 1
            _status['total_rerun'] += int(record['rerun'])

            _tests[i] = {
                'status': str(record['status']),
                'message': str(record['message']),
                'test_name': str(record['test_name']),
                'rerun': str(record['rerun']),
            }

        self.json_data['content']['suites'][suite_index] = {
            'suite_name': str(name),
            'tests': _tests,
            'status': _status,
        }

        suite_row_text = SuiteRow(
            sname=str(name),
            spass=str(_status['total_pass']),
            sfail=str(_status['total_fail']),
            sskip=str(_status['total_skip']),
            sxpass=str(_status['total_xpass']),
            sxfail=str(_status['total_xfail']),
            serror=str(_status['total_error']),
            srerun=str(_status['total_rerun'])
        )

        ConfigVars._suite_metrics_content += str(suite_row_text)

        self._test_passed(_status['total_pass'])
        self._test_failed(_status['total_fail'])
        self._test_skipped(_status['total_skip'])
        self._test_xpassed(_status['total_xpass'])
        self._test_xfailed(_status['total_xfail'])
        self._test_error(_status['total_error'])

    def update_counts(self, records):
        """Run-wide totals, counted off the records rather than accumulated.

        The controller of an xdist run never sees a test report of its own, so
        these cannot be incremented as tests go by.
        """
        ConfigVars._pass = len([r for r in records if r['status'] == 'PASS'])
        ConfigVars._fail = len([r for r in records if r['status'] == 'FAIL'])
        ConfigVars._skip = len([r for r in records if r['status'] == 'SKIP'])
        ConfigVars._xpass = len([r for r in records if r['status'] == 'xPASS'])
        ConfigVars._xfail = len([r for r in records if r['status'] == 'xFAIL'])
        ConfigVars._error = len(records) - (
            ConfigVars._pass + ConfigVars._fail + ConfigVars._skip
            + ConfigVars._xpass + ConfigVars._xfail
        )
        ConfigVars._total = ConfigVars._executed = len(records)

    def update_test_error(self, msg):
        ConfigVars._current_error = msg

    def update_test_status(self, status):
        ConfigVars._test_status = status

    def _date(self):
        return date.today().strftime("%B %d, %Y")

    def _test_suites(self, name):
        ConfigVars._test_suite_name.append(name.split('/')[-1].replace('.py', ''))

    def _test_passed(self, value):
        ConfigVars._test_pass_list.append(value)

    def _test_failed(self, value):
        ConfigVars._test_fail_list.append(value)

    def _test_skipped(self, value):
        ConfigVars._test_skip_list.append(value)

    def _test_xpassed(self, value):
        ConfigVars._test_xpass_list.append(value)

    def _test_xfailed(self, value):
        ConfigVars._test_xfail_list.append(value)

    def _test_error(self, value):
        ConfigVars._test_error_list.append(value)

    def renew_template_text(self, logo_url):
        template_text = HtmlTemplate(
            custom_logo=logo_url,
            execution_time=str(ConfigVars._execution_time),
            title=ConfigVars._title,
            title_full=str(ConfigVars._title_full),
            title_class=str(ConfigVars._title_class),
            total=str(
                ConfigVars._aspass + ConfigVars._asfail + ConfigVars._asskip + ConfigVars._aserror + ConfigVars._asxpass + ConfigVars._asxfail),
            executed=str(ConfigVars._executed),
            _pass=str(ConfigVars._aspass),
            fail=str(ConfigVars._asfail),
            skip=str(ConfigVars._asskip),
            error=str(ConfigVars._aserror),
            xpass=str(ConfigVars._asxpass),
            xfail=str(ConfigVars._asxfail),
            rerun=str(ConfigVars._asrerun),
            suite_metrics_row=str(ConfigVars._suite_metrics_content),
            test_metrics_row=str(ConfigVars._test_metrics_content),
            date=str(self._date()),
            test_suites=str(ConfigVars._test_suite_name),
            test_suite_length=str(len(ConfigVars._test_suite_name)),
            test_suite_pass=str(ConfigVars._test_pass_list),
            test_suites_fail=str(ConfigVars._test_fail_list),
            test_suites_skip=str(ConfigVars._test_skip_list),
            test_suites_xpass=str(ConfigVars._test_xpass_list),
            test_suites_xfail=str(ConfigVars._test_fail_list),
            test_suites_error=str(ConfigVars._test_error_list),
            archive_status=str(ConfigVars._archive_tab_content),
            archive_body_content=str(ConfigVars._archive_body_content),
            archive_count=str(ConfigVars._archive_count),
            archives=str(ConfigVars.archives),
            max_failure_suite_name_final=str(ConfigVars.max_failure_suite_name_final),
            max_failure_suite_count=str(ConfigVars.max_failure_suite_count),
            similar_max_failure_suite_count=str(ConfigVars.similar_max_failure_suite_count),
            max_failure_total_tests=str(ConfigVars.max_failure_total_tests),
            max_failure_percent=str(ConfigVars.max_failure_percent),
            trends_label=str(ConfigVars.trends_label),
            tpass=str(ConfigVars.tpass),
            tfail=str(ConfigVars.tfail),
            tskip=str(ConfigVars.tskip),
            attach_screenshot_details=str(ConfigVars._attach_screenshot_details),
            test_logs=str(ConfigVars._test_logs_content),
            logs_notice=str(ConfigVars._logs_notice),
            environment_rows=str(ConfigVars._environment_rows),
            environment=str(ConfigVars._environment_label),
            environment_title=str(ConfigVars._environment),
            environment_class=str(ConfigVars._environment_class)
        )

        return str(template_text)

    def generate_json_data(self, base):
        self.json_data['date'] = self._date()
        self.json_data['start_time'] = ConfigVars._start_execution_time
        self.json_data['total_suite'] = len(ConfigVars._test_suite_name)

        suite = self.json_data['content']['suites']
        for i in suite:
            for k in self.json_data['content']['suites'][i]['status']:
                if (k == 'total_fail' or k == 'total_error') and self.json_data['content']['suites'][i]['status'][k] != 0:
                    self.json_data['status'] = "FAIL"
                    break
                else:
                    continue

            try:
                if self.json_data['status'] == "FAIL": break
            except KeyError:
                if len(ConfigVars._test_suite_name) == i + 1: self.json_data['status'] = "PASS"

        for i in suite:
            for k in self.json_data['content']['suites'][i]['status']:
                if k == 'total_pass':
                    ConfigVars._aspass += self.json_data['content']['suites'][i]['status'][k]
                elif k == 'total_fail':
                    ConfigVars._asfail += self.json_data['content']['suites'][i]['status'][k]
                elif k == 'total_skip':
                    ConfigVars._asskip += self.json_data['content']['suites'][i]['status'][k]
                elif k == 'total_error':
                    ConfigVars._aserror += self.json_data['content']['suites'][i]['status'][k]
                elif k == 'total_xpass':
                    ConfigVars._asxpass += self.json_data['content']['suites'][i]['status'][k]
                elif k == 'total_xfail':
                    ConfigVars._asxfail += self.json_data['content']['suites'][i]['status'][k]
                elif k == 'total_rerun':
                    ConfigVars._asrerun += self.json_data['content']['suites'][i]['status'][k]

        ConfigVars._astotal = ConfigVars._aspass + ConfigVars._asfail + ConfigVars._asskip + ConfigVars._aserror + ConfigVars._asxpass + ConfigVars._asxfail

        self.json_data.setdefault('status_list', {})['pass'] = str(ConfigVars._aspass)
        self.json_data.setdefault('status_list', {})['fail'] = str(ConfigVars._asfail)
        self.json_data.setdefault('status_list', {})['skip'] = str(ConfigVars._asskip)
        self.json_data.setdefault('status_list', {})['error'] = str(ConfigVars._aserror)
        self.json_data.setdefault('status_list', {})['xpass'] = str(ConfigVars._asxpass)
        self.json_data.setdefault('status_list', {})['xfail'] = str(ConfigVars._asxfail)
        self.json_data.setdefault('status_list', {})['rerun'] = str(ConfigVars._asrerun)
        self.json_data['total_tests'] = str(ConfigVars._astotal)

        with open(base + '/output.json', 'w') as outfile:
            json.dump(self.json_data, outfile)

    def update_archives_template(self, base):
        f = glob.glob(base + '/archive/*.json')
        cf = glob.glob(base + '/output.json')
        if len(f) > 0:
            ConfigVars._archive_count = len(f) + 1
            self.load_archive(cf, value='current')

            f.sort(reverse=True)
            self.load_archive(f, value='history')
        else:
            ConfigVars._archive_count = 1
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
                archive_row_text = ArchiveRow(astate=state(data['status'].lower())[0],
                                              astate_color=state(data['status'].lower())[1])
                if value == "current":
                    archive_row_text.astatus = 'build #' + str(ConfigVars._archive_count)
                    archive_row_text.acount = str(ConfigVars._archive_count)
                else:
                    archive_row_text.astatus = 'build #' + str(len(f) - i)
                    archive_row_text.acount = str(len(f) - i)

                adate = datetime.strptime(
                    data['date'].split(None, 1)[0][:1 + 2:] + ' ' +
                    data['date'].split(None, 1)[1].replace(',', ''), "%b %d %Y"
                )

                atime = \
                    "".join(list(filter(lambda x: ':' in x, time.ctime(float(data['start_time'])).split(' ')))).rsplit(
                        ':',
                        1)[0]
                archive_row_text.adate = str(adate.date()) + ' | ' + str(time_converter(atime))
                ConfigVars._archive_tab_content += str(archive_row_text)

                _archive_body_text = ArchiveBody(
                    total_tests=data['total_tests'],
                    date=data['date'].upper(),
                    _pass=data['status_list']['pass'],
                    fail=data['status_list']['fail'],
                    skip=data['status_list']['skip'],
                    xpass=data['status_list']['xpass'],
                    xfail=data['status_list']['xfail'],
                    error=data['status_list']['error'],
                    status=data['status'].lower()
                )

                if value == "current":
                    _archive_body_text.iloop = str(i)
                    _archive_body_text.acount = str(ConfigVars._archive_count)
                else:
                    _archive_body_text.iloop = str(i + 1)
                    _archive_body_text.acount = str(len(f) - i)

                try:
                    _archive_body_text.rerun = data['status_list']['rerun']
                except KeyError:
                    _archive_body_text.rerun = '0'

                index = i
                if value != "current": index = i + 1
                ConfigVars.archives.setdefault(str(index), {})['pass'] = data['status_list']['pass']
                ConfigVars.archives.setdefault(str(index), {})['fail'] = data['status_list']['fail']
                ConfigVars.archives.setdefault(str(index), {})['skip'] = data['status_list']['skip']
                ConfigVars.archives.setdefault(str(index), {})['xpass'] = data['status_list']['xpass']
                ConfigVars.archives.setdefault(str(index), {})['xfail'] = data['status_list']['xfail']
                ConfigVars.archives.setdefault(str(index), {})['error'] = data['status_list']['error']

                try:
                    ConfigVars.archives.setdefault(str(index), {})['rerun'] = data['status_list']['rerun']
                except KeyError:
                    ConfigVars.archives.setdefault(str(index), {})['rerun'] = '0'

                ConfigVars.archives.setdefault(str(index), {})['total'] = data['total_tests']
                ConfigVars._archive_body_content += str(_archive_body_text)

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
            ConfigVars.trends_label.append(
                str(time_converter(atime)).upper() + ' | ' + str(adate.date().strftime("%b")) + ' '
                + str(adate.date().strftime("%d")))

            ConfigVars.tpass.append(data['status_list']['pass'])
            ConfigVars.tfail.append(int(data['status_list']['fail']) + int(data['status_list']['error']))
            ConfigVars.tskip.append(data['status_list']['skip'])

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
                ConfigVars.trends_label.append(
                    str(time_converter(atime)).upper() + ' | ' + str(adate.date().strftime("%b")) + ' '
                    + str(adate.date().strftime("%d")))

                ConfigVars.tpass.append(data['status_list']['pass'])
                ConfigVars.tfail.append(int(data['status_list']['fail']) + int(data['status_list']['error']))
                ConfigVars.tskip.append(data['status_list']['skip'])

                if i == 4: break

    def attach_screenshots(self, screen_name, test_suite, test_case, test_error):

        _screenshot_details = ScreenshotDetails(
            screen_name=str(screen_name),
            ts=str(test_suite),
            tc=str(test_case),
            te=str(test_error)
        )

        if len(test_case) == 17: test_case = '..' + test_case

        ConfigVars._attach_screenshot_details += str(_screenshot_details)
