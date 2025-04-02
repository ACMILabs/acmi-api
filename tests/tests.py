# pylint: disable=too-many-lines

import csv
import json
import os
from unittest.mock import MagicMock, mock_open, patch

import botocore
import elasticsearch
import pytest
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


class NoDataException(Exception):
    """
    This exception is raised when we don't have mocked sample data for this request.
    """


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

    raise NoDataException("No mocked sample data for request: " + kwargs['url'])


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


def mock_index(resource='works'):
    """
    Mocked index.json data.
    """
    if resource == 'works':
        with open('tests/data/index.json', 'rb') as json_file:
            return mock_open(read_data=json_file.read())
    if resource == 'audio':
        with open('tests/data/audio_index.json', 'rb') as json_file:
            return mock_open(read_data=json_file.read())
    if resource == 'constellations':
        with open('tests/data/constellation_index.json', 'rb') as json_file:
            return mock_open(read_data=json_file.read())
    if resource == 'creators':
        with open('tests/data/creator_index.json', 'rb') as json_file:
            return mock_open(read_data=json_file.read())
    return None


def mock_item(resource='works'):
    """
    Mocked individual item.json data.
    """
    if resource == 'works':
        with open('tests/data/1.json', 'rb') as json_file:
            return mock_open(read_data=json_file.read())
    if resource == 'audio':
        with open('tests/data/audio_1.json', 'rb') as json_file:
            return mock_open(read_data=json_file.read())
    if resource == 'constellations':
        with open('tests/data/constellation_1.json', 'rb') as json_file:
            return mock_open(read_data=json_file.read())
    if resource == 'creators':
        with open('tests/data/creator_34373.json', 'rb') as json_file:
            return mock_open(read_data=json_file.read())
    return None


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
        raise elasticsearch.exceptions.NotFoundError(
            message='Not found',
            meta=MagicMock(),
            body={},
        )
    if q == '400':
        raise elasticsearch.exceptions.RequestError(
            message='Request error',
            meta=MagicMock(),
            body={},
        )
    if q == '503':
        raise elasticsearch.exceptions.ConnectionError(
            message='Server error',
        )
    if q == '504':
        raise elasticsearch.exceptions.ConnectionTimeout(
            message='Connection timeout',
        )
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
    assert api.get()['api'] == [
        '/audio/',
        '/audio/<audio_id>/',
        '/constellations/',
        '/constellations/<constellation_id>/',
        '/creators/',
        '/creators/<creator_id>/',
        '/search/',
        '/suggestions/',
        '/suggestions/<suggestion_id>/',
        '/works/',
        '/works/<work_id>/',
    ]
    assert 'ACMI would like to acknowledge the Traditional Custodians'\
        in api.get()['acknowledgement']


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


@patch('builtins.open', mock_item())
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


@patch('builtins.open', mock_index(resource='audio'))
def test_audio_list_api():
    """
    Test the Audio List API returns expected content.
    """
    with acmi_api.application.test_client() as client:
        response = client.get(
            '/audio/',
            content_type='application/json',
        )
        assert response.status_code == 200
        assert response.json['next'] == 'https://api.acmi.net.au/audio/?page=2'
        assert response.json['results']
        assert response.json['count']

        response = client.get(
            '/audio/?labels=123',
            content_type='application/json',
        )
        assert response.status_code == 200
        assert not response.json['next']
        assert not response.json['results']
        assert response.json['count'] == 0


def test_audio_list_api_labels_filter():
    """
    Test the Audio List API labels filter returns expected content.
    """
    with acmi_api.application.test_client() as client:
        response = client.get(
            '/audio/?labels=61314',
            content_type='application/json',
        )
        assert response.status_code == 200
        assert not response.json['next']
        assert response.json['count'] == 1
        assert response.json['results'][0]['id'] == 1


@patch('builtins.open', mock_item(resource='audio'))
def test_audio_api():
    """
    Test the individual Audio API returns expected content.
    """
    with acmi_api.application.test_client() as client:
        response = client.get(
            '/audio/1/',
            content_type='application/json',
        )
        assert response.status_code == 200
        assert response.json['id'] == 1
        assert response.json['work']['id'] == 122500
        assert response.json['work']['labels'][0] == 61958
        assert 'work_122500.mp3' in response.json['resource']


@patch('builtins.open', mock_index(resource='constellations'))
def test_constellations_api():
    """
    Test the Constellations API returns expected content.
    """
    with acmi_api.application.test_client() as client:
        response = client.get(
            '/constellations/',
            content_type='application/json',
        )
        assert response.status_code == 200
        assert response.json['next'] == 'https://api.acmi.net.au/constellations/?page=2'
        assert response.json['results']
        assert response.json['count']


@patch('builtins.open', mock_item(resource='constellations'))
def test_constellation_api():
    """
    Test the individual Constellation API returns expected content.
    """
    with acmi_api.application.test_client() as client:
        response = client.get(
            '/constellations/1/',
            content_type='application/json',
        )
        assert response.status_code == 200
        assert response.json['id'] == 1
        assert response.json['name'] == 'Pen names, poems and puppets'


@patch('builtins.open', mock_index(resource='creators'))
def test_creators_api():
    """
    Test the Creators API returns expected content.
    """
    with acmi_api.application.test_client() as client:
        response = client.get(
            '/creators/',
            content_type='application/json',
        )
        assert response.status_code == 200
        assert response.json['next'] == 'https://api.acmi.net.au/creators/?page=2'
        assert response.json['results']
        assert response.json['count']


@patch('builtins.open', mock_item(resource='creators'))
def test_creator_api():
    """
    Test the individual Creator API returns expected content.
    """
    with acmi_api.application.test_client() as client:
        response = client.get(
            '/creators/34373/',
            content_type='application/json',
        )
        assert response.status_code == 200
        assert response.json['id'] == 34373
        assert response.json['name'] == 'Agnes Varda'


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
    with patch('elasticsearch.Elasticsearch.delete', MagicMock()) as mock_search_delete:
        xos_private_api.delete_works()
        assert os.path.isfile(acmi_api.JSON_ROOT / 'works/index.json')
        assert os.path.isfile(acmi_api.JSON_ROOT / 'works/index_page_2.json')
        assert os.path.isfile(acmi_api.JSON_ROOT / 'works/1.json')
        assert not os.path.isfile(acmi_api.JSON_ROOT / 'works/2.json')
        assert mock_search_delete.call_args[1]['index'] == 'works'
        assert mock_search_delete.call_args[1]['id'] == '2'

    search_delete_error = elasticsearch.exceptions.ConnectionError(message='Connection error.')
    search_delete_error.args = (500, 'Error', {})
    with patch(
        'elasticsearch.Elasticsearch.delete',
        MagicMock(
            side_effect=search_delete_error,
        ),
    ) as mock_search_delete:
        xos_private_api.get_works()
        assert os.path.isfile(acmi_api.JSON_ROOT / 'works/2.json')
        xos_private_api.delete_works()
        assert not os.path.isfile(acmi_api.JSON_ROOT / 'works/2.json')

    search_delete_error = elasticsearch.exceptions.NotFoundError(
        message='Not found',
        meta=MagicMock(),
        body={},
    )
    search_delete_error.args = (404, 'NotFoundError', {})
    with patch(
        'elasticsearch.Elasticsearch.delete',
        MagicMock(
            side_effect=search_delete_error,
        ),
    ) as mock_search_delete:
        xos_private_api.delete_works()
        assert not os.path.isfile(acmi_api.JSON_ROOT / 'works/2.json')


@patch('requests.get', MagicMock(side_effect=mocked_requests_get))
@patch('app.api.s3_resource.Object', MagicMock(side_effect=mock_boto3))
def test_xos_api_params():
    """
    Test the default XOSAPI params aren't mutated by method calls.
    """
    params = {
        'page_size': 10,
        'unpublished': False,
        'external': False,
    }
    xos_private_api = XOSAPI()
    assert xos_private_api.params == params
    xos_private_api.get_works()
    assert xos_private_api.params == params
    xos_private_api.delete_works()
    assert xos_private_api.params == params


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


@patch('app.api.s3_resource.Object', MagicMock(side_effect=mock_boto3))
@patch('app.api.destination_bucket', MagicMock())
def test_update_assets_with_audio():
    """
    Test update assets uploads and renames Audio asset links.
    Note: thumbnails are always uploaded
    """
    with open('tests/data/audio_1.json', 'rb') as audio:
        acmi_api.INCLUDE_IMAGES = True
        acmi_api.INCLUDE_VIDEOS = True
        audio_json = json.load(audio)
        xos_private_api = XOSAPI()
        audio_json_1 = xos_private_api.update_assets(audio_json)
        thumbnail_filename = (
            f'https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/'
            'image/Marshmallow_Laser_Feast_We_Live_In_An_Ocean_of_Air'
            '_Courtesy_of_artists_2.jpg.1200x1200_q85.jpg'
        )
        resource_filename = (
            f'https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/audio/work_122500.mp3'
        )
        assert audio_json_1['work']['thumbnail']['image_url'] == thumbnail_filename
        assert audio_json_1['resource'] == resource_filename

        acmi_api.INCLUDE_IMAGES = False
        acmi_api.INCLUDE_VIDEOS = False
        audio_json_1 = xos_private_api.update_assets(audio_json)
        assert audio_json_1['work']['thumbnail']['image_url'] == thumbnail_filename
        assert audio_json_1['resource'] == resource_filename


@patch('app.api.s3_resource.Object', MagicMock(side_effect=mock_boto3))
@patch('app.api.destination_bucket', MagicMock())
def test_update_assets_with_constellations():
    """
    Test update assets uploads and renames Constellation asset links.
    """
    with open('tests/data/constellation_1.json', 'rb') as constellation:
        acmi_api.INCLUDE_IMAGES = True
        acmi_api.INCLUDE_VIDEOS = True
        constellation_json = json.load(constellation)
        xos_private_api = XOSAPI()
        constellation_json_1 = xos_private_api.update_assets(constellation_json)
        thumbnail_filename = (
            f'https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/'
            'image/P177007_MyBrilliantCareerBook_34.jpg.1200x1200_q85.jpg'
        )
        assert constellation_json_1['key_work']['thumbnail']['image_url'] == thumbnail_filename
        assert constellation_json_1['links'][2]['start']['thumbnail']['image_url'] == \
            thumbnail_filename

        acmi_api.INCLUDE_IMAGES = False
        acmi_api.INCLUDE_VIDEOS = False
        constellation_json_1 = xos_private_api.update_assets(constellation_json)
        assert not constellation_json_1['key_work'].get('thumbnail')
        assert not constellation_json_1['links'][2]['start'].get('thumbnail')


@patch('app.api.s3_resource.Object', MagicMock(side_effect=mock_boto3))
@patch('app.api.destination_bucket', MagicMock())
def test_update_assets_with_creators():
    """
    Test update assets uploads and renames Creator asset links.
    """
    with open('tests/data/creator_34373.json', 'rb') as creator:
        acmi_api.INCLUDE_IMAGES = True
        acmi_api.INCLUDE_VIDEOS = True
        creator_json = json.load(creator)
        xos_private_api = XOSAPI()
        creator_json_1 = xos_private_api.update_assets(creator_json)
        image_filename = (
            f'https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/'
            'image/AgnC3A8s_Varda_28Berlinale_201929_28cropped29.jpg'
        )
        assert creator_json_1['image'] == image_filename

        acmi_api.INCLUDE_IMAGES = False
        acmi_api.INCLUDE_VIDEOS = False
        creator_json_1 = xos_private_api.update_assets(creator_json)
        assert not creator_json_1.get('image')


@patch('requests.get')
def test_get_creators(mock_get):
    """
    Test get_creators default params.
    """
    mock_get.return_value = MockResponse('{"results": []}', 200)
    xos_private_api = XOSAPI()
    xos_private_api.get_creators()
    assert not mock_get.call_args_list[0][1]['params']['external']
    assert mock_get.call_args_list[0][1]['params']['date_modified__gte']
    # Saving the index
    assert not mock_get.call_args_list[1][1]['params']['external']
    assert not mock_get.call_args_list[1][1]['params'].get('date_modified__gte')

    acmi_api.ALL_CREATORS = True
    xos_private_api = XOSAPI()
    xos_private_api.get_creators()
    assert not mock_get.call_args_list[2][1]['params']['external']
    assert not mock_get.call_args_list[2][1]['params'].get('date_modified__gte')


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


@patch('elasticsearch.Elasticsearch.search', MagicMock(side_effect=mock_search))
def test_search_api_audio():
    """
    Test the Search API with the audio resource.
    """
    with acmi_api.application.test_client() as client:
        response = client.get(
            '/search/?query=ocean&resource=audio',
            content_type='application/json',
        )
        assert response.status_code == 200
        assert response.json['count'] == 1
        assert response.json['next'] == \
            'http://localhost/search/?query=ocean&resource=audio&page=2'
        assert not response.json['previous']
        assert len(response.json['results']) == 1
        assert response.json['results'][0]['id'] == 15
        assert response.json['results'][0]['work']['labels'][0] == 61958


@patch('elasticsearch.Elasticsearch.search', MagicMock(side_effect=mock_search))
def test_search_api_constellations():
    """
    Test the Search API with the constellations resource.
    """
    with acmi_api.application.test_client() as client:
        response = client.get(
            '/search/?query=pen&resource=constellations',
            content_type='application/json',
        )
        assert response.status_code == 200
        assert response.json['count'] == 5
        assert response.json['next'] == \
            'http://localhost/search/?query=pen&resource=constellations&page=2'
        assert not response.json['previous']
        assert len(response.json['results']) == 5
        assert response.json['results'][0]['id'] == 1
        assert response.json['results'][0]['name'] == 'Pen names, poems and puppets'


@patch('elasticsearch.Elasticsearch.search', MagicMock(side_effect=mock_search))
def test_search_api_creators():
    """
    Test the Search API with the creators resource.
    """
    with acmi_api.application.test_client() as client:
        response = client.get(
            '/search/?query=agnes&resource=creators',
            content_type='application/json',
        )
        assert response.status_code == 200
        assert response.json['count'] == 1
        assert response.json['next'] == \
            'http://localhost/search/?query=agnes&resource=creators&page=2'
        assert not response.json['previous']
        assert len(response.json['results']) == 1
        assert response.json['results'][0]['id'] == 34373
        assert response.json['results'][0]['name'] == 'Agnes Varda'


def test_xos_private_api_retries(tmp_path):
    """
    Test the XOS private API interface retries 3 times before raising an exception.
    """
    with patch('requests.get', MagicMock(side_effect=requests.exceptions.ReadTimeout)) as mock_get:
        acmi_api.JSON_ROOT = tmp_path
        xos_private_api = XOSAPI()
        with pytest.raises(requests.exceptions.ReadTimeout):
            xos_private_api.get('works')
            assert mock_get.call_count == 3


def test_generate_tsv(tmp_path):
    """
    Test the generated TSV is in the correct format with the right number of rows.
    """
    acmi_api.TSV_ROOT = tmp_path
    acmi_api.JSON_ROOT = '/code/tests/data/'
    xos_private_api = XOSAPI()
    xos_private_api.generate_tsv('works')
    assert os.path.isfile(acmi_api.TSV_ROOT / 'works.tsv')
    with open(f'{acmi_api.TSV_ROOT}/works.tsv', encoding='utf-8') as tsv_file:
        reader = csv.reader(tsv_file, delimiter='\t')
        header = next(reader)
        assert len(header) == 49
        assert header[0] == 'id'
        row_count = 0
        for _ in reader:
            row_count += 1
        assert row_count == 4

    xos_private_api.generate_tsv('creators')
    assert os.path.isfile(acmi_api.TSV_ROOT / 'creators.tsv')
    with open(f'{acmi_api.TSV_ROOT}/creators.tsv', encoding='utf-8') as tsv_file:
        reader = csv.reader(tsv_file, delimiter='\t')
        header = next(reader)
        assert len(header) == 15
        assert header[0] == 'id'
        row_count = 0
        for _ in reader:
            row_count += 1
        assert row_count == 1


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


def test_external_references_to_string():
    """
    Test the external_references_to_string method returns the correct data.
    """
    external_references = [
        {
            'source': {
                'name': 'Wikidata',
                'slug': 'wikidata',
            },
            'source_identifier': 'Q101096725',
        },
        {
            'source': {
                'name': 'TMDB-TV',
                'slug': 'tmdb-tv',
            },
            'source_identifier': '95396',
        },
    ]
    string = XOSAPI().external_references_to_string(external_references)
    assert string == '(Wikidata,Q101096725),(TMDB-TV,95396)'
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


def test_suggestions_list_get():
    """Test GET /suggestions/ returns a list of suggestions in reverse order."""
    with acmi_api.application.app_context():
        acmi_api.database.drop_all()
        acmi_api.database.create_all()

        # Add sample suggestions
        suggestion1 = acmi_api.Suggestion(url='http://example.com/1', text='Text 1')
        suggestion2 = acmi_api.Suggestion(url='http://example.com/2', text='Text 2')
        acmi_api.database.session.add(suggestion1)
        acmi_api.database.session.add(suggestion2)
        acmi_api.database.session.commit()

    with acmi_api.application.test_client() as client:
        response = client.get('/suggestions/', content_type='application/json')
        assert response.status_code == 200
        data = response.json
        assert len(data) == 2
        assert data[0]['text'] == 'Text 2'  # Reversed order
        assert data[1]['text'] == 'Text 1'

        # Test with limit parameter
        response = client.get('/suggestions/?limit=1', content_type='application/json')
        assert response.status_code == 200
        data = response.json
        assert len(data) == 1
        assert data[0]['text'] == 'Text 2'


@patch(
    'app.jira.Client.create_or_update',
    return_value={'id': 'jira_id', 'key': 'JIRA-1'},
)
@patch('app.api.JIRA_ENABLED', True)
@patch('app.api.SUGGESTIONS_API_KEYS', ['test_key'])
def test_suggestions_list_post_create(mock_create_or_update):
    """Test POST /suggestions/ creates a new suggestion."""
    headers = {'Authorization': 'Bearer test_key'}
    data = {'url': 'http://example.com/3', 'text': 'Text 3', 'suggestion': 'A new suggestion'}
    with acmi_api.application.test_client() as client:
        response = client.post('/suggestions/', json=data, headers=headers)
        assert response.status_code == 200
        suggestion = response.json
        assert suggestion['url'] == 'http://example.com/3'
        assert suggestion['text'] == 'Text 3'
        assert suggestion['score'] == 0
        assert suggestion['suggestions'] == ['A new suggestion']
        mock_create_or_update.assert_called_once_with(suggestion)


@patch(
    'app.jira.Client.create_or_update',
    return_value={'id': 'jira_id', 'key': 'JIRA-1'},
)
@patch('app.api.JIRA_ENABLED', True)
@patch('app.api.SUGGESTIONS_API_KEYS', ['test_key'])
def test_suggestions_list_post_vote(mock_create_or_update):
    """Test POST /suggestions/ updates score with up/down votes."""
    headers = {'Authorization': 'Bearer test_key'}
    # Vote up
    vote_data = {'url': 'http://example.com/4', 'text': 'Text 4', 'vote': 'up'}
    with acmi_api.application.test_client() as client:
        response = client.post('/suggestions/', json=vote_data, headers=headers)
        assert response.status_code == 200
        updated_suggestion = response.json
        assert updated_suggestion['score'] == 1
        mock_create_or_update.assert_called_once_with(updated_suggestion)

        # Vote down
        vote_data['vote'] = 'down'
        response = client.post('/suggestions/', json=vote_data, headers=headers)
        assert response.status_code == 200
        updated_suggestion = response.json
        assert updated_suggestion['score'] == 0


@patch(
    'app.jira.Client.create_or_update',
    return_value={'id': 'jira_id', 'key': 'JIRA-1'},
)
@patch('app.api.JIRA_ENABLED', True)
@patch('app.api.SUGGESTIONS_API_KEYS', ['test_key'])
def test_suggestions_list_post_add_suggestion(mock_create_or_update):
    """Test POST /suggestions/ adds suggestion text without duplicates."""
    headers = {'Authorization': 'Bearer test_key'}
    with acmi_api.application.test_client() as client:
        # Add suggestion text
        suggestion_data = {
            'url': 'http://example.com/5',
            'text': 'Text 5',
            'suggestion': 'New suggestion',
        }
        response = client.post('/suggestions/', json=suggestion_data, headers=headers)
        assert response.status_code == 200
        updated_suggestion = response.json
        assert updated_suggestion['suggestions'] == ['New suggestion']
        mock_create_or_update.assert_called_once_with(updated_suggestion)

        # Add another suggestion
        suggestion_data['suggestion'] = 'Another suggestion'
        response = client.post('/suggestions/', json=suggestion_data, headers=headers)
        assert response.status_code == 200
        updated_suggestion = response.json
        assert updated_suggestion['suggestions'] == ['New suggestion', 'Another suggestion']

        # Try adding duplicate suggestion
        response = client.post('/suggestions/', json=suggestion_data, headers=headers)
        assert response.status_code == 200
        updated_suggestion = response.json
        assert updated_suggestion['suggestions'] == ['New suggestion', 'Another suggestion']


@patch('app.api.SUGGESTIONS_API_KEYS', ['test_key'])
def test_suggestions_list_post_errors():
    """Test POST /suggestions/ error handling."""
    headers = {'Authorization': 'Bearer test_key'}
    # Missing API key
    data = {'url': 'http://example.com/6', 'text': 'Text 6'}
    with acmi_api.application.test_client() as client:
        response = client.post('/suggestions/', json=data)
        assert response.status_code == 400
        assert response.json['error'] == 'A valid API Key is required'

        # Invalid vote
        data['vote'] = 'sideways'
        response = client.post('/suggestions/', json=data, headers=headers)
        assert response.status_code == 400
        assert response.json['error'] == "Vote must be 'up' or 'down'"

        # Missing url
        data = {'text': 'Text 7'}
        response = client.post('/suggestions/', json=data, headers=headers)
        assert response.status_code == 400
        assert response.json['error'] == 'URL and text fields are required'

        # Missing text
        data = {'url': 'http://example.com/7'}
        response = client.post('/suggestions/', json=data, headers=headers)
        assert response.status_code == 400
        assert response.json['error'] == 'URL and text fields are required'

        # Missing vote or suggestion
        data = {'url': 'http://example.com/7', 'text': 'Text 7'}
        response = client.post('/suggestions/', json=data, headers=headers)
        assert response.status_code == 400
        assert response.json['error'] == 'A vote or a suggestion is required'


def test_suggestion_get():
    """Test GET /suggestions/<id>/ retrieves a single suggestion."""
    with acmi_api.application.app_context():
        suggestion = acmi_api.Suggestion(url='http://example.com/8', text='Text 8')
        acmi_api.database.session.add(suggestion)
        acmi_api.database.session.commit()
        suggestion_id = suggestion.id

    with acmi_api.application.test_client() as client:
        response = client.get(f'/suggestions/{suggestion_id}/', content_type='application/json')
        assert response.status_code == 200
        data = response.json
        assert data['id'] == suggestion_id
        assert data['url'] == 'http://example.com/8'
        assert data['text'] == 'Text 8'

        # Test non-existent suggestion
        response = client.get('/suggestions/999/', content_type='application/json')
        assert response.status_code == 404
        assert response.json['message'] == "That Suggestion doesn't exist, sorry."
