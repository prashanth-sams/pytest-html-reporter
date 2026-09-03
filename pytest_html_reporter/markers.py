"""What a test says about itself before it runs: its markers, its parameters,
its fixtures and its docstring.

All of it is read off the item at teardown, which is the only moment that sees
the whole picture - a marker added by ``request.node.add_marker`` during the
test is not there at collection, and a parametrized case does not know its own
values until it has one.

``item.own_markers`` is the obvious source and it is the wrong one: it holds
only the markers written on the test itself, so a module-level ``pytestmark``
and a ``@pytest.mark.parametrize`` on the class both vanish from it. The report
promises every marker, so ``iter_markers_with_node`` is used instead - it walks
out through class, module, package and session, and hands back the node each
marker came from, which is what lets the report say where one was written.

Everything returned is built-in types. A record has to survive being pickled
back from an xdist worker, and a Mark holding a live exception class does not.
"""

from collections import OrderedDict


# pytest's own markers. Not a style choice: these change how the test is run,
# while a user's marker only names it, and the two read very differently on a
# badge.
BUILTIN_MARKERS = frozenset((
    'skip', 'skipif', 'xfail', 'parametrize', 'usefixtures', 'filterwarnings',
))

# pytest-bdd hands a Scenario Outline's example row to the test through a
# parametrize marker of its own. It is machinery, not something anyone wrote,
# and its argvalues carry the whole ParameterSet - so it is dropped here and
# the row's values are shown as parameters instead. Note that the name to match
# is the *argument*: the marker itself is an ordinary `parametrize`.
INTERNAL_MARKERS = frozenset(('_pytest_bdd_example',))


def _is_internal(mark):
    """True for a marker some other plugin applied as plumbing.

    Nothing a user wrote is hidden - the report promises every marker - but a
    generated one names machinery, and showing it invites people to go looking
    for a decorator that is not in their file.
    """
    if mark.name in INTERNAL_MARKERS: return True

    return bool(mark.args) and str(mark.args[0]) in INTERNAL_MARKERS


# Fixtures every test is given whether it asked or not. Listing them would bury
# the one or two a test actually named.
IMPLICIT_FIXTURES = frozenset(('request', 'pytestconfig'))

# The node types iter_markers_with_node walks out through, as the report says
# them. Anything else - a custom collector - falls back to its own class name.
SCOPES = OrderedDict((
    ('Function', 'function'),
    ('Class', 'class'),
    ('Module', 'module'),
    ('Package', 'package'),
    ('Session', 'session'),
))

VALUE_MAX = 120
DOC_MAX = 400


def _value(value):
    """A marker argument or a parameter as something readable on a badge.

    ``repr`` is the honest default but it is ugly for the two things that turn
    up most: ``@pytest.mark.xfail(raises=ValueError)`` reads as
    ``<class 'ValueError'>``, and every string argument arrives wearing quotes
    that say nothing. Both are unwrapped; everything else keeps its repr, which
    is the only form that cannot mislead.
    """
    if isinstance(value, type): return value.__name__

    if isinstance(value, str): text = value
    else:
        try:
            text = repr(value)
        except Exception:
            # A repr that raises is rare and entirely the object's business,
            # but it must not take the report down with it.
            text = '<unrepresentable>'

    return text[:VALUE_MAX - 1] + '…' if len(text) > VALUE_MAX else text


def _arguments(mark):
    """The arguments worth showing for one marker.

    Two of pytest's own are cut down, because printing them whole says less
    than printing part of them. ``parametrize`` carries every row the test will
    ever run with - a hundred of them for one badge - and this case's own row
    is shown as its parameters anyway, so only the argument names are kept.
    And a ``skipif`` condition is evaluated at import, so what arrives is
    ``True`` or ``False`` rather than the expression that was written: the
    reason is the half that still means something.
    """
    if mark.name == 'parametrize': return [_value(arg) for arg in mark.args[:1]]

    if mark.name == 'skipif':
        return [_value(arg) for arg in mark.args if not isinstance(arg, bool)]

    return [_value(arg) for arg in mark.args]


def _signature(mark):
    """A marker written the way it was written in the file.

    ``@pytest.mark.flaky(reruns=3)`` rather than a name and a shrug.
    """
    parts = _arguments(mark)
    parts += ['%s=%s' % (name, _value(value)) for name, value in sorted(mark.kwargs.items())]

    return '%s(%s)' % (mark.name, ', '.join(parts)) if parts else mark.name


def _scope(node):
    return SCOPES.get(type(node).__name__, type(node).__name__.lower())


def markers(item):
    """Every marker on a test, nearest first, each said once.

    A marker written at more than one level arrives once per level, so
    ``pytestmark = pytest.mark.slow`` on a module whose class repeats it is two
    identical entries. Identical ones collapse; ``tier('unit')`` and
    ``tier('slow')`` do not, because they are two different things to say.
    """
    seen = OrderedDict()

    for node, mark in _iter_markers(item):
        if _is_internal(mark): continue

        signature = _signature(mark)
        if signature in seen: continue

        seen[signature] = {
            'name': str(mark.name),
            'text': signature,
            # Where it was written. A failure explained by a marker nobody
            # remembers applying is usually one inherited from a conftest.
            'scope': _scope(node),
            'kind': 'builtin' if mark.name in BUILTIN_MARKERS else 'user',
        }

    return list(seen.values())


def _iter_markers(item):
    """(node, mark) pairs, closest to the test first.

    The order of the pair is worth pinning down: it reads as (mark, node) and
    is not, so getting it round the wrong way asks a Function for ``.args`` and
    takes down every test in the run.
    """
    walk = getattr(item, 'iter_markers_with_node', None)
    if walk is None: return [(item, mark) for mark in getattr(item, 'own_markers', [])]

    try:
        return list(walk())
    except Exception:
        return [(item, mark) for mark in getattr(item, 'own_markers', [])]


def params(item):
    """The values this parametrized case was called with, as [name, value].

    Read off the callspec rather than off the ``parametrize`` marker: the
    marker carries every row the test will ever run with, and this test is one
    of them.
    """
    callspec = getattr(item, 'callspec', None)
    if callspec is None: return []

    values = []
    for name, value in sorted(getattr(callspec, 'params', {}).items()):
        # A Scenario Outline's row arrives as one dict under pytest-bdd's own
        # parameter name. Unwrapped, it is exactly what the Examples table
        # said - count = 2 - rather than a mapping nobody wrote.
        if name in INTERNAL_MARKERS and isinstance(value, dict):
            values += [[str(key), _value(item)] for key, item in sorted(value.items())]
            continue

        values.append([str(name), _value(value)])

    return values


def fixtures(item):
    """The fixtures a test asked for, by name, in the order it asked.

    Taken from the test's own signature and its ``usefixtures`` markers rather
    than from ``item.fixturenames``, which is the whole transitive closure -
    every autouse fixture in every conftest above the test, plus the fixtures
    its fixtures depend on. Asking for ``tmp_path`` put ``tmp_path_factory``
    in that list too, and a test that names two fixtures should not read as a
    test that names nine.

    A parametrized argument is a fixture as far as pytest is concerned; it is
    already shown as a parameter, so it is not repeated here.
    """
    function = getattr(item, 'function', None)
    parametrized = set(getattr(getattr(item, 'callspec', None), 'params', {}) or {})

    names = []
    try:
        code = function.__code__
        names += list(code.co_varnames[:code.co_argcount])
    except AttributeError:
        pass

    for _node, mark in _iter_markers(item):
        if mark.name == 'usefixtures': names += [str(arg) for arg in mark.args]

    seen = OrderedDict.fromkeys(
        name for name in names
        if name not in IMPLICIT_FIXTURES
        and name not in parametrized
        and not name.startswith('_')
        # A method's receiver is not a fixture, and neither is anything else
        # pytest injects positionally.
        and name not in ('self', 'cls')
    )

    return list(seen)


def doc(item):
    """The test's own docstring, which is usually the sentence a report wants.

    Only the function's own: a class docstring describes the class, and
    repeating it under every method in it says nothing about any of them.
    """
    function = getattr(item, 'function', None)

    # Checked rather than left to getattr's default: ``None.__doc__`` is
    # NoneType's own docstring, so an item that is not a python function - a
    # DoctestItem under --doctest-modules, a YAML-driven one - was describing
    # every one of its rows as "The type of the None singleton."
    if function is None: return ''

    text = (getattr(function, '__doc__', None) or '').strip()
    if not text: return ''

    # Collapsed to one paragraph. An indented docstring keeps the indentation
    # of the file it was written in, which is nothing to do with the report.
    text = ' '.join(line.strip() for line in text.splitlines() if line.strip())

    return text[:DOC_MAX - 1] + '…' if len(text) > DOC_MAX else text


def describe(item):
    """Everything the report knows about a test that is not its outcome.

    Guarded as a whole rather than field by field: this runs inside a teardown
    hook, and an item that will not answer one of these questions is not a
    reason for the test to be missing from the report.
    """
    try:
        return {
            'markers': markers(item),
            'params': params(item),
            'fixtures': fixtures(item),
            'doc': doc(item),
        }
    except Exception:
        return {'markers': [], 'params': [], 'fixtures': [], 'doc': ''}
