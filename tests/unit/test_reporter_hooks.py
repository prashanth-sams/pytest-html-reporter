"""Cover the reporter's optional hooks and its two "never take the report down" paths.

Two unrelated things live here because they share one rule.

The pytest-bdd hooks are all ``optionalhook``, and that is load-bearing: pytest
refuses to start when a plugin implements a hook nobody registered, so
declaring them plainly would take down every run without pytest-bdd - which is
most of them. Called directly here, because a suite that has pytest-bdd
installed never exercises the plain forwarding, and a suite that does not never
reaches them at all.

The junit write and the attachment drain are the other half of the same rule: a
raise from either happens after every test has finished, and would cost the run
its html report, its output.json and its archived build over a decoration.
"""

import pytest

from pytest_html_reporter.attachments import attach_text, take_attachments
from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.html_reporter import HTMLReporter
from pytest_html_reporter.steps import take_steps


class _FakePluginManager:
    def hasplugin(self, name):
        return False


class _FakeConfig:
    def __init__(self, options=None):
        self.pluginmanager = _FakePluginManager()
        self._options = options or {}

    def getoption(self, name, default=None):
        return self._options.get(name, default)

    def getini(self, name):
        raise ValueError(name)


class _Named:
    def __init__(self, **attributes):
        for name, value in attributes.items():
            setattr(self, name, value)


@pytest.fixture(autouse=True)
def _drained():
    take_steps()
    take_attachments()
    ConfigVars._bdd = None
    yield
    take_steps()
    take_attachments()
    ConfigVars._bdd = None


def _reporter(tmp_path, **options):
    return HTMLReporter(str(tmp_path), "", _FakeConfig(options))


# ------------------------------------------------------- the pytest-bdd hooks ---

def test_a_scenario_starting_is_remembered_for_the_record(tmp_path):
    reporter = _reporter(tmp_path)

    reporter.pytest_bdd_before_scenario(
        request=None,
        feature=_Named(name="Shopping cart", rel_filename="features/cart.feature"),
        scenario=_Named(name="Add 2 items"))

    assert ConfigVars._bdd["feature"] == "Shopping cart"
    assert ConfigVars._bdd["scenario"] == "Add 2 items"


def test_a_step_starting_and_finishing_reaches_the_steps_tab(tmp_path):
    reporter = _reporter(tmp_path)
    step = _Named(keyword="Given", name="a logged in user")

    reporter.pytest_bdd_before_step(request=None, feature=None, scenario=None,
                                    step=step, step_func=None)
    reporter.pytest_bdd_after_step(request=None, feature=None, scenario=None,
                                   step=step, step_func=None,
                                   step_func_args={"user": "amy"})

    recorded, = take_steps()
    assert recorded["title"] == "Given a logged in user"
    assert recorded["kind"] == "given"
    assert recorded["status"] == "PASS"
    assert recorded["params"] == [["user", "amy"]]


def test_a_step_that_raised_is_closed_with_why(tmp_path):
    """pytest-bdd never calls after_step for a failure, so this is its close."""
    reporter = _reporter(tmp_path)
    step = _Named(keyword="When", name="the payment is declined")

    reporter.pytest_bdd_before_step(request=None, feature=None, scenario=None,
                                    step=step, step_func=None)
    reporter.pytest_bdd_step_error(
        request=None, feature=None, scenario=None, step=step, step_func=None,
        step_func_args={}, exception=AssertionError("card declined"))

    recorded, = take_steps()
    assert recorded["status"] == "FAIL"
    assert "card declined" in recorded["error"]


def test_a_step_the_suite_never_implemented_is_named_rather_than_skipped(tmp_path):
    """Nothing opened it, so the tab only names that line if this does both."""
    reporter = _reporter(tmp_path)

    reporter.pytest_bdd_step_func_lookup_error(
        request=None, feature=None, scenario=None,
        step=_Named(keyword="Then", name="the cart is emailed"),
        exception=Exception("StepDefinitionNotFoundError"))

    recorded, = take_steps()
    assert recorded["title"] == "Then the cart is emailed"
    assert recorded["status"] == "FAIL"


# ----------------------------------------------------- collect_attachments ---

def test_the_attachments_a_test_handed_over_are_collected(tmp_path):
    reporter = _reporter(tmp_path, report_attachments="all")
    attach_text("the response body", name="Body")

    collected = reporter.collect_attachments("PASS")

    assert len(collected) == 1
    assert collected[0]["title"] == "Body"


def test_none_mode_keeps_nothing_but_still_drains_the_buffer(tmp_path):
    """An attachment left behind is reported as the next test's own - the bug
    screenshots had before every record started claiming the pending image."""
    reporter = _reporter(tmp_path, report_attachments="none")
    attach_text("the response body", name="Body")

    assert reporter.collect_attachments("FAIL") == []
    assert take_attachments() == []


def test_failed_mode_keeps_nothing_from_a_test_that_passed(tmp_path):
    reporter = _reporter(tmp_path, report_attachments="failed")
    attach_text("the response body", name="Body")

    assert reporter.collect_attachments("PASS") == []
    assert take_attachments() == []


@pytest.mark.parametrize("status", ["FAIL", "ERROR"])
def test_failed_mode_keeps_what_a_failure_attached(tmp_path, status):
    reporter = _reporter(tmp_path, report_attachments="failed")
    attach_text("the response body", name="Body")

    assert len(reporter.collect_attachments(status)) == 1


def test_a_payload_is_trimmed_to_the_limit(tmp_path):
    reporter = _reporter(tmp_path, report_attachments="all",
                         report_attachment_limit=20)
    attach_text("x" * 500, name="Body")

    collected = reporter.collect_attachments("PASS")

    assert len(collected[0]["parts"][0]["text"]) <= 500


def test_a_test_that_attached_nothing_collects_nothing(tmp_path):
    assert _reporter(tmp_path, report_attachments="all").collect_attachments("PASS") == []


# ------------------------------------------------------- write_junit_report ---

def test_the_junit_document_is_written_where_it_was_asked_for(tmp_path):
    reporter = _reporter(tmp_path, report_junit=str(tmp_path / "results.xml"))
    reporter._records = [{
        "nodeid": "tests/test_cart.py::test_add", "suite_name": "tests/test_cart.py",
        "test_name": "test_add", "status": "PASS", "message": "", "duration": 0.01,
        "rerun": 0, "index": 0, "worker": "", "screenshots": [], "logs": [],
        "attachments": [], "steps": [], "phases": {},
    }]

    written = reporter.write_junit_report(1.0)

    assert written
    assert (tmp_path / "results.xml").exists()
    assert "test_add" in (tmp_path / "results.xml").read_text()


def test_a_path_that_cannot_be_written_costs_the_xml_and_nothing_else(tmp_path, capsys):
    """A raise here would cost the run its html report, its output.json and
    its archived build as well as its xml - over a mistyped path."""
    occupied = tmp_path / "results.xml"
    occupied.mkdir()

    reporter = _reporter(tmp_path, report_junit=str(occupied))
    reporter._records = []

    assert reporter.write_junit_report(1.0) is None
    assert "could not write" in capsys.readouterr().err


def test_a_run_that_asked_for_no_xml_writes_none(tmp_path):
    reporter = _reporter(tmp_path)
    reporter._records = []

    assert reporter.write_junit_report(1.0) is None
