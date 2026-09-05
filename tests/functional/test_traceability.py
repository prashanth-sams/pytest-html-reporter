"""Owners and tracker links, as a suite you can look at.

Everything here is ordinary pytest. The only thing that makes an id clickable
is the ``report_link_pattern`` block in the repository's ``pytest.ini``::

    report_link_pattern =
        jira = https://acme.atlassian.net/browse/{}
        testcase = https://acme.testrail.io/index.php?/cases/view/{}

which reads as "when you see @pytest.mark.jira('PAY-412'), build a link by
putting PAY-412 where the {} is". Nothing is fetched and no token is needed -
the ids below point at hosts that do not exist, and the badges still render,
which is the whole point of a url template over an api client.

Run it and open the report::

    pytest tests/functional/test_traceability.py --html-report=./report

Then, on the Test Steps tab: the Owner row of pills above the rail, and the
Owner / Jira / Testcase rows on each test. Run it two or three times and the
Analytics tab grows a "Who owns what" table, which needs more than one build
before it has anything to say.

Two tests fail on purpose. They are what puts a red row in that table - a
roll-up where every team is green shows nothing about how it ranks them.

There is no unowned test in this file, and there cannot be: ``pytestmark``
reaches every test in the module, class methods included. The Unowned pill and
the Unowned row are filled by every other file in this folder, none of which
mentions an owner - so run the whole folder to see them::

    pytest tests/functional/ --html-report=./report
"""

import pytest

# Written once for the file rather than on each test, which is the usual way a
# team claims a suite. It reaches every test below through iter_markers_with_node,
# so the report shows it on all of them and says it came from the module.
pytestmark = pytest.mark.owner("payments-team")


@pytest.mark.jira("PAY-412")
@pytest.mark.testcase("C4471")
def test_a_declined_card_is_rejected():
    """A card the bank declines must not complete the order."""
    assert True


@pytest.mark.jira("PAY-880")
@pytest.mark.jira("PAY-881")
def test_a_refund_returns_the_full_amount():
    """Two tickets on one test, which land in one Jira row as two badges."""
    assert 99.50 == 100.00


@pytest.mark.owner("platform-team")
@pytest.mark.testcase("C5002")
def test_the_gateway_is_reachable():
    """A second owner on top of the module's.

    Both are shown and both are counted: two owner markers are two teams that
    put their name on this, and picking one would take the other off the hook.
    """
    assert True


@pytest.mark.jira
def test_a_ticketless_marker_links_nowhere():
    """``@pytest.mark.jira`` with nothing in its brackets names no issue.

    It stays a plain badge rather than becoming a link to the tracker's front
    page, which would look like the link had worked.
    """
    assert True


@pytest.mark.owner("search-team")
@pytest.mark.jira("SRCH-12")
@pytest.mark.slow
def test_searching_for_a_product():
    """A third team, so the Owner pills have something to choose between."""
    raise AssertionError("no results returned")

