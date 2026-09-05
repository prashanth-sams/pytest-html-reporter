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
from html_page.step_link import StepLink
from html_page.step_phase import StepPhase
from html_page.step_scenario import StepScenario
from html_page.step_suite import StepSuite
from html_page.step_test import StepTest
from html_page.test_shot import TestShot
from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.markers import SEVERITY_MARKER_KIND, severity_value
from pytest_html_reporter.util import (
    escape_report_text,
    marker_url,
    record_owners,
    record_severity,
)


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

# How a test's owners are packed into one attribute for the rail to filter on.
# A pipe rather than a comma: a team is called "Payments, EU" often enough to
# matter and is called "Payments|EU" essentially never.
OWNER_SEPARATOR = '|'

# The badge kind an overridden severity is drawn as. It is still shown - the
# tab promises every marker, and "the module said normal" is the sentence that
# explains why a test nobody touched changed colour - but it is drawn as spent
# rather than as a second severity the test somehow also has.
SEVERITY_PAST_KIND = 'severity-past'

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
    """The file name of a suite, which is the half that names it.

    The directories repeat down the whole rail and were crowding out the part
    that differs - and truncating the path instead put an ellipsis at the front
    while the rail's own overflow put another at the back, so a long one was
    clipped at both ends and said nothing. The full path is on the row's title
    and across the top of the pane beside it.
    """
    return str(path).replace('\\', '/').split('/')[-1] or str(path)


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


def _threw(steps):
    """The step a failure came out of, or None.

    A raised exception walks out through every step it was inside and each of
    those is marked failed, but only the innermost one is given the text - so
    the one carrying a message is the one that actually threw. The last of
    them, if a test managed to fail twice; failing deeper beats failing later,
    which is why the message is what this reads rather than the status.
    """
    threw = [index for index, step in enumerate(steps) if (step.get('error') or '').strip()]
    if threw: return threw[-1]

    failed = [index for index, step in enumerate(steps)
              if str(step.get('status') or '').upper() in ('FAIL', 'ERROR')]

    return failed[-1] if failed else None


def _shots_by_step(record):
    """This test's screenshots, filed under the step each one belongs to.

    Two ways a picture gets here. One was taken while a step was open - by a
    test calling ``attach`` inside it - and says so itself. The other is the
    automatic capture, which runs from the teardown hook with nothing open at
    all: those are filed against the step that threw, because a photograph of
    the browser at the end of a failing test is a photograph of the state that
    step left behind, and looking for it anywhere else is the whole complaint.

    What is left over - a picture from a test that passed, or one from a test
    whose failure named no step - goes to the phase, under `None`.
    """
    steps = record.get('steps') or []
    threw = _threw(steps) if str(record.get('status') or '').upper() in ('FAIL', 'ERROR') else None

    filed = {}
    for shot in record.get('screenshots') or []:
        try:
            index = int(shot.get('step', -1))
        except (TypeError, ValueError):
            index = -1

        if not 0 <= index < len(steps):
            index = threw if threw is not None else None

        filed.setdefault(index, []).append(shot)

    return filed


def _shot_strip(shots, record):
    """The thumbnails themselves, in the same gallery the tab opens them in."""
    if not shots: return ''

    thumbs = ''.join(
        str(TestShot(
            screen_name=escape_report_text(shot.get('name') or ''),
            ts=escape_report_text(shot.get('suite') or ''),
            tc=escape_report_text(shot.get('test') or record.get('test_name') or ''),
            # A gallery of its own: the tab shows one test at a time, so
            # arrowing across should stay inside the test being read rather
            # than travel the whole run the way the table's strip does.
            group='steps',
            tip=escape_report_text('Screenshot taken here'),
        ))
        for shot in shots)

    return '<div class="step-shots">%s</div>' % thumbs


def _line(step, width, attachments, shots, record):
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
        shots=_shot_strip(shots, record),
    ))


def _tree_order(owned):
    """One phase's steps in the order the tree reads, rather than the order
    they started.

    The two are the same thing until something runs concurrently. Steps are
    buffered as they open, so three gathered coroutines - or three threads -
    put all three siblings in before any of their children, and a list read
    straight down indents every one of those children under the *last* sibling.
    Same depths, same durations, wrong parents.

    A step whose parent is not in this phase is a root here: one held open by a
    fixture across a whole test belongs to Set up, and the test body it spans
    is not a step of it.

    Walked with an explicit stack. Recursion would be the obvious way to write
    it and a suite whose steps nest a thousand deep would take the run down
    with it - the depth a step is *drawn* at is capped, the depth it is allowed
    to reach is not.
    """
    present = set(step.get('id') for _index, step in owned if step.get('id') is not None)
    roots, children = [], {}

    for entry in owned:
        step = entry[1]
        parent = step.get('parent')

        if parent is not None and parent in present and parent != step.get('id'):
            children.setdefault(parent, []).append(entry)
        else:
            roots.append(entry)

    ordered, seen = [], set()
    pending = list(reversed(roots))

    while pending:
        index, step = pending.pop()
        if index in seen: continue

        seen.add(index)
        ordered.append((index, step))
        pending.extend(reversed(children.get(step.get('id'), ())))

    # Nothing is dropped. A record is read back off a bundle written by another
    # process and another version, and a step missing from the tab altogether
    # is a worse answer than one drawn at the wrong indent.
    if len(ordered) != len(owned):
        ordered += [entry for entry in owned if entry[0] not in seen]

    return ordered


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
    shots = _shots_by_step(record)

    # A picture belonging to no step is shown against the test body: a test
    # with no named steps is the ordinary case, and the body is where it ran.
    loose = shots.get(None) or []

    blocks = ''
    for phase, label in PHASES.items():
        owned = _tree_order([(index, step) for index, step in enumerate(steps)
                             if (step.get('phase') or 'call') == phase])

        lines = ''.join(_line(step, widths.get(index, 0), attachments,
                              shots.get(index) or [], record)
                        for index, step in owned)

        blocks += str(StepPhase(
            phase=phase,
            label=label,
            ms=escape_report_text(duration(timings.get(phase, 0))),
            lines=lines,
            state='filled' if owned else 'bare',
            none='' if owned else 'No steps named here',
            shots=_shot_strip(loose if phase == 'call' else [], record),
        ))

    return blocks


def _label(name):
    """A marker name as the label of the row its ids sit in: `jira` -> `Jira`."""
    text = str(name or '').replace('_', ' ').replace('-', ' ').strip()

    return text[:1].upper() + text[1:]


def _badge(marker, bare=False):
    """One marker, linked when a pattern says where it points.

    `bare` drops the marker's name from the badge and shows its argument alone.
    It is set for the badges that sit under a label already naming the marker -
    the Jira row, the Owner row - where `jira(PROJ-123)` would say `jira` twice
    and `PROJ-123` says it once.
    """
    kind = marker.get('kind') or 'user'
    scope = marker.get('scope') or 'test'
    args = marker.get('args') or []

    text = str(args[0]) if (bare and args) else (marker.get('text') or marker.get('name') or '')
    url = marker_url(ConfigVars._link_patterns, marker)

    if not url:
        return str(StepBadge(kind=escape_report_text(kind),
                             text=escape_report_text(text),
                             # Where it was written, which is the answer when
                             # nobody remembers applying it.
                             title='%s marker, from the %s'
                                   % (escape_report_text(kind), escape_report_text(scope))))

    # The url is the title rather than the scope: this one opens something, and
    # what it is about to open is the thing worth seeing before clicking it.
    return str(StepLink(kind=escape_report_text(kind),
                        text=escape_report_text(text),
                        url=escape_report_text(url),
                        title=escape_report_text(url)))


def _traced(markers):
    """(linked markers grouped by their marker name, everything else).

    Grouped rather than left in the markers row because a bare `PROJ-123` says
    nothing about which system it is an id in, and the group's own label is the
    cheapest place on the page to say it. A test that closes two tickets has
    two entries under one label, in the order they were written.
    """
    groups = OrderedDict()
    rest = []

    for marker in markers:
        if marker_url(ConfigVars._link_patterns, marker):
            groups.setdefault(str(marker.get('name') or ''), []).append(marker)
        else:
            rest.append(marker)

    return groups, rest


def _severity_badges(markers, effective):
    """The severity row: the level that applies, then the ones it overrode.

    Nothing is hidden and nothing is drawn twice as loud as it is. A test
    inside a module marked `normal` and a class marked `critical` carries both
    markers and always did; what the row has to say is which of them the run
    was actually rated at, and each badge's tooltip says where its word was
    written - the answer when a level nobody typed on this test is the one
    deciding its colour.
    """
    badges = ''
    won = False

    for marker in markers:
        level = severity_value(marker)
        scope = str(marker.get('scope') or 'test')

        # The first marker at the effective level is the one that carried it;
        # a second copy of the same word further out was still overridden.
        current = level == effective and not won
        won = won or current

        badges += str(StepBadge(
            kind=escape_report_text('severity-%s' % level if current else SEVERITY_PAST_KIND),
            text=escape_report_text(level),
            title=escape_report_text(
                '%s, from the %s' % (level, scope) if current
                else '%s, from the %s - overridden by %s' % (level, scope, effective)),
        ))

    return badges


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

    # Who to tell, first and on its own. It is the one fact here that is about
    # a person rather than about the test, and it is what somebody reading a
    # red run is looking for - so it does not go in a row of eight badges where
    # `smoke` and `slow` are the ones catching the eye.
    owners = [marker for marker in markers if marker.get('kind') == 'owner']
    if owners:
        facts += str(StepFact(label=_pluralise(len(owners), 'owner'),
                              value=''.join(_badge(marker, bare=True) for marker in owners)))

    # How bad, next: it is the other question a red run is read with, and the
    # only marker on the page whose *value* is ranked rather than merely named.
    severities = [marker for marker in markers if marker.get('kind') == SEVERITY_MARKER_KIND]
    if severities:
        facts += str(StepFact(label='Severity',
                              value=_severity_badges(severities, record_severity(record))))

    linked, plain = _traced([marker for marker in markers
                             if marker.get('kind') not in ('owner', SEVERITY_MARKER_KIND)])

    for name, group in linked.items():
        facts += str(StepFact(label=escape_report_text(_label(name)),
                              value=''.join(_badge(marker, bare=True) for marker in group)))

    if plain:
        facts += str(StepFact(label=_pluralise(len(plain), 'marker'),
                              value=''.join(_badge(marker) for marker in plain)))

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

    text = ' '.join(str(term) for term in terms if term).lower()

    # A test is named test_a_declined_card, and what somebody types is "declined
    # card". Both spellings are indexed rather than asking people to guess which
    # one the box wants.
    spaced = text.replace('_', ' ')

    return text if spaced == text else text + ' ' + spaced


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
                owner=escape_report_text(OWNER_SEPARATOR.join(record_owners(record))),
                sev=escape_report_text(record_severity(record)),
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
            sindex=str(suite_index),
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
