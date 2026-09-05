"""What machine, interpreter and CI run produced this report.

The Environment panel could name the host, the Python and the pytest, and that
is the easy half of the question a red build actually asks. The other half -
which CI run this came out of, which commit it was cut from, how many workers
split it, and which versions of everything else were installed - was left to
whoever wrote a ``--build-info`` flag before the run. A report is a build
artifact: it is read a week later, on somebody else's laptop, by a person who
cannot re-run it and cannot ask the machine anything. Everything it does not
say about itself is gone.

So every answer here is collected without being asked for, and every one of
them is optional. A checkout that is not a git checkout, a CI system nobody
here has heard of, an ``importlib.metadata`` that trips over a half-installed
distribution - each is worth far less than the report it would otherwise take
down with it, so each is wrapped and each falls back to saying nothing. This
module raises nothing and prints nothing.

The one thing that is *not* collected by default is the installed package list.
It is the only answer here that is hundreds of lines long and the only one that
publishes a full dependency inventory into a file that gets passed around, so
it waits for ``--report-packages``.
"""

import os
import platform
import subprocess
import sys

# A CI variable set to one of these is saying "no". CI=false is a real thing to
# write in a matrix that turns a step off, and reading it as "this is CI" gets
# it exactly backwards. report_opener.py keeps its own copy of this on purpose:
# it answers a different question (may I open a browser?) and must not start
# importing this module to answer it.
FALSEY = ("", "0", "false", "no", "off")

# How much of a commit sha the panel shows. Long enough to be unambiguous in
# any repository anybody is likely to be looking at, short enough to sit beside
# a branch name without wrapping the row.
SHA_LENGTH = 12

# Seconds to wait on `git`. The report is already written by the time this
# runs; a checkout on a slow network mount is not worth holding it up for, and
# a missing revision is a row that does not render rather than a failure.
GIT_TIMEOUT = 3


def _env(name, default=""):
    return str(os.environ.get(name) or default).strip()


def _truthy(name):
    return _env(name).lower() not in FALSEY


# --------------------------------------------------------------------------
# the machine and the interpreter
# --------------------------------------------------------------------------

def _linux_distribution():
    """The distribution's own name for itself, from /etc/os-release.

    ``platform.freedesktop_os_release()`` does this and is 3.10 and newer; this
    package supports 3.7. The file is a handful of KEY=value lines and reading
    the one key needed is smaller than the version check would be.
    """
    for path in ("/etc/os-release", "/usr/lib/os-release"):
        try:
            with open(path, encoding="utf-8") as handle:
                for line in handle:
                    key, sep, value = line.partition("=")
                    if sep and key.strip() == "PRETTY_NAME":
                        return value.strip().strip('"').strip("'")
        except OSError:
            continue

    return ""


def os_summary():
    """The operating system, named the way the people running it name it.

    "Darwin 24.6.0" is the kernel, and nobody reading a report thinks in kernel
    versions - they think "macOS 15.6", "Ubuntu 22.04". The architecture is
    carried along because it is the difference between two machines that agree
    about everything else in this panel and disagree about which wheel got
    installed.
    """
    try:
        uname = platform.uname()
        system = str(uname.system or "").strip()
        release = str(uname.release or "").strip()
        machine = str(uname.machine or "").strip()

        if system == "Darwin":
            version = platform.mac_ver()[0]
            name = ("macOS " + version).strip() if version else "macOS"
        elif system == "Windows":
            version = platform.win32_ver()[0]
            name = ("Windows " + version).strip() if version else "Windows"
        elif system == "Linux":
            distribution = _linux_distribution()
            # Both, when both are known: a wheel is chosen by the distribution
            # and a container bug is explained by the kernel, and the two are
            # routinely different machines' worth of information.
            name = (distribution + " · Linux " + release).strip(" ·") if distribution \
                else (system + " " + release).strip()
        else:
            name = (system + " " + release).strip()

        return (name + " (" + machine + ")") if machine and name else name or machine
    except Exception:
        return ""


def python_summary():
    """Version, implementation and word size of the interpreter running this."""
    try:
        bits = 64 if sys.maxsize > 2 ** 32 else 32

        return "%s (%s, %d-bit)" % (platform.python_version(),
                                    platform.python_implementation(), bits)
    except Exception:
        return platform.python_version()


def interpreter_path():
    """Which python this is - the row that ends an argument about the venv."""
    return str(sys.executable or "")


# --------------------------------------------------------------------------
# xdist
# --------------------------------------------------------------------------

def worker_summary(config, records=None):
    """How many xdist workers ran the suite, or '' when nothing was sharded.

    Counted from the records rather than taken from ``-n``, because the number
    that matters afterwards is how many processes actually reported results.
    ``-n`` is kept only to say so when the two disagree: xdist quietly runs
    fewer workers than asked for when there are fewer tests than workers, and a
    report claiming eight when three ran would be read as three crashes.
    """
    observed = len({str(record.get('worker') or '') for record in (records or [])} - {''})

    try:
        requested = config.getoption("numprocesses", None)
        requested = int(requested) if requested else 0
    except (AttributeError, TypeError, ValueError):
        requested = 0

    if not observed and not requested:
        return ""

    if observed and requested and observed != requested:
        return "%d of %d requested" % (observed, requested)

    return str(observed or requested)


# --------------------------------------------------------------------------
# the CI run
# --------------------------------------------------------------------------

class CIRun(object):
    """The CI system, the build it ran as, and the page that build lives on."""

    def __init__(self, system="", label="", build="", url=""):
        self.system = system
        self.label = label
        self.build = build
        self.url = url

    @property
    def summary(self):
        """The one line the panel's CI row shows."""
        return (self.label + " · " + self.build).strip(" ·") if self.build else self.label

    def as_dict(self):
        return {'system': self.system, 'label': self.label,
                'build': self.build, 'url': self.url}

    def __bool__(self):
        return bool(self.label)

    __nonzero__ = __bool__


def _github_url():
    """.../actions/runs/<id>, and the attempt when this is not the first one.

    GITHUB_RUN_ID deliberately does not change when a workflow is re-run, so
    the bare run url opens the *latest* attempt. A report written by attempt 1
    linking to attempt 3 is a link to somebody else's failure, so the attempt
    is pinned whenever it is known to be past the first.
    """
    server = _env("GITHUB_SERVER_URL", "https://github.com")
    repository = _env("GITHUB_REPOSITORY")
    run = _env("GITHUB_RUN_ID")

    if not (repository and run):
        return ""

    url = "%s/%s/actions/runs/%s" % (server.rstrip("/"), repository, run)
    attempt = _env("GITHUB_RUN_ATTEMPT")

    return url + "/attempts/" + attempt if attempt.isdigit() and int(attempt) > 1 else url


def _azure_url():
    """The build's results page, assembled from the three parts Azure sets."""
    collection = _env("SYSTEM_TEAMFOUNDATIONCOLLECTIONURI")
    project = _env("SYSTEM_TEAMPROJECT")
    build = _env("BUILD_BUILDID")

    if not (collection and project and build):
        return ""

    return "%s/%s/_build/results?buildId=%s" % (collection.rstrip("/"), project, build)


def _appveyor_url():
    account = _env("APPVEYOR_ACCOUNT_NAME")
    slug = _env("APPVEYOR_PROJECT_SLUG")
    build = _env("APPVEYOR_BUILD_ID")

    if not (account and slug and build):
        return ""

    return "%s/project/%s/%s/builds/%s" % (
        _env("APPVEYOR_URL", "https://ci.appveyor.com").rstrip("/"), account, slug, build)


def _bitbucket_url():
    repository = _env("BITBUCKET_REPO_FULL_NAME")
    build = _env("BITBUCKET_BUILD_NUMBER")

    if not (repository and build):
        return ""

    return "https://bitbucket.org/%s/pipelines/results/%s" % (repository, build)


def _semaphore_url():
    organisation = _env("SEMAPHORE_ORGANIZATION_URL")
    workflow = _env("SEMAPHORE_WORKFLOW_ID")

    if not (organisation and workflow):
        return ""

    return "%s/workflows/%s" % (organisation.rstrip("/"), workflow)


def _jenkins_url():
    """BUILD_URL, or the job's own page when Jenkins only set the pieces.

    BUILD_URL is absent whenever Jenkins was installed without a configured
    root url, which is common enough on self-hosted controllers that falling
    back is worth the four lines.
    """
    url = _env("BUILD_URL")
    if url:
        return url

    root = _env("JENKINS_URL") or _env("HUDSON_URL")
    path = _env("JOB_URL")
    build = _env("BUILD_NUMBER")

    if path and build:
        return "%s/%s/" % (path.rstrip("/"), build)

    return root


def _from_vars(*names):
    """The first of these variables that is set to anything."""
    def read():
        for name in names:
            value = _env(name)
            if value:
                return value

        return ""

    return read


def _build_label(*names):
    return _from_vars(*names)


# Each entry: the id this system is known by, the name it calls itself, the
# variable that identifies it, how to reach its build page, and where its build
# number is. The marker is checked for truthiness rather than presence - a
# matrix that sets GITLAB_CI=false is not GitLab - and the order is
# specific-before-generic, so the last entry catches a system nobody here has
# heard of rather than letting it go unnamed.
#
# Every variable name below was read off the system's own documentation. The
# ones that publish a ready-made build url (GitLab, Jenkins, CircleCI,
# Buildkite, Travis, Drone) are used as given rather than assembled: they are
# correct behind a reverse proxy, on a self-hosted install and on a renamed
# domain, and an assembled url is only correct on the vendor's own hosting.
_CI_SYSTEMS = (
    ('github', 'GitHub Actions', 'GITHUB_ACTIONS', _github_url,
     _build_label('GITHUB_RUN_NUMBER', 'GITHUB_RUN_ID')),
    ('gitlab', 'GitLab CI', 'GITLAB_CI', _from_vars('CI_PIPELINE_URL', 'CI_JOB_URL'),
     _build_label('CI_PIPELINE_ID', 'CI_JOB_ID')),
    ('circleci', 'CircleCI', 'CIRCLECI', _from_vars('CIRCLE_BUILD_URL'),
     _build_label('CIRCLE_BUILD_NUM')),
    ('buildkite', 'Buildkite', 'BUILDKITE', _from_vars('BUILDKITE_BUILD_URL'),
     _build_label('BUILDKITE_BUILD_NUMBER')),
    ('azure', 'Azure Pipelines', 'TF_BUILD', _azure_url,
     _build_label('BUILD_BUILDNUMBER', 'BUILD_BUILDID')),
    ('travis', 'Travis CI', 'TRAVIS', _from_vars('TRAVIS_BUILD_WEB_URL'),
     _build_label('TRAVIS_BUILD_NUMBER')),
    ('appveyor', 'AppVeyor', 'APPVEYOR', _appveyor_url,
     _build_label('APPVEYOR_BUILD_NUMBER')),
    ('drone', 'Drone', 'DRONE', _from_vars('DRONE_BUILD_LINK'),
     _build_label('DRONE_BUILD_NUMBER')),
    ('bitbucket', 'Bitbucket Pipelines', 'BITBUCKET_BUILD_NUMBER', _bitbucket_url,
     _build_label('BITBUCKET_BUILD_NUMBER')),
    ('semaphore', 'Semaphore', 'SEMAPHORE', _semaphore_url,
     _build_label('SEMAPHORE_JOB_ID')),
    ('codebuild', 'AWS CodeBuild', 'CODEBUILD_BUILD_ID',
     _from_vars('CODEBUILD_PUBLIC_BUILD_URL'),
     _build_label('CODEBUILD_BUILD_NUMBER', 'CODEBUILD_BUILD_ID')),
    ('teamcity', 'TeamCity', 'TEAMCITY_VERSION', _from_vars('BUILD_URL'),
     _build_label('BUILD_NUMBER')),
    # Jenkins is late on purpose: BUILD_NUMBER and BUILD_URL are set by several
    # of the systems above, and JENKINS_URL is what actually says Jenkins.
    ('jenkins', 'Jenkins', 'JENKINS_URL', _jenkins_url,
     _build_label('BUILD_NUMBER')),
    ('jenkins', 'Jenkins', 'HUDSON_URL', _jenkins_url,
     _build_label('BUILD_NUMBER')),
    # Anything else that says it is CI. Named rather than skipped: "this ran on
    # a build agent, not on somebody's laptop" is most of what the row is for.
    ('ci', 'CI', 'CI', _from_vars('BUILD_URL'), _build_label('BUILD_NUMBER', 'BUILD_ID')),
    ('ci', 'CI', 'CONTINUOUS_INTEGRATION', _from_vars('BUILD_URL'),
     _build_label('BUILD_NUMBER', 'BUILD_ID')),
)


def ci_run():
    """The CI run this report was produced by, or an empty CIRun locally."""
    for system, label, marker, url, build in _CI_SYSTEMS:
        if not _truthy(marker):
            continue

        try:
            return CIRun(system=system, label=label, build=build(), url=url())
        except Exception:
            return CIRun(system=system, label=label)

    return CIRun()


# --------------------------------------------------------------------------
# the revision under test
# --------------------------------------------------------------------------

# Where each CI system puts the branch and the commit. Read before git is asked
# anything, because a CI checkout is normally a detached HEAD: `git rev-parse
# --abbrev-ref HEAD` there answers "HEAD", which is true and useless, while the
# system itself knows the branch name that was clicked. GITHUB_HEAD_REF comes
# first for pull requests - GITHUB_REF_NAME on a pull_request event is the
# merge ref ("42/merge"), not the branch anybody recognises.
_GIT_BRANCH_VARS = (
    'GITHUB_HEAD_REF', 'GITHUB_REF_NAME', 'CI_COMMIT_REF_NAME', 'CIRCLE_BRANCH',
    'BUILDKITE_BRANCH', 'BUILD_SOURCEBRANCHNAME', 'TRAVIS_PULL_REQUEST_BRANCH',
    'TRAVIS_BRANCH', 'APPVEYOR_REPO_BRANCH', 'DRONE_BRANCH', 'BITBUCKET_BRANCH',
    'SEMAPHORE_GIT_BRANCH', 'GIT_BRANCH', 'BRANCH_NAME',
)

_GIT_COMMIT_VARS = (
    'GITHUB_SHA', 'CI_COMMIT_SHA', 'CIRCLE_SHA1', 'BUILDKITE_COMMIT',
    'BUILD_SOURCEVERSION', 'TRAVIS_COMMIT', 'APPVEYOR_REPO_COMMIT',
    'DRONE_COMMIT_SHA', 'BITBUCKET_COMMIT', 'SEMAPHORE_GIT_SHA',
    'CODEBUILD_RESOLVED_SOURCE_VERSION', 'GIT_COMMIT', 'BUILD_VCS_NUMBER',
)


def _git(root, *args):
    """One git command's stdout, or '' for anything at all going wrong.

    Wrong includes: no git installed, not a checkout, a checkout owned by
    another user (git refuses those outright), and a repository big enough that
    the call would outlast the report.
    """
    try:
        result = subprocess.run(
            ("git",) + args,
            cwd=root or None,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=GIT_TIMEOUT,
        )
    except Exception:
        return ""

    if result.returncode != 0:
        return ""

    return result.stdout.decode("utf-8", "replace").strip()


def git_revision(root=None):
    """(branch, short commit) for the checkout under test, either may be ''.

    The CI system is believed before git is asked, and git is only asked at all
    when it has something to add: two processes on a build agent that already
    published both answers is two processes nobody needed.
    """
    branch = next((value for value in (_env(name) for name in _GIT_BRANCH_VARS) if value), "")
    commit = next((value for value in (_env(name) for name in _GIT_COMMIT_VARS) if value), "")

    if not branch:
        branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
        # A detached HEAD - what a CI checkout and a bisect both look like.
        # "HEAD" is not a branch name and saying it in a panel that has just
        # named a commit is worse than leaving the row out.
        if branch == "HEAD":
            branch = ""

    if not commit:
        commit = _git(root, "rev-parse", "HEAD")

    # Shortened here rather than at the row, so a bundle carries what the panel
    # shows and a merge does not have to know what a sha looks like.
    return branch, commit[:SHA_LENGTH]


# --------------------------------------------------------------------------
# what was installed
# --------------------------------------------------------------------------

def installed_packages():
    """Every installed distribution as name==version, the way pip freeze reads.

    The Plugins row above answers "which pytest plugins", which is a different
    and much smaller question: the library whose new minor version broke the
    suite last night is almost never a pytest plugin.
    """
    packages = {}

    try:
        try:
            from importlib.metadata import distributions
        except ImportError:  # Python 3.7
            from importlib_metadata import distributions  # noqa: F401

        found = distributions()
    except Exception:
        return _installed_packages_legacy()

    try:
        for distribution in found:
            try:
                metadata = distribution.metadata
                name = str(metadata["Name"] or "").strip() if metadata else ""
                version = str(distribution.version or "").strip()
            except Exception:
                # One unreadable distribution - a half-deleted directory, a
                # metadata file written in another encoding - must not cost the
                # other three hundred.
                continue

            if name:
                packages.setdefault(name, version)
    except Exception:
        return _installed_packages_legacy()

    return ["%s==%s" % (name, version) if version else name
            for name, version in sorted(packages.items(), key=lambda pair: pair[0].lower())]


def _installed_packages_legacy():
    """The same list from pkg_resources, for a 3.7 without importlib_metadata."""
    try:
        import pkg_resources
    except Exception:
        return []

    packages = {}

    try:
        for distribution in pkg_resources.working_set:
            name = str(getattr(distribution, "project_name", "") or "").strip()
            if name:
                packages.setdefault(name, str(getattr(distribution, "version", "") or ""))
    except Exception:
        return []

    return ["%s==%s" % (name, version) if version else name
            for name, version in sorted(packages.items(), key=lambda pair: pair[0].lower())]


def packages_row(packages):
    """(label, value) for the Packages row, or None when there is nothing.

    The count goes in the label because it is the part somebody scanning the
    panel reads, and the list itself is one long value the overlay wraps.
    """
    packages = [str(name).strip() for name in (packages or []) if str(name).strip()]

    if not packages:
        return None

    return ("Packages (%d)" % len(packages), ", ".join(packages))
