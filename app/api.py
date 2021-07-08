import datetime
import json
import os
import requests
from threading import Thread

from flask import Flask
from flask_restful import abort, Resource, Api

DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'
XOS_API_ENDPOINT = os.getenv('XOS_API_ENDPOINT', None)
SITE_ROOT = os.path.realpath(os.path.dirname(__file__))
JSON_ROOT = os.path.join(SITE_ROOT, 'json/')

app = Flask(__name__)
api = Api(app)

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
        for route in app.url_map.iter_rules():
            if 'static' not in str(route) and not str(route) == '/':
                routes.append('%s' % route)
        return routes

class WorksAPI(Resource):
    """
    Works API. The ACMI Collection.
    """
    def get(self):
        """
        List public Works.
        """
        try:
            json_file_path = os.path.join(JSON_ROOT, 'works', f'index.json')
            data = json.load(open(json_file_path))
            return data
        except FileNotFoundError:
            return {abort(404, message=f'Works couldn\'t be downloaded from {XOS_API_ENDPOINT}, sorry.')}

class Work(Resource):
    """
    Get an individual Work JSON.
    """
    def get(self, work_id):
        """
        Returns the requested Work or a 404.
        """
        try:
            json_file_path = os.path.join(JSON_ROOT, 'works', f'{work_id}.json')
            data = json.load(open(json_file_path))
            return data
        except FileNotFoundError:
            return abort(404, message=f'Work {work_id} doesn\'t exist, sorry.')

class XOSAPI():
    """
    XOS private API interface.
    """
    def __init__(self):
        self.uri = XOS_API_ENDPOINT

    def get(self, resource):
        """
        Returns JSON for this resource.
        """
        xos_endpoint = os.path.join(self.uri, f'{resource}/')
        params = {'date_modified__gte': datetime.datetime.now() - datetime.timedelta(hours=6)}
        try:
            json_file_path = os.path.join(JSON_ROOT, 'works', 'index.json')
            json_data = requests.get(url=xos_endpoint, params=params, timeout=15).json()
            with open(json_file_path, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=4)
            message = f'Saved {json_data.get("count")} {resource} from {xos_endpoint} to {json_file_path}'
            print(message)
        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as exception:
            print(f'ERROR: couldn\'t get {xos_endpoint} with exception: {exception}')
        
        print('Downloading individual works...')
        try:
            # TODO: Page through all results...
            for result in json_data.get('results'):
                work_id = str(result.get('id'))
                xos_work_endpoint = os.path.join(xos_endpoint, work_id)
                work_json = requests.get(url=xos_work_endpoint, timeout=15).json()
                json_file_path = os.path.join(JSON_ROOT, 'works', f'{work_id}.json')
                with open(json_file_path, 'w', encoding='utf-8') as f:
                    json.dump(work_json, f, ensure_ascii=False, indent=4)
            print(f'Finished downloading Works.')
        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as exception:
            print(f'ERROR: couldn\'t get {xos_endpoint} with exception: {exception}')

api.add_resource(API, '/')
api.add_resource(WorksAPI, '/api/works/')
api.add_resource(Work, '/api/works/<work_id>/')

if __name__ == '__main__':
    print('===============================================')
    print('Starting thread to update Works API from XOS...')
    xos_private_api = XOSAPI()
    Thread(target=xos_private_api.get('works')).start()
    print('===============================================')
    app.run(
        host='0.0.0.0',
        port=8081,
        debug=DEBUG,
    )
