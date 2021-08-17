# ACMI collection API

A public API for ACMI's collection data - [api.acmi.net.au](https://api.acmi.net.au)

![ACMI API CI](https://github.com/ACMILabs/acmi-api/workflows/ACMI%20API%20CI/badge.svg)

Documentation can be found here: https://kb.acmi.net.au/display/OPS/XOS+Public+API

## Archive

This repository contains a full archive of ACMI collection `JSON` data files.

Find them at: `/app/json/`

Image and video assets can be found in the public S3 bucket: `s3://acmi-public-api`

## API server

This API server exposes the following routes:

* `/` - a list of API routes
* `/works/` - a list of all public ACMI Work records
* `/works/<id>/` - an individual ACMI Work record

## Updating

This repository includes a cron job to update itself automatically each night. The job runs the updater script `/scripts/update-api.sh`, which runs:

* `git checkout update` - makes changes on the `update` branch
* `python -u -m app.api` - pulls changes from the XOS API
* `git add app/json` and `git commit` - adds changes in a commit
* `git merge` and `git push` - merges changes back into the `main` branch and pushes
* This push to `main` causes a GitHub Action to deploy onto our Staging API infrastructure

## Development

To run the Flask development server:

* Copy `config.tmpl.env` to `config.env`
* Add `DEBUG=true` to your `config.env`
* Run `cd development` and `docker-compose up --build`
* Visit: http://localhost:8081

To update Works `json` files modified in the last day from XOS:

* Add `UPDATE_WORKS=true` and `DEBUG=true` to your `config.env`
* Run `cd development` and `docker-compose up --build`
* Works appear in `/app/json/`

To update **ALL** Works from XOS:

* Add `ALL_WORKS=true` and `UPDATE_WORKS=true` and `DEBUG=true` to your `config.env`
* Run `cd development` and `docker-compose up --build`

To run the gunicorn server:

* Set `DEBUG=false` in your `config.env`
* Run `cd development` and `docker-compose up --build`
* Visit: http://localhost:8081

## Tests

To run linting and tests:

* Run `cd development` and `docker-compose up --build`
* In another terminal tab run `docker exec -it api make linttest`

To run a speed test against `ACMI_API_ENDPOINT` (defaults to https://api.acmi.net.au):

* Run `cd development` and `docker-compose up --build`
* In another terminal tab run `docker exec -it api make speed`

To run a load test against https://api.acmi.net.au `/`, `/works/` and `/works/<ID>`:

* Modify the `load_test.js` file if needed
* Run `cd development` and `docker-compose up --build`
* In another terminal tab run `docker exec -it api make load`

## Architecture

**Flask app**

* Gets public XOS API `json` files
* Replaces signed S3 asset links with public S3 bucket links
* Puts assets into the public S3 bucket `s3://acmi-public-api`
* Updates from XOS nightly, auto-deploying to the Staging API
