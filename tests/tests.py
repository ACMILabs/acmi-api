import json
import os
from unittest.mock import MagicMock, mock_open, patch

import botocore

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
                with open('tests/data/index_page_2_unpublished.json', 'r') as json_file:
                    return MockResponse(json_file.read(), 200)
            with open('tests/data/index_page_2.json', 'r') as json_file:
                return MockResponse(json_file.read(), 200)
        with open('tests/data/index.json', 'r') as json_file:
            return MockResponse(json_file.read(), 200)
    if kwargs['url'] == 'https://xos.acmi.net.au/api/works/1/':
        with open('tests/data/1.json', 'r') as json_file:
            return MockResponse(json_file.read(), 200)
    if kwargs['url'] == 'https://xos.acmi.net.au/api/works/2/':
        with open('tests/data/2.json', 'r') as json_file:
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
    with open('tests/data/index.json') as json_file:
        return mock_open(read_data=json_file.read())


def mock_work():
    """
    Mocked individual work.json data.
    """
    with open('tests/data/1.json') as json_file:
        return mock_open(read_data=json_file.read())


def mock_file_not_found():
    """
    Mocked file not found.
    """
    mock = mock_open()
    mock.side_effect = FileNotFoundError
    return mock


def test_api_root():
    """
    Test the API root returns expected content.
    """
    api = API()
    assert api.get()['hello'] == 'Welcome to the ACMI Public API.'
    assert api.get()['api'] == ['/works/', '/works/<work_id>/']
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
    with open(acmi_api.JSON_ROOT / 'works/index.json') as index_page_1:
        index_page_1_json = json.load(index_page_1)
        assert index_page_1_json['next'] == 'https://api.acmi.net.au/works/?page=2'
        assert not index_page_1_json['previous']
        assert index_page_1_json['results']
        assert index_page_1_json['count']

    with open(acmi_api.JSON_ROOT / 'works/index_page_2.json') as index_page_2:
        index_page_2_json = json.load(index_page_2)
        assert not index_page_2_json['next']
        assert index_page_2_json['previous'] == 'https://api.acmi.net.au/works/?page=1'
        assert index_page_2_json['results']
        assert index_page_2_json['count']

    with open(acmi_api.JSON_ROOT / 'works/1.json') as work:
        work_json = json.load(work)
        assert work_json['id'] == 1
        assert work_json['description'] == 'Work data returned from the filesystem.'

    with open(acmi_api.JSON_ROOT / 'works/2.json') as work:
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
    with open('tests/data/100542.json') as work:
        work_json = json.load(work)
        xos_private_api = XOSAPI()
        work_json = xos_private_api.update_assets(work_json)
        thumbnail_filename = (
            f'https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/'
            'image/Z000133_Webwurld_Still2_ACMI.tif.1200x1200_q85.jpg'
        )
        assert work_json['thumbnail']['image_url'] == thumbnail_filename
        assert work_json['images'][0]['image_file'] == \
            thumbnail_filename.replace('.1200x1200_q85.jpg', '')
        assert work_json['images'][0]['image_file_l'] == \
            thumbnail_filename.replace('1200x1200', '3840x3840')

    with open('tests/data/111326.json') as video:
        video_json = json.load(video)
        xos_private_api = XOSAPI()
        video_json = xos_private_api.update_assets(video_json)
        thumbnail_filename = (
            f'https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/'
            'video/snapshot_1657_669s.jpg'
        )
        video_filename = (
            f'https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/'
            'video/a_000011_ap01_FiftyYearsOfService.mp4'
        )
        assert video_json['thumbnail']['image_url'] == thumbnail_filename
        assert video_json['videos'][0]['resource'] == video_filename
