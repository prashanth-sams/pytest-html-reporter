"""Cover how a coverage summary is turned into the things the tab shows.

test_coverage.py covers the reading - the same figures out of a live run, a
coverage.json and a Cobertura xml. This is the other end: the sentence under
the ring, the tiles beside it, the rows of the table, and the chip that says
which way the number moved.

Each is a formatting decision with a reason - a dash rather than a 0 for a file
with no branches, no Branches tile at all when --cov-branch was never passed -
and a formatting decision is only pinned by the case that reads wrong without
it.
"""

import xml.etree.ElementTree as ElementTree

import pytest

from pytest_html_reporter.coverage_report import (
    _condition_coverage,
    build_summary,
    cap_note,
    coverage_grade,
    coverage_rows,
    coverage_target,
    coverage_tiles,
    format_delta,
    source_line,
    summarize_xml,
)


def _file(name, statements=10, missing=0, branches=0, branches_covered=0,
          percent=100.0, lines=""):
    return {"name": name, "statements": statements, "missing": missing,
            "branches": branches, "branches_covered": branches_covered,
            "partial": 0, "excluded": 0, "covered": statements - missing,
            "percent": percent, "lines": lines}


def _summary(**overrides):
    summary = {
        "files": [], "files_total": 0, "percent": 100.0, "statements": 0,
        "covered": 0, "missing": 0, "excluded": 0, "branches": 0,
        "branches_covered": 0, "partial": 0, "branch": False,
        "generated": "", "source": "coverage",
    }
    summary.update(overrides)
    return summary


class _AwkwardConfig:
    """A Config whose getoption refuses the question pytest-cov's would answer."""

    def __init__(self, error):
        self._error = error

    def getoption(self, name, default=None):
        if name == "cov_fail_under":
            raise self._error
        return None

    def getini(self, name):
        raise ValueError(name)


# ------------------------------------------------------- coverage_target ---

@pytest.mark.parametrize("error", [AttributeError("no such option"),
                                   ValueError("unregistered")])
def test_a_build_without_pytest_cov_installed_simply_has_no_target(error):
    """--cov-fail-under is pytest-cov's flag; asking for it without pytest-cov
    raises, and a missing target is not a reason to fail the render."""
    assert coverage_target(_AwkwardConfig(error)) is None


# -------------------------------------------------------- coverage_grade ---

def test_a_run_that_measured_nothing_is_not_coloured_as_a_success():
    """None is 'we do not know', which must not read as a pass."""
    assert coverage_grade(None) == "low"
    assert coverage_grade(None, target=80) == "low"


def test_the_bands_colour_a_percentage_with_no_target_set():
    assert coverage_grade(95.0) == "strong"
    assert coverage_grade(80.0) == "fair"
    assert coverage_grade(50.0) == "low"


def test_a_target_the_build_exactly_met_is_not_shown_as_a_failure():
    """79.999999999 against --cov-fail-under=80 passed the build."""
    assert coverage_grade(79.999999999, target=80) == "strong"


def test_a_target_replaces_the_bands_rather_than_joining_them():
    """50% against a target of 40 is a pass, however low it looks."""
    assert coverage_grade(50.0, target=40) == "strong"


# --------------------------------------------------- _condition_coverage ---

def test_a_cobertura_condition_is_read_as_taken_over_total():
    assert _condition_coverage("50% (1/2)") == (1, 2)


def test_an_attribute_that_was_never_written_is_no_branches_at_all():
    assert _condition_coverage("") == (0, 0)
    assert _condition_coverage(None) == (0, 0)


def test_an_attribute_without_the_bracketed_half_is_not_guessed_at():
    assert _condition_coverage("50%") == (0, 0)


def test_a_bracketed_half_that_is_not_two_numbers_is_not_guessed_at():
    assert _condition_coverage("50% (half of them)") == (0, 0)
    assert _condition_coverage("50% (1)") == (0, 0)


# ---------------------------------------------------------- summarize_xml ---

def test_a_cobertura_total_that_is_not_a_number_counts_as_none():
    """A hand-edited or half-written report must not take the tab down."""
    xml = ElementTree.fromstring(
        '<coverage lines-valid="lots" lines-covered="also lots" '
        'branches-valid="" branches-covered=""><packages/></coverage>')

    summary = summarize_xml(xml)

    assert summary["statements"] == 0
    assert summary["covered"] == 0


# ------------------------------------------------------------ source_line ---

def test_a_live_run_says_it_measured_the_numbers_itself():
    assert source_line(_summary(source="pytest-cov")) \
        == "Measured by pytest-cov during this run"


def test_a_file_on_disk_says_when_it_was_written():
    """A coverage.json from three days ago reads exactly like a fresh one."""
    summary = _summary(source="coverage.json", generated="2024-09-01T14:18:22")

    assert source_line(summary) == "Read from coverage.json, written 2024-09-01 14:18"


def test_a_file_that_did_not_record_when_it_was_written_still_names_itself():
    assert source_line(_summary(source="coverage.xml")) == "Read from coverage.xml"


def test_a_summary_that_named_no_source_still_says_something():
    assert source_line(_summary(source="")) == "Read from coverage"


# ---------------------------------------------------------- coverage_tiles ---

def test_the_four_tiles_every_run_gets():
    tiles = coverage_tiles(_summary(statements=100, covered=80, missing=20,
                                    files_total=5))

    for label in ("Statements", "Covered", "Missing", "Files"):
        assert label in tiles


def test_a_run_without_branch_coverage_gets_no_branch_tiles():
    """A Branches 0/0 tile says only that --cov-branch was not passed."""
    tiles = coverage_tiles(_summary(statements=100, branch=False, branches=0))

    assert "Branches" not in tiles
    assert "Partial" not in tiles


def test_branch_tiles_appear_once_branch_coverage_was_switched_on():
    tiles = coverage_tiles(_summary(statements=100, branch=True, branches=40,
                                    branches_covered=30, partial=4))

    assert "Branches" in tiles
    assert "30/40" in tiles
    assert "Partial" in tiles


def test_a_run_that_asked_for_branches_but_measured_none_gets_no_tile():
    tiles = coverage_tiles(_summary(statements=100, branch=True, branches=0))

    assert "Branches" not in tiles


def test_excluded_lines_are_only_mentioned_when_there_were_some():
    assert "Excluded" not in coverage_tiles(_summary(excluded=0))
    assert "Excluded" in coverage_tiles(_summary(excluded=7))


# ----------------------------------------------------------- coverage_rows ---

def test_a_file_with_no_branches_shows_a_dash_not_a_zero():
    """'0/0' reads as none of its branches being covered, which is not what
    a file with no branches at all is saying."""
    rows = coverage_rows(_summary(files=[_file("app/models.py")]))

    assert "&mdash;" in rows or "—" in rows
    assert "0/0" not in rows


def test_a_file_with_branches_shows_how_many_were_taken():
    rows = coverage_rows(_summary(
        files=[_file("app/views.py", branches=10, branches_covered=7)]))

    assert "7/10" in rows


def test_each_row_is_graded_against_the_projects_own_target():
    summary = _summary(files=[_file("app/a.py", percent=85.0)])

    assert 'strong' in coverage_rows(summary, target=80)
    assert 'low' in coverage_rows(summary, target=90)


def test_a_file_name_cannot_smuggle_markup_into_the_table():
    rows = coverage_rows(_summary(files=[_file("<script>x</script>.py")]))

    assert "<script>" not in rows


def test_a_run_with_no_files_renders_no_rows():
    assert coverage_rows(_summary()) == ""


# --------------------------------------------------------------- cap_note ---

def test_nothing_is_said_when_the_table_lists_the_whole_run():
    assert cap_note(_summary(files_total=10), 500) == ""


def test_nothing_is_said_when_the_limit_was_switched_off():
    assert cap_note(_summary(files_total=10_000), 0) == ""


def test_the_note_says_how_much_of_the_run_is_being_listed():
    note = cap_note(_summary(files_total=1200), 500)

    assert "Listing 500 of 1200 files" in note
    assert "--report-coverage-limit=0" in note


def test_a_run_exactly_at_the_limit_is_not_called_short():
    assert cap_note(_summary(files_total=500), 500) == ""


# ----------------------------------------------------------- format_delta ---

def test_a_build_that_moved_up_says_so_with_a_sign():
    assert format_delta(0.8) == "+0.8"


def test_a_build_that_moved_down_says_so():
    assert format_delta(-1.2) == "-1.2"


def test_a_movement_too_small_to_matter_is_called_no_change():
    """+0.0 reads as a measurement; 'no change' reads as the answer."""
    assert format_delta(0.0) == "no change"
    assert format_delta(0.04) == "no change"
    assert format_delta(-0.04) == "no change"


def test_a_first_build_has_nothing_to_compare_against():
    assert format_delta(None) == ""


# -------------------------------------------------- the pieces together ---

def test_a_summary_renders_end_to_end_from_the_files_it_was_built_from():
    """build_summary is what every reader hands to every renderer, so the two
    halves agreeing about its shape is the thing worth checking."""
    summary = build_summary(
        files=[_file("app/a.py", statements=10, missing=5, percent=50.0,
                     lines="4, 7-9")],
        percent=50.0, statements=10, covered=5, missing=5, excluded=0,
        branches=0, branches_covered=0, partial=0, branch=False,
        generated="2024-09-01T14:18:22",
    )

    assert "Statements" in coverage_tiles(summary)
    assert "app/a.py" in coverage_rows(summary)
    assert "4, 7-9" in coverage_rows(summary)
    assert cap_note(summary, 500) == ""
