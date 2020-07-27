import pytest
import os, time
from datetime import date

_total = _executed = 0
_pass = _fail = 0
_skip = _error = 0
_xpass = _xfail = 0
_current_error = ""
_suite_name = _test_name = None
_test_suite_name = []
_test_pass_list = []
_test_fail_list = []
_test_skip_list = []
_test_xpass_list = []
_test_xfail_list = []
_test_status = None
_test_start_time = None
_execution_time = _duration = 0
_test_metrics_content = _suite_metrics_content = ""
_previous_suite_name = "None"
_initial_trigger = True
_spass_tests = _sfail_tests = _sskip_tests = 0
_serror_tests = _sxfail_tests = _sxpass_tests = 0


def pytest_addoption(parser):
    group = parser.getgroup("report generator")
    group.addoption(
        "--html",
        action="store",
        dest="path",
        default=".",
        help="path to generate html report",
    )


def pytest_configure(config):
    path = config.getoption("path")

    config._html = HTMLReporter(path, config)
    config.pluginmanager.register(config._html)


class HTMLReporter:

    def __init__(self, path, config):
        self.path = path
        self.config = config

    def pytest_runtest_teardown(self, item, nextitem):
        self.append_test_metrics_row()

    def report_path(self):
        logfile = os.path.expanduser(os.path.expandvars(self.path))
        return os.path.abspath(logfile)

    @pytest.hookimpl(hookwrapper=True)
    def pytest_terminal_summary(self, terminalreporter, exitstatus, config):
        yield

        global _execution_time
        _execution_time = time.time() - terminalreporter._sessionstarttime

        global _total
        _total = _pass + _fail + _xpass + _xfail + _skip + _error

        report_filename = "pytest_report.html"
        path = os.path.join(self.report_path(), report_filename)
        os.makedirs(self.report_path(), exist_ok=True)
        live_logs_file = open(path, 'w')
        message = self.renew_template_text('https://i.imgur.com/LRSRHJO.png')
        live_logs_file.write(message)
        live_logs_file.close()

    @pytest.hookimpl(tryfirst=True, hookwrapper=True)
    def pytest_runtest_makereport(self, item, call):
        outcome = yield
        rep = outcome.get_result()

        global _suite_name
        _suite_name = rep.nodeid.split("::")[0]

        if _initial_trigger:
            self.update_previous_suite_name()
            self.set_initial_trigger()

        if str(_previous_suite_name) != str(_suite_name):
            self.append_suite_metrics_row(_previous_suite_name)
            self.update_previous_suite_name()
            self.reset_counts()
        else:
            self.update_counts(rep)

        if rep.when == "call" and rep.passed:
            if hasattr(rep, "wasxfail"):
                self.increment_xpass()
                self.update_test_status("xPASS")
                global _current_error
                self.update_test_error("")
            else:
                self.increment_pass()
                self.update_test_status("PASS")
                self.update_test_error("")

        if rep.failed:
            if getattr(rep, "when", None) == "call":
                if hasattr(rep, "wasxfail"):
                    self.increment_xpass()
                    self.update_test_status("xPASS")
                    self.update_test_error("")
                else:
                    self.increment_fail()
                    self.update_test_status("FAIL")
                    if rep.longrepr:
                        for line in rep.longreprtext.splitlines():
                            exception = line.startswith("E   ")
                            if exception:
                                self.update_test_error(line.replace("E    ", ""))
            else:
                self.increment_error()
                self.update_test_status("ERROR")
                if rep.longrepr:
                    for line in rep.longreprtext.splitlines():
                        self.update_test_error(line)

        if rep.skipped:
            if hasattr(rep, "wasxfail"):
                self.increment_xfail()
                self.update_test_status("xFAIL")
                if rep.longrepr:
                    for line in rep.longreprtext.splitlines():
                        exception = line.startswith("E   ")
                        if exception:
                            self.update_test_error(line.replace("E    ", ""))
            else:
                self.increment_skip()
                self.update_test_status("SKIP")
                if rep.longrepr:
                    for line in rep.longreprtext.splitlines():
                        self.update_test_error(line)

    def append_test_metrics_row(self):
        test_row_text = """
            <tr>
                <td style="word-wrap: break-word;max-width: 200px; white-space: normal; text-align:left">__sname__</td>
                <td style="word-wrap: break-word;max-width: 200px; white-space: normal; text-align:left">__name__</td>
                <td>__stat__</td>
                <td>__dur__</td>
                <td style="word-wrap: break-word;max-width: 200px; white-space: normal; text-align:left"">__msg__</td>
            </tr>
        """
        test_row_text = test_row_text.replace("__sname__", str(_suite_name))
        test_row_text = test_row_text.replace("__name__", str(_test_name))
        test_row_text = test_row_text.replace("__stat__", str(_test_status))
        test_row_text = test_row_text.replace("__dur__", str(round(_duration, 2)))
        test_row_text = test_row_text.replace("__msg__", str(_current_error))

        global _test_metrics_content
        _test_metrics_content += test_row_text

    def append_suite_metrics_row(self, name):
        self._test_suites(name)
        self._test_passed(int(_spass_tests))
        self._test_failed(int(_sfail_tests))
        self._test_skipped(int(_sskip_tests))
        self._test_xpassed(int(_sxpass_tests))
        self._test_xfailed(int(_sxfail_tests))

        suite_row_text = """
            <tr>
                <td style="word-wrap: break-word;max-width: 200px; white-space: normal; text-align:left">__sname__</td>
                <td>__spass__</td>
                <td>__sfail__</td>
                <td>__sskip__</td>
                <td>__sxpass__</td>
                <td>__sxfail__</td>
                <td>__serror__</td>
            </tr>
        """
        suite_row_text = suite_row_text.replace("__sname__", str(name))
        suite_row_text = suite_row_text.replace("__spass__", str(_spass_tests))
        suite_row_text = suite_row_text.replace("__sfail__", str(_sfail_tests))
        suite_row_text = suite_row_text.replace("__sskip__", str(_sskip_tests))
        suite_row_text = suite_row_text.replace("__sxpass__", str(_sxpass_tests))
        suite_row_text = suite_row_text.replace("__sxfail__", str(_sxfail_tests))
        suite_row_text = suite_row_text.replace("__serror__", str(_serror_tests))

    def set_initial_trigger(self):
        global _initial_trigger
        _initial_trigger = False

    def update_previous_suite_name(self):
        global _previous_suite_name
        _previous_suite_name = _suite_name

    def update_counts(self, rep):
        global _sfail_tests, _spass_tests, _sskip_tests, _serror_tests, _sxfail_tests, _sxpass_tests

        if rep.when == "call" and rep.passed:
            if hasattr(rep, "wasxfail"):
                _sxpass_tests += 1
            else:
                _spass_tests += 1

        if rep.failed:
            if getattr(rep, "when", None) == "call":
                if hasattr(rep, "wasxfail"):
                    _sxpass_tests += 1
                else:
                    _sfail_tests += 1
            else:
                _serror_tests += 1

        if rep.skipped:
            if hasattr(rep, "wasxfail"):
                _sxfail_tests += 1
            else:
                _sskip_tests += 1

    def reset_counts(self):
        global _sfail_tests, _spass_tests, _sskip_tests, _serror_tests, _sxfail_tests, _sxpass_tests
        _spass_tests = 0
        _sfail_tests = 0
        _sskip_tests = 0
        _serror_tests = 0
        _sxfail_tests = 0
        _sxpass_tests = 0

    def update_test_error(self, msg):
        global _current_error
        _current_error = msg

    def update_test_status(self, status):
        global _test_status
        _test_status = status

    def increment_xpass(self):
        global _xpass
        _xpass += 1

    def increment_xfail(self):
        global _xfail
        _xfail += 1

    def increment_pass(self):
        global _pass
        _pass += 1

    def increment_fail(self):
        global _fail
        _fail += 1

    def increment_skip(self):
        global _skip
        _skip += 1

    def increment_error(self):
        global _error
        _error += 1

    def _date(self):
        return date.today().strftime("%B %d, %Y")

    def _test_suites(self, name):
        global _test_suite_name
        _test_suite_name.append(name.split('/')[-1].replace('.py', ''))

    def _test_passed(self, value):
        global _test_pass_list
        _test_pass_list.append(value)

    def _test_failed(self, value):
        global _test_fail_list
        _test_fail_list.append(value)

    def _test_skipped(self, value):
        global _test_skip_list
        _test_skip_list.append(value)

    def _test_xpassed(self, value):
        global _test_xpass_list
        _test_xpass_list.append(value)

    def _test_xfailed(self, value):
        global _test_xfail_list
        _test_xfail_list.append(value)

    def html_template(self):
        return """
    	<!DOCTYPE doctype html>
        <html lang="en">
            <head>
                <link href="https://img.icons8.com/flat_round/64/000000/bar-chart.png" rel="shortcut icon" type="image/x-icon" />
                <title>Pytest HTML Reporter</title>
                <meta charset="utf-8" />
                <meta content="width=device-width, initial-scale=1" name="viewport" />
                <link href="https://cdn.datatables.net/1.10.19/css/jquery.dataTables.min.css" rel="stylesheet" />
                <link href="https://cdn.datatables.net/buttons/1.5.2/css/buttons.dataTables.min.css" rel="stylesheet" />
                <link href="https://cdnjs.cloudflare.com/ajax/libs/twitter-bootstrap/4.1.3/css/bootstrap.min.css" rel="stylesheet" />
                <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css" rel="stylesheet" />
                <script src="https://code.jquery.com/jquery-3.3.1.js" type="text/javascript"></script>
                <!-- Bootstrap core Googleccharts -->
                <script src="https://www.gstatic.com/charts/loader.js" type="text/javascript"></script>
                <script src="https://www.gstatic.com/charts/loader.js" type="text/javascript"></script>
                <script type="text/javascript">
                    google.charts.load('current', {
                        packages: ['corechart']
                    });
                </script>
                <!-- Bootstrap core Datatable-->
                <script src="https://cdn.datatables.net/1.10.19/js/jquery.dataTables.min.js" type="text/javascript"></script>
                <script src="https://cdn.datatables.net/buttons/1.5.2/js/dataTables.buttons.min.js" type="text/javascript"></script>
                <script src="https://cdnjs.cloudflare.com/ajax/libs/jszip/3.1.3/jszip.min.js" type="text/javascript"></script>
                <script src="https://cdn.datatables.net/buttons/1.5.2/js/buttons.html5.min.js" type="text/javascript"></script>
                <script src="https://cdn.datatables.net/buttons/1.5.2/js/buttons.print.min.js" type="text/javascript"></script>
                <script src="https://cdn.datatables.net/buttons/1.6.1/js/buttons.colVis.min.js" type="text/javascript"></script>
                <script src="https://cdn.jsdelivr.net/npm/chart.js@2.8.0" type="text/javascript"></script>
                <style>
                    body {
                        font-family: -apple-system, sans-serif;
                        background-color: #eeeeee;
                    }
                    .sidenav {
                        height: 100%;
                        width: 240px;
                        position: fixed;
                        z-index: 1;
                        top: 0;
                        left: 0;
                        background-color: #211f1f;
                        overflow-x: hidden;
                    }
                    .sidenav a {
                        padding: 12px 10px 8px 12px;
                        text-decoration: none;
                        font-size: 18px;
                        color: #a2a2a2;
                        display: block;
                    }
                    .main {
                        padding-top: 10px;
                    }
                    @media screen and (max-height: 450px) {
                        .sidenav {
                            padding-top: 15px;
                        }
                        .sidenav a {
                            font-size: 18px;
                        }
                    }
                    .wrimagecard {
                        margin-top: 0;
                        margin-bottom: 0.6rem;
                        border-radius: 5px;
                        transition: all 0.3s ease;
                        background-color: #f8f9fa;
                    }
                    .rowcard {
                        # padding-top: 10px;
                        box-shadow: 12px 15px 20px 0px rgba(46, 61, 73, 0.15);
                        border-radius: 6px;
                        transition: all 0.3s ease;
                        # background-color: white;
                    }
                    .tablecard {
                        background-color: white;
                        font-size: 15px;
                    }
                    tr {
                        height: 40px;
                    }
                    .dt-buttons {
                        margin-left: 5px;
                    }
                    th, td, tr {
                        text-align:center;
                        vertical-align: middle;
                    }
                    .loader {
                        position: fixed;
                        left: 0px;
                        top: 0px;
                        width: 100%;
                        height: 100%;
                        z-index: 9999;
                        background: url('https://i.ibb.co/cXnKsNR/Cube-1s-200px.gif') 50% 50% no-repeat rgb(249, 249, 249);
                    }

                    .card-wrapper {
                      background-color: #f5f5f5;
                      # height: 100vh;
                      # width: 100vw;
                      display: grid;
                    }

                    .card {
                      background-color: #ffff;
                      display: flex;
                      flex-direction: column;
                      # place-self: center;
                      border-radius: 4px;
                      box-shadow: 1px 1px 4px rgba(0,0,0,0.4);
                    }

                    .card__content {
                      padding: 1.5rem;
                      font-family: sans-serif;
                    }

                    .card__header {
                      display: flex;
                      flex-direction: row;
                      justify-content: space-between;
                    }

                    .header__title {
                      font-size: 1.5rem;
                      font-weight: 600;
                      font-family: sans-serif;
                      padding-top: 4%;
                      padding-left: 5%;
                      color: dimgrey;
                    }

                    .header__date {
                      font-size: 1.3rem;
                      font-family: sans-serif;
                      padding-left: 5%;
                      color: darkgray;
                    }

                    .total__count {
                      font-size: 5.3rem;
                      font-family: sans-serif;
                      color: black;
                      padding-top: 8%;
                    }

                    .total_count__label {
                      font-size: 1.3rem;
                      font-family: sans-serif;
                      padding-left: 12%;
                      color: darkgray;
                    }

                    .header__title-icon {
                      font-size: 1.6rem;
                      color: #ccc;
                    }

                    .header__title-icon:hover {
                      color: rgba(54, 162, 235, 1);;
                    }

                    .header__button {
                      border-radius: 50px;
                      background-color: #f5f5f5;
                      padding: 0.5rem 1rem;
                      border: none;
                      margin-left: 1rem;
                    }

                    .header__button:hover {
                      background-color: rgba(54, 162, 235, 0.25);
                    }

                    .chart {
                      padding: 2.0rem 60;
                    }

                    .card__footer {
                      display: flex;
                      flex-direction: row;
                      justify-content: space-between;
                      margin-bottom: 5%;
                    }

                    .card__footer-section {
                      text-align: center;
                      width: 33%;
                      # border-right: 1px solid #ccc;
                    }

                    .card__footer-section:nth-child(3) {
                      border-right: none;
                    }

                    .footer-section__data {
                      font-size: 2.2rem;
                      font-weight: 900;
                    }

                    .footer-section__label {
                      text-transform: uppercase;
                      color: slategrey;
                      font-size: 1.0rem;
                    }

                </style>
            </head>
        </html>
        <body>
            <div class="loader"></div>
            <div class="sidenav">
                <a><img class="wrimagecard" src="__custom_logo__" style="max-width:98%;" /></a>
                <a class="tablink" href="#" id="defaultOpen" onclick="openPage('dashboard', this, 'white', '#565656', 'groove')">
                    <i class="fa fa-home" id="tablinkicon" style="color:currentcolor; margin:5% 5% 5% 10%"></i> Dashboard</a>
                <a class="tablink" href="#" onclick="openPage('suiteMetrics', this, 'white', '#565656', 'groove'); executeDataTable('#sm',2)">
                    <i class="fa fa-briefcase" id="tablinkicon" style="color:currentcolor; margin:5% 5% 5% 10%"></i> Suites</a>
                <a class="tablink" href="#" onclick="openPage('testMetrics', this, 'white', '#565656', 'groove'); executeDataTable('#tm',3)">
                    <i class="fa fa-server" id="tablinkicon" style="color:currentcolor; margin:5% 5% 5% 10%"></i> Test Metrics</a>
            </div>
            <div class="main col-md-9 ml-sm-auto col-lg-10 px-4">
                <div class="tabcontent" id="dashboard">

                    <div class="row rowcard">
                        <div class="col-md-4 border-right" style="margin-left: -1%;">
                          <div class="card" style="width:150%;height:500px;text-align: center;">
                            <div class="card__content">
                              <div style="margin-bottom: -6%; margin-left: 40%;">
                                <span style="color: darkgray; font-size: 17px;">
                                    <i class="fa fa-clock-o" style="color:currentcolor; margin: 2% 2% 0% 29%; font-size: 25px;"></i>
                                        Time taken __execution_time__ secs
                                </span>
                              </div>
                              <div>
                                  <div class="card__header">
                                    <div class="header__title">
                                      PYTEST REPORT
                                    </div>
                                  </div>
                                  <div class="card__header">
                                    <span class="header__date">__date__</span>
                                  </div>
                                  <div style="display: flex;">
                                    <span class="total__count">__total__</span>
                                  </div>
                                  <div style="display: flex;">
                                    <span class="total_count__label">TEST CASES</span>
                                  </div>
                              </div>
                              <div>
                                  <div style="width: 600px;height: 350px; margin-left: 22%;margin-top: -50%;">
                                    <canvas class="chart" id="myChart" style="margin-top: 6%; height: 290px;"></canvas>
                                  </div>
                                  <div style="margin-top: -5%;">
                                      <div class="card__footer">
                                        <div class="card__footer-section">
                                          <div class="footer-section__data" style="color:#98cc64">__pass__</div>
                                          <div class="footer-section__label">passed</div>
                                        </div>
                                        <div class="card__footer-section">
                                          <div class="footer-section__data" style="color:#fc6766">__fail__</div>
                                          <div class="footer-section__label">failed</div>
                                        </div>
                                        <div class="card__footer-section">
                                          <div class="footer-section__data" style="color:#ffd050">__skip__</div>
                                          <div class="footer-section__label">skipped</div>
                                        </div>
                                        <div class="card__footer-section">
                                          <div class="footer-section__data" style="color:#aaaaaa">__xpass__</div>
                                          <div class="footer-section__label">xpassed</div>
                                        </div>
                                        <div class="card__footer-section">
                                          <div class="footer-section__data" style="color:#d35fbf">__xfail__</div>
                                          <div class="footer-section__label">xfailed</div>
                                        </div>
                                      </div>
                                  </div>
                              </div>
                            </div>
                          </div>
                        </div>

                        <div style="max-width: 49.95%; padding-left: 15%;">
                          <div class="card" style="width:150%;height:500px;text-align: center;">
                            <div class="card__content">
                              <div>
                              </div>
                              <div>
                                  <div style="width: 600px;height: 350px; margin-left: 22%;margin-top: -50%;">

                                  </div>
                                  <div style="margin-top: -5%;">
                                      <div class="card__footer">
                                      </div>
                                  </div>
                              </div>
                            </div>
                          </div>
                        </div>

                    </div>

                    <div class="row rowcard" style="padding-top: 0.8%;">
                        <div class="col-md-8 card border-right">
                            <div style="font-size: 1.9rem; color: darkgrey; margin-bottom: -4%;">
                                <div style="font-weight: 550;font-family: sans-serif;padding-top: 5%;padding-left: 2%;"><i class="fa fa-area-chart" style="color:currentcolor; margin-right: 2%; padding-left: 3%;"></i>Test Suite
                                    __test_suite_length__
                                </div>
                            </div>
                            <canvas class="chart" id="groupBarChart" style="margin-top: 6%; height: 451px; width: 903px;"></canvas>
                        </div>
                        <div class="col-md-4 card border-left" style="max-width: 32.4%; padding-left: 3%; padding-top: 2%; margin-left: 0.75%;">
                            <div style="font-size: 1.9rem; color: darkgrey; margin-bottom: -4%;">
                                <div style="font-weight: 550;font-family: sans-serif;padding-top: 5%;padding-left: 2%;"><i class="fa fa-bolt" style="color:currentcolor; margin-right: 2%; padding-left: 3%;"></i>Suite Highlights</div>
                            </div>
                        </div>
                    </div>
                    <hr/>

                    <div class="row">
                        <div class="col-md-12" style="width:auto;">
                            <p class="text-muted" style="text-align:center;font-size:9px"> <a href="https://github.com/prashanth-sams/pytest-html-reporter" target="_blank">pytest-html-reporter</a>
                            </p>
                        </div>
                    </div>
                    <script>
                        window.onload = function() {
                            alignTotalCount();
                            executeDataTable('#sm', 2);
                            executeDataTable('#tm', 3);
                            createBarGraph('#sm', 0, 2, 5, 'suiteBarID', 'Failure ', 'Suite');
                            createPieChart(__pass__, __fail__, __xpass__, __xfail__, 'testChartID', 'Tests Status:');
                            createBarGraph('#tm', 1, 3, 10, 'testsBarID', 'Elapsed Time (s) ', 'Test');
                        };
                    </script>
                </div>
                <div class="tabcontent" id="suiteMetrics">
                    <h4><b><i class="fa fa-briefcase"></i> Test Suite</b></h4>
                    <hr/>
                    <table class="table row-border tablecard" id="sm">
                        <thead>
                            <tr>
                                <th>Suite</th>
                                <th>Pass</th>
                                <th>Fail</th>
                                <th>Skip</th>
                                <th>xPass</th>
                                <th>xFail</th>
                                <th>Error</th>
                            </tr>
                        </thead>
                        <tbody>
                            __suite_metrics_row__
                        </tbody>
                    </table>
                    <div class="row">
                        <div class="col-md-12" style="height:25px;width:auto;"></div>
                    </div>
                </div>
            <div class="tabcontent" id="testMetrics">
                <h4><b><i class="fa fa-table"></i> Test Metrics</b></h4>
                <hr/>
                <table class="table row-border tablecard" id="tm">
                    <thead>
                        <tr>
                            <th>Suite</th>
                            <th>Test Case</th>
                            <th>Status</th>
                            <th>Time (s)</th>
                            <th>Error Message</th>
                        </tr>
                    </thead>
                    <tbody>
                        __test_metrics_row__
                    </tbody>
                </table>
                <div class="row">
                    <div class="col-md-12" style="height:25px;width:auto;"></div>
                </div>
            </div>
            <script>
                function createPieChart(pass_count, fail_count, xpass_count, xfail_count, ChartID, ChartName) {
                    var status = [];
                    status.push(['Status', 'Percentage']);
                    status.push(['PASS', parseInt(pass_count)], ['FAIL', parseInt(fail_count)],
                     ['xPASS', parseInt(xpass_count)], ['xFAIL', parseInt(xfail_count)], );
                    var data = google.visualization.arrayToDataTable(status);
                    var options = {
                        pieHole: 0.6,
                        legend: 'bottom',
                        chartArea: {
                            width: "85%",
                            height: "80%"
                        },
                        colors: ['#2ecc71', '#fc6666', '#9e6b6b', '#96a74c'],
                    };
                    var chart = new google.visualization.PieChart(document.getElementById(ChartID));
                    chart.draw(data, options);
                }
            </script>
            <script>
                function createBarGraph(tableID, keyword_column, time_column, limit, ChartID, Label, type) {
                    var status = [];
                    css_selector_locator = tableID + ' tbody >tr'
                    var rows = $(css_selector_locator);
                    var columns;
                    var myColors = [
                        '#4F81BC',
                        '#C0504E',
                        '#9BBB58',
                        '#24BEAA',
                        '#8064A1',
                        '#4AACC5',
                        '#F79647',
                        '#815E86',
                        '#76A032',
                        '#34558B'
                    ];
                    status.push([type, Label, {
                        role: 'annotation'
                    }, {
                        role: 'style'
                    }]);
                    for (var i = 0; i < rows.length; i++) {
                        if (i == Number(limit)) {
                            break;
                        }
                        //status = [];
                        name_value = $(rows[i]).find('td');
                        time = ($(name_value[Number(time_column)]).html());
                        keyword = ($(name_value[Number(keyword_column)]).html()).trim();
                        status.push([keyword, parseFloat(time), parseFloat(time), myColors[i]]);
                    }
                    var data = google.visualization.arrayToDataTable(status);
                    var options = {
                        legend: 'none',
                        chartArea: {
                            width: "92%",
                            height: "75%"
                        },
                        bar: {
                            groupWidth: '90%'
                        },
                        annotations: {
                            alwaysOutside: true,
                            textStyle: {
                                fontName: 'Comic Sans MS',
                                fontSize: 13,
                                bold: true,
                                italic: true,
                                color: "black", // The color of the text.
                            },
                        },
                        hAxis: {
                            textStyle: {
                                fontName: 'Arial',
                                fontSize: 10,
                            }
                        },
                        vAxis: {
                            gridlines: {
                                count: 10
                            },
                            textStyle: {
                                fontName: 'Comic Sans MS',
                                fontSize: 10,
                            }
                        },
                    };
                    // Instantiate and draw the chart.
                    var chart = new google.visualization.ColumnChart(document.getElementById(ChartID));
                    chart.draw(data, options);
                }
            </script>
            <script>
                function executeDataTable(tabname, sortCol) {
                    var fileTitle;
                    switch (tabname) {
                        case "#sm":
                            fileTitle = "SuiteMetrics";
                            break;
                        case "#tm":
                            fileTitle = "TestMetrics";
                            break;
                        default:
                            fileTitle = "metrics";
                    }
                    $(tabname).DataTable({
                        retrieve: true,
                        "order": [
                            [Number(sortCol), "desc"]
                        ],
                        dom: 'l<".margin" B>frtip',
                        "lengthMenu": [[10, 25, 50, 100, -1], [10, 25, 50, 100, "All"]],
                        buttons: [
                        {
                            extend:    'copyHtml5',
                            text:      '<i class="fa fa-files-o"></i>',
                            filename: function() {
                                return fileTitle + '-' + new Date().toLocaleString();
                            },
                            titleAttr: 'Copy',
                            exportOptions: {
                                columns: ':visible'
                            }
    					},
                        {
                            extend:    'csvHtml5',
                            text:      '<i class="fa fa-file-text-o"></i>',
                            titleAttr: 'CSV',
                            filename: function() {
                                return fileTitle + '-' + new Date().toLocaleString();
                            },
                            exportOptions: {
                                columns: ':visible'
                            }
                        },
                        {
                            extend:    'excelHtml5',
                            text:      '<i class="fa fa-file-excel-o"></i>',
                            titleAttr: 'Excel',
                            filename: function() {
                                return fileTitle + '-' + new Date().toLocaleString();
                            },
                            exportOptions: {
                                columns: ':visible'
                            }
                        },
                        {
                            extend:    'print',
                            text:      '<i class="fa fa-print"></i>',
                            titleAttr: 'Print',
                            exportOptions: {
                                columns: ':visible',
                                alignment: 'left',
                            }
                        },
                        {
                            extend:    'colvis',
                            collectionLayout: 'fixed two-column',
                            text:      '<i class="fa fa-low-vision"></i>',
                            titleAttr: 'Hide Column',
                            exportOptions: {
                                columns: ':visible'
                            },
                            postfixButtons: [ 'colvisRestore' ]
                        },
                    ],
                    columnDefs: [ {
                        visible: false,
                    } ]
                    }
                );
            }
            </script>
            <script>
                function alignTotalCount() {
                    arr1 = [1, 2, 3, 4, 5];
                    arr2 = ['19%', '14%', '11%', '7%', '4%'];
                    zipped = arr1.map((x, i) => [x, arr2[i]]);
                    var x = parseInt(__total__);
                    size = zipped[(x.toString().length)-1][1];
                    document.getElementsByClassName("total__count")[0].style.paddingLeft = `${size}`;
                }
            </script>
            <script>
                function openPage(pageName,elmnt,color,bgcolor,borderstyle) {
                    var i, tabcontent, tablinks;
                    tabcontent = document.getElementsByClassName("tabcontent");
                    for (i = 0; i < tabcontent.length; i++) {
                        tabcontent[i].style.display = "none";
                    }
                    tablinks = document.getElementsByClassName("tablink");
                    for (i = 0; i < tablinks.length; i++) {
                        tablinks[i].style.color = "";
                        tablinks[i].style.background = "";
                        tablinks[i].style.borderRight = "";
                    }
                    document.getElementById(pageName).style.display = "block";
                    elmnt.style.color = color;
                    elmnt.style.background = bgcolor;
                    elmnt.style.borderRight = borderstyle;
                }
                // Get the element with id="defaultOpen" and click on it
                document.getElementById("defaultOpen").click();
            </script>
            <script>
                // Get the element with id="defaultOpen" and click on it
                document.getElementById("defaultOpen").click();
            </script>
            <script>
                $(window).on('load',function(){$('.loader').fadeOut();});
            </script>
            <script>
                var ctx = document.getElementById('myChart');
                var myChart = new Chart(ctx, {
                    type: 'doughnut',
                    data: {
                        labels: ['PASS', 'FAIL', 'SKIP', 'XPASS', 'XFAIL'],
                        datasets: [{
                            label: '# of Votes',
                            data: [__pass__, __fail__, __skip__, __xpass__, __xfail__],
                            backgroundColor: [
                                '#98cc64',
                                '#fc6766',
                                '#ffd050',
                                '#aaaaaa',
                                '#d35fbf'
                            ],
                            hoverBackgroundColor: [
                                "#84b356",
                                "#e35857",
                                "#e4b942",
                                "#bdbbbb",
                                "#c357b0"
                            ],
                            hoverBorderColor: [
                                '#9bca6d',
                                '#fd8a89',
                                '#ffcf4c',
                                '#abaaaa',
                                '#f26fdb'
                            ]
                        }]
                    },
                    options: {
                      doughnut_chart: true,
                      legend: {
                        display: false
                      },
                      responsive: true,
                      cutoutPercentage: 80,
                      tooltips: {
                          callbacks: {
                            title: function(tooltipItem, data) {
                                return data['labels'][tooltipItem[0]['index']];
                            },
                            label: function(tooltipItem, data) {
                                return ''
                            },
                            afterLabel: function(tooltipItem, data) {
                              var dataset = data['datasets'][0];
                              var percent = Math.round((dataset['data'][tooltipItem['index']] / dataset["_meta"][0]['total']) * 100)
                              return percent + '%';
                            }
                          },
                          backgroundColor: '#FFF',
                          titleFontSize: 16,
                          titleFontColor: '#555555',
                          bodyFontColor: '#000',
                          bodyFontSize: 14,
                          displayColors: false,
                          borderColor: '#555555',
                          borderWidth: 3,
                          multiKeyBackground: '#555555',
                          cornerRadius: 3,
                          caretSize: 15,
                          caretPadding: 13,
                          xPadding: 12,
                          yPadding: 12
                        }
                    }
                });

                Chart.pluginService.register({
                    beforeDraw: function(chart) {
                        if (chart.config.options.doughnut_chart) {
                            var width = chart.chart.width,
                                height = chart.chart.height,
                                ctx = chart.chart.ctx;

                            ctx.restore();
                            var fontSize = (height / 114).toFixed(2);
                            ctx.font = fontSize + "em sans-serif";
                            ctx.textBaseline = "middle";

                            var passPercent = Math.round((__pass__ / __total__) * 100)

                            var text = passPercent + "%",
                                textX = Math.round((width - ctx.measureText(text).width) / 2),
                                textY = height / 2;

                            ctx.fillText(text, textX, textY);
                            ctx.save();
                        }
                      }
                    });
            </script>

            <script>
                var ctx = document.getElementById('groupBarChart').getContext('2d');
                var myChart = new Chart(ctx, {
                    type: 'bar',
                    data: {
                        labels: __test_suites__,
                        datasets: [{
                            label: 'Passed',
                            backgroundColor: '#98cc64',
                            hoverBackgroundColor: '#84b356',
                            borderColor: '#9bca6d',
                            borderWidth: 1,
                            data: __test_suite_pass__
                        }, {
                            label: 'Failed',
                            backgroundColor: '#fc6766',
                            hoverBackgroundColor: '#e35857',
                            borderColor: '#fd8a89',
                            borderWidth: 1,
                            data: __test_suites_fail__
                        }, {
                            label: 'Skipped',
                            backgroundColor: '#ffd050',
                            hoverBackgroundColor: '#e4b942',
                            borderColor: '#ffcf4c',
                            borderWidth: 1,
                            data: __test_suites_skip__
                        }, {
                            label: 'XPassed',
                            backgroundColor: '#aaaaaa',
                            hoverBackgroundColor: '#bdbbbb',
                            borderColor: '#abaaaa',
                            borderWidth: 1,
                            data: __test_suites_xpass__
                        }, {
                            label: 'XFailed',
                            backgroundColor: '#d35fbf',
                            hoverBackgroundColor: '#c357b0',
                            borderColor: '#f26fdb',
                            borderWidth: 1,
                            data: __test_suites_xfail__
                        }]
                    },
                    options: {
                        title: {
                            display: false,
                            text: 'Test Suites'
                        },
                        tooltips: {
                            mode: 'index',
                            intersect: false,
                            backgroundColor: '#FFF',
                            titleFontSize: 16,
                            titleFontColor: '#555555',
                            bodyFontColor: '#000',
                            bodyFontSize: 14,
                            displayColors: false,
                            borderColor: '#555555',
                            borderWidth: 3,
                            multiKeyBackground: '#555555',
                            cornerRadius: 3,
                            caretSize: 15,
                            caretPadding: 13,
                            xPadding: 12,
                            yPadding: 12
                        },
                        legend: {
                            display: false
                        },
                        responsive: true,
                        scales: {
                            xAxes: [{
                                stacked: true
                            }],
                            yAxes: [{
                                stacked: true,
                                ticks: {
                                    beginAtZero: true
                                }
                            }]
                        }
                    }
                });
            </script>

        </body>
    	"""

    def renew_template_text(self, logo_url):
        template_text = self.html_template()
        template_text = template_text.replace("__custom_logo__", logo_url)
        template_text = template_text.replace("__execution_time__", str(round(_execution_time, 2)))
        # template_text = template_text.replace("__executed_by__", str(platform.uname()[1]))
        # template_text = template_text.replace("__os_name__", str(platform.uname()[0]))
        # template_text = template_text.replace("__python_version__", str(sys.version.split(' ')[0]))
        # template_text = template_text.replace("__generated_date__", str(datetime.datetime.now().strftime("%b %d %Y, %H:%M")))
        template_text = template_text.replace("__total__", str(_total))
        template_text = template_text.replace("__executed__", str(_executed))
        template_text = template_text.replace("__pass__", str(_pass))
        template_text = template_text.replace("__fail__", str(_fail))
        template_text = template_text.replace("__skip__", str(_skip))
        # template_text = template_text.replace("__error__", str(_error))
        template_text = template_text.replace("__xpass__", str(_xpass))
        template_text = template_text.replace("__xfail__", str(_xfail))
        template_text = template_text.replace("__suite_metrics_row__", str(_suite_metrics_content))
        template_text = template_text.replace("__test_metrics_row__", str(_test_metrics_content))
        template_text = template_text.replace("__date__", str(self._date()))
        template_text = template_text.replace("__test_suites__", str(_test_suite_name))
        template_text = template_text.replace("__test_suite_length__", str(len(_test_suite_name)))
        template_text = template_text.replace("__test_suite_pass__", str(_test_pass_list))
        template_text = template_text.replace("__test_suites_fail__", str(_test_fail_list))
        template_text = template_text.replace("__test_suites_skip__", str(_test_skip_list))
        template_text = template_text.replace("__test_suites_xpass__", str(_test_xpass_list))
        template_text = template_text.replace("__test_suites_xfail__", str(_test_xfail_list))
        return template_text
