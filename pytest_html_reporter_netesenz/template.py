def html_template():
    return """
	<!DOCTYPE doctype html>
    <html lang="en">
        <head>
            <link href="https://i.imgur.com/UwGDzXn.png" rel="shortcut icon" type="image/x-icon" />
            <title>Pytest HTML Reporter</title>
            <meta charset="utf-8" />
            <meta content="width=device-width, initial-scale=1" name="viewport" />
            <link href="https://cdn.datatables.net/1.10.19/css/jquery.dataTables.min.css" rel="stylesheet" crossorigin="anonymous"/>
            <link href="https://cdn.datatables.net/buttons/1.5.2/css/buttons.dataTables.min.css" rel="stylesheet" crossorigin="anonymous" />
            <link href="https://cdnjs.cloudflare.com/ajax/libs/twitter-bootstrap/4.1.3/css/bootstrap.min.css" rel="stylesheet" crossorigin="anonymous" />
            <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css" rel="stylesheet" crossorigin="anonymous"/>
            <script src="https://cdn.jsdelivr.net/npm/jquery@3.5.1/dist/jquery.min.js"></script>
            <link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/fancyapps/fancybox@3.5.7/dist/jquery.fancybox.min.css" crossorigin="anonymous"/>
            <script src="https://cdn.jsdelivr.net/gh/fancyapps/fancybox@3.5.7/dist/jquery.fancybox.min.js"></script>
            
            <script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/1.3.2/jspdf.min.js"></script>
            <script src="https://cdnjs.cloudflare.com/ajax/libs/dom-to-image/2.6.0/dom-to-image.min.js"></script>
            <script src="https://maxcdn.bootstrapcdn.com/bootstrap/4.1.3/js/bootstrap.min.js"></script>

            <!-- Bootstrap core Datatable-->
            <script src="https://cdn.datatables.net/1.10.19/js/jquery.dataTables.min.js" type="text/javascript" crossorigin="anonymous"></script>
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
                    width: 220px;
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
                    font-size: 14px;
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
                    background: url('https://i.imgur.com/n3Tcoxz.gif') 50% 50% no-repeat rgb(249, 249, 249);
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
                
                .time__taken {
                    color: darkgray;
                    font-size: 17px;
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
                  font-size: 2.6rem;
                  font-weight: 900;
                }
                
                .archive-footer-section__data {
                  font-size: 4.2rem;
                  font-weight: 700;
                }
                
                .footer-section__label {
                  text-transform: uppercase;
                  color: slategrey;
                  font-size: 10pt;
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
                    background-color: #ffff;
                    max-width: 80%;
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
                    height: 50%;
                    width: 48%;
                    margin-left: 40%;
                    margin-top: 6%;
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
                    width: 220px;
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
                    margin: 0px 0 32px;
                    color: dimgrey;
                    float: right;
                }
                
                .loading .icon {
                    padding-right: 15px;
                }
                
                .loading .percentage {
                    float: right;
                }
                
                .loading .progress-bar {
                    height: 20px;
                    background: #50597b;
                    border-radius: 5px;
                    margin: 0 auto;
                    margin-top: -4%;
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
                
                .desc-video h2 {
                     margin-top: 0px;
                }
                 .desc-video-none {
                     display: none;
                }
                 .video {
                     display: block;
                     position: relative;
                     padding-top: 60%;
                     overflow: hidden;
                     background-repeat: no-repeat;
                     background-position: center center;
                     background-size: cover;
                }
                 .video:hover .video-hover-desc {
                     margin-top: -170px;
                     height: 170px;
                }
                 .video:hover .video-hover-desc:before {
                     background: linear-gradient(to top,rgba(35,72,133,0.82),rgba(35,72,133,0));
                     transition: .3s;
                }
                 .img-hover .text-desc {
                     display: none;
                }
                 .below-desc {
                     display: block;
                     height: 70px;
                     width: 100%;
                     padding: 10px;
                }
                 .video-hover-desc {
                     display: block;
                     padding: 10px 20px;
                     background-color: #234885;
                     background-color: rgba(35,72,133,0.82);
                     height: 90px;
                     margin-top: -90px;
                     transition: .3s;
                     color: white;
                     text-shadow: none;
                }
                 .video-hover-desc:before {
                     display: block;
                     position: absolute;
                     content: '';
                     left: 0;
                     right: 0;
                     height: 116px;
                     transition: .3s;
                     margin-top: -126px;
                }
                 .video-hover-desc h2 {
                     color: white;
                     margin-top: 0px;
                     height: 50px;
                }
                 .video-hover-desc.video-hover-small {
                     height: 50px;
                     margin-top: -50px;
                }
                .modal p {
                    word-wrap: break-word;
                }
                
                .modal-footer {
                    border-top: 0px solid #e9ecef;
                }
                .btn-primary {
                    background-color: #3571a3;
                    border-color: #3571a3;
                }
                
                .dashboard__headers {
                    font-size: 1.9rem;
                    color: darkgrey;
                    margin-bottom: -4%;
                }

                .outer_my_chart {
                    margin-left: 50%;
                    margin-top: -40%;
                    max-height: 43%;
                }
                
                .inner_my_chart {
                    margin-top: 31%;
                    height: 48%;
                    margin-left: 16%;
                    max-width: 75%;
                }
                
                .archive__chart {
                    width: "440px";
                    height: "440px";
                }
                
                @media screen and (max-width: 3560px) {   
                    .footer-section__data {
                        font-size: 3.6rem;
                    }
                    .suite_count_section {
                        margin-top: -16%;
                    }
                }
                
                @media screen and (max-width: 2442px) {
                    .outer_my_chart {
                        margin-top: -40%;
                    }
                    .inner_my_chart {
                        margin-top: 31%;
                    }
                    .footer-section__data {
                        font-size: 3.4rem;
                    }
                    .suite_count_section {
                        margin-top: -17%;
                    }
                }
                
                @media screen and (max-width: 2156px) {
                    .outer_my_chart {
                        margin-top: -42%;
                    }
                    .inner_my_chart {
                        margin-top: 25%;
                    }
                    .suite_count_section {
                        margin-top: -16%;
                    }
                }
                
                @media screen and (max-width: 1940px) {
                    .outer_my_chart {
                        margin-top: -41%;
                    }
                    .inner_my_chart {
                        margin-top: 16%;
                    }
                    .footer-section__data {
                        font-size: 2.6rem;
                    }
                    .suite_count_section {
                        margin-top: -11%;
                    }
                }
                
                @media screen and (max-width: 1662px) {
                    .outer_my_chart {
                        margin-top: -45%;
                    }
                }
                
                @media screen and (max-width: 1307px) {
                    .outer_my_chart {
                        margin-top: -50%;
                    }
                    .px-4 {
                        padding-left: 2.5rem!important;
                    }
                    .loading p {
                        margin: 0px -14px 32px;
                    }
                    .dashboard__headers {
                        font-size: 1.8rem;
                    }
                }
                
                @media screen and (max-width: 1209px) {
                    .outer_my_chart {
                        margin-top: -41%;
                    }
                    .px-4 {
                        padding-left: 4.5rem!important;
                    }
                    .inner_my_chart {
                        margin-top: 0%;
                    }
                    .footer-section__label {
                        font-size: 8pt;
                    }
                    .time__taken {
                        font-size: 14px;
                    }
                    .total__count {
                        font-size: 4.3rem;
                    }
                    .total_count__label {
                        font-size: 1.2rem;
                    }
                    .loading p {
                        font-size: 0.8rem;
                    }
                    .dashboard__headers {
                        font-size: 1.7rem;
                    }
                    .header__title {
                        font-size: 1.3rem;
                        padding-top: 8%;
                    }
                }
                
                @media screen and (max-width: 1148px) {
                    .outer_my_chart {
                        margin-top: -43%;
                    }
                    .dashboard__headers {
                        font-size: 1.5rem;
                    }
                    .header__title {
                        font-size: 1.2rem;
                    }
                    .tooltip-inner {
                        font-size: 75%;
                    }
                    .time__taken {
                        font-size: 13px;
                    }
                }
                
                @media screen and (max-width: 1076px) {
                    .outer_my_chart {
                        margin-top: -52%;
                    }
                    .footer-section__label {
                        font-size: 7pt;
                    }
                    .total__count {
                        padding-top: 13%;
                    }
                }
                
                @media screen and (max-width: 1031px) {
                    .time__taken {
                        margin-left: -5%;
                    }
                    .dashboard__headers {
                        font-size: 1.3rem;
                    }
                    .suite-highlights-header {
                        font-size: 0.75rem;
                    }
                    .tooltip-inner {
                        font-size: 70%;
                    }
                    .header__title {
                        padding-top: 10%;
                    }
                }
                
                .total__tests {
                    font-size: 10.3rem;
                    font-family: sans-serif;
                    color: black;
                    padding-top: 8%;
                }
                
                .archive__label {
                    font-size: 1.8rem;
                    font-family: sans-serif;
                    color: darkgray;
                }
                
                .archive__bar {
                    padding-top: 8.5%;
                }
                
                @media screen and (max-width: 1497px) {
                    .total__tests {
                        font-size: 9.3rem;
                    }
                    .archive__label {
                        font-size: 1.7rem;
                    }
                    .archive__bar {
                        padding-top: 4.5%;
                    }
                }
                
                @media screen and (max-width: 1314px) {
                    .total__tests {
                        font-size: 6.3rem;
                    }
                    .archive__label {
                        font-size: 1.3rem;
                    }
                    .archive__bar {
                        margin-top: -12%;
                        padding-top: 0%;
                    }
                    .count-title {
                        font-size: 40px;
                    }
                    .archive-build-row {
                        right: -2.9%;
                    }
                }
                
                @media screen and (max-width: 1114px) {
                    .total__tests {
                        font-size: 5.3rem;
                    }
                    .archive__label {
                        font-size: 1.1rem;
                    }
                    .archive__bar {
                        margin-top: -25%;
                        padding-top: 0%;
                    }
                    .count-title {
                        font-size: 40px;
                    }
                    .archive-build-row {
                        right: -4.9%;
                    }
                    .list-group-item {
                        padding: 0.75rem 0.25rem;
                    }
                }
                
            </style>
            <style>
                .progress-bar.downloading {
                    background: -webkit-linear-gradient(left, #fc6665 __max_failure_percent__%,#50597b __max_failure_percent__%); /* Chrome10+,Safari5.1+ */
                    background: -ms-linear-gradient(left, #fc6665 __max_failure_percent__%,#50597b __max_failure_percent__%); /* IE10+ */
                    background: linear-gradient(to right, #fc6665 __max_failure_percent__%,#50597b __max_failure_percent__%); /* W3C */
                }
            </style>
        </head>
    </html>
    <body>
        <div class="loader"></div>
        <div class="sidenav">
            <a onclick="openPage('dashboard', this, '', '', '')" href="#dashboard">
                <img id="wrimagecard" class="wrimagecard" src="__custom_logo__" style="max-width:98%;" />
            </a>
            <a class="tablink" href="#dashboard" id="defaultOpen" onclick="openPage('dashboard', this, 'white', '#565656', 'groove')">
                <i class="fa fa-home" id="tablinkicon" style="color:currentcolor; margin:5% 5% 5% 10%"></i> Dashboard
            </a>
            <a class="tablink" href="#suites" onclick="openPage('suiteMetrics', this, 'white', '#565656', 'groove'); executeDataTable('#sm',2)">
                <i class="fa fa-briefcase" id="tablinkicon" style="color:currentcolor; margin:5% 5% 5% 10%"></i> Suites
            </a>
            <a class="tablink" href="#test-metrics" onclick="openPage('testMetrics', this, 'white', '#565656', 'groove'); executeDataTable('#tm',3)">
                <i class="fa fa-server" id="tablinkicon" style="color:currentcolor; margin:5% 5% 5% 10%"></i> Test Metrics
            </a>
            <a class="tablink" href="#archives" onclick="openPage('archives', this, 'white', '#565656', 'groove');">
                <i class="fa fa-history" id="tablinkicon" style="color:currentcolor; margin:5% 5% 5% 10%"></i> Archives
            </a>
            <a class="tablink" href="#screenshots" onclick="openPage('screenshots', this, 'white', '#565656', 'groove');">
                <i class="fa fa-camera" id="tablinkicon" style="color:currentcolor; margin:5% 5% 5% 10%"></i> Screenshots
            </a>
        </div>
        <div class="main col-md-9 ml-sm-auto col-lg-10 px-4" style="height: 100%;">
            <div class="tabcontent" id="dashboard">
                
                <div class="row rowcard">
                    <div class="col-md-6 card" style="max-width: 49%;">
                      <div style="width:100%;height:500px;text-align: center;">
                        <div class="card__content">
                          <div style="margin-bottom: -4%; margin-left: 30%;">
                            <span class="time__taken">
                                <svg width="22px" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false" style="margin: -1% 2% 0% 29%; -ms-transform: rotate(360deg); -webkit-transform: rotate(360deg); transform: rotate(360deg);" preserveAspectRatio="xMidYMid meet" viewBox="0 0 1536 1536"><path d="M896 416v448q0 14-9 23t-23 9H544q-14 0-23-9t-9-23v-64q0-14 9-23t23-9h224V416q0-14 9-23t23-9h64q14 0 23 9t9 23zm416 352q0-148-73-273t-198-198t-273-73t-273 73t-198 198t-73 273t73 273t198 198t273 73t273-73t198-198t73-273zm224 0q0 209-103 385.5T1153.5 1433T768 1536t-385.5-103T103 1153.5T0 768t103-385.5T382.5 103T768 0t385.5 103T1433 382.5T1536 768z" fill="#a9a9a9"/></svg>
                                    Time taken __execution_time__
                            </span>
                          </div>
                          <div>
                              <div class="card__header">
                                <div class="header__title">
                                  __title__
                                </div>
                              </div>
                              <div class="card__header">
                                <span class="header__date">__date__</span>
                                <span class="header__date">Environment: __env__</span>
                              </div>
                              <div style="display: flex;">
                                <span class="total__count">__total__</span>
                              </div>
                              <div style="display: flex;">
                                <span class="total_count__label">TEST CASES</span>
                              </div>
                          </div>
                          <div>
                              <div class="outer_my_chart">
                                <canvas id="myChart" class="inner_my_chart" style="height: 38%;"></canvas>
                              </div>
                          </div>
                          <div style="margin-top: 23%;position: static;">
                              <div class="suite_count_section">
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
                                    <div class="card__footer-section">
                                      <div class="footer-section__data" style="color:#e6a800">__rerun__</div>
                                      <div class="footer-section__label">rerun</div>
                                    </div>
                                  </div>
                              </div>                          
                          </div>
                        </div>
                      </div>
                    </div>
                    
                    <div class="col-md-6 card" style="margin-left: 0.75%;">
                      <a href="#" id="download" download="pytest-html-reporter.pdf" target="_self">
                        <i class="fa fa-download" style="color:dimgrey; font-size: 1.75rem; padding-top: 2%; float: right; position: fixed; right: 50px;"></i>
                      </a>
                      <div style="text-align: center;">
                        <div>
                            <div class="dashboard__headers">
                                <div style="font-weight: 550;font-family: sans-serif;padding-top: 5%;padding-left: 2%;"><svg height="32pt" viewBox="0 0 512 512.00007" width="25pt" xmlns="http://www.w3.org/2000/svg"><path style="fill: currentColor;" d="m509.785156 15.433594c-.773437-6.972656-6.277344-12.480469-13.253906-13.253906-118.703125-13.183594-219.890625 34.300781-302.429688 119.265624-23.621093 24.316407-44.109374 50.054688-61.597656 74.894532-29.597656-1.203125-62.414062 12.1875-85.679687 35.453125l-42.429688 42.429687c-4.800781 4.800782-5.777343 12.230469-2.382812 18.109375 3.394531 5.878907 10.3125 8.742188 16.875 6.988281 9.84375-2.644531 25.839843-5.71875 41.207031-6.433593 5.617188-.261719 10.285156-.179688 14.164062.117187-9.363281 18.007813-16.539062 33.09375-18.917968 36.871094-3.726563 5.929688-2.863282 13.644531 2.089844 18.597656l24.550781 24.550782c-35.730469 48.730468-36.320313 73.6875-36.195313 77.222656.261719 7.488281 6.101563 14.503906 15.773438 14.503906 8.375 0 32.394531-3.554688 76.121094-36.027344l25.824218 25.824219c4.988282 4.988281 12.78125 5.824219 18.71875 2.011719 4.039063-2.597656 18.238282-9.472656 35.265625-18.371094.28125 12.691406-1.441406 31.328125-5.179687 56.589844-2.125 14.328125 15.292968 22.953125 25.445312 12.804687l42.429688-42.429687c21.878906-21.878906 34.566406-54.375 33.628906-84.859375 26.167969-18.285157 53.390625-39.855469 78.808594-64.78125 84.15625-82.527344 130.179687-182.949219 117.164062-300.078125zm-28.695312 15.4375c2.394531 32.34375-.160156 63.695312-7.601563 94.035156-18.480469-5.820312-36.546875-17.253906-52.863281-33.566406-16.375-16.378906-27.832031-34.519532-33.628906-53.066406 30.328125-7.332032 61.699218-9.816407 94.09375-7.402344zm-422.953125 232.039062 9.898437-9.902344c11.972656-11.96875 27.542969-20.589843 43.027344-24.464843-8.089844 12.839843-15.300781 25.101562-21.660156 36.417969-9.824219-2.167969-20.746094-2.570313-31.265625-2.050782zm28.386719 72.230469c3.246093-6.40625 7.171874-14.4375 14.378906-28.054687l19.746094 19.75c-7.347657 7.882812-13.980469 15.371093-19.957032 22.46875zm73.355468-5.738281c10.929688-10.925782 21.410156-12.921875 34.429688-13.203125-.285156 12.6875-2.320313 23.523437-13.214844 34.417969-46.570312 46.570312-78.492188 67.367187-97.582031 76.648437 9.417969-19.457031 30.269531-51.765625 76.367187-97.863281zm16.871094 95.964844-15.46875-15.472657c7.0625-6 14.527344-12.652343 22.402344-20.027343l21.019531 21.019531c-13.820313 7.378906-19.585937 10.15625-27.953125 14.480469zm82.214844 18.570312-12.007813 12.011719c.972657-14.550781.636719-25.152344-.738281-33.332031 11.03125-6.210938 23.011719-13.253907 35.566406-21.132813-3.578125 15.859375-11.621094 31.257813-22.820312 42.453125zm-26.953125-48.167969-26.894531-26.898437c19.902343-21.898438 19.160156-43 19.160156-67.652344 0-8.285156-6.714844-15-15-15-23.03125 0-45.195313-1.234375-67.652344 19.164062l-25.683594-25.683593c70.132813-122.980469 151.199219-200.839844 242.28125-232.902344 7.210938 23.332031 21.246094 45.8125 41.191406 65.757813 19.851563 19.855468 42.226563 33.855468 65.457032 41.09375-32.25 90.582031-110.089844 171.597656-232.859375 242.121093zm0 0"/><path style="fill: currentColor;" d="m378.199219 133.765625c-29.246094-29.242187-76.832031-29.242187-106.074219 0-29.242188 29.246094-29.242188 76.832031 0 106.074219 29.242188 29.242187 76.828125 29.246094 106.074219 0 29.242187-29.242188 29.242187-76.828125 0-106.074219zm-21.214844 84.859375c-17.546875 17.546875-46.101563 17.546875-63.644531 0-17.546875-17.546875-17.546875-46.097656 0-63.644531 17.542968-17.542969 46.09375-17.546875 63.644531 0 17.546875 17.546875 17.546875 46.097656 0 63.644531zm0 0"/></svg>&nbsp;&nbsp;Trends
                                </div>
                            </div>
                            <canvas id="trends" width="100%" height="360px" style="margin-top: 10%; max-height: 375px; padding-bottom: 4%;"></canvas>
                        </div>
                      </div>
                    </div>
                    
                </div>
                
                <div class="row rowcard" style="padding-top: 0.8%;">
                    <div class="col-md-8 card border-right">
                        <div class="dashboard__headers">
                            <div style="font-weight: 550;font-family: sans-serif;padding-top: 5%;padding-left: 5%;">
                                <svg xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false" width="1.34em" height="1em" style="margin-top: -1%; margin-right: 2%; padding-left: 0.9%; -ms-transform: rotate(360deg); -webkit-transform: rotate(360deg); transform: rotate(360deg);" preserveAspectRatio="xMidYMid meet" viewBox="0 0 2048 1536"><path d="M2048 1408v128H0V0h128v1408h1920zM1664 384l256 896H256V704l448-576l576 576z" fill="#a9a9a9"/></svg>Test Suite
                                __test_suite_length__
                            </div>
                        </div>
                        <canvas class="chart" id="groupBarChart" style="margin-top: 6%; height: 451px; width: 903px;"></canvas>
                    </div>
                    <div class="col-md-4 card border-left" style="max-width: 32.4%; padding-left: 3%; padding-top: 2%; margin-left: 0.75%;">
                        <div class="dashboard__headers">
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
                        failureScreenshots();
                        executeDataTable('#sm', 2);
                        executeDataTable('#tm', 3);
                    };
                </script>
            </div>
            <div class="tabcontent" id="suiteMetrics">
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
                            <th>Rerun</th>
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
        <div class="tabcontent" id="screenshots">
            <div id="content">
              <div class="fold-main">
                <div class="container-fluid">
                  <div id="main-content">
                    <div class="bg-highlight p-4 mt-3">
                      <div class="row">
                        __attach_screenshot_details__
                        <div class="below-desc"></div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
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
                        responsive: true,
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
        <script>
            var lineCanvas = document.getElementById('trends').getContext("2d");
            var trends = new Chart(lineCanvas, {
                type: 'line',
                data: {
                  labels : __trends_label__,
                  datasets : [
                    {
                      label: 'Passed',
                      fill: false,
                      borderColor : "#98cc64",
                      pointBackgroundColor : "#b3c89e",
                      data : __tpass__
                    },
                    {
                      label: 'Failed',
                      fill: false,
                      borderColor : "#fc6766",
                      pointBackgroundColor : "#d68d8c",
                      data : __tfail__
                    },
                    {
                      label: 'Skipped',
                      fill: false,
                      borderColor : "#ffd050",
                      pointBackgroundColor : "#dac079",
                      data : __tskip__
                    }
                  ]
                },
                options : {
                    title: {
                        display: false,
                        text: 'Trends'
                    },
                    legend: {
                        display: false
                    },
                    responsive: true,
                    maintainAspectRatio: false,
                    tooltips: {
                        mode: 'point',
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
                    }
                }
            });
        </script>
        <script>
            function failureScreenshots() {
                $('.video').hover(function (e) {
                  var hoverText = $(this).siblings('.text-desc').html();
                
                  $(e.target).closest('.bg-highlight').find('.below-desc').first().html(hoverText);
                }, function (e) {
                  $(e.target).closest('.bg-highlight').find('.below-desc').first().html('');
                });
            }
            
            $('#download').click(function () {
                domtoimage.toPng(document.getElementById('dashboard'))
                .then(function (blob) {
                    var pdf = new jsPDF('l', 'pt', [$('#dashboard').width()+20, $('#dashboard').height()]);
                    pdf.addImage(blob, 'PNG', 10, 10, $('#dashboard').width(), $('#dashboard').height());
                    pdf.save("pytest_html_reporter.pdf");
                });
            });

        </script>
        
    </body>
	"""
