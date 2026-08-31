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
| generic run           | `pytest -v -s test_yield_fixture.py` |
| Run specific test case| `pytest -v -s test_yield_fixture.py::test_fail` |
| Run tagged tests      | `pytest -v -s test_mark.py -m 'slow'` |

### Browser tests

`test_selenium.py`, `test_screenshot.py` and `test_playwright.py` drive a real browser
to exercise screenshot-on-failure. They are run by hand, so their dependencies are kept
out of `requirements.txt` and each file skips itself when its driver is missing:

| Test                                       | Install                                                 |
| ------------------------------------------ | ------------------------------------------------------- |
| `test_selenium.py`, `test_screenshot.py`   | `pip install selenium` (plus a local Chrome)            |
| `test_playwright.py`                       | `pip install pytest-playwright && playwright install chromium` |

Each file has one test that fails on purpose - that is the one that puts a screenshot
in the report.
