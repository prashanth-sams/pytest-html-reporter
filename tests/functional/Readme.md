# pytest bank
> pytest exercises

### Feature
- [x] Basic
- [x] Fixture #mock-data
- [x] UseFixture #background-teardown
- [x] Autouse
- [x] Mark #Tags
- [x] Parameterize #data-driven
- [x] Yield #hooks
- [x] Skip tests

### Pytest Runner

| Type                  | Command               |
| --------------        | ---------             |
| generic run           | `pytest -v -s pytest/test_yield_fixture.py` |
| Run specific test case| `pytest -v -s pytest/test_yield_fixture.py::test_fail` |
| Run tagged tests      | `pytest -v -s pytest/test_mark.py -m 'slow'` |
