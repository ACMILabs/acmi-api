from app.api import API


def test_api_root():
    """
    Test the API root returns expected content.
    """
    api = API()
    assert api.get().get('hello') == 'Welcome to the ACMI Public API.'
    assert api.get().get('api') == ['/api/works/', '/api/works/<work_id>/']
