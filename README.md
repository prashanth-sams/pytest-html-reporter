# pytest-html-reporter
[![PyPI version](https://badge.fury.io/py/pytest-html-reporter.svg)](https://badge.fury.io/py/pytest-html-reporter)
[![Build Status](https://travis-ci.com/prashanth-sams/pytest-html-reporter.svg?branch=master)](https://travis-ci.com/prashanth-sams/pytest-html-reporter)
[![Downloads](https://pepy.tech/badge/pytest-html-reporter)](https://pepy.tech/project/pytest-html-reporter)

> Generates a static html report based on `pytest` framework

<div align="center"><img src="./PHR.png" width="200"/></div>

## Installation

```
pip install pytest-html-reporter
```

Or install it by adding this line in your project's `requirements.txt` file:

```
pytest-html-reporter
```

And then execute:
```
pip install -r requirements.txt
```

## Usage outline

By default, the filename used is `pytest_html_reporter.html` and path chosen is `report`; you can skip both or either
one of them if not needed

    pytest tests/
> Custom path and filename

Add `--html` tag followed by path location and filename to customize the report location and filename

    pytest tests/ --html=./report

    pytest tests/ --html=./report/report.html

> pytest.ini

Alternate option is to add this snippet in the `pytest.ini` file:
    
    [pytest]
    addopts = -vs -rf --html=./report
    

**Note:** If you fail to provide `--html` tag, it consider your project's home directory as the base 

![](https://i.imgur.com/cDIp9JG.jpg)

---
#### Is there a demo available for this gem?

Yes, you can use this demo as an example, https://github.com/prashanth-sams/pytest-html-reporter
```
pytest tests/
```