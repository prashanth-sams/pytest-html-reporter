import pytest


class DB:

    def __init__(self):
        self.data = []

    def begin(self, test_name):
        self.data.append(test_name)

    def rollback(self):
        self.data.pop()


@pytest.fixture(scope='module')
def db():
    return DB()


class TestDB:

    @pytest.fixture(autouse=True)
    def transact(self, request, db):
        db.begin(request.function.__name__)
        yield
        db.rollback()

    def test_dbx1(self, db):
        assert db.data == ['test_dbx1']

    def test_dbx2(self, db):
        assert db.data == ['test_dbx2']