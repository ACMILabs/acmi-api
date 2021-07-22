from unittest.mock import mock_open, patch

import app.api as acmi_api
from app.api import API


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
        assert response.json['next'] == '/works/?page=2'
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
        assert response.json['message'] == 'Works list doesn\'t exist, sorry.'


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
        assert response.json['message'] == 'Work 2 doesn\'t exist, sorry.'
