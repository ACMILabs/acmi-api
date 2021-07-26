import http from "k6/http";
import { check, sleep } from "k6";
import { Rate } from "k6/metrics";

var failureRate = new Rate("check_failure_rate");

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
        // We want the median HTTP request durations to be less than 250ms
        "http_req_duration": ["med<250"],
        // Thresholds to track application failures
        "check_failure_rate": [
            // Global failure rate should be less than 1%
            "rate<0.01",
            // Abort the test early if it climbs over 5%
            { threshold: "rate<=0.05", abortOnFail: true },
        ],
    },
};

export default function () {
    let response = http.get("https://api.acmi.net.au");
    let checkRes = check(response, {
        "status is 200": (r) => r.status === 200,
        "content is present": (r) => r.body.indexOf("Welcome to the ACMI Public API") !== -1,
    });
    failureRate.add(!checkRes);

    let responseTwo = http.get("https://api.acmi.net.au/works/");
    let checkResTwo = check(responseTwo, {
        "status is 200": (r) => r.status === 200,
        "content is present": (r) => r.body.indexOf("https://api.acmi.net.au/works/?page=2") !== -1,
    });
    failureRate.add(!checkResTwo);

    let responseThree = http.get("https://api.acmi.net.au/works/?page=2");
    let checkResThree = check(responseThree, {
        "status is 200": (r) => r.status === 200,
        "content is present": (r) => r.body.indexOf("https://api.acmi.net.au/works/?page=3") !== -1,
    });
    failureRate.add(!checkResThree);

    let responseFour = http.get("https://api.acmi.net.au/works/118209/");
    let checkResFour = check(responseFour, {
        "status is 200": (r) => r.status === 200,
        "content is present": (r) => r.body.indexOf("acmi_id") !== -1,
    });
    failureRate.add(!checkResFour);

    sleep(Math.random() * 3 + 2); // Random sleep between 2s and 5s
}
