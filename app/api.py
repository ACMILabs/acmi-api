import datetime
import json
import os
import re
from pathlib import Path
from urllib.parse import unquote, urljoin

import boto3
import botocore
import pytz
import requests
from flask import Flask, request
from flask_restful import Api, Resource, abort
from furl import furl
from requests.utils import requote_uri

DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'
UPDATE_WORKS = os.getenv('UPDATE_WORKS', 'false').lower() == 'true'
ALL_WORKS = os.getenv('ALL_WORKS', 'false').lower() == 'true'
ACMI_API_ENDPOINT = os.getenv('ACMI_API_ENDPOINT', 'https://api.acmi.net.au')
XOS_API_ENDPOINT = os.getenv('XOS_API_ENDPOINT', None)
SITE_ROOT = os.path.realpath(os.path.dirname(__file__))
JSON_ROOT = os.path.join(SITE_ROOT, 'json/')
TIMEZONE = pytz.timezone('Australia/Melbourne')
YESTERDAY = datetime.datetime.now(TIMEZONE) - datetime.timedelta(days=1)
UPDATE_FROM_DATE = os.getenv('UPDATE_FROM_DATE', YESTERDAY.date())
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_STORAGE_BUCKET_NAME = os.getenv('AWS_STORAGE_BUCKET_NAME', 'acmi-public-api')

application = Flask(__name__)
api = Api(application)
s3_resource = boto3.resource(
    's3',
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
)
destination_bucket = s3_resource.Bucket(AWS_STORAGE_BUCKET_NAME)


class API(Resource):
    """
    API root. Lists all ACMI public APIs.
    """
    def get(self):
        """
        API root list view.
        """
        return {
            'hello': 'Welcome to the ACMI Public API.',
            'api': self.routes(),
        }

    def routes(self):
        """
        Return a list of all API routes.
        """
        routes = []
        for route in application.url_map.iter_rules():
            if 'static' not in str(route) and str(route) != '/':
                routes.append('%s' % route)
        return routes


class WorksAPI(Resource):  # pylint: disable=too-few-public-methods
    """
    Works API. The ACMI Collection.
    """
    def get(self):
        """
        List public Works.
        """
        filename = 'index.json'
        args = request.args
        if args.get('page'):
            filename = f'index_page_{args.get("page")}.json'
        try:
            json_file_path = os.path.join(JSON_ROOT, 'works', filename)
            with open(json_file_path) as json_file:
                return json.load(json_file)
        except FileNotFoundError:
            return {
                abort(404, message='Works list doesn\'t exist, sorry.')
            }


class WorkAPI(Resource):  # pylint: disable=too-few-public-methods
    """
    Get an individual Work JSON.
    """
    def get(self, work_id):
        """
        Returns the requested Work or a 404.
        """
        try:
            json_file_path = os.path.join(JSON_ROOT, 'works', f'{work_id}.json')
            with open(json_file_path) as json_file:
                return json.load(json_file)
        except FileNotFoundError:
            return abort(404, message=f'Work {work_id} doesn\'t exist, sorry.')


class XOSAPI():
    """
    XOS private API interface.
    """
    def __init__(self):
        self.uri = XOS_API_ENDPOINT

    def get(self, resource, params=None):
        """
        Returns JSON for this resource.
        """
        endpoint = os.path.join(self.uri, f'{resource}/')
        if not params:
            params = {
                'page_size': 10,
            }
        try:
            response = requests.get(url=endpoint, params=params, timeout=15)
            response.raise_for_status()
            return response
        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as exception:
            print(f'ERROR: couldn\'t get {endpoint} with exception: {exception}')
            return None

    def get_works(self):
        """
        Download and save Works from XOS.
        """
        resource = 'works'
        params = {
            'page_size': 10,
            'unpublished': False,
        }
        if ALL_WORKS:
            print('Downloading all XOS Works... this will take a while')
        else:
            print(f'Updating XOS Works since {UPDATE_FROM_DATE}...')
            params['date_modified__gte'] = UPDATE_FROM_DATE
        params['page'] = 1
        works_saved = 0
        while True:
            works_json = self.get(resource, params).json()
            works_json = self.update_assets(works_json)
            self.save_works_list(resource, works_json, params.get('page'))
            works_saved += self.save_works(resource, works_json)
            if not works_json.get('next'):
                break
            params['page'] = furl(works_json.get('next')).args.get('page')
        print(f'Finished downloading {works_saved} {resource}.')

        if not ALL_WORKS:
            # TODO: Delete old works lists if the collection shrinks # pylint: disable=fixme
            self.save_works_lists(resource)

    def save_works_list(self, resource, works_json, page=None):
        """
        Save a list of Works page from XOS.
        """
        endpoint = urljoin(ACMI_API_ENDPOINT, f'/{resource}/')
        if page and not page == 1:
            if works_json.get('next'):
                works_json['next'] = f'{endpoint}?page={int(page) + 1}'
            works_json['previous'] = f'{endpoint}?page={int(page) - 1}'
            page = f'_page_{page}'
        else:
            if works_json.get('next'):
                works_json['next'] = f'{endpoint}?page=2'
            works_json['previous'] = None
            page = ''
        json_directory = os.path.join(JSON_ROOT, resource)
        Path(json_directory).mkdir(parents=True, exist_ok=True)
        json_file_path = os.path.join(json_directory, f'index{page}.json')
        with open(json_file_path, 'w', encoding='utf-8') as json_file:
            json.dump(works_json, json_file, ensure_ascii=False, indent=None)
            print(f'Saved {resource} index to {json_file_path}')

    def save_works(self, resource, works_json):
        """
        Download and save these individual Works from XOS.
        """
        works_saved = 0
        for result in works_json.get('results'):
            work_id = str(result.get('id'))
            work_resource = os.path.join(f'{resource}/', work_id)
            work_json = self.get(resource=work_resource).json()
            work_json = self.update_assets(work_json)
            json_directory = os.path.join(JSON_ROOT, resource)
            Path(json_directory).mkdir(parents=True, exist_ok=True)
            json_file_path = os.path.join(json_directory, f'{work_id}.json')
            with open(json_file_path, 'w', encoding='utf-8') as json_file:
                json.dump(work_json, json_file, ensure_ascii=False, indent=None)
            works_saved += 1
        return works_saved

    def delete_works(self):
        """
        Delete unpublished Works from the file system.
        """
        resource = 'works'
        params = {
            'page_size': 10,
            'unpublished': True,
        }
        if ALL_WORKS:
            print('Deleting all unpublished XOS Works...')
        else:
            print(f'Deleting unpublished XOS Works since {UPDATE_FROM_DATE}...')
            params['date_modified__gte'] = UPDATE_FROM_DATE
        work_ids_to_delete = []
        works_deleted = 0
        params['page'] = 1
        while True:
            works_json = self.get(resource, params).json()
            for result in works_json['results']:
                if result.get('unpublished'):
                    work_ids_to_delete.append(str(result.get('id')))
                    self.update_assets(result, delete=True)
            if not works_json.get('next'):
                break
            params['page'] = furl(works_json.get('next')).args.get('page')

        for work_id in work_ids_to_delete:
            json_file_path = os.path.join(JSON_ROOT, resource, f'{work_id}.json')
            try:
                os.remove(json_file_path)
                works_deleted += 1
            except OSError as exception:
                print(
                    f'Error: couldn\'t delete {exception.filename} '
                    f'with error: {exception.strerror}'
                )

        print(f'Finished deleting {works_deleted}/{len(work_ids_to_delete)} {resource}.')

    def save_works_lists(self, resource):
        """
        Download and save all Works list pages from XOS.
        """
        print(f'Saving all {resource} list index files...')
        params = {
            'page_size': 10,
            'unpublished': False,
        }
        params['page'] = 1
        while True:
            works_json = self.get(resource, params).json()
            works_json = self.update_assets(works_json)
            self.save_works_list(resource, works_json, params.get('page'))
            if not works_json.get('next'):
                break
            params['page'] = furl(works_json.get('next')).args.get('page')

    def update_assets(self, work_json, delete=False):
        """
        Upload images/videos to a public bucket, and update the links in the json.
        """
        # Upload assets to ACMI public API bucket
        asset_regex = r'(https:\/\/[a-z0-9\-]+\.s3\.amazonaws\.com.*?)\?'
        assets = re.findall(asset_regex, str(work_json))
        for asset in assets:
            source = re.findall(r'https:\/\/(.*?)\.s3', asset)[0]
            key = re.findall(r'\.com/(.*?)$', asset)[0]
            destination_key = re.findall(r'\.com\/media\/(.*?)$', asset)[0]

            # Unquote URL quoted filenames
            key = unquote(key)
            destination_key = unquote(destination_key)

            if 'collection/' in destination_key:
                destination_key = destination_key.replace('collection/', '')
            else:
                destination_key = f'video/{destination_key}'

            if delete:
                if self.asset_exists(destination_key):
                    print(f'Deleting {AWS_STORAGE_BUCKET_NAME}/{destination_key}...')
                    s3_resource.Object(AWS_STORAGE_BUCKET_NAME, destination_key).delete()
            else:
                if self.asset_exists(destination_key):
                    print(f'{destination_key} exists...')
                else:
                    copy_source = {
                        'Bucket': source,
                        'Key': key
                    }
                    print(f'Copying {copy_source} to {AWS_STORAGE_BUCKET_NAME}/{destination_key}')
                    destination_bucket.copy(
                        copy_source,
                        destination_key,
                        ExtraArgs={'ACL': 'public-read'},
                    )
                # Replace image/video links with public API bucket links
                destination_key = requote_uri(destination_key)
                work_json_string = re.sub(
                    rf'"({asset})\?.*?"',
                    f'"https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/{destination_key}"',
                    json.dumps(work_json),
                )
                work_json = json.loads(work_json_string)

        return work_json

    def asset_exists(self, key):
        """
        Check the destination bucket to see if the asset exists.
        """
        try:
            s3_resource.Object(AWS_STORAGE_BUCKET_NAME, key).load()
        except botocore.exceptions.ClientError as exception:
            if exception.response['Error']['Code'] == '404':
                return False
            print(f'ERROR accessing asset: {key}, {exception}')
            return False
        return True


api.add_resource(API, '/')
api.add_resource(WorksAPI, '/works/')
api.add_resource(WorkAPI, '/works/<work_id>/')

if __name__ == '__main__':
    if DEBUG and UPDATE_WORKS:
        print('===============================================')
        print('Starting thread to update Works API from XOS...')
        xos_private_api = XOSAPI()
        xos_private_api.get_works()
        xos_private_api.delete_works()
        print('===============================================')
    else:
        application.run(
            host='0.0.0.0',
            port=8081,
            debug=DEBUG,
        )
