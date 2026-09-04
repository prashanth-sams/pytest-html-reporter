"""The last handful of branches, each one a fallback nobody's happy path takes.

Suite Highlights answering before any history exists, a plugin distribution
that will not say what it is called, a step decorator stacked in a way inspect
cannot follow, a buffer somebody left holding the wrong type. None of these is
a feature and none is reached by a run that goes well - which is exactly the
argument for testing them, because a regression in one is invisible until the
day something else has already gone wrong.
"""

import pytest

from pytest_html_reporter.analytics import exception_type
from pytest_html_reporter.attachments import _pending, attach_text, take_attachments
from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.steps import step, take_steps
from pytest_html_reporter.util import (
    _plugin_versions,
    generate_suite_highlights,
    suite_highlights,
)


class _Dist:
    def __init__(self, **attributes):
        for name, value in attributes.items():
            setattr(self, name, value)


class _PluginManager:
    def __init__(self, dists=()):
        self._dists = list(dists)

    def list_plugin_distinfo(self):
        return [(None, dist) for dist in self._dists]


class _Config:
    def __init__(self, dists=()):
        self.pluginmanager = _PluginManager(dists)


def _build(suite, fails):
    return {"content": {"suites": {"1": {"suite_name": suite,
                                         "status": {"total_fail": fails}}}}}


_HIGHLIGHTS = ("highlights", "p_highlights", "max_failure_suite_name",
               "max_failure_suite_count", "max_failure_percent",
               "max_failure_suite_name_final", "max_failure_total_tests")


@pytest.fixture(autouse=True)
def _isolate():
    saved = {name: getattr(ConfigVars, name, None) for name in _HIGHLIGHTS}
    ConfigVars.highlights = {}
    ConfigVars.p_highlights = {}
    take_steps()
    take_attachments()
    yield
    take_steps()
    take_attachments()
    for name, value in saved.items():
        setattr(ConfigVars, name, value)


# ------------------------------------------------------- suite highlights ---

def test_a_first_build_has_no_worst_suite_to_name():
    """Nothing has failed yet, and "0%" against a blank name reads as a bug."""
    generate_suite_highlights()

    assert ConfigVars.max_failure_suite_name_final == "No failures in History"
    assert ConfigVars.max_failure_suite_count == 0
    assert ConfigVars.max_failure_percent == "0"


def test_the_suite_that_failed_most_often_is_the_one_named():
    for _ in range(3):
        suite_highlights(_build("tests/test_cart.py", fails=1))
    suite_highlights(_build("tests/test_login.py", fails=1))

    generate_suite_highlights()

    assert ConfigVars.max_failure_suite_name == "tests/test_cart.py"
    assert ConfigVars.max_failure_suite_count == 3


def test_a_suite_that_also_passed_counts_both_halves_as_its_total():
    """The percentage is failures over every build the suite appeared in, so a
    suite that fails once in fifty is not shown beside one that fails always."""
    suite_highlights(_build("tests/test_cart.py", fails=1))
    for _ in range(4):
        suite_highlights(_build("tests/test_cart.py", fails=0))

    generate_suite_highlights()

    assert ConfigVars.max_failure_total_tests == 5


def test_a_suite_that_has_only_ever_failed_totals_its_failures():
    suite_highlights(_build("tests/test_cart.py", fails=2))
    suite_highlights(_build("tests/test_cart.py", fails=1))

    generate_suite_highlights()

    assert ConfigVars.max_failure_total_tests == 2


# --------------------------------------------------------- plugin versions ---

def test_a_plugin_is_named_and_versioned():
    versions = _plugin_versions(_Config([_Dist(project_name="pytest-xdist",
                                               version="3.8.0")]))

    assert versions == ["xdist-3.8.0"]


def test_a_distribution_using_the_newer_attribute_name_is_read():
    """importlib.metadata calls it `name`; the old pkg_resources called it
    `project_name`, and pytest hands over whichever it has."""
    versions = _plugin_versions(_Config([_Dist(name="pytest-cov", version="7.1.0")]))

    assert versions == ["cov-7.1.0"]


def test_a_distribution_that_will_not_say_what_it_is_called_is_skipped():
    versions = _plugin_versions(_Config([_Dist(project_name="", name=""),
                                         _Dist(name="pytest-cov", version="1.0")]))

    assert versions == ["cov-1.0"]


def test_a_plugin_with_no_version_is_still_named():
    assert _plugin_versions(_Config([_Dist(name="pytest-bdd")])) == ["bdd"]


def test_the_same_plugin_listed_twice_is_named_once():
    dists = [_Dist(name="pytest-cov", version="1.0"),
             _Dist(name="pytest-cov", version="1.0")]

    assert _plugin_versions(_Config(dists)) == ["cov-1.0"]


def test_the_list_is_sorted_so_the_row_reads_the_same_every_run():
    dists = [_Dist(name="pytest-xdist", version="1.0"),
             _Dist(name="pytest-bdd", version="2.0")]

    assert _plugin_versions(_Config(dists)) == ["bdd-2.0", "xdist-1.0"]


def test_a_run_with_no_plugins_at_all_names_none():
    assert _plugin_versions(_Config()) == []


# --------------------------------------------------------------- the step ---

def test_a_signature_inspect_cannot_follow_costs_the_title_not_the_run():
    """A decorator stacked in a way inspect cannot see through still has to
    leave the test running."""
    @step("Charge {amount}")
    def charge(*args, **kwargs):
        return "charged"

    assert charge(10) == "charged"

    recorded, = take_steps()
    assert recorded["status"] == "PASS"


def test_a_signature_that_binds_fills_the_placeholder_in():
    @step("Charge {amount}")
    def charge(amount):
        return "charged"

    charge(10)

    assert take_steps()[0]["title"] == "Charge 10"


def test_a_receiver_is_not_offered_as_a_placeholder_value():
    class Till:
        @step("Charge {amount}")
        def charge(self, amount):
            return "charged"

    Till().charge(10)

    assert take_steps()[0]["title"] == "Charge 10"


# ------------------------------------------------------ the attachment buffer ---

def test_the_attachment_buffer_recovers_from_the_wrong_type():
    ConfigVars._attachments = "not a list"

    assert _pending() == []


def test_an_attachment_still_lands_after_the_buffer_was_replaced():
    ConfigVars._attachments = None
    attach_text("body", name="Body")

    assert len(take_attachments()) == 1


# --------------------------------------------------------------- analytics ---

def test_an_exception_named_on_the_last_line_still_wins():
    """Every line is read, because a traceback puts the raise at the bottom."""
    assert exception_type("some noise\nmore noise\nTimeoutError: gone") \
        == "TimeoutError"


def test_the_first_plain_name_is_kept_when_no_exception_is_ever_named():
    assert exception_type("Timeout: a\nFailure2: b") == "Timeout"
