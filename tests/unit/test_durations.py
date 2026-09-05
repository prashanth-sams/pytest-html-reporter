"""Cover how long the report says a test took, and when it says a build began.

Both numbers used to be read off ``ConfigVars._start_execution_time``, which is
process-global state the merge writes to as well - so they were only ever right
for a run where nothing else in the plugin had anything to say. A test that
merged a shard bundle while it ran was billed every second since the epoch, and
the build itself was stamped with the moment its last test began setting up.

Driven through a real pytest process rather than by calling the hooks: the
whole point is the order the hooks fire in, and a test that calls them itself
would be asserting the order it chose.
"""

import json
import os
import subprocess
import sys
import textwrap

import pytest


SAMPLE = {
    "test_timing.py": """
        import time

        from pytest_html_reporter.const_vars import ConfigVars


        def test_slow_enough_to_measure():
            time.sleep(1.0)


        def test_that_moves_the_global_clock(tmp_path_factory):
            '''What a merge does to this process on its way past.

            merge_into() sets this so the build it writes is stamped with the
            matrix's start rather than the merging machine's. Nothing warns a
            test that it happened, and the duration used to be measured
            against it.
            '''
            ConfigVars._start_execution_time = 0.0


        def test_last():
            with open("started", "w") as handle:
                handle.write(str(time.time()))
    """,
}


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    """One run of the sample suite, and the output.json it wrote."""
    base = tmp_path_factory.mktemp("durations")

    for name, body in SAMPLE.items():
        (base / name).write_text(textwrap.dedent(body).lstrip())

    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--html-report=./report",
         "-p", "no:cacheprovider"],
        cwd=str(base),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )

    written = base / "report" / "output.json"
    assert written.is_file(), result.stdout

    data = json.loads(written.read_text())
    data["_last_started"] = float((base / "started").read_text())

    return data


def _durations(data):
    return {
        test["test_name"]: test["duration"]
        for suite in data["content"]["suites"].values()
        for test in suite["tests"].values()
    }


# ------------------------------------------------------------ a test's time ---

def test_a_test_is_timed_by_the_phases_pytest_reported(report):
    """The regression: the middle test read back as 1788535128.1 seconds.

    Measured against a start it had just zeroed itself, its duration was the
    current unix time - 56 years - and the slowest-tests chart drew every
    other test in the suite as a sliver beside it.
    """
    durations = _durations(report)

    assert durations["test_that_moves_the_global_clock"] < 60
    assert durations["test_slow_enough_to_measure"] >= 1.0
    assert durations["test_slow_enough_to_measure"] < 60


def test_the_sum_of_the_durations_is_the_run(report):
    """Every test's time added up is the suite's time, near enough.

    One epoch-sized duration is all it takes for the "time in tests" tile to
    read 608889402m, so what matters is not any single number but that the
    total stays inside the run that produced it.
    """
    total = sum(_durations(report).values())

    assert 1.0 <= total < 60


# ----------------------------------------------------------- a build's time ---

def test_the_build_is_stamped_with_the_start_of_the_run(report):
    """Not the moment its last test began setting up.

    Analytics sorts builds on this number and labels every point of every
    chart with it, so a stamp taken at the end of the run puts the build on
    the trend minutes after it happened - and two builds of one pipeline in
    the wrong order.
    """
    assert report["start_time"] <= report["_last_started"] - 1.0
