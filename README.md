# ACMI collection API

A public API for ACMI's collection data.

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
