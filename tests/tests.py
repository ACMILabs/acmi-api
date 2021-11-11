import csv
import json
import os
from unittest.mock import MagicMock, mock_open, patch

import botocore
import elasticsearch
import requests

import app.api as acmi_api
from app.api import API, AWS_STORAGE_BUCKET_NAME, XOSAPI


class MockResponse:
    def __init__(self, json_data, status_code):
        self.content = json.loads(json_data)
        self.status_code = status_code

    def json(self):
        return self.content

    def raise_for_status(self):
        return None


def mocked_requests_get(*args, **kwargs):
    if kwargs['url'] == 'https://xos.acmi.net.au/api/works/':
        if kwargs['params'].get('page') == '2':
            if kwargs['params'].get('unpublished'):
                with open('tests/data/index_page_2_unpublished.json', 'rb') as json_file:
                    return MockResponse(json_file.read(), 200)
            with open('tests/data/index_page_2.json', 'rb') as json_file:
                return MockResponse(json_file.read(), 200)
        with open('tests/data/index.json', 'rb') as json_file:
            return MockResponse(json_file.read(), 200)
    if kwargs['url'] == 'https://xos.acmi.net.au/api/works/1/':
        with open('tests/data/1.json', 'rb') as json_file:
            return MockResponse(json_file.read(), 200)
    if kwargs['url'] == 'https://xos.acmi.net.au/api/works/2/':
        with open('tests/data/2.json', 'rb') as json_file:
            return MockResponse(json_file.read(), 200)

    raise Exception("No mocked sample data for request: " + kwargs['url'])


def mock_boto3(_, key):
    """
    Mock boto3 responses.
    """
    if key == 'image/image-to-delete.jpg':
        return MagicMock()
    raise botocore.exceptions.ClientError(
        error_response={'Error': {'Code': '404'}},
        operation_name='HeadObject',
    )


def mock_index():
    """
    Mocked index.json data.
    """
    with open('tests/data/index.json', 'rb') as json_file:
        return mock_open(read_data=json_file.read())


def mock_work():
    """
    Mocked individual work.json data.
    """
    with open('tests/data/1.json', 'rb') as json_file:
        return mock_open(read_data=json_file.read())


def mock_file_not_found():
    """
    Mocked file not found.
    """
    mock = mock_open()
    mock.side_effect = FileNotFoundError
    return mock


def mock_search(index=None, body=None, q=None, params=None):  # pylint: disable=invalid-name
    """
    Mock Elasticsearch responses.
    """
    if q == '404':
        raise elasticsearch.exceptions.NotFoundError
    if q == '400':
        raise elasticsearch.exceptions.RequestError
    if q == '503':
        raise elasticsearch.exceptions.ConnectionError
    if q == '504':
        raise elasticsearch.exceptions.ConnectionTimeout
    if q and not body:
        with open(
            f'tests/data/search_{index}_{q}_{params["size"]}_{params["from"]}.json',
            'rb',
        ) as json_file:
            return json.loads(json_file.read())
    elif body and not q:
        key = [key for key in body['query']['match'].keys()][0]  # pylint: disable=unnecessary-comprehension
        with open(
            f'tests/data/search_{index}_{body["query"]["match"][key]}_'
            f'{key}_{body["size"]}_{body["from"]}.json',
            'rb',
        ) as json_file:
            return json.loads(json_file.read())
    raise elasticsearch.exceptions.NotFoundError


def test_api_root():
    """
    Test the API root returns expected content.
    """
    api = API()
    assert api.get()['message'] == 'Welcome to the ACMI Public API.'
    assert api.get()['api'] == ['/search/', '/works/', '/works/<work_id>/']
    assert 'ACMI acknowledges the Traditional Owners' in api.get()['acknowledgement']


@patch('builtins.open', mock_index())
def test_works_api():
    """
    Test the Works API returns expected content.
    """
    with acmi_api.application.test_client() as client:
        response = client.get(
            '/works/',
            content_type='application/json',
        )
        assert response.status_code == 200
        assert response.json['next'] == 'https://api.acmi.net.au/works/?page=2'
        assert response.json['results']
        assert response.json['count']


@patch('builtins.open', mock_file_not_found())
def test_works_api_404():
    """
    Test the Works API returns a 404 as expected.
    """
    with acmi_api.application.test_client() as client:
        response = client.get(
            '/works/?page=999999',
            content_type='application/json',
        )
        assert response.status_code == 404
        assert response.json['message'] == 'That Works list doesn\'t exist, sorry.'

        response = client.get(
            '/works/?page=!~*&-evil-text"',
            content_type='application/json',
        )
        assert response.status_code == 404
        assert response.json['message'] == 'That Works list doesn\'t exist, sorry.'


@patch('builtins.open', mock_work())
def test_work_api():
    """
    Test the individual Work API returns expected content.
    """
    with acmi_api.application.test_client() as client:
        response = client.get(
            '/works/1/',
            content_type='application/json',
        )
        assert response.status_code == 200
        assert response.json['id'] == 1
        assert response.json['description'] == 'Work data returned from the filesystem.'


@patch('builtins.open', mock_file_not_found())
def test_work_api_404():
    """
    Test the individual Work API returns a 404 as expected.
    """
    with acmi_api.application.test_client() as client:
        response = client.get(
            '/works/2/',
            content_type='application/json',
        )
        assert response.status_code == 404
        assert response.json['message'] == 'That Work doesn\'t exist, sorry.'

        response = client.get(
            '/works/!~*&-evil-text"/',
            content_type='application/json',
        )
        assert response.status_code == 404
        assert response.json['message'] == 'That Work doesn\'t exist, sorry.'


@patch('requests.get', MagicMock(side_effect=mocked_requests_get))
def test_get_works(tmp_path):
    """
    Test get and save XOS works saves expected JSON files.
    """
    acmi_api.JSON_ROOT = tmp_path
    xos_private_api = XOSAPI()
    xos_private_api.get_works()
    with open(acmi_api.JSON_ROOT / 'works/index.json', 'rb') as index_page_1:
        index_page_1_json = json.load(index_page_1)
        assert index_page_1_json['next'] == 'https://api.acmi.net.au/works/?page=2'
        assert not index_page_1_json['previous']
        assert index_page_1_json['results']
        assert index_page_1_json['count']

    with open(acmi_api.JSON_ROOT / 'works/index_page_2.json', 'rb') as index_page_2:
        index_page_2_json = json.load(index_page_2)
        assert not index_page_2_json['next']
        assert index_page_2_json['previous'] == 'https://api.acmi.net.au/works/?page=1'
        assert index_page_2_json['results']
        assert index_page_2_json['count']

    with open(acmi_api.JSON_ROOT / 'works/1.json', 'rb') as work:
        work_json = json.load(work)
        assert work_json['id'] == 1
        assert work_json['description'] == 'Work data returned from the filesystem.'

    with open(acmi_api.JSON_ROOT / 'works/2.json', 'rb') as work:
        work_json = json.load(work)
        assert work_json['id'] == 2
        assert work_json['description'] == 'Work data 2 returned from the filesystem.'

    assert not os.path.isfile(acmi_api.JSON_ROOT / 'works/3.json')


@patch('requests.get', MagicMock(side_effect=mocked_requests_get))
@patch('app.api.s3_resource.Object', MagicMock(side_effect=mock_boto3))
def test_delete_works(tmp_path):
    """
    Test delete XOS works removes expected JSON files.
    """
    acmi_api.JSON_ROOT = tmp_path
    xos_private_api = XOSAPI()
    xos_private_api.get_works()
    assert os.path.isfile(acmi_api.JSON_ROOT / 'works/index.json')
    assert os.path.isfile(acmi_api.JSON_ROOT / 'works/index_page_2.json')
    assert os.path.isfile(acmi_api.JSON_ROOT / 'works/1.json')
    assert os.path.isfile(acmi_api.JSON_ROOT / 'works/2.json')
    xos_private_api.delete_works()
    assert os.path.isfile(acmi_api.JSON_ROOT / 'works/index.json')
    assert os.path.isfile(acmi_api.JSON_ROOT / 'works/index_page_2.json')
    assert os.path.isfile(acmi_api.JSON_ROOT / 'works/1.json')
    assert not os.path.isfile(acmi_api.JSON_ROOT / 'works/2.json')


@patch('app.api.s3_resource.Object', MagicMock(side_effect=mock_boto3))
@patch('app.api.destination_bucket', MagicMock())
def test_update_assets():
    """
    Test update assets uploads and renames asset links.
    """
    with open('tests/data/100542.json', 'rb') as work:
        acmi_api.INCLUDE_IMAGES = True
        acmi_api.INCLUDE_VIDEOS = True
        work_json = json.load(work)
        xos_private_api = XOSAPI()
        work_json_1 = xos_private_api.update_assets(work_json)
        thumbnail_filename = (
            f'https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/'
            'image/Z000133_Webwurld_Still2_ACMI.tif.1200x1200_q85.jpg'
        )
        assert work_json_1['thumbnail']['image_url'] == thumbnail_filename
        assert work_json_1['images'][0]['image_file'] == \
            thumbnail_filename.replace('.1200x1200_q85.jpg', '')
        assert work_json_1['images'][0]['image_file_l'] == \
            thumbnail_filename.replace('1200x1200', '3840x3840')
        assert work_json_1['video_links'][0]['uri'] == 'https://vimeo.com/19599227'
        assert work_json_1['video_links'][1]['uri'] == 'https://youtu.be/tCI396HyhbQ'

        acmi_api.INCLUDE_IMAGES = True
        acmi_api.INCLUDE_VIDEOS = False
        work_json_2 = xos_private_api.update_assets(work_json)
        assert not work_json_2.get('thumbnail')
        assert work_json_2.get('images')
        assert work_json_2['video_links'][0]['uri'] == 'https://youtu.be/tCI396HyhbQ'
        assert len(work_json_2['video_links']) == 1

        acmi_api.INCLUDE_IMAGES = False
        acmi_api.INCLUDE_VIDEOS = False
        work_json_3 = xos_private_api.update_assets(work_json)
        assert not work_json_3.get('thumbnail')
        assert not work_json_3.get('images')
        assert work_json_3['video_links'][0]['uri'] == 'https://youtu.be/tCI396HyhbQ'
        assert len(work_json_3['video_links']) == 1

    with open('tests/data/111326.json', 'rb') as video:
        acmi_api.INCLUDE_IMAGES = True
        acmi_api.INCLUDE_VIDEOS = True
        video_json = json.load(video)
        xos_private_api = XOSAPI()
        video_json_1 = xos_private_api.update_assets(video_json)
        thumbnail_filename = (
            f'https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/'
            'video/snapshot_1657_669s.jpg'
        )
        video_filename = (
            f'https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/'
            'video/a_000011_ap01_FiftyYearsOfService.mp4'
        )
        assert video_json_1['thumbnail']['image_url'] == thumbnail_filename
        assert video_json_1['videos'][0]['resource'] == video_filename

        acmi_api.INCLUDE_IMAGES = False
        acmi_api.INCLUDE_VIDEOS = True
        video_json_3 = xos_private_api.update_assets(video_json)
        assert not video_json_3.get('thumbnail')
        assert video_json_3.get('videos')

        acmi_api.INCLUDE_IMAGES = False
        acmi_api.INCLUDE_VIDEOS = False
        video_json_3 = xos_private_api.update_assets(video_json)
        assert not video_json_3.get('thumbnail')
        assert not video_json_3.get('videos')


def test_include_external_filter():
    """
    Test the INCLUDE_EXTERNAL variable sets the XOS API `exclude` filter as expected.
    """
    with patch('requests.get', MagicMock()) as mock_get:
        xos_private_api = XOSAPI()
        xos_private_api.get('works')
        assert not mock_get.call_args[1]['params']['external']
        assert not mock_get.call_args[1]['params']['unpublished']

    with patch('requests.get', MagicMock()) as mock_get:
        acmi_api.INCLUDE_EXTERNAL = True
        xos_private_api = XOSAPI()
        xos_private_api.get('works')
        assert mock_get.call_args[1]['params']['external']
        assert not mock_get.call_args[1]['params']['unpublished']


def test_search_api():
    """
    Test the Search API root returns expected content.
    """
    with acmi_api.application.test_client() as client:
        response = client.get(
            '/search/',
            content_type='application/json',
        )
        assert response.status_code == 400
        assert response.json['message'] == 'Try adding a search query. e.g. /search/?query=xos'


@patch('elasticsearch.Elasticsearch.search', MagicMock(side_effect=mock_search))
def test_search_api_results():
    """
    Test the Search API results returns expected content.
    """
    with acmi_api.application.test_client() as client:
        response = client.get(
            '/search/?query=xos',
            content_type='application/json',
        )
        assert response.status_code == 200
        assert response.json['count'] == 243
        assert response.json['next'] == 'http://localhost/search/?query=xos&page=2'
        assert not response.json['previous']
        assert len(response.json['results']) == 20
        assert response.json['results'][0]['id'] == 114496

    with acmi_api.application.test_client() as client:
        response = client.get(
            '/search/?query=xos&page=2',
            content_type='application/json',
        )
        assert response.status_code == 200
        assert response.json['count'] == 243
        assert response.json['next'] == 'http://localhost/search/?query=xos&page=3'
        assert response.json['previous'] == 'http://localhost/search/?query=xos&page=1'
        assert len(response.json['results']) == 20
        assert response.json['results'][0]['id'] == 107348

    with acmi_api.application.test_client() as client:
        response = client.get(
            '/search/?query=xos&page=2&size=10',
            content_type='application/json',
        )
        assert response.status_code == 200
        assert response.json['count'] == 243
        assert response.json['next'] == 'http://localhost/search/?query=xos&size=10&page=3'
        assert response.json['previous'] == 'http://localhost/search/?query=xos&size=10&page=1'
        assert len(response.json['results']) == 10
        assert response.json['results'][0]['id'] == 106665

    with acmi_api.application.test_client() as client:
        response = client.get(
            '/search/?query=dog&field=title&size=4&page=3',
            content_type='application/json',
        )
        assert response.status_code == 200
        assert response.json['count'] == 63
        assert response.json['next'] == \
            'http://localhost/search/?query=dog&field=title&size=4&page=4'
        assert response.json['previous'] == \
            'http://localhost/search/?query=dog&field=title&size=4&page=2'
        assert len(response.json['results']) == 4
        assert response.json['results'][0]['id'] == 108013

    with acmi_api.application.test_client() as client:
        response = client.get(
            '/search/?query=xos&raw=true',
            content_type='application/json',
        )
        assert response.status_code == 200
        assert response.json['hits']['total']['value'] == 243
        assert len(response.json['hits']['hits']) == 20
        assert response.json['hits']['hits'][0]['_source']['id'] == 114496

    with acmi_api.application.test_client() as client:
        response = client.get(
            '/search/?query=xos&field=title',
            content_type='application/json',
        )
        assert response.status_code == 200
        assert response.json['count'] == 1
        assert response.json['next'] == 'http://localhost/search/?query=xos&field=title&page=2'
        assert not response.json['previous']
        assert len(response.json['results']) == 1
        assert response.json['results'][0]['id'] == 78738


@patch('elasticsearch.Elasticsearch.search', MagicMock(side_effect=mock_search))
def test_search_api_results_failures():
    """
    Test the Search API results fails as expected.
    """
    with acmi_api.application.test_client() as client:
        response = client.get(
            '/search/?query=404',
            content_type='application/json',
        )
        assert response.status_code == 404
        assert response.json['message'] == 'No results found, sorry.'

    with acmi_api.application.test_client() as client:
        response = client.get(
            '/search/?query=400',
            content_type='application/json',
        )
        assert response.status_code == 400
        assert response.json['message'] == 'Error in your query.'

    with acmi_api.application.test_client() as client:
        response = client.get(
            '/search/?query=503',
            content_type='application/json',
        )
        assert response.status_code == 503
        assert response.json['message'] == \
            'Sorry, search is unavailable at the moment. Please try again later.'

    with acmi_api.application.test_client() as client:
        response = client.get(
            '/search/?query=504',
            content_type='application/json',
        )
        assert response.status_code == 504
        assert response.json['message'] == \
            'Sorry, your search request timed out. Please try again later.'


def test_xos_private_api_retries(tmp_path):
    """
    Test the XOS private API interface retries 3 times before failing gracefully.
    """
    with patch('requests.get', MagicMock(side_effect=requests.exceptions.ReadTimeout)) as mock_get:
        acmi_api.JSON_ROOT = tmp_path
        xos_private_api = XOSAPI()
        response = xos_private_api.get('works')
        assert not response
        assert mock_get.call_count == 3


def test_generate_tsv(tmp_path):
    """
    Test the generated TSV is in the correct format with the right number of rows.
    """
    acmi_api.TSV_ROOT = tmp_path
    acmi_api.JSON_ROOT = '/code/tests/'
    xos_private_api = XOSAPI()
    xos_private_api.generate_tsv('data')
    assert os.path.isfile(acmi_api.TSV_ROOT / 'data.tsv')
    with open(f'{acmi_api.TSV_ROOT}/data.tsv', encoding='utf-8') as tsv_file:
        reader = csv.reader(tsv_file, delimiter='\t')
        header = next(reader)
        assert len(header) == 47
        assert header[0] == 'id'
        row_count = 0
        for _ in reader:
            row_count += 1
        assert row_count == 4


def test_keys_from_dicts():
    """
    Test the keys_from_dicts method returns the correct data.
    """
    your_list = []
    dict_1 = {'id': 1}
    dict_2 = {'id': 9}
    dict_3 = {'id': 2}
    your_list.append(dict_1)
    your_list.append(dict_2)
    your_list.append(dict_3)
    keys = XOSAPI().keys_from_dicts('id', your_list)
    assert keys == '1,9,2'

    your_list = []
    dict_1 = {'name': 'Pip'}
    dict_2 = {'name': 'Simon'}
    dict_3 = {'name': 'Sam'}
    your_list.append(dict_1)
    your_list.append(dict_2)
    your_list.append(dict_3)
    keys = XOSAPI().keys_from_dicts('name', your_list)
    assert keys == 'Pip,Simon,Sam'


def test_nested_value():
    """
    Test the nested_value method returns the correct data.
    """
    default_value = 'Oh really?'
    dictionary = {
        'this': {
            'that': 'The other.',
        }
    }
    value = XOSAPI().nested_value(dictionary, ['this', 'that'], default_value)
    assert value == 'The other.'
    value = XOSAPI().nested_value(dictionary, ['this', 'something'], default_value)
    assert value == 'Oh really?'
    value = XOSAPI().nested_value(dictionary, ['something', 'else'], default_value)
    assert value == 'Oh really?'


def test_strings_from_list():
    """
    Test the strings_from_list method returns the correct data.
    """
    your_list = [1, 2, 7, 9]
    string = XOSAPI().strings_from_list(your_list)
    assert string == '1,2,7,9'
    string = XOSAPI().strings_from_list(666)
    assert string == ''


def test_remove_external_works():
    """
    Test removing external works removes siblings with an acmi_id
    prefix of AEO, LN or P from group_siblings.
    """
    xos_private_api = XOSAPI()
    work_json = {
        'id': 119669,
        'group_siblings': [
            {
                'id': 123,
                'acmi_id': 'AEO123',
            },
            {
                'id': 124,
                'acmi_id': 'LN124',
            },
            {
                'id': 125,
                'acmi_id': 'P125',
            },
            {
                'id': 126,
                'acmi_id': '126',
            }
        ]
    }
    assert len(work_json['group_siblings']) == 4
    xos_private_api.remove_external_works(work_json)
    assert len(work_json['group_siblings']) == 1
    assert work_json['group_siblings'][0]['id'] == 126

    works_json = {
        'results': [
            {
                'id': 119669,
                'group_siblings': [
                    {
                        'id': 123,
                        'acmi_id': 'AEO123',
                    },
                    {
                        'id': 126,
                        'acmi_id': '126',
                    }
                ]
            },
            {
                'id': 119670,
                'group_siblings': [
                    {
                        'id': 124,
                        'acmi_id': 'LN124',
                    },
                    {
                        'id': 128,
                        'acmi_id': '128',
                    }
                ]
            }
        ]
    }
    assert len(works_json['results']) == 2
    assert len(works_json['results'][0]['group_siblings']) == 2
    assert len(works_json['results'][1]['group_siblings']) == 2
    xos_private_api.remove_external_works(works_json)
    assert len(works_json['results']) == 2
    assert len(works_json['results'][0]['group_siblings']) == 1
    assert works_json['results'][0]['group_siblings'][0]['id'] == 126
    assert len(works_json['results'][1]['group_siblings']) == 1
    assert works_json['results'][1]['group_siblings'][0]['id'] == 128
