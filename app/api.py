# pylint: disable=too-many-lines

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
from elastic_transport import ObjectApiResponse
from elasticsearch import Elasticsearch
from flask import Flask, request
from flask_restful import Api, Resource, abort
from flask_sqlalchemy import SQLAlchemy
from furl import furl
from requests.utils import requote_uri

DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'
UPDATE_ITEMS = os.getenv('UPDATE_ITEMS', 'false').lower() == 'true'
ALL_WORKS = os.getenv('ALL_WORKS', 'false').lower() == 'true'
ALL_CREATORS = os.getenv('ALL_CREATORS', 'false').lower() == 'true'
UPDATE_SEARCH = os.getenv('UPDATE_SEARCH', 'false').lower() == 'true'
ACMI_API_ENDPOINT = os.getenv('ACMI_API_ENDPOINT', 'https://api.acmi.net.au')
XOS_API_ENDPOINT = os.getenv('XOS_API_ENDPOINT', None)
XOS_RETRIES = int(os.getenv('XOS_RETRIES', '3'))
XOS_TIMEOUT = int(os.getenv('XOS_TIMEOUT', '60'))
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
SUGGESTIONS_DATABASE = os.getenv('SUGGESTIONS_DATABASE')
SUGGESTIONS_DATABASE_PATH = os.path.join(SITE_ROOT, 'instance', SUGGESTIONS_DATABASE)
SUGGESTIONS_API_KEYS = json.loads(os.getenv('SUGGESTIONS_API_KEYS', '[]'))

application = Flask(__name__)
api = Api(application)

if SUGGESTIONS_DATABASE == ':memory:':
    application.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{SUGGESTIONS_DATABASE}'
else:
    application.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{SUGGESTIONS_DATABASE_PATH}.db'
print(f"Database URI: {application.config['SQLALCHEMY_DATABASE_URI']}")
database = SQLAlchemy(application)

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
                'ACMI would like to acknowledge the Traditional Custodians of the lands '
                'and waterways of greater Melbourne, the people of the Kulin Nation, and '
                'recognise that ACMI is located on the lands of the Wurundjeri people. '
                'First Nations (Aboriginal and Torres Strait Islander) people should be aware '
                'that this website may contain images, voices, or names of deceased persons in '
                'photographs, film, audio recordings or text.',
        }

    def routes(self):
        """
        Return a list of all API routes.
        """
        routes = []
        for route in application.url_map.iter_rules():
            if 'static' not in str(route) and str(route) != '/':
                routes.append(str(route))
        routes.sort()
        return routes


class AudioListAPI(Resource):  # pylint: disable=too-few-public-methods
    """
    Audio API. The ACMI Collection.
    """
    def get(self):
        """
        List all Audio.
        """
        filename = 'index.json'
        args = request.args
        try:
            if args.get('labels'):
                return self.get_labels(args.get('labels'))
            if args.get('page'):
                filename = f'index_page_{int(args.get("page"))}.json'
            json_file_path = os.path.join(JSON_ROOT, 'audio', filename)
            with open(json_file_path, 'rb') as json_file:
                return json.load(json_file)
        except (FileNotFoundError, ValueError):
            return {
                abort(404, message='That Audio list doesn\'t exist, sorry.')
            }

    def get_labels(self, labels):
        """
        Returns a JSON list of Audio records from Label IDs.
        """
        labels_json = {
            'count': 0,
            'next': None,
            'previous': None,
            'results': [],
        }
        lookup_file_path = os.path.join(
            JSON_ROOT,
            'audio',
            'audio_labels.json',
        )
        with open(lookup_file_path, 'rb') as lookup_json_file:
            lookup_table = json.load(lookup_json_file)
            for label_id in labels.split(','):
                try:
                    audio_id = lookup_table[label_id]
                    json_file_path = os.path.join(
                        JSON_ROOT,
                        'audio',
                        f'{audio_id}.json',
                    )
                    with open(json_file_path, 'rb') as json_file:
                        labels_json['results'].append(json.load(json_file))
                        labels_json['count'] += 1
                except (FileNotFoundError, KeyError, ValueError):
                    pass
        return labels_json


class AudioAPI(Resource):  # pylint: disable=too-few-public-methods
    """
    Get an individual Audio JSON.
    """
    def get(self, audio_id):
        """
        Returns the requested Audio or a 404.
        """
        try:
            json_file_path = os.path.join(
                JSON_ROOT,
                'audio',
                f'{int(audio_id)}.json',
            )
            with open(json_file_path, 'rb') as json_file:
                return json.load(json_file)
        except (FileNotFoundError, ValueError):
            return abort(404, message='That Audio doesn\'t exist, sorry.')


class ConstellationsAPI(Resource):  # pylint: disable=too-few-public-methods
    """
    Constellations API. The ACMI Collection.
    """
    def get(self):
        """
        List public Constellations.
        """
        filename = 'index.json'
        args = request.args
        try:
            if args.get('page'):
                filename = f'index_page_{int(args.get("page"))}.json'
            json_file_path = os.path.join(JSON_ROOT, 'constellations', filename)
            with open(json_file_path, 'rb') as json_file:
                return json.load(json_file)
        except (FileNotFoundError, ValueError):
            return {
                abort(404, message='That Constellations list doesn\'t exist, sorry.')
            }


class ConstellationAPI(Resource):  # pylint: disable=too-few-public-methods
    """
    Get an individual Constellation JSON.
    """
    def get(self, constellation_id):
        """
        Returns the requested Constellation or a 404.
        """
        try:
            json_file_path = os.path.join(
                JSON_ROOT,
                'constellations',
                f'{int(constellation_id)}.json',
            )
            with open(json_file_path, 'rb') as json_file:
                return json.load(json_file)
        except (FileNotFoundError, ValueError):
            return abort(404, message='That Constellation doesn\'t exist, sorry.')


class CreatorsAPI(Resource):  # pylint: disable=too-few-public-methods
    """
    Creators API. The ACMI Collection.
    """
    def get(self):
        """
        List public Creators.
        """
        filename = 'index.json'
        args = request.args
        try:
            if args.get('page'):
                filename = f'index_page_{int(args.get("page"))}.json'
            json_file_path = os.path.join(JSON_ROOT, 'creators', filename)
            with open(json_file_path, 'rb') as json_file:
                return json.load(json_file)
        except (FileNotFoundError, ValueError):
            return {
                abort(404, message='That Creators list doesn\'t exist, sorry.')
            }


class CreatorAPI(Resource):  # pylint: disable=too-few-public-methods
    """
    Get an individual Creator JSON.
    """
    def get(self, creator_id):
        """
        Returns the requested Creator or a 404.
        """
        try:
            json_file_path = os.path.join(
                JSON_ROOT,
                'creators',
                f'{int(creator_id)}.json',
            )
            with open(json_file_path, 'rb') as json_file:
                return json.load(json_file)
        except (FileNotFoundError, ValueError):
            return abort(404, message='That Creator doesn\'t exist, sorry.')


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
                        'resource': 'e.g. ?resource=works Returns only Work search results',
                    }],
                )
            elastic_search = Search()
            resource = request.args.get('resource', 'works')
            return elastic_search.search(resource=resource, args=request.args)
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
            search_results = self.elastic_search.search(  # pylint: disable=unexpected-keyword-arg
                index=resource,
                body=query_body,
            )
        else:
            search_results = self.elastic_search.search(  # pylint: disable=unexpected-keyword-arg
                index=resource,
                q=query,
                params=query_body,
            )

        if raw:
            if isinstance(search_results, ObjectApiResponse):
                search_results = search_results.body
        else:
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
        for date in json_data.get('production_dates', []):
            try:
                date.pop('date')
            except KeyError:
                pass
        try:
            self.elastic_search.index(  # pylint: disable=unexpected-keyword-arg,missing-kwoa
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

    def delete(self, resource, item_id):
        """
        Delete the search index for a single record.
        """
        success = False
        try:
            self.elastic_search.delete(
                index=resource,
                id=item_id,
            )
            success = True
            return success
        except (
            elasticsearch.exceptions.RequestError,
            elasticsearch.exceptions.ConnectionTimeout,
            elasticsearch.exceptions.ConnectionError,
            elasticsearch.exceptions.NotFoundError,
        ) as exception:
            print(f'ERROR deleting the index for {item_id}: {exception}')
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


class XOSAPI():  # pylint: disable=too-many-public-methods
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
            params = self.params.copy()
        retries = 0
        while retries < XOS_RETRIES:
            try:
                response = requests.get(url=endpoint, params=params, timeout=XOS_TIMEOUT)
                response.raise_for_status()
                return response
            except (
                requests.exceptions.HTTPError,
                requests.exceptions.ConnectionError,
                requests.exceptions.ReadTimeout,
            ) as exception:
                print(
                    f'ERROR: couldn\'t get {endpoint} with params: {params}, '
                    f'exception: {exception}... retrying',
                )
                retries += 1
                if retries == XOS_RETRIES:
                    raise exception
        return None

    def get_works(self):
        """
        Download and save Works from XOS.
        """
        resource = 'works'
        params = self.params.copy()
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
            self.remove_external_works(works_json)
            self.save_list(resource, works_json, params.get('page'))
            works_saved += self.save_items(resource, works_json)
            if not works_json.get('next'):
                break
            params['page'] = furl(works_json.get('next')).args.get('page')
        print(f'Finished downloading {works_saved} {resource}.')

        if not ALL_WORKS:
            # TODO: Delete old works lists if the collection shrinks # pylint: disable=fixme
            self.save_items_lists(resource)

    def get_audio(self):
        """
        Download and save Audio from XOS.
        """
        resource = 'audio'
        params = self.params.copy()
        print('Downloading all XOS Audio...')
        params['page'] = 1
        audio_saved = 0
        audio_labels = {}
        while True:
            audio_json = self.get(resource, params).json()
            audio_json = self.update_assets(audio_json)
            self.save_list(resource, audio_json, params.get('page'))
            self.add_audio_labels(audio_json, audio_labels)
            audio_saved += self.save_items(resource, audio_json)
            if not audio_json.get('next'):
                break
            params['page'] = furl(audio_json.get('next')).args.get('page')
        print(f'Finished downloading {audio_saved} {resource}.')

        json_directory = os.path.join(JSON_ROOT, resource)
        audio_labels_file_path = os.path.join(json_directory, 'audio_labels.json')
        with open(audio_labels_file_path, 'w', encoding='utf-8') as json_file:
            json.dump(audio_labels, json_file, ensure_ascii=False, indent=None)
            print(f'Saved {resource} labels lookup to {audio_labels_file_path}')

    def get_constellations(self):
        """
        Download and save Constellations from XOS.
        """
        resource = 'constellations'
        params = self.params.copy()
        print('Downloading all XOS Constellations...')
        params['page'] = 1
        constellations_saved = 0
        while True:
            constellations_json = self.get(resource, params).json()
            constellations_json = self.update_assets(constellations_json)
            self.save_list(resource, constellations_json, params.get('page'))
            constellations_saved += self.save_items(resource, constellations_json)
            if not constellations_json.get('next'):
                break
            params['page'] = furl(constellations_json.get('next')).args.get('page')
        print(f'Finished downloading {constellations_saved} {resource}.')

    def get_creators(self):
        """
        Download and save Creators from XOS.
        """
        resource = 'creators'
        params = self.params.copy()
        if ALL_CREATORS:
            print('Downloading all XOS Creators... this will take a while')
        else:
            print(f'Updating XOS Creators since {UPDATE_FROM_DATE}...')
            params['date_modified__gte'] = UPDATE_FROM_DATE
        params['page'] = 1
        creators_saved = 0
        while True:
            creators_json = self.get(resource, params).json()
            creators_json = self.update_assets(creators_json)
            self.save_list(resource, creators_json, params.get('page'))
            creators_saved += self.save_items(resource, creators_json)
            if not creators_json.get('next'):
                break
            params['page'] = furl(creators_json.get('next')).args.get('page')
        print(f'Finished downloading {creators_saved} {resource}.')

        if not ALL_CREATORS:
            # TODO: Delete old creators lists if the collection shrinks # pylint: disable=fixme
            self.save_items_lists(resource)

    def add_audio_labels(self, audio_json, audio_labels):
        """
        Adds a Label ID key to an audio_labels dict with the value set to the Audio ID.
        """
        for audio in audio_json.get('results', []):
            try:
                audio_labels[audio['work']['labels'][0]] = audio['id']
            except TypeError:
                pass

    def save_list(self, resource, works_json, page=None):
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

    def save_items(self, resource, items_json):
        """
        Download and save items from XOS.
        """
        items_saved = 0
        for result in items_json.get('results'):
            item_id = str(result.get('id'))
            item_resource = os.path.join(f'{resource}/', item_id)
            item_json = self.get(resource=item_resource).json()
            item_json = self.update_assets(item_json)
            self.remove_external_works(item_json)
            json_directory = os.path.join(JSON_ROOT, resource)
            Path(json_directory).mkdir(parents=True, exist_ok=True)
            json_file_path = os.path.join(json_directory, f'{item_id}.json')
            with open(json_file_path, 'w', encoding='utf-8') as json_file:
                json.dump(item_json, json_file, ensure_ascii=False, indent=None)
            items_saved += 1
        return items_saved

    def delete_works(self):
        """
        Delete unpublished Works from the file system.
        """
        resource = 'works'
        params = self.params.copy()
        params['unpublished'] = True
        elastic_search = Search()
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
            # Remove the Work from the search index
            elastic_search.delete(resource, work_id)

        print(f'Finished deleting {works_deleted}/{len(work_ids_to_delete)} {resource}.')

    def save_items_lists(self, resource):
        """
        Download and save all Items list pages from XOS.
        """
        print(f'Saving all {resource} list index files...')
        params = self.params.copy()
        params['page'] = 1
        while True:
            works_json = self.get(resource, params).json()
            works_json = self.update_assets(works_json)
            self.remove_external_works(works_json)
            self.save_list(resource, works_json, params.get('page'))
            if not works_json.get('next'):
                break
            params['page'] = furl(works_json.get('next')).args.get('page')

    def update_assets(self, item_json, delete=False):
        """
        Upload images/videos to a public bucket, and update the links in the json.
        """
        # Upload assets to ACMI public API bucket
        asset_regex = r'(https:\/\/[a-z0-9\-]+\.s3[a-z0-9\-\.]+amazonaws\.com.*?)\?'
        assets = re.findall(asset_regex, str(item_json))
        for asset in assets:
            source = re.findall(r'https:\/\/(.*?)\.s3', asset)[0]
            key = re.findall(r'\.com/(.*?)$', asset)[0]
            destination_key = re.findall(r'\.com\/media\/(.*?)$', asset)[0]

            # Unquote URL quoted filenames
            key = unquote(key)
            destination_key = unquote(destination_key)

            if 'collection/' in destination_key:
                destination_key = destination_key.replace('collection/', '')
            elif 'works/' in destination_key:
                destination_key = destination_key.replace('works/', '')
            elif '.mp3' in destination_key:
                destination_key = f'audio/{destination_key}'
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
                item_json_string = re.sub(
                    rf'"({asset})\?.*?"',
                    f'"https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/{destination_key}"',
                    json.dumps(item_json),
                )
                item_json = json.loads(item_json_string)

        if not INCLUDE_IMAGES:
            self.remove_assets(item_json, 'images')

        if not INCLUDE_VIDEOS:
            self.remove_assets(item_json, 'videos')
            self.remove_assets(item_json, 'video')
            self.remove_video_links(item_json)

        return item_json

    def remove_assets(self, item_json, asset):
        """
        Remove assets from the API.
        """

        if item_json.get('id'):
            # Individual record
            item_json.pop(asset, None)
            self.remove_all_thumbnails(item_json)
        else:
            # Index page of records
            for item in item_json.get('results'):
                item.pop(asset, None)
                self.remove_all_thumbnails(item)

    def remove_external_works(self, work_json):
        """
        Remove external works from the group_siblings field.
        e.g. records where the acmi_id starts with AEO, LN, or P.
        Note: we want to fix this in the XOS external=false filter
        but for now let's do it here for launch.
        """
        loaned_work_prefixes = [
            'AEO',
            'LN',
            'P',
        ]
        if work_json.get('id'):
            # Individual record
            self.remove_sibling(work_json, loaned_work_prefixes)
        else:
            # Index page of records
            for work in work_json['results']:
                self.remove_sibling(work, loaned_work_prefixes)

    def remove_sibling(self, work_json, prefixes):
        """
        Remove a sibling from the group_siblings field if its acmi_id
        starts with one of the prefixes.
        """
        try:
            for sibling in work_json['group_siblings'][:]:
                for prefix in prefixes:
                    if sibling['acmi_id'].startswith(prefix):
                        print(
                            f'Removing group sibling: {sibling["id"]}, '
                            f'ACMI ID: {sibling["acmi_id"]} from: {work_json["id"]}'
                        )
                        work_json['group_siblings'].remove(sibling)
        except KeyError:
            pass

    def remove_all_thumbnails(self, item_json):  # pylint: disable=too-many-branches
        """
        Remove all thumbnails from an item JSON, including group works etc.
        Because we don't know whether a related Work has thumbnails from
        a video or an image, let's be overly conservative and remove them
        all when either INCLUDE_IMAGES or INCLUDE_VIDEOS is False.
        """
        item_json.pop('thumbnail', None)

        if item_json.get('group'):
            item_json['group'].pop('thumbnail', None)
        if item_json.get('group_works'):
            for work in item_json.get('group_works'):
                work.pop('thumbnail', None)
        if item_json.get('group_siblings'):
            for work in item_json.get('group_siblings'):
                work.pop('thumbnail', None)

        if item_json.get('part'):
            item_json['part'].pop('thumbnail', None)
        if item_json.get('parts'):
            for work in item_json.get('parts'):
                work.pop('thumbnail', None)
        if item_json.get('part_siblings'):
            for work in item_json.get('part_siblings'):
                work.pop('thumbnail', None)

        # Constellations
        if item_json.get('key_work'):
            item_json['key_work'].pop('thumbnail', None)
        if item_json.get('links'):
            for link in item_json.get('links'):
                if link.get('start'):
                    link['start'].pop('thumbnail', None)
                if link.get('end'):
                    link['end'].pop('thumbnail', None)

        # Creators
        item_json.pop('image', None)

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
            writer.writerow(self.get_tsv_header(resource))

            files_written = 0
            file_paths = glob.glob(f'{os.path.join(JSON_ROOT, resource)}/[0-9]*.json')
            print(f'Generating the TSV for {resource}...')
            for file_path in file_paths:
                if 'index' not in file_path:
                    with open(file_path, 'rb') as json_file:
                        json_data = json.load(json_file)
                        writer.writerow(self.get_tsv_row(resource, json_data))
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

    def external_references_to_string(self, external_references):
        """
        Return a comma separated string of tuples from a list of external references.
        """
        try:
            return ','.join([
                f'({reference["source"]["name"]},{reference["source_identifier"]})'
                for reference in external_references
            ])
        except TypeError:
            return ''

    def get_tsv_header(self, resource):
        """
        Returns an array of header strings for the TSV file of this resource.
        """
        header = None
        if resource == 'works':
            header = [
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
                'eaas_environment_id',
                'external_references',
            ]
        if resource == 'creators':
            header = [
                'id',
                'name',
                'also_known_as',
                'date_of_birth',
                'date_of_death',
                'places_of_operation',
                'biography',
                'biography_author',
                'date_of_biography',
                'external_links',
                'uuid',
                'source',
                'source_identifier',
                'external_references',
                'date_modified',
            ]
        return header

    def get_tsv_row(self, resource, json_data):
        """
        Returns an array of row data strings for the TSV file of this resource.
        """
        row = []
        if resource == 'works':
            row = [
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
                self.keys_from_dicts('creator_id', json_data.get('creators_primary')),
                self.keys_from_dicts('creator_id', json_data.get('creators_other')),
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
                json_data.get('eaas_environment_id'),
                self.external_references_to_string(
                    json_data.get('external_references')
                ),
            ]
        if resource == 'creators':
            row = [
                json_data.get('id'),
                json_data.get('name'),
                json_data.get('also_known_as'),
                json_data.get('date_of_birth'),
                json_data.get('date_of_death'),
                self.keys_from_dicts('name', json_data.get('places_of_operation')),
                json_data.get('biography'),
                json_data.get('biography_author'),
                json_data.get('date_of_biography'),
                self.keys_from_dicts('uri', json_data.get('external_links')),
                json_data.get('uuid'),
                self.nested_value(json_data, ['source', 'name'], ''),
                json_data.get('source_identifier'),
                self.external_references_to_string(
                    json_data.get('external_references')
                ),
                json_data.get('date_modified'),
            ]
        return row


class Suggestion(database.Model):  # pylint: disable=too-few-public-methods
    """
    Suggestions database model.
    """
    id = database.Column(database.Integer, primary_key=True)
    url = database.Column(database.String, unique=True, nullable=False)
    text = database.Column(database.String, nullable=False)
    score = database.Column(database.Integer, default=0)
    suggestions = database.Column(database.Text, default='[]')  # Store list as JSON string

    def to_dict(self):
        return {
            'id': self.id,
            'url': self.url,
            'text': self.text,
            'score': self.score,
            'suggestions': json.loads(self.suggestions)
        }


class SuggestionsListAPI(Resource):  # pylint: disable=too-few-public-methods
    """
    Suggestions API. An implementation of yes/no/fix.
    """
    def __init__(self):
        # Create database tables if they don't exist
        with application.app_context():
            database.create_all()

    def get(self):
        """
        List all Suggestions.
        """
        args = request.args
        limit = int(args.get('limit', '100'))
        suggestions = []
        with application.app_context():
            suggestions = Suggestion.query.order_by(Suggestion.id.desc()).limit(limit).all()
            suggestions_dict = [suggestion.to_dict() for suggestion in suggestions]
        return suggestions_dict

    def post(self):
        """
        Create or update a Suggestion.
        """
        data = request.get_json()
        url = data.get('url')
        text = data.get('text')
        vote = data.get('vote')
        suggestion = data.get('suggestion')
        api_key = request.headers.get('Authorization', '')\
            .replace('Bearer ', '').replace('Token ', '')

        if not api_key or api_key not in SUGGESTIONS_API_KEYS:
            return {'error': 'A valid API Key is required'}, 400

        # Validate that URL and text fields are provided
        if not url or not text:
            return {'error': 'URL and text fields are required'}, 400

        with application.app_context():
            suggestion_object = Suggestion.query.filter_by(url=url, text=text).first()
            if not suggestion_object:
                suggestion_object = Suggestion(url=url, text=text, score=0)
                database.session.add(suggestion_object)

            # Update score based on vote
            if vote:
                if vote == 'up':
                    suggestion_object.score += 1
                elif vote == 'down':
                    suggestion_object.score -= 1
                else:
                    return {'error': "Vote must be 'up' or 'down'"}, 400

            # Add suggestion to the list if provided
            if suggestion:
                suggestions_list = json.loads(suggestion_object.suggestions or '[]')
                if suggestion not in suggestions_list:
                    suggestions_list.append(suggestion)
                suggestion_object.suggestions = json.dumps(suggestions_list)

            database.session.commit()
            return suggestion_object.to_dict()


class SuggestionsAPI(Resource):  # pylint: disable=too-few-public-methods
    """
    Get an individual Suggestions JSON.
    """
    def get(self, suggestion_id):
        """
        Returns the requested Suggestion or a 404.
        """
        with application.app_context():
            suggestion = Suggestion.query.filter_by(id=suggestion_id).first()
            if suggestion:
                return suggestion.to_dict()
        return abort(404, message='That Suggestion doesn\'t exist, sorry.')


api.add_resource(API, '/')
api.add_resource(AudioListAPI, '/audio/')
api.add_resource(AudioAPI, '/audio/<audio_id>/')
api.add_resource(ConstellationsAPI, '/constellations/')
api.add_resource(ConstellationAPI, '/constellations/<constellation_id>/')
api.add_resource(CreatorsAPI, '/creators/')
api.add_resource(CreatorAPI, '/creators/<creator_id>/')
api.add_resource(WorksAPI, '/works/')
api.add_resource(WorkAPI, '/works/<work_id>/')
api.add_resource(SearchAPI, '/search/')
api.add_resource(SuggestionsListAPI, '/suggestions/')
api.add_resource(SuggestionsAPI, '/suggestions/<suggestion_id>/')

if __name__ == '__main__':
    if UPDATE_ITEMS:
        print('========================================')
        print('Starting to update Works API from XOS...')
        xos_private_api = XOSAPI()
        xos_private_api.get_works()
        xos_private_api.delete_works()
        xos_private_api.generate_tsv('works')
        search = Search()
        search.update_index(resource='works')
        print('=================================================')
        print('Starting to update Audio API from XOS...')
        xos_private_api.get_audio()
        search.update_index(resource='audio')
        print('=================================================')
        print('Starting to update Constellations API from XOS...')
        xos_private_api.get_constellations()
        search.update_index(resource='constellations')
        print('=================================================')
        print('Starting to update Creators API from XOS...')
        xos_private_api.get_creators()
        xos_private_api.generate_tsv('creators')
        search.update_index(resource='creators')
        print('=================================================')
    elif UPDATE_SEARCH:
        print('========================')
        print('Starting search indexing...')
        search = Search()
        search.update_index(resource='works')
        search.update_index(resource='audio')
        search.update_index(resource='constellations')
        search.update_index(resource='creators')
        print('========================')
    else:
        application.run(
            host='0.0.0.0',
            port=8081,
            debug=DEBUG,
        )
