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
- [x] Traceability #owner-jira-testcase

### Pytest Runner

| Type                  | Command               |
| --------------        | ---------             |
| generic run           | `pytest -v -s test_yield_fixture.py` |
| Run specific test case| `pytest -v -s test_yield_fixture.py::test_fail` |
| Run tagged tests      | `pytest -v -s test_mark.py -m 'slow'` |

### Attachments

`test_attachments.py` fills the `API Logs` tab. It needs no browser and no network -
its HTTP client is a stub shaped like a `requests` response - so it is the quickest way
to see what the tab does:

```
pytest tests/functional/test_attachments.py --html-report=./report
```

Two of its tests fail on purpose, and it shows every helper: `attach_api` from a response
object and from arguments alone, `attach_json`, `attach_text`, `attach_file`, and the
attach-the-last-call-on-failure fixture. It also carries a fake bearer token, an
`?api_key=` and a password in a payload, none of which reach the report.

### Traceability

`test_traceability.py` fills the `Owner`, `Jira` and `Testcase` rows on the Test Steps
tab, and the `Owner` pills above the rail:

```
pytest tests/functional/test_traceability.py --html-report=./report
```

The ids become links because the repository's `pytest.ini` says what they mean:

```ini
report_link_pattern =
    jira = https://acme.atlassian.net/browse/{}
    testcase = https://acme.testrail.io/index.php?/cases/view/{}
```

`{}` is where the marker's argument goes. The hosts are made up and nothing is fetched,
so the badges render whether or not those sites exist - which is the point of a url
template over an api client.

It covers every branch worth seeing: an owner written once for the whole file with
`pytestmark`, a second owner on top of it, two Jira ids on one test, a `testcase` in a
different tracker, and a bare `@pytest.mark.jira` with nothing in its brackets, which
stays a plain badge rather than linking to the tracker's front page.

Two tests fail on purpose - they are what puts a red row in the **Who owns what** table
on `Analytics`. That table needs more than one build before it has anything to say, so
run it two or three times. There is no unowned test in the file and there cannot be:
`pytestmark` reaches every test in the module. Run the whole folder to see the `Unowned`
pill, since no other file here mentions an owner:

```
pytest tests/functional/ --html-report=./report
```

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
