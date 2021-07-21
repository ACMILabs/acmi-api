import app.api as acmi_api
from app.api import API


def test_api_root():
    """
    Test the API root returns expected content.
    """
    api = API()
    assert api.get()['hello'] == 'Welcome to the ACMI Public API.'
    assert api.get()['api'] == ['/works/', '/works/<work_id>/']


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
        response = client.get(
            '/works/?page=999999',
            content_type='application/json',
        )
        assert response.status_code == 404
        assert response.json['message'] == 'Works list doesn\'t exist, sorry.'


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
        response = client.get(
            '/works/2/',
            content_type='application/json',
        )
        assert response.status_code == 404
        assert response.json['message'] == 'Work 2 doesn\'t exist, sorry.'
