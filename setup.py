#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import codecs
from setuptools import setup, find_packages


def read(fname):
    file_path = os.path.join(os.path.dirname(__file__), fname)
    return codecs.open(file_path, encoding="utf-8").read()


setup(
    name="pytest-html-reporter-netesenz",
    version="0.0.4",
    author="Deependra Singh",
    author_email="",
    maintainer="Deependra Singh",
    maintainer_email="",
    license="MIT",
    long_description_content_type='text/markdown',
    url="https://github.com/prashanth-sams/pytest-html-reporter",
    description="Generates a static html report based on pytest framework",
    long_description=read("README.rst"),
    keywords=["pytest", "py.test", "html", "reporter", "report"],
    packages=find_packages(),
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
            "reporter = pytest_html_reporter_netesenz.plugin",
        ],
    },
)
