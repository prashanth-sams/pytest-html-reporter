"""Turning a pytest-bdd scenario into the steps the report already knows.

A Gherkin scenario *is* a list of steps - it is the one style of test that
arrives already broken into named pieces - so a suite written this way fills
the Test Steps tab without anyone reaching for ``step()`` at all.

Nothing here imports pytest_bdd. The hooks are declared ``optionalhook`` on the
reporter, which is the whole of the defence: pytest refuses to start at all -
``PluginValidationError: unknown hook 'pytest_bdd_after_step'`` - when a plugin
implements a hook nobody registered, and pytest-bdd is not a dependency of this
one. Every object handed to those hooks is then read by ``getattr``, because
the attributes moved between pytest-bdd 4 and 8 and this plugin pins neither.

Only pytest-bdd is covered. behave does not run under pytest, so there is no
hook to implement and nothing that could be shown.
"""

from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.steps import KINDS, start, stop


def _read(source, *names):
    """The first of `names` the object will part with, as text.

    pytest-bdd renamed several of these across its major versions, and a step
    missing its keyword is worth far more than a run that stops because of one.
    """
    for name in names:
        try:
            value = getattr(source, name, None)
        except Exception:
            continue

        if value is not None: return value

    return None


def _text(source, *names):
    value = _read(source, *names)

    return '' if value is None else str(value)


def _kind(step):
    """Which Gherkin word this is, for the badge in front of it.

    ``keyword`` is what was written - And, But - while ``type`` is what pytest
    resolved it to. The written word is the one worth showing, and it falls
    back to the resolved one for a dialect that spells it differently.
    """
    keyword = _text(step, 'keyword').strip().lower()
    if keyword in KINDS: return keyword

    resolved = _text(step, 'type').strip().lower()

    return resolved if resolved in KINDS else 'step'


def _title(step):
    """The step as the feature file wrote it, keyword and all.

    A Scenario Outline's placeholders are already filled in by the time this
    runs, so ``When I add <count> items`` arrives as ``When I add 2 items`` -
    the row that actually ran, which is the one worth reporting.
    """
    keyword = _text(step, 'keyword').strip()
    name = _text(step, 'name')

    return ('%s %s' % (keyword, name)).strip() if keyword else name


def _params(step_func_args):
    """What the step was called with, minus the fixtures it was handed.

    A step's own parsed arguments - the ``{count:d}`` of its parser - are worth
    showing. The fixtures pytest-bdd injects alongside them are the plumbing
    that made the call possible, and there is one for every ``target_fixture``
    the scenario has built up by then: ``Then the cart shows 2 items`` was
    arriving with the whole cart printed beside it.

    They are told apart by shape rather than by asking pytest-bdd, whose way of
    saying which is which has changed more than once. A Gherkin parser only
    ever yields scalars - it is parsing a line of text - so anything richer
    than one came from the fixture machinery.
    """
    if not isinstance(step_func_args, dict): return []

    return sorted((name, value) for name, value in step_func_args.items()
                  if not str(name).startswith('_')
                  and isinstance(value, (str, int, float, bool, type(None))))


def before_step(step):
    """Open a step for the Given/When/Then about to run."""
    start(_title(step), kind=_kind(step))


def after_step(step_func_args):
    """Close the step that just passed, with what it was called with."""
    stop(params=_params(step_func_args))


def step_error(exception, step_func_args=None):
    """Close the step that just raised, with why.

    pytest-bdd calls this *and then* lets the exception out, so ``after_step``
    never runs for a failed step and this is the only close it gets.
    """
    stop('FAIL', '%s: %s' % (type(exception).__name__, exception),
         params=_params(step_func_args))


def lookup_error(step, exception):
    """Record a step the feature file names and the suite never implemented.

    No step function was found, so nothing opened this one - it is opened and
    closed here, so the tab names the unimplemented line rather than simply
    stopping short of it.
    """
    start(_title(step), kind=_kind(step))
    step_error(exception)


def before_scenario(feature, scenario):
    """Remember the scenario a BDD test came from, for its record.

    A pytest-bdd test function is generated, so its name and its module say far
    less about it than the feature file does. Stored on ConfigVars beside the
    other per-test state and claimed by the record the same way.
    """
    ConfigVars._bdd = {
        'feature': _text(feature, 'name'),
        'scenario': _text(scenario, 'name'),
        # rel_filename is the path as the run saw it; older versions only had
        # the absolute one, which says nothing useful in a published report.
        'file': _text(feature, 'rel_filename', 'filename'),
        # Tags live on the feature as often as on the scenario, and pytest-bdd
        # applies both to the test as markers - so the report shows them in
        # both places, as tags here and as markers there.
        'tags': sorted(set(_read(scenario, 'tags') or []) | set(_read(feature, 'tags') or [])),
    }


def take_scenario():
    """Hand over the scenario this test came from, and forget it.

    Drained like every other per-test buffer: a scenario left behind would be
    claimed by the next test to finish, and a plain pytest test would be
    reported as a piece of somebody's feature file.
    """
    scenario = getattr(ConfigVars, '_bdd', None)
    ConfigVars._bdd = None

    return scenario
