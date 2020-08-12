def html_template():
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
                
                .archive-card__footer {
                  display: flex;
                  flex-direction: row;
                  justify-content: space-between;
                  margin-bottom: 5%;
                  max-width: 60%;
                  padding-top: 5.5%;
                  padding-left: 5%;
                }
                
                .card__footer-section {
                  text-align: center;
                  width: 33%;
                  # border-right: 1px solid #ccc;
                }
                
                .archive-card__footer-section {
                  text-align: center;
                }
                
                .card__footer-section:nth-child(3) {
                  border-right: none;
                }
                
                .footer-section__data {
                  font-size: 2.2rem;
                  font-weight: 900;
                }
                
                .archive-footer-section__data {
                  font-size: 4.2rem;
                  font-weight: 700;
                }
                
                .footer-section__label {
                  text-transform: uppercase;
                  color: slategrey;
                  font-size: 1.0rem;
                }
                
                .list-group-item {
                    border: 5px solid rgba(0,0,0,0);
                }
                
                .list-group {
                    height: 100%;
                    background-color: #ffff;
                    display: flex;
                    flex-direction: column;
                    place-self: center;
                    border-radius: 4px;
                    box-shadow: 1px 1px 4px rgba(0,0,0,0.4);
                }
                
                .archive-body {
                    height: 100%;
                    background-color: #ffff;
                    max-width: 85%;
                    border-radius: 4px;
                    box-shadow: 1px 1px 4px rgba(0,0,0,0.4);
                    margin-bottom: 0.8%;
                }
                
                .archive-header {
                    padding-top: 4%;
                    padding-left: 5%;
                    color: gray;
                }
                
                .archive-date {
                    padding-top: 2%;
                    padding-left: 5%;
                    color: gray;
                }
                
                .archive-chart-container {
                    margin-top: 6%;
                    height: 50%;
                    width: 50%;
                    margin-left: 40%;
                }
                
                .statistic-section-pass {
                     padding-top: 51px;
                     padding-bottom: 45px;
                     background: #00c6ff;  /* fallback for old browsers */
                     background: linear-gradient(to right, #333333, #2b4440);
                }
                
                .statistic-section-fail {
                     padding-top: 51px;
                     padding-bottom: 45px;
                     background: #00c6ff;  /* fallback for old browsers */
                     background: linear-gradient(to right, #333333, #442b2b);
                }
                
                .count-title {
                    font-size: 50px;
                    font-weight: normal;
                    margin-top: 10px;
                    margin-bottom: 0;
                      text-align: center;
                      font-weight: bold;
                    color: #fff;
                }
                
                .stats-text {
                    font-size: 15px;
                    font-weight: normal;
                    margin-top: 15px;
                    margin-bottom: 0;
                    text-align: center;
                      color: #fff;
                      text-transform: uppercase;
                      font-weight: bold;
                }
                
                .stats-line-black {
                    margin: 12px auto 0;
                    width: 55px;
                    height: 2px;
                    background-color: #fff;
                }
                
                .stats-icon {
                      font-size: 35px;
                      margin: 0 auto;
                    float: none;
                    display: table;
                    color: #fff;
                }
                
                @media (max-width: 992px) {
                    .counter {
                        margin-bottom: 40px;
                    }
                }
                
                .archive-build-row {
                    right: 0.5%;
                    width: 200px;
                    top: 0;
                    bottom: 0;
                    position: fixed;
                    overflow-y: scroll;
                    overflow-x: hidden;
                }
                
                .loading {
                    height: 200px;
                    padding-top: 35px;
                }
                
                .loading p {
                    font-size: 1.1rem;
                    padding-top: 5%;
                    margin: 0px 0 45px;
                    color: dimgrey;
                    float: right;
                }
                
                .loading .icon {
                    padding-right: 15px;
                }
                
                .loading .percentage {
                    float: right;
                    padding: 6px 35px 0 0;
                }
                
                .loading .progress-bar {
                    height: 20px;
                    background: #50597b;
                    border-radius: 5px;
                    margin: 0 auto;
                    margin-top: -4%;
                }
                
                .progress-bar.downloading {
                    background: -webkit-linear-gradient(left, #fc6665 __max_failure_percent__%,#50597b __max_failure_percent__%); /* Chrome10+,Safari5.1+ */
                    background: -ms-linear-gradient(left, #fc6665 __max_failure_percent__%,#50597b __max_failure_percent__%); /* IE10+ */
                    background: linear-gradient(to right, #fc6665 __max_failure_percent__%,#50597b __max_failure_percent__%); /* W3C */
                }
                
                .arrow {
                    left: 50%;
                    color: #403b3b;
                }
                
               .tooltip {
                    position: relative;
                    display: inline-block;
                    margin: 10px 20px;
                    opacity: 1;
                }
                
                .tooltip-inner {
                    background-color: #403b3b;
                }
                
                .bs-tooltip-top .arrow::before {
                    border-top-color: #403b3b;
                }
                
                .suite-highlights-header {
                    font-size: 0.95rem;
                    padding-top: 5%;
                    margin: 0px 0 45px;
                    color: dimgrey;
                    float: right;
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
            <a class="tablink" href="#" onclick="openPage('archives', this, 'white', '#565656', 'groove'); executeDataTable('#tm',3)">
                <i class="fa fa-history" id="tablinkicon" style="color:currentcolor; margin:5% 5% 5% 10%"></i> Archives</a>
        </div>
        <div class="main col-md-9 ml-sm-auto col-lg-10 px-4" style="height: 100%;">
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
                                    <div class="card__footer-section">
                                      <div class="footer-section__data" style="color:#b13635">__error__</div>
                                      <div class="footer-section__label">error</div>
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
                            <div style="font-weight: 550;font-family: sans-serif;padding-top: 5%;padding-left: 2%;">
                                <i class="fa fa-bolt" style="color:currentcolor; margin-right: 2%; padding-left: 3%;"></i>
                                Suite Highlights
                            </div>
                            <div>
                                <div class="loading">
                                    <div style="display: flow-root;">
                                        <div class="tooltip bs-tooltip-top tooltip-dark" role="tooltip">
                                           <div class="arrow" style="left: 50%"></div>
                                           <div class="tooltip-inner">__max_failure_suite_name_final__</div>
                                        </div>
                                        <p class="percentage">__max_failure_suite_count__<sup> /__max_failure_total_tests__</sup> Times</p>
                                    </div>
                                    <div class="progress-bar downloading"></div>
                                    <span class="suite-highlights-header">MOST FAILED SUITE</span>
                                </div>
                            </div>
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
        <div class="tabcontent" id="archives">
            <div id="list-example" class="list-group archive-build-row">
              __archive_status__
            </div>
            
            <div data-spy="scroll" data-target="#list-example" data-offset="0" class="scrollspy-example">
                __archive_body_content__
            </div>
        </div>
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
            function archiveTotalCase(total, i) {
                number = [1, 2, 3, 4, 5];
                container = ['23%', '20%', '15%', '12%', '7%'];
                label = ['-24%', '-2%', '15%', '27%', '31%'];
                
                zipped = container.map((x, i) => [x, label[i]]);
                var x = parseInt(total);
                
                acontainer = zipped[(x.toString().length)-1][0];
                alabel = zipped[(x.toString().length)-1][1];
                
                document.getElementById(`archive-container-${i}`).style.paddingLeft = `${acontainer}`;
                document.getElementById(`archive-label-${i}`).style.marginLeft = `${alabel}`;
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
                    labels: ['PASS', 'FAIL', 'SKIP', 'XPASS', 'XFAIL', 'ERROR'],
                    datasets: [{
                        label: '# of Votes',
                        data: [__pass__, __fail__, __skip__, __xpass__, __xfail__, __error__],
                        backgroundColor: [
                            '#98cc64',
                            '#fc6766',
                            '#ffd050',
                            '#aaaaaa',
                            '#d35fbf',
                            '#b13635'
                        ],
                        hoverBackgroundColor: [
                            "#84b356",
                            "#e35857",
                            "#e4b942",
                            "#bdbbbb",
                            "#c357b0",
                            '#8b2828'
                        ],
                        hoverBorderColor: [
                            '#9bca6d',
                            '#fd8a89',
                            '#ffcf4c',
                            '#abaaaa',
                            '#f26fdb',
                            '#b13635'
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
            for(var i=0; i<=__archive_count__; i++) {
                var MeSeContext = document.getElementById("archive-chart-"+i).getContext("2d");
                var archives = __archives__;
                var pass = archives[i].pass;
                var fail = archives[i].fail;
                var skip = archives[i].skip;
                var xpass = archives[i].xpass;
                var xfail = archives[i].xfail;
                var error = archives[i].error;
                var total = archives[i].total;
                
                archiveTotalCase(total, i)
                
                var MeSeData = {
                    labels: ["PASS", "FAIL", "SKIP", "XPASS", "XFAIL", "ERROR"],
                    datasets: [{
                        label: "Test",
                        data: [pass, fail, skip, xpass, xfail, error],
                        backgroundColor: ["#98cc64", "#fc6766", '#ffd050', '#aaaaaa', '#d35fbf', '#b13635'],
                        hoverBackgroundColor: ["#84b356", "#e35857", "#e4b942", "#bdbbbb", "#c357b0", '#8b2828'],
                        hoverBorderColor: ["#9bca6d", "#fd8a89", "#ffcf4c", "#abaaaa", "#f26fdb", "#b13635"]
                    }]
                };
                
                var MeSeChart = new Chart(MeSeContext, {
                    type: 'horizontalBar',
                    data: MeSeData,
                    options: {
                        legend: {
                            display: false
                        },
                        responsive: false,
                        scales: {
                            yAxes: [{
                                stacked: true
                            }]
                        },
                        tooltips: {
                          backgroundColor: '#FFF',
                          titleFontSize: 10,
                          titleFontColor: '#555555',
                          bodyFontColor: '#000',
                          bodyFontSize: 12,
                          displayColors: false,
                          borderColor: '#555555',
                          borderWidth: 2,
                          multiKeyBackground: '#555555',
                          cornerRadius: 2,
                          caretSize: 5,
                          caretPadding: 5,
                          xPadding: 5,
                          yPadding: 5
                      }
                    }
                });
            }
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
                    }, {
                        label: 'Error',
                        backgroundColor: '#b13635',
                        hoverBackgroundColor: '#8b2828',
                        borderColor: '#b13635',
                        borderWidth: 1,
                        data: __test_suites_error__
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
