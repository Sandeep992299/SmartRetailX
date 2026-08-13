/*
   Licensed to the Apache Software Foundation (ASF) under one or more
   contributor license agreements.  See the NOTICE file distributed with
   this work for additional information regarding copyright ownership.
   The ASF licenses this file to You under the Apache License, Version 2.0
   (the "License"); you may not use this file except in compliance with
   the License.  You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
*/
var showControllersOnly = false;
var seriesFilter = "";
var filtersOnlySampleSeries = true;

/*
 * Add header in statistics table to group metrics by category
 * format
 *
 */
function summaryTableHeader(header) {
    var newRow = header.insertRow(-1);
    newRow.className = "tablesorter-no-sort";
    var cell = document.createElement('th');
    cell.setAttribute("data-sorter", false);
    cell.colSpan = 1;
    cell.innerHTML = "Requests";
    newRow.appendChild(cell);

    cell = document.createElement('th');
    cell.setAttribute("data-sorter", false);
    cell.colSpan = 3;
    cell.innerHTML = "Executions";
    newRow.appendChild(cell);

    cell = document.createElement('th');
    cell.setAttribute("data-sorter", false);
    cell.colSpan = 7;
    cell.innerHTML = "Response Times (ms)";
    newRow.appendChild(cell);

    cell = document.createElement('th');
    cell.setAttribute("data-sorter", false);
    cell.colSpan = 1;
    cell.innerHTML = "Throughput";
    newRow.appendChild(cell);

    cell = document.createElement('th');
    cell.setAttribute("data-sorter", false);
    cell.colSpan = 2;
    cell.innerHTML = "Network (KB/sec)";
    newRow.appendChild(cell);
}

/*
 * Populates the table identified by id parameter with the specified data and
 * format
 *
 */
function createTable(table, info, formatter, defaultSorts, seriesIndex, headerCreator) {
    var tableRef = table[0];

    // Create header and populate it with data.titles array
    var header = tableRef.createTHead();

    // Call callback is available
    if(headerCreator) {
        headerCreator(header);
    }

    var newRow = header.insertRow(-1);
    for (var index = 0; index < info.titles.length; index++) {
        var cell = document.createElement('th');
        cell.innerHTML = info.titles[index];
        newRow.appendChild(cell);
    }

    var tBody;

    // Create overall body if defined
    if(info.overall){
        tBody = document.createElement('tbody');
        tBody.className = "tablesorter-no-sort";
        tableRef.appendChild(tBody);
        var newRow = tBody.insertRow(-1);
        var data = info.overall.data;
        for(var index=0;index < data.length; index++){
            var cell = newRow.insertCell(-1);
            cell.innerHTML = formatter ? formatter(index, data[index]): data[index];
        }
    }

    // Create regular body
    tBody = document.createElement('tbody');
    tableRef.appendChild(tBody);

    var regexp;
    if(seriesFilter) {
        regexp = new RegExp(seriesFilter, 'i');
    }
    // Populate body with data.items array
    for(var index=0; index < info.items.length; index++){
        var item = info.items[index];
        if((!regexp || filtersOnlySampleSeries && !info.supportsControllersDiscrimination || regexp.test(item.data[seriesIndex]))
                &&
                (!showControllersOnly || !info.supportsControllersDiscrimination || item.isController)){
            if(item.data.length > 0) {
                var newRow = tBody.insertRow(-1);
                for(var col=0; col < item.data.length; col++){
                    var cell = newRow.insertCell(-1);
                    cell.innerHTML = formatter ? formatter(col, item.data[col]) : item.data[col];
                }
            }
        }
    }

    // Add support of columns sort
    table.tablesorter({sortList : defaultSorts});
}

$(document).ready(function() {

    // Customize table sorter default options
    $.extend( $.tablesorter.defaults, {
        theme: 'blue',
        cssInfoBlock: "tablesorter-no-sort",
        widthFixed: true,
        widgets: ['zebra']
    });

    var data = {"OkPercent": 20.241171403962102, "KoPercent": 79.7588285960379};
    var dataset = [
        {
            "label" : "FAIL",
            "data" : data.KoPercent,
            "color" : "#FF6347"
        },
        {
            "label" : "PASS",
            "data" : data.OkPercent,
            "color" : "#9ACD32"
        }];
    $.plot($("#flot-requests-summary"), dataset, {
        series : {
            pie : {
                show : true,
                radius : 1,
                label : {
                    show : true,
                    radius : 3 / 4,
                    formatter : function(label, series) {
                        return '<div style="font-size:8pt;text-align:center;padding:2px;color:white;">'
                            + label
                            + '<br/>'
                            + Math.round10(series.percent, -2)
                            + '%</div>';
                    },
                    background : {
                        opacity : 0.5,
                        color : '#000'
                    }
                }
            }
        },
        legend : {
            show : true
        }
    });

    // Creates APDEX table
    createTable($("#apdexTable"), {"supportsControllersDiscrimination": true, "overall": {"data": [0.16236003445305772, 500, 1500, "Total"], "isController": false}, "titles": ["Apdex", "T (Toleration threshold)", "F (Frustration threshold)", "Label"], "items": [{"data": [0.5344827586206896, 500, 1500, "03 – Browse Products (/api/v1/products)"], "isController": false}, {"data": [0.06382978723404255, 500, 1500, "Stress – Gateway Health"], "isController": false}, {"data": [0.0, 500, 1500, "01a – Register Test User"], "isController": false}, {"data": [0.0, 500, 1500, "Login – Stress User"], "isController": false}, {"data": [0.4, 500, 1500, "05 – Check Inventory (/api/v1/inventory/1)"], "isController": false}, {"data": [0.40963855421686746, 500, 1500, "04 – View Product (/api/v1/products/{id})"], "isController": false}, {"data": [0.4887640449438202, 500, 1500, "02 – Gateway Health Check (/healthz)"], "isController": false}, {"data": [0.0, 500, 1500, "Stress – Create Order"], "isController": false}, {"data": [0.0, 500, 1500, "07 – Get User Profile (/api/v1/users/profile)"], "isController": false}, {"data": [0.11702127659574468, 500, 1500, "Stress – Browse Products"], "isController": false}, {"data": [0.11538461538461539, 500, 1500, "06 – Create Order (/api/v1/orders)"], "isController": false}, {"data": [0.027472527472527472, 500, 1500, "01b – Login and Extract Token"], "isController": false}, {"data": [0.05194805194805195, 500, 1500, "08 – List Orders (/api/v1/orders)"], "isController": false}]}, function(index, item){
        switch(index){
            case 0:
                item = item.toFixed(3);
                break;
            case 1:
            case 2:
                item = formatDuration(item);
                break;
        }
        return item;
    }, [[0, 0]], 3);

    // Create statistics table
    createTable($("#statisticsTable"), {"supportsControllersDiscrimination": true, "overall": {"data": ["Total", 1161, 926, 79.7588285960379, 820.1989664082678, 269, 10313, 287.0, 635.9999999999998, 3645.6999999999844, 10274.76, 7.484672859841281, 4.025552586918262, 2.3307192615090546], "isController": false}, "titles": ["Label", "#Samples", "FAIL", "Error %", "Average", "Min", "Max", "Median", "90th pct", "95th pct", "99th pct", "Transactions/s", "Received", "Sent"], "items": [{"data": ["03 – Browse Products (/api/v1/products)", 87, 40, 45.97701149425287, 297.49425287356337, 272, 580, 290.0, 321.8, 354.19999999999993, 580.0, 0.6299098577272563, 0.7294150820873909, 0.1544017327046302], "isController": false}, {"data": ["Stress – Gateway Health", 94, 88, 93.61702127659575, 290.2978723404255, 271, 441, 281.0, 318.5, 385.75, 441.0, 4.359319204192366, 1.3497422523535687, 1.0344868814636183], "isController": false}, {"data": ["01a – Register Test User", 92, 92, 100.0, 1182.1630434782608, 272, 10003, 331.5, 1076.4000000000015, 10001.35, 10003.0, 0.6228251892170004, 0.3090127395676781, 0.21888264653316544], "isController": false}, {"data": ["Login – Stress User", 124, 123, 99.19354838709677, 2642.548387096774, 270, 10313, 304.5, 10002.0, 10206.25, 10305.25, 3.2393740693330546, 2.775010041406515, 0.8240280245042974], "isController": false}, {"data": ["05 – Check Inventory (/api/v1/inventory/1)", 80, 48, 60.0, 292.1375, 271, 358, 286.5, 316.8, 330.55, 358.0, 0.6013590715015936, 0.21903505829424497, 0.14916523843887183], "isController": false}, {"data": ["04 – View Product (/api/v1/products/{id})", 83, 49, 59.036144578313255, 293.5783132530121, 271, 414, 286.0, 318.0, 360.0, 414.0, 0.6113054686061499, 0.2688990287239919, 0.15814882157981955], "isController": false}, {"data": ["02 – Gateway Health Check (/healthz)", 89, 39, 43.82022471910113, 344.16853932584263, 271, 706, 288.0, 569.0, 586.0, 706.0, 0.6297184663171375, 0.21265159233866118, 0.14943514386236761], "isController": false}, {"data": ["Stress – Create Order", 94, 94, 100.0, 301.92553191489367, 269, 765, 284.0, 319.5, 416.75, 765.0, 4.353867531264474, 1.3491398650995832, 1.8305910577813802], "isController": false}, {"data": ["07 – Get User Profile (/api/v1/users/profile)", 78, 78, 100.0, 302.0384615384616, 272, 864, 286.0, 329.40000000000003, 358.99999999999994, 864.0, 0.6286925612773743, 0.19790686433539945, 0.25517021548840546], "isController": false}, {"data": ["Stress – Browse Products", 94, 82, 87.23404255319149, 296.6489361702128, 270, 549, 283.0, 322.0, 367.75, 549.0, 4.355885078776645, 2.2098007414272476, 1.0677022995829473], "isController": false}, {"data": ["06 – Create Order (/api/v1/orders)", 78, 69, 88.46153846153847, 298.12820512820525, 270, 899, 286.0, 312.0, 352.05, 899.0, 0.6315584920326467, 0.2257802631898562, 0.3340447222357171], "isController": false}, {"data": ["01b – Login and Extract Token", 91, 53, 58.24175824175824, 2823.0879120879117, 273, 10292, 1591.0, 10214.8, 10284.2, 10292.0, 0.5988890936372969, 0.5048820669735699, 0.16630380952694343], "isController": false}, {"data": ["08 – List Orders (/api/v1/orders)", 77, 71, 92.20779220779221, 315.54545454545456, 273, 709, 285.0, 383.8000000000002, 593.2, 709.0, 0.6292803321292558, 0.33540654471976594, 0.2520696784949576], "isController": false}]}, function(index, item){
        switch(index){
            // Errors pct
            case 3:
                item = item.toFixed(2) + '%';
                break;
            // Mean
            case 4:
            // Mean
            case 7:
            // Median
            case 8:
            // Percentile 1
            case 9:
            // Percentile 2
            case 10:
            // Percentile 3
            case 11:
            // Throughput
            case 12:
            // Kbytes/s
            case 13:
            // Sent Kbytes/s
                item = item.toFixed(2);
                break;
        }
        return item;
    }, [[0, 0]], 0, summaryTableHeader);

    // Create error table
    createTable($("#errorsTable"), {"supportsControllersDiscrimination": false, "titles": ["Type of error", "Number of errors", "% in errors", "% in all samples"], "items": [{"data": ["400/Bad Request", 45, 4.859611231101512, 3.875968992248062], "isController": false}, {"data": ["Non HTTP response code: org.apache.http.NoHttpResponseException/Non HTTP response message: adef77e62998148bf97f8564f1fe7123-1693663817.us-east-1.elb.amazonaws.com:8000 failed to respond", 1, 0.1079913606911447, 0.08613264427217916], "isController": false}, {"data": ["401/Unauthorized", 71, 7.667386609071274, 6.11541774332472], "isController": false}, {"data": ["404/Not Found", 5, 0.5399568034557235, 0.4306632213608958], "isController": false}, {"data": ["429/Too Many Requests", 755, 81.53347732181426, 65.03014642549526], "isController": false}, {"data": ["Non HTTP response code: java.net.SocketTimeoutException/Non HTTP response message: Read timed out", 49, 5.291576673866091, 4.220499569336779], "isController": false}]}, function(index, item){
        switch(index){
            case 2:
            case 3:
                item = item.toFixed(2) + '%';
                break;
        }
        return item;
    }, [[1, 1]]);

        // Create top5 errors by sampler
    createTable($("#top5ErrorsBySamplerTable"), {"supportsControllersDiscrimination": false, "overall": {"data": ["Total", 1161, 926, "429/Too Many Requests", 755, "401/Unauthorized", 71, "Non HTTP response code: java.net.SocketTimeoutException/Non HTTP response message: Read timed out", 49, "400/Bad Request", 45, "404/Not Found", 5], "isController": false}, "titles": ["Sample", "#Samples", "#Errors", "Error", "#Errors", "Error", "#Errors", "Error", "#Errors", "Error", "#Errors", "Error", "#Errors"], "items": [{"data": ["03 – Browse Products (/api/v1/products)", 87, 40, "429/Too Many Requests", 40, "", "", "", "", "", "", "", ""], "isController": false}, {"data": ["Stress – Gateway Health", 94, 88, "429/Too Many Requests", 88, "", "", "", "", "", "", "", ""], "isController": false}, {"data": ["01a – Register Test User", 92, 92, "429/Too Many Requests", 44, "400/Bad Request", 42, "Non HTTP response code: java.net.SocketTimeoutException/Non HTTP response message: Read timed out", 6, "", "", "", ""], "isController": false}, {"data": ["Login – Stress User", 124, 123, "429/Too Many Requests", 94, "Non HTTP response code: java.net.SocketTimeoutException/Non HTTP response message: Read timed out", 29, "", "", "", "", "", ""], "isController": false}, {"data": ["05 – Check Inventory (/api/v1/inventory/1)", 80, 48, "429/Too Many Requests", 48, "", "", "", "", "", "", "", ""], "isController": false}, {"data": ["04 – View Product (/api/v1/products/{id})", 83, 49, "429/Too Many Requests", 46, "400/Bad Request", 3, "", "", "", "", "", ""], "isController": false}, {"data": ["02 – Gateway Health Check (/healthz)", 89, 39, "429/Too Many Requests", 39, "", "", "", "", "", "", "", ""], "isController": false}, {"data": ["Stress – Create Order", 94, 94, "429/Too Many Requests", 76, "401/Unauthorized", 18, "", "", "", "", "", ""], "isController": false}, {"data": ["07 – Get User Profile (/api/v1/users/profile)", 78, 78, "429/Too Many Requests", 56, "401/Unauthorized", 17, "404/Not Found", 5, "", "", "", ""], "isController": false}, {"data": ["Stress – Browse Products", 94, 82, "429/Too Many Requests", 82, "", "", "", "", "", "", "", ""], "isController": false}, {"data": ["06 – Create Order (/api/v1/orders)", 78, 69, "429/Too Many Requests", 54, "401/Unauthorized", 15, "", "", "", "", "", ""], "isController": false}, {"data": ["01b – Login and Extract Token", 91, 53, "429/Too Many Requests", 38, "Non HTTP response code: java.net.SocketTimeoutException/Non HTTP response message: Read timed out", 14, "Non HTTP response code: org.apache.http.NoHttpResponseException/Non HTTP response message: adef77e62998148bf97f8564f1fe7123-1693663817.us-east-1.elb.amazonaws.com:8000 failed to respond", 1, "", "", "", ""], "isController": false}, {"data": ["08 – List Orders (/api/v1/orders)", 77, 71, "429/Too Many Requests", 50, "401/Unauthorized", 21, "", "", "", "", "", ""], "isController": false}]}, function(index, item){
        return item;
    }, [[0, 0]], 0);

});
