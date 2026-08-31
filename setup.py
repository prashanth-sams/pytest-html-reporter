#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import codecs
from setuptools import setup, find_packages


def read(fname):
    file_path = os.path.join(os.path.dirname(__file__), fname)
    return codecs.open(file_path, encoding="utf-8").read()


setup(
    name="pytest-html-reporter",
    version="0.3.6",
    author="Prashanth Sams",
    author_email="sams.prashanth@gmail.com",
    maintainer="Prashanth Sams",
    maintainer_email="sams.prashanth@gmail.com",
    license="MIT",
    url="https://github.com/prashanth-sams/pytest-html-reporter",
    description="Generates a light-weight static html report based on pytest framework",
    long_description=read("README.rst"),
    keywords=["pytest", "py.test", "html", "reporter", "report", "pytest-plugin", "html-report", "test-report", "pytest-html", "pytest-html-reporter", "api-testing", "xdist", "playwright", "selenium", "test-coverage", "pytest-cov", "pytest-html-cov", "pytest-html-coverage", "pytest-coverage"],
    packages=find_packages(),
    include_package_data=True,
    package_data={
        "html_page": ["html/*.html"],
    },
    python_requires=">=3.5",
    install_requires=["pytest", "Pillow"],
    classifiers=[
        "Framework :: Pytest",
        "Topic :: Software Development :: Testing",
        "Programming Language :: Python",
        "Operating System :: OS Independent",
        "License :: OSI Approved :: MIT License",
    ],
    entry_points={
        "pytest11": [
            "reporter = pytest_html_reporter.plugin",
        ],
    },
)
