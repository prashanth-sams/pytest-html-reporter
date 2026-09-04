"""How much a failure matters, as a suite you can look at.

Ordinary pytest, and nothing to configure: ``severity`` is built in the way
``owner`` is. The five levels are Allure's - blocker, critical, normal, minor,
trivial - worst first.

Run it and open the report::

    pytest tests/functional/test_severity.py --html-report=./report

Then, on the Test Steps tab: the Severity row of pills above the rail, under
the Owner row, and a Severity row on each test. The pills are drawn in ladder
order rather than by how many tests are at each level, and they count inside
the two filters above them - so picking ``Failed``, then a team, then
``blocker`` is that team's blocking failures, and the number on the pill is
what the rail will show.

Two tests fail on purpose, at two different levels, because a run where
everything red is equally red says nothing about how the panel ranks them.

Run it two or three times and the Analytics tab grows a "How much it matters"
table, which - like every other panel there - needs more than one build before
it has much to say.

There is no unrated test in this file, and there cannot be: the module-level
``pytestmark`` reaches every test in it. The Unrated pill and the Unrated row
are filled by every other file in this folder, none of which mentions a
severity - so run the whole folder to see them::

    pytest tests/functional/ --html-report=./report
"""

import pytest

# The file's own baseline, the usual way a suite says "this area is ordinary".
# Every test below inherits it, and the ones that say otherwise override it.
pytestmark = pytest.mark.severity("normal")


@pytest.mark.owner("payments-team")
@pytest.mark.severity("blocker")
def test_a_customer_can_pay():
    """The one that stops a release.

    Its Severity row shows two badges: `blocker`, and the module's `normal`
    struck through behind it. Both markers are on this test and always were;
    what the row says is which of them the run was rated at.
    """
    assert True


@pytest.mark.owner("payments-team")
@pytest.mark.severity("critical")
def test_a_declined_card_is_rejected():
    """Red at a level worth waking up for."""
    raise AssertionError("the order completed anyway")


@pytest.mark.severity("trivial")
def test_the_footer_year_is_current():
    """Red, and nobody's evening.

    The panel sorts by the ladder rather than by the numbers, so this stays
    under `blocker` however much redder it gets - a table that put trivial on
    top because trivial had more failures would be arguing with the words in
    it.
    """
    raise AssertionError("still says last year")


@pytest.mark.severity("minor")
@pytest.mark.severity("blocker")
def test_two_levels_at_one_scope():
    """Rated `blocker`.

    Nothing is nearer than anything else here, so the worse of the two is
    taken. Reading a blocker down to a minor because of the order two
    decorators happen to sit in is the one mistake here that hides work.
    """
    assert True


@pytest.mark.severity("Critical")
def test_the_level_is_the_same_however_it_is_capitalised():
    """One level, not two - a shift key must not split the counts in half."""
    assert True


@pytest.mark.severity
def test_a_levelless_marker_rates_nothing():
    """Empty brackets name no level.

    It is not a sixth level and it is not `normal`; it is a marker somebody
    left unfinished, so it stays a plain badge and the module's `normal` is
    what this test is rated at.
    """
    assert True


@pytest.mark.severity("catastrophic")
def test_a_word_outside_the_five_is_kept():
    """Shown and filterable rather than dropped - a filter that silently omits
    a test is worse than one that shows a typo - but sorted after `trivial`
    everywhere, because it is far more often a typo than a level somebody
    meant, and a typo must not outrank a blocker.
    """
    assert True


@pytest.mark.severity("minor")
class TestTheCheckoutPage:
    """A class rated below its module, which the tests inside it inherit."""

    def test_the_basket_totals_correctly(self):
        """Rated `minor`, from the class - which its tooltip says."""
        assert True

    @pytest.mark.severity("blocker")
    def test_the_basket_survives_a_reload(self):
        """And nearer still wins again: `blocker`, over the class's `minor`."""
        assert True
