import pytest

"""
# can be used globally as well
# content of pytest.ini
[pytest]
usefixtures = cleandir
"""
@pytest.fixture
def cleandir():
    print('before executing test')
    yield
    print('after executing test')


@pytest.mark.usefixtures('cleandir')
class TestClass:

    def test_fixture_pass(self):
        print('executing tests x1')
        pass


    def test_fixture_fail(self):
        print('executing tests x2')
        pass
