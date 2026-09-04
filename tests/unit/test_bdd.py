"""Cover the Gherkin translation itself, hook by hook.

test_bdd_steps.py drives a real pytest-bdd suite in a subprocess, which proves
the wiring but says nothing about the corners: an object that raises on
attribute access, a keyword pytest-bdd spells differently in the version
somebody happens to have, a fixture handed to a step alongside its own parsed
arguments. Those are the cases the module reads defensively for, and the only
way to reach them is to call it with the objects it was written to survive.

The steps buffer is module state, so every test drains it first - a step left
behind by the test above would be counted as this one's.
"""

import pytest

from pytest_html_reporter import bdd
from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.steps import take_steps


@pytest.fixture(autouse=True)
def drained():
    take_steps()
    ConfigVars._step_limit = 500
    ConfigVars._bdd = None
    yield
    take_steps()
    ConfigVars._bdd = None


class _Step:
    """A pytest-bdd step, named the way whichever version built it did."""

    def __init__(self, **attributes):
        for name, value in attributes.items():
            setattr(self, name, value)


class _Hostile:
    """An object whose attributes raise - a handle whose session has gone."""

    def __getattribute__(self, name):
        raise RuntimeError("session closed")


# ------------------------------------------------------------------ _read ---

def test_read_takes_the_first_name_the_object_answers_to():
    step = _Step(rel_filename="features/cart.feature", filename="/abs/cart.feature")

    assert bdd._read(step, "rel_filename", "filename") == "features/cart.feature"


def test_read_falls_through_to_the_older_name():
    """pytest-bdd renamed these across majors, and the report wants either."""
    step = _Step(filename="/abs/cart.feature")

    assert bdd._read(step, "rel_filename", "filename") == "/abs/cart.feature"


def test_read_skips_a_name_that_is_present_but_none():
    step = _Step(rel_filename=None, filename="/abs/cart.feature")

    assert bdd._read(step, "rel_filename", "filename") == "/abs/cart.feature"


def test_read_is_none_when_the_object_answers_to_none_of_them():
    assert bdd._read(_Step(), "rel_filename", "filename") is None


def test_read_survives_an_attribute_that_raises():
    """A step object is somebody else's; reading it must not fail the test."""
    assert bdd._read(_Hostile(), "keyword", "name") is None


# ------------------------------------------------------------------ _text ---

def test_text_stringifies_whatever_it_found():
    assert bdd._text(_Step(name=12), "name") == "12"


def test_text_is_empty_rather_than_the_word_none():
    """'' is what the badge renders as nothing; 'None' would be printed."""
    assert bdd._text(_Step(), "name") == ""


# ------------------------------------------------------------------ _kind ---

@pytest.mark.parametrize("keyword", ["Given", "WHEN", " then ", "And", "But"])
def test_kind_is_the_word_the_feature_file_wrote(keyword):
    assert bdd._kind(_Step(keyword=keyword)) == keyword.strip().lower()


def test_kind_falls_back_to_the_type_pytest_bdd_resolved():
    """A dialect spelling its keyword differently still gets a real badge."""
    assert bdd._kind(_Step(keyword="Etant donne", type="given")) == "given"


def test_kind_is_a_plain_step_when_neither_is_a_gherkin_word():
    assert bdd._kind(_Step(keyword="Zzz", type="Zzz")) == "step"


def test_kind_is_a_plain_step_when_the_object_offers_nothing():
    assert bdd._kind(_Step()) == "step"


# ----------------------------------------------------------------- _title ---

def test_title_keeps_the_keyword_in_front_of_the_name():
    step = _Step(keyword="Given", name="a logged in user")

    assert bdd._title(step) == "Given a logged in user"


def test_title_is_the_name_alone_when_there_is_no_keyword():
    assert bdd._title(_Step(name="a logged in user")) == "a logged in user"


def test_title_of_an_outline_row_is_the_row_that_ran():
    """Placeholders are filled in before the hook fires, so 2 not <count>."""
    step = _Step(keyword="When", name="I add 2 items to the cart")

    assert bdd._title(step) == "When I add 2 items to the cart"


# ---------------------------------------------------------------- _params ---

def test_params_keep_the_steps_own_parsed_arguments():
    assert bdd._params({"count": 2}) == [("count", 2)]


def test_params_drop_the_fixtures_injected_beside_them():
    """A target_fixture cart is plumbing; printing it beside the step is noise."""
    assert bdd._params({"count": 2, "cart": {"n": 2}}) == [("count", 2)]


def test_params_drop_private_names():
    assert bdd._params({"_request": "x", "count": 2}) == [("count", 2)]


def test_params_keep_every_scalar_a_gherkin_parser_can_yield():
    found = bdd._params({"text": "amy", "n": 2, "ratio": 1.5, "ok": True, "none": None})

    assert found == [("n", 2), ("none", None), ("ok", True),
                     ("ratio", 1.5), ("text", "amy")]


def test_params_are_sorted_so_the_row_reads_the_same_every_run():
    assert [name for name, _ in bdd._params({"z": 1, "a": 2})] == ["a", "z"]


@pytest.mark.parametrize("value", [None, [], "not a dict", 7])
def test_params_are_empty_when_pytest_bdd_hands_over_no_mapping(value):
    assert bdd._params(value) == []


# ------------------------------------------------------------ the hooks ---

def test_before_step_opens_the_step_with_its_gherkin_badge():
    bdd.before_step(_Step(keyword="Given", name="a logged in user"))
    bdd.after_step({})

    step, = take_steps()
    assert step["title"] == "Given a logged in user"
    assert step["kind"] == "given"
    assert step["status"] == "PASS"


def test_after_step_records_what_the_step_was_called_with():
    bdd.before_step(_Step(keyword="When", name="I add 2 items"))
    bdd.after_step({"count": 2, "cart": {"n": 2}})

    step, = take_steps()
    assert step["params"] == [["count", "2"]]


def test_step_error_closes_the_step_that_raised_with_why():
    """pytest-bdd never calls after_step for a failure, so this is its close."""
    bdd.before_step(_Step(keyword="When", name="the payment is declined"))
    bdd.step_error(AssertionError("card declined by gateway"), {"count": 2})

    step, = take_steps()
    assert step["status"] == "FAIL"
    assert step["error"] == "AssertionError: card declined by gateway"
    assert step["params"] == [["count", "2"]]


def test_step_error_needs_no_arguments_to_close_a_step():
    bdd.before_step(_Step(keyword="Then", name="the cart shows 9 items"))
    bdd.step_error(ValueError("nope"))

    step, = take_steps()
    assert step["status"] == "FAIL"
    assert step["params"] == []


def test_lookup_error_names_a_step_the_suite_never_implemented():
    """Nothing opened this one, so the tab only names it if this does both."""
    bdd.lookup_error(_Step(keyword="Then", name="the cart is emailed"),
                     Exception("StepDefinitionNotFoundError"))

    step, = take_steps()
    assert step["title"] == "Then the cart is emailed"
    assert step["kind"] == "then"
    assert step["status"] == "FAIL"
    assert "StepDefinitionNotFoundError" in step["error"]


# --------------------------------------------------------- the scenario ---

def test_before_scenario_remembers_the_feature_file_the_test_came_from():
    bdd.before_scenario(
        _Step(name="Shopping cart", rel_filename="features/cart.feature", tags=["cart"]),
        _Step(name="Add 2 items", tags=["smoke"]),
    )

    assert bdd.take_scenario() == {
        "feature": "Shopping cart",
        "scenario": "Add 2 items",
        "file": "features/cart.feature",
        "tags": ["cart", "smoke"],
    }


def test_before_scenario_prefers_the_path_the_run_saw():
    """An absolute path says nothing useful in a published report."""
    bdd.before_scenario(
        _Step(name="Cart", rel_filename="features/cart.feature",
              filename="/home/ci/build/features/cart.feature"),
        _Step(name="Add"),
    )

    assert bdd.take_scenario()["file"] == "features/cart.feature"


def test_before_scenario_falls_back_to_the_absolute_path():
    bdd.before_scenario(
        _Step(name="Cart", filename="/home/ci/build/features/cart.feature"),
        _Step(name="Add"),
    )

    assert bdd.take_scenario()["file"] == "/home/ci/build/features/cart.feature"


def test_scenario_tags_are_deduplicated_across_feature_and_scenario():
    bdd.before_scenario(_Step(name="Cart", tags=["smoke", "cart"]),
                        _Step(name="Add", tags=["smoke"]))

    assert bdd.take_scenario()["tags"] == ["cart", "smoke"]


def test_a_scenario_with_no_tags_anywhere_records_an_empty_list():
    bdd.before_scenario(_Step(name="Cart"), _Step(name="Add"))

    assert bdd.take_scenario()["tags"] == []


def test_take_scenario_forgets_it_so_the_next_test_cannot_claim_it():
    """A plain pytest test must not be reported as part of somebody's feature."""
    bdd.before_scenario(_Step(name="Cart"), _Step(name="Add"))
    bdd.take_scenario()

    assert bdd.take_scenario() is None


def test_take_scenario_is_none_when_no_scenario_ever_ran():
    assert bdd.take_scenario() is None
