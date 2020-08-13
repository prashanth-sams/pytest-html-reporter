=====================
pytest-html-reporter
=====================

.. image:: https://badge.fury.io/py/pytest-html-reporter.svg
    :target: https://badge.fury.io/py/pytest-html-reporter
    :alt: PyPI version

.. image:: https://travis-ci.com/prashanth-sams/pytest-html-reporter.svg?branch=master
    :target: https://travis-ci.com/prashanth-sams/pytest-html-reporter
    :alt: Build Status

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
- Archives

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

Add ``--html`` tag followed by path location and filename to customize the report location and filename::

    $ pytest tests/ --html=./report
    $ pytest tests/ --html=./report/report.html

..

        pytest.ini

Alternate option is to add this snippet in the ``pytest.ini`` file::

    [pytest]
    addopts = -vs -rf --html=./report

**Note:** If you fail to provide ``--html`` tag, it consider your project's home directory as the base

.. image:: https://i.imgur.com/iYD6wmH.png
    :align: center
    :alt: pytest-html-reporter-overview

|

.. image:: https://i.imgur.com/ge6OCM6.gif


Is there a demo available for this gem?
------------------------------------------------

Yes, you can use this demo as an example, https://github.com/prashanth-sams/pytest-html-reporter::

    $ pytest tests/