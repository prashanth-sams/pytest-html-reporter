"""Cover what markers.py does when the item will not cooperate.

test_markers.py drives real runs, which is the right way to prove that a
module-level pytestmark is not missed. It cannot reach the other half of this
module, though: every helper here is written to survive an item that answers a
question badly, and pytest does not build badly-behaved items on request. So
these are hand-built - a mark whose repr raises, an item whose
iter_markers_with_node blows up, a pytest-bdd example row - and each one exists
because the module has a branch for it.

The rule the guards are there for: this all runs inside a teardown hook, and a
test missing from the report entirely is a worse outcome than a badge that
reads '<unrepresentable>'.
"""

from pytest_html_reporter.markers import (
    DOC_MAX,
    VALUE_MAX,
    _iter_markers,
    _value,
    describe,
    doc,
    fixtures,
    markers,
    params,
)


class Mark:
    """A pytest Mark, as much of one as these helpers ever read."""

    def __init__(self, name, args=(), kwargs=None):
        self.name = name
        self.args = tuple(args)
        self.kwargs = dict(kwargs or {})


class Node:
    """A collection node, named so _scope can say where a marker was written."""


class Function(Node):
    pass


class Module(Node):
    pass


class Item:
    """An item that answers exactly what it was built to answer."""

    def __init__(self, pairs=None, own_markers=(), callspec=None,
                 function=None, walk_raises=False):
        self._pairs = pairs
        self.own_markers = list(own_markers)
        self.walk_raises = walk_raises

        if callspec is not None:
            self.callspec = callspec
        if function is not None:
            self.function = function

    def iter_markers_with_node(self):
        if self.walk_raises:
            raise RuntimeError("this item will not be walked")
        return list(self._pairs or [])


class CallSpec:
    def __init__(self, params):
        self.params = params


# ------------------------------------------------------------------ _value ---

def test_an_exception_class_is_named_rather_than_repred():
    """xfail(raises=ValueError) should not read as <class 'ValueError'>."""
    assert _value(ValueError) == "ValueError"


def test_a_string_loses_the_quotes_that_said_nothing():
    assert _value("smoke") == "smoke"


def test_everything_else_keeps_the_repr_that_cannot_mislead():
    assert _value(3) == "3"
    assert _value(None) == "None"
    assert _value([1, 2]) == "[1, 2]"


def test_a_repr_that_raises_does_not_take_the_report_down():
    class Awkward:
        def __repr__(self):
            raise RuntimeError("no repr for you")

    assert _value(Awkward()) == "<unrepresentable>"


def test_a_long_value_is_cut_to_something_a_badge_can_hold():
    text = _value("x" * (VALUE_MAX + 50))

    assert len(text) == VALUE_MAX
    assert text.endswith("…")


def test_a_value_exactly_at_the_limit_is_left_alone():
    assert _value("x" * VALUE_MAX) == "x" * VALUE_MAX


# -------------------------------------------------------------- _signature ---

def test_a_marker_is_written_the_way_the_file_wrote_it():
    item = Item(pairs=[(Function(), Mark("flaky", kwargs={"reruns": 3}))])

    assert markers(item)[0]["text"] == "flaky(reruns=3)"


def test_a_marker_with_nothing_to_say_is_just_its_name():
    item = Item(pairs=[(Function(), Mark("slow"))])

    assert markers(item)[0]["text"] == "slow"


def test_a_parametrize_marker_shows_only_its_names():
    """It carries every row the test will ever run with - a hundred per badge."""
    mark = Mark("parametrize", args=("count", [1, 2, 3, 4, 5]))
    item = Item(pairs=[(Function(), mark)])

    assert markers(item)[0]["text"] == "parametrize(count)"


def test_a_skipif_shows_the_reason_not_the_bool_it_became():
    """The condition was evaluated at import; only the reason still means anything."""
    mark = Mark("skipif", args=(True,), kwargs={"reason": "windows only"})
    item = Item(pairs=[(Function(), mark)])

    assert markers(item)[0]["text"] == "skipif(reason=windows only)"


def test_a_skipif_written_with_a_string_condition_keeps_it():
    mark = Mark("skipif", args=("sys.platform == 'win32'",))
    item = Item(pairs=[(Function(), mark)])

    assert markers(item)[0]["text"] == "skipif(sys.platform == 'win32')"


def test_pytests_own_markers_are_told_apart_from_everyone_elses():
    item = Item(pairs=[(Function(), Mark("skip")), (Function(), Mark("tier"))])

    assert [entry["kind"] for entry in markers(item)] == ["builtin", "user"]


def test_a_marker_says_which_scope_it_was_written_at():
    item = Item(pairs=[(Function(), Mark("fast")), (Module(), Mark("slow"))])

    assert [entry["scope"] for entry in markers(item)] == ["function", "module"]


def test_an_unfamiliar_collector_is_named_after_itself():
    class Repository(Node):
        pass

    item = Item(pairs=[(Repository(), Mark("slow"))])

    assert markers(item)[0]["scope"] == "repository"


def test_the_same_marker_from_two_levels_is_said_once():
    item = Item(pairs=[(Function(), Mark("slow")), (Module(), Mark("slow"))])

    assert len(markers(item)) == 1


def test_two_markers_saying_different_things_both_survive():
    item = Item(pairs=[(Function(), Mark("tier", args=("unit",))),
                       (Module(), Mark("tier", args=("slow",)))])

    assert [entry["text"] for entry in markers(item)] == ["tier(unit)", "tier(slow)"]


def test_a_marker_another_plugin_applied_as_plumbing_is_hidden():
    """Showing it invites people to go looking for a decorator not in their file."""
    item = Item(pairs=[(Function(), Mark("parametrize", args=("_pytest_bdd_example",))),
                       (Function(), Mark("smoke"))])

    assert [entry["name"] for entry in markers(item)] == ["smoke"]


# ------------------------------------------------------------ _iter_markers ---

def test_an_item_too_old_to_walk_falls_back_to_its_own_markers():
    class Old:
        own_markers = [Mark("slow")]

    pairs = _iter_markers(Old())

    assert [mark.name for _node, mark in pairs] == ["slow"]


def test_a_walk_that_raises_falls_back_rather_than_failing_the_test():
    item = Item(walk_raises=True, own_markers=[Mark("slow")])

    assert [mark.name for _node, mark in _iter_markers(item)] == ["slow"]


def test_the_pair_is_node_first_so_nobody_asks_a_function_for_args():
    """Round the wrong way this takes down every test in the run."""
    node, mark = _iter_markers(Item(pairs=[(Function(), Mark("slow"))]))[0]

    assert isinstance(node, Function)
    assert mark.name == "slow"


# ------------------------------------------------------------------ params ---

def test_a_test_that_was_not_parametrized_has_no_parameters():
    assert params(Item()) == []


def test_the_parameters_are_this_cases_own_row():
    item = Item(callspec=CallSpec({"count": 2, "name": "amy"}))

    assert params(item) == [["count", "2"], ["name", "amy"]]


def test_a_gherkin_example_row_is_unwrapped_into_its_own_values():
    """Otherwise the row reads as a mapping nobody wrote."""
    item = Item(callspec=CallSpec({"_pytest_bdd_example": {"count": "2"}}))

    assert params(item) == [["count", "2"]]


def test_a_bdd_parameter_that_is_not_a_mapping_is_left_as_it_is():
    item = Item(callspec=CallSpec({"_pytest_bdd_example": "2"}))

    assert params(item) == [["_pytest_bdd_example", "2"]]


def test_a_callspec_with_no_params_at_all_yields_nothing():
    item = Item(callspec=CallSpec({}))

    assert params(item) == []


# ---------------------------------------------------------------- fixtures ---

def test_the_fixtures_are_the_ones_the_test_named_in_order():
    def a_test(page, tmp_path):
        pass

    assert fixtures(Item(function=a_test)) == ["page", "tmp_path"]


def test_the_fixtures_every_test_gets_anyway_are_not_listed():
    def a_test(request, pytestconfig, page):
        pass

    assert fixtures(Item(function=a_test)) == ["page"]


def test_a_methods_receiver_is_not_a_fixture():
    def a_test(self, page):
        pass

    assert fixtures(Item(function=a_test)) == ["page"]


def test_a_usefixtures_marker_counts_as_asking():
    def a_test():
        pass

    item = Item(function=a_test, pairs=[(Function(), Mark("usefixtures", args=("db",)))])

    assert fixtures(item) == ["db"]


def test_a_parametrized_argument_is_shown_as_a_parameter_not_a_fixture():
    def a_test(count, page):
        pass

    item = Item(function=a_test, callspec=CallSpec({"count": 2}))

    assert fixtures(item) == ["page"]


def test_a_private_argument_is_not_offered_as_a_fixture():
    def a_test(_internal, page):
        pass

    assert fixtures(Item(function=a_test)) == ["page"]


def test_the_same_fixture_asked_for_twice_is_listed_once():
    def a_test(db):
        pass

    item = Item(function=a_test, pairs=[(Function(), Mark("usefixtures", args=("db",)))])

    assert fixtures(item) == ["db"]


def test_an_item_with_no_function_asks_for_nothing():
    """A collector that is not a test function still has to answer."""
    assert fixtures(Item()) == []


def test_a_function_with_no_code_object_asks_for_nothing():
    class Callable:
        def __call__(self):
            pass

    assert fixtures(Item(function=Callable())) == []


# --------------------------------------------------------------------- doc ---

def test_the_docstring_is_collapsed_to_one_paragraph():
    """An indented docstring keeps the indentation of the file it is in."""
    def a_test():
        """First line.

        Second line.
        """

    assert doc(Item(function=a_test)) == "First line. Second line."


def test_a_test_with_no_docstring_says_nothing():
    def a_test():
        pass

    assert doc(Item(function=a_test)) == ""


def test_a_long_docstring_is_cut():
    def a_test():
        pass

    a_test.__doc__ = "x " * DOC_MAX

    text = doc(Item(function=a_test))
    assert len(text) == DOC_MAX
    assert text.endswith("…")


def test_an_item_that_is_not_a_python_function_has_no_docstring():
    """A DoctestItem has no .function, and ``None.__doc__`` is not empty - it
    is NoneType's own docstring, so every doctest row in a --doctest-modules
    run was described as "The type of the None singleton."
    """
    assert doc(Item()) == ""
    assert describe(Item())["doc"] == ""


# ---------------------------------------------------------------- describe ---

def test_describe_answers_every_question_at_once():
    def a_test(page):
        """What it does."""

    item = Item(function=a_test, pairs=[(Function(), Mark("slow"))],
                callspec=CallSpec({"count": 2}))

    assert describe(item) == {
        "markers": [{"name": "slow", "text": "slow", "args": [],
                     "scope": "function", "kind": "user"}],
        "params": [["count", "2"]],
        "fixtures": ["page"],
        "doc": "What it does.",
    }


def test_an_item_that_will_not_answer_is_still_not_missing_from_the_report():
    """Guarded as a whole: a blank description beats a test nobody can see."""
    class Hostile:
        @property
        def own_markers(self):
            raise RuntimeError("nope")

        def iter_markers_with_node(self):
            raise RuntimeError("nope")

    assert describe(Hostile()) == {"markers": [], "params": [],
                                   "fixtures": [], "doc": ""}
