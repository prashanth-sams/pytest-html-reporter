import pytest


@pytest.yield_fixture()
def setup():
    yield


def test_pass(setup):
    assert True


def test_fail(setup):
    assert False
