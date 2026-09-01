"""A cucumber-style suite, to see Given/When/Then arriving as steps.

Run it and open the report::

    $ pytest tests/functional/test_gherkin.py --html-report=./report

Nothing here mentions the reporter. A pytest-bdd scenario is already a list of
named steps, so the tab fills itself - each step timed, badged with its Gherkin
keyword, and carrying whatever its parser pulled out of the line.
"""

import time

import pytest

pytest.importorskip("pytest_bdd", reason="the Gherkin demo needs pytest-bdd")

from pytest_bdd import given, parsers, scenarios, then, when  # noqa: E402


scenarios("features")


@given("a logged in shopper", target_fixture="basket")
def _shopper():
    time.sleep(0.02)

    return []


@when(parsers.parse('they add {count:d} of "{sku}" to the basket'))
def _add(basket, count, sku):
    time.sleep(0.03)
    basket += [sku] * count


@when("they check out")
def _check_out(basket):
    time.sleep(0.04)

    if "DECLINE" in basket:
        raise AssertionError("card declined by the gateway")


@then(parsers.parse("the basket holds {count:d} items"))
def _holds(basket, count):
    assert len(basket) == count
