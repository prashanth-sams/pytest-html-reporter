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
- [x] Attachments #api-json-text

### Pytest Runner

| Type                  | Command               |
| --------------        | ---------             |
| generic run           | `pytest -v -s test_yield_fixture.py` |
| Run specific test case| `pytest -v -s test_yield_fixture.py::test_fail` |
| Run tagged tests      | `pytest -v -s test_mark.py -m 'slow'` |

### Attachments

`test_attachments.py` fills the `Attachments` tab. It needs no browser and no network -
its HTTP client is a stub shaped like a `requests` response - so it is the quickest way
to see what the tab does:

```
pytest tests/functional/test_attachments.py --html-report=./report
```

Two of its tests fail on purpose, and it shows every helper: `attach_api` from a response
object and from arguments alone, `attach_json`, `attach_text`, `attach_file`, and the
attach-the-last-call-on-failure fixture. It also carries a fake bearer token, an
`?api_key=` and a password in a payload, none of which reach the report.

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
