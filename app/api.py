import csv
import datetime
import glob
import json
import os
import re
from pathlib import Path
from urllib.parse import unquote, urljoin

import boto3
import botocore
import elasticsearch
import pytz
import requests
from elasticsearch import Elasticsearch
from flask import Flask, request
from flask_restful import Api, Resource, abort
from furl import furl
from requests.utils import requote_uri

DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'
UPDATE_WORKS = os.getenv('UPDATE_WORKS', 'false').lower() == 'true'
ALL_WORKS = os.getenv('ALL_WORKS', 'false').lower() == 'true'
UPDATE_SEARCH = os.getenv('UPDATE_SEARCH', 'false').lower() == 'true'
ACMI_API_ENDPOINT = os.getenv('ACMI_API_ENDPOINT', 'https://api.acmi.net.au')
XOS_API_ENDPOINT = os.getenv('XOS_API_ENDPOINT', None)
SITE_ROOT = os.path.realpath(os.path.dirname(__file__))
JSON_ROOT = os.path.join(SITE_ROOT, 'json/')
TSV_ROOT = os.path.join(SITE_ROOT, 'tsv/')
TIMEZONE = pytz.timezone('Australia/Melbourne')
YESTERDAY = datetime.datetime.now(TIMEZONE) - datetime.timedelta(days=1)
UPDATE_FROM_DATE = os.getenv('UPDATE_FROM_DATE', YESTERDAY.date())
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_STORAGE_BUCKET_NAME = os.getenv('AWS_STORAGE_BUCKET_NAME', 'acmi-public-api')
ELASTICSEARCH_HOST = os.getenv('ELASTICSEARCH_HOST', 'http://api-search:9200')
ELASTICSEARCH_CLOUD_ID = os.getenv('ELASTICSEARCH_CLOUD_ID')
ELASTICSEARCH_API_KEY = os.getenv('ELASTICSEARCH_API_KEY')
ELASTICSEARCH_API_KEY_ID = os.getenv('ELASTICSEARCH_API_KEY_ID')
INCLUDE_IMAGES = os.getenv('INCLUDE_IMAGES', 'false').lower() == 'true'
INCLUDE_VIDEOS = os.getenv('INCLUDE_VIDEOS', 'false').lower() == 'true'
INCLUDE_EXTERNAL = os.getenv('INCLUDE_EXTERNAL', 'false').lower() == 'true'

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
            'message': 'Welcome to the ACMI Public API.',
            'api': self.routes(),
            'acknowledgement':
                'ACMI acknowledges the Traditional Owners, the Wurundjeri and Boon Wurrung '
                'people of the Kulin Nation, on whose land we meet, share and work. We pay our '
                'respects to Elders past and present and extend our respect to Aboriginal and '
                'Torres Strait Islander people from all nations of this land. Aboriginal and '
                'Torres Strait Islander people should be aware that this website may contain '
                'images, voices or names of deceased persons in photographs, film, audio '
                'recordings or text.',
        }

    def routes(self):
        """
        Return a list of all API routes.
        """
        routes = []
        for route in application.url_map.iter_rules():
            if 'static' not in str(route) and str(route) != '/':
                routes.append(str(route))
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
        try:
            if args.get('page'):
                filename = f'index_page_{int(args.get("page"))}.json'
            json_file_path = os.path.join(JSON_ROOT, 'works', filename)
            with open(json_file_path, 'rb') as json_file:
                return json.load(json_file)
        except (FileNotFoundError, ValueError):
            return {
                abort(404, message='That Works list doesn\'t exist, sorry.')
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
            json_file_path = os.path.join(JSON_ROOT, 'works', f'{int(work_id)}.json')
            with open(json_file_path, 'rb') as json_file:
                return json.load(json_file)
        except (FileNotFoundError, ValueError):
            return abort(404, message='That Work doesn\'t exist, sorry.')


class SearchAPI(Resource):  # pylint: disable=too-few-public-methods
    """
    Search the API using Elasticsearch to return results.
    """
    def get(self):
        """
        Returns search results for the search query.
        """
        try:
            search_query = request.args.get('query')
            if not search_query:
                return abort(
                    400,
                    message='Try adding a search query. e.g. /search/?query=xos',
                    filters=[{
                        'field': 'e.g. ?field=title&query=xos '
                        'Only search the title field for the query `xos`',
                        'size': 'e.g. ?size=2 Search results page size. default: 20, limit: 50',
                        'page': 'e.g. ?page=3 Return this page of the search results',
                        'raw': 'e.g. ?raw=true Return the raw Elasticsearch results',
                    }],
                )
            elastic_search = Search()
            return elastic_search.search(resource='works', args=request.args)
        except elasticsearch.exceptions.NotFoundError:
            return abort(404, message='No results found, sorry.')
        except elasticsearch.exceptions.RequestError as exception:
            message = None
            try:
                message = exception.info['error']['root_cause'][0]['reason']
            except (IndexError, KeyError):
                message = 'Error in your query.'
            return abort(400, message=message)
        except elasticsearch.exceptions.ConnectionTimeout:
            return abort(
                504,
                message='Sorry, your search request timed out. Please try again later.',
            )
        except (
            elasticsearch.exceptions.ConnectionError,
            elasticsearch.exceptions.TransportError,
        ):
            return abort(
                503,
                message='Sorry, search is unavailable at the moment. Please try again later.',
            )


class Search():
    """
    Elasticsearch interface.
    """
    def __init__(self):
        if DEBUG:
            self.elastic_search = Elasticsearch(
                ELASTICSEARCH_HOST,
            )
        else:
            self.elastic_search = Elasticsearch(
                cloud_id=ELASTICSEARCH_CLOUD_ID,
                api_key=ELASTICSEARCH_API_KEY,
            )

    def search(self, resource, args):
        """
        Perform a search for a query string in the index (resource).
        """
        query_body = {}
        query = args.get('query')
        field = args.get('field')
        size = args.get('size', type=int, default=20)
        page = args.get('page', type=int, default=1)
        raw = args.get('raw', type=bool, default=False)
        # Limit search results per page to 50
        size = min(size, 50)
        query_body['size'] = size

        # Elasticsearch uses `from` to specify page of results
        # e.g. Page 1 = from 0
        if page == 1:
            page = 0
        else:
            page = (page - 1) * size
        query_body['from'] = page

        if field:
            query_body['query'] = {
                'match': {
                    field: query
                }
            }
            search_results = self.elastic_search.search(index=resource, body=query_body)
        else:
            search_results = self.elastic_search.search(  # pylint: disable=unexpected-keyword-arg
                index=resource,
                q=query,
                params=query_body,
            )

        if not raw:
            search_results = self.format_results(search_results)

        return search_results

    def format_results(self, search_results):
        """
        Format Elasticsearch results to match the DRF API results from XOS.
        """
        count = search_results['hits']['total']['value']
        search_time = search_results['took']
        max_score = search_results['hits']['max_score']
        results = [result['_source'] for result in search_results['hits']['hits']]
        page = request.args.get('page', type=int)
        next_page = None
        previous_page = None
        endpoint = request.base_url
        args = request.args.copy()
        if page:
            args.pop('page')
        endpoint = furl(endpoint).add(args)
        if page and not page == 1:
            next_page = f'{endpoint}&page={int(page) + 1}'
            previous_page = f'{endpoint}&page={int(page) - 1}'
        else:
            next_page = f'{endpoint}&page=2'
            previous_page = None
        search_results = {
            'count': count,
            'took': search_time,
            'max_score': max_score,
            'next': next_page,
            'previous': previous_page,
            'results': results,
        }
        return search_results

    def index(self, resource, json_data):
        """
        Update the search index for a single record.
        """
        success = False
        # Remove production_dates.date which elasticsearch can't parse
        for date in json_data.get('production_dates'):
            try:
                date.pop('date')
            except KeyError:
                pass
        try:
            self.elastic_search.index(
                index=resource,
                id=json_data.get('id'),
                body=json_data,
            )
            success = True
            return success
        except (
            elasticsearch.exceptions.RequestError,
            elasticsearch.exceptions.ConnectionTimeout,
            elasticsearch.exceptions.ConnectionError,
        ) as exception:
            print(f'ERROR indexing {json_data.get("id")}: {exception}')
            return success

    def update_index(self, resource):
        """
        Update the search index for an API resource. e.g. 'works'
        """
        files_indexed = 0
        objects_to_retry = []
        file_paths = glob.glob(f'{os.path.join(JSON_ROOT, resource)}/[0-9]*.json')
        print('Updating the search index, this will take a while...')
        for file_path in file_paths:
            if 'index' not in file_path:
                with open(file_path, 'rb') as json_file:
                    json_data = json.load(json_file)
                    success = self.index(resource, json_data)
                    if success:
                        files_indexed += 1
                    else:
                        objects_to_retry.append(json_data)
            if files_indexed % 1000 == 0:
                print(f'Indexed {files_indexed} {resource}...')
        for json_data in objects_to_retry:
            print(f'Retrying {json_data.get("id")}...')
            success = self.index(resource, json_data)
            if success:
                files_indexed += 1
        print(f'Finished indexing {files_indexed}/{len(file_paths)} {resource}')
        return files_indexed


class XOSAPI():
    """
    XOS private API interface.
    """
    def __init__(self):
        self.uri = XOS_API_ENDPOINT
        self.params = {
            'page_size': 10,
            'unpublished': False,
            'external': INCLUDE_EXTERNAL,
        }

    def get(self, resource, params=None):
        """
        Returns JSON for this resource.
        """
        endpoint = os.path.join(self.uri, f'{resource}/')
        if not params:
            params = self.params
        retries = 0
        while retries < 3:
            try:
                response = requests.get(url=endpoint, params=params, timeout=30)
                response.raise_for_status()
                return response
            except (
                requests.exceptions.HTTPError,
                requests.exceptions.ConnectionError,
                requests.exceptions.ReadTimeout,
            ) as exception:
                print(f'ERROR: couldn\'t get {endpoint} with exception: {exception}... retrying')
                retries += 1
        return None

    def get_works(self):
        """
        Download and save Works from XOS.
        """
        resource = 'works'
        params = self.params
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
        params = self.params
        params['unpublished'] = True
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
        params = self.params
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

        if not INCLUDE_IMAGES:
            self.remove_assets(work_json, 'images')

        if not INCLUDE_VIDEOS:
            self.remove_assets(work_json, 'videos')
            self.remove_video_links(work_json)

        return work_json

    def remove_assets(self, work_json, asset):
        """
        Remove assets from the API.
        """

        if work_json.get('id'):
            # Individual record
            work_json.pop(asset, None)
            self.remove_all_thumbnails(work_json)
        else:
            # Index page of records
            for work in work_json.get('results'):
                work.pop(asset, None)
                self.remove_all_thumbnails(work)

    def remove_all_thumbnails(self, work_json):
        """
        Remove all thumbnails from a Work JSON, including group works etc.
        Because we don't know whether a related Work has thumbnails from
        a video or an image, let's be overly conservative and remove them
        all when either INCLUDE_IMAGES or INCLUDE_VIDEOS is False.
        """
        work_json.pop('thumbnail', None)

        if work_json.get('group'):
            work_json['group'].pop('thumbnail', None)
        if work_json.get('group_works'):
            for work in work_json.get('group_works'):
                work.pop('thumbnail', None)
        if work_json.get('group_siblings'):
            for work in work_json.get('group_siblings'):
                work.pop('thumbnail', None)

        if work_json.get('part'):
            work_json['part'].pop('thumbnail', None)
        if work_json.get('parts'):
            for work in work_json.get('parts'):
                work.pop('thumbnail', None)
        if work_json.get('part_siblings'):
            for work in work_json.get('part_siblings'):
                work.pop('thumbnail', None)

    def remove_video_links(self, work_json):
        """
        Remove any video_links that aren't from YouTube until we negotiate
        licensing with our partners.
        """
        if work_json.get('video_links'):
            for idx, video_link in enumerate(work_json['video_links']):
                if 'youtu' not in video_link.get('uri'):
                    work_json['video_links'].pop(idx)

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

    def generate_tsv(self, resource):
        """
        Generate a tab separated spreadsheet of data for the selected resource.
        """
        Path(TSV_ROOT).mkdir(parents=True, exist_ok=True)
        tsv_file_path = os.path.join(TSV_ROOT, f'{resource}.tsv')
        with open(tsv_file_path, 'w', encoding='utf-8') as tsv_file:
            writer = csv.writer(tsv_file, delimiter='\t')
            # Header row
            writer.writerow([
                'id',
                'acmi_id',
                'title',
                'title_annotation',
                'slug',
                'creator_credit',
                'credit_line',
                'headline_credit',
                'has_video',
                'record_type',
                'type',
                'is_on_display',
                'last_on_display_place',
                'last_on_display_date',
                'is_context_indigenous',
                'material_description',
                'unpublished',
                'first_production_date',
                'brief_description',
                'constellations_primary',
                'constellations_other',
                'title_for_label',
                'creator_credit_for_label',
                'headline_credit_for_label',
                'description',
                'description_for_label',
                'credit_line_for_label',
                'tap_count',
                'links',
                'creators_primary',
                'creators_other',
                'video_links',
                'media_note',
                'images',
                'videos',
                'holdings',
                'part_of',
                'parts',
                'part_siblings',
                'group',
                'group_works',
                'group_siblings',
                'source',
                'source_identifier',
                'production_places',
                'production_dates',
                'labels',
            ])

            files_written = 0
            file_paths = glob.glob(f'{os.path.join(JSON_ROOT, resource)}/[0-9]*.json')
            print(f'Generating the TSV for {resource}...')
            for file_path in file_paths:
                if 'index' not in file_path:
                    with open(file_path, 'rb') as json_file:
                        json_data = json.load(json_file)
                        writer.writerow([
                            json_data.get('id'),
                            json_data.get('acmi_id'),
                            json_data.get('title'),
                            json_data.get('title_annotation'),
                            json_data.get('slug'),
                            json_data.get('creator_credit'),
                            json_data.get('credit_line'),
                            json_data.get('headline_credit'),
                            self.nested_value(json_data, ['thumbnail', 'has_video'], 'false'),
                            json_data.get('record_type'),
                            json_data.get('type'),
                            json_data.get('is_on_display'),
                            json_data.get('last_on_display_place'),
                            json_data.get('last_on_display_date'),
                            json_data.get('is_context_indigenous'),
                            json_data.get('material_description'),
                            json_data.get('unpublished'),
                            json_data.get('first_production_date'),
                            json_data.get('brief_description'),
                            self.keys_from_dicts('id', json_data.get('constellations_primary')),
                            self.keys_from_dicts('id', json_data.get('constellations_other')),
                            json_data.get('title_for_label'),
                            json_data.get('creator_credit_for_label'),
                            json_data.get('headline_credit_for_label'),
                            json_data.get('description'),
                            self.strings_from_list(json_data.get('description_for_label')),
                            json_data.get('credit_line_for_label'),
                            self.nested_value(json_data, ['stats', 'tap_count'], 0),
                            self.keys_from_dicts('url', json_data.get('links')),
                            self.keys_from_dicts('id', json_data.get('creators_primary')),
                            self.keys_from_dicts('id', json_data.get('creators_other')),
                            self.keys_from_dicts('uri', json_data.get('video_links')),
                            json_data.get('media_note'),
                            self.keys_from_dicts('id', json_data.get('images')),
                            self.keys_from_dicts('id', json_data.get('videos')),
                            self.keys_from_dicts('name', json_data.get('holdings')),
                            self.nested_value(json_data, ['part_of', 'id'], ''),
                            self.keys_from_dicts('id', json_data.get('parts')),
                            self.keys_from_dicts('id', json_data.get('part_siblings')),
                            self.nested_value(json_data, ['group', 'id'], ''),
                            self.keys_from_dicts('id', json_data.get('group_works')),
                            self.keys_from_dicts('id', json_data.get('group_siblings')),
                            self.nested_value(json_data, ['source', 'name'], ''),
                            json_data.get('source_identifier'),
                            self.keys_from_dicts('name', json_data.get('production_places')),
                            self.keys_from_dicts('date', json_data.get('production_dates')),
                            self.strings_from_list(json_data.get('labels')),
                        ])
                        files_written += 1
                if files_written % 1000 == 0:
                    print(f'Added {files_written} {resource}...')
            print(f'Finished generating {files_written}/{len(file_paths)} {resource} TSV')

    def keys_from_dicts(self, your_key, your_list):
        """
        Return a comma separated string of keys from a list of dictionaries.
        """
        try:
            return ','.join([str(list_item[your_key]) for list_item in your_list])
        except (KeyError, TypeError):
            return ''

    def nested_value(self, json_data, nested_list, default_value):
        """
        Return the value of an key from a nested item.
        """
        try:
            return json_data[nested_list[0]][nested_list[1]]
        except (KeyError, TypeError):
            return default_value

    def strings_from_list(self, your_list):
        """
        Return a comma separated list of strings from a list.
        """
        try:
            return ','.join(str(label) for label in your_list)
        except TypeError:
            return ''


api.add_resource(API, '/')
api.add_resource(WorksAPI, '/works/')
api.add_resource(WorkAPI, '/works/<work_id>/')
api.add_resource(SearchAPI, '/search/')

if __name__ == '__main__':
    if UPDATE_WORKS:
        print('========================================')
        print('Starting to update Works API from XOS...')
        xos_private_api = XOSAPI()
        xos_private_api.get_works()
        xos_private_api.delete_works()
        xos_private_api.generate_tsv('works')
        search = Search()
        search.update_index(resource='works')
        print('========================================')
    elif UPDATE_SEARCH:
        print('========================')
        print('Starting search indexing...')
        search = Search()
        search.update_index(resource='works')
        print('========================')
    else:
        application.run(
            host='0.0.0.0',
            port=8081,
            debug=DEBUG,
        )
