from pytest_html_reporter.util import max_rerun


def test_max_rerun_none():
    assert max_rerun() is None
