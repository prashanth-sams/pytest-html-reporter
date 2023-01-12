from datetime import datetime as dt


def time_converter(time):
    midday_dt = dt.strptime('12:00', '%H:%M')
    time_dt = dt.strptime(time, '%H:%M')

    if time_dt >= midday_dt:
        if time_dt >= dt.strptime('13:00', '%H:%M'):
            hours, minutes = clamp_to_twelve(time_dt, midday_dt)
            time = f'{hours}:{minutes}'
        time += ' pm'
    else:
        if time_dt < dt.strptime('10:00', '%H:%M'):
            time = time[1:]
        if is_midnight(time_dt):
            hours, minutes = clamp_to_twelve(time_dt, midday_dt)
            time = f'{hours}:{minutes:02d}'
        time += ' am'
    return time


def clamp_to_twelve(time_dt, midday_dt):
    clamp_dt = time_dt - midday_dt
    minutes, seconds = divmod(clamp_dt.seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return [hours, minutes]


def is_midnight(time_dt):
    return dt.strptime('00:00', '%H:%M') <= time_dt <= dt.strptime('00:59', '%H:%M')
