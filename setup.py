#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import re
import codecs
from urllib.parse import quote
from setuptools import setup, find_packages

RAW_ROOT = "https://raw.githubusercontent.com/prashanth-sams/pytest-html-reporter/master/"

# ![alt](images/x.png), src="images/x.png", srcset="images/x.png" -- but not
# a path that is already absolute.
RELATIVE_IMAGE = re.compile(
    r"""(!\[[^\]]*\]\(|(?:src|srcset)=["'])(?!https?://|//|/|\#)(images/[^)"'\s]+)"""
)


def read(fname):
    file_path = os.path.join(os.path.dirname(__file__), fname)
    return codecs.open(file_path, encoding="utf-8").read()


def read_long_description(fname):
    # PyPI renders the long description on its own domain with no base URL, so
    # a relative image path that resolves fine on GitHub 404s there and the
    # project page shows broken images. Keep README.md relative for the repo
    # and absolutise only the copy that goes into the package metadata.
    return RELATIVE_IMAGE.sub(
        lambda m: m.group(1) + RAW_ROOT + quote(m.group(2)), read(fname)
    )


setup(
    name="pytest-html-reporter",
    version="0.4.2",
    author="Prashanth Sams",
    author_email="sams.prashanth@gmail.com",
    maintainer="Prashanth Sams",
    maintainer_email="sams.prashanth@gmail.com",
    license="MIT",
    project_urls={
        "Homepage": "https://github.com/prashanth-sams/pytest-html-reporter",        
        "Source": "https://github.com/prashanth-sams/pytest-html-reporter",
        "Issues": "https://github.com/prashanth-sams/pytest-html-reporter/issues",
        "Changelog": "https://github.com/prashanth-sams/pytest-html-reporter/blob/master/CHANGELOG.txt",
        "Roadmap": "https://github.com/prashanth-sams/pytest-html-reporter/blob/master/ROADMAP.md",
    },
    description="A pytest plugin for generating lightweight HTML test reports with screenshots, logs, coverage, archives, and xdist support",
    long_description=read_long_description("README.md"),
    keywords=["pytest", "py.test", "html", "reporter", "report", "pytest-plugin", "html-report", "test-report", "pytest-html", "pytest-html-reporter", "api-testing", "xdist", "playwright", "selenium", "test-coverage", "pytest-cov", "pytest-html-cov", "pytest-html-coverage", "pytest-coverage"],
    packages=find_packages(),
    include_package_data=True,
    package_data={
        "html_page": [
            "html/*.html",
            "icons/*.svg",
            "icons/README.md",
            "images/*",
            "vendor/*.js",
            "vendor/*.css",
            "vendor/README.md",
        ],
    },
    long_description_content_type="text/markdown",
    python_requires=">=3.7",
    install_requires=["pytest", "Pillow"],
    classifiers=[
        "Framework :: Pytest",
        "Topic :: Software Development :: Testing",
        "Topic :: Software Development :: Quality Assurance",
        "Programming Language :: Python",
        "Operating System :: OS Independent",
        "License :: OSI Approved :: MIT License",
    ],
    entry_points={
        "pytest11": [
            "reporter = pytest_html_reporter.plugin",
        ],
        # The merge of a sharded run is its own process, not another pytest
        # run: a report folder has exactly one writer per build, and a fifth
        # pytest started in it to do the merging would clean_screenshots away
        # the images it was sent to collect.
        "console_scripts": [
            "pytest-html-reporter = pytest_html_reporter.cli:main",
        ],
    },
)
