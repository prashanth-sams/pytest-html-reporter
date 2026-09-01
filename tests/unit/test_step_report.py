"""Cover what a step looks like once it is on the page.

The module tests pin down what a step holds. What matters here is the trip
through a real run: that it lands on the test that ran it, that a payload
cannot be turned into markup or into a template placeholder on the way, and
that the tab still says something useful about a suite that never named one.
"""

import os
import re
import subprocess
import sys
import textwrap

import pytest


SUITE = '''
    import time
    import pytest
    from pytest_html_reporter import attach_json, step

    pytestmark = pytest.mark.suite("checkout")

    @pytest.fixture
    def cart():
        with step("Start a session"):
            time.sleep(0.01)
        yield {"items": []}
        with step("Close the session"):
            pass

    @step("Log in as {user}")
    def login(user):
        with step("Submit credentials"):
            attach_json({"user": user}, name="Credentials")

    @pytest.mark.slow
    @pytest.mark.parametrize("sku", ["A-12"])
    def test_buys_an_item(cart, sku):
        """Buys one item."""
        login("amy")
        with step("Add to the cart", sku=sku):
            cart["items"].append(sku)

    def test_fails_deep_in_a_step():
        with step("Check out"):
            with step("Charge the card"):
                raise AssertionError("card declined")

    def test_names_no_steps():
        assert True
'''


def _run(tmp_path, body=SUITE, *args):
    """Run a generated suite and hand back the report page it wrote."""
    (tmp_path / "test_steps_ran.py").write_text(textwrap.dedent(body))

    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--html-report=./report", "-p", "no:cacheprovider"]
        + list(args),
        cwd=str(tmp_path), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        universal_newlines=True,
    )

    report = tmp_path / "report" / "pytest_html_report.html"
    assert report.is_file(), result.stdout

    return report.read_text(encoding="utf-8")


def _payload(page, test_name):
    """The step tree parked in the store for one test."""
    match = re.search(
        r'<div class="step-payload"[^>]*data-test="%s"[^>]*>(.*?)'
        r'(?=<div class="step-payload"|</div>\s*</div>\s*</div>\s*</div>)'
        % re.escape(test_name), page, re.S)

    return match.group(1) if match else ""


def _lines(payload):
    """(status, title) for every step drawn, in page order."""
    return [(status, re.sub(r"<[^>]+>", "", title).strip())
            for status, title in re.findall(
                r'class="step-line step-line--(\w+)".*?class="step-line__title">(.*?)</span>',
                payload, re.S)]


def test_every_step_reaches_the_tab(tmp_path):
    page = _run(tmp_path)

    assert [title for _status, title in _lines(_payload(page, "test_buys_an_item[A-12]"))] == [
        "Start a session",
        "Log in as amy",
        "Submit credentials",
        "Add to the cart",
        "Close the session",
    ]


def test_a_step_is_filed_under_the_phase_that_ran_it(tmp_path):
    payload = _payload(_run(tmp_path), "test_buys_an_item[A-12]")

    setup = re.search(r'data-phase="setup".*?data-phase="call"', payload, re.S).group(0)
    teardown = payload[payload.index('data-phase="teardown"'):]

    assert "Start a session" in setup
    assert "Close the session" in teardown


def test_every_test_gets_all_three_phases_even_with_no_steps(tmp_path):
    # The tab is never useless: a suite that named nothing still gets a tree
    # saying where its time went.
    payload = _payload(_run(tmp_path), "test_names_no_steps")

    assert re.findall(r'data-phase="(\w+)"', payload) == ["setup", "call", "teardown"]
    assert "No steps named here" in payload


def test_a_failing_step_carries_the_message(tmp_path):
    payload = _payload(_run(tmp_path), "test_fails_deep_in_a_step")

    assert _lines(payload) == [("FAIL", "Check out"), ("FAIL", "Charge the card")]
    assert payload.count("card declined") == 1


def test_the_message_is_not_repeated_up_the_tree(tmp_path):
    # One exception walking out through two steps printed the same traceback
    # twice, with the innermost - the only one that says where - underneath.
    payload = _payload(_run(tmp_path), "test_fails_deep_in_a_step")
    errors = re.findall(r'class="step-line__error">(.*?)</pre>', payload, re.S)

    assert len(errors) == 1


def test_a_step_keeps_what_it_was_called_with(tmp_path):
    payload = _payload(_run(tmp_path), "test_buys_an_item[A-12]")

    assert "sku=A-12" in payload


def test_an_attachment_is_filed_under_the_step_that_made_it(tmp_path):
    payload = _payload(_run(tmp_path), "test_buys_an_item[A-12]")

    submit = payload[payload.index("Submit credentials"):]

    assert "step-line__attach" in submit[:400]


def test_the_markers_reach_the_tab(tmp_path):
    payload = _payload(_run(tmp_path), "test_buys_an_item[A-12]")

    assert "slow" in payload
    assert "suite(checkout)" in payload
    assert "parametrize(sku)" in payload


def test_the_row_counts_what_it_can_open(tmp_path):
    page = _run(tmp_path)

    counts = re.findall(r'onclick="showStepsFor\(\'[\d-]+\'\)"[^>]*>\s*<i[^>]*></i>(\d+)', page)

    assert sorted(counts) == ["0", "2", "5"]


def test_a_payload_is_escaped_rather_than_rendered(tmp_path):
    page = _run(tmp_path, '''
        from pytest_html_reporter import step

        def test_one():
            with step("<script>alert(1)</script>"):
                pass
    ''')

    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page


def test_a_step_title_cannot_become_a_template_placeholder(tmp_path):
    page = _run(tmp_path, '''
        from pytest_html_reporter import step

        def test_one():
            with step("%(step_store)% and $(vendor_assets)$"):
                pass
    ''')

    assert "%(step_store)%" not in page.split('id="stepStore"')[0]


def test_a_non_ascii_step_survives_the_write(tmp_path):
    page = _run(tmp_path, '''
        from pytest_html_reporter import step

        def test_one():
            with step("Añadir al carrito \\u2014 \\u00e9\\u00e8"):
                pass
    ''')

    assert "Añadir al carrito" in page


def test_none_mode_keeps_nothing(tmp_path):
    page = _run(tmp_path, SUITE, "--report-steps=none")

    assert _lines(_payload(page, "test_buys_an_item[A-12]")) == []
    # The phases are still there - they are not steps, and they are the half
    # that costs nothing.
    assert 'data-phase="setup"' in page


def test_failed_mode_keeps_only_the_failures(tmp_path):
    page = _run(tmp_path, SUITE, "--report-steps=failed")

    assert _lines(_payload(page, "test_buys_an_item[A-12]")) == []
    assert _lines(_payload(page, "test_fails_deep_in_a_step"))


def test_the_limit_caps_what_one_test_records(tmp_path):
    page = _run(tmp_path, '''
        from pytest_html_reporter import step

        def test_one():
            for index in range(40):
                with step("s%d" % index):
                    pass
    ''', "--report-step-limit=3")

    lines = _lines(_payload(page, "test_one"))

    assert len(lines) == 4
    assert "more steps not recorded" in lines[-1][1]


def test_the_tab_guides_you_when_nothing_named_a_step(tmp_path):
    page = _run(tmp_path, '''
        def test_one():
            assert True
    ''')

    assert "step-page is-bare" in page
    assert "No test named a step in this run" in page


def test_the_guide_goes_away_once_a_step_is_named(tmp_path):
    page = _run(tmp_path)

    assert "step-page is-bare" not in page


def test_steps_survive_an_xdist_run(tmp_path):
    pytest.importorskip("xdist")

    page = _run(tmp_path, SUITE, "-n", "2")

    assert len(_lines(_payload(page, "test_buys_an_item[A-12]"))) == 5
    assert _lines(_payload(page, "test_fails_deep_in_a_step"))


def test_a_retry_reports_the_attempt_that_stuck(tmp_path):
    pytest.importorskip("pytest_rerunfailures")

    page = _run(tmp_path, '''
        from pytest_html_reporter import step

        STATE = {"n": 0}

        def test_flaky():
            STATE["n"] += 1
            with step("Attempt %d" % STATE["n"]):
                assert STATE["n"] > 1
    ''', "--reruns", "2")

    lines = _lines(_payload(page, "test_flaky"))

    # The attempt that passed ran its own steps; showing the failing attempt's
    # tree beside a green test would describe a run that did not happen.
    assert lines == [("PASS", "Attempt 2")]


def test_a_suite_is_named_by_its_file_in_the_rail(tmp_path):
    # The directories repeat down the whole rail. Truncating the path instead
    # put an ellipsis at the front while the rail's own overflow put another at
    # the back, so a long one was clipped at both ends and named nothing.
    page = _run(tmp_path)

    assert re.search(r'class="step-suite__name" title="[^"]*test_steps_ran\.py">test_steps_ran\.py<', page)


def test_the_cheatsheet_can_be_opened_from_the_button(tmp_path):
    # It is written once, in the tab, and the popup is filled from it - so the
    # guide someone reads on an empty run and the one they open from the button
    # cannot drift apart.
    page = _run(tmp_path)

    assert 'onclick="toggleStepHelp(true)"' in page
    assert 'id="stepHelp"' in page
    assert page.count('class="step-guide__sheet"') == 1


def test_the_tab_opens_on_a_failure_that_has_steps(tmp_path):
    # The first row in collection order is almost always a test that named no
    # steps, so the tab used to introduce itself with three empty phases.
    page = _run(tmp_path)

    assert "function stepPickDefault()" in page
    assert "showStep(stepPickDefault())" in page


def test_the_search_matches_a_test_name_typed_with_spaces(tmp_path):
    # A test is named test_fails_deep_in_a_step, and what somebody types is
    # "fails deep". Both spellings are indexed rather than asking people to
    # guess which one the box wants.
    page = _run(tmp_path)

    entry = re.search(r'<button[^>]*class="step-test"[^>]*data-search="([^"]*)"[^>]*>', page)
    searches = re.findall(r'data-search="([^"]*)"', page)

    assert entry is not None
    assert any("fails deep in a step" in text for text in searches)
    assert any("fails_deep_in_a_step" in text for text in searches)


def test_the_summary_counts_the_suites_the_rail_is_showing(tmp_path):
    # Counted off the rail rather than off the run, so the number can never
    # disagree with the list under it once a filter is on.
    page = _run(tmp_path)

    summary = page.split("function renderStepSummary()")[1].split("function ")[0]

    assert "stepSuites()" in summary
    assert "!suite.hidden" in summary
    assert "'suite' : 'suites'" in summary


def test_the_rail_opens_collapsed_with_controls_to_open_it(tmp_path):
    # A run of six hundred tests opened with nine screens of test names. Shut,
    # the first thing the rail shows is the shape of the suite.
    page = _run(tmp_path)

    assert 'onclick="toggleAllStepSuites(true)"' in page
    assert 'onclick="toggleAllStepSuites(false)"' in page
    assert "toggleAllStepSuites(false);" in page.split("function refreshSteps()")[1][:600]


def test_the_selected_test_is_never_hidden_behind_a_shut_suite(tmp_path):
    page = _run(tmp_path)

    assert "function revealStepSuite(sid)" in page
    assert "revealStepSuite(sid);" in page


def _jump_cells(page, kind):
    """Every table cell that crosses into the tree, by what it points at."""
    return re.findall(r'data-jump="%s" data-target="([^"]*)"' % kind, page)


def test_a_test_name_in_the_table_crosses_to_its_own_entry(tmp_path):
    # The name and the Steps icon at the end of the row answer the same
    # question, so both cross - and to the same id, or one of them lands on
    # somebody else's tree.
    page = _run(tmp_path)

    targets = _jump_cells(page, "test")
    buttons = re.findall(r"onclick=\"showStepsFor\('([\d-]+)'\)\"", page)

    assert targets
    assert targets == buttons
    for sid in targets:
        assert 'id="step-test-%s"' % sid in page


def test_a_suite_name_in_the_table_crosses_to_its_own_group(tmp_path):
    # Both tables name the suite, and the id they point at has to be the one
    # the rail gave that group.
    page = _run(tmp_path)

    targets = _jump_cells(page, "suite")
    rail = re.findall(r'<div class="step-suite" id="step-suite-([^"]*)"', page)

    assert rail
    assert set(targets) == set(rail)
    # Once per test row plus once on the Test Suites table.
    assert len(targets) == len(_jump_cells(page, "test")) + len(rail)


def test_crossing_to_a_suite_opens_that_group_and_shuts_the_rest(tmp_path):
    # A rail a hundred names long buries the group that was asked for if the
    # others are left open beside it.
    page = _run(tmp_path)

    body = page.split("function showStepsForSuite(sindex)")[1].split("\n            function ")[0]

    assert "isolateStepSuite(suite);" in body
    assert "other.classList.toggle('is-shut', other !== suite);" in page
    # The pane cannot be left showing a test that belongs to a suite the
    # crossing has just shut.
    assert "stepPickFrom(inside)" in body
