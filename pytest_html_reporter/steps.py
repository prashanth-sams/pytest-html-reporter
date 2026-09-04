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

Steps are recorded against whoever ran them - a thread, or an asyncio task -
so that work fanned out concurrently comes back as the siblings it was rather
than nested inside whichever sibling happened to start first; see ``_state``.

An ``async`` test spells a step the same two ways, with ``await`` in front of
what it is timing::

    @step("Send the notification")
    async def notify(user): ...

    async with step("Check out"):
        await cart.pay()
"""

import contextvars
import functools
import inspect
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


# What is open, and where the current phase started, for whoever is running:
# a thread, or an asyncio task. Held in a ContextVar rather than a
# threading.local because asyncio runs every task on the one thread - three
# gathered coroutines pushing onto a per-thread stack come back nested three
# deep inside one another, a tree that never existed, and an attachment made
# in one of them is filed under whichever sibling happened to be open.
#
# The value is a tuple, and it is replaced rather than edited. A task starts
# from a copy of the context that created it, so a mutable stack would be the
# *same* list in every one of them and we would be back to sharing one;
# replacing the tuple keeps a task's steps to itself while still letting them
# nest under whatever was already open when it was started.
_STATE = contextvars.ContextVar('pytest_html_reporter.steps')

# (epoch, stack, floor, raised), where the stack holds (frame, started) pairs.
_EMPTY = (0, (), 0, None)


def _epoch():
    """Which test the state found in a context belongs to."""
    value = getattr(ConfigVars, '_step_epoch', 0)

    return value if isinstance(value, int) else 0


def _state():
    """This context's step state, dropped if it outlived the test that made it.

    A context can outlast the test that used it - a pooled worker thread's
    does, since the thread is handed to the next test still holding whatever
    it was left with. Its stack names steps that have already been taken and
    rendered, so counting depth from it would indent the next test's first
    step underneath somebody else's. The epoch is stamped on write and checked
    here, and a stale stack is dropped rather than carried forward.
    """
    state = _STATE.get(_EMPTY)

    return state if state[0] == _epoch() else _EMPTY


def _store(stack, floor, raised):
    _STATE.set((_epoch(), stack, floor, raised))


def _stack():
    """The steps currently open, innermost last."""
    return _state()[1]


def _open_frames():
    """Every step open anywhere, in the order they were opened.

    ``take_steps`` closes what is left in here, and cannot go by the stacks: a
    step opened inside a task that was cancelled, or on a thread that has since
    ended, is open in a context nothing can reach any more - and a step that
    just stops being mentioned reads as a step that never ran.

    Keyed by ``id`` because a frame is a dict and dicts do not hash. Nothing is
    registered that the buffer is not also holding, so no id is handed to
    something else while it is still in here.
    """
    if not isinstance(getattr(ConfigVars, '_step_open', None), dict):
        ConfigVars._step_open = {}

    return ConfigVars._step_open


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

    epoch, stack, floor, raised = _state()
    _store(stack, len(stack), raised)


def limit():
    value = getattr(ConfigVars, '_step_limit', 0)

    return value if isinstance(value, int) else 0


def take_steps():
    """Hand over this test's steps and empty the buffer.

    Drained by every record, whatever the test did and whatever the mode: a
    step nobody claims must not be left for the next test to pick up and
    present as its own - the bug screenshots had before every record started
    claiming the pending image.

    Anything still open is closed here, wherever it was opened. A ``with``
    block that never exited means the test died inside it - or that a task
    holding one was cancelled - and a step that just stops being mentioned
    reads as a step that never ran.
    """
    with _LOCK:
        pending = list(_open_frames().values())
        _open_frames().clear()

    for frame, started in reversed(pending):
        _close(frame, started, 'FAIL', '')

    # Every stack still holding any of these is stale from here on: this
    # context's, and any a pooled thread or a finished task is sitting on.
    ConfigVars._step_epoch = _epoch() + 1

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
    epoch, stack, floor, raised = _state()
    depth = min(max(len(stack) - floor, 0), DEPTH_MAX)
    started = time.time()
    parent = _parent(stack[floor:])

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
                # The step this one is a step *of*. Depth alone says how far to
                # indent, which is the same answer for two steps of different
                # parents - and steps are buffered in the order they started,
                # so concurrent work puts every sibling before any of their
                # children and the reader is left attributing all of them to
                # the last sibling. Rendering walks this instead.
                'parent': parent,
            }
            steps.append(frame)
            _open_frames()[id(frame)] = (frame, started)

            # Said once, as a step of its own, rather than dropped in silence:
            # a tree that stops halfway reads as a test that stopped there.
            if limit() and len(steps) == limit():
                steps.append({
                    'title': 'more steps not recorded - raise --report-step-limit to keep them',
                    'kind': 'step', 'phase': phase(), 'depth': depth,
                    'status': 'SKIP', 'ms': 0, 'params': [], 'error': '', 'id': len(steps),
                    'parent': parent,
                })

    _store(stack + ((frame, started),), floor, raised)

    return frame


def _parent(stack):
    """The step a step opened now would be a step of, by id, or None.

    Read from the phase's own slice of the stack, so that it agrees with the
    depth counted from the same place: a step drawn at the left margin is a
    step with no parent, and one held open by a fixture across the whole test
    does not adopt the test body.
    """
    for frame, _started in reversed(stack):
        if frame is not None: return frame['id']

    return None


def _at(stack, entry):
    """Where this entry is on the stack, innermost first, or None."""
    for index in range(len(stack) - 1, -1, -1):
        if stack[index] is entry: return index

    return None


def _finish(entry, status='PASS', error=''):
    """Close the step an opened block is holding, wherever the block ended up.

    Normally the entry is on top of this context's stack and is taken off it.
    It is not when a block was entered in one context and left in another - an
    async fixture holding a step open across its ``yield`` is resumed on a task
    of its own, whose stack was copied before the step existed. The frame is
    closed on its own there, because the block did exit: leaving it behind for
    ``take_steps`` to sweep up would report a fixture that worked perfectly as
    the place the test died.

    Whatever sat above it on the stack goes too. A step opened with ``start``
    and never stopped would otherwise stay there for the rest of the test,
    indenting everything after it underneath a block that had already closed.
    """
    if entry is None: return

    epoch, stack, floor, raised = _state()
    index = _at(stack, entry)

    if index is not None: _store(stack[:index], floor, raised)

    frame, started = entry
    if frame is None: return

    with _LOCK:
        _open_frames().pop(id(frame), None)

    _close(frame, started, status, _text(error, ERROR_MAX))


def stop(status='PASS', error='', params=None):
    """Close the innermost open step, whatever happened inside it.

    The stack says which step that is, rather than the caller: a step is closed
    exactly where it was opened, and a caller holding the wrong frame could
    otherwise close somebody else's.
    """
    stack = _stack()
    if not stack: return

    entry = stack[-1]

    # pytest-bdd only knows what a step was called with once it has run it, so
    # the parameters can arrive at the close rather than at the open.
    if params and entry[0] is not None:
        entry[0]['params'] = [[_text(n, VALUE_MAX), _value(v)] for n, v in params]

    _finish(entry, status, error)


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
    epoch, stack, floor, raised = _state()

    if raised is exception: return False

    _store(stack, floor, exception)

    return True


# ------------------------------------------------------------- public API ---

class step(object):
    """Name and time a piece of a test, as a decorator or a ``with`` block.

    ::

        @step("Log in as {user}")
        def login(user): ...

        with step("Add to cart", sku="A-12"):
            cart.add(sku)

    An ``async`` test writes both the same way. ``@step`` on an ``async def``
    times the call, not the building of its coroutine, and ``async with`` holds
    the step open across everything awaited inside it::

        @step("Send the notification")
        async def notify(user): ...

        async with step("Check out"):
            await cart.pay()

    Steps opened in coroutines running concurrently - gathered, or in a task
    group - are siblings, not a chain, and each of them keeps its own idea of
    what an attachment made inside it belongs to.

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

        # What each open block of this step is holding, innermost last. Held
        # here rather than read back off the stack on the way out, because the
        # context that leaves the block is not always the one that entered it.
        # A list because one `step` object can be entered more than once - a
        # decorator's is built fresh per call, but nothing stops a caller
        # keeping one and reusing it.
        self._open = []

    def __enter__(self):
        start(self.title, sorted(self.params.items()))
        self._open.append(_stack()[-1])

        return self

    def __exit__(self, kind, exception, traceback):
        entry = self._open.pop() if self._open else None

        if exception is None:
            _finish(entry)
        else:
            # The message goes on the step that raised, and the steps it was
            # raised inside are marked failed without it. One exception walking
            # out through four steps otherwise prints the same traceback four
            # times, and the innermost - the only one that says where - is the
            # one furthest down the page.
            _finish(entry, _outcome(exception),
                    _error_text(exception) if _first_sighting(exception) else '')

        return False

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, kind, exception, traceback):
        return self.__exit__(kind, exception, traceback)

    def __call__(self, function):
        if _awaits(function):
            @functools.wraps(function)
            async def wrapper(*args, **kwargs):
                bound = _bind(function, args, kwargs)

                async with step(_fill(self.title, bound), **dict(self.params, **bound)):
                    return await function(*args, **kwargs)

            return wrapper

        @functools.wraps(function)
        def wrapper(*args, **kwargs):
            bound = _bind(function, args, kwargs)

            with step(_fill(self.title, bound), **dict(self.params, **bound)):
                return function(*args, **kwargs)

        return wrapper


def _awaits(function):
    """True if calling this hands back something that still has to be awaited.

    Worth going to some trouble over, because getting it wrong is silent: the
    plain wrapper would time the *building* of the coroutine, close the step at
    nought milliseconds and record PASS on a call that had not run yet - so an
    ``async def`` step that goes on to raise is reported green.

    ``iscoroutinefunction`` does not look through ``functools.wraps``, and a
    decorator stacked above this one - a retry, a rate limiter - leaves a plain
    function with the ``async def`` behind it. The ``__wrapped__`` chain those
    leave is followed to find it, and the visited ids are kept because a chain
    pointed back at itself would otherwise be walked forever.
    """
    seen = set()

    while function is not None and id(function) not in seen:
        if inspect.iscoroutinefunction(function): return True

        seen.add(id(function))
        function = getattr(function, '__wrapped__', None)

    return False


def _bind(function, args, kwargs):
    """A call's arguments by name, as far as they can be worked out.

    Never raises: a signature that will not bind - a decorator stacked in a way
    inspect cannot follow - costs the title its placeholders, not the test its
    run.
    """
    try:
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
