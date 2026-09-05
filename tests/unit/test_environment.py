"""What the Environment panel now answers without being asked.

Every row here used to be somebody's ``--build-info`` flag, written before the
run by a person who already knew the answer. These tests are mostly about the
cases where nobody wrote one: a detached CI checkout, a re-run workflow, a
matrix that sets CI=false, a distribution with unreadable metadata.
"""

import os

import pytest

from pytest_html_reporter import environment
from pytest_html_reporter.environment import (
    CIRun,
    ci_run,
    git_revision,
    installed_packages,
    os_summary,
    packages_row,
    python_summary,
    worker_summary,
)
from pytest_html_reporter.util import env_rows, environment_entries


# Everything the detection reads. Cleared for every test in this module,
# because the suite itself runs on CI: a test asserting "no CI was detected"
# would pass on a laptop and fail on the very system the feature is for.
_CI_VARIABLES = tuple(marker for _, _, marker, _, _ in environment._CI_SYSTEMS) + (
    'GITHUB_SERVER_URL', 'GITHUB_REPOSITORY', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT',
    'GITHUB_RUN_NUMBER', 'CI_PIPELINE_URL', 'CI_JOB_URL', 'CI_PIPELINE_ID', 'CI_JOB_ID',
    'CIRCLE_BUILD_URL', 'CIRCLE_BUILD_NUM', 'BUILDKITE_BUILD_URL', 'BUILDKITE_BUILD_NUMBER',
    'SYSTEM_TEAMFOUNDATIONCOLLECTIONURI', 'SYSTEM_TEAMPROJECT', 'BUILD_BUILDID',
    'BUILD_BUILDNUMBER', 'TRAVIS_BUILD_WEB_URL', 'TRAVIS_BUILD_NUMBER',
    'APPVEYOR_URL', 'APPVEYOR_ACCOUNT_NAME', 'APPVEYOR_PROJECT_SLUG', 'APPVEYOR_BUILD_ID',
    'APPVEYOR_BUILD_NUMBER', 'DRONE_BUILD_LINK', 'DRONE_BUILD_NUMBER',
    'BITBUCKET_REPO_FULL_NAME', 'SEMAPHORE_ORGANIZATION_URL', 'SEMAPHORE_WORKFLOW_ID',
    'SEMAPHORE_JOB_ID', 'CODEBUILD_PUBLIC_BUILD_URL', 'CODEBUILD_BUILD_NUMBER',
    'BUILD_URL', 'BUILD_NUMBER', 'BUILD_ID', 'JOB_URL', 'JOB_NAME',
) + environment._GIT_BRANCH_VARS + environment._GIT_COMMIT_VARS


@pytest.fixture(autouse=True)
def _no_inherited_ci(monkeypatch):
    for name in _CI_VARIABLES:
        monkeypatch.delenv(name, raising=False)


class _FakeConfig:
    """Just enough of pytest's Config for the panel's own helpers."""

    def __init__(self, options=None, ini=None, rootpath="."):
        self._options = options or {}
        self._ini = ini or {}
        self.rootpath = rootpath
        self.pluginmanager = self

    def getoption(self, name, default=None):
        value = self._options.get(name, default)

        return default if value is None else value

    def getini(self, name):
        if name not in self._ini:
            raise ValueError(name)

        return self._ini[name]

    def list_plugin_distinfo(self):
        return []


# ------------------------------------------------------------- the machine ---

def test_the_platform_row_names_the_os_and_not_the_kernel():
    """"Darwin 24.6.0" is a true answer to a question nobody asked. Whoever
    reads this row thinks in macOS versions, distributions and architectures."""
    summary = os_summary()

    assert summary
    assert "Darwin" not in summary or os.uname().sysname != "Darwin"
    assert "(" in summary and ")" in summary


def test_the_python_row_carries_the_implementation_and_the_word_size():
    """Two suites that agree about 3.11 and disagree about PyPy - or about
    which half of a Windows install they are on - install different wheels."""
    summary = python_summary()

    assert summary.startswith(".".join(str(part) for part in os.sys.version_info[:3]))
    assert "CPython" in summary or "PyPy" in summary
    assert "-bit" in summary


# --------------------------------------------------------------- the shards ---

def test_a_serial_run_says_nothing_about_workers():
    """One process is not a worker count, and a row reading "1" invites the
    reader to wonder which seven crashed."""
    assert worker_summary(_FakeConfig(), []) == ""


def test_the_workers_that_reported_are_counted():
    records = [{'worker': 'gw0'}, {'worker': 'gw1'}, {'worker': 'gw0'}, {'worker': ''}]

    assert worker_summary(_FakeConfig(options={'numprocesses': 2}), records) == "2"


def test_fewer_workers_than_asked_for_is_said_rather_than_smoothed_over():
    """xdist runs fewer workers than -n when there are fewer tests than
    workers. A report claiming eight when three ran reads as five crashes."""
    records = [{'worker': 'gw0'}, {'worker': 'gw1'}]

    assert worker_summary(_FakeConfig(options={'numprocesses': 8}), records) == "2 of 8 requested"


def test_a_controller_that_collected_no_records_still_reports_what_it_asked_for():
    assert worker_summary(_FakeConfig(options={'numprocesses': 4}), []) == "4"


def test_a_nonsense_numprocesses_is_not_an_error():
    """-n auto is resolved by xdist before this reads it, but a shim config
    answers whatever it was handed, and this runs while a report is written."""
    assert worker_summary(_FakeConfig(options={'numprocesses': 'auto'}), []) == ""


# ------------------------------------------------------------------ the CI ---

def test_no_ci_is_an_empty_run_rather_than_a_row():
    assert not ci_run()
    assert ci_run().summary == ""


def test_github_actions_is_named_and_linked(monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/app")
    monkeypatch.setenv("GITHUB_RUN_ID", "1717")
    monkeypatch.setenv("GITHUB_RUN_NUMBER", "42")

    run = ci_run()

    assert run.system == "github"
    assert run.summary == "GitHub Actions · 42"
    assert run.url == "https://github.com/acme/app/actions/runs/1717"


def test_a_re_run_workflow_links_its_own_attempt(monkeypatch):
    """GITHUB_RUN_ID does not change when a workflow is re-run, so the bare url
    opens the latest attempt - which is somebody else's failure."""
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/app")
    monkeypatch.setenv("GITHUB_RUN_ID", "1717")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "3")

    assert ci_run().url.endswith("/actions/runs/1717/attempts/3")


def test_the_first_attempt_is_not_pinned(monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/app")
    monkeypatch.setenv("GITHUB_RUN_ID", "1717")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")

    assert ci_run().url.endswith("/actions/runs/1717")


def test_a_github_enterprise_server_is_linked_to_itself(monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://git.acme.internal/")
    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/app")
    monkeypatch.setenv("GITHUB_RUN_ID", "5")

    assert ci_run().url == "https://git.acme.internal/acme/app/actions/runs/5"


def test_gitlab_is_linked_with_the_url_it_publishes_itself(monkeypatch):
    """Assembling one would only be right on gitlab.com; CI_PIPELINE_URL is
    right behind a reverse proxy and on a self-hosted install too."""
    monkeypatch.setenv("GITLAB_CI", "true")
    monkeypatch.setenv("CI_PIPELINE_URL", "https://gitlab.acme.dev/acme/app/-/pipelines/99")
    monkeypatch.setenv("CI_PIPELINE_ID", "99")

    run = ci_run()

    assert run.summary == "GitLab CI · 99"
    assert run.url == "https://gitlab.acme.dev/acme/app/-/pipelines/99"


def test_azure_assembles_the_build_results_page(monkeypatch):
    monkeypatch.setenv("TF_BUILD", "True")
    monkeypatch.setenv("SYSTEM_TEAMFOUNDATIONCOLLECTIONURI", "https://dev.azure.com/acme/")
    monkeypatch.setenv("SYSTEM_TEAMPROJECT", "payments")
    monkeypatch.setenv("BUILD_BUILDID", "812")

    assert ci_run().url == "https://dev.azure.com/acme/payments/_build/results?buildId=812"


def test_jenkins_falls_back_to_the_job_url_when_the_root_url_is_unset(monkeypatch):
    """BUILD_URL is absent on a controller installed without a configured root
    url, which is common enough on self-hosted Jenkins to be worth handling."""
    monkeypatch.setenv("JENKINS_URL", "https://ci.acme.dev/")
    monkeypatch.setenv("JOB_URL", "https://ci.acme.dev/job/payments/")
    monkeypatch.setenv("BUILD_NUMBER", "41")

    run = ci_run()

    assert run.system == "jenkins"
    assert run.url == "https://ci.acme.dev/job/payments/41/"


def test_a_system_that_only_says_ci_is_still_named(monkeypatch):
    """"This ran on a build agent and not on somebody's laptop" is most of what
    the row is for, and it is worth saying about a system nobody has heard of."""
    monkeypatch.setenv("CI", "true")

    assert ci_run().label == "CI"


def test_ci_set_to_false_is_not_ci(monkeypatch):
    """CI=false is a real thing to write in a matrix that turns a step off, and
    reading it as "this is CI" gets it exactly backwards."""
    monkeypatch.setenv("CI", "false")

    assert not ci_run()


def test_a_ci_run_that_cannot_be_linked_is_still_named(monkeypatch):
    monkeypatch.setenv("BITBUCKET_BUILD_NUMBER", "7")

    run = ci_run()

    assert run.summary == "Bitbucket Pipelines · 7"
    assert run.url == ""


def test_a_run_carries_its_four_fields_through_a_bundle():
    """The merge rebuilds this from a shard's json rather than re-detecting."""
    run = CIRun(system="github", label="GitHub Actions", build="42", url="https://x/1")

    assert CIRun(**run.as_dict()).summary == "GitHub Actions · 42"


# ------------------------------------------------------------ the revision ---

def test_the_ci_systems_branch_beats_a_detached_head(monkeypatch):
    """A CI checkout is a detached HEAD, where git answers "HEAD" - true, and
    useless. The system itself knows the branch somebody clicked."""
    monkeypatch.setenv("GITHUB_REF_NAME", "main")
    monkeypatch.setenv("GITHUB_SHA", "0123456789abcdef0123456789abcdef01234567")

    branch, commit = git_revision(".")

    assert branch == "main"
    assert commit == "0123456789ab"


def test_a_pull_request_reports_the_branch_and_not_the_merge_ref(monkeypatch):
    """GITHUB_REF_NAME on a pull_request event is "42/merge", which is not a
    branch anybody recognises."""
    monkeypatch.setenv("GITHUB_HEAD_REF", "feature/login")
    monkeypatch.setenv("GITHUB_REF_NAME", "42/merge")

    assert git_revision(".")[0] == "feature/login"


def test_a_folder_that_is_not_a_checkout_reports_nothing(tmp_path):
    """A report from outside a repository is a report with no Branch row, not
    a traceback and not a row reading "fatal: not a git repository"."""
    assert git_revision(str(tmp_path)) == ("", "")


def test_a_detached_head_is_left_out_rather_than_reported_as_a_branch(monkeypatch):
    monkeypatch.setattr(environment, "_git",
                        lambda root, *args: "HEAD" if "--abbrev-ref" in args else "abc123def456789")

    assert git_revision(".") == ("", "abc123def456")


def test_git_failing_is_not_the_report_failing(monkeypatch):
    def explode(*args, **kwargs):
        raise OSError("no git here")

    monkeypatch.setattr(environment.subprocess, "run", explode)

    assert git_revision(".") == ("", "")


# ------------------------------------------------------------ the packages ---

def test_the_installed_packages_read_like_pip_freeze():
    packages = installed_packages()

    assert packages
    assert any(name.startswith("pytest==") for name in packages)
    assert all("==" in name or name for name in packages)


def test_the_packages_are_listed_in_a_case_insensitive_order():
    """Sorted the way a person reads a list, not the way ASCII does - which
    puts every capitalised distribution above every lowercase one."""
    names = [entry.partition("==")[0] for entry in installed_packages()]

    assert names == sorted(names, key=lambda name: name.lower())


def test_an_empty_list_is_no_row_at_all():
    assert packages_row([]) is None
    assert packages_row(None) is None


def test_the_packages_row_counts_them_in_its_label():
    label, value = packages_row(["attrs==23.2.0", "pytest==8.2.0"])

    assert label == "Packages (2)"
    assert value == "attrs==23.2.0, pytest==8.2.0"


# ---------------------------------------------------------------- the rows ---

def test_a_row_with_a_url_becomes_a_link():
    rows = env_rows([("Pipeline", "https://ci.acme.dev/42", "https://ci.acme.dev/42")])

    assert 'class="env-item__link"' in rows
    assert 'href="https://ci.acme.dev/42"' in rows


def test_a_row_without_a_url_is_still_plain_text():
    rows = env_rows([("Host", "runner-3")])

    assert "<a " not in rows
    assert "runner-3" in rows


def test_a_hostile_scheme_never_becomes_an_href():
    """Every value on this panel now comes from an environment variable, and
    anything that can set one must not be able to put a javascript: url into a
    report somebody opens."""
    rows = env_rows([("Pipeline", "click me", "javascript:alert(1)")])

    assert "javascript:" not in rows
    assert "<a " not in rows


# --------------------------------------------------------------- the panel ---

def test_the_panel_asks_for_no_packages_by_default():
    """A few hundred entries, and a full dependency inventory published into a
    file that gets attached to tickets - a fine thing to do deliberately."""
    labels = [entry[0] for entry in environment_entries(_FakeConfig())]

    assert not any(label.startswith("Packages") for label in labels)


def test_the_flag_adds_the_packages_row():
    entries = environment_entries(_FakeConfig(options={'report_packages': True}))

    assert any(entry[0].startswith("Packages (") for entry in entries)


def test_the_ini_key_adds_the_packages_row():
    entries = environment_entries(_FakeConfig(ini={'report_packages': 'true'}))

    assert any(entry[0].startswith("Packages (") for entry in entries)


def test_a_build_info_branch_is_not_argued_with(monkeypatch):
    """A team that publishes its own Branch row means that one, and two rows
    disagreeing about the branch is worse than either of them alone."""
    monkeypatch.setenv("GITHUB_REF_NAME", "detected")

    entries = environment_entries(_FakeConfig(options={'build_info': ['branch=stated']}))
    branches = [value for label, *value in entries if label.lower() == "branch"]

    assert branches == [["stated"]]


def test_the_ci_rows_are_there_when_the_run_was_a_ci_run(monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/app")
    monkeypatch.setenv("GITHUB_RUN_ID", "1717")

    entries = dict((entry[0], entry[1]) for entry in environment_entries(_FakeConfig()))

    assert entries["CI"] == "GitHub Actions · 1717"
    assert entries["Pipeline"].endswith("/actions/runs/1717")


def test_the_pipeline_row_carries_its_own_url_to_link_to(monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/app")
    monkeypatch.setenv("GITHUB_RUN_ID", "1717")

    pipeline = [entry for entry in environment_entries(_FakeConfig()) if entry[0] == "Pipeline"][0]

    assert len(pipeline) == 3
    assert 'class="env-item__link"' in env_rows([pipeline])
