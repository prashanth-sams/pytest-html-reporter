import os
import shutil
import sys
from collections import Counter
from io import BytesIO
from PIL import Image

from pytest_html_reporter import const_vars

def suite_highlights(data):

    for i in data['content']['suites']:
        if data['content']['suites'][i]['status']['total_fail'] == 0:
            l = data['content']['suites'][i]['suite_name']
            if l not in const_vars.p_highlights:
                const_vars.p_highlights[l] = 1
            else:
                const_vars.p_highlights[l] += 1
        else:
            k = data['content']['suites'][i]['suite_name']

            if k not in const_vars.highlights:
                const_vars.highlights[k] = 1
            else:
                const_vars.highlights[k] += 1


def generate_suite_highlights():

    if const_vars.highlights == {}:
        const_vars.max_failure_suite_name_final = 'No failures in History'
        const_vars.max_failure_suite_count = 0
        const_vars.max_failure_percent = '0'
        return

    const_vars.max_failure_suite_name = max(const_vars.highlights, key=const_vars.highlights.get)
    const_vars.max_failure_suite_count = const_vars.highlights[const_vars.max_failure_suite_name]

    if const_vars.max_failure_suite_name in const_vars.p_highlights:
        const_vars.max_failure_total_tests = const_vars.p_highlights[const_vars.max_failure_suite_name] + const_vars.max_failure_suite_count
    else:
        const_vars.max_failure_total_tests = const_vars.max_failure_suite_count

    const_vars.max_failure_percent = (const_vars.max_failure_suite_count / const_vars.max_failure_total_tests) * 100

    if const_vars.max_failure_suite_name.__len__() > 25:
        const_vars.max_failure_suite_name_final = ".." + const_vars.max_failure_suite_name[-23:]
    else:
        const_vars.max_failure_suite_name_final = const_vars.max_failure_suite_name

    res = Counter(const_vars.highlights.values())
    if max(res.values()) > 1: const_vars.similar_max_failure_suite_count = max(res.values())


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

    const_vars.screen_base = HTMLReporter.base_path
    const_vars.screen_img = Image.open(BytesIO(data))


def clean_screenshots(path):
    screenshot_dir = os.path.abspath(os.path.expanduser(os.path.expandvars(path))) + '/pytest_screenshots'
    if os.path.isdir(screenshot_dir):
        shutil.rmtree(screenshot_dir)


def custom_title(title):
    global _title

    _title = title[:26] + '...' if title.__len__() > 29 else title