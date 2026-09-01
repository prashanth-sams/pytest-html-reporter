"""Cover a Gherkin scenario arriving as steps, and the guard that lets it.

A pytest-bdd scenario is already a list of named steps, so a suite written that
way fills the Test Steps tab without anyone reaching for step(). The half of
this worth being careful about is not the translation but the guard: pytest
refuses to start when a plugin implements a hook nobody registered, and
pytest-bdd is not a dependency of this one.
"""

import os
import re
import subprocess
import sys
import textwrap

import pytest

from pytest_html_reporter.html_reporter import HTMLReporter


FEATURE = '''
    @smoke @cart
    Feature: Shopping cart
      Scenario Outline: Add <count> items
        Given a logged in user
        When I add <count> items to the cart
        Then the cart shows <count> items
        Examples:
          | count |
          | 2     |

      Scenario: A card that is declined
        Given a logged in user
        When the payment is declined
        Then the cart shows 9 items
'''

STEPS = '''
    from pytest_bdd import scenarios, given, when, then, parsers

    scenarios("features")

    @given("a logged in user")
    def _user():
        return {"user": "amy"}

    @when(parsers.parse("I add {count:d} items to the cart"), target_fixture="cart")
    def _add(count):
        return {"n": count}

    @when("the payment is declined")
    def _decline():
        raise AssertionError("card declined by gateway")

    @then(parsers.parse("the cart shows {count:d} items"))
    def _check(cart, count):
        assert cart["n"] == count
'''


def test_every_bdd_hook_is_declared_optional():
    """The whole of the defence, and it fails loudly rather than subtly.

    Without optionalhook, pytest does not warn and does not skip the hook - it
    refuses to start at all, with `unknown hook 'pytest_bdd_after_step'`, for
    every user who has not installed pytest-bdd. Which is most of them.
    """
    hooks = [name for name in dir(HTMLReporter) if name.startswith("pytest_bdd_")]

    assert hooks, "the bdd hooks moved"

    for name in hooks:
        opts = getattr(getattr(HTMLReporter, name), "pytest_impl", {})
        assert opts.get("optionalhook") is True, "%s would break every run without pytest-bdd" % name


def _run(tmp_path, *args):
    """Run a generated feature and hand back the report page it wrote."""
    pytest.importorskip("pytest_bdd")

    (tmp_path / "features").mkdir()
    (tmp_path / "features" / "shop.feature").write_text(textwrap.dedent(FEATURE).lstrip())
    (tmp_path / "test_shop.py").write_text(textwrap.dedent(STEPS))

    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--html-report=./report", "-p", "no:cacheprovider",
         "test_shop.py"] + list(args),
        cwd=str(tmp_path), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        universal_newlines=True,
    )

    report = tmp_path / "report" / "pytest_html_report.html"
    assert report.is_file(), result.stdout

    return report.read_text(encoding="utf-8")


def _payload(page, needle):
    match = re.search(
        r'<div class="step-payload"[^>]*data-test="[^"]*%s[^"]*"[^>]*>(.*?)(?=<div class="step-payload"|<div id=)'
        % re.escape(needle), page, re.S)

    return match.group(1) if match else ""


def _lines(payload):
    return [re.sub(r"<[^>]+>", "", title).strip()
            for title in re.findall(r'class="step-line__title">(.*?)</span>', payload, re.S)]


def test_a_scenarios_steps_arrive_without_anyone_naming_them(tmp_path):
    payload = _payload(_run(tmp_path), "test_add_count_items")

    assert _lines(payload) == [
        "Given a logged in user",
        "When I add 2 items to the cart",
        "Then the cart shows 2 items",
    ]


def test_an_outlines_placeholders_are_shown_filled_in(tmp_path):
    # <count> is already substituted by the time the hook fires, so the report
    # shows the row that actually ran rather than the template it came from.
    payload = _payload(_run(tmp_path), "test_add_count_items")

    assert "<count>" not in payload
    assert "When I add 2 items to the cart" in _lines(payload)


def test_a_gherkin_step_is_badged_as_one(tmp_path):
    # A specification and a piece of somebody's plumbing do not read the same,
    # so they are not drawn the same.
    payload = _payload(_run(tmp_path), "test_add_count_items")

    assert re.findall(r'step-badge--gherkin[^>]*>(\w+)<', payload) == ["Given", "When", "Then"]


def test_the_feature_and_scenario_are_named(tmp_path):
    payload = _payload(_run(tmp_path), "test_add_count_items")

    assert "Shopping cart" in payload
    assert "Add 2 items" in payload
    assert "shop.feature" in payload


def test_a_step_keeps_the_arguments_its_parser_pulled_out(tmp_path):
    payload = _payload(_run(tmp_path), "test_add_count_items")

    assert "count=2" in payload


def test_an_injected_fixture_is_not_shown_as_a_step_argument(tmp_path):
    # pytest-bdd hands the step every target_fixture the scenario has built up
    # by then, so `Then the cart shows 2 items` was arriving with the whole
    # cart printed beside it.
    payload = _payload(_run(tmp_path), "test_add_count_items")

    assert "cart=" not in payload


def test_a_failing_step_is_the_one_that_carries_the_message(tmp_path):
    payload = _payload(_run(tmp_path), "test_a_card_that_is_declined")
    statuses = re.findall(r'class="step-line step-line--(\w+)"', payload)

    assert statuses == ["PASS", "FAIL"]
    assert "card declined by gateway" in payload


def test_a_step_after_the_failing_one_is_never_reported_as_run(tmp_path):
    payload = _payload(_run(tmp_path), "test_a_card_that_is_declined")

    assert "Then the cart shows 9 items" not in _lines(payload)


def test_a_scenarios_tags_arrive_as_markers(tmp_path):
    # pytest-bdd applies @smoke and @cart to the test as real markers, and a
    # feature-level tag belongs to every scenario under it.
    payload = _payload(_run(tmp_path), "test_add_count_items")

    assert "smoke" in payload
    assert "cart" in payload


def test_the_internal_example_marker_is_not_shown_as_one(tmp_path):
    # An Outline's row reaches the test through a parametrize marker of
    # pytest-bdd's own making. It is machinery, and its argvalues carry the
    # whole ParameterSet.
    payload = _payload(_run(tmp_path), "test_add_count_items")

    assert "_pytest_bdd_example" not in payload


def test_the_example_row_is_shown_as_a_parameter(tmp_path):
    payload = _payload(_run(tmp_path), "test_add_count_items")

    assert "count = 2" in payload


def test_a_generated_docstring_is_not_shown_as_a_description(tmp_path):
    # pytest-bdd generates the test function, and its docstring is the absolute
    # path of the feature file - which said nothing and wrapped over two lines.
    payload = _payload(_run(tmp_path), "test_add_count_items")

    assert "Description" not in payload
