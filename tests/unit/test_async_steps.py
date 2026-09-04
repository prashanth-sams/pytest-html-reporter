"""Cover what a step does in an ``async`` test.

asyncio runs every task on the one thread, so the per-thread stack that keeps
threads from trampling each other did nothing at all for coroutines: three
gathered legs pushed onto the same stack and came back nested three deep inside
one another - a tree that never existed - and an attachment made in one of them
was filed under whichever sibling happened to be open. Worse, ``@step`` on an
``async def`` closed the step on the *building* of the coroutine, so a call
that went on to raise was reported green. Every test here is the shape of one
of those.

No pytest-asyncio: the loop is driven with ``asyncio.run`` from ordinary sync
tests, so this file adds nothing to the two dependencies the plugin has.
"""

import asyncio
import concurrent.futures
import functools

import pytest

from pytest_html_reporter.const_vars import ConfigVars
from pytest_html_reporter.steps import (
    open_step,
    set_phase,
    start,
    step,
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


def shape(steps):
    return [(entry['title'], entry['depth'], entry['status']) for entry in steps]


# ================================================== async with ==============

def test_an_async_with_block_records_one_step():
    async def body():
        async with step("Add to cart", sku="A-12"):
            await asyncio.sleep(0)

    asyncio.run(body())

    recorded, = take_steps()

    assert recorded['title'] == "Add to cart"
    assert recorded['status'] == 'PASS'
    assert recorded['params'] == [['sku', 'A-12']]


def test_an_async_with_block_is_held_open_across_what_it_awaits():
    async def body():
        async with step("Charge the card"):
            await asyncio.sleep(0.03)

    asyncio.run(body())

    assert take_steps()[0]['ms'] >= 25


def test_an_async_with_block_hands_back_the_step_it_opened():
    async def body():
        async with step("Check out") as opened:
            assert opened.title == "Check out"
            assert open_step()['title'] == "Check out"

    asyncio.run(body())


def test_a_sync_block_and_an_async_one_nest_in_one_another():
    async def body():
        with step("Outer"):
            async with step("Inner"):
                await asyncio.sleep(0)

    asyncio.run(body())

    assert shape(take_steps()) == [("Outer", 0, 'PASS'), ("Inner", 1, 'PASS')]


def test_the_message_goes_on_the_async_step_that_raised():
    async def body():
        async with step("Check out"):
            async with step("Charge the card"):
                raise ValueError("declined")

    with pytest.raises(ValueError):
        asyncio.run(body())

    recorded = take_steps()

    assert [entry['status'] for entry in recorded] == ['FAIL', 'FAIL']
    assert [entry['error'] for entry in recorded] == ['', "ValueError: declined"]


# ================================================== the decorator ===========

def test_a_decorated_coroutine_is_timed_across_the_call():
    # Calling an `async def` only builds a coroutine. The plain wrapper closed
    # the step on that - nought milliseconds - before any of the work ran.
    @step("Send the notification")
    async def notify():
        await asyncio.sleep(0.03)

    asyncio.run(notify())

    assert take_steps()[0]['ms'] >= 25


def test_a_decorated_coroutine_still_returns_what_it_returned():
    @step("Fetch the order")
    async def fetch():
        await asyncio.sleep(0)

        return "order-1"

    assert asyncio.run(fetch()) == "order-1"


def test_a_decorated_coroutines_own_arguments_fill_in_its_title():
    @step("Log in as {user}")
    async def login(user):
        await asyncio.sleep(0)

    asyncio.run(login("amy"))

    recorded, = take_steps()

    assert recorded['title'] == "Log in as amy"
    assert recorded['params'] == [['user', 'amy']]


def test_a_coroutine_that_raises_is_failed_and_the_exception_carries_on_out():
    # The one that mattered. The step was closed before the coroutine ran, so
    # a call that went on to raise was recorded PASS with no message at all.
    @step("Charge the card")
    async def charge():
        await asyncio.sleep(0)

        raise ValueError("declined")

    with pytest.raises(ValueError):
        asyncio.run(charge())

    recorded, = take_steps()

    assert recorded['status'] == 'FAIL'
    assert recorded['error'] == "ValueError: declined"


def test_an_async_function_behind_another_decorator_is_still_found():
    # iscoroutinefunction does not look through functools.wraps, so a retry or
    # a rate limiter stacked above this one leaves a plain function with the
    # `async def` behind it - and not seeing it is what reports the step green.
    def retry(function):
        @functools.wraps(function)
        def wrapper(*args, **kwargs):
            return function(*args, **kwargs)

        return wrapper

    @step("Publish")
    @retry
    async def publish():
        await asyncio.sleep(0.03)

        raise RuntimeError("nope")

    with pytest.raises(RuntimeError):
        asyncio.run(publish())

    recorded, = take_steps()

    assert recorded['status'] == 'FAIL'
    assert recorded['ms'] >= 25


def test_a_wrapped_chain_pointed_back_at_itself_does_not_hang():
    def loopy():
        return "ok"

    loopy.__wrapped__ = loopy

    assert step("Round and round")(loopy)() == "ok"
    assert take_steps()[0]['title'] == "Round and round"


def test_an_async_generator_is_not_mistaken_for_a_coroutine():
    # Calling one hands back an async generator, which is not awaitable - the
    # async wrapper would await it and fail. It stays on the plain path, where
    # it behaves exactly as it did before any of this.
    @step("Stream the rows")
    async def rows():
        yield 1
        yield 2

    async def body():
        return [value async for value in rows()]

    assert asyncio.run(body()) == [1, 2]
    assert take_steps()[0]['title'] == "Stream the rows"


# ================================================== concurrency =============

def test_gathered_legs_are_siblings_and_not_a_chain():
    async def leg(name, delay):
        async with step(name):
            await asyncio.sleep(delay)

    async def body():
        await asyncio.gather(leg("Leg A", 0.03), leg("Leg B", 0.02), leg("Leg C", 0.01))

    asyncio.run(body())

    assert sorted(shape(take_steps())) == [("Leg A", 0, 'PASS'),
                                           ("Leg B", 0, 'PASS'),
                                           ("Leg C", 0, 'PASS')]


def test_gathered_legs_still_nest_under_the_step_that_fanned_them_out():
    # A task starts from a copy of the context that created it, so the step
    # that was open when it was started is still the step it belongs to.
    async def leg(name):
        async with step(name):
            await asyncio.sleep(0)

    async def body():
        async with step("Fan out"):
            await asyncio.gather(leg("Leg A"), leg("Leg B"))

    asyncio.run(body())

    assert sorted(shape(take_steps())) == [("Fan out", 0, 'PASS'),
                                           ("Leg A", 1, 'PASS'),
                                           ("Leg B", 1, 'PASS')]


def test_a_plain_await_nests_the_way_a_plain_call_does():
    # Nothing creates a task, so the step opened inside is a step of the one
    # that awaited it - which is the whole of how steps nest.
    async def inner():
        async with step("Inner"):
            await asyncio.sleep(0)

    async def body():
        async with step("Outer"):
            await inner()

    asyncio.run(body())

    assert shape(take_steps()) == [("Outer", 0, 'PASS'), ("Inner", 1, 'PASS')]


def test_an_attachment_made_in_one_leg_is_filed_under_that_leg():
    # `open_step` is what attach_json and the screenshot capture ask. Off one
    # shared stack it answered with whichever sibling happened to be open, so
    # a picture taken in Leg B arrived on Leg C.
    filed = {}

    async def leg(name, delay):
        async with step(name):
            await asyncio.sleep(delay)
            filed[name] = open_step()['title']

    async def body():
        await asyncio.gather(leg("Leg A", 0.03), leg("Leg B", 0.01), leg("Leg C", 0.02))

    asyncio.run(body())
    take_steps()

    assert filed == {"Leg A": "Leg A", "Leg B": "Leg B", "Leg C": "Leg C"}


def test_one_step_object_entered_twice_at_once_closes_both():
    # `with step(...)` builds one per block, but nothing stops a caller keeping
    # one and reusing it, and neither entry may be left open behind the other.
    shared = step("Shared")

    async def leg(delay):
        async with shared:
            await asyncio.sleep(delay)

    async def body():
        await asyncio.gather(leg(0.02), leg(0.01))

    asyncio.run(body())

    recorded = take_steps()

    assert len(recorded) == 2
    assert [entry['status'] for entry in recorded] == ['PASS', 'PASS']


# ================================================== the awkward ends ========

def test_a_step_held_open_across_a_yield_closes_where_the_fixture_resumes():
    # pytest-asyncio drives an async generator fixture with one run_until_complete
    # per half, and each of those is a task with a context of its own - so the
    # block is entered in one and left in another. It is closed on the frame it
    # is holding rather than off a stack that never saw it, because a fixture
    # that worked perfectly must not be reported as the place the test died.
    async def fixture():
        with step("Open a session"):
            yield "session"

    generator = fixture()
    loop = asyncio.new_event_loop()

    try:
        loop.run_until_complete(generator.__anext__())
        loop.run_until_complete(asyncio.sleep(0))

        with pytest.raises(StopAsyncIteration):
            loop.run_until_complete(generator.__anext__())
    finally:
        loop.close()

    assert shape(take_steps()) == [("Open a session", 0, 'PASS')]


def test_a_cancelled_tasks_open_step_is_closed_rather_than_left_behind():
    # Its context is gone, so nothing can reach the stack it was open on - and
    # a step that just stops being mentioned reads as a step that never ran.
    async def leg():
        async with step("Waiting on the queue"):
            await asyncio.sleep(30)

    async def body():
        task = asyncio.ensure_future(leg())
        await asyncio.sleep(0.01)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(body())

    assert take_steps()[0]['status'] == 'FAIL'


def test_a_thread_that_leaked_a_step_does_not_indent_the_next_test():
    # A pooled thread is handed to the next test still holding whatever it was
    # left with, and counting depth off that stack indented the first step of
    # the next test underneath one that had already been taken and rendered.
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)

    def clean(index):
        with step("after %d" % index):
            pass

    try:
        list(pool.map(lambda index: start("Leaked %d" % index), range(4)))

        assert [entry['status'] for entry in take_steps()] == ['FAIL'] * 4

        list(pool.map(clean, range(4)))

        assert set(entry['depth'] for entry in take_steps()) == {0}
    finally:
        pool.shutdown()
