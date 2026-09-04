"""The ``pytest-html-reporter`` command - ``merge``, ``junit`` and ``inspect``.

Merging is its own process rather than another pytest run, and that is the
whole design. A build is one set of totals, one archived ``output.json``, one
rotation of ``archive/``, one point on the trend chart and one entry in every
per-test history Analytics reconstructs - so exactly one process may write into
the report folder. Four matrix legs writing four reports into one folder do not
add up to a build, they overwrite each other's ``output.json`` and manufacture
four builds out of one; and a fifth pytest run started in the report folder to
do the merging would call ``clean_screenshots`` on the way in and delete the
images it was sent to collect.

So the legs write bundles and write nothing else (``shards.py``), this command
reads them and drives the ordinary render pipeline exactly once
(``merge.render_merged``), and the report it produces is assembled by the same
code every other build on that report's history was assembled by. Nothing here
re-implements a page, a total or a template.

Three subcommands rather than three commands, because they are three views of
one merge:

* ``merge`` does the whole of it - the report, and the JUnit XML when asked.
* ``junit`` stops after the XML, for a pipeline that publishes test results
  without publishing a report.
* ``inspect`` stops before anything is written at all, which is what you want
  when four artifacts were downloaded and only three of them are there.

argparse and the standard library only: ``install_requires`` is ``pytest`` and
``Pillow``, and a merge command that needed a dependency of its own would be a
command CI could not run.
"""

import argparse
import json
import os
import sys

import pytest

from pytest_html_reporter import __version__
from pytest_html_reporter import merge as merge_module
from pytest_html_reporter import shards
from pytest_html_reporter.junit import (
    JUNIT_LOGGING_MODES,
    JUNIT_XPASS_MODES,
    write_junit,
)
from pytest_html_reporter.merge import (
    DUPLICATE_POLICIES,
    ORDERS,
    START_TIMES,
    MergeError,
    MergeOptions,
    provenance_lines,
)
from pytest_html_reporter.shim import MergeConfig
from pytest_html_reporter.util import archive_count, archive_days, archive_since


PROG = "pytest-html-reporter"

# The only three answers this command gives, so that a pipeline can branch on
# them without reading the text. 1 is a verdict about the tests or about the
# completeness of the merge and always comes with a report; 2 means nothing was
# produced at all.
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

# Where a bundle is looked for when nobody says. The everyday shape is one
# folder holding the artifacts four CI jobs uploaded, and the everyday command
# is run from inside it.
DEFAULT_PATHS = ["."]

COVERAGE_LIMIT_DEFAULT = 500


class _Silence(object):
    """A stream that swallows what is written to it, for ``-q``.

    Handed to JunitOptions rather than dropping its warnings, because the
    warnings are still collected in ``opts.warnings`` and ``--strict`` still
    reads them. ``-q`` asks for a quiet terminal, not for a merge that stops
    noticing things.
    """

    def write(self, text):
        pass

    def flush(self):
        pass


# --------------------------------------------------------------------------
# saying things
# --------------------------------------------------------------------------

def _note(message, quiet=False):
    """One decision the merge made, on stderr.

    Every duplicate fold, every quarantined record and every image a bundle
    promised and did not carry comes through here. On stderr and not on stdout
    so that ``inspect --json`` stays a document, and printed in every mode but
    ``-q`` because a merged report that silently dropped a test is the one
    failure mode this whole feature has to be honest about.
    """
    if quiet: return

    sys.stderr.write("%s: %s\n" % (PROG, message))


def _fail(message):
    """Say why nothing was produced, and hand back the code for it.

    Printed whatever ``-q`` says: quiet asks for fewer notes, never for a
    silent failure.
    """
    sys.stderr.write("%s: %s\n" % (PROG, message))

    return EXIT_USAGE


# --------------------------------------------------------------------------
# checking what was asked for
# --------------------------------------------------------------------------

def _check_html_report(path):
    """Why ``--html-report`` cannot be used, or '' when it can.

    ``HTMLReporter.report_path`` decides between "a folder" and "a file" on
    ``'.html' in self.path`` (html_reporter.py:350), so a path that merely
    contains ``.html`` without ending in it - ``./my.html.d``, a folder somebody
    named after the file it holds - is read as a file, and the report lands in
    the current directory under the folder's name. Refused here rather than
    obeyed, because the run has already happened by the time anybody looks for
    the report and does not find it where they put it.
    """
    path = str(path or "")

    if not path.strip():
        return "--html-report takes a folder or an .html file to write the merged report to"

    if ".html" in path and not path.endswith(".html"):
        return ("--html-report %r has '.html' in it without ending in it, so it would be read "
                "as a file name and the report would be written into the current directory; "
                "name the folder without '.html' in it, or name the .html file itself" % path)

    # The folder the build goes into, decided the same way HTMLReporter does it.
    # Something already sitting there that is not a folder is refused now, with
    # the other usage errors, rather than reaching os.makedirs at the end of the
    # render and coming out as a FileExistsError traceback over a merge that had
    # otherwise succeeded.
    folder = os.path.dirname(path) or "." if path.endswith(".html") else path

    if os.path.exists(folder) and not os.path.isdir(folder):
        return ("--html-report %r cannot be written to: %r already exists and is not a folder"
                % (path, folder))

    return ""


def _check_start_time(value):
    """Why ``--start-time`` cannot be used, or '' when it can.

    Checked here as well as in ``merge._start_stamp`` so that ``--dry-run``,
    which never reaches the render, still reports a typo rather than promising
    a build it would not have been able to stamp.
    """
    value = str(value or "").strip().lower()

    if value in START_TIMES: return ""

    try:
        float(value)
    except ValueError:
        return "--start-time takes earliest, now or a unix timestamp, not %r" % value

    return ""


def _check_retention(opts):
    """Why the archive flags cannot be used, or '' when they can.

    Asked of the very ``util`` helpers the pytest run asks - so that
    ``--archive-count nine`` is refused by the merge in the same words and for
    the same reason it is refused by a run - and asked *before* anything is
    written, because these three are read deep inside ``render()`` where a
    UsageError would abort a build that had already rotated the archive.
    """
    probe = MergeConfig(options={
        "archive_count": opts.archive_count,
        "archive_days": opts.archive_days,
        "archive_since": opts.archive_since,
    })

    try:
        archive_count(probe)
        archive_days(probe)
        archive_since(probe)
    except pytest.UsageError as error:
        return str(error)

    return ""


# --------------------------------------------------------------------------
# the merge itself
# --------------------------------------------------------------------------

def _options(args, **overrides):
    """A MergeOptions out of an argparse namespace.

    The argparse dests are the MergeOptions field names on purpose, so adding a
    flag is one edit rather than two. The four names that are not options are
    dropped rather than carried: MergeOptions keeps whatever else it is handed,
    and an ``opts.handler`` holding a function is the kind of thing that later
    reads as a field somebody meant.
    """
    values = dict(vars(args))

    for name in ("command", "handler", "paths", "json", "output"):
        values.pop(name, None)

    values.update(overrides)

    return MergeOptions(**values)


def _merged(paths, opts):
    """Every bundle under `paths`, merged - the work all three subcommands share.

    Raises MergeError when there is nothing to merge, so that "no bundles" and
    "a duplicate under --on-duplicate error" leave by the same door and get the
    same exit code; there is nothing to tell apart about them from a pipeline's
    point of view.
    """
    notes = []
    bundles = merge_module.load_bundles(paths, notes)

    if not bundles:
        # The paths are named back because the usual cause is a CI step that
        # unpacked the artifacts one directory deeper than the merge was told.
        for note in notes:
            _note(note, opts.quiet)

        raise MergeError("no shard bundles under %s" % ", ".join(paths))

    result = merge_module.merge_bundles(bundles, opts)

    # The discovery notes come first because they are about files, and the merge
    # notes are about records: the reader wants to know what was walked past
    # before being told what was folded.
    result.notes = notes + result.notes

    # Kept apart from result.notes as well, because --strict has to be able to
    # tell "a file in the folder was not a bundle" from "a fold happened", and
    # MergeResult.clean only knows about the second.
    result.unreadable = list(notes)

    # How many bundles order_bundles dropped because two files claimed one shard
    # id. It keeps the later one and carries on - a retried CI leg whose artifact
    # landed twice is recoverable and not worth failing a merge over - but it is
    # exactly the kind of "did all four artifacts arrive, and were they the four
    # I think" question --strict exists to answer, and MergeResult.clean does not
    # know about it. Counted here rather than parsed back out of the notes.
    result.collapsed = len(bundles) - len(result.bundles)

    return result


def _report_notes(result, quiet):
    """Everything the merge decided, one line each."""
    for note in result.notes:
        _note(note, quiet)


def _exit_code(result, opts, junit_warnings):
    """0, or 1 when something the caller asked to be told about happened.

    The two flags answer two different questions and are deliberately separate:
    ``--strict`` is about the merge being complete - nothing quarantined,
    nothing unreadable, nothing folded, no image missing - and ``--exit-code``
    is about the tests. A pipeline that wants the build to go red on a failing
    test says so; one that only wants to know that all four artifacts arrived
    says the other thing. The report is written either way, which is the point:
    a merge that exits 1 has still produced the page that explains why.
    """
    if opts.strict and (not result.clean or result.unreadable or result.collapsed
                        or junit_warnings):
        return EXIT_FAILED

    if opts.exit_code and result.failed:
        return EXIT_FAILED

    return EXIT_OK


# --------------------------------------------------------------------------
# the junit xml
# --------------------------------------------------------------------------

def _junit_options(result, opts, report_base, quiet):
    """The JunitOptions for a merged document, as this command's flags shape it.

    The facts a merged document carries about the matrix - which shards, whose
    clock, how many reruns and folds - are settled by merge.merged_junit_options
    so that this command and the --report-shard-merge leg, which writes the same
    document from HTMLReporter.render(), cannot drift apart. Everything below is
    a flag of this command's own, and an unset one is dropped rather than
    imposed: --junit-hostname arrives as '' when nobody typed it, and passing
    that through would blank the host the shards themselves reported.
    """
    return merge_module.merged_junit_options(
        result,
        suite_name=opts.junit_suite_name,
        hostname=opts.junit_hostname,
        xpass=opts.junit_xpass,
        logging=opts.junit_logging,
        attachments=opts.junit_attachments,
        report_base=report_base,
        stream=_Silence() if quiet else sys.stderr,
    )


def _shard_scope_screenshots(records):
    """Prefix every screenshot name with the shard that took it.

    What ``stage_assets`` does while a merge copies the images, done here for
    the ``junit`` command, which copies nothing and still has to name the files
    the way a merged report holds them. ``screenshot_name()`` restarts its
    counter in every process, so two machines' first screenshots are both
    ``<ms>-1``: without this, one shard's attachment line names another
    shard's image.
    """
    for record in records:
        shots = record.get("screenshots") or []
        if not shots: continue

        renamed = []

        for entry in shots:
            entry = dict(entry)

            # Each picture's own shard, not the row's: the 'merge' duplicate
            # policy keeps one shard's record and back-fills another shard's
            # screenshots onto it, and naming those after the row would point
            # the attachment line at a folder that never held them.
            shard_id = merge_module.shot_shard(entry, record)

            name = str(entry.get("name") or "")
            if name and shard_id: entry["name"] = shard_id + "/" + name
            renamed.append(entry)

        record["screenshots"] = renamed


# --------------------------------------------------------------------------
# printing what happened
# --------------------------------------------------------------------------

def _status_counts(records):
    """{status: how many}, in the order the statuses were first seen."""
    counts = []
    index = {}

    for record in records:
        status = str(record.get("status") or "")
        if not status: continue

        if status not in index:
            index[status] = len(counts)
            counts.append([status, 0])

        counts[index[status]][1] += 1

    return counts


def _seconds(value):
    """A span of time in the register the report's own header uses."""
    value = float(value or 0.0)

    if value < 60: return "%.2f secs" % value

    return "%d mins %02d secs" % (int(value // 60), int(value % 60))


def _bundle_line(bundle):
    """One bundle, on one line, for ``inspect``."""
    collects = sum(1 for record in bundle.records if record.get("collect"))

    return "%-20s %6d records  %3d collect  %-16s %s" % (
        bundle.shard.id,
        len(bundle.records) - collects,
        collects,
        bundle.run.hostname or "-",
        bundle.path,
    )


def _print_summary(result, report="", junit="", provenance=True):
    """What the merge came to, on stdout.

    On stdout rather than stderr because it is the answer to the question that
    was asked, while the notes are asides about how it was arrived at - and a
    pipeline that captures one very often wants to discard the other. Printed
    under ``-q`` as well for the same reason.

    `provenance` is off for ``inspect`` alone, which has already printed a
    fuller line for every bundle including the path it was read from; every
    other caller names each bundle here, always, so that a bundle from
    yesterday is a line in the output rather than two extra tests in the
    totals.
    """
    stream = sys.stdout
    meta = result.meta
    tests = result.tests

    stream.write("merged %d shard%s: %d test%s\n" % (
        len(result.bundles), "" if len(result.bundles) == 1 else "s",
        len(tests), "" if len(tests) == 1 else "s"))

    if provenance:
        for line in provenance_lines(result.bundles):
            stream.write("  %s\n" % line)

    counts = _status_counts(tests)
    if counts:
        stream.write("  %s\n" % ", ".join("%s %d" % (status, count) for status, count in counts))

    if result.collects:
        stream.write("  %d collection record%s\n"
                     % (len(result.collects), "" if len(result.collects) == 1 else "s"))

    # Only the numbers that are not zero, so the everyday clean merge prints
    # three lines and the interesting one stands out.
    for label, values in (("duplicates folded", result.folds),
                          ("quarantined", result.quarantined),
                          ("missing screenshots", result.missing_assets),
                          ("unrecognised statuses", result.unrecognised)):
        if values:
            stream.write("  %s: %d\n" % (label, len(values)))

    # Its own line rather than another row above it: this one counts whole
    # bundles that were put aside, not records, and reading it as a number of
    # tests would badly understate what happened.
    if getattr(result, "collapsed", 0):
        stream.write("  bundles superseded by a newer copy: %d\n" % result.collapsed)

    stream.write("  ran on %s over %s\n"
                 % (", ".join(meta.hosts) or "an unnamed host", _seconds(meta.wall)))

    if result.coverage_notice:
        stream.write("  coverage: %s\n" % result.coverage_notice)

    if report: stream.write("  report: %s\n" % report)
    if junit: stream.write("  junit:  %s\n" % junit)


def _inspect_payload(result):
    """Everything ``inspect`` prints, as data, for ``--json``.

    A document rather than the lines reformatted, because the reason to ask for
    json is that something downstream is going to check that four shards
    arrived and that none of them was empty.
    """
    meta = result.meta

    bundles = []
    for bundle in result.bundles:
        collects = sum(1 for record in bundle.records if record.get("collect"))

        bundles.append({
            "id": bundle.shard.id,
            "label": bundle.shard.label,
            "path": bundle.path,
            "hostname": bundle.run.hostname,
            "platform": bundle.run.platform,
            "python": bundle.run.python,
            "pytest": bundle.run.pytest,
            "exitstatus": bundle.run.exitstatus,
            "session_start": bundle.run.session_start,
            "session_end": bundle.run.session_end,
            "records": len(bundle.records) - collects,
            "collect": collects,
            "coverage": bool(bundle.coverage),
        })

    return {
        "bundles": bundles,
        "summary": {
            "shards": len(result.bundles),
            "tests": len(result.tests),
            "collects": len(result.collects),
            "statuses": dict(_status_counts(result.tests)),
            "reruns": sum(int(record.get("rerun") or 0) for record in result.records),
            "duplicates_folded": len(result.folds),
            "quarantined": len(result.quarantined),
            "unreadable": len(getattr(result, "unreadable", [])),
            "superseded": getattr(result, "collapsed", 0),
            "unrecognised": len(result.unrecognised),
            "session_start": meta.session_start,
            "session_end": meta.session_end,
            "wall": meta.wall,
            "hosts": list(meta.hosts),
            "environment": meta.environment,
            "coverage_notice": result.coverage_notice,
            "notes": list(result.notes),
        },
    }


# --------------------------------------------------------------------------
# merge
# --------------------------------------------------------------------------

def merge_command(args):
    """Read every bundle, merge them, and render one build."""
    problem = _check_html_report(args.html_report) or _check_start_time(args.start_time)
    if problem: return _fail(problem)

    opts = _options(args)

    problem = _check_retention(opts)
    if problem: return _fail(problem)

    try:
        result = _merged(args.paths, opts)
    except (MergeError, shards.BundleTooNew) as error:
        return _fail(str(error))

    if opts.dry_run:
        # Nothing is written and nothing is staged, which is what makes this
        # worth running: the summary below is the summary of the build that
        # would have been produced, arrived at by the same code.
        _report_notes(result, opts.quiet)
        _print_summary(result)

        return _exit_code(result, opts, [])

    try:
        reporter = merge_module.render_merged(result, opts)
    except (MergeError, pytest.UsageError) as error:
        # A UsageError can still surface from the retention helpers deeper in
        # render(), and it names the flag - which the merge spells identically.
        return _fail(str(error))

    report = os.path.join(*reporter.report_path)

    # Named in the summary only once it is on disk. render() writes no page for
    # a run that produced no records - the `if self._records:` guard, which a
    # plain pytest run obeys too - and a merge of shards that between them
    # collected nothing lands there. Printing the path anyway would send the
    # next step of a pipeline off to publish a file that was never written, and
    # it would blame the copy rather than the empty matrix.
    if not os.path.isfile(report):
        _note("no report was written: the shards hold no test records between them", opts.quiet)
        report = ""

    junit = ""
    warnings = []
    unwritten = False

    if opts.junit_xml:
        junit_options = _junit_options(result, opts, reporter.report_path[0], opts.quiet)
        warnings = junit_options.warnings

        try:
            junit = write_junit(opts.junit_xml, result.records, options=junit_options)
        except (OSError, ValueError) as error:
            # The report is already on disk by now, so this is not exit 2 -
            # something *was* produced - and it is not a clean run either. Said
            # here rather than raised, because a traceback out of a merge that
            # succeeded reads as though the merge is what went wrong.
            sys.stderr.write("%s: --junit-xml could not write %s: %s\n"
                             % (PROG, opts.junit_xml, error))
            unwritten = True

    # After the render, because staging the screenshots is part of it and it is
    # the step that finds out an image a bundle named is not in the bundle.
    _report_notes(result, opts.quiet)
    _print_summary(result, report, junit)

    if unwritten: return EXIT_FAILED

    return _exit_code(result, opts, warnings)


# --------------------------------------------------------------------------
# junit
# --------------------------------------------------------------------------

def junit_command(args):
    """Merge the same way and write only the XML.

    No report, so no screenshots are copied and no archive is rotated - which
    is exactly why this exists as its own subcommand rather than as a flag on
    ``merge``: a pipeline that publishes test results into GitLab or Azure and
    keeps no HTML at all should not have to write a build it will throw away.
    """
    opts = _options(args, html_report="", junit_xml=args.output)

    try:
        result = _merged(args.paths, opts)
    except (MergeError, shards.BundleTooNew) as error:
        return _fail(str(error))

    # No report base is passed to the options below, so the attachment lines
    # fall back to the same relative path the HTML page uses - correct whenever
    # the XML is written beside a report that a `merge` produced from the same
    # bundles, which is the only place those images ever exist.
    _shard_scope_screenshots(result.records)

    if opts.dry_run:
        _report_notes(result, opts.quiet)
        _print_summary(result)

        return _exit_code(result, opts, [])

    junit_options = _junit_options(result, opts, "", opts.quiet)

    try:
        junit = write_junit(opts.junit_xml, result.records, options=junit_options)
    except (OSError, ValueError) as error:
        # The one thing this subcommand exists to produce, so unlike the merge
        # it really has produced nothing: exit 2, and no summary of a document
        # that is not there.
        return _fail("-o could not write %s: %s" % (opts.junit_xml, error))

    _report_notes(result, opts.quiet)
    _print_summary(result, junit=junit)

    return _exit_code(result, opts, junit_options.warnings)


# --------------------------------------------------------------------------
# inspect
# --------------------------------------------------------------------------

def inspect_command(args):
    """Say what is there and what merging it would come to, writing nothing.

    The question this answers is "did all four artifacts arrive, and do they
    overlap" - asked before a merge in CI, and asked by hand when the totals on
    a merged report were not the totals somebody expected.
    """
    opts = _options(args, html_report="", dry_run=True)

    try:
        result = _merged(args.paths, opts)
    except (MergeError, shards.BundleTooNew) as error:
        return _fail(str(error))

    if args.json:
        json.dump(_inspect_payload(result), sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")

        return EXIT_OK

    for bundle in result.bundles:
        sys.stdout.write("%s\n" % _bundle_line(bundle))

    _report_notes(result, opts.quiet)
    _print_summary(result, provenance=False)

    return EXIT_OK


# --------------------------------------------------------------------------
# the parser
# --------------------------------------------------------------------------

def _add_paths(parser):
    """The bundles to read - the one argument all three subcommands take."""
    parser.add_argument(
        "paths", nargs="*", default=DEFAULT_PATHS, metavar="PATH",
        help="directories to search for shard bundles, or records.json files named "
             "directly (default: the current directory)")


def _add_shaping(parser):
    """The three flags that decide what the merged record list is.

    Shared by all three subcommands because they decide the answer, not the
    output: `inspect` reporting a different set of tests from the `merge` that
    follows it would make it useless as a pre-flight check.
    """
    parser.add_argument(
        "--on-duplicate", choices=DUPLICATE_POLICIES, default="merge",
        help="what to do when one nodeid ran in more than one shard: merge folds the "
             "attempts and counts them as reruns, first/last keep one, worst keeps the most "
             "severe, error stops the merge (default: merge)")

    parser.add_argument(
        "--order", choices=ORDERS, default="shard",
        help="row order: shard keeps each suite's rows in shard order, name sorts by suite "
             "and test name (default: shard)")

    parser.add_argument(
        "--strip-path-prefix", action="append", default=[], metavar="PREFIX",
        help="strip this prefix from the front of every nodeid, so shards that ran under "
             "different checkout roots group into one suite; repeatable")


def _add_junit_flags(parser):
    """The flags that shape the XML, shared by `merge` and `junit`."""
    parser.add_argument(
        "--junit-suite-name", default="pytest", metavar="NAME",
        help="the <testsuite> name (default: pytest)")

    parser.add_argument(
        "--junit-hostname", default="", metavar="NAME",
        help="the hostname attribute; by default the shards' single host, or 'merged' when "
             "they ran on more than one - never the machine doing the merging")

    parser.add_argument(
        "--junit-xpass", choices=JUNIT_XPASS_MODES, default="pass",
        help="how an unexpectedly passing test is written down (default: pass)")

    parser.add_argument(
        "--junit-logging", choices=JUNIT_LOGGING_MODES, default="no",
        help="which tests carry their captured output (default: no)")

    parser.add_argument(
        "--junit-attachments", dest="junit_attachments", action="store_true", default=True,
        help="write [[ATTACHMENT|...]] lines for screenshots (default)")

    parser.add_argument(
        "--no-junit-attachments", dest="junit_attachments", action="store_false",
        help="leave the screenshots out of the XML")


def _add_outcome_flags(parser):
    """How this command answers, rather than what it produces."""
    parser.add_argument(
        "--strict", action="store_true",
        help="exit 1 when anything was quarantined, unreadable, folded or missing; the "
             "report is still written")

    parser.add_argument(
        "--exit-code", action="store_true",
        help="exit 1 when the merged build has any failure or error")

    parser.add_argument(
        "--dry-run", action="store_true",
        help="merge and print the summary, writing nothing")

    parser.add_argument(
        "-q", "--quiet", action="store_true",
        help="suppress the per-decision notes; errors still print")


def build_parser():
    """The whole command line, as one parser."""
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Merge sharded pytest-html-reporter runs into one report and one "
                    "JUnit XML.")

    parser.add_argument("--version", action="version", version="%s %s" % (PROG, __version__))

    commands = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)

    # ---- merge -----------------------------------------------------------
    merge = commands.add_parser(
        "merge", help="merge shard bundles into one report",
        description="Merge every shard bundle under PATH into one build - one report, one "
                    "output.json, one archived build and one trend point.")

    _add_paths(merge)

    merge.add_argument(
        "--html-report", required=True, metavar="PATH",
        help="where the merged report is written; a folder, or the .html file itself")

    merge.add_argument(
        "--junit-xml", default="", metavar="PATH",
        help="also write the merged JUnit XML here")

    _add_shaping(merge)

    merge.add_argument(
        "--start-time", default="earliest", metavar="WHEN",
        help="the moment this build is filed under - earliest, now, or a unix timestamp; it "
             "names the archive file, stamps output.json and labels the trend point "
             "(default: earliest)")

    merge.add_argument(
        "--report-coverage-file", default="", metavar="PATH",
        help="one already-combined coverage report - json, xml or a .coverage data file")

    merge.add_argument(
        "--coverage-data", action="append", default=[], metavar="PATH",
        help=".coverage data files, or directories holding them, to combine with the "
             "coverage package; repeatable")

    merge.add_argument(
        "--report-coverage-limit", type=int, default=COVERAGE_LIMIT_DEFAULT, metavar="N",
        help="how many files the Coverage tab lists; 0 lists every one (default: %d)"
             % COVERAGE_LIMIT_DEFAULT)

    merge.add_argument(
        "--coverage-target", type=float, default=None, metavar="N",
        help="the percentage this project set for itself, which colours the coverage ring")

    merge.add_argument(
        "--title", default="PYTEST REPORT", metavar="TEXT",
        help="the report's title (default: PYTEST REPORT)")

    merge.add_argument(
        "--environment", default="", metavar="NAME",
        help="the environment under test; by default the one value every shard agreed on")

    merge.add_argument(
        "--build-info", action="append", default=[], metavar="K=V",
        help="a row for the Environment panel; repeatable")

    merge.add_argument(
        "--report-link", action="append", default=[], metavar="LABEL=URL",
        help="a link in the report's nav; repeatable")

    merge.add_argument(
        "--archive-count", default="", metavar="N",
        help="how many builds to keep; empty keeps every one, 0 keeps none")

    merge.add_argument(
        "--archive-days", default=None, metavar="D",
        help="how many days of build history to keep")

    merge.add_argument(
        "--archive-since", default=None, metavar="DATE",
        help="the oldest build to keep, as YYYY-MM-DD or 'YYYY-MM-DD HH:MM'")

    merge.add_argument(
        "--report-open", choices=("auto", "always", "none"), default="none",
        help="whether the finished report is opened in a browser; deliberately not the "
             "pytest run's 'auto', because a merge must not steal a tab (default: none)")

    _add_junit_flags(merge)

    merge.add_argument(
        "--copy-assets", dest="copy_assets", action="store_true", default=True,
        help="copy the screenshots the merged records name into the report (default)")

    merge.add_argument(
        "--no-copy-assets", dest="copy_assets", action="store_false",
        help="leave the screenshots in the shard folders")

    _add_outcome_flags(merge)
    merge.set_defaults(handler=merge_command)

    # ---- junit -----------------------------------------------------------
    junit = commands.add_parser(
        "junit", help="write only the merged JUnit XML",
        description="Merge every shard bundle under PATH and write the JUnit XML, without "
                    "writing a report.")

    _add_paths(junit)

    junit.add_argument(
        "-o", "--output", required=True, metavar="FILE",
        help="where the merged JUnit XML is written")

    _add_shaping(junit)
    _add_junit_flags(junit)
    _add_outcome_flags(junit)
    junit.set_defaults(handler=junit_command)

    # ---- inspect ---------------------------------------------------------
    inspect = commands.add_parser(
        "inspect", help="list the bundles and what merging them would come to",
        description="Print one line per shard bundle and the summary of the merge they "
                    "would produce, writing nothing.")

    _add_paths(inspect)

    inspect.add_argument(
        "--json", action="store_true",
        help="print the same thing as a json document")

    _add_shaping(inspect)

    inspect.add_argument(
        "-q", "--quiet", action="store_true",
        help="suppress the per-decision notes; errors still print")

    inspect.set_defaults(handler=inspect_command)

    return parser


def main(argv=None):
    """The console script. Returns the exit code rather than raising SystemExit.

    argparse leaves by itself with 2 on a usage error, which is the same 2 this
    returns for a merge that could not be started - so a pipeline sees one code
    for "the command was wrong or there was nothing to merge" and never has to
    tell the two apart.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    return args.handler(args)
