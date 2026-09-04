import copy


class ConfigVars:
    _total = _executed = 0
    _pass = _fail = 0
    _skip = _error = 0
    _xpass = _xfail = 0
    _apass = _afail = 0
    _askip = _aerror = 0
    _axpass = _axfail = 0
    _astotal = 0
    _aspass = 0
    _asfail = 0
    _asskip = 0
    _aserror = 0
    _asxpass = 0
    _asxfail = 0
    _asrerun = 0
    _current_error = ""
    _xfail_reason = ""
    _suite_name = None
    _test_name = None
    _test_suite_name = []
    _test_pass_list = []
    _test_fail_list = []
    _test_skip_list = []
    _test_xpass_list = []
    _test_xfail_list = []
    _test_error_list = []
    _test_status = None
    _start_execution_time = 0
    _execution_time = _duration = 0
    _test_metrics_content = ""
    _test_logs_content = ""
    _logs_notice = ""
    _suite_metrics_content = ""
    _previous_suite_name = "None"
    _initial_trigger = True
    _spass_tests = 0
    _sfail_tests = 0
    _sskip_tests = 0
    _serror_tests = 0
    _srerun_tests = 0
    _sxfail_tests = 0
    _sxpass_tests = 0
    _suite_length = 0
    _archive_tab_content = ""
    _archive_body_content = ""
    _archive_count = ""
    archive_pass = 0
    archive_fail = 0
    archive_skip = 0
    archive_xpass = 0
    archive_xfail = 0
    archive_error = 0
    archives = {}
    highlights = {}
    p_highlights = {}
    max_failure_suite_name = ''
    max_failure_suite_name_final = ''
    max_failure_suite_count = 0
    similar_max_failure_suite_count = 0
    max_failure_total_tests = 0
    max_failure_percent = ''
    trends_label = []
    tpass = []
    tfail = []
    tskip = []
    _suite_error = 0
    _suite_fail = 0
    _attach_screenshot_details = ''
    _screenshots = []
    _attachments = []
    _steps = []
    _step_open = None
    _step_epoch = 0
    _step_phase = 'call'
    _step_limit = 500
    _bdd = None
    _step_tree = ''
    _step_store = ''
    _step_state = 'is-bare'
    _step_named = '0'
    _step_total = '0'
    _attachment_items = ''
    _attachment_store = ''
    _environment_rows = ''
    _environment = ''
    _environment_label = ''
    _environment_class = ''
    _coverage = None
    _coverage_state = 'is-empty'
    _coverage_rows = ''
    _coverage_tiles = ''
    _coverage_chip = ''
    _coverage_display = '0'
    _coverage_dash = ''
    _coverage_grade = 'low'
    _coverage_meta = ''
    _coverage_delta = ''
    _coverage_delta_class = ''
    _coverage_target = ''
    _coverage_link = ''
    _coverage_note = ''
    _coverage_notice = ''
    _coverage_branch = 'false'
    _coverage_trend_labels = '[]'
    _coverage_trend_values = '[]'
    _coverage_trend_state = 'no-trend'
    tcoverage = []
    _failure_delta = ''
    _failure_delta_class = ''
    _failure_delta_title = ''
    _failure_delta_figure = ''
    _failure_delta_unit = ''
    _report_links = ''
    _link_patterns = {}
    _title = 'PYTEST REPORT'
    _title_full = 'PYTEST REPORT'
    _title_class = ''
    _analytics_tiles = ''
    _analytics_rows = ''
    _analytics_movement = ''
    _analytics_builds = '0'
    _analytics_scope = ''
    _analytics_state = 'is-solo'
    _analytics_labels = '[]'
    _analytics_pass_rate = '[]'
    _analytics_growth = '[]'
    _analytics_flow_labels = '[]'
    _analytics_flow_fixed = '[]'
    _analytics_flow_regressed = '[]'
    _analytics_flow_added = '[]'
    _analytics_flow_removed = '[]'
    _analytics_bucket_labels = '[]'
    _analytics_buckets = '[]'
    _analytics_slowest = '[]'
    _analytics_faults = ''
    _analytics_fault_note = ''
    _analytics_fault_state = 'is-empty'
    _analytics_owners = ''
    _analytics_owner_note = ''
    _analytics_owner_state = 'is-empty'


# Every attribute as it stood at import, so a process that renders a second
# time can start from the same slate the first one did.
_PRISTINE = {name: copy.deepcopy(value)
             for name, value in vars(ConfigVars).items()
             if not name.startswith('__')}


def reset_config_vars():
    """Put every ConfigVars attribute back to the value it had at import.

    ConfigVars is class-level state, and one render leaves its marks all over
    it. generate_json_data accumulates _aspass.._asrerun with +=, and the
    template renders that family rather than the one update_counts assigns, so
    a second render in the same process doubles every number on the dashboard
    without raising anything. The merge command renders once per process today
    and this still runs first, because "today" is not a guarantee.

    Not a substitute for the test suite's _isolate_config_vars fixtures: those
    save the values they find and put those back, which is what a test run
    needs. This resets to import-time and restores nothing.
    """
    for name, value in _PRISTINE.items():
        setattr(ConfigVars, name, copy.deepcopy(value))
