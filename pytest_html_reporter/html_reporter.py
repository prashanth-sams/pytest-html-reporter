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
from html_page.attachment_body import AttachmentBody
from html_page.attachment_item import AttachmentItem
from html_page.attachment_meta import AttachmentMeta
from html_page.attachment_part import AttachmentPart
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
    escape_report_text,
    js_literal,
    count_log_lines,
    report_attachments_mode,
    report_attachment_limit,
    archive_days,
    archive_since,
    archive_cutoff,
    expired_archives,
    generate_report_links,
)
from pytest_html_reporter.coverage_report import (
    collect_coverage,
    generate_coverage_view,
)
from pytest_html_reporter.attachments import (
    attachment_size,
    filename_for,
    human_size,
    take_attachments,
    trim_parts,
)
from pytest_html_reporter.time_converter import time_converter
from pytest_html_reporter.const_vars import ConfigVars


# What fits the caption strip under a gallery tile.
SCREENSHOT_NAME_MAX = 19

# Stand-ins for the test name of a file that never produced a test at all.
COLLECT_ERROR_NAME = '(collection error)'
COLLECT_SKIP_NAME = '(module skipped)'


def archived_coverage(data):
    """One build's coverage percentage out of its output.json, or None.

    Every archived build predating this feature simply has no coverage key,
    and so does any build that ran without coverage measured - both are "not
    known", which is a different answer from zero.
    """
    try:
        return float((data.get('coverage') or {})['percent'])
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


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
        self.attachments_mode = report_attachments_mode(config)
        self.attachment_limit = report_attachment_limit(config)

        # Age-based retention, alongside --archive-count. A run on a schedule
        # wants "the last 30 days": a build count has to be retuned every time
        # the schedule changes, and says nothing about how far back the report
        # actually reaches.
        self.archive_days = archive_days(config)
        self.archive_since = archive_since(config)

        # One record per finished test. In a serial run this process fills the
        # list on its own; under xdist every worker fills its own copy and the
        # controller merges them all before anything is rendered.
        self._records = []

        # Where each test's record sits in that list, so a retry can replace the
        # attempt it superseded instead of being reported as another test.
        self._record_slots = {}

        # Which collectors have already been recorded as failed or skipped, so
        # a broken file seen by several processes is reported once.
        self._collect_slots = set()
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

    def pytest_collectreport(self, report):
        """Keep a file that never produced a test, so it cannot vanish silently.

        A module that fails to import - or one skipped at module level - yields
        no items at all, so nothing reaches pytest_runtest_teardown and the
        whole file, every test in it and the error itself were missing from the
        report while pytest printed them. A broken import is exactly the case
        where the report is read to find out what happened, and it was the one
        case the report did not cover.
        """
        if report.passed: return
        if not report.nodeid: return  # the session collector itself

        # A skipped collector's longrepr is a (path, lineno, reason) tuple, and
        # rendering it as text would put the tuple's repr in the report.
        if report.skipped and isinstance(report.longrepr, tuple):
            message = str(report.longrepr[2])
        else:
            message = str(report.longreprtext or '')

        self.store_collect_record({
            'suite_name': str(report.nodeid),
            'test_name': COLLECT_SKIP_NAME if report.skipped else COLLECT_ERROR_NAME,
            'nodeid': str(report.nodeid),
            'status': 'SKIP' if report.skipped else 'ERROR',
            'message': message,
            'duration': 0,
            'rerun': 0,
            # Collection runs before any test does, and before collection order
            # is even known, so these sort ahead of the run itself: a file that
            # never loaded is the first thing worth seeing.
            'index': -1,
            'worker': self.worker_id,
            'screenshot': None,
            'logs': [],
            'attachments': [],
            'collect': True,
        })

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
                self.store_record(record)

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
        """Apply the retention limits to the builds kept on disk.

        --archive-count, --archive-days and --archive-since intersect: a build
        has to satisfy every limit that is set to survive. Nothing set keeps
        everything, which is how the report grows until it is slow to open.

        The folder is taken from report_path rather than from self.path: the
        path can name the html file itself - ./report/report.html - and the
        archive sits beside it, in the folder.
        """
        archive_dir = os.path.join(self.report_path[0], 'archive')
        cutoff = archive_cutoff(days=self.archive_days, since=self.archive_since)

        if self.archive_count == '' and cutoff is None:
            return

        if self.archive_count == '0':
            if os.path.isdir(archive_dir):
                shutil.rmtree(archive_dir)
            return

        if not os.path.isdir(archive_dir):
            return

        # The build being reported now is shown alongside the archived ones and
        # counts against --archive-count, so one fewer is kept on disk.
        keep = int(self.archive_count) - 1 if self.archive_count != '' else None

        for path in expired_archives(glob.glob(os.path.join(archive_dir, '*.json')),
                                     keep=keep, cutoff=cutoff):
            os.remove(path)

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

            # read whatever coverage this run produced, before the json is
            # written: output.json carries the percentage, which is what lets
            # the next build show a delta and the trend read across builds
            self.collect_coverage_data(base)

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

            # build the Coverage tab from what was collected above, now that
            # update_trends has filled in the archived builds' percentages
            generate_coverage_view(self.config)

            # extra side-nav entries asked for with --report-link
            generate_report_links(self.config)

            # generate html report
            live_logs_file = open(path, 'w', encoding='utf-8')
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

        # The record was built from the teardown hook, which runs before pytest
        # has finished reporting that phase, so whatever the teardown itself
        # said has to be folded into the stored record here.
        if rep.when == 'teardown': self.refresh_record(rep.nodeid)

    def refresh_record(self, nodeid):
        """Fold the teardown phase into the record already stored for a test.

        A fixture that blows up while cleaning up left the test standing in the
        report as a plain pass: pytest counted it as an error, the report did
        not, and a failing run could read as green. Captured output is re-read
        at the same time - after the status, so a test that only failed in its
        teardown keeps its output under --report-logs failed - which is what
        puts fixture teardown output, the output of the code that cleans up
        after a failure, in the report at all.
        """
        slot = self._record_slots.get(str(nodeid))
        if slot is None: return

        record = self._records[slot]

        # A test that already failed keeps the failure it was reported with:
        # that is the headline, and pytest lists it the same way, as a failure
        # with an error beside it rather than as an error.
        if (ConfigVars._test_status == 'ERROR') and (record['status'] not in ('FAIL', 'ERROR')):
            record['status'] = 'ERROR'
            record['message'] = str(ConfigVars._current_error)

        if self.logs_mode != 'none':
            record['logs'] = self.collect_logs(record['status'])

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
            'attachments': self.collect_attachments(str(ConfigVars._test_status)),
        }

        # Whatever the test did. A screenshot of a pass is a baseline, and one
        # of a skip says why it was skipped; keeping only the failures threw
        # away images that had been deliberately attached. Every record claims
        # the pending image, so none is left behind for a later test to pick up
        # and present as its own.
        if ConfigVars.screen_img is not None:
            record['screenshot'] = self.generate_screenshot_data()

        self.store_test_record(record)

    def collect_logs(self, status):
        """What pytest captured while this test ran, ready to be rendered.

        Plain lists and strings, like the rest of a record, so an xdist worker
        can ship them back to the controller that writes the report.
        """
        if self.logs_mode == 'none': return []
        if (self.logs_mode == 'failed') and (status not in ('FAIL', 'ERROR')): return []

        return format_log_sections(self._log_sections, self.log_limit)

    def collect_attachments(self, status):
        """The text, JSON and API calls this test handed over, trimmed to size.

        The buffer is drained whatever the mode says. An attachment left in it
        would be picked up by the next test to finish and reported as that
        test's own - the bug screenshots had before every record started
        claiming the pending image.
        """
        pending = take_attachments()

        if self.attachments_mode == 'none': return []
        if (self.attachments_mode == 'failed') and (status not in ('FAIL', 'ERROR')): return []

        collected = []
        for attachment in pending:
            attachment = dict(attachment)
            attachment['parts'] = trim_parts(attachment['parts'], self.attachment_limit)
            collected.append(attachment)

        return collected

    def store_record(self, record):
        """Store a record of either kind - a test that ran, or a file that did not."""
        if record.get('collect'):
            self.store_collect_record(record)
        else:
            self.store_test_record(record)

    def store_collect_record(self, record):
        """Keep one record per collector that failed, however many saw it fail.

        Every xdist worker collects the whole suite, and the controller is sent
        their collect reports as well, so the same unimportable file arrives
        here once per process. Only the first is kept.
        """
        if record['nodeid'] in self._collect_slots: return

        self._collect_slots.add(record['nodeid'])
        self._records.append(record)

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
        # attempt it replaces, rather than dropping it from the report. The
        # same goes for its attachments: a flaky test that captured the failing
        # response on its first attempt should not lose it by then passing.
        if record['screenshot'] is None: record['screenshot'] = superseded['screenshot']
        if not record.get('attachments'): record['attachments'] = superseded.get('attachments') or []

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
        # Escaped here rather than in the record: output.json carries the same
        # text and wants it raw. The message is cut to length first, so the cut
        # cannot land in the middle of an entity and leave "&a" on the page.
        test_row_text = TestRow(
            sname=escape_report_text(record['suite_name']),
            name=escape_report_text(record['test_name']),
            stat=str(record['status']),
            dur=str(record['duration']),
            msg=escape_report_text(record['message'][:50]),
            runt=row_id,
            log_count=str(self.attach_test_logs(record, row_id)),
            attach_count=str(self.attach_test_data(record, row_id))
        )

        # The raw length, not the escaped one: this asks whether the message was
        # cut short, and escaping it first would make a message full of angle
        # brackets look long enough to need a modal it does not need.
        if len(record['message']) < 49:
            test_row_text.floating_error_text = ''
        else:
            test_row_text.floating_error_text = str(
                FloatingError(full_msg=escape_report_text(record['message']), runt=row_id)
            )

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
                title=escape_report_text(section['title']),
                text=escape_report_text(section['text'])
            ))

        ConfigVars._test_logs_content += str(TestLog(
            runt=row_id,
            sname=escape_report_text(record['suite_name']),
            name=escape_report_text(record['test_name']),
            sections=body
        ))

        return count_log_lines(sections)

    def attach_test_data(self, record, row_id):
        """Park a test's attachments outside the table, return how many there are.

        Same reasoning as the captured output: a response body sitting in a
        cell would be swept into the table's search index and into every CSV,
        Excel and print export. The row keeps the count, which is all it needs
        to show a button and all the Attachments tab needs to be linked to.
        """
        attachments = record.get('attachments') or []

        for index, attachment in enumerate(attachments):
            aid = '%s-%s' % (row_id, index)

            parts = ''
            for part in attachment['parts']:
                parts += str(AttachmentPart(
                    title=escape_report_text(part['title']),
                    format=escape_report_text(part['format']),
                    text=escape_report_text(part['text'])
                ))

            meta = ''
            for label, value in attachment['meta']:
                meta += str(AttachmentMeta(
                    label=escape_report_text(label),
                    value=escape_report_text(value),
                    title=escape_report_text(value)
                ))

            ConfigVars._attachment_store += str(AttachmentBody(
                aid=aid,
                sname=escape_report_text(record['suite_name']),
                name=escape_report_text(record['test_name']),
                title=escape_report_text(attachment['title']),
                filename=escape_report_text(filename_for(record['test_name'], attachment['title'])),
                meta=meta,
                parts=parts
            ))

            ConfigVars._attachment_items += str(AttachmentItem(
                aid=aid,
                runt=row_id,
                kind=escape_report_text(attachment['kind']),
                status=escape_report_text(attachment['status']),
                code=escape_report_text(attachment['code']),
                detail=escape_report_text(attachment['detail']
                                          or human_size(attachment_size(attachment))),
                ms=escape_report_text(attachment.get('ms', '')),
                size=str(attachment_size(attachment)),
                title=escape_report_text(attachment['title']),
                # The file name, not the path: every entry in the rail carries
                # the same directories, and they were crowding out the test
                # name, which is the half that says which entry this is.
                sname=escape_report_text(record['suite_name'].split('/')[-1]),
                name=escape_report_text(record['test_name']),
                search=escape_report_text(self.attachment_search_text(record, attachment))
            ))

        return len(attachments)

    def attachment_search_text(self, record, attachment):
        """What the Attachments search box matches an entry on.

        The suite, the test, the title and every meta value - so a url, a
        method or a status code finds the call - but not the payloads: those
        are already several thousand characters each, and repeating them in an
        attribute would double the size of the file to no end.
        """
        terms = [record['suite_name'], record['test_name'], attachment['title'],
                 attachment['kind'], attachment['code']]
        terms += [value for _, value in attachment['meta']]

        return ' '.join(term for term in terms if term).lower()

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
        # The head of the name, not its tail. Keeping the last 17 characters
        # turned test_login_page_renders into "ogin_page_renders", which names
        # nothing and reads as a bug in the report.
        _screenshot_test_name = ConfigVars._test_name
        if len(_screenshot_test_name) > SCREENSHOT_NAME_MAX:
            _screenshot_test_name = _screenshot_test_name[:SCREENSHOT_NAME_MAX - 2] + '..'

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
            sname=escape_report_text(name),
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

    def collect_coverage_data(self, base):
        """Read this run's coverage, and put its headline in output.json.

        Stored alongside the test counts rather than in a file of its own: the
        archives, the trend chart and Suite Highlights all read output.json
        already, so a percentage kept there is a percentage every one of them
        can reach without a second format to keep in step.
        """
        summary, notice = collect_coverage(self.config, base, self._sessionstarttime)

        ConfigVars._coverage = summary
        ConfigVars._coverage_notice = notice

        if summary is None: return

        self.json_data['coverage'] = {
            'percent': summary['percent'],
            'statements': summary['statements'],
            'covered': summary['covered'],
            'missing': summary['missing'],
            'branch': summary['branch'],
        }

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
            title=escape_report_text(ConfigVars._title),
            title_full=escape_report_text(ConfigVars._title_full),
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
            test_suites=js_literal(ConfigVars._test_suite_name),
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
            max_failure_suite_name_final=escape_report_text(ConfigVars.max_failure_suite_name_final),
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
            attachment_items=str(ConfigVars._attachment_items),
            attachment_store=str(ConfigVars._attachment_store),
            logs_notice=str(ConfigVars._logs_notice),
            environment_rows=str(ConfigVars._environment_rows),
            environment=escape_report_text(ConfigVars._environment_label),
            environment_title=escape_report_text(ConfigVars._environment),
            environment_class=str(ConfigVars._environment_class),
            coverage_state=str(ConfigVars._coverage_state),
            coverage_display=str(ConfigVars._coverage_display),
            coverage_dash=str(ConfigVars._coverage_dash),
            coverage_grade=str(ConfigVars._coverage_grade),
            coverage_tiles=str(ConfigVars._coverage_tiles),
            coverage_rows=str(ConfigVars._coverage_rows),
            coverage_meta=str(ConfigVars._coverage_meta),
            coverage_delta=str(ConfigVars._coverage_delta),
            coverage_delta_class=str(ConfigVars._coverage_delta_class),
            coverage_target=str(ConfigVars._coverage_target),
            coverage_link=str(ConfigVars._coverage_link),
            coverage_note=str(ConfigVars._coverage_note),
            coverage_notice=escape_report_text(ConfigVars._coverage_notice),
            coverage_branch=str(ConfigVars._coverage_branch),
            coverage_trend_state=str(ConfigVars._coverage_trend_state),
            coverage_trend_labels=str(ConfigVars._coverage_trend_labels),
            coverage_trend_values=str(ConfigVars._coverage_trend_values),
            coverage_chip=str(ConfigVars._coverage_chip),
            report_links=str(ConfigVars._report_links)
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
            ConfigVars.tcoverage.append(archived_coverage(data))

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
                # None, not 0: a build that ran before coverage was switched on
                # never measured anything, and drawing it as zero would invent a
                # cliff in the trend that never happened.
                ConfigVars.tcoverage.append(archived_coverage(data))

                if i == 4: break

    def attach_screenshots(self, screen_name, test_suite, test_case, test_error):

        # The suite and test names land in a data-caption attribute as well as
        # in the tile's text, so they are escaped for both.
        _screenshot_details = ScreenshotDetails(
            screen_name=escape_report_text(screen_name),
            ts=escape_report_text(test_suite),
            tc=escape_report_text(test_case),
            te=escape_report_text(test_error)
        )

        ConfigVars._attach_screenshot_details += str(_screenshot_details)
