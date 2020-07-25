import pytest


@pytest.mark.slow
def test_fixture_pass():
    assert 5 == 5


@pytest.mark.fast
def test_fixture_fail():
    assert 5 == 6