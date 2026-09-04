"""One leg of a sharded run, written out whole so another process can render it.

A matrix that splits a suite across four machines has four processes that each
know a quarter of the run, and none of them can write the report: a build is
one set of totals, one archived output.json, one trend point and one entry in
every per-test history Analytics reconstructs. Four processes writing four
reports into one folder do not add up to that, they overwrite each other and
manufacture four builds out of one.

So a shard writes no report at all. It writes this file - its records, exactly
as they stand in memory, plus what it alone knows about the machine it ran on -
and the merge builds the one report from all of them.

Why the whole record list rather than something smaller:

- output.json is not an interchange format. append_suite_metrics_row
  (html_reporter.py:1109-1120) keeps {status, message, test_name, rerun,
  duration} per test - no node id, no logs, no steps, no attachments, no
  phases. A merge built on it would produce correct totals over an empty
  report, and could not name a single test in a JUnit file.
- The records need no serialiser. append_test_record (html_reporter.py:584-608)
  already builds every one of them out of JSON-safe built-ins, precisely so an
  xdist worker can ship its list to the controller through config.workeroutput,
  so logs, steps, attachments, phases, meta, bdd, worker and index all travel
  losslessly and this module transforms nothing on the way out.

Screenshots are the one exception and travel as real files inside the shard
directory: collect_screenshots (html_reporter.py:1021-1067) writes the png and
stores only a bare name, and both screenshot templates concatenate
"pytest_screenshots/" + that name + ".png" into an href and a src, so a data
URI could not be rendered even if the bytes were worth carrying.

The shard is a *directory* under the report base - <base>/shards/<id>/ - and
never a bare file beside the report. That is what makes

    pytest-html-reporter merge ./report --html-report ./report

safe: the merge clears ./report/pytest_screenshots, while every source image
sits in ./report/shards/<id>/pytest_screenshots and is untouched.
"""

import json
import os
import platform
import re
import shutil
import sys
import tempfile
import time

import pytest

from pytest_html_reporter import __version__
from pytest_html_reporter.util import (
    _ini,
    _invocation_args,
    _plugin_versions,
    build_info,
    capture_notice,
    capture_summary,
    environment_name,
    report_logs_mode,
)


# The exact string a bundle has to carry to be one. Anything else is somebody
# else's json that happens to be called records.json, and is skipped rather
# than parsed hopefully.
SHARD_SCHEMA = "pytest-html-reporter/records"

# Bumped only when a reader that does not know about the change would get the
# wrong answer. A bundle claiming a higher version is refused by name rather
# than read on the chance that nothing important moved.
SHARD_VERSION = 1

# version -> a function that takes that version's payload and returns the next
# one's. Empty at v1, and deliberately here rather than added later: it is the
# thing that lets v2 add a key without every artifact already on a CI server
# becoming unreadable.
_UPGRADES = {}

# The file inside a shard directory, and the name the merge looks for when it
# is pointed at a folder of downloaded artifacts.
RECORDS_FILENAME = "records.json"

# The subdirectory of the shard holding its pngs, mirroring the name the
# report itself uses so a bundle reads the same way as a report folder.
ASSETS_DIRNAME = "pytest_screenshots"

# Characters that survive sanitisation. Everything else becomes '-': shard ids
# come from CI matrix values ("1/4", "python3.11 (ubuntu)") and end up as a
# directory name and as part of a screenshot path inside the report.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")
_RUNS = re.compile(r"-+")

# Long enough for "python3.12-ubuntu-latest-integration", short enough that the
# staged screenshot path stays inside every filesystem's per-component limit.
SHARD_ID_MAX = 64

# ini values that mean yes for the boolean flags in this feature. The pytest
# flags are store_true and need none of this; an ini key is text and somebody
# will write "true".
_TRUTHY = ("1", "true", "yes", "on")

# The CI variables a run token is derived from when nobody names one, in the
# order they are looked at. Each entry's first variable is the one that has to
# be set for the entry to answer at all; the rest are appended when they are
# there. Every answer carries the name of the system it came from, so that
# Jenkins build 41 and Drone build 41 cannot produce the same token and have
# two unrelated runs' bundles merged into one build.
#
# Every name here was read off the system's own documentation rather than
# remembered. GitHub Actions' GITHUB_RUN_ID is unique within a repository and
# deliberately does not change when a workflow is re-run, which is exactly why
# GITHUB_RUN_ATTEMPT - 1 for the first attempt, incremented for each re-run -
# is carried beside it: a re-run of a matrix must not answer the token its
# first attempt's bundles are already stamped with. GitLab's CI_PIPELINE_ID is
# unique across the whole instance. Jenkins' BUILD_TAG is
# jenkins-${JOB_NAME}-${BUILD_NUMBER} and is preferred to the bare
# BUILD_NUMBER, which only counts within one job. CircleCI's
# CIRCLE_WORKFLOW_ID is the same for every job in a workflow instance, which
# is precisely the matrix. Buildkite's BUILDKITE_BUILD_ID is the build's uuid,
# Azure Pipelines' Build.BuildId reaches a script as BUILD_BUILDID, and
# Travis, AppVeyor and Drone each name their build directly.
#
# TeamCity is last and is the one entry that is not a run id at all:
# BUILD_VCS_NUMBER is the revision that was built, so two runs of the same
# commit share it and the second would be allowed to merge the first's
# bundles. It is a last resort rather than an answer, and it is rarely
# reached: TeamCity also sets BUILD_NUMBER, so a TeamCity leg is normally
# answered by the Jenkins entry above and labelled jenkins. That mislabelling
# is cosmetic - the prefix is there to keep two systems' numbering apart, and
# it still does that.
_CI_RUN_VARIABLES = (
    ('github', ('GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT')),
    ('gitlab', ('CI_PIPELINE_ID',)),
    ('jenkins', ('BUILD_TAG',)),
    ('jenkins', ('BUILD_NUMBER',)),
    ('circleci', ('CIRCLE_WORKFLOW_ID',)),
    ('buildkite', ('BUILDKITE_BUILD_ID',)),
    ('azure', ('BUILD_BUILDID',)),
    ('travis', ('TRAVIS_BUILD_ID',)),
    ('appveyor', ('APPVEYOR_BUILD_ID',)),
    ('drone', ('DRONE_BUILD_NUMBER',)),
    ('teamcity', ('BUILD_VCS_NUMBER',)),
)


# Every key build_report and the row builders index without asking whether it
# is there, with the value each of them would rather have than a KeyError. This
# is the whole defence against a bundle written by another version of this
# plugin: build_report sorts on hard r['index'] and r['worker']
# (html_reporter.py:729) and append_test_metrics_row indexes eight more, so one
# absent key does not degrade the report, it ends the merge with a traceback
# after every test has already run.
RECORD_DEFAULTS = {
    'suite_name': '', 'test_name': '', 'nodeid': '', 'status': '', 'message': '',
    'duration': 0.0, 'rerun': 0, 'index': 0, 'worker': '',
    'screenshots': [], 'logs': [], 'attachments': [], 'steps': [],
    'phases': {}, 'meta': {}, 'bdd': None, 'xfail_reason': '',
}

_STRING_FIELDS = ('suite_name', 'test_name', 'nodeid', 'status', 'message', 'worker', 'xfail_reason')
_INT_FIELDS = ('index', 'rerun')
_LIST_FIELDS = ('screenshots', 'logs', 'attachments', 'steps')
_DICT_FIELDS = ('phases', 'meta')


class BundleTooNew(Exception):
    """A bundle written by a newer pytest-html-reporter than this one.

    Raised rather than skipped, and named rather than counted: silently
    dropping a quarter of a matrix produces a report that is wrong in a way
    nobody looking at it can see.
    """


class _NotABundle(object):
    """The answer for a file that is json, or is not, but is not one of ours."""

    def __repr__(self):
        return 'NOT_A_BUNDLE'

    def __bool__(self):
        return False


# A singleton so callers can write `if bundle is NOT_A_BUNDLE`, which is the
# one test that cannot be confused with a bundle that merely holds no records.
NOT_A_BUNDLE = _NotABundle()


# --------------------------------------------------------------------------
# options
# --------------------------------------------------------------------------

def report_shard(config):
    """This process's shard name as it was typed, or '' when it is not a shard.

    The raw value, not the sanitised one: it is what the report shows as the
    shard's label, and "1/4" reads better there than "1-4".
    """
    value = config.getoption("report_shard", None)
    if value is None or str(value).strip() == "":
        value = _ini(config, "report_shard")

    return str(value or "").strip()


def report_shard_merge(config):
    """Whether this leg also merges every shard beside it and renders.

    For the sequential case - unit, then integration, then e2e, on one machine -
    where a fourth command to merge the three is a fourth thing to remember.
    """
    if config.getoption("report_shard_merge", None):
        return True

    return str(_ini(config, "report_shard_merge") or "").strip().lower() in _TRUTHY


def ci_run_token(environ=None):
    """A token naming the CI run this process is part of, or '' off a CI system.

    `environ` is an argument so that this can be answered about a mapping that
    is not this process's own, which is the only way to test it without
    editing os.environ underneath a running suite.
    """
    environ = os.environ if environ is None else environ

    for name, variables in _CI_RUN_VARIABLES:
        values = [str(environ.get(variable) or "").strip() for variable in variables]

        # The first variable is the one that identifies the system. An entry
        # whose second variable is missing still answers, so a GitHub Actions
        # runner too old to set GITHUB_RUN_ATTEMPT gets a token rather than
        # falling through to somebody else's variable.
        if not values[0]: continue

        return "%s:%s" % (name, "-".join(value for value in values if value))

    return ""


def report_shard_run(config):
    """Which CI run this leg belongs to, or '' when nothing says.

    --report-shard-run beats the report_shard_run ini key, which beats whatever
    the CI system's own variables say, which beats nothing at all.

    This exists because the sequential flow points every leg at one persistent
    --html-report, so <base>/shards accumulates: a leg that is renamed or
    deleted between two CI runs leaves its bundle sitting there and the next
    run's --report-shard-merge picks it up and reports tests that did not run.
    Four tests run and the build says six, with nothing on the page saying
    where the other two came from. The token is what tells the two cases apart
    from inside a single leg, which a clock cannot: every bundle beside a
    merging leg was written before it, whether ten minutes ago by this run or
    yesterday by the last one.
    """
    value = config.getoption("report_shard_run", None)
    if value is None or str(value).strip() == "":
        value = _ini(config, "report_shard_run")

    value = str(value or "").strip()
    if value: return value

    return ci_run_token()


def report_shard_reset(config):
    """Whether this leg empties <base>/shards before it writes into it.

    The deterministic answer for a sequential flow that has no run token to
    filter on: the first leg of a run says --report-shard-reset, and whatever
    the last run left behind is gone before this one writes a byte. Never
    implied by anything else - not by --report-shard, not by
    --report-shard-merge - because it deletes the other legs' work, and a flag
    that does that has to be the one the user typed.
    """
    if config.getoption("report_shard_reset", None): return True

    return str(_ini(config, "report_shard_reset") or "").strip().lower() in _TRUTHY


def sanitise_id(value):
    """A shard id fit to be a directory name, or '' when nothing was asked for.

    The id names a directory under the report base and a folder of screenshots
    inside the report, so it cannot carry a separator or anything a filesystem
    argues about. A value that is entirely made of such characters - "//" - is
    a usage error rather than a silent fallback: a shard whose id came out
    empty would write over the report base itself.

    Dots are stripped from both ends for the same reason, and this is not
    tidiness: '.' and '..' are made entirely of characters the pattern below
    considers safe, so "--report-shard=.." would come through untouched and
    shard_dir would hand back <base>/shards/.., which is <base>. That shard
    would then empty the report's own pytest_screenshots folder, file its
    pictures there and drop its bundle in the report base - exactly the
    outcome the empty-id check above exists to prevent, reached by a value
    that is not empty. A dot inside the id ("1.4", "python3.11") is left
    alone; only the ends are trimmed.
    """
    value = str(value or "").strip()
    if not value: return ""

    cleaned = _RUNS.sub("-", _UNSAFE.sub("-", value)).strip("-.")[:SHARD_ID_MAX].strip("-.")

    if not cleaned:
        raise pytest.UsageError(
            "--report-shard takes a name for this shard, not %r" % value)

    return cleaned


def shards_root(base):
    """The folder every leg of a run files its own directory under.

    Named on its own because two callers talk about the whole of it rather
    than about one leg: --report-shard-reset empties it, and a merging leg
    names it when it says which directory holds bundles it would not merge.
    """
    return os.path.join(base, 'shards')


def shard_dir(base, shard_id):
    """Where one shard's bundle lives, under the report base.

    A subtree of the report folder rather than the folder itself, so a merge
    written back into the same folder cannot delete its own sources.
    """
    return os.path.join(shards_root(base), shard_id)


def reset_shard_dir(directory):
    """Remove `directory` outright, before this leg writes anything into it.

    What the shard branch used to do was clean_screenshots(shard directory),
    which empties only <directory>/pytest_screenshots. That leaves everything
    else a previous run of the same leg wrote - a records.json, and the
    .records-*.tmp of a write that was killed - and the stale records.json is
    then what the merge reads and what CI uploads as this leg's artifact. When
    the previous run collected more tests than this one does, the leftovers are
    reported as though they had just run.

    Removing the whole directory is also simply what the branch means: a leg
    owns its own directory and nothing outside it, and everything inside it
    belongs to the run starting now. The same function empties the whole of
    <base>/shards for --report-shard-reset, which is the same statement made
    about every leg at once.
    """
    if not os.path.isdir(directory): return

    shutil.rmtree(directory)


def natural_key(text):
    """A sort key that reads runs of digits as numbers, so "2-4" sorts before "10-16".

    Shard ids are almost always numbered, and plain string order puts the tenth
    shard second. The merge orders everything - rows, index numbering, the
    Environment panel - off this, so an ordering that surprises here is an
    ordering that surprises everywhere.

    Each part is a three-tuple whose first member says which kind it is, so a
    number is never compared against a string on any Python.
    """
    key = []

    for part in re.split(r"(\d+)", str(text)):
        if not part: continue

        if part.isdigit():
            key.append((0, int(part), ""))
        else:
            key.append((1, 0, part))

    return tuple(key)


# --------------------------------------------------------------------------
# records
# --------------------------------------------------------------------------

def safe_shot_name(value):
    """One screenshot's file name, reduced to something that cannot leave a folder.

    The name is put into a path twice over - the merge reads
    <bundle>/pytest_screenshots/<name>.png and writes
    <out>/pytest_screenshots/<shard>/<name>.png - and it comes out of a bundle,
    which is a file downloaded from CI rather than anything this process wrote.
    An absolute name takes over the whole os.path.join and lands the copy
    outside the report directory entirely; a '..' walks out of it a level at a
    time. screenshot_name() only ever produces '<ms>[-<worker>]-<n>', so
    flattening to a bare name costs a real run nothing.
    """
    name = str(value or '').replace('\\', '/')
    name = os.path.basename(name)

    return '' if name in ('.', '..') else name


def normalise_record(raw):
    """One record with every key present and every type the report expects.

    A bundle can have been written by a different release of this plugin, by a
    version that had not grown a field yet, or by one that had already changed
    it - and it arrives after the tests have finished, which is the worst
    moment to raise. Every key in RECORD_DEFAULTS is filled in and coerced, so
    the sort in build_report and the eight hard lookups in the row builders
    cannot fail on it.

    Unknown keys are kept exactly as they came, so a bundle from a newer minor
    version loses nothing on the way through.
    """
    record = dict(raw or {})

    for name, default in RECORD_DEFAULTS.items():
        record.setdefault(name, default)

    for name in _STRING_FIELDS:
        record[name] = str(record[name]) if record[name] is not None else ''

    # Tolerant rather than strict: a duration that arrives as the string "1.2"
    # or as None is a decoration on a row, and no reason to lose the row.
    try:
        record['duration'] = float(record['duration'])
    except (TypeError, ValueError):
        record['duration'] = 0.0

    for name in _INT_FIELDS:
        try:
            record[name] = int(record[name])
        except (TypeError, ValueError):
            record[name] = 0

    for name in _LIST_FIELDS:
        record[name] = list(record[name]) if isinstance(record[name], (list, tuple)) else []

    for name in _DICT_FIELDS:
        record[name] = dict(record[name]) if isinstance(record[name], dict) else {}

    # Flattened at the boundary rather than trusted by each of the three places
    # that build a path out of it. An entry that is not a mapping at all is
    # dropped: every consumer indexes it by key.
    shots = []
    for entry in record['screenshots']:
        if not isinstance(entry, dict): continue

        entry = dict(entry)
        entry['name'] = safe_shot_name(entry.get('name'))
        shots.append(entry)

    record['screenshots'] = shots

    # Left exactly as it is: None for a plain pytest test, a dict for a
    # pytest-bdd scenario, and the tab keys off which of the two it got.
    record.setdefault('bdd', None)

    # Always present, so the merge can split collectors from tests with a plain
    # lookup rather than a get() that has to guess what a missing key means.
    record['collect'] = bool(record.get('collect'))

    return record


# --------------------------------------------------------------------------
# writing a bundle
# --------------------------------------------------------------------------

def _collected_count(reporter):
    """How many tests a leg was given, counted from its records.

    The fallback for an xdist controller, whose own _collected is empty because
    pytest_collection_modifyitems never fires there - the workers collect. The
    tests only: a collection error is a record about a *file* that yielded no
    tests at all, and counting it would have a leg that collected nothing
    report one.
    """
    return len([record for record in reporter._records if not record.get('collect')])


def describe_run(reporter, exitstatus):
    """What this process alone knows: its machine, its arguments, its clock.

    Captured here, in the shard, because the merge runs somewhere else - often
    on a machine that ran none of the tests. Everything in this dict is
    something the merging process would otherwise answer about itself and be
    wrong about.
    """
    config = reporter.config
    uname = platform.uname()

    workers = sorted({str(record.get('worker') or '') for record in reporter._records} - {''})

    return {
        # The honest start of this leg, not ConfigVars._start_execution_time:
        # that is reset by every pytest_runtest_setup, so by the time the report
        # is written it holds the last test's setup time.
        'session_start': float(reporter._sessionstarttime or time.time()),
        'session_end': time.time(),
        'exitstatus': int(exitstatus or 0),
        # Which CI run this leg belongs to, so that a merging leg can tell this
        # run's bundles from the ones the last run left in the same folder. A
        # new key rather than a version bump: a reader that has never heard of
        # it reads the RUN_DEFAULTS empty string and behaves exactly as it did
        # before, which is the whole reason unknown keys survive a round trip.
        'token': report_shard_run(config),
        # How many tests this leg was given. _collected is filled in by
        # pytest_collection_modifyitems, which never fires on an xdist
        # controller - the workers do the collecting - so an `-n 4` leg would
        # otherwise write 0 beside a bundle holding four hundred records, and
        # this is the number somebody opening the file goes to first.
        'collected': len(reporter._collected) or _collected_count(reporter),
        'hostname': str(uname.node),
        'platform': (str(uname.system) + " " + str(uname.release)).strip(),
        'python': platform.python_version(),
        'pytest': pytest.__version__,
        'plugins': _plugin_versions(config),
        'arguments': _invocation_args(config),
        'rootdir': str(getattr(config, "rootpath", None) or getattr(config, "rootdir", "") or ""),
        'environment': environment_name(config),
        # Pairs as 2-lists because json has no tuples, and a merge that read
        # them back as lists and compared them against tuples would find no
        # build info anywhere.
        'build_info': [[label, value] for label, value in build_info(config)],
        # Both of these are read off the *shard's* config on purpose. Under the
        # merge shim getoption("capture") is None, so _capture_is_off is false
        # and the "-s suppressed stdout" explanation would silently vanish from
        # a merged report - leaving an unexplained column of dashes.
        'capture_row': capture_summary(config, report_logs_mode(config)),
        'capture_notice': capture_notice(config, report_logs_mode(config)),
        'xdist_workers': workers,
    }


def _shard_coverage(reporter):
    """This leg's coverage summary for the bundle, or None.

    Read through the reporter's own seam, so a shard measures coverage exactly
    the way a plain run does. The link to coverage.py's annotated html is
    dropped: it is a path relative to the shard's report base, and the merged
    report is written somewhere else entirely, so keeping it would put a link
    into the page that goes nowhere.

    A failure here is swallowed. The tests have run; losing the coverage tile
    is a decoration, and failing the leg would lose the records with it.
    """
    try:
        summary, _ = reporter.coverage_source(reporter.report_path[0])
    except Exception:
        return None

    if not summary: return None

    summary = dict(summary)
    summary['html'] = ''

    return summary


def shard_payload(reporter, exitstatus):
    """Everything this leg hands to the merge, ready to be written."""
    records = reporter._records
    collect = len([record for record in records if record.get('collect')])

    return {
        'schema': SHARD_SCHEMA,
        'version': SHARD_VERSION,
        'generator': "pytest-html-reporter %s" % __version__,
        'shard': {
            'id': reporter.shard_id,
            'label': report_shard(reporter.config) or reporter.shard_id,
            'assets': ASSETS_DIRNAME,
        },
        'run': describe_run(reporter, exitstatus),
        'coverage': _shard_coverage(reporter),
        # For `inspect`, and never trusted by the merge, which counts the
        # records it actually read.
        'counts': {'records': len(records) - collect, 'collect': collect},
        # Verbatim. Whatever this version of the plugin puts in a record is
        # what the next one reads back out of it.
        'records': records,
    }


def _warn_on_a_different_leg(path, payload):
    """Say so when this write is about to bury a bundle from another leg.

    Overwriting is the everyday case and is right: the sequential flow points
    three legs at one --html-report, and the next CI run points the same three
    at it again. What is never right is two *different* legs landing on one
    directory, which happens because sanitise_id folds separators - "1/4" and
    "1-4" are both "1-4", and so are "ubuntu 22.04" and "ubuntu-22.04". The
    second leg would then replace the first's records with its own and the
    merge would report a matrix a quarter smaller with nothing anywhere saying
    a leg had been lost. The labels are what tell the two cases apart, so they
    are what is compared.

    Never fatal, and never allowed to stop the write: this runs after every
    test in the leg has finished, and losing the bundle over a warning about
    the bundle would be the worse of the two outcomes.
    """
    try:
        if not os.path.isfile(path): return

        with open(path, encoding='utf-8') as handle:
            existing = json.load(handle)

        if existing.get('schema') != SHARD_SCHEMA: return

        was = str((existing.get('shard') or {}).get('label') or '')
        now = str((payload.get('shard') or {}).get('label') or '')

        if was and now and was != now:
            sys.stderr.write(
                "pytest-html-reporter: --report-shard %r and %r both name the "
                "directory %s; this run replaces the other one's records. Give "
                "the two legs names that differ by more than punctuation.\n"
                % (was, now, os.path.dirname(path)))
    except Exception:
        # A directory holding something that is not one of our bundles is the
        # merge's problem to report, not this write's problem to fail over.
        return


def write_bundle(directory, payload):
    """Write records.json into `directory`, atomically, and return its path.

    A shard is written from pytest_terminal_summary, which is the last thing a
    CI leg does before the job is allowed to be cancelled or the runner
    reclaimed. A half-written file is worse than a missing one - the missing
    one is reported as "not a bundle" and the merge carries on, the half one
    would be too if json were the only reader, but it is also what somebody
    would go and look at to find out what happened. Written to a temporary
    file in the same directory, flushed to the disk and renamed over the top,
    so what is there is either the previous file or the whole new one.
    """
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, RECORDS_FILENAME)

    _warn_on_a_different_leg(path, payload)

    handle = tempfile.NamedTemporaryFile(
        mode='w', encoding='utf-8', dir=directory, prefix='.records-',
        suffix='.tmp', delete=False)

    try:
        json.dump(payload, handle)
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        os.replace(handle.name, path)
    except Exception:
        handle.close()
        try:
            os.remove(handle.name)
        except OSError:
            pass
        raise

    return path


# --------------------------------------------------------------------------
# reading a bundle
# --------------------------------------------------------------------------

class _Fields(object):
    """Attribute access over one of a bundle's json sub-objects, with defaults.

    The merge reads b.shard.id and b.run.session_end all over, and a bundle
    written by a version that had not grown one of those keys yet must answer
    the default rather than raise from inside a comprehension.
    """

    def __init__(self, data, defaults):
        merged = dict(defaults)
        merged.update({key: value for key, value in (data or {}).items() if value is not None})
        self._data = merged

    def __getattr__(self, name):
        # Only ever reached for a name that is not an instance attribute, so
        # _data itself never comes through here and cannot recurse.
        try:
            return self.__dict__['_data'][name]
        except KeyError:
            raise AttributeError(name)

    def set(self, name, value):
        self._data[name] = value

    def as_dict(self):
        return dict(self._data)


SHARD_DEFAULTS = {'id': '', 'label': '', 'assets': ASSETS_DIRNAME}

RUN_DEFAULTS = {
    'session_start': 0.0, 'session_end': 0.0, 'exitstatus': 0, 'collected': 0,
    'token': '',
    'hostname': '', 'platform': '', 'python': '', 'pytest': '', 'plugins': [],
    'arguments': '', 'rootdir': '', 'environment': '', 'build_info': [],
    'capture_row': '', 'capture_notice': '', 'xdist_workers': [],
}


class Bundle(object):
    """One shard's file, read.

    `payload` is kept whole rather than picked apart, so keys this version has
    never heard of survive being read and written back out.
    """

    def __init__(self, path, payload):
        self.path = path
        self.directory = os.path.dirname(os.path.abspath(path))
        self.payload = payload

        self.shard = _Fields(payload.get('shard'), SHARD_DEFAULTS)
        self.run = _Fields(payload.get('run'), RUN_DEFAULTS)
        self.coverage = payload.get('coverage') or None
        self.records = list(payload.get('records') or [])
        self.generator = str(payload.get('generator') or '')

        # Where this bundle sits in the merge's deterministic order. Filled in
        # by order_bundles, and read by every step that has to break a tie
        # between two shards the same way twice running.
        self.ordinal = 0

        # The shard whose id is empty still has to be told apart from the next
        # one, or two anonymous bundles collapse into one.
        if not self.shard.id:
            self.shard.set('id', _fallback_id(path))

        # Sanitised on the way in, not only on the way out. A leg sanitises its
        # own id before it writes, but a bundle is a file that arrived from CI,
        # and this id becomes a directory component under the merged report -
        # so an id of '..', or one carrying a separator, would put a staged
        # screenshot somewhere the merge does not own.
        self.shard.set('id', sanitise_id(self.shard.id) or _fallback_id(path))

    @property
    def assets_dir(self):
        """Where this bundle's pngs are, absolute."""
        return os.path.join(self.directory, self.shard.assets or ASSETS_DIRNAME)

    def __repr__(self):
        return "<Bundle %s (%d records)>" % (self.shard.id, len(self.records))


def _fallback_id(path):
    """A shard id for a bundle that carries none - its own directory's name.

    Hand-assembled bundles and artifacts unpacked by a CI step that renamed the
    folder both turn up without one, and an id is what every ordering, every
    screenshot path and every duplicate note is keyed on.
    """
    name = os.path.basename(os.path.dirname(os.path.abspath(path)))

    return sanitise_id(name) if name else 'shard'


def read_bundle(path, notes=None):
    """A Bundle, or NOT_A_BUNDLE; raises BundleTooNew for a newer format.

    Three outcomes rather than two, because they need three different
    reactions. A file that is not a bundle is one of the other files sitting in
    an artifact folder and is skipped without comment beyond a note. A file
    that is a bundle from the future cannot be read correctly and must not be
    read hopefully - it is named and the merge stops. Anything else is a
    bundle.

    `notes` is an optional list that collects the reason a file was rejected,
    so the caller can say which of the twenty files in the folder it walked
    past and why.
    """
    try:
        with open(path, encoding='utf-8') as handle:
            payload = json.load(handle)
    except (OSError, ValueError) as error:
        if notes is not None:
            notes.append("could not be read as json and was skipped: %s (%s)" % (path, error))
        return NOT_A_BUNDLE

    if not isinstance(payload, dict) or payload.get('schema') != SHARD_SCHEMA:
        if notes is not None:
            notes.append("skipped, not a bundle: %s" % path)
        return NOT_A_BUNDLE

    try:
        version = int(payload.get('version') or 0)
    except (TypeError, ValueError):
        version = 0

    if version > SHARD_VERSION:
        raise BundleTooNew(
            "%s was written by a newer pytest-html-reporter (bundle version %d); "
            "this one understands %d" % (path, version, SHARD_VERSION))

    # Walked one version at a time rather than jumped, so a v3 reader gets a v1
    # file through the same two steps a v2 reader took it through.
    while version < SHARD_VERSION and version in _UPGRADES:
        payload = _UPGRADES[version](payload)
        version += 1

    return Bundle(path, payload)


def find_bundles(paths):
    """Every records.json under `paths`, in a stable order, without repeats.

    Files may be named directly - a CI step that unpacks one artifact knows
    exactly where it put it - and directories are walked, because the usual
    shape is one folder holding four downloaded artifacts. The walk is sorted
    at every level so the same folder yields the same list twice running; the
    merge re-orders by shard id afterwards regardless, but a discovery order
    that wobbles makes every intermediate note wobble with it.
    """
    found = []
    seen = set()

    for path in paths:
        path = os.path.expanduser(os.path.expandvars(str(path)))

        if os.path.isfile(path):
            candidates = [path]
        else:
            candidates = []
            for root, directories, files in os.walk(path):
                directories.sort()
                if RECORDS_FILENAME in files:
                    candidates.append(os.path.join(root, RECORDS_FILENAME))
            candidates.sort()

        for candidate in candidates:
            real = os.path.abspath(candidate)
            if real in seen: continue

            seen.add(real)
            found.append(candidate)

    return found
