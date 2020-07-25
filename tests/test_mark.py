import pytest


@pytest.mark.slow
def test_fixture_pass():
    assert 5 == 5


@pytest.mark.fast
def test_fixture_fail():
    assert 5 == 6

@pytest.mark.fast
def test_fixture_failx2():
    assert 5 == 6

@pytest.mark.fast
def test_fixture_failx3():
    assert 5 == 6
