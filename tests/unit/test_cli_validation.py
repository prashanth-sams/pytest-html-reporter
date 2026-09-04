"""Cover the merge CLI's own checks, and the two paths that report a run.

Every flag the merge takes is checked before a bundle is read, and the reason
is in _check_html_report's docstring: the run has already happened by the time
anybody looks for the report and does not find it where they put it. A usage
error that arrives after a successful merge is a usage error that arrives too
late.

test_merge_cli.py drives the command end to end. These call the checks
directly, which is the only way to cover the messages nobody's happy path ever
produces - and the messages are the whole point of the checks.
"""

import os
import subprocess
import sys

import pytest

from pytest_html_reporter import __version__
from pytest_html_reporter.cli import (
    _check_html_report,
    _check_start_time,
    main,
)
from pytest_html_reporter.plugin import report_base


# ------------------------------------------------------ _check_html_report ---

def test_a_folder_is_what_the_flag_usually_takes():
    assert _check_html_report("./report") == ""


def test_naming_the_html_file_itself_is_allowed():
    assert _check_html_report("./report/index.html") == ""


def test_a_flag_with_nothing_after_it_says_what_it_takes():
    assert "takes a folder or an .html file" in _check_html_report("")
    assert "takes a folder or an .html file" in _check_html_report("   ")
    assert "takes a folder or an .html file" in _check_html_report(None)


def test_a_folder_named_after_the_file_it_holds_is_refused():
    """'.html' in it without ending in it is read as a file name, and the
    report lands in the current directory under the folder's name."""
    message = _check_html_report("./my.html.d")

    assert "without ending in it" in message
    assert "./my.html.d" in message


def test_a_folder_that_is_really_a_file_is_refused_before_the_merge_runs(tmp_path):
    """Otherwise it reaches os.makedirs at the end and comes out as a
    FileExistsError traceback over a merge that had otherwise succeeded."""
    occupied = tmp_path / "report"
    occupied.write_text("not a folder")

    message = _check_html_report(str(occupied))

    assert "already exists and is not a folder" in message


def test_an_html_file_whose_folder_is_a_file_is_refused_too(tmp_path):
    occupied = tmp_path / "report"
    occupied.write_text("not a folder")

    message = _check_html_report(str(occupied / "index.html"))

    assert "already exists and is not a folder" in message


def test_an_html_file_named_with_no_folder_at_all_is_fine():
    assert _check_html_report("index.html") == ""


# ------------------------------------------------------- _check_start_time ---

@pytest.mark.parametrize("value", ["earliest", "now", "EARLIEST", "  now  "])
def test_the_words_the_flag_documents_are_accepted(value):
    assert _check_start_time(value) == ""


def test_a_unix_timestamp_is_accepted():
    assert _check_start_time("1725200000") == ""
    assert _check_start_time("1725200000.5") == ""


def test_a_typo_is_reported_rather_than_promising_a_build():
    """--dry-run never reaches the render, so this is where a typo is caught."""
    message = _check_start_time("yesterday")

    assert "takes earliest, now or a unix timestamp" in message
    assert "yesterday" in message


# --------------------------------------------------------------- entrypoints ---

def test_the_module_runs_as_a_command_of_its_own():
    """python -m works in a pip-installed wheel, a tox environment and a
    checkout alike, so a pipeline never has to find out which it is in."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest_html_reporter", "--version"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)

    assert result.returncode == 0
    assert __version__ in result.stdout


def test_the_module_hands_back_the_exit_code_rather_than_raising():
    """main returns it so that every caller agrees about who owns SystemExit."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest_html_reporter", "merge", "--html-report="],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)

    assert result.returncode != 0


def test_main_returns_the_code_it_would_have_exited_with():
    assert main(["merge", "--html-report=./my.html.d"]) != 0


# ------------------------------------------------------------- report_base ---

def test_a_folder_is_its_own_report_base(tmp_path):
    assert report_base(str(tmp_path)) == str(tmp_path)


def test_an_html_file_reports_the_folder_holding_it():
    assert report_base("./out/index.html") == os.path.abspath("./out")


def test_an_html_file_with_no_folder_reports_the_current_directory():
    assert report_base("index.html") == os.path.abspath(".")


def test_a_folder_named_after_a_file_resolves_the_same_way_the_reporter_does():
    """The two answers naming different folders is far worse than either being
    surprising: the shard would clean one and write its screenshots to another."""
    assert report_base("./my.html.d") == os.path.abspath(".")
