"""Fold several shards' records into the one build they were always meant to be.

The merge happens at the level of *records* - the dicts append_test_record
builds - and nowhere else. The two obvious alternatives were both tried on
paper and both lose something that cannot be recovered afterwards:

- Merging output.json files. append_suite_metrics_row (html_reporter.py:1109)
  writes {status, message, test_name, rerun, duration} and nothing else, so the
  totals would be right and every row would be empty, the Logs, Steps,
  Attachments and Screenshots tabs would have nothing to show, and a JUnit file
  built from it could not name a test.
- Merging each shard's rendered html. There is nothing to merge: the page is
  one document with one dashboard, one trend chart and one Analytics view, all
  computed from the records.

Records are dicts of built-in types, which is the whole reason this is
possible: they already survive a round trip through config.workeroutput on an
xdist run, so they survive one through a json file on a CI artifact.

What this module refuses to do, and why:

- It never routes a cross-shard duplicate through HTMLReporter.store_test_record
  (html_reporter.py:690-719). That method exists to fold pytest-rerunfailures
  attempts and only fires when pluginmanager.hasplugin("rerunfailures") is true
  *in the merging process* - so the same four bundles would merge differently
  on a machine that happens to have the plugin installed. It also pins the
  survivor to the superseded record's index, which is a per-process number that
  means nothing once four processes are involved.
- It never concatenates a record's field lists. steps[i]['id'] is an index into
  that record's own step list, and both attachments and screenshots point back
  at a step by position, so splicing two records' steps together re-points every
  attachment at the wrong step.
- It never calls coverage_report.discover_coverage. That function searches
  os.getcwd() (coverage_report.py:610) and stops at the first hit, so a
  coverage.json left in the merging machine's working directory would become
  the build's headline number and be archived into the trend for ever.
- It never averages the shards' coverage percentages. Four percentages over
  four different subsets of the code do not average to anything.
"""

import os
import shutil
import sys
import time
from collections import OrderedDict
from datetime import datetime

from html_page.logs_notice import LogsNotice
from pytest_html_reporter import shards
from pytest_html_reporter.const_vars import ConfigVars, reset_config_vars
from pytest_html_reporter.coverage_report import (
    COVERAGE_LIMIT_DEFAULT,
    coverage_file,
    coverage_limit,
    coverage_mode,
    has_data,
    read_coverage_path,
    summarize_data_file,
)
from pytest_html_reporter.junit import JunitOptions
from pytest_html_reporter.shards import (
    natural_key,
    normalise_record,
    read_bundle,
    report_shard_run,
    shards_root,
)
from pytest_html_reporter.shim import MergeConfig
from pytest_html_reporter.environment import CIRun, packages_row
from pytest_html_reporter.util import (
    archive_count,
    attempt_summary,
    custom_title,
    env_rows,
    environment_label,
    escape_report_text,
)


# What to do when one node id ran in more than one shard. There is no single
# right answer - a matrix that overlaps by accident wants 'merge', a matrix
# that retries a whole leg wants 'last', a gate that must not be fooled wants
# 'error' - so it is asked rather than guessed, and every fold is reported
# whichever is chosen.
DUPLICATE_POLICIES = ('merge', 'first', 'last', 'worst', 'error')

ORDERS = ('shard', 'name')

START_TIMES = ('earliest', 'now')

# Which of two outcomes for the same test is the one worth keeping under
# --on-duplicate worst. A status this version has never heard of scores below
# every real one: it is already reported as unrecognised, and letting an
# unreadable value outrank a genuine FAIL would hide the failure.
STATUS_SEVERITY = {'ERROR': 5, 'FAIL': 4, 'xPASS': 3, 'SKIP': 2, 'xFAIL': 1, 'PASS': 0}
UNKNOWN_SEVERITY = -1

KNOWN_STATUSES = tuple(STATUS_SEVERITY)


class MergeError(Exception):
    """A merge that cannot honestly produce a report.

    Only three things raise it: --on-duplicate error finding a duplicate, a
    --start-time that is not a time, and a coverage combine the caller asked
    for by name. Everything else that goes wrong is a note on the report, on
    the principle the rest of this plugin follows - the tests have already run,
    and a decoration is never worth losing them over.
    """


class MergeOptions(object):
    """Everything the merge is steered by, with the defaults the CLI documents.

    A plain object rather than a namedtuple or a dataclass: the CLI builds it
    from an argparse namespace, the field names are the argparse dests, and
    both of the alternatives make adding a flag a change in two places.
    """

    def __init__(self, html_report='', junit_xml='', on_duplicate='merge', order='shard',
                 strip_path_prefix=None, start_time='earliest', report_coverage='auto',
                 report_coverage_file='', coverage_data=None, report_coverage_limit=None,
                 coverage_target=None, title='PYTEST REPORT', environment='',
                 build_info=None, report_link=None, report_link_pattern=None,
                 archive_count='', archive_days=None,
                 archive_since=None, report_open='none', junit_suite_name='pytest',
                 junit_hostname='', junit_xpass='pass', junit_logging='no',
                 junit_attachments=True, copy_assets=True, strict=False, exit_code=False,
                 dry_run=False, quiet=False, **extra):
        self.html_report = html_report
        self.junit_xml = junit_xml
        self.on_duplicate = on_duplicate
        self.order = order
        self.strip_path_prefix = list(strip_path_prefix or [])
        self.start_time = start_time
        self.report_coverage = report_coverage
        self.report_coverage_file = report_coverage_file
        self.coverage_data = list(coverage_data or [])
        self.report_coverage_limit = report_coverage_limit
        self.coverage_target = coverage_target
        self.title = title
        self.environment = environment
        self.build_info = list(build_info or [])
        self.report_link = list(report_link or [])

        # Declared rather than left to **extra. The CLI always passes it, but
        # the --report-shard-merge leg builds a MergeOptions of its own with
        # only the handful of fields it cares about, and an undeclared field is
        # an AttributeError the moment build_merge_config reads it.
        self.report_link_pattern = list(report_link_pattern or [])
        self.archive_count = archive_count
        self.archive_days = archive_days
        self.archive_since = archive_since

        # Never the plugin's 'auto'. A merge run on somebody's laptop to look
        # at four downloaded artifacts must not steal a browser tab.
        self.report_open = report_open

        self.junit_suite_name = junit_suite_name
        self.junit_hostname = junit_hostname
        self.junit_xpass = junit_xpass
        self.junit_logging = junit_logging
        self.junit_attachments = junit_attachments
        self.copy_assets = copy_assets
        self.strict = strict
        self.exit_code = exit_code
        self.dry_run = dry_run
        self.quiet = quiet

        # Flags a later version adds are carried rather than rejected, so a CLI
        # and a merge module that are half a release apart still work together.
        for name, value in extra.items():
            setattr(self, name, value)


# --------------------------------------------------------------------------
# 1. discover
# --------------------------------------------------------------------------

def load_bundles(paths, notes=None):
    """Every readable bundle under `paths`, unordered.

    Discovery and reading are one step because they fail the same way: a folder
    of CI artifacts holds junit.xml files, logs and a coverage report beside the
    bundles, and every one of them is walked past with a note rather than
    treated as a failure. A bundle from a newer format is the exception and
    raises shards.BundleTooNew.
    """
    bundles = []

    for path in shards.find_bundles(paths):
        bundle = read_bundle(path, notes)
        if bundle is shards.NOT_A_BUNDLE: continue

        bundles.append(bundle)

    return bundles


# --------------------------------------------------------------------------
# 2. order - deterministic, and never load order
# --------------------------------------------------------------------------

def order_bundles(bundles, notes=None):
    """The bundles in the one order this merge will ever put them in.

    Sorted by the natural key of the shard id, so "2-4" comes before "10-16",
    with the id and then the file path breaking ties. Load order is never used
    for anything: two CI jobs downloading the same four artifacts in different
    orders have to produce the same report, or the diff between two builds is
    unreadable.
    """
    bundles = sorted(bundles, key=lambda b: (natural_key(b.shard.id), b.shard.id, b.path))

    # Two files claiming one id: keep the one that finished later. A CI leg
    # that was retried and whose artifact landed twice is common, recoverable,
    # and not worth failing a merge over - the later run is the one whose
    # result the pipeline acted on.
    kept = OrderedDict()
    for bundle in bundles:
        prior = kept.get(bundle.shard.id)

        if prior is None:
            kept[bundle.shard.id] = bundle
            continue

        newer, older = (bundle, prior) if bundle.run.session_end > prior.run.session_end else (prior, bundle)
        kept[bundle.shard.id] = newer

        if notes is not None:
            notes.append("two bundles claim the shard id %s; kept %s (it finished later), "
                         "ignored %s" % (bundle.shard.id, newer.path, older.path))

    ordered = list(kept.values())

    # Assigned after the collapse rather than before it, so the ordinals are
    # dense and a tie broken on them is broken on a position somebody reading
    # the report can count to.
    for ordinal, bundle in enumerate(ordered):
        bundle.ordinal = ordinal

    return ordered


# --------------------------------------------------------------------------
# 3. normalise
# --------------------------------------------------------------------------

def normalise_nodeid(nodeid, prefixes=()):
    """One node id, in the form the merge compares identities on.

    Two machines can run the same test under different roots - a Windows
    runner's backslashes, a container that checked the repo out at /src and a
    runner that used /home/runner/work - and the same test under two spellings
    is two rows, two histories in Analytics and two entries in the JUnit file.

    Separators first, then the prefixes the caller named, because a prefix is
    typed the way the path is read rather than the way the shard happened to
    write it.
    """
    text = str(nodeid or '').replace('\\', '/')

    while '//' in text:
        text = text.replace('//', '/')

    while text.startswith('./'):
        text = text[2:]

    for prefix in prefixes:
        prefix = str(prefix or '').replace('\\', '/').strip()
        while prefix.startswith('./'):
            prefix = prefix[2:]
        if not prefix: continue

        if text.startswith(prefix):
            stripped = text[len(prefix):].lstrip('/')

            # A prefix that swallows the whole node id leaves nothing to
            # identify the test by, and an empty node id is quarantined. The
            # original is worth more than that.
            if stripped: text = stripped

    return text


def _normalise_stream(bundle, opts, quarantined):
    """One bundle's records, repaired, re-identified and tagged with its shard."""
    stream = []

    for raw in bundle.records:
        record = normalise_record(raw)

        if not record['nodeid']:
            # Dropped rather than fatal. A record with no node id cannot be
            # grouped, sorted against a duplicate or linked to, and the merge
            # runs after every test in the matrix has finished - which is the
            # worst moment there is to raise.
            quarantined.append((bundle.shard.id, record))
            continue

        nodeid = normalise_nodeid(record['nodeid'], opts.strip_path_prefix)

        if nodeid != record['nodeid']:
            record['nodeid'] = nodeid

            # Recomputed rather than stripped on its own: html_reporter.py:475
            # derives suite_name from the node id in exactly this way, so
            # grouping follows identity instead of drifting away from it.
            record['suite_name'] = nodeid if record['collect'] else nodeid.split('::')[0]

        # Private, and ridden along for the whole merge: which shard a row came
        # from is what names its screenshots, orders it against its neighbours
        # and goes into its JUnit <system-out>.
        record['_shard'] = bundle.shard.id

        # And separately on every screenshot, because a row and its pictures do
        # not always come from the same bundle. The 'merge' duplicate policy
        # keeps the last shard's record and back-fills its empty 'screenshots'
        # from a loser - so a test that failed and was photographed on shard 1
        # and then passed on shard 2 ends up as a shard-2 row holding shard-1
        # images. Looking those up under the row's shard finds nothing, and the
        # picture of the only failure in the matrix is dropped as "not in the
        # bundle" while it sits on disk in the shard next door.
        record['screenshots'] = _tag_shots(record['screenshots'], bundle.shard.id)

        stream.append(record)

    return stream


def _tag_shots(shots, shard_id):
    """Copies of `shots`, each remembering the shard whose folder holds its png.

    Copies rather than the entries themselves: normalise_record's list() is a
    shallow one, so the dicts inside are still the bundle's own, and a merge
    that wrote into them would change what a second merge in the same process
    reads. The tag is private to the merge, like a record's own '_shard'; every
    template reads screenshots by name and ignores the keys it does not know.
    """
    tagged = []

    for entry in shots:
        if not isinstance(entry, dict): continue

        entry = dict(entry)
        entry['_shard'] = shard_id
        tagged.append(entry)

    return tagged


def shot_shard(entry, record):
    """The shard whose bundle holds this screenshot's png.

    The entry's own tag when it has one, and the row's shard for anything that
    reached here another way - a hand-assembled record list in a test, say.
    """
    return str(entry.get('_shard') or record.get('_shard') or '')


# --------------------------------------------------------------------------
# 4. one record per test
# --------------------------------------------------------------------------

def _severity(record):
    return STATUS_SEVERITY.get(record['status'], UNKNOWN_SEVERITY)


def _first_non_empty(records, field):
    for record in records:
        if record.get(field):
            return record[field]

    return None


def merge_records(streams, on_duplicate='merge', notes=None, folds=None):
    """(collection records, test records) - one of each per node id.

    Steps 4a and 4b of the merge. Collectors and tests are separated because
    they are deduplicated on completely different grounds: every process
    collects the whole suite, so a broken import is *expected* in all four
    bundles and is not a duplicate at all, while the same test running in two
    shards means the matrix overlaps and somebody has to be told.
    """
    notes = notes if notes is not None else []
    folds = folds if folds is not None else []

    # ---- 4a. collection errors ----
    collects = OrderedDict()

    for bundle, records in streams:
        for record in records:
            if not record['collect']: continue

            prior = collects.get(record['nodeid'])

            if prior is None:
                collects[record['nodeid']] = record
            elif prior['status'] == 'SKIP' and record['status'] == 'ERROR':
                # A file that failed to import on one machine failed to import,
                # full stop. Another machine skipping it - a platform marker, a
                # missing optional dependency - does not make the import work.
                notes.append("collection: ERROR from %s supersedes SKIP for %s"
                             % (bundle.shard.id, record['nodeid']))
                collects[record['nodeid']] = record
            elif record['status'] == prior['status'] and len(record['message']) > len(prior['message']):
                # Same verdict twice: keep the text that says more. One runner
                # often has the traceback another one truncated.
                collects[record['nodeid']] = record

    # ---- 4b. duplicate node ids ----
    groups = OrderedDict()
    for bundle, records in streams:
        for record in records:
            if record['collect']: continue

            groups.setdefault(record['nodeid'], []).append(record)

    tests = []
    clashes = []

    for nodeid, members in groups.items():
        if len(members) == 1:
            tests.append(members[0])
            continue

        ids = [member['_shard'] for member in members]
        notes.append("nodeid ran in %d shards: %s (%s)" % (len(members), nodeid, ", ".join(ids)))

        if on_duplicate == 'error':
            clashes.append((nodeid, ids))
            continue

        if on_duplicate == 'first':
            kept = keep = members[0]
        elif on_duplicate == 'last':
            kept = keep = members[-1]
        elif on_duplicate == 'worst':
            # The ordinal breaks a tie, so two shards reporting the same status
            # resolve to the earlier one and the answer does not depend on
            # which artifact was downloaded first.
            kept = keep = max(enumerate(members), key=lambda pair: (_severity(pair[1]), -pair[0]))[1]
        else:
            # `kept` is the member itself and `keep` the copy that is folded
            # into and shipped. The two are tracked separately because the
            # fold note below is written by identity, and a copy is not the
            # member it was copied from - which had the survivor naming itself
            # in its own list of dropped shards.
            kept = members[-1]
            keep = dict(kept)

            # Every member is an attempt at this test, and each one may already
            # stand for several - that is what a rerun-folded record is. The
            # ones being dropped are attempts too, hence the + (len - 1).
            keep['rerun'] = sum(int(member['rerun']) for member in members) + (len(members) - 1)

            # And what those attempts did, so a test that failed on one shard
            # and passed on another can still say what it failed with. Shard
            # order, not clock order: the shards ran at the same time on
            # different machines, so there is no true order to put them in, and
            # the survivor's own retries come last because they came before the
            # outcome the row now shows.
            trail = []
            for member in members[:-1]:
                trail.extend(member.get('attempts') or [])
                trail.append(attempt_summary(member))
            keep['attempts'] = trail + list(kept.get('attempts') or [])

            # Back-fill only what the survivor is missing, from the latest
            # loser that has it, exactly as store_test_record does for a retry:
            # a shard that captured the failing response should not lose it
            # because another shard then passed. Never a concatenation - see
            # the module docstring.
            for field in ('screenshots', 'attachments', 'steps'):
                if not keep.get(field):
                    keep[field] = _first_non_empty(list(reversed(members[:-1])), field) or []

        folds.append({
            'nodeid': nodeid,
            'kept': keep['_shard'],
            'dropped': [member['_shard'] for member in members if member is not kept],
            'statuses': [member['status'] for member in members],
        })
        tests.append(keep)

    if clashes:
        raise MergeError(
            "--on-duplicate error: %d node id(s) ran in more than one shard:\n%s"
            % (len(clashes), "\n".join("  %s  (%s)" % (nodeid, ", ".join(ids))
                                       for nodeid, ids in clashes)))

    return list(collects.values()), tests


# --------------------------------------------------------------------------
# 5. global index rebasing
# --------------------------------------------------------------------------

def order_records(collects, tests, ordinals, order='shard'):
    """Every record renumbered so build_report's own sort becomes a no-op.

    `index` is a per-*process* collection position (html_reporter.py:592). Four
    shards each number their tests 0..n-1, so build_report's
    sorted(records, key=(index, worker)) (html_reporter.py:729) has four
    records claiming index 0 and the stable sort falls back to whatever order
    the bundles were loaded in - which is the one thing this merge has spent
    two steps making sure never decides anything.

    Renumbering densely here rather than teaching build_report a cleverer sort
    key is deliberate: build_report is on the live pytest path for every run of
    this plugin, and it is not touched.
    """
    collect_rows = sorted(collects, key=lambda r: (ordinals.get(r['_shard'], 0), r['nodeid']))

    for position, record in enumerate(collect_rows):
        # -N .. -1: a total order among themselves, and still ahead of every
        # test, which is what html_reporter.py:236 intends by giving a
        # collection failure index -1 in the first place.
        record['index'] = -len(collect_rows) + position

    if order == 'name':
        tests.sort(key=lambda r: (r['suite_name'], r['test_name'],
                                  ordinals.get(r['_shard'], 0), r['nodeid']))
    else:
        # Suites in order of first appearance, so a suite split across shards
        # keeps its rows contiguous in index space as well as in the grouping
        # build_report does anyway - otherwise the table shows the same file
        # twice, once per shard.
        order_of_suite = {}
        for position, record in enumerate(tests):
            order_of_suite.setdefault(record['suite_name'], position)

        tests.sort(key=lambda r: (order_of_suite[r['suite_name']],
                                  ordinals.get(r['_shard'], 0), int(r['index']),
                                  r['worker'], r['nodeid']))

    for position, record in enumerate(tests):
        # 0..n-1 and unique, so 'worker' - the second half of build_report's
        # sort key, and a name that means nothing across machines - never
        # breaks a tie again.
        record['index'] = position

    return collect_rows + tests


# --------------------------------------------------------------------------
# 6. run metadata
# --------------------------------------------------------------------------

class ShardMeta(object):
    """One shard's account of itself, for the Environment panel.

    Seven fields rather than the four the merge strictly needs to order rows,
    because naming the machine each leg ran on is this panel's whole job on a
    merged build: a row reading only "runner-3" says less than the merging
    host's row used to, and that row was at least complete about a machine that
    ran none of the tests.
    """

    def __init__(self, bundle):
        self.id = bundle.shard.id
        self.label = bundle.shard.label or bundle.shard.id
        self.hostname = bundle.run.hostname
        # The distribution-and-architecture string when the shard wrote one,
        # and the kernel string every older bundle carries when it did not.
        self.platform = bundle.run.os or bundle.run.platform
        self.python = bundle.run.python_detail or bundle.run.python
        self.pytest = bundle.run.pytest
        self.arguments = bundle.run.arguments
        self.workers = len([worker for worker in (bundle.run.xdist_workers or []) if worker])

    @property
    def summary(self):
        """The one line the Environment panel shows for this shard.

        Only what the shard actually reported: a leg that could not name its
        platform contributes no separator either, rather than a row reading
        "runner-3 ·  · Python".
        """
        terms = [
            self.hostname,
            self.platform,
            ("Python " + self.python) if self.python else "",
            ("pytest " + self.pytest) if self.pytest else "",
            # A leg that split itself four ways and a leg that ran serially are
            # two different runs, and on a merged report this line is the only
            # place that difference can still be seen.
            ("%d workers" % self.workers) if self.workers > 1 else "",
            self.arguments,
        ]

        return " · ".join(term for term in terms if str(term).strip())


class RunMeta(object):
    """What the merged build says about the machines that produced it."""

    def __init__(self):
        self.session_start = 0.0
        self.session_end = 0.0
        self.wall = 0.0
        self.hosts = []
        self.platforms = []
        self.pythons = []
        self.pytests = []
        self.plugins = []
        self.shards = []
        self.environment = ''
        self.build_info = []
        self.capture_rows = []
        self.capture_notices = []
        self.notes = []

        # What the shards said about the run itself rather than about their own
        # machines: which CI build produced the matrix, which commit it was cut
        # from, and - when somebody asked for it - what was installed.
        self.ci = ''
        self.pipeline = ''
        self.branch = ''
        self.commit = ''
        self.package_rows = []


def _unique(values):
    """The distinct non-empty values, in the order they were first seen."""
    seen = OrderedDict()

    for value in values:
        value = str(value or '').strip()
        if value:
            seen.setdefault(value, None)

    return list(seen)


def merge_runs(bundles):
    """One RunMeta describing the whole matrix, from every bundle's own account.

    Not one machine's answer generalised to all of them. The Environment panel
    on a merged report would otherwise confidently describe the host that ran
    the merge - which ran none of the tests.
    """
    meta = RunMeta()
    if not bundles: return meta

    starts = [float(b.run.session_start) for b in bundles if b.run.session_start]
    ends = [float(b.run.session_end) for b in bundles if b.run.session_end]

    meta.session_start = min(starts) if starts else time.time()
    meta.session_end = max(ends) if ends else meta.session_start

    # The span of the matrix, not the sum of the legs: four shards that each
    # took ten minutes in parallel took ten minutes, and the header says so.
    meta.wall = max(0.0, meta.session_end - meta.session_start)

    meta.hosts = _unique(b.run.hostname for b in bundles)
    meta.platforms = _unique(b.run.platform for b in bundles)
    meta.pythons = _unique(b.run.python for b in bundles)
    meta.pytests = _unique(b.run.pytest for b in bundles)
    meta.plugins = sorted({str(name) for b in bundles for name in (b.run.plugins or [])})

    meta.shards = [ShardMeta(b) for b in bundles]

    environments = _unique(b.run.environment for b in bundles)
    if len(environments) == 1:
        meta.environment = environments[0]
    elif environments:
        # Left blank rather than picked. The badge names the environment the
        # whole build ran against, and there is no such thing here.
        meta.notes.append("shards disagree about the environment (%s); the badge is left empty"
                          % ", ".join(environments))

    # First occurrence per key wins, so the shard that sorts first decides -
    # deterministically - what "Commit" says when two legs disagree.
    info = OrderedDict()
    for bundle in bundles:
        for pair in (bundle.run.build_info or []):
            if len(pair) < 2: continue
            info.setdefault(str(pair[0]), str(pair[1]))
    meta.build_info = list(info.items())

    meta.capture_rows = [(b.shard.label or b.shard.id, b.run.capture_row) for b in bundles]
    meta.capture_notices = [(b.shard.label or b.shard.id, b.run.capture_notice)
                            for b in bundles if b.run.capture_notice]

    _merge_identity(meta, bundles)

    return meta


def _ci_summary(ci):
    """The one line a shard's recorded CI run reads as, or ''.

    Rebuilt through CIRun rather than formatted here, so the row on a merged
    report and the row on a plain one are assembled by the same code and cannot
    drift apart. Unknown keys are dropped: a bundle from a newer version may
    carry more than this one knows how to read, and that is not a reason to
    refuse the four fields it does know.
    """
    if not isinstance(ci, dict):
        return ''

    fields = {key: str(ci.get(key) or '') for key in ('system', 'label', 'build', 'url')}

    return CIRun(**fields).summary


def _merge_identity(meta, bundles):
    """Which build, which commit and which packages the matrix as a whole was.

    Agreement is the normal case and gets one row. Disagreement is not smoothed
    over - a matrix whose legs ran different commits is a matrix whose results
    should not have been merged, and the panel saying both is how anybody finds
    that out.
    """
    summaries = _unique(_ci_summary(b.run.ci) for b in bundles)
    meta.ci = ", ".join(summaries)

    urls = _unique(str((b.run.ci or {}).get('url') or '') if isinstance(b.run.ci, dict) else ''
                   for b in bundles)
    if len(urls) == 1:
        meta.pipeline = urls[0]
    elif urls:
        # No single link is the honest answer here, and a link to the first
        # shard's pipeline would be read as the whole build's.
        meta.notes.append("shards name %d different pipelines; the panel links none of them"
                          % len(urls))

    def _git(bundle, key):
        return str(bundle.run.git.get(key) or '') if isinstance(bundle.run.git, dict) else ''

    meta.branch = ", ".join(_unique(_git(b, 'branch') for b in bundles))
    meta.commit = ", ".join(_unique(_git(b, 'commit') for b in bundles))

    listed = [(b.shard.label or b.shard.id, list(b.run.packages or [])) for b in bundles
              if b.run.packages]

    if listed and len({tuple(packages) for _, packages in listed}) == 1:
        # One environment, described once. The label is dropped because there
        # is nothing to tell apart - and because eight identical three-hundred
        # entry rows is not a panel, it is a wall.
        meta.package_rows = [('', listed[0][1])]
    else:
        meta.package_rows = listed


# --------------------------------------------------------------------------
# 7. coverage
# --------------------------------------------------------------------------

def _combine_coverage(paths, root, limit):
    """(summary, notice) for a set of .coverage data files combined into one.

    Copied into a temporary directory first, because coverage.py's combine()
    deletes the files it read - and these are somebody's CI artifacts, which
    are very often the only copy.
    """
    import coverage  # noqa: F401  - only reached once the caller has checked it imports
    import tempfile

    directory = tempfile.mkdtemp(prefix='pytest-html-reporter-combine-')

    try:
        copies = []
        for position, path in enumerate(paths):
            copy = os.path.join(directory, '.coverage.%d' % position)
            shutil.copyfile(path, copy)
            copies.append(copy)

        target = os.path.join(directory, '.coverage')
        combined = coverage.Coverage(data_file=target)
        combined.combine(copies)
        combined.save()

        summary = summarize_data_file(target, root, limit)

        if not has_data(summary):
            return None, ("--coverage-data named %d file(s) and the combined data measured "
                          "nothing." % len(paths))

        summary['source'] = "%d combined data files" % len(paths)

        return summary, ''
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def _coverage_data_files(entries):
    """The .coverage data files named by --coverage-data, files and folders alike."""
    files = []

    for entry in entries:
        entry = os.path.expanduser(os.path.expandvars(str(entry)))

        if os.path.isdir(entry):
            for name in sorted(os.listdir(entry)):
                if name.startswith('.coverage'):
                    files.append(os.path.join(entry, name))
        elif os.path.isfile(entry):
            files.append(entry)

    return files


def merge_coverage(bundles, opts, root=''):
    """(summary, notice) - the merged build's coverage, and why it may be empty.

    Five branches, in this order, and no sixth. There is no combine story in
    this codebase to inherit: nothing calls coverage.combine(), and
    discover_coverage searches os.getcwd() and stops at the first hit
    (coverage_report.py:610), so letting it run here would let a stale
    coverage.json on the merging machine become this build's number - and
    output.json archives that number, so the wrong figure would sit in the
    trend chart for as long as the archive is kept.

    A summary of None means no 'coverage' key is written into output.json at
    all, which archived_coverage (html_reporter.py:100) reads as "not
    measured". That is a different answer from zero, and it is the true one.
    """
    if str(opts.report_coverage or 'auto').strip().lower() == 'none':
        return None, ''

    limit = opts.report_coverage_limit
    limit = COVERAGE_LIMIT_DEFAULT if limit in (None, '') else int(limit)

    if opts.report_coverage_file:
        summary = read_coverage_path(opts.report_coverage_file, root, limit)
        if has_data(summary):
            return summary, ''

        return None, ("--report-coverage-file pointed at %s, and nothing there could be read "
                      "as coverage data." % opts.report_coverage_file)

    if opts.coverage_data:
        files = _coverage_data_files(opts.coverage_data)

        try:
            import coverage  # noqa: F401
        except ImportError:
            return None, ("--coverage-data needs the coverage package to combine data files; "
                          "it is not installed in the environment running the merge.")

        if not files:
            return None, ("--coverage-data named nothing that looks like a coverage data "
                          "file (.coverage, .coverage.*).")

        try:
            return _combine_coverage(files, root, limit)
        except Exception as error:
            # A merge that otherwise succeeded must not fail over a decoration.
            return None, ("the coverage data files named with --coverage-data could not be "
                          "combined: %s" % error)

    measured = [bundle for bundle in bundles if bundle.coverage]

    if len(measured) == 1:
        summary = measured[0].coverage
        if len(bundles) == 1:
            return summary, ''

        return summary, ("1 of %d shards measured coverage, so this figure covers that shard's "
                         "share of the run." % len(bundles))

    if len(measured) > 1:
        return None, ("%d shards were merged and their coverage cannot be reconciled. Combine "
                      "the data first - `coverage combine && coverage json` - and pass the "
                      "result with --report-coverage-file, or pass the shards' data files "
                      "with --coverage-data." % len(bundles))

    return None, ("%d shards were merged and none of them was asked for coverage. Run the "
                  "shards under pytest-cov, then combine the data - `coverage combine && "
                  "coverage json` - and pass the result with --report-coverage-file."
                  % len(bundles))


# --------------------------------------------------------------------------
# the merge itself
# --------------------------------------------------------------------------

class MergeResult(object):
    """Everything one merge produced, before anything has been rendered.

    Kept whole and returned rather than printed, so `inspect` and `--dry-run`
    can report exactly what a real merge would have done without writing a
    byte.
    """

    def __init__(self, bundles, records, meta, coverage=None, coverage_notice='',
                 notes=None, quarantined=None, folds=None, missing_assets=None):
        self.bundles = bundles
        self.records = records
        self.meta = meta
        self.coverage = coverage
        self.coverage_notice = coverage_notice
        self.notes = list(notes or [])
        self.quarantined = list(quarantined or [])
        self.folds = list(folds or [])
        self.missing_assets = list(missing_assets or [])

    @property
    def tests(self):
        return [record for record in self.records if not record.get('collect')]

    @property
    def collects(self):
        return [record for record in self.records if record.get('collect')]

    @property
    def failed(self):
        """Whether this build has anything --exit-code should report."""
        return any(record['status'] in ('FAIL', 'ERROR') for record in self.records)

    @property
    def clean(self):
        """Whether --strict has nothing to complain about."""
        return not (self.quarantined or self.folds or self.missing_assets
                    or self.unrecognised)

    @property
    def unrecognised(self):
        """Records whose status this version has never heard of.

        Flagged rather than absorbed: update_counts derives its error total as
        "everything that was not one of the others" (html_reporter.py:1160), so
        a status from a version-skewed bundle would silently become an error
        with nobody told where it came from.
        """
        return [record for record in self.records
                if record['status'] and record['status'] not in KNOWN_STATUSES]


def merge_bundles(bundles, opts):
    """Steps 2 to 7: bundles in, one build's worth of records out.

    A pure function over the loaded bundles - nothing is written, nothing is
    rendered, and ConfigVars is not touched. That is what makes --dry-run and
    `inspect` honest, and what makes the whole of this testable without a
    filesystem.
    """
    notes = []
    quarantined = []
    folds = []

    bundles = order_bundles(bundles, notes)
    ordinals = {bundle.shard.id: bundle.ordinal for bundle in bundles}

    streams = [(bundle, _normalise_stream(bundle, opts, quarantined)) for bundle in bundles]

    collects, tests = merge_records(streams, opts.on_duplicate, notes, folds)
    records = order_records(collects, tests, ordinals, opts.order)

    meta = merge_runs(bundles)
    notes.extend(meta.notes)

    summary, coverage_notice = merge_coverage(bundles, opts)

    for shard_id, record in quarantined:
        notes.append("quarantined a record from %s with no node id (%r); it cannot be "
                     "grouped or linked to" % (shard_id, record['test_name']))

    return MergeResult(bundles, records, meta, summary, coverage_notice,
                       notes, quarantined, folds)


# --------------------------------------------------------------------------
# screenshots
# --------------------------------------------------------------------------

def _within(root, candidate):
    """True when `candidate` really does sit under `root` once both are resolved."""
    root = os.path.abspath(root)
    candidate = os.path.abspath(candidate)

    return candidate == root or candidate.startswith(root + os.sep)


def stage_assets(bundles, records, out_base, notes=None):
    """Copy every png the merged records name into the report's own folder.

    By the names the records hold, never by globbing the shard's folder.
    clean_screenshots is a silent no-op when --html-report names an .html file
    (util.py:87 appends '/pytest_screenshots' to the file path), so a shard
    folder can be holding images from a previous build of the same leg, and
    sweeping the folder would carry them into this report as tests that did not
    run in it.

    Each shard's images land in a folder of their own because screenshot_name()
    is <milliseconds>[-<worker>]-<counter> with the counter restarting at 1 in
    every process - so two machines' first screenshots are both "<ms>-1", and
    one would overwrite the other in a shared folder.

    The '<shard>/<name>' the record then carries needs no template change:
    test_shot.html and screenshot_details.html both build
    "pytest_screenshots/" + name + ".png" by plain concatenation, and
    escape_report_text leaves '/' alone (util.py:513-522). One field feeds all
    three render sites - the metrics strip, the Screenshots card and the step
    tree - so rewriting it here fixes all three at once.
    """
    notes = notes if notes is not None else []
    missing = []

    target_root = os.path.join(out_base, 'pytest_screenshots')

    # The merge owns this folder: one build comes out of one merge, and an
    # image left over from the last one would be shown as part of this one.
    if os.path.isdir(target_root):
        shutil.rmtree(target_root)

    sources = {bundle.shard.id: bundle.assets_dir for bundle in bundles}

    for record in records:
        shots = []

        for entry in (record.get('screenshots') or []):
            entry = dict(entry)

            # The shard that took the picture, which is not always the shard
            # this row was kept from - see _tag_shots. Reading the row's shard
            # here is what dropped a back-filled image as missing while it lay
            # on disk under the shard that actually photographed it.
            shard_id = shot_shard(entry, record)
            name = str(entry.get('name') or '')

            source = os.path.join(sources.get(shard_id, ''), name + '.png')

            if not name or not os.path.isfile(source):
                # Dropped rather than left pointing at nothing: a card with a
                # broken image reads as a bug in the report, and the note says
                # which file the bundle promised and did not carry.
                missing.append(source)
                notes.append("screenshot named by %s is not in the bundle and was dropped: %s"
                             % (record['nodeid'], source))
                continue

            destination = os.path.join(target_root, shard_id, name + '.png')

            # The check that does not depend on normalise_record having run.
            # Both halves of this path came out of a bundle, and a merge is not
            # entitled to write outside the folder it was pointed at whatever a
            # downloaded artifact says - so a name that still resolves out of
            # the tree is dropped and named rather than followed.
            if not _within(target_root, destination):
                missing.append(source)
                notes.append("screenshot named by %s would be written outside the report "
                             "folder and was dropped: %s" % (record['nodeid'], name))
                continue

            os.makedirs(os.path.dirname(destination), exist_ok=True)

            try:
                shutil.copyfile(source, destination)
            except (shutil.Error, OSError) as exc:
                # An unreadable source, a name the filesystem will not take, or
                # a source that is already the destination. The build is worth
                # more than the thumbnail, so the row keeps everything else.
                missing.append(source)
                notes.append("screenshot named by %s could not be copied and was dropped: %s"
                             % (record['nodeid'], exc))
                continue

            entry['name'] = shard_id + '/' + name
            shots.append(entry)

        if record.get('screenshots'):
            record['screenshots'] = shots

    return missing


# --------------------------------------------------------------------------
# the environment panel and the logs notice
# --------------------------------------------------------------------------

def _pairs(entries):
    """(label, value) out of the "K=V" strings a --build-info flag collects.

    The same split util.build_info does, so the merge flag and the pytest flag
    are written the same way by the same person on the same day.
    """
    pairs = []

    for entry in entries:
        entry = str(entry).strip()
        if not entry: continue

        key, _, value = entry.partition("=")
        pairs.append((key.strip(), value.strip()))

    return pairs


def _env_rows(entries):
    """The panel's rows, rendered exactly the way a plain run renders them.

    Kept as a name of its own because the merge's tests call it, but no longer
    a second implementation: an entry carrying a url has to become a link here
    too, and two row builders is how one of them quietly stops doing that.
    """
    return env_rows(entries)


def merged_environment_rows(meta, opts):
    """Fill the Environment panel from every shard, and return the rows.

    This *replaces* generate_environment_info rather than following it:
    util.py:322 assigns ConfigVars._environment_rows, it does not append, so a
    call and then an append would simply be a call.

    Every row here is something a shard reported about itself. The panel on a
    merged report used to be the one part of the page that could not be
    honest - the merging machine's host, platform, Python and arguments,
    describing a process that ran no tests at all.
    """
    environment = str(opts.environment or meta.environment or '').strip()

    ConfigVars._environment = environment
    ConfigVars._environment_label, was_cut = environment_label(environment)
    ConfigVars._environment_class = "is-truncated" if was_cut else ""

    entries = []
    if environment:
        entries.append(("Environment", environment))

    named = _pairs(opts.build_info)
    entries += named

    # The shards' own build info, minus anything the merge flag already said.
    given = {label for label, _ in named}
    entries += [(label, value) for label, value in meta.build_info if label not in given]

    # What the shards recorded about the run they belonged to. Anything a
    # --build-info flag already answered - on the merge or on a leg - is left
    # alone, the same way it is on a plain run: a team that publishes its own
    # Commit row means that one.
    stated = {str(label).strip().lower() for label, _ in named} | \
             {str(label).strip().lower() for label, _ in meta.build_info}

    if meta.ci and "ci" not in stated:
        entries.append(("CI", meta.ci))
    if meta.pipeline and "pipeline" not in stated:
        entries.append(("Pipeline", meta.pipeline, meta.pipeline))
    if meta.branch and "branch" not in stated:
        entries.append(("Branch", meta.branch))
    if meta.commit and "commit" not in stated:
        entries.append(("Commit", meta.commit))

    captured = _unique(row for _, row in meta.capture_rows)
    if len(captured) == 1:
        entries.append(("Captured output", captured[0]))
    else:
        # A matrix where one leg ran with -s and the others did not is exactly
        # the case where one summarised row would be a lie, so each leg answers
        # for itself.
        entries += [("Captured output (%s)" % label, row) for label, row in meta.capture_rows if row]

    entries.append(("Generated", datetime.now().strftime("%b %d %Y, %H:%M:%S")))
    entries.append(("Merged from", "%d shard%s" % (len(meta.shards),
                                                   "" if len(meta.shards) == 1 else "s")))

    # One row per leg, and the only rows on this panel that name a machine.
    entries += [("Shard %s" % shard.label, shard.summary) for shard in meta.shards]

    # Last, because it is the longest thing on the panel by two orders of
    # magnitude and everything above it is read first.
    for label, packages in meta.package_rows:
        row = packages_row(packages)
        if not row:
            continue

        name, value = row
        entries.append(("%s (%s)" % (name, label) if label else name, value))

    ConfigVars._environment_rows = _env_rows(entries)

    return ConfigVars._environment_rows


def merged_logs_notice(meta):
    """Say why the Logs column may be empty, using the shards' own explanations.

    Read off each shard's config while it ran, not off the merge's. Under the
    shim getoption("capture") is None, so util._capture_is_off is false and the
    "-s suppressed stdout and stderr" sentence would silently vanish - leaving
    a column of dashes with nothing to explain it.
    """
    ConfigVars._logs_notice = ""

    if not meta.capture_notices:
        return ""

    distinct = _unique(text for _, text in meta.capture_notices)

    if len(distinct) == 1:
        text = distinct[0]
    else:
        text = "; ".join("%s: %s" % (label, note) for label, note in meta.capture_notices)

    ConfigVars._logs_notice = str(LogsNotice(text=escape_report_text(text)))

    return text


# --------------------------------------------------------------------------
# the merged junit document
# --------------------------------------------------------------------------

def merged_junit_options(result, **overrides):
    """The JunitOptions describing one merged document, wherever it is written.

    Two callers write a merged JUnit xml - the `merge` and `junit` subcommands,
    and the --report-shard-merge leg, which writes it from HTMLReporter.render()
    with the same flag a plain run uses. They must not disagree: a CI system
    reading `<property name="shard.ids">` or the `shard: 1/4 (runner-1)` line in
    a testcase's <system-out> would otherwise get them from one flow and not the
    other, and "which machine ran this test" is exactly what those two facts are
    there to answer. So the four things only a merge knows - the shards, the
    matrix's clock, the reruns and the folds - are settled once, here, and the
    caller overrides only what its own flags gave it.

    ``hostname`` is the shards' single host when the matrix happened to run on
    one machine and the literal ``merged`` otherwise - never this machine, which
    ran none of the tests and which Azure would otherwise name as the agent that
    did. A caller with a --junit-hostname flag passes it as an override.
    """
    meta = result.meta

    options = dict(
        hostname=meta.hosts[0] if len(meta.hosts) == 1 else "merged",

        # The earliest shard's start and the span of the whole matrix, because
        # Azure computes the end of the run as timestamp + SUM(testcase@time)
        # and would otherwise read a forty-minute matrix as the seconds the
        # merge took.
        timestamp=meta.session_start,
        time=meta.wall,

        shards=dict((shard.id, (shard.label, shard.hostname)) for shard in meta.shards),
        reruns=sum(int(record.get("rerun") or 0) for record in result.records),
        duplicates=len(result.folds),
    )

    # An override that was never given - an unset --junit-hostname arriving as
    # '' - must not overwrite the answer worked out above with nothing.
    options.update((name, value) for name, value in overrides.items() if value not in (None, ''))

    return JunitOptions(**options)


# --------------------------------------------------------------------------
# 8. render, once
# --------------------------------------------------------------------------

def _start_stamp(meta, start_time):
    """The timestamp this build is filed under.

    It names the file the *next* build archives this one as, stamps
    output.json['start_time'], labels the point on the trend chart and orders
    the builds in Analytics - so it is asked about rather than assumed.
    """
    value = str(start_time or 'earliest').strip().lower()

    if value == 'now': return time.time()
    if value == 'earliest': return meta.session_start

    try:
        return float(start_time)
    except (TypeError, ValueError):
        raise MergeError(
            "--start-time takes earliest, now or a unix timestamp, not %r" % start_time)


def _merge_config(opts):
    """The Config stand-in the merged render is driven with."""
    return MergeConfig(
        options={
            'path': opts.html_report,
            'title': opts.title,
            'environment': opts.environment,
            'build_info': list(opts.build_info),
            'report_link': list(opts.report_link),
            'report_link_pattern': list(opts.report_link_pattern),
            'archive_count': opts.archive_count,
            'archive_days': opts.archive_days,
            'archive_since': opts.archive_since,
            'report_open': opts.report_open,
            'report_coverage_limit': opts.report_coverage_limit,
            # Answered to coverage_target, which is what colours the ring
            # against the bar the project set for itself. Not read as a
            # coverage source: that arrives through the reporter's seam,
            # already decided by merge_coverage.
            'cov_fail_under': opts.coverage_target,
        },
        args=sys.argv[1:],
    )


def render_merged(result, opts):
    """Drive the existing render pipeline once, over the merged records.

    Not a second implementation of the report. Everything the page shows -
    the dashboard, the archive rotation, the trend, the run delta, Suite
    Highlights, Analytics, the Coverage tab - comes out of HTMLReporter.render()
    exactly as it does for a plain pytest run, because a merged build that is
    assembled by different code is a build that drifts away from every other
    one on the report's own history.

    Returns the reporter, so the caller can name the file it wrote.
    """
    # Imported here rather than at the top: html_reporter imports this module
    # for the --report-shard-merge path, and a plain import at module level
    # would close that circle at interpreter start.
    from pytest_html_reporter.html_reporter import HTMLReporter

    meta = result.meta
    stamp = _start_stamp(meta, opts.start_time)

    # Before custom_title and before the reporter exists. generate_json_data
    # accumulates _aspass.._asrerun with += (html_reporter.py:1344-1358) and the
    # template renders that family rather than the one update_counts assigns, so
    # a second merge in one process would double every number on the dashboard
    # and raise nothing at all.
    reset_config_vars()
    custom_title(opts.title)

    config = _merge_config(opts)
    reporter = HTMLReporter(opts.html_report, archive_count(config), config)

    # Belt and braces. store_test_record is not used by this path at all, and
    # this is the flag that decides what it would do if it ever were.
    reporter.rerun_plugin = False

    # Assigned directly, never through store_record: these records are already
    # unique per node id and already renumbered, and store_test_record would
    # fold or duplicate them a second time on rules that have nothing to do
    # with a matrix.
    reporter._records = result.records

    reporter._sessionstarttime = meta.session_start

    # The span of the matrix, not the seconds this merge took. A report whose
    # header reads "0.4 secs" for a forty-minute run is worse than no header.
    reporter._execution_seconds = meta.wall

    # _date() derives from this, so a matrix that started before midnight and
    # was merged after it is dated the day it ran.
    reporter._build_time = stamp

    ConfigVars._start_execution_time = stamp

    summary, notice = result.coverage, result.coverage_notice
    reporter.coverage_source = lambda base: (summary, notice)
    reporter.environment_source = lambda: merged_environment_rows(meta, opts)
    reporter.logs_notice_source = lambda: merged_logs_notice(meta)

    if opts.copy_assets:
        result.missing_assets.extend(
            stage_assets(result.bundles, result.records, reporter.report_path[0], result.notes))

    reporter.render()

    return reporter


# --------------------------------------------------------------------------
# provenance
# --------------------------------------------------------------------------

def provenance_lines(bundles):
    """One line per merged bundle: which leg, how many tests, when it finished.

    Printed by both merges, every time, with no threshold anywhere near it.
    There is no honest way to decide from inside a merge that a bundle is
    stale: every bundle beside a merging leg was written before it, whether
    ten minutes ago by this run or yesterday by the last one. So nothing is
    guessed and the times are simply shown, which is what turns yesterday's leg
    from a silent extra two tests in the totals into a line in the log of the
    run that merged it.

    Local time on purpose. This is read beside a CI log whose own timestamps
    are on the same clock, and asking a reader to convert a UTC stamp before
    they can notice a bundle is a day old is asking them not to notice.
    """
    lines = []

    for bundle in bundles:
        tests = len([record for record in bundle.records if not record.get('collect')])
        finished = float(bundle.run.session_end or 0.0)

        # A bundle with no session_end is one that was hand-assembled or
        # written by a version that did not record it. Saying so is better
        # than printing the epoch, which reads as a real date.
        when = (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(finished))
                if finished else "at a time it did not record")

        lines.append("shard %s: %d test%s, finished %s"
                     % (bundle.shard.id, tests, "" if tests == 1 else "s", when))

    return lines


def bundles_from_this_run(bundles, token):
    """Split the bundles into the ones this run wrote and the ones it did not.

    A merging leg with no token merges everything, which is what it has always
    done and the only thing it can do: an empty token says nothing about which
    run a bundle came from, and refusing to merge on the strength of it would
    break every matrix that does not run on a CI system this plugin recognises.
    That case is answered by --report-shard-reset instead.

    A leg that has one keeps only the bundles carrying the same one. A bundle
    with no token at all is a bundle from before the leg was given one, or from
    a run that was started by hand, and it is not this run's - so it is put
    aside and named rather than merged, because the failure it causes is
    invisible: the totals are simply larger than the run was.
    """
    if not token: return list(bundles), []

    mine = []
    foreign = []

    for bundle in bundles:
        if str(bundle.run.token or '') == token:
            mine.append(bundle)
        else:
            foreign.append(bundle)

    return mine, foreign


# --------------------------------------------------------------------------
# the --report-shard-merge path
# --------------------------------------------------------------------------

def merge_into(reporter):
    """Point a live reporter at every shard beside it, ready to render once.

    The sequential case: three legs on one machine, the last of them passing
    --report-shard-merge so that three commands do the work of four. This leg
    has already written its own bundle, so the bundles under <base>/shards are
    the whole run - which is why _records is replaced rather than added to.

    "The whole run" is the qualification that matters: that folder is
    persistent, so it also holds whatever the last run left in it. A leg with a
    run token merges only the bundles carrying the same one and says what it
    put aside; a leg without one merges everything, as it always has, and every
    bundle it merged is named on stderr with the time it was written so that a
    leg from yesterday is visible rather than silently two more tests.

    reset_config_vars() is deliberately NOT called here, unlike in
    render_merged: this process configured itself as a normal pytest run, and
    resetting would throw away the title custom_title stored in
    pytest_configure along with everything else set before the tests ran.

    Returns the MergeResult, or None when there was nothing to merge.
    """
    config = reporter.config
    base = reporter.report_path[0]

    notes = []
    root = shards_root(base)
    bundles = load_bundles([root], notes)

    # Before anything is counted, and before the no-bundles check below, so
    # that a folder holding nothing but another run's leftovers is reported as
    # what it is rather than merged into this build.
    token = report_shard_run(config)
    bundles, foreign = bundles_from_this_run(bundles, token)

    if foreign:
        described = ", ".join(
            "%s (%s)" % (bundle.shard.id, str(bundle.run.token or '') or 'no run token')
            for bundle in foreign)

        sys.stderr.write(
            "pytest-html-reporter: %d bundle%s under %s came from another run and %s not "
            "merged - this run's token is %s and they carry: %s\n"
            % (len(foreign), "" if len(foreign) == 1 else "s", root,
               "was" if len(foreign) == 1 else "were", token, described))
        sys.stderr.write(
            "pytest-html-reporter: clear %s between runs, or give the first leg of a run "
            "--report-shard-reset, to stop them accumulating\n" % root)

    if not bundles:
        for note in notes:
            sys.stderr.write("pytest-html-reporter: %s\n" % note)
        return None

    opts = MergeOptions(
        html_report=reporter.path,
        report_coverage=coverage_mode(config),
        report_coverage_file=coverage_file(config),
        report_coverage_limit=coverage_limit(config),
        # Left empty on purpose: this leg's own bundle carries the environment
        # and the build info it was given, so they arrive through merge_runs
        # alongside the other legs' rather than being imposed by whichever leg
        # happened to be last.
        environment='',
    )

    result = merge_bundles(bundles, opts)
    result.notes = notes + result.notes

    meta = result.meta

    reporter._records = result.records
    reporter._sessionstarttime = meta.session_start
    reporter._execution_seconds = meta.wall
    reporter._build_time = meta.session_start

    # The archive filename, the trend label and Analytics' build order all read
    # this, and it currently holds the last test's setup time.
    ConfigVars._start_execution_time = meta.session_start

    summary, notice = result.coverage, result.coverage_notice
    reporter.coverage_source = lambda coverage_base: (summary, notice)
    reporter.environment_source = lambda: merged_environment_rows(meta, opts)
    reporter.logs_notice_source = lambda: merged_logs_notice(meta)

    # So that --report-junit on this leg writes the same document the merge
    # command would have written from these bundles - the shard properties, the
    # matrix's timestamp and span, and a `shard: 1/4 (runner-1)` line naming the
    # leg by the label it was given rather than by the directory it was filed
    # under. Only xpass is this run's own, because --report-junit-xpass is the
    # one shaping flag a pytest run has.
    reporter.junit_options = merged_junit_options(
        result, xpass=reporter.junit_xpass, report_base=base,
        trace_markers=reporter.trace_markers)

    result.missing_assets.extend(
        stage_assets(bundles, result.records, base, result.notes))

    # Said out loud on every merge, not only when something looks wrong. The
    # build this leg is about to write is made of these bundles and nothing
    # else, and this is the only place that is ever recorded.
    for line in provenance_lines(result.bundles):
        sys.stderr.write("pytest-html-reporter: merged %s\n" % line)

    for note in result.notes:
        sys.stderr.write("pytest-html-reporter: %s\n" % note)

    return result
