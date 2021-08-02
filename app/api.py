import datetime
import json
import os
from pathlib import Path
from urllib.parse import urljoin

import pytz
import requests
from flask import Flask, request
from flask_restful import Api, Resource, abort
from furl import furl

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

application = Flask(__name__)
api = Api(application)


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
        self.next_page = None

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
        works_json = self.get(resource, params).json()
        self.next_page = works_json.get('next')
        self.save_works_list(resource, works_json)
        works_saved = 0
        works_saved += self.save_works(resource, works_json)
        while self.next_page:
            params['page'] = furl(self.next_page).args.get('page')
            works_json = self.get(resource, params).json()
            self.next_page = works_json.get('next')
            self.save_works_list(resource, works_json, params.get('page'))
            works_saved += self.save_works(resource, works_json)
        print(f'Finished downloading {works_saved} {resource}.')

        if not ALL_WORKS:
            # TODO: Enable this once we're live # pylint: disable=fixme
            # self.save_works_lists(resource)
            pass

    def save_works_list(self, resource, works_json, page=None):
        """
        Save a list of Works page from XOS.
        """
        endpoint = urljoin(ACMI_API_ENDPOINT, f'/{resource}/')
        if page:
            if works_json.get('next'):
                works_json['next'] = f'{endpoint}?page={int(page) + 1}'
            works_json['previous'] = f'{endpoint}?page={int(page) - 1}'
            page = f'_page_{page}'
        else:
            works_json['next'] = f'{endpoint}?page=2'
            works_json['previous'] = None
            page = ''
        json_directory = os.path.join(JSON_ROOT, resource)
        Path(json_directory).mkdir(parents=True, exist_ok=True)
        json_file_path = os.path.join(json_directory, f'index{page}.json')
        with open(json_file_path, 'w', encoding='utf-8') as json_file:
            json.dump(works_json, json_file, ensure_ascii=False, indent=4)
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
            json_directory = os.path.join(JSON_ROOT, resource)
            Path(json_directory).mkdir(parents=True, exist_ok=True)
            json_file_path = os.path.join(json_directory, f'{work_id}.json')
            work_json = self.update_assets(work_json)
            with open(json_file_path, 'w', encoding='utf-8') as json_file:
                json.dump(work_json, json_file, ensure_ascii=False, indent=4)
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
        works_json = self.get(resource, params).json()
        self.next_page = works_json.get('next')
        for result in works_json['results']:
            if result.get('unpublished'):
                work_ids_to_delete.append(str(result.get('id')))
        while self.next_page:
            params['page'] = furl(self.next_page).args.get('page')
            works_json = self.get(resource, params).json()
            self.next_page = works_json.get('next')
            for result in works_json['results']:
                if result.get('unpublished'):
                    work_ids_to_delete.append(str(result.get('id')))

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
        works_json = self.get(resource, params).json()
        self.next_page = works_json.get('next')
        self.save_works_list(resource, works_json)
        while self.next_page:
            params['page'] = furl(self.next_page).args.get('page')
            works_json = self.get(resource, params).json()
            self.next_page = works_json.get('next')
            self.save_works_list(resource, works_json, params.get('page'))

    def update_assets(self, work_json):
        """
        Upload images/videos to a public bucket, and update the links in the json.
        """
        # TODO: Upload images/videos to public bucket # pylint: disable=fixme
        # TODO: Rename image/video links to public bucket # pylint: disable=fixme
        return work_json


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
    application.run(
        host='0.0.0.0',
        port=8081,
        debug=DEBUG,
    )
