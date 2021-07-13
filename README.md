# ACMI collection API

A public API for ACMI's collection data.

![ACMI API CI](https://github.com/ACMILabs/acmi-api/workflows/ACMI%20API%20CI/badge.svg)

## Development

To run the Flask development server:

* Copy `config.tmpl.env` to `config.env`
* Add `DEBUG=true` to your `config.env`
* Run `cd development` and `docker-compose up --build`
* Visit: http://localhost:8081

To update Works `json` files modified in the last day from XOS:

* Add `DOWNLOAD_WORKS=true` and `DEBUG=true` to your `config.env`
* Run `cd development` and `docker-compose up --build`
* Works appear in `/app/json/`

To update **ALL** Works from XOS:

* Add `ALL_WORKS=true` and `DOWNLOAD_WORKS=true` and `DEBUG=true` to your `config.env`
* Run `cd development` and `docker-compose up --build`

To run the gunicorn server:

* Set `DEBUG=false` in your `config.env`
* Run `cd development` and `docker-compose up --build`
* Visit: http://localhost:8081

## Tests

To run linting and tests:

* Run `cd development` and `docker-compose up --build`
* In another terminal tab run `docker exec -it api make linttest`

## TODO

**Spike**: deploy this setup and see how it performs.

- [x] Create Flask app
- [x] Add an XOS API interface to save `json` data
- [x] Setup a production server (gunicorn/nginx)
- [ ] Deploy it for evaluation

## Architecture

**Flask app**

* Gets public XOS API `json` files
* Replaces S3 asset links with CloudFront links (or we do this on the XOS side)
* Puts those files into a public S3 bucket
* Gets `html` API documentation files from the ACMI website
* Puts those files into the S3 public bucket
* Updates nightly

**API server**

* Use [CloudFront](https://aws.amazon.com/cloudfront/) to serve the `json`, `html`, and `images`
* Use [Cloudflare](https://www.cloudflare.com/en-au/) to cache and limit attacks

## Archive

Keep a full archive of all of the above, including instructions to run a simple Python or Flask server to serve the `json` files locally for development.
