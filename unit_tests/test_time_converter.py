from pytest_html_reporter.time_converter import time_converter, clamp_to_twelve, is_midnight
import datetime


def test_time_converter():
    if time_converter("18:31") == '6:31 pm':
        pass
    else:
        raise Exception("invalid method: time_converter")


def test_clamp_to_twelve():
    time_dt = datetime.datetime(1900, 1, 1, 18, 40)
    midday_dt = datetime.datetime(1900, 1, 1, 12, 0)

    if clamp_to_twelve(time_dt, midday_dt) == [6, 40]:
        pass
    else:
        raise Exception("invalid method: clamp_to_twelve")


def test_is_midnight():
    time_dt = datetime.datetime(1900, 1, 1, 18, 40)

    if not is_midnight(time_dt):
        pass
    else:
        raise Exception("invalid method: is_midnight")