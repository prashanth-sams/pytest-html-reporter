
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
                  padding: 2.0rem 52;
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
                <i class="fa fa-dashboard" id="tablinkicon" style="color:CORNFLOWERBLUE; margin:5% 5% 5% 10%"></i> Dashboard</a>
            <a class="tablink" href="#" onclick="openPage('suiteMetrics', this, 'white', '#565656', 'groove'); executeDataTable('#sm',2)">
                <i class="fa fa-th-large" id="tablinkicon" style="color:CADETBLUE; margin:5% 5% 5% 10%"></i> Suite Metrics</a>
            <a class="tablink" href="#" onclick="openPage('testMetrics', this, 'white', '#565656', 'groove'); executeDataTable('#tm',3)">
                <i class="fa fa-list-alt" id="tablinkicon" style="color:PALEVIOLETRED; margin:5% 5% 5% 10%"></i> Test Metrics</a>
        </div>
        <div class="main col-md-9 ml-sm-auto col-lg-10 px-4">
            <div class="tabcontent" id="dashboard">
                
                <div class="row rowcard">
                    <div class="col-md-4 border-right">
                          <div class="card" style="width:150%;height:500px;text-align: center;">
                            <div class="card__content">
                              <div>
                                  <div class="card__header">
                                    <div class="header__title">
                                      PYTEST REPORT
                                    </div>
                                  </div>
                                  <div class="card__header">
                                    <span class="header__date">July 24, 2020</span>
                                  </div>
                              </div>
                              <div>
                                  <div style="width: 600px;height: 350px; margin-left: 22%;margin-top: -15%;">
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
            });
        </script>
    </body>
	"""