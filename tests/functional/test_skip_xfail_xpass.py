import pytest


def test_skip():
    pytest.skip("skip this test")


@pytest.mark.xfail
def test_xfail():
    assert 5 == 3


@pytest.mark.xfail
def test_xpass():
    pass
