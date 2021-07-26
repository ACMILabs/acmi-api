// ##################
// Load test using k6
// Install k6: brew install k6
// Run: make load
// ##################

import http from "k6/http";
import { check, sleep } from "k6";
import { Rate } from "k6/metrics";

// A custom metric to track failure rates
var failureRate = new Rate("check_failure_rate");

// Options
export let options = {
    stages: [
        // Linearly ramp up from 1 to 50 VUs during first minute
        { target: 50, duration: "1m" },
        // Hold at 50 VUs for the next 3 minutes and 30 seconds
        { target: 50, duration: "3m30s" },
        // Linearly ramp down from 50 to 0 50 VUs over the last 30 seconds
        { target: 0, duration: "30s" }
        // Total execution time will be ~5 minutes
    ],
    thresholds: {
        // We want the 95th percentile of all HTTP request durations to be less than 1s
        "http_req_duration": ["p(95)<1000"],
        "http_req_duration": ["med<250"],
        // Thresholds based on the custom metric we defined and use to track application failures
        "check_failure_rate": [
            // Global failure rate should be less than 1%
            "rate<0.01",
            // Abort the test early if it climbs over 5%
            { threshold: "rate<=0.05", abortOnFail: true },
        ],
    },
};

// Main function
export default function () {
    let response = http.get("https://api.acmi.net.au");
    // check() returns false if any of the specified conditions fail
    let checkRes = check(response, {
        "status is 200": (r) => r.status === 200,
        "content is present": (r) => r.body.indexOf("Welcome to the ACMI Public API") !== -1,
    });
    // We reverse the check() result since we want to count the failures
    failureRate.add(!checkRes);

    let responseTwo = http.get("https://api.acmi.net.au/works/");
    // check() returns false if any of the specified conditions fail
    let checkResTwo = check(responseTwo, {
        "status is 200": (r) => r.status === 200,
        "content is present": (r) => r.body.indexOf("https://api.acmi.net.au/works/?page=2") !== -1,
    });
    // We reverse the check() result since we want to count the failures
    failureRate.add(!checkResTwo);

    let responseThree = http.get("https://api.acmi.net.au/works/?page=2");
    // check() returns false if any of the specified conditions fail
    let checkResThree = check(responseThree, {
        "status is 200": (r) => r.status === 200,
        "content is present": (r) => r.body.indexOf("https://api.acmi.net.au/works/?page=3") !== -1,
    });
    // We reverse the check() result since we want to count the failures
    failureRate.add(!checkResThree);

    let responseFour = http.get("https://api.acmi.net.au/works/118209/");
    // check() returns false if any of the specified conditions fail
    let checkResFour = check(responseFour, {
        "status is 200": (r) => r.status === 200,
        "content is present": (r) => r.body.indexOf("acmi_id") !== -1,
    });
    // We reverse the check() result since we want to count the failures
    failureRate.add(!checkResFour);

    sleep(Math.random() * 3 + 2); // Random sleep between 2s and 5s
}
