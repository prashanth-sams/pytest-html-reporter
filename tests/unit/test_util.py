from pytest_html_reporter.util import (
    build_info,
    environment_label,
    environment_name,
    max_rerun,
)


def test_max_rerun_none():
    assert max_rerun() is None


class _FakeConfig:
    """Just enough of pytest's Config for the option/ini resolution helpers."""

    def __init__(self, options=None, ini=None):
        self._options = options or {}
        self._ini = ini or {}

    def getoption(self, name, default=None):
        return self._options.get(name, default)

    def getini(self, name):
        if name not in self._ini:
            raise ValueError(name)
        return self._ini[name]


def test_environment_name_from_ini():
    assert environment_name(_FakeConfig(ini={"environment": "staging"})) == "staging"


def test_environment_name_cli_beats_ini():
    config = _FakeConfig(options={"environment": "prod"}, ini={"environment": "staging"})
    assert environment_name(config) == "prod"


def test_environment_name_defaults_to_empty():
    assert environment_name(_FakeConfig()) == ""


def test_build_info_merges_cli_and_ini():
    config = _FakeConfig(
        options={"build_info": ["release=2.4.0"]},
        ini={"build_info": ["branch=main", "team=payments"]},
    )
    assert build_info(config) == [
        ("release", "2.4.0"),
        ("branch", "main"),
        ("team", "payments"),
    ]


def test_build_info_skips_blanks_and_keeps_bare_keys():
    config = _FakeConfig(ini={"build_info": ["  ", "branch = main", "note"]})
    assert build_info(config) == [("branch", "main"), ("note", "")]


def test_build_info_keeps_equals_in_the_value():
    config = _FakeConfig(ini={"build_info": ["job=https://ci/run?id=7"]})
    assert build_info(config) == [("job", "https://ci/run?id=7")]


def test_environment_label_keeps_short_names():
    assert environment_label("staging") == "staging"


def test_environment_label_keeps_names_of_exactly_ten():
    assert environment_label("production") == "production"


def test_environment_label_trims_longer_names_to_ten():
    label = environment_label("pre-production")
    assert label == "pre-produ\u2026"
    assert len(label) == 10
