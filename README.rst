=====================
pytest-html-reporter
=====================

.. image:: https://badges.gitter.im/prashanth-sams/pytest-html-reporter.svg
   :alt: Join the chat at https://gitter.im/prashanth-sams/pytest-html-reporter
   :target: https://gitter.im/prashanth-sams/pytest-html-reporter?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge

.. image:: https://badge.fury.io/py/pytest-html-reporter.svg
    :target: https://badge.fury.io/py/pytest-html-reporter
    :alt: PyPI version

.. image:: https://travis-ci.com/prashanth-sams/pytest-html-reporter.svg?branch=master
    :target: https://travis-ci.com/prashanth-sams/pytest-html-reporter
    :alt: Build Status

.. image:: https://coveralls.io/repos/github/prashanth-sams/pytest-html-reporter/badge.svg?branch=master
    :target: https://coveralls.io/github/prashanth-sams/pytest-html-reporter?branch=master

.. image:: https://pepy.tech/badge/pytest-html-reporter
    :target: https://pepy.tech/project/pytest-html-reporter
    :alt: Downloads


..

        Generates a static html report based on ``pytest`` framework


.. image:: https://i.imgur.com/4TYia5j.png
   :alt: pytest-html-reporter

Features
------------
- Generic information
    - Overview
    - Trends
    - Suite Highlights
    - Test suite details
- Archives / History
- Screenshots on failure
- Test Rerun support

Installation
------------

.. code-block:: console

    $ pip install pytest-html-reporter


Usage
------------

By default, the filename used is ``pytest_html_reporter.html`` and path chosen is ``report``; you can skip both or
either one of them if not needed::

    $ pytest tests/


..

        Custom path and filename

Add ``--html-report`` tag followed by path location and filename to customize the report location and filename::

    $ pytest tests/ --html-report=./report
    $ pytest tests/ --html-report=./report/report.html

..

        pytest.ini

Alternate option is to add this snippet in the ``pytest.ini`` file::

    [pytest]
    addopts = -vs -rf --html-report=./report

**Note:** If you fail to provide ``--html-report`` tag, it consider your project's home directory as the base

screenshots on failure
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Import ``attach`` from the library and call it with the selenium command as given below::

    from pytest_html_reporter import attach

    ...
    attach(data=self.driver.get_screenshot_as_png())


.. image:: https://i.imgur.com/1HSYkdC.gif


Is there a demo available for this gem?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Yes, you can use this demo as an example, https://github.com/prashanth-sams/pytest-html-reporter::

    $ pytest tests/functional/