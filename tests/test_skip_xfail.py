import pytest


@pytest.mark.skip
def test_skip():
    assert 5 == 5


@pytest.mark.xfail
def test_xfail():
    assert 5 == 3


@pytest.mark.xfail
def test_xpass():
    pass
