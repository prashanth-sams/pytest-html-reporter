import pytest


@pytest.mark.parametrize('a, b', [(1, 1), (1, 2)])
def test_fixture_pass(a, b):
    assert a == b