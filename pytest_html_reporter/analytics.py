"""Cross-build analytics: what every retained build says about each test.

The Dashboard answers "how did this run go?" and reads one build to do it.
This answers a different question - "how does this test behave?" - and no
single build can. Every archived build already carries the same per-test
status list the run just wrote, so a test's whole history has been sat on
disk all along; it had simply never been read across files before.

Nothing here collects anything new. It opens ``output.json`` and every
``archive/*.json`` beside it, lines the builds up oldest first, and reduces
them to the handful of numbers a person actually triages on: which tests
flip, which have never passed, what the pass rate is doing over time, and
where the run's minutes go.
"""

import glob
import json
import os
import re
import time
from collections import OrderedDict

from html_page.analytics_fault import AnalyticsFault
from html_page.analytics_move import AnalyticsMove
from html_page.analytics_owner import AnalyticsOwner
from html_page.analytics_row import AnalyticsRow
from html_page.analytics_tile import AnalyticsTile
from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.markers import severity_rank
from pytest_html_reporter.util import escape_report_text, js_literal

# Bucket edges for the duration histogram, in seconds. Anything past the last
# edge lands in the overflow bucket, which is the one worth looking at.
DURATION_EDGES = (0.1, 0.5, 1.0, 5.0, 10.0, 30.0)
DURATION_LABELS = ('< 100ms', '100 - 500ms', '0.5 - 1s', '1 - 5s',
                   '5 - 10s', '10 - 30s', '30s +')

# How many builds the trend charts draw. The maths behind the tables still
# reads every build kept on disk - --archive-count is what bounds that - but
# forty labels on one axis is unreadable, and the recent shape is the point.
TREND_BUILDS = 20

# How many of a test's outcomes the sparkline in its row shows.
SPARK_BUILDS = 12

# Rows in the slowest-tests chart, and names listed under each movement card.
TOP_SLOWEST = 10
MOVEMENT_NAMES = 6

# A test counts as consistently failing once it has failed this many builds in
# a row: one failure is a failure, a standing one is a different conversation.
BROKEN_STREAK = 2

# Exception groups listed in the failure panel, and test names shown under each.
FAULT_TYPES = 8
FAULT_NAMES = 4

# Where a failure lands when nothing in its message names an exception - a
# collection error, a fixture that could not be found, a message the reporter
# never captured. Ranked last however many are in it: it is the one group that
# says nothing about what went wrong.
OTHER = 'Unclassified'


def outcome(status):
    """Reduce a pytest status to the three things a history reads as.

    ``xFAIL`` and ``xPASS`` sit on the pass side. Both are outcomes the suite
    declared in advance, neither turns a build red, and counting an expected
    failure against a test's pass rate would make every xfail-marked test look
    like the least reliable thing in the suite.
    """
    status = str(status or '').upper()

    if status in ('FAIL', 'ERROR'): return 'fail'
    if status == 'SKIP': return 'skip'
    return 'pass'


# Colour written into the message by pytest's own diff, or by whatever the
# test printed. It is invisible in the report - the page renders the escapes
# as nothing - but it sits between the start of a line and the exception name.
_ANSI = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')

# A line that opens with a raised exception: an optionally dotted name, then a
# colon or the end of the line. Anchored at the start on purpose. An assertion
# diff prints lines like "- ValueError: nope", and that is a string being
# compared, not something that was raised.
_RAISED = re.compile(r'^((?:[A-Za-z_]\w*\.)*[A-Z]\w*)\s*(?::|$)')

# What makes a name read as an exception rather than as a word that happens to
# start a line. "Failed" and "Skipped" are pytest's own; "Message" is
# Selenium's, and is exactly what this keeps out - a WebDriver error prints
# "TimeoutException: Message: ..." and then more "Message:" lines under it.
_RAISED_SUFFIXES = ('Error', 'Exception', 'Failure', 'Failed', 'Skipped',
                    'Timeout', 'Interrupt', 'Abort', 'Exit')

# pytest marks the lines it wants read with an "E" and pads the rest out to the
# source indent beside it. A failure has had that stripped by the time it is
# stored, but an error keeps the whole traceback as printed - and the exception
# is on one of the marked lines.
_MARKER = re.compile(r'^E\s+')


def exception_type(message):
    """The exception a stored failure message came out of, or ``''``.

    What is stored per test is what pytest printed, not an exception object -
    by the time a build is read back it is text and nothing else, and in an
    archive it always was. So the type is read back out of the message.

    One pass, but the two things it looks for want opposite ends of the
    message. A name spelled like an exception is taken from the *last* line
    that has one: a chained failure prints the original traceback first and the
    exception that actually surfaced last, which is the one pytest itself
    reports. Anything else is taken from the *first* line, where a plain
    traceback puts its headline.

    A bare ``assert`` is read as an AssertionError. pytest prints those with no
    type name at all - "assert 1 == 2" and nothing else - and they are far too
    common a failure to leave sitting in the unclassified pile.
    """
    raised = named = ''

    for line in _ANSI.sub('', str(message or '')).splitlines():
        line = _MARKER.sub('', line.strip())
        if not line: continue

        match = _RAISED.match(line)
        if match is None:
            if not named and line.startswith('assert '): named = 'AssertionError'
            continue

        # Dotted names are cut to the class: "selenium.common.exceptions.
        # TimeoutException" and "TimeoutException" are one group, and which of
        # them a message carries is down to how the traceback was rendered.
        name = match.group(1).rsplit('.', 1)[-1]

        if name.endswith(_RAISED_SUFFIXES): raised = name
        elif not named: named = name

    return raised or named


def _to_int(value, fallback=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# A per-test duration past this is not a measurement of anything. Reports
# written before the duration was taken from pytest's own phase timings billed
# a test that merged a bundle mid-run with the time since whatever start the
# merge had installed - the epoch, or a shard's own stamp - and those archives
# are still on disk. Read back literally, one of them draws a 56-year bar in
# the slowest-tests chart and carries every total on the tab with it.
#
# A day, because that is the line past which the number is more likely to be a
# subtraction gone wrong than a test: nothing this tab is for - which bands are
# filling up, which ten tests to look at next - survives a single row being
# larger than every other row put together, and the run's own Test Metrics
# table still prints whatever was recorded either way.
MAX_DURATION = 24 * 60 * 60


def _plausible(duration):
    """A duration, or None where the archive holds something that cannot be one.

    None rather than zero, which is the same answer this gives for a build
    archived before durations were recorded at all: unknown, so it is left out
    of the totals instead of being drawn as a test that took no time.
    """
    if duration is None: return None
    if duration < 0 or duration > MAX_DURATION: return None

    return duration


def _read_json(path):
    try:
        with open(path, encoding='utf-8') as handle:
            return json.load(handle)
    except (OSError, ValueError):
        # A half-written or hand-edited archive is skipped rather than taking
        # the whole tab down: the other builds still have something to say.
        return None


def _label(stamp, date_text):
    """Short axis label for one build - "Sep 01 14:18"."""
    if stamp:
        return time.strftime('%b %d %H:%M', time.localtime(stamp))

    # A build written before start_time was recorded still has its date.
    return str(date_text or '')


def _normalise(data, stamp):
    """One build, flattened to what the analytics actually read.

    Tests are keyed by suite and name together. That is the only identity the
    archives carry - ``nodeid`` is not written into them - and it is stable
    across builds, which is the whole requirement.
    """
    tests = OrderedDict()
    counts = {'pass': 0, 'fail': 0, 'skip': 0}
    total_duration = 0.0
    timed = False

    suites = (data.get('content') or {}).get('suites') or {}
    for suite in suites.values():
        suite_name = str(suite.get('suite_name', ''))

        for test in (suite.get('tests') or {}).values():
            name = str(test.get('test_name', ''))
            state = outcome(test.get('status'))
            duration = _plausible(_to_float(test.get('duration')))

            counts[state] += 1
            if duration is not None:
                total_duration += duration
                timed = True

            tests['%s::%s' % (suite_name, name)] = {
                'suite': suite_name,
                'name': name,
                'status': str(test.get('status', '')),
                'outcome': state,
                # Kept as written so the failure grouping can read the
                # exception back out of it. Every build on disk already
                # carries this; nothing new is being collected for it.
                'message': str(test.get('message', '')),
                'rerun': _to_int(test.get('rerun')),
                'duration': duration,
                # A list, and empty for every build archived before ownership
                # was written into the file at all - which reads as unowned,
                # because that is what those tests were as far as any report
                # could tell at the time.
                'owner': [str(name) for name in (test.get('owner') or [])],
                # One word or none. Empty for every build archived before
                # severity was written into the file, which reads as unrated -
                # what those tests were, as far as any report could tell.
                'severity': str(test.get('severity') or ''),
            }

    return {
        'stamp': stamp,
        'label': _label(stamp, data.get('date')),
        'date': str(data.get('date', '')),
        'status': str(data.get('status', '')),
        'tests': tests,
        'counts': counts,
        'total': len(tests),
        # None, not zero: builds archived before per-test durations were
        # recorded never measured this, and drawing them as instant would
        # invent a cliff in the duration trend that never happened.
        'duration': round(total_duration, 2) if timed else None,
        'reruns': sum(test['rerun'] for test in tests.values()),
    }


def read_builds(base):
    """Every build still on disk, oldest first, the current run last.

    The current run is ``output.json``; the ones before it were moved into
    ``archive/`` on their way out and are read from there. Retention has
    already been applied by the time this runs, so what is on disk is exactly
    what --archive-count and friends asked to keep.
    """
    builds = []

    for path in glob.glob(os.path.join(base, 'archive', '*.json')):
        data = _read_json(path)
        if not data: continue

        # Sorted on the stamp inside the file rather than the file name: the
        # name carries the same number, but as text, where 1788194287.2 sorts
        # after 1788194287.271306.
        stamp = _to_float(data.get('start_time')) or os.path.getmtime(path)
        builds.append(_normalise(data, stamp))

    builds.sort(key=lambda build: build['stamp'])

    current = _read_json(os.path.join(base, 'output.json'))
    if current:
        stamp = _to_float(current.get('start_time')) or time.time()
        builds.append(_normalise(current, stamp))

    _label_distinctly(builds)

    return builds


def _label_distinctly(builds):
    """Make sure no two builds share an axis label.

    A pipeline that runs the suite three times inside a minute - a rerun, a
    retry, a matrix leg - produces three builds stamped to the same minute,
    and three identical ticks on the x axis is a chart nobody can read. The
    repeats are numbered rather than given seconds, because the seconds are
    not what anyone is looking for.
    """
    seen = {}

    for build in builds:
        label = build['label']
        seen[label] = seen.get(label, 0) + 1

    used = {}
    for build in builds:
        label = build['label']
        if seen[label] < 2: continue

        used[label] = used.get(label, 0) + 1
        build['label'] = '%s (%d)' % (label, used[label])


def _streak(states):
    """How many builds the newest outcome has held for, uninterrupted."""
    if not states: return 0

    latest = states[-1]
    run = 0
    for state in reversed(states):
        if state != latest: break
        run += 1

    return run


def _summarise(history, build_count):
    points = history['points']
    states = [point['outcome'] for point in points]

    # Skips say nothing about whether a test works, so the pass/fail maths -
    # rate, flips, streak - is done on the builds that decided something. A
    # test skipped for three builds between two passes has not flipped twice.
    decided = [state for state in states if state != 'skip']
    durations = [point['duration'] for point in points if point['duration'] is not None]

    passes = decided.count('pass')
    fails = decided.count('fail')
    flips = sum(1 for before, after in zip(decided, decided[1:]) if before != after)

    history['runs'] = len(points)
    history['passes'] = passes
    history['fails'] = fails
    history['skips'] = states.count('skip')
    history['pass_rate'] = round(100.0 * passes / len(decided), 1) if decided else None
    history['flips'] = flips
    history['flip_rate'] = flips / float(len(decided) - 1) if len(decided) > 1 else 0.0
    history['reruns'] = sum(point['rerun'] for point in points)
    history['status'] = points[-1]['status']
    history['outcome'] = states[-1]
    history['streak'] = _streak(decided)
    history['duration'] = points[-1]['duration']
    history['avg_duration'] = round(sum(durations) / len(durations), 2) if durations else None
    history['spark'] = states[-SPARK_BUILDS:]
    history['current'] = points[-1]['build'] == build_count - 1

    # A retry inside a single build is the least ambiguous flake evidence
    # there is: the same code, the same build, two different answers.
    history['flaky'] = bool(flips) or bool(history['reruns'])
    history['broken'] = bool(decided) and fails == len(decided) and history['streak'] >= BROKEN_STREAK

    # A test that only ever fails is not flaky, it is broken, and listing it
    # under flakiness sends people hunting for a race that is not there.
    if history['broken']: history['flaky'] = False


def histories(builds):
    """Every test ever seen across the builds, with its record summarised."""
    tracked = OrderedDict()

    for position, build in enumerate(builds):
        for key, test in build['tests'].items():
            history = tracked.get(key)

            if history is None:
                history = tracked[key] = {
                    'key': key,
                    'suite': test['suite'],
                    'name': test['name'],
                    'owner': [],
                    'severity': '',
                    'points': [],
                }

            # Overwritten each build rather than merged: ownership is a fact
            # about now, not a history. A test that moved teams last month
            # should page the team that has it today, and a union of every
            # owner it ever had would page both.
            if test['owner']: history['owner'] = list(test['owner'])

            # And for the same reason: a test raised to `blocker` this month is
            # a blocker, not the average of what it has been rated before.
            if test['severity']: history['severity'] = test['severity']

            history['points'].append({
                'build': position,
                'outcome': test['outcome'],
                'status': test['status'],
                'rerun': test['rerun'],
                'duration': test['duration'],
            })

    for history in tracked.values():
        _summarise(history, len(builds))

    return tracked


def movements(builds):
    """What changed between each pair of consecutive builds.

    Four numbers per step, and they are the ones a standup asks for: what got
    fixed, what regressed, what tests were added, and what quietly disappeared.
    A test vanishing from the suite is worth seeing - it is as often an
    accident as a decision.
    """
    steps = []

    for index in range(1, len(builds)):
        before = builds[index - 1]['tests']
        after = builds[index]['tests']

        fixed, regressed = [], []
        for key, test in after.items():
            was = before.get(key)
            if was is None: continue

            if was['outcome'] == 'fail' and test['outcome'] == 'pass': fixed.append(key)
            elif was['outcome'] == 'pass' and test['outcome'] == 'fail': regressed.append(key)

        steps.append({
            'label': builds[index]['label'],
            'fixed': fixed,
            'regressed': regressed,
            'added': [key for key in after if key not in before],
            'removed': [key for key in before if key not in after],
        })

    return steps


def duration_buckets(tracked):
    """Spread the current run's tests across the duration bands.

    Answers "where do the minutes go?" in a way a single slowest-tests list
    cannot: a suite of two thousand tests at 300ms each is a different
    problem from ten tests at a minute.
    """
    counts = [0] * len(DURATION_LABELS)
    measured = False

    for history in tracked.values():
        if not history['current']: continue

        duration = history['duration']
        if duration is None: continue

        measured = True
        for index, edge in enumerate(DURATION_EDGES):
            if duration < edge:
                counts[index] += 1
                break
        else:
            counts[-1] += 1

    return counts if measured else []


def failure_counts(build):
    """One build's failures, grouped by the exception each came out of.

    Keyed by suite and test the same way the histories are, so a group can be
    turned back into the tests in it.
    """
    groups = OrderedDict()

    for key, test in (build or {}).get('tests', {}).items():
        # ERROR sits with FAIL here, as it does everywhere else in the tab: a
        # test that blew up in a fixture failed for a reason worth grouping,
        # and the reason is in the same field. xFAIL does not - it is an
        # outcome the suite asked for, not one anybody is triaging.
        if test['outcome'] != 'fail': continue

        groups.setdefault(exception_type(test['message']) or OTHER, []).append(key)

    return groups


def failure_types(build, previous=None):
    """The failure groups of one build, ranked, with movement against the last.

    Biggest group first, ties broken by name so the order is stable between
    two runs that failed the same way. ``OTHER`` is held at the bottom however
    large it is: a list headed by "Unclassified: 40" is a list that has
    answered nothing.

    ``delta`` is ``None`` when there is no build to compare against - which is
    not the same as a group that has not moved, and is drawn differently.
    """
    groups = failure_counts(build)
    total = sum(len(keys) for keys in groups.values())
    if not total: return []

    before = {name: len(keys) for name, keys in failure_counts(previous).items()} if previous else None

    ranked = sorted(groups.items(), key=lambda group: (group[0] == OTHER, -len(group[1]), group[0]))

    return [{
        'name': name,
        'count': len(keys),
        'share': round(100.0 * len(keys) / total),
        'keys': keys,
        'delta': None if before is None else len(keys) - before.get(name, 0),
    } for name, keys in ranked]


def failure_headline(entries):
    """The one line the panel is worth reading for.

    "12 failures, 9 are TimeoutException" - the count on its own is already on
    the Dashboard, and it is the second half that says where to start.
    """
    total = sum(entry['count'] for entry in entries)
    if not total: return ''

    plural = 'failure' if total == 1 else 'failures'
    top = entries[0]

    # OTHER only ever ranks first by being the only group there is.
    if top['name'] == OTHER:
        return '%d %s, none of them naming an exception' % (total, plural)

    if top['count'] == total:
        if total == 1: return 'the one failure is a %s' % top['name']

        return 'all %d %s are %s' % (total, plural, top['name'])

    # Nothing groups with anything: naming the first of twelve one-offs would
    # read as a lead, and that a run failed twelve different ways is itself the
    # thing worth saying.
    if top['count'] == 1:
        return '%d %s, every one a different exception' % (total, plural)

    return '%d %s, %d are %s' % (total, plural, top['count'], top['name'])


def stability_score(tracked):
    """One number, 0-100, for how much the suite can be trusted.

    Two things make a suite untrustworthy and they are not the same thing:
    tests that fail, and tests that will not say. So the score starts at the
    mean per-test pass rate and is then charged half of the mean flip rate -
    a test alternating pass, fail, pass has a 50% pass rate *and* tells you
    nothing, and should not score the same as one that half the team knows is
    genuinely broken.
    """
    rated = [history for history in tracked.values() if history['pass_rate'] is not None]
    if not rated: return None

    mean_pass = sum(history['pass_rate'] for history in rated) / len(rated)
    mean_flip = sum(history['flip_rate'] for history in rated) / len(rated)

    return max(0, min(100, int(round(mean_pass - 50.0 * mean_flip))))


def score_grade(score):
    if score is None: return 'low'
    if score >= 80: return 'strong'
    if score >= 60: return 'fair'
    return 'low'


def _pass_rate(build):
    decided = build['counts']['pass'] + build['counts']['fail']
    if not decided: return None

    return round(100.0 * build['counts']['pass'] / decided, 1)


def _duration_text(seconds):
    if seconds is None: return '--'
    if seconds < 1: return '%dms' % round(seconds * 1000)
    if seconds < 60: return '%ss' % round(seconds, 1)

    minutes, rest = divmod(int(round(seconds)), 60)
    if minutes < 60: return '%dm %02ds' % (minutes, rest)

    # Past an hour the seconds are noise, and the reader of "608889402m 03s"
    # is left doing the division themselves.
    hours, minutes = divmod(minutes, 60)
    return '%dh %02dm' % (hours, minutes)


def _tile(value, label, note='', grade=''):
    return str(AnalyticsTile(value=escape_report_text(value),
                             label=escape_report_text(label),
                             note=escape_report_text(note),
                             grade=grade))


def _spark(states):
    """A test's recent outcomes as bare markup - one cell per build.

    Deliberately not a chart: there is one of these per row, and a few hundred
    Chart.js instances would make the tab slow to open for information that a
    row of coloured blocks carries perfectly well.

    The markup is kept short on purpose. A thousand-test suite over twelve
    builds is twelve thousand of these, and they are the single largest thing
    in the tab's markup - so the class names are scoped to `.spark i` rather
    than repeated in full on every block, and the strip is described once
    instead of every block carrying a tooltip that only says its own colour.
    """
    cells = ''.join('<i class="%s"></i>' % state for state in states)
    decided = [state for state in states if state != 'skip']

    summary = 'Last %d builds, oldest first: %d passed, %d failed' % (
        len(states), decided.count('pass'), decided.count('fail'))

    skipped = len(states) - len(decided)
    if skipped: summary += ', %d skipped' % skipped

    return '<span class="spark" role="img" aria-label="%s" title="%s">%s</span>' % (
        summary, summary, cells)


def _spark_order(states):
    """Sort value for the History column.

    The strip carries no text, so without this every row sorts equal and the
    header looks broken. What it is ordered on is what it draws: how the test
    has behaved over the last few builds - which is a different question from
    the Pass rate column, that one reads every build ever kept.

    Recent pass share leads; the number of builds drawn breaks ties, so a
    long clean strip outranks a single green block. A strip of nothing but
    skips has decided nothing and sorts below both.
    """
    decided = [state for state in states if state != 'skip']
    if not decided: return -1

    return round(1000.0 * decided.count('pass') / len(decided), 1) + len(states)


def _more_link(title, label, noun):
    """An "and N more" line, as the button that opens the rest of the list.

    The list it opens is the one already in the page: a card renders every
    name it has and hides the tail, and the overlay shows the same items with
    the hiding taken off. A second copy of the names in a data attribute would
    be the same bytes again, and two lists to keep in step.
    """
    return ('<button type="button" class="more-link" aria-haspopup="dialog"'
            ' data-title="%s" data-noun="%s" onclick="showMore(this)">%s</button>'
            % (escape_report_text(title), noun, escape_report_text(label)))


def _named(key, tracked):
    """One test as a two-line entry: what it is called, and where it lives."""
    history = tracked.get(key)

    return (history['name'] if history else key.rsplit('::', 1)[-1],
            history['suite'] if history else key.rsplit('::', 1)[0])


def _movement_card(icon, title, keys, tracked, tone):
    names = ''
    for position, key in enumerate(keys):
        name, suite = _named(key, tracked)

        # Everything past the first few is written into the card but not shown
        # in it: that tail is what the overlay opens, and a card listing forty
        # tests would push the three cards beside it off the screen.
        names += ('<li class="move__item%s"><span class="move__test">%s</span>'
                  '<span class="move__suite">%s</span></li>'
                  % (' is-extra' if position >= MOVEMENT_NAMES else '',
                     escape_report_text(name), escape_report_text(suite)))

    extra = len(keys) - MOVEMENT_NAMES
    if extra > 0:
        names += ('<li class="move__more">%s</li>'
                  % _more_link(title, 'and %d more' % extra, 'tests'))

    if not keys:
        names = '<li class="move__empty">Nothing</li>'

    return str(AnalyticsMove(icon=icon, title=escape_report_text(title),
                             count=str(len(keys)), tone=tone, items=names))


def _fault_tone(delta):
    """How a group's movement should read: worse, better, or neither."""
    if delta is None: return 'flat'
    if delta > 0: return 'up'
    if delta < 0: return 'down'

    return 'flat'


def _fault_delta(delta, count):
    """The movement in a group since the build before, as a person says it.

    A group that is new says so rather than showing "+3": the number on its own
    reads as three more of something that was already there, and a failure mode
    the last build did not have at all is the more interesting of the two.
    """
    if delta is None: return ''
    if delta == 0: return 'level'
    if delta == count: return 'new'

    return '%+d' % delta


def _fault_rows(entries, tracked):
    """The failure panel: one row per exception, with the tests under it.

    The tests are named rather than counted alone. "9 TimeoutException" says
    what broke; the names say whether it is one page object nine tests go
    through or nine unrelated waits, and those are different mornings.
    """
    content = ''

    for entry in entries[:FAULT_TYPES]:
        tests = ''
        for position, key in enumerate(entry['keys']):
            name, suite = _named(key, tracked)

            tests += ('<li class="fault__test%s" title="%s">%s</li>'
                      % (' is-extra' if position >= FAULT_NAMES else '',
                         escape_report_text('%s::%s' % (suite, name)), escape_report_text(name)))

        extra = entry['count'] - FAULT_NAMES
        if extra > 0:
            tests += ('<li class="fault__more">%s</li>'
                      % _more_link(entry['name'], 'and %d more' % extra, 'tests'))

        content += str(AnalyticsFault(
            name=escape_report_text(entry['name']),
            count=str(entry['count']),
            share=str(entry['share']),
            delta=escape_report_text(_fault_delta(entry['delta'], entry['count'])),
            tone=_fault_tone(entry['delta']),
            tests=tests,
        ))

    # Eight groups is already a long panel, and the tail of a list like this is
    # one-offs. They are counted rather than dropped: a run whose failures are
    # all different is itself the finding, and the whole tail is a click away.
    rest = entries[FAULT_TYPES:]
    if rest:
        failures = sum(entry['count'] for entry in rest)

        items = ''.join(
            '<li class="fault__rest-item is-extra"><span class="more__name">%s</span>'
            '<span class="more__meta">%d %s</span></li>'
            % (escape_report_text(entry['name']), entry['count'],
               'failure' if entry['count'] == 1 else 'failures')
            for entry in rest)

        content += ('<li class="fault__rest"><ul class="fault__rest-list">%s'
                    '<li class="fault__more">%s</li></ul></li>'
                    % (items, _more_link(
                        'More exception types',
                        'and %d more %s, %d %s between them'
                        % (len(rest), 'type' if len(rest) == 1 else 'types',
                           failures, 'failure' if failures == 1 else 'failures'),
                        'types')))

    return content


UNOWNED = 'Unowned'


def owner_totals(tracked):
    """One row per owner: how much of the suite they hold, and how it behaves.

    The question this answers is not "which test is worst" - the stability
    table above already answers that, test by test - but "whose morning is
    this". A run with forty failures spread evenly over six teams and a run
    with forty in one team read identically everywhere else on the page.

    A test with two owners counts once for each. That is the honest reading of
    two owner markers, and the alternative - picking one - would quietly take a
    team off the hook for a test they had put their name on.
    """
    totals = OrderedDict()

    for history in tracked.values():
        # Only what this run actually ran. A test deleted three builds ago is
        # nobody's morning, and leaving it in makes a team's numbers unfixable.
        if not history['current']: continue

        for owner in (history['owner'] or [UNOWNED]):
            row = totals.get(owner)
            if row is None:
                row = totals[owner] = {'owner': owner, 'tests': 0, 'failing': 0,
                                       'flaky': 0, 'broken': 0, 'rates': [],
                                       'duration': 0.0}

            row['tests'] += 1
            if history['outcome'] == 'fail': row['failing'] += 1
            if history['flaky']: row['flaky'] += 1
            if history['broken']: row['broken'] += 1
            if history['pass_rate'] is not None: row['rates'].append(history['pass_rate'])
            if history['duration']: row['duration'] += history['duration']

    for row in totals.values():
        # The mean of the tests' own rates rather than passes over runs. A team
        # holding one test that has run two hundred times and forty that ran
        # once should not have the two hundred decide their number.
        row['pass_rate'] = round(sum(row['rates']) / len(row['rates']), 1) if row['rates'] else None
        row['duration'] = round(row['duration'], 2)
        row['share'] = 0

    rows = sorted(totals.values(), key=_owner_rank)

    # The share bar is drawn against the busiest owner rather than against the
    # whole suite: with twelve teams every bar would be a stub, and the column
    # is there to compare teams with each other.
    widest = max((row['tests'] for row in rows), default=0)
    for row in rows:
        row['share'] = int(round(100.0 * row['tests'] / widest)) if widest else 0

    return rows


def _owner_rank(row):
    """Worst first, so the table opens on the team with the most to do.

    Unowned sorts last whatever its numbers, because it is not a team and
    reading it in among them invites somebody to go and find out who Unowned
    is. It is still drawn - unclaimed tests are a finding - just at the end.
    """
    return (row['owner'] == UNOWNED,
            -row['broken'], -row['failing'], -row['flaky'],
            row['pass_rate'] if row['pass_rate'] is not None else 101,
            row['owner'])


def _owner_headline(named, rows):
    """The sentence over the owner table, or '' when there is no table.

    Says the one thing the rows cannot: how much of the suite has no owner at
    all. A roll-up read as "these are the teams" is misleading while a third of
    the tests are not in it.
    """
    if not named: return ''

    unowned = sum(row['tests'] for row in rows if row['owner'] == UNOWNED)
    total = sum(row['tests'] for row in rows)

    text = '%d %s' % (len(named), 'owner' if len(named) == 1 else 'owners')

    if not unowned: return text + ', every test claimed'

    # The noun belongs to the total, not to the count in front of it:
    # "1 of 4 tests unclaimed", never "1 of 4 test".
    return '%s, and %d of %d %s unclaimed' % (text, unowned, total,
                                              'test' if total == 1 else 'tests')


def _owner_rows(rows):
    """The owner roll-up as table rows.

    Every owner, not a top few. Owners are teams and there are rarely more
    than a couple of dozen, and a team cut off the bottom of the list is a team
    that does not know it has work - which is the one thing this table exists
    to stop. The panel scrolls instead.
    """
    content = ''

    for row in rows:
        # A team with nothing wrong is not drawn in alarm colours, and a team
        # whose tests only ever fail is not drawn in the same tone as one with
        # a single flake.
        if row['broken']: tone = 'bad'
        elif row['failing'] or row['flaky']: tone = 'warn'
        else: tone = 'good'

        content += str(AnalyticsOwner(
            owner=escape_report_text(row['owner']),
            kind='unowned' if row['owner'] == UNOWNED else 'owner',
            tests=str(row['tests']),
            share=str(row['share']),
            rate='--' if row['pass_rate'] is None else '%s%%' % row['pass_rate'],
            failing=str(row['failing']),
            flaky=str(row['flaky']),
            broken=str(row['broken']),
            duration=escape_report_text(_duration_text(row['duration'])),
            tone=tone,
        ))

    return content


UNRATED = 'Unrated'


def severity_totals(tracked):
    """One row per severity level: how much of the suite sits at it, and how it behaves.

    The owner table answers "whose morning is this". This one answers the
    question asked before it: *does any of this matter today*. Forty failures
    at `trivial` and two at `blocker` are the same number everywhere else on
    the page and are not remotely the same run.

    A test counts once, unlike the owner roll-up: it has one severity by
    construction, because ``record_severity`` has already picked between the
    markers that claimed it.
    """
    totals = OrderedDict()

    for history in tracked.values():
        # This run's tests only, for the same reason the owner table takes
        # them: a test deleted three builds ago cannot be triaged.
        if not history['current']: continue

        level = history['severity'] or UNRATED
        row = totals.get(level)
        if row is None:
            row = totals[level] = {'severity': level, 'tests': 0, 'failing': 0,
                                   'flaky': 0, 'broken': 0, 'rates': [],
                                   'duration': 0.0}

        row['tests'] += 1
        if history['outcome'] == 'fail': row['failing'] += 1
        if history['flaky']: row['flaky'] += 1
        if history['broken']: row['broken'] += 1
        if history['pass_rate'] is not None: row['rates'].append(history['pass_rate'])
        if history['duration']: row['duration'] += history['duration']

    for row in totals.values():
        row['pass_rate'] = round(sum(row['rates']) / len(row['rates']), 1) if row['rates'] else None
        row['duration'] = round(row['duration'], 2)
        row['share'] = 0

    rows = sorted(totals.values(), key=_severity_row_rank)

    widest = max((row['tests'] for row in rows), default=0)
    for row in rows:
        row['share'] = int(round(100.0 * row['tests'] / widest)) if widest else 0

    return rows


def _severity_row_rank(row):
    """The ladder, worst first - and not the worst *numbers* first.

    The owner table sorts on behaviour because no team outranks another. These
    rows do outrank each other, and that order is the whole content of the
    column: a table that put `trivial` above `blocker` because trivial had more
    failures would be arguing with the words in it.

    Unrated sorts last however many tests are in it. It is not a level.
    """
    return (row['severity'] == UNRATED,
            severity_rank(row['severity']),
            row['severity'])


def _severity_headline(rows):
    """The sentence over the severity table, or '' when there is no table.

    It leads with the thing somebody came to the tab to find out - whether
    anything important is red - and falls back to how much of the suite has
    never been rated, which is what makes the rest of the table readable or
    not.
    """
    rated = [row for row in rows if row['severity'] != UNRATED]
    if not rated: return ''

    total = sum(row['tests'] for row in rows)
    unrated = sum(row['tests'] for row in rows if row['severity'] == UNRATED)

    # The worst level that has anything wrong in it, which is the one line
    # worth spending the headline on when there is one.
    hurt = next((row for row in rated if row['failing'] or row['broken']), None)
    if hurt:
        count = hurt['failing'] or hurt['broken']
        return '%d %s %s failing' % (count, hurt['severity'],
                                     'test' if count == 1 else 'tests')

    text = '%d %s in use' % (len(rated), 'level' if len(rated) == 1 else 'levels')

    if not unrated: return text + ', every test rated'

    return '%s, and %d of %d %s unrated' % (text, unrated, total,
                                            'test' if total == 1 else 'tests')


def _severity_rows(rows):
    """The severity roll-up as table rows.

    Drawn with the owner table's row, deliberately: the two answer neighbouring
    questions about the same run with the same six numbers, and giving them two
    layouts would make readers work out twice that the third column is a pass
    rate.
    """
    content = ''

    for row in rows:
        if row['broken']: tone = 'bad'
        elif row['failing'] or row['flaky']: tone = 'warn'
        else: tone = 'good'

        content += str(AnalyticsOwner(
            owner=escape_report_text(row['severity']),
            # The level is in the class so the chip can carry the ladder in its
            # colour. An unrecognised word gets no colour of its own and reads
            # as the plain chip it is, which is the honest look for a typo.
            kind=escape_report_text(
                'unowned' if row['severity'] == UNRATED
                else 'severity-%s' % row['severity']),
            tests=str(row['tests']),
            share=str(row['share']),
            rate='--' if row['pass_rate'] is None else '%s%%' % row['pass_rate'],
            failing=str(row['failing']),
            flaky=str(row['flaky']),
            broken=str(row['broken']),
            duration=escape_report_text(_duration_text(row['duration'])),
            tone=tone,
        ))

    return content


def _rank(history):
    """Sort key for the stability table: worst behaviour at the top.

    Consistently failing first, then flaky by how much it flips, then
    everything else by pass rate. The table is sortable, but what it shows
    before anyone touches it should already be the list to work through.
    """
    if history['broken']: return (0, -history['streak'], history['name'])
    if history['flaky']: return (1, -history['flip_rate'], -history['reruns'])

    return (2, history['pass_rate'] if history['pass_rate'] is not None else 101, history['name'])


def _rows(tracked):
    content = ''

    for history in sorted(tracked.values(), key=_rank):
        # "Unreliable" is a claim about a pattern, and a test that has failed
        # the only build it was in has not shown one yet - it has simply
        # failed. Saying more than the history supports is how a report
        # stops being believed.
        if history['broken']: verdict, tone = 'Always failing', 'broken'
        elif history['flaky']: verdict, tone = 'Flaky', 'flaky'
        elif history['pass_rate'] == 0: verdict, tone = 'Failing', 'broken'
        elif history['pass_rate'] == 100: verdict, tone = 'Stable', 'stable'
        elif history['pass_rate'] is None: verdict, tone = 'Skipped', 'muted'
        else: verdict, tone = 'Unreliable', 'flaky'

        if not history['current']:
            verdict, tone = 'Not in this run', 'muted'

        rate = '--' if history['pass_rate'] is None else '%s%%' % history['pass_rate']

        # A test that has only ever been skipped has decided nothing, and "0
        # builds" reads as a measurement rather than as the absence of one.
        if history['streak']:
            streak = '%d %s' % (history['streak'], 'build' if history['streak'] == 1 else 'builds')
        else:
            streak = '--'

        content += str(AnalyticsRow(
            sname=escape_report_text(history['suite']),
            name=escape_report_text(history['name']),
            verdict=verdict,
            tone=tone,
            runs=str(history['runs']),
            rate=rate,
            # Sorted on the number, shown as a percentage: DataTables would
            # otherwise order "9.1%" after "80%" as text.
            rate_sort=str(history['pass_rate'] if history['pass_rate'] is not None else -1),
            flips=str(history['flips']),
            reruns=str(history['reruns']),
            streak=streak,
            streak_sort=str(history['streak']),
            last_tone=history['outcome'],
            dur=_duration_text(history['duration']),
            dur_sort=str(history['duration'] if history['duration'] is not None else -1),
            spark=_spark(history['spark']),
            spark_sort=str(_spark_order(history['spark'])),
        ))

    return content


def generate_analytics(base):
    """Fill in everything the Analytics tab draws.

    Called once, after retention has pruned the archives, so the history read
    here is the history the report will actually ship with.
    """
    builds = read_builds(base)
    if not builds: return

    tracked = histories(builds)
    steps = movements(builds)
    current = builds[-1]

    flaky = [history for history in tracked.values() if history['flaky']]
    broken = [history for history in tracked.values() if history['broken']]
    score = stability_score(tracked)

    # --- headline tiles -----------------------------------------------------
    rate = _pass_rate(current)
    previous_rate = _pass_rate(builds[-2]) if len(builds) > 1 else None

    if rate is None or previous_rate is None: move = 'no earlier build to compare'
    elif round(rate - previous_rate, 1) == 0: move = 'level with the last build'
    else: move = '%+.1f pts since the last build' % (rate - previous_rate)

    timed = [build['duration'] for build in builds if build['duration'] is not None]
    # Durations are kept to two decimals, so a genuinely quick test measures
    # 0.0 - and ten rows of "slowest test: no time at all" reads as a chart
    # that failed to load rather than as a fast suite.
    slowest = sorted((history for history in tracked.values()
                      if history['current'] and history['duration']),
                     key=lambda history: history['duration'], reverse=True)

    tiles = _tile('--' if score is None else str(score), 'stability score',
                  'pass rate, less how often tests flip', score_grade(score))
    tiles += _tile('--' if rate is None else '%s%%' % rate, 'pass rate this run', move)
    tiles += _tile(str(len(flaky)), 'flaky tests', 'flipped or needed a retry')
    tiles += _tile(str(len(broken)), 'always failing',
                   'failing %d builds or more' % BROKEN_STREAK)
    tiles += _tile(str(len(builds)), 'builds analysed',
                   'oldest %s' % (builds[0]['label'] or 'unknown'))

    if timed: median = 'median build %s' % _duration_text(sorted(timed)[len(timed) // 2])
    else: median = 'not recorded in this run'

    tiles += _tile(_duration_text(current['duration']), 'time in tests', median)

    # --- charts -------------------------------------------------------------
    recent = builds[-TREND_BUILDS:]
    recent_steps = steps[-(len(recent) - 1):] if len(recent) > 1 else []

    ConfigVars._analytics_labels = js_literal([build['label'] for build in recent])
    ConfigVars._analytics_pass_rate = js_literal([_pass_rate(build) for build in recent])
    ConfigVars._analytics_growth = js_literal([build['total'] for build in recent])

    ConfigVars._analytics_flow_labels = js_literal([step['label'] for step in recent_steps])
    ConfigVars._analytics_flow_fixed = js_literal([len(step['fixed']) for step in recent_steps])
    ConfigVars._analytics_flow_regressed = js_literal([len(step['regressed']) for step in recent_steps])
    ConfigVars._analytics_flow_added = js_literal([len(step['added']) for step in recent_steps])
    ConfigVars._analytics_flow_removed = js_literal([len(step['removed']) for step in recent_steps])

    buckets = duration_buckets(tracked)
    ConfigVars._analytics_bucket_labels = js_literal(list(DURATION_LABELS) if buckets else [])
    ConfigVars._analytics_buckets = js_literal(buckets)

    # The one series carrying test names, and the only one that does not go
    # into a <script> block. A name is arbitrary text - a parametrized case can
    # be called anything at all - and js_literal would keep it from breaking
    # out, but the page has one escaping path that every other name already
    # travels, so this rides on an attribute and is parsed back rather than
    # being written as source code. Nothing a test is named ever lands
    # somewhere the browser is willing to execute.
    ConfigVars._analytics_slowest = escape_report_text(json.dumps(
        [[history['name'], history['duration']] for history in slowest[:TOP_SLOWEST]]))

    # --- panels -------------------------------------------------------------
    latest = steps[-1] if steps else {'fixed': [], 'regressed': [], 'added': [], 'removed': []}

    movement = _movement_card('fa-exclamation-triangle', 'Newly failing',
                              latest['regressed'], tracked, 'bad')
    movement += _movement_card('fa-check', 'Newly fixed', latest['fixed'], tracked, 'good')
    movement += _movement_card('fa-file-o', 'New tests', latest['added'], tracked, 'neutral')
    movement += _movement_card('fa-times', 'No longer run', latest['removed'], tracked, 'muted')

    # --- why this run failed --------------------------------------------
    # Read off the current build alone. Everything else on the tab needs a
    # history before it means anything; this is answerable on a first run, and
    # a first run that is red is exactly when somebody wants it.
    faults = failure_types(current, builds[-2] if len(builds) > 1 else None)

    ConfigVars._analytics_faults = _fault_rows(faults, tracked)
    ConfigVars._analytics_fault_note = failure_headline(faults)
    ConfigVars._analytics_fault_state = '' if faults else 'is-empty'

    # --- who owns what --------------------------------------------------
    # Empty for every suite that never wrote an owner marker, and the panel
    # goes with it: a table of one row called Unowned is a table saying
    # nothing at all.
    owners = owner_totals(tracked)
    named = [row for row in owners if row['owner'] != UNOWNED]

    ConfigVars._analytics_owners = _owner_rows(owners) if named else ''
    ConfigVars._analytics_owner_state = '' if named else 'is-empty'
    ConfigVars._analytics_owner_note = _owner_headline(named, owners)

    # --- how much any of it matters --------------------------------------
    # Empty, panel and all, for a suite that never rated a test: a table whose
    # only row is Unrated is a table saying nothing at all.
    severities = severity_totals(tracked)
    rated = [row for row in severities if row['severity'] != UNRATED]

    ConfigVars._analytics_severities = _severity_rows(severities) if rated else ''
    ConfigVars._analytics_severity_state = '' if rated else 'is-empty'
    ConfigVars._analytics_severity_note = _severity_headline(severities)

    ConfigVars._analytics_tiles = tiles
    ConfigVars._analytics_movement = movement
    ConfigVars._analytics_rows = _rows(tracked)
    ConfigVars._analytics_builds = str(len(builds))

    # One build is a perfectly ordinary first run, not an error - the tab
    # still has this run's durations to show, and says why the rest is blank
    # rather than drawing four empty axes.
    ConfigVars._analytics_state = '' if len(builds) > 1 else 'is-solo'
    ConfigVars._analytics_scope = (
        'across %d builds, %s to %s' % (len(builds), builds[0]['label'], current['label'])
        if len(builds) > 1 else 'this run only - history builds up as you run again'
    )
