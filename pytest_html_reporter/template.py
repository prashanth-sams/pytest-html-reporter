
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
                background-color: white;
                overflow-x: hidden;
            }
            .sidenav a {
                padding: 12px 10px 8px 12px;
                text-decoration: none;
                font-size: 18px;
                color: Black;
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
                border-radius: 10px;
                transition: all 0.3s ease;
                background-color: #f8f9fa;
            }
            .rowcard {
                padding-top: 10px;
                box-shadow: 12px 15px 20px 0px rgba(46, 61, 73, 0.15);
                border-radius: 15px;
                transition: all 0.3s ease;
                background-color: white;
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
        </style>
    </head>
    </html>
    <body>
        <div class="loader"></div>
        <div class="sidenav">
            <a><img class="wrimagecard" src="__custom_logo__" style="height:20vh;max-width:98%;" /></a>
            <a class="tablink" href="#" id="defaultOpen" onclick="openPage('dashboard', this, '#fc6666')">
                <i class="fa fa-dashboard" style="color:CORNFLOWERBLUE"></i> Dashboard</a>
            <a class="tablink" href="#" onclick="openPage('suiteMetrics', this, '#fc6666'); executeDataTable('#sm',2)">
                <i class="fa fa-th-large" style="color:CADETBLUE"></i> Suite Metrics</a>
            <a class="tablink" href="#" onclick="openPage('testMetrics', this, '#fc6666'); executeDataTable('#tm',3)">
                <i class="fa fa-list-alt" style="color:PALEVIOLETRED"></i> Test Metrics</a>
        </div>
        <div class="main col-md-9 ml-sm-auto col-lg-10 px-4">
            <div class="tabcontent" id="dashboard">
                <div class="d-flex flex-column flex-md-row align-items-center p-1 mb-3 bg-light border-bottom shadow-sm rowcard">
                    <h5 class="my-0 mr-md-auto font-weight-normal"><i class="fa fa-dashboard"></i> Dashboard</h5>
                    <nav class="my-2 my-md-0 mr-md-3" style="color:red">
                        <a class="p-2"><b style="color:black;">Execution Time:</b> __execution_time__ s</a>
                    </nav>
                </div>
                <div class="row rowcard">
                    <div class="col-md-4 border-right">
                        <table style="width:100%;height:200px;text-align: center;">
                            <tbody>
                                <tr style="height:60%">
                                    <td>
                                        <table style="width:100%">
                                            <tbody>
                                                <tr style="height:100%">
                                                    <td style="font-size:60px; color:rgb(105, 135, 219)">__total__</td>
                                                </tr>
                                                <tr>
                                                    <td>
                                                        <span style="color: #999999;font-size:12px">Total</span>
                                                    </td>
                                                </tr>
                                            </tbody>
                                        </table>
                                    </td>
                                </tr>
                                <tr style="height:25%">
                                    <td>
                                        <table style="width:100%">
                                            <tbody>
                                                <tr align="center" style="height:70%;font-size:25px" valign="middle">
                                                    <td style="width: 33%; color:rgb(17, 3, 3)">__executed__</td>
                                                    <td style="width: 33%; color:#96a74c">__skip__</td>
                                                </tr>
                                                <tr align="center" style="height:30%" valign="top">
                                                    <td style="width: 33%">
                                                        <span style="color: #999999;font-size:10px">Executed</span>
                                                    </td>
                                                    <td style="width: 33%">
                                                        <span style="color: #999999;font-size:10px">Skip</span>
                                                    </td>
                                                </tr>
                                            </tbody>
                                        </table>
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                    <div class="col-md-4 borders" data-toggle="tooltip">
                        <table style="width:100%;height:200px;text-align: center;">
                            <tbody>
                                <tr style="height:100%">
                                    <td>
                                        <table style="width:100%">
                                            <tbody>
                                                <tr style="height:100%">
                                                    <td style="font-size:60px; color:#2ecc71">__pass__</td>
                                                    <td style="font-size:60px; color:#fc6666">__fail__</td>
                                                </tr>
                                                <tr>
                                                    <td>
                                                        <span style="color: #999999;font-size:12px">Pass</span>
                                                    </td>
                                                    <td>
                                                        <span style="color: #999999;font-size:12px">Fail</span>
                                                    </td>
                                                </tr>
                                            </tbody>
                                        </table>
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                    <div class="col-md-4 border-left">
                        <table style="width:100%;height:200px;text-align: center;">
                            <tbody>
                                <tr style="height:100%">
                                    <td>
                                        <table style="width:100%">
                                            <tbody>
                                                <tr style="height:100%">
                                                    <td style="font-size:60px; color:#9e6b6b">__xpass__</td>
                                                    <td style="font-size:60px; color:#96a74c">__xfail__</td>
                                                </tr>
                                                <tr>
                                                    <td>
                                                        <span style="color: #999999;font-size:12px">xPass</span>
                                                    </td>
                                                    <td>
                                                        <span style="color: #999999;font-size:12px">xFail</span>
                                                    </td>
                                                </tr>
                                            </tbody>
                                        </table>
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
                <hr/>
                <div class="row rowcard">
                    <div class="col-md-4"> <span style="font-weight:bold;color:gray">Test Status:</span>
                        <div id="testChartID" style="height:280px;width:auto;"></div>
                    </div>
                    <div class="col-md-8"> <span style="font-weight:bold;color:gray">Top 5 Suite Failures:</span>
                        <div id="suiteBarID" style="height:300px;width:auto;"></div>
                    </div>
                </div>
                <hr/>
                <div class="row rowcard">
                    <div class="col-md-12" style="height:450px;width:auto;"> <span style="font-weight:bold;color:gray">Top 10 Test Performance (sec):</span>
                        <div id="testsBarID" style="height:400px;width:auto;"></div>
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
                        executeDataTable('#sm', 2);
                        executeDataTable('#tm', 3);
                        createBarGraph('#sm', 0, 2, 5, 'suiteBarID', 'Failure ', 'Suite');
                        createPieChart(__pass__, __fail__, __xpass__, __xfail__, 'testChartID', 'Tests Status:');
                        createBarGraph('#tm', 1, 3, 10, 'testsBarID', 'Elapsed Time (s) ', 'Test');
                    };
                </script>
            </div>
            <div class="tabcontent" id="suiteMetrics">
                <h4><b><i class="fa fa-table"></i> Suite Metrics</b></h4>
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
            function openPage(pageName,elmnt,color) {
                var i, tabcontent, tablinks;
                tabcontent = document.getElementsByClassName("tabcontent");
                for (i = 0; i < tabcontent.length; i++) {
                    tabcontent[i].style.display = "none";
                }
                tablinks = document.getElementsByClassName("tablink");
                for (i = 0; i < tablinks.length; i++) {
                    tablinks[i].style.color = "";
                }
                document.getElementById(pageName).style.display = "block";
                elmnt.style.color = color;
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
    </body>
	"""