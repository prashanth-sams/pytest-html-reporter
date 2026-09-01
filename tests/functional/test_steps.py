"""A suite that exists to fill the Test Steps tab, so you can see it working.

Run it and open the report::

    $ pytest tests/functional/test_steps.py --html-report=./report

No browser, no network, nothing to install. Everything here is what a real
suite would do - a page object whose methods are the steps, a fixture that sets
up and tears down, a parametrized case, a failure buried three steps deep - only
with sleeps where the work would be.
"""

import time

import pytest

from pytest_html_reporter import attach_json, step


class Cart:
    """The page object a UI suite would have, with steps on its methods.

    Decorating the methods once names every test that calls them - which is why
    this is the recipe worth reaching for first. Nothing in the tests below has
    to know that steps exist.
    """

    def __init__(self):
        self.items = []

    @step("Log in as {user}")
    def login(self, user):
        with step("Open the login page"):
            time.sleep(0.03)

        with step("Submit credentials"):
            attach_json({"user": user, "remember": True}, name="Credentials")
            time.sleep(0.05)

    @step("Add {sku} to the cart")
    def add(self, sku, quantity=1):
        time.sleep(0.04)
        self.items += [sku] * quantity

    @step("Check out")
    def checkout(self):
        with step("Total the basket"):
            time.sleep(0.02)

        with step("Charge the card"):
            time.sleep(0.06)

            if any(sku == "DECLINE" for sku in self.items):
                raise AssertionError("card declined by the gateway")


@pytest.fixture
def cart():
    """Setup and teardown steps land under their own phases, not the test's."""
    with step("Open a session"):
        time.sleep(0.02)

    yield Cart()

    with step("Close the session"):
        time.sleep(0.01)


@pytest.mark.smoke
def test_a_shopper_can_buy_one_item(cart):
    """The happy path, as three named steps."""
    cart.login("amy")
    cart.add("A-12")
    cart.checkout()

    assert cart.items == ["A-12"]


@pytest.mark.regression
@pytest.mark.parametrize("quantity", [2, 5])
def test_a_shopper_can_buy_several(cart, quantity):
    """A parametrized case keeps its own row and its own steps."""
    cart.login("amy")
    cart.add("B-7", quantity=quantity)

    with step("Check the basket holds {quantity}".format(quantity=quantity)):
        assert len(cart.items) == quantity


@pytest.mark.regression
def test_a_declined_card_is_reported_on_the_step_that_failed(cart):
    """The point of the tab: the failure names the step, not just the test."""
    cart.login("amy")
    cart.add("DECLINE")
    cart.checkout()


@pytest.mark.slow
def test_a_test_that_names_no_steps_still_says_where_its_time_went(cart):
    """Nothing is declared here, and the tab is still not empty."""
    time.sleep(0.05)

    assert cart.items == []
