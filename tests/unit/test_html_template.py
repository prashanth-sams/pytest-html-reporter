import sys
import os

myPath = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, myPath + '/../../')
from pytest_html_reporter.template import html_template


def test_html_template():
    if "".__eq__(html_template()):
        raise Exception("invalid method: html_template")
    else:
        pass
