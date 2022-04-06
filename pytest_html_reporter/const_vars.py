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
    _suite_name = _test_name = None
    _scenario = []
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
    _test_metrics_content = _suite_metrics_content = ""
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
    _previous_test_name = ''
    _suite_error = 0
    _suite_fail = 0
    _pvalue = 0
    screen_base = ''
    screen_img = None
    _attach_screenshot_details = ''
    _title = 'PYTEST REPORT'