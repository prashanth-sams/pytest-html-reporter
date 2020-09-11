import pytest


@pytest.mark.slow
def test_fixture_pass():
    assert 5 == 5