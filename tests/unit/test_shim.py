"""Cover the stand-in Config a merge is rendered with.

The merge command has no pytest session, so nothing it renders can ask a real
Config anything. MergeConfig is what the render pipeline is handed instead, and
its whole job is to answer every question those helpers ask without any of them
learning that a merge exists.

The answers are load-bearing in a way that is easy to miss - getini raising
rather than returning '' is the difference between --archive-count defaulting
and quietly keeping nothing - so each one is pinned here.
"""

import os
import sys

import pytest

from pytest_html_reporter.shim import MergeConfig
from pytest_html_reporter.util import REPORT_PATH_DEFAULT, report_path


# ------------------------------------------------------------- getoption ---

def test_an_option_the_merge_set_is_handed_back():
    config = MergeConfig(options={"path": "./report"})

    assert config.getoption("path") == "./report"


def test_an_option_nobody_set_falls_back_to_the_default():
    assert MergeConfig().getoption("path", "./default") == "./default"


def test_an_option_explicitly_none_falls_back_to_the_default():
    """argparse fills every flag it did not see with None."""
    config = MergeConfig(options={"path": None})

    assert config.getoption("path", "./default") == "./default"


def test_an_option_with_no_default_and_no_value_is_none():
    assert MergeConfig().getoption("path") is None


def test_a_falsey_value_that_was_actually_set_survives():
    """0 and '' are answers; only None means nobody said."""
    config = MergeConfig(options={"archive_count": 0, "title": ""})

    assert config.getoption("archive_count", 5) == 0
    assert config.getoption("title", "Report") == ""


# ----------------------------------------------------------------- getini ---

def test_every_ini_question_raises_so_the_helpers_fall_through():
    """util._ini catches this and returns None, which is what makes each
    option helper use its own default. Returning '' would work for the string
    options and quietly break the ones that treat '' as deliberate."""
    with pytest.raises(ValueError):
        MergeConfig().getini("environment")


# --------------------------------------------------------- config.option ---

def test_the_namespace_reads_the_very_dict_getoption_reads():
    config = MergeConfig(options={"path": "./report"})

    assert config.option.path == "./report"


def test_writing_through_the_namespace_is_seen_by_getoption():
    """plugin.py expands --html-report once and writes it back; a namespace
    holding its own copy would let the two views drift, and the drift shows up
    as a report written to one path and screenshots to another."""
    config = MergeConfig(options={"path": "./report"})

    config.option.path = "/expanded/report"

    assert config.getoption("path") == "/expanded/report"
    assert config.option.path == "/expanded/report"


def test_a_name_nobody_set_is_an_attribute_error_not_a_key_error():
    """Every reader in the tree guards with getattr, which only catches one."""
    config = MergeConfig()

    with pytest.raises(AttributeError):
        config.option.nothing_set_this


def test_a_name_written_that_was_never_there_becomes_readable():
    config = MergeConfig()
    config.option.junit_path = "./out.xml"

    assert config.option.junit_path == "./out.xml"


# --------------------------------------------------- the plugin manager ---

def test_no_plugin_is_ever_installed():
    manager = MergeConfig().pluginmanager

    assert manager.hasplugin("xdist") is False
    assert manager.getplugin("xdist") is None
    assert manager.get_plugin("xdist") is None


def test_the_plugin_list_is_empty_rather_than_missing():
    """util._plugin_versions calls this unguarded, and a shim that crashes on
    the function it replaced is not a shim."""
    assert MergeConfig().pluginmanager.list_plugin_distinfo() == []


# ---------------------------------------------------------------- rootpath ---

def test_the_root_defaults_to_where_the_merge_was_run():
    config = MergeConfig()

    assert config.rootpath == os.getcwd()
    assert config.rootdir == config.rootpath


def test_the_root_is_a_string_because_every_reader_treats_it_as_one(tmp_path):
    config = MergeConfig(rootpath=tmp_path)

    assert isinstance(config.rootpath, str)
    assert config.rootpath == str(tmp_path)


# -------------------------------------------------- the invocation args ---

def test_the_arguments_row_shows_what_the_merge_was_asked_to_do():
    config = MergeConfig(args=["merge", "--html-report=./report"])

    assert config.invocation_params.args == ("merge", "--html-report=./report")


def test_the_arguments_default_to_this_processs_own():
    assert MergeConfig().invocation_params.args == tuple(sys.argv[1:])


def test_an_empty_argument_list_is_kept_rather_than_replaced():
    """[] is 'nothing was passed', which is not the same as 'nobody said'."""
    assert MergeConfig(args=[]).invocation_params.args == ()


# --------------------------------------- the render pipeline reads it ---

def test_the_render_pipeline_resolves_a_path_through_it(tmp_path):
    """The point of the whole class: a helper written for a pytest Config
    answers correctly when handed this instead."""
    config = MergeConfig(options={"path": str(tmp_path / "out")})

    assert report_path(config) == str(tmp_path / "out")


def test_the_render_pipeline_falls_back_to_its_default_through_it():
    """Reached only because getini raised and getoption said None."""
    assert report_path(MergeConfig()) == REPORT_PATH_DEFAULT
