"""Cover what a step records, and what it does when the test misbehaves.

The buffer is module state, so every test here drains it first: a step left
behind by the test above would be counted as this one's, which is the exact bug
the drain exists to prevent.
"""

import threading
import time

import pytest

from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.steps import (
    DEPTH_MAX,
    open_step,
    set_phase,
    start,
    step,
    stop,
    take_steps,
)


@pytest.fixture(autouse=True)
def drained():
    take_steps()
    ConfigVars._step_limit = 500
    set_phase('call')
    yield
    take_steps()
    ConfigVars._step_limit = 500


def titles(steps):
    return [entry['title'] for entry in steps]


def test_a_with_block_records_one_step():
    with step("Add to cart"):
        pass

    steps = take_steps()

    assert titles(steps) == ["Add to cart"]
    assert steps[0]['status'] == 'PASS'
    assert steps[0]['depth'] == 0


def test_steps_nest_by_being_called_from_inside_one_another():
    with step("Check out"):
        with step("Charge the card"):
            with step("Authorise"):
                pass

    assert [entry['depth'] for entry in take_steps()] == [0, 1, 2]


def test_a_step_is_recorded_where_it_started_not_where_it_finished():
    # Pre-order, so the tree reads down the page in the order it happened. A
    # buffer appended to on close would put every parent after its children.
    with step("Outer"):
        with step("First"):
            pass
        with step("Second"):
            pass

    assert titles(take_steps()) == ["Outer", "First", "Second"]


def test_a_step_is_timed():
    with step("Slow"):
        time.sleep(0.03)

    assert take_steps()[0]['ms'] >= 25


def test_the_decorator_fills_its_title_from_the_call():
    @step("Log in as {user}")
    def login(user):
        pass

    login("amy")

    steps = take_steps()

    assert titles(steps) == ["Log in as amy"]
    assert ['user', 'amy'] in steps[0]['params']


def test_a_title_naming_something_the_call_did_not_pass_keeps_its_braces():
    # Better a title with a brace in it than a step that loses its name, and
    # far better than a KeyError raised out of a reporting call.
    @step("Log in as {missing}")
    def login(user):
        pass

    login("amy")

    assert titles(take_steps()) == ["Log in as {missing}"]


def test_the_decorator_returns_what_the_function_returned():
    @step("Add")
    def add(a, b):
        return a + b

    assert add(2, 3) == 5


def test_a_step_that_raises_is_recorded_and_the_exception_carries_on():
    with pytest.raises(ValueError):
        with step("Charge the card"):
            raise ValueError("declined")

    steps = take_steps()

    assert steps[0]['status'] == 'FAIL'
    assert steps[0]['error'] == "ValueError: declined"


def test_the_message_goes_on_the_step_that_raised_not_on_its_ancestors():
    # One exception walking out through three steps used to print the same
    # traceback three times, with the innermost - the only one that says where
    # - furthest down the page.
    with pytest.raises(ValueError):
        with step("Outer"):
            with step("Middle"):
                with step("Inner"):
                    raise ValueError("declined")

    steps = take_steps()

    assert [entry['status'] for entry in steps] == ['FAIL', 'FAIL', 'FAIL']
    assert [entry['error'] for entry in steps] == ['', '', "ValueError: declined"]


def test_two_steps_that_each_raised_both_keep_their_message():
    for _ in range(2):
        with pytest.raises(ValueError):
            with step("Attempt"):
                raise ValueError("boom")

    assert [entry['error'] for entry in take_steps()] == ["ValueError: boom"] * 2


def test_a_caught_failure_leaves_the_step_that_caught_it_passing():
    with step("Retry until it works"):
        try:
            with step("First attempt"):
                raise ValueError("declined")
        except ValueError:
            pass

    assert [entry['status'] for entry in take_steps()] == ['PASS', 'FAIL']


def test_a_skip_inside_a_step_is_not_a_failure_of_that_step():
    with pytest.raises(BaseException):
        with step("Needs a browser"):
            pytest.skip("no browser here")

    assert take_steps()[0]['status'] == 'SKIP'


def test_a_step_that_was_never_closed_is_closed_at_the_drain():
    # The test died inside the block. A step that simply stops being mentioned
    # reads as a step that never ran.
    opened = step("Never closed")
    opened.__enter__()

    steps = take_steps()

    assert titles(steps) == ["Never closed"]
    assert steps[0]['status'] == 'FAIL'


def test_the_buffer_is_not_handed_to_the_next_test():
    with step("Mine"):
        pass

    take_steps()

    assert take_steps() == []


def test_steps_are_filed_under_the_phase_that_was_running():
    set_phase('setup')
    with step("Build a cart"):
        pass

    set_phase('call')
    with step("Buy something"):
        pass

    set_phase('teardown')
    with step("Empty the cart"):
        pass

    assert [entry['phase'] for entry in take_steps()] == ['setup', 'call', 'teardown']


def test_a_fixture_holding_a_step_open_does_not_swallow_the_test():
    # A yield fixture's `with step(...)` stays open across the whole test, so
    # counting depth from the stack alone reported every step the test ran as a
    # step *of the fixture*.
    set_phase('setup')
    held = step("Build a cart")
    held.__enter__()

    set_phase('call')
    with step("Buy something"):
        pass

    assert [entry['depth'] for entry in take_steps()] == [0, 0]


def test_nesting_stops_being_drawn_past_the_depth_limit():
    blocks = [step("Deep %d" % index) for index in range(DEPTH_MAX + 4)]
    for block in blocks:
        block.__enter__()
    for block in reversed(blocks):
        block.__exit__(None, None, None)

    assert max(entry['depth'] for entry in take_steps()) == DEPTH_MAX


def test_the_limit_caps_what_one_test_can_record():
    ConfigVars._step_limit = 4

    for index in range(30):
        with step("s%d" % index):
            pass

    steps = take_steps()

    # The cap, plus one line saying the rest were dropped - silence would read
    # as a test that stopped there.
    assert len(steps) == 5
    assert 'more steps not recorded' in steps[-1]['title']


def test_the_limit_can_be_lifted():
    ConfigVars._step_limit = 0

    for index in range(60):
        with step("s%d" % index):
            pass

    assert len(take_steps()) == 60


def test_a_capped_step_still_nests_the_ones_that_follow_it():
    ConfigVars._step_limit = 2

    with step("kept"):
        with step("also kept - this is the notice"):
            with step("dropped"):
                pass

    # Nothing raised, and the stack came back balanced, which is the property
    # that matters: the cap must not corrupt the tree it stops recording.
    assert open_step() is None


def test_the_open_step_is_the_innermost_one():
    assert open_step() is None

    with step("Outer"):
        assert open_step()['title'] == "Outer"

        with step("Inner"):
            assert open_step()['title'] == "Inner"

        assert open_step()['title'] == "Outer"

    assert open_step() is None


def test_every_step_gets_an_id_of_its_own():
    with step("a"):
        with step("b"):
            pass
    with step("c"):
        pass

    ids = [entry['id'] for entry in take_steps()]

    assert ids == sorted(set(ids))


def test_a_background_thread_nests_within_itself():
    # One stack shared by every thread came back nested in whatever order the
    # threads interleaved - a tree that never existed.
    def work(index):
        with step("thread %d outer" % index):
            with step("thread %d inner" % index):
                time.sleep(0.01)

    threads = [threading.Thread(target=work, args=(index,)) for index in range(5)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()

    steps = take_steps()
    ids = [entry['id'] for entry in steps]

    assert len(ids) == len(set(ids)) == 10
    assert sorted(set(entry['depth'] for entry in steps)) == [0, 1]


def test_a_value_that_cannot_be_repred_does_not_take_the_run_down():
    class Awkward:
        def __repr__(self):
            raise RuntimeError("no")

    with step("Odd", thing=Awkward()):
        pass

    assert take_steps()[0]['params'] == [['thing', '<unrepresentable>']]


def test_start_and_stop_can_be_driven_directly():
    # What the pytest-bdd hooks use: the step opens in one hook and closes in
    # another, so there is no block to hold it.
    start("Given a logged in user", kind='given')
    stop(params=[('user', 'amy')])

    steps = take_steps()

    assert steps[0]['kind'] == 'given'
    assert steps[0]['params'] == [['user', 'amy']]


def test_stopping_when_nothing_is_open_is_not_an_error():
    stop()

    assert take_steps() == []
