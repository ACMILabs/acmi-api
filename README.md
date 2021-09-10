# ACMI collection API

A public API for ACMI's collection data - [api.acmi.net.au](https://api.acmi.net.au)

![ACMI API CI](https://github.com/ACMILabs/acmi-api/workflows/ACMI%20API%20CI/badge.svg)

Documentation can be found here: https://kb.acmi.net.au/display/OPS/XOS+Public+API

## Archive

This repository contains a full archive of ACMI collection `JSON` data files.

Find them at: `/app/json/`

Image and video assets can be found in the public S3 bucket: `s3://acmi-public-api`

## Licences

* Software: [Mozilla Public License Version 2.0](https://www.mozilla.org/en-US/MPL/2.0/)
* Collection metadata in `/app/json/`: [Creative Commons CC0](https://creativecommons.org/share-your-work/public-domain/cc0/)
* Images: Licence is found in the `credit_line` field within the `images` field on the Works API
* Videos: Videos are available only via their YouTube link in the `video_links` field. Please ensure that if you present them through another application you provide the attribution from the `credit_line` field

## API server

This API server exposes the following routes:

* `/` - a list of API routes
* `/search/` - a search engine for the ACMI API
* `/works/` - a list of all public ACMI Work records
* `/works/<id>/` - an individual ACMI Work record

## Updating

This repository includes a cron job to update itself automatically each night. The job runs the updater script `/scripts/update-api.sh`, which runs:

* `python -u -m app.api` - pulls changes from the XOS API
* `git add app/json` and `git commit` - adds changes in a commit
* `git push` - merges changes back into the `main` branch and pushes
* This push to `main` causes a GitHub Action to deploy onto our Staging API infrastructure
* After updating from XOS, the search index is updated

## Search

Search is handled by Elasticsearch.

### Production

In production we're using [Elastic Cloud](https://www.elastic.co/cloud/) for our search.

The search index is updated every time the API update runs.

To update it manually, run:

* Add Elastic Cloud credentials `ELASTICSEARCH_CLOUD_ID` and `ELASTICSEARCH_API_KEY` to your `config.env`
* Start only the API container: `cd development` and `docker-compose -f docker-compose-base.yml up --build`
* Connect to a Python shell: `docker exec -it api python`
* Inside that shell run: `from app.api import Search` and `Search().update_index('works')`
* The production search will now be indexed: http://localhost:8081/search/

### Development

To update the development search index locally:

* Add `UPDATE_SEARCH=true` and `DEBUG=true` to your `config.env`
* Run `cd development` and `docker-compose up --build`
* The search will now be indexed at: http://localhost:8081/search/
* You can see the Elasticsearch files: `/elasticsearch_data/`

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
