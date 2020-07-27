# pytest-html-reporter
[![PyPI version](https://badge.fury.io/py/pytest-html-reporter.svg)](https://badge.fury.io/py/pytest-html-reporter)
[![Build Status](https://travis-ci.com/prashanth-sams/pytest-html-reporter.svg?branch=master)](https://travis-ci.com/prashanth-sams/pytest-html-reporter)

> Generates a static html report based on `pytest` framework

<div align="center"><img src="./PHR.png" width="200"/></div>

### Installation

```
pip3 install pytest-html-reporter
```

Or install it by adding this line in your project's `requirements.txt` file:

```
pytest-html-reporter
```

And then execute:
```
pip3 install -r requirements.txt
```

## #Usage outline

- Add `--html` tag followed by path location in the command line:
    ```
    pytest tests/ --html=./report
    ```

- Or add this snippet in the `pytest.ini` file:
    ```
    [pytest]
    addopts = -vs -rf --html=./report
    ```

**Note:** If you fail to provide `--html` tag, it consider your project's home directory as the base 

---
#### Is there a demo available for this gem?

Yes, you can use this demo as an example, https://github.com/prashanth-sams/pytest-html-reporter
```
pytest tests/
```