import pytest


@pytest.fixture
def mock_data():
    name = 'Jesus'
    profession = 'Saving world'
    history = 'Created everything we know and what we see, you and me'
    return [name, profession, history]


def test_fixture_pass(mock_data):
    assert mock_data[0] == 'Jesus'


def test_fixture_fail(mock_data):
    assert mock_data[1] == 'Jesus'
