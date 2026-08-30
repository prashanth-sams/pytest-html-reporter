import os
import platform
import shutil
import sys
from collections import Counter
from datetime import datetime
from html import escape
from io import BytesIO

import pytest
from PIL import Image

from html_page.env_row import EnvRow
from pytest_html_reporter.const_vars import ConfigVars


def suite_highlights(data):
    for i in data['content']['suites']:
        if data['content']['suites'][i]['status']['total_fail'] == 0:
            l = data['content']['suites'][i]['suite_name']
            if l not in ConfigVars.p_highlights:
                ConfigVars.p_highlights[l] = 1
            else:
                ConfigVars.p_highlights[l] += 1
        else:
            k = data['content']['suites'][i]['suite_name']

            if k not in ConfigVars.highlights:
                ConfigVars.highlights[k] = 1
            else:
                ConfigVars.highlights[k] += 1


def generate_suite_highlights():
    if ConfigVars.highlights == {}:
        ConfigVars.max_failure_suite_name_final = 'No failures in History'
        ConfigVars.max_failure_suite_count = 0
        ConfigVars.max_failure_percent = '0'
        return

    ConfigVars.max_failure_suite_name = max(ConfigVars.highlights, key=ConfigVars.highlights.get)
    ConfigVars.max_failure_suite_count = ConfigVars.highlights[ConfigVars.max_failure_suite_name]

    if ConfigVars.max_failure_suite_name in ConfigVars.p_highlights:
        ConfigVars.max_failure_total_tests = ConfigVars.p_highlights[ConfigVars.max_failure_suite_name] + ConfigVars.max_failure_suite_count
    else:
        ConfigVars.max_failure_total_tests = ConfigVars.max_failure_suite_count

    ConfigVars.max_failure_percent = (ConfigVars.max_failure_suite_count / ConfigVars.max_failure_total_tests) * 100

    if ConfigVars.max_failure_suite_name.__len__() > 25:
        ConfigVars.max_failure_suite_name_final = ".." + ConfigVars.max_failure_suite_name[-23:]
    else:
        ConfigVars.max_failure_suite_name_final = ConfigVars.max_failure_suite_name

    res = Counter(ConfigVars.highlights.values())
    if max(res.values()) > 1: ConfigVars.similar_max_failure_suite_count = max(res.values())


def is_xdist_worker(config):
    """True when this process is one of pytest-xdist's workers (gw0, gw1, ...).

    xdist hands every worker a ``workerinput`` dict; the controller never has
    one, and neither does a plain serial run.
    """
    return hasattr(config, "workerinput")


def xdist_worker_id(config):
    """The worker's id, or '' on the controller and on serial runs."""
    return str(getattr(config, "workerinput", {}).get("workerid", ""))


def screenshot(data=None):
    from pytest_html_reporter.html_reporter import HTMLReporter

    ConfigVars.screen_base = HTMLReporter.base_path
    ConfigVars.screen_img = Image.open(BytesIO(data))


def clean_screenshots(path):
    screenshot_dir = os.path.abspath(os.path.expanduser(os.path.expandvars(path))) + '/pytest_screenshots'
    if os.path.isdir(screenshot_dir):
        shutil.rmtree(screenshot_dir)


TITLE_MAX = 20
ENVIRONMENT_LABEL_MAX = 10


def _fit(value, limit):
    """(text, was_cut) for a value hard-cut at `limit` characters.

    No ellipsis: the UI fades the tail instead, and `was_cut` is what tells it
    to.
    """
    value = str(value)

    return value[:limit], len(value) > limit


def custom_title(title):
    ConfigVars._title_full = str(title)
    ConfigVars._title, was_cut = _fit(title, TITLE_MAX)
    ConfigVars._title_class = "is-truncated" if was_cut else ""


def _plugin_versions(config):
    """Names and versions of the pytest plugins active for this run."""
    plugins = []

    for _, dist in config.pluginmanager.list_plugin_distinfo():
        name = getattr(dist, "project_name", None) or getattr(dist, "name", "")
        if not name:
            continue

        version = getattr(dist, "version", "")
        name = name.replace("pytest-", "")
        plugins.append(name + "-" + version if version else name)

    return sorted(set(plugins))


def _invocation_args(config):
    """The command line pytest was started with, minus the executable."""
    params = getattr(config, "invocation_params", None)
    args = getattr(params, "args", None) if params is not None else None

    return " ".join(args) if args else " ".join(sys.argv[1:])


def _ini(config, name):
    """An ini value, tolerating pytest builds where the key is unregistered."""
    try:
        return config.getini(name)
    except (ValueError, KeyError):
        return None


def environment_name(config):
    """The environment under test. --environment wins over the ini key."""
    return str(config.getoption("environment", None) or _ini(config, "environment") or "").strip()


def environment_label(name):
    """(badge text, was_cut) for an environment name."""
    return _fit(name, ENVIRONMENT_LABEL_MAX)


def build_info(config):
    """(label, value) pairs from --build-info and the build_info ini key."""
    entries = list(config.getoption("build_info", None) or [])
    entries += list(_ini(config, "build_info") or [])

    pairs = []
    for entry in entries:
        entry = str(entry).strip()
        if not entry:
            continue

        key, _, value = entry.partition("=")
        pairs.append((key.strip(), value.strip()))

    return pairs


def generate_environment_info(config):
    uname = platform.uname()
    plugins = _plugin_versions(config)
    root = getattr(config, "rootpath", None) or getattr(config, "rootdir", "")

    ConfigVars._environment = environment_name(config)
    ConfigVars._environment_label, was_cut = environment_label(ConfigVars._environment)
    ConfigVars._environment_class = "is-truncated" if was_cut else ""

    entries = []
    if ConfigVars._environment:
        entries.append(("Environment", ConfigVars._environment))
    entries += build_info(config)

    entries += [
        ("Host", uname.node),
        ("Platform", (uname.system + " " + uname.release).strip()),
        ("Python", platform.python_version()),
        ("pytest", pytest.__version__),
        ("Plugins", ", ".join(plugins)),
        ("Arguments", _invocation_args(config)),
        ("Root", str(root)),
        ("Generated", datetime.now().strftime("%b %d %Y, %H:%M:%S")),
    ]

    rows = ""
    for label, value in entries:
        value = str(value).strip() or "-"
        rows += str(EnvRow(label=escape(label), value=escape(value), title=escape(value)))

    ConfigVars._environment_rows = rows
