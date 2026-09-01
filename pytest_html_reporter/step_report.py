"""Building the Test Steps tab out of the records a run produced.

The tab is a drill-down, not a list: a suite, then a test in it, then what that
test did. Allure keeps the same information inside its suites view, and the
cost of that is a high-level page you cannot skim any more - so this is a page
of its own, and Test Suites stays a page of totals.

It is never empty and never useless. A suite that has not named a single step
still gets a tree: every test has a setup, a body and a teardown, each of them
timed, and every test carries its markers, its parameters, the fixtures it
named and its docstring. Naming steps makes that tree deeper - it does not
bring it into existence.

Everything is rendered here rather than in the page, for the same reason logs
and attachments are: what the browser receives is finished markup parked
outside the tables, out of the DataTables search index and out of every CSV,
Excel and print export.
"""

from collections import OrderedDict

from html_page.step_badge import StepBadge
from html_page.step_body import StepBody
from html_page.step_fact import StepFact
from html_page.step_line import StepLine
from html_page.step_phase import StepPhase
from html_page.step_scenario import StepScenario
from html_page.step_suite import StepSuite
from html_page.step_test import StepTest
from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.util import escape_report_text


# The phases every test has, in the order they run, as the tab names them.
# pytest's own words - setup, call, teardown - are what the record carries;
# these are what a person reading a report calls the same three things.
PHASES = OrderedDict((
    ('setup', 'Set up'),
    ('call', 'Test body'),
    ('teardown', 'Tear down'),
))

# The Gherkin words, which are shown as a badge in front of a step so a
# specification never reads as a piece of somebody's plumbing.
GHERKIN = ('given', 'when', 'then', 'and', 'but')

# A suite path repeats down the whole rail; only its tail tells one from the next.
SUITE_TAIL_MAX = 34


def duration(ms):
    """A step's time in the unit that keeps it to three or four digits."""
    try:
        ms = float(ms)
    except (TypeError, ValueError):
        return ''

    if ms < 1: return '0 ms'

    return '%.2f s' % (ms / 1000.0) if ms >= 1000 else '%d ms' % round(ms)


def _test_ms(record):
    """How long a test took, in milliseconds.

    The record's own duration is kept in seconds rounded to two places, for a
    column that has always been headed "Time (s)" - so every test faster than
    5ms reaches this tab as a flat 0. The phase timings are whole milliseconds
    taken from pytest's own report, and they add up to the same test.
    """
    phases = record.get('phases') or {}
    measured = sum(int(phases.get(phase) or 0) for phase in PHASES)

    return max(measured, int(round((record.get('duration') or 0) * 1000)))


def _short(path):
    """The end of a suite path, which is the half that names it."""
    path = str(path)

    return path if len(path) <= SUITE_TAIL_MAX else '…' + path[-(SUITE_TAIL_MAX - 1):]


def _pluralise(count, noun):
    return '%d %s' % (count, noun if count == 1 else noun + 's')


def _widths(steps):
    """How wide each step's duration bar is drawn, as a percentage.

    Measured against the slowest step of *this test* rather than of the run: a
    tab that scaled every bar to the slowest step anywhere would draw a flat
    line for every test but one, and the question being asked here is always
    "which part of this test was slow", never "which test was slow".
    """
    longest = max([int(step.get('ms') or 0) for step in steps] or [0])
    if longest <= 0: return [0] * len(steps)

    return [int(round(int(step.get('ms') or 0) * 100.0 / longest)) for step in steps]


def _kind_badge(step):
    """The Given/When/Then badge, and nothing at all for an ordinary step.

    A Gherkin keyword is part of what the step *says*; a plain step's title is
    the whole of it, and prefixing every one of those with the word "step"
    would be noise on every line of the tree.
    """
    kind = str(step.get('kind') or 'step')
    if kind not in GHERKIN: return ''

    return str(StepBadge(kind='gherkin', text=escape_report_text(kind.title()),
                         title='Gherkin ' + escape_report_text(kind)))


def _params_text(params):
    """A step's parameters as the call that was actually made."""
    if not params: return ''

    return ', '.join('%s=%s' % (name, value) for name, value in params)


def _attach_chip(step, attachments):
    """How many payloads were attached while this step was open."""
    count = sum(1 for item in attachments if item.get('step') == step.get('id'))
    if not count: return ''

    return ('<span class="step-line__attach" title="%s attached here">'
            '<i class="fa fa-paperclip" aria-hidden="true"></i>%d</span>'
            % (_pluralise(count, 'attachment'), count))


def _line(step, width, attachments):
    params = _params_text(step.get('params') or [])
    error = step.get('error') or ''

    return str(StepLine(
        stat=escape_report_text(step.get('status') or 'PASS'),
        depth=str(int(step.get('depth') or 0)),
        kind=_kind_badge(step),
        title=escape_report_text(step.get('title') or ''),
        params=('<span class="step-line__params" title="%s">%s</span>'
                % (escape_report_text(params), escape_report_text(params))) if params else '',
        attach=_attach_chip(step, attachments),
        width=str(width),
        ms=escape_report_text(duration(step.get('ms'))),
        error=('<pre class="step-line__error">%s</pre>' % escape_report_text(error)) if error else '',
    ))


def _phases(record):
    """The three phase blocks of one test, with its steps filed under them.

    A phase with no steps of its own is still drawn: its duration is the answer
    to "where did the time go" for a test whose setup is the slow part, and
    that is exactly the test least likely to have named any steps.
    """
    steps = record.get('steps') or []
    attachments = record.get('attachments') or []
    timings = record.get('phases') or {}
    widths = dict(zip(range(len(steps)), _widths(steps)))

    blocks = ''
    for phase, label in PHASES.items():
        owned = [(index, step) for index, step in enumerate(steps)
                 if (step.get('phase') or 'call') == phase]

        lines = ''.join(_line(step, widths.get(index, 0), attachments) for index, step in owned)

        blocks += str(StepPhase(
            phase=phase,
            label=label,
            ms=escape_report_text(duration(timings.get(phase, 0))),
            lines=lines,
            state='filled' if owned else 'bare',
            none='' if owned else 'No steps named here',
        ))

    return blocks


def _facts(record):
    """What the test says about itself, as a row of labelled facts."""
    meta = record.get('meta') or {}
    facts = ''

    # A pytest-bdd test function is generated, and so is its docstring - the
    # absolute path of the feature file and the scenario's unrendered name.
    # The scenario strip above says both, properly.
    doc = '' if record.get('bdd') else (meta.get('doc') or '')
    if doc:
        facts += str(StepFact(label='Description', value=escape_report_text(doc)))

    markers = meta.get('markers') or []
    if markers:
        badges = ''.join(
            str(StepBadge(kind=escape_report_text(marker.get('kind') or 'user'),
                          text=escape_report_text(marker.get('text') or marker.get('name') or ''),
                          # Where it was written, which is the answer when
                          # nobody remembers applying it.
                          title='%s marker, from the %s'
                                % (escape_report_text(marker.get('kind') or 'user'),
                                   escape_report_text(marker.get('scope') or 'test'))))
            for marker in markers)
        facts += str(StepFact(label=_pluralise(len(markers), 'marker'), value=badges))

    params = meta.get('params') or []
    if params:
        badges = ''.join(
            str(StepBadge(kind='param',
                          text=escape_report_text('%s = %s' % (name, value)),
                          title=escape_report_text('%s = %s' % (name, value))))
            for name, value in params)
        facts += str(StepFact(label=_pluralise(len(params), 'parameter'), value=badges))

    fixtures = meta.get('fixtures') or []
    if fixtures:
        badges = ''.join(
            str(StepBadge(kind='fixture', text=escape_report_text(name),
                          title=escape_report_text(name)))
            for name in fixtures)
        facts += str(StepFact(label=_pluralise(len(fixtures), 'fixture'), value=badges))

    return facts


def _scenario(record):
    """The feature and scenario a BDD test came from, when it came from one."""
    bdd = record.get('bdd') or {}
    if not bdd: return ''

    return str(StepScenario(
        feature=escape_report_text(bdd.get('feature') or ''),
        scenario=escape_report_text(bdd.get('scenario') or ''),
        file=escape_report_text(bdd.get('file') or ''),
    ))


def _note(record):
    """The one line under a test's name in the rail."""
    steps = record.get('steps') or []
    bdd = record.get('bdd') or {}

    if bdd: return bdd.get('scenario') or 'scenario'
    if steps: return _pluralise(len(steps), 'step')

    return 'no steps named'


def _search_text(record):
    """What the rail's search box matches a test on.

    The suite, the test, every step title, every marker and the scenario - so
    a marker name, a Gherkin line or a feature finds the test - but not the
    parameters or the errors, which are already several thousand characters
    across a run and would double the size of the file for nothing.
    """
    meta = record.get('meta') or {}
    bdd = record.get('bdd') or {}

    terms = [record.get('suite_name'), record.get('test_name'), record.get('status')]
    terms += [step.get('title') for step in (record.get('steps') or [])]
    terms += [marker.get('text') for marker in (meta.get('markers') or [])]
    terms += [bdd.get('feature'), bdd.get('scenario')]

    return ' '.join(str(term) for term in terms if term).lower()


def generate_steps_view(suites):
    """Fill the Test Steps tab from the records, grouped as the report groups them.

    `suites` is an ordered mapping of suite name to its records, which is what
    build_report has already worked out - re-deriving it here would risk the
    two disagreeing about which test sits where, and the rail's ids have to
    match the table's rows for the Steps column to be able to cross to them.
    """
    rail = ''
    store = ''
    total_steps = 0
    named = 0

    for suite_index, suite_name in enumerate(suites):
        records = suites[suite_name]
        entries = ''

        for row_id, record in enumerate(records):
            sid = '%s-%s' % (suite_index, row_id)
            steps = record.get('steps') or []

            total_steps += len(steps)
            if steps: named += 1

            entries += str(StepTest(
                sid=sid,
                stat=escape_report_text(record.get('status') or ''),
                kind='bdd' if record.get('bdd') else 'plain',
                name=escape_report_text(record.get('test_name') or ''),
                note=escape_report_text(_note(record)),
                dur=escape_report_text(duration(_test_ms(record))),
                search=escape_report_text(_search_text(record)),
            ))

            store += str(StepBody(
                sid=sid,
                runt=sid,
                sname=escape_report_text(record.get('suite_name') or ''),
                name=escape_report_text(record.get('test_name') or ''),
                stat=escape_report_text(record.get('status') or ''),
                dur=escape_report_text(duration(_test_ms(record))),
                rerun=str(record.get('rerun') or 0),
                scenario=_scenario(record),
                meta=_facts(record),
                phases=_phases(record),
            ))

        rail += str(StepSuite(
            sname=escape_report_text(suite_name),
            short=escape_report_text(_short(suite_name)),
            count=str(len(records)),
            tests=entries,
        ))

    ConfigVars._step_tree = rail
    ConfigVars._step_store = store
    # Whether anyone named a step. The tab still works either way - it is the
    # teaching panel under it that is only worth showing while nobody has.
    ConfigVars._step_state = '' if total_steps else 'is-bare'
    ConfigVars._step_named = str(named)
    ConfigVars._step_total = str(total_steps)
