import os
import shutil
import sys
from collections import Counter
from io import BytesIO

from PIL import Image

highlights = {}
p_highlights = {}

def suite_highlights(data):
    global highlights, p_highlights

    for i in data['content']['suites']:
        if data['content']['suites'][i]['status']['total_fail'] == 0:
            l = data['content']['suites'][i]['suite_name']
            if l not in p_highlights:
                p_highlights[l] = 1
            else:
                p_highlights[l] += 1
        else:
            k = data['content']['suites'][i]['suite_name']

            if k not in highlights:
                highlights[k] = 1
            else:
                highlights[k] += 1


def generate_suite_highlights():
    global max_failure_suite_name, max_failure_suite_count, similar_max_failure_suite_count, max_failure_total_tests
    global max_failure_percent, max_failure_suite_name_final

    if highlights == {}:
        max_failure_suite_name_final = 'No failures in History'
        max_failure_suite_count = 0
        max_failure_percent = '0'
        return

    max_failure_suite_name = max(highlights, key=highlights.get)
    max_failure_suite_count = highlights[max_failure_suite_name]

    if max_failure_suite_name in p_highlights:
        max_failure_total_tests = p_highlights[max_failure_suite_name] + max_failure_suite_count
    else:
        max_failure_total_tests = max_failure_suite_count

    max_failure_percent = (max_failure_suite_count / max_failure_total_tests) * 100

    if max_failure_suite_name.__len__() > 25:
        max_failure_suite_name_final = ".." + max_failure_suite_name[-23:]
    else:
        max_failure_suite_name_final = max_failure_suite_name

    res = Counter(highlights.values())
    if max(res.values()) > 1: similar_max_failure_suite_count = max(res.values())


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

    global screen_base, screen_img

    screen_base = HTMLReporter.base_path
    screen_img = Image.open(BytesIO(data))


def clean_screenshots(path):
    screenshot_dir = os.path.abspath(os.path.expanduser(os.path.expandvars(path))) + '/pytest_screenshots'
    if os.path.isdir(screenshot_dir):
        shutil.rmtree(screenshot_dir)


def custom_title(title):
    global _title

    _title = title[:26] + '...' if title.__len__() > 29 else title