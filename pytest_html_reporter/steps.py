"""Steps: the named, timed pieces a test is actually made of.

A test that fails tells you it failed. A test made of steps tells you *where*,
and how long it had been running when it got there - which is the question a
report is opened to answer and the one a status column cannot reach.

Steps are declared two ways, both spelled ``step``::

    @step("Log in as {user}")
    def login(user): ...

    with step("Add to cart", sku=sku):
        ...

and they nest, because the second one called from inside the first is a step of
it. Nothing has to be declared at all: every test already has a setup, a body
and a teardown, and those are timed and shown whether or not anyone reached for
this module.

The buffer lives on ConfigVars beside the screenshots and the attachments, is
drained by every finished test whatever the mode says, and holds nothing but
built-in types - an xdist worker has to pickle the whole record back to the
controller that writes the report.

Steps are recorded on the thread that ran the test. One opened in a worker
thread would nest itself under whatever the main thread happened to have open,
so it is left alone rather than guessed at; see ``_stack``.
"""

import functools
import threading
import time

from pytest_html_reporter.const_vars import ConfigVars


# What a step can be. Everything a user writes is a 'step'; the Gherkin kinds
# are what a pytest-bdd scenario contributes, and they are kept apart because
# "Given a logged in user" is a specification and "open the browser" is not.
KINDS = ('step', 'given', 'when', 'then', 'and', 'but')

# The phases a step can belong to, in the order they run.
PHASES = ('setup', 'call', 'teardown')

TITLE_MAX = 160
VALUE_MAX = 120
ERROR_MAX = 2000

# Past this depth a step is still timed and still run - it is only its
# indentation that stops growing. Nothing legible happens at column forty.
DEPTH_MAX = 12

# Two threads opening a step at the same moment would otherwise read the same
# length for the buffer and be given the same id, and an attachment filed under
# it would land on whichever of them lost the race.
_LOCK = threading.Lock()


def _text(value, limit):
    try:
        text = value if isinstance(value, str) else str(value)
    except Exception:
        text = '<unrepresentable>'

    return text[:limit - 1] + '…' if len(text) > limit else text


def _value(value):
    if isinstance(value, str): return _text(value, VALUE_MAX)

    try:
        return _text(repr(value), VALUE_MAX)
    except Exception:
        return '<unrepresentable>'


# ------------------------------------------------------------- the buffer ---

def _steps():
    """Steps recorded for the test currently running."""
    if not isinstance(getattr(ConfigVars, '_steps', None), list):
        ConfigVars._steps = []

    return ConfigVars._steps


def _local():
    """Per-thread step state: what is open, and where this phase started.

    Kept per thread. A test that fans work out to a pool would otherwise have
    every thread pushing onto one stack, and the steps would come back nested
    inside each other in whatever order the threads happened to interleave -
    a tree that never existed. Each thread nests within itself instead, and a
    background thread's steps land at the top level where they belong.
    """
    local = getattr(ConfigVars, '_step_local', None)
    if local is None:
        local = ConfigVars._step_local = threading.local()

    if getattr(local, 'stack', None) is None:
        local.stack = []
        local.floor = 0

    return local


def _stack():
    """The steps currently open, innermost last."""
    return _local().stack


def phase():
    return getattr(ConfigVars, '_step_phase', 'call') or 'call'


def set_phase(name):
    """Say which phase the steps opened from now on belong to.

    The open stack is marked at the same time. A ``yield`` fixture holds its
    ``with step(...)`` open across the whole test, so without this every step
    the test body ran would be reported as a step *of the fixture* - one
    ``Build a cart`` swallowing the test that used it. Nesting is counted from
    the phase's own floor instead, and the fixture's step still closes normally
    when the fixture resumes.
    """
    ConfigVars._step_phase = name if name in PHASES else 'call'

    local = _local()
    local.floor = len(local.stack)


def limit():
    value = getattr(ConfigVars, '_step_limit', 0)

    return value if isinstance(value, int) else 0


def take_steps():
    """Hand over this test's steps and empty the buffer.

    Drained by every record, whatever the test did and whatever the mode: a
    step nobody claims must not be left for the next test to pick up and
    present as its own - the bug screenshots had before every record started
    claiming the pending image.

    Anything still open is closed here. A ``with`` block that never exited
    means the test died inside it, and a step that just stops being mentioned
    reads as a step that never ran.
    """
    local = _local()

    for frame, started in reversed(local.stack):
        if frame is not None: _close(frame, started, 'FAIL', '')

    del local.stack[:]
    local.floor = 0
    local.raised = None

    steps = _steps()
    ConfigVars._steps = []
    ConfigVars._step_phase = 'call'

    return steps


# -------------------------------------------------------------- recording ---

def _close(frame, started, status, error):
    frame['ms'] = int(round((time.time() - started) * 1000))

    # A step that already failed keeps the failure it was reported with. The
    # exception walks out through every step it was raised inside, and each of
    # those is genuinely failed, but only the innermost one knows why.
    if frame['status'] != 'FAIL':
        frame['status'] = status
        frame['error'] = error


def start(title, params=(), kind='step'):
    """Open a step, and hand back the frame ``stop`` needs to close it.

    Returns None once a test has recorded more steps than the limit allows.
    The stack is pushed either way, so the steps still running keep nesting
    correctly around the ones that were dropped.
    """
    local = _local()
    stack = local.stack
    depth = min(max(len(stack) - local.floor, 0), DEPTH_MAX)

    with _LOCK:
        steps = _steps()
        frame = None

        if not (limit() and len(steps) >= limit()):
            frame = {
                'title': _text(title, TITLE_MAX) or 'step',
                'kind': kind if kind in KINDS else 'step',
                'phase': phase(),
                'depth': depth,
                'status': 'PASS',
                'ms': 0,
                'params': [[_text(name, VALUE_MAX), _value(value)] for name, value in params],
                'error': '',
                # Where an attachment made while this step was open will say it
                # belongs. The index is the step's own place in the buffer,
                # which is stable because nothing is ever removed from it.
                'id': len(steps),
            }
            steps.append(frame)

            # Said once, as a step of its own, rather than dropped in silence:
            # a tree that stops halfway reads as a test that stopped there.
            if limit() and len(steps) == limit():
                steps.append({
                    'title': 'more steps not recorded - raise --report-step-limit to keep them',
                    'kind': 'step', 'phase': phase(), 'depth': depth,
                    'status': 'SKIP', 'ms': 0, 'params': [], 'error': '', 'id': len(steps),
                })

    stack.append((frame, time.time()))

    return frame


def stop(status='PASS', error='', params=None):
    """Close the innermost open step, whatever happened inside it.

    The stack says which step that is, rather than the caller: a step is closed
    exactly where it was opened, and a caller holding the wrong frame could
    otherwise close somebody else's.
    """
    stack = _stack()
    if not stack: return

    opened, started = stack.pop()
    if opened is None: return

    # pytest-bdd only knows what a step was called with once it has run it, so
    # the parameters can arrive at the close rather than at the open.
    if params: opened['params'] = [[_text(n, VALUE_MAX), _value(v)] for n, v in params]

    _close(opened, started, status, _text(error, ERROR_MAX))


def open_step():
    """The innermost step still running, or None.

    What an attachment made mid-test is filed under. Read rather than passed,
    because ``attach_json`` is called by code that has no idea a report exists.
    """
    for frame, _started in reversed(_stack()):
        if frame is not None: return frame

    return None


def _outcome(exception):
    """How a step that raised should be reported.

    A ``pytest.skip()`` inside a step is not a failure of that step; it is the
    test saying it should not have run. Matched by name rather than by import
    so this module does not reach into pytest's internals for one class.
    """
    if type(exception).__name__ in ('Skipped', 'OutcomeException'): return 'SKIP'

    return 'FAIL'


def _error_text(exception):
    return '%s: %s' % (type(exception).__name__, exception) if str(exception) else type(exception).__name__


def _first_sighting(exception):
    """True unless this is the exception that just closed the step below.

    The same exception walking out through the steps it was raised inside is
    one failure, and printing it once - on the step that actually raised - is
    the whole point. Two steps that each raised their own ValueError('boom')
    are two failures, and both messages are worth keeping.

    The object itself is remembered rather than its ``id``: an exception that
    has been caught is collected, and CPython hands the same id straight back
    to the next one, so an id-keyed set silently swallowed the second of two
    identical-looking failures. One slot is enough because an exception only
    ever propagates through steps that are still open under it.
    """
    local = _local()

    if getattr(local, 'raised', None) is exception: return False

    local.raised = exception

    return True


# ------------------------------------------------------------- public API ---

class step(object):
    """Name and time a piece of a test, as a decorator or a ``with`` block.

    ::

        @step("Log in as {user}")
        def login(user): ...

        with step("Add to cart", sku="A-12"):
            cart.add(sku)

    A decorated function's own arguments fill in the ``{placeholders}`` of its
    title and are kept as the step's parameters, so the report shows the call
    that was actually made rather than the sentence it was written from.

    Steps nest by being called from inside one another; nothing has to be
    passed between them. A step that raises is recorded as failed, with the
    message, and the exception carries on out - a report that swallowed a
    failure to describe it would be worse than no report.
    """

    def __init__(self, title, **params):
        self.title = title
        self.params = params

    def __enter__(self):
        start(self.title, sorted(self.params.items()))

        return self

    def __exit__(self, kind, exception, traceback):
        if exception is None:
            stop()
        else:
            # The message goes on the step that raised, and the steps it was
            # raised inside are marked failed without it. One exception walking
            # out through four steps otherwise prints the same traceback four
            # times, and the innermost - the only one that says where - is the
            # one furthest down the page.
            stop(_outcome(exception),
                 _error_text(exception) if _first_sighting(exception) else '')

        return False

    def __call__(self, function):
        @functools.wraps(function)
        def wrapper(*args, **kwargs):
            bound = _bind(function, args, kwargs)

            with step(_fill(self.title, bound), **dict(self.params, **bound)):
                return function(*args, **kwargs)

        return wrapper


def _bind(function, args, kwargs):
    """A call's arguments by name, as far as they can be worked out.

    Never raises: a signature that will not bind - a decorator stacked in a way
    inspect cannot follow - costs the title its placeholders, not the test its
    run.
    """
    try:
        import inspect

        bound = inspect.signature(function).bind_partial(*args, **kwargs)
        bound.apply_defaults()

        return {name: value for name, value in bound.arguments.items()
                if name not in ('self', 'cls')}
    except Exception:
        return {}


def _fill(title, values):
    """``"Log in as {user}"`` with the call's own arguments written into it."""
    if '{' not in str(title): return title

    try:
        return str(title).format(**values)
    except Exception:
        # A title naming something the call did not pass keeps its braces
        # rather than costing the step its name.
        return title
