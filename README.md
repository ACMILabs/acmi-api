# ACMI collection API

A public API for ACMI's collection data - [api.acmi.net.au](https://api.acmi.net.au)

![ACMI API CI](https://github.com/ACMILabs/acmi-api/workflows/ACMI%20API%20CI/badge.svg)

Public documentation: https://www.acmi.net.au/api

Internal documentation: https://kb.acmi.net.au/display/OPS/XOS+Public+API

## Archive

### JSON metadata

This repository contains a full archive of ACMI collection `JSON` data files.

Find them at: `/app/json/`

### TSV spreadsheet

This repository contains a full archive of ACMI collection metadata in TSV (tab separated values) format.

Find them at: `/app/tsv/`

The [2017 collections TSV](https://github.com/ACMILabs/collection/blob/master/src/collections_data.tsv) can be found in the deprecated repository: [github.com/ACMILabs/collection](https://github.com/ACMILabs/collection)

### Assets

Image and video assets will be found in the public S3 bucket when we have arranged suitable licenses with our partners: `s3://acmi-public-api`

### TMDB and IGDB images

Works that were imported from [TMDB](https://www.themoviedb.org) or [IGDB](https://www.igdb.com) have their source saved in the field `source` and their originating ID saved in the field `source_identifier`. This allows you to use the [TMDB API](https://developers.themoviedb.org) or [IGDB API](https://www.igdb.com/api) to retrieve images for these Works.

## Licences

* Software: [Mozilla Public License Version 2.0](https://www.mozilla.org/en-US/MPL/2.0/)
* Collection metadata in `/app/json/`: [Creative Commons CC0](https://creativecommons.org/share-your-work/public-domain/cc0/)
* Images: coming soon...
* Videos: coming soon...

## API server

This API server exposes the following routes:

* `/` - a list of API routes
* `/constellations/` - a list of ACMI Constellation records
* `/constellations/<id>` - an individual ACMI Constellation record
* `/creators/` - a list of ACMI Creator records
* `/creators/<id>` - an individual ACMI Creator record
* `/search/` - a search engine for the ACMI API
* `/works/` - a list of all public ACMI Work records
* `/works/<id>/` - an individual ACMI Work record

## Linked Art

Individual Work and Creator records are also available as [Linked Art](https://linked.art) JSON-LD, a CIDOC-CRM based linked data profile used by art museums to publish interoperable collection data.

Request the Linked Art representation of a record either by content negotiation:

```bash
curl -H 'Accept: application/ld+json;profile="https://linked.art/ns/v1/linked-art.json"' https://api.acmi.net.au/works/116936/
```

or with a query string argument:

```bash
curl https://api.acmi.net.au/works/116936/?format=linked-art
curl https://api.acmi.net.au/creators/34373/?format=linked-art
```

How ACMI records map to Linked Art:

* Works (films, TV shows, videogames etc.) become conceptual `VisualItem` records; Works of type `Object` become physical `HumanMadeObject` records
* Work titles, ACMI identifiers, types, descriptions and production details (dates, places, creators and their roles) are expressed using [Getty AAT](https://www.getty.edu/research/tools/vocabularies/aat/) classifications
* Creators become `Person` or `Group` records, with Wikidata links expressed via `equivalent`

The transformation lives in `app/linked_art.py`. Production place URIs (e.g. `/places/<id>/`) and constellation `Set` records don't dereference yet - they're planned for a future phase, along with an [Activity Streams](https://linked.art/api/1.0/hal/) change feed for harvesters.

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

* Add `UPDATE_ITEMS=true` and `DEBUG=true` to your `config.env`
* Run `cd development` and `docker-compose up --build`
* Works appear in `/app/json/`

To update **ALL** Works from XOS:

* Add `ALL_WORKS=true` and `UPDATE_ITEMS=true` and `DEBUG=true` to your `config.env`
* Run `cd development` and `docker-compose up --build`

To update **ALL** Creators from XOS:

* Add `ALL_CREATORS=true` and `UPDATE_ITEMS=true` and `DEBUG=true` to your `config.env`
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
