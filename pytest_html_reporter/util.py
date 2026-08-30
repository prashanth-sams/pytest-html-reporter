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


def max_rerun():
    indices = [i for i, s in enumerate(sys.argv) if 'reruns' in s]

    try:
        if "=" in sys.argv[int(indices[0])]:
            return int(sys.argv[int(indices[0])].split('=')[1])
        else:
            return int(sys.argv[int(indices[0]) + 1])
    except IndexError:
        return None


def screenshot(data=None):
    from pytest_html_reporter.html_reporter import HTMLReporter

    ConfigVars.screen_base = HTMLReporter.base_path
    ConfigVars.screen_img = Image.open(BytesIO(data))


def clean_screenshots(path):
    screenshot_dir = os.path.abspath(os.path.expanduser(os.path.expandvars(path))) + '/pytest_screenshots'
    if os.path.isdir(screenshot_dir):
        shutil.rmtree(screenshot_dir)


def custom_title(title):
    ConfigVars._title = title[:26] + '...' if title.__len__() > 29 else title


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


def generate_environment_info(config):
    uname = platform.uname()
    plugins = _plugin_versions(config)
    root = getattr(config, "rootpath", None) or getattr(config, "rootdir", "")

    entries = [
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
