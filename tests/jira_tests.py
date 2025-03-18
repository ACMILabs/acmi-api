import json
import os
from unittest.mock import patch
from urllib.parse import urlencode

import requests

from app.jira import Client


def mocked_requests_post(*args, **kwargs):
    """
    Mocked requests.post for create_issue.
    """
    class MockResponse:
        def __init__(self, json_data, status_code):
            self._json_data = json_data
            self.status_code = status_code
            self.headers = {'content-type': 'application/json'}

        def json(self):
            return self._json_data

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError

    if 'rest/api/2/issue' in kwargs.get('url', ''):
        return MockResponse({'id': 'new_issue_id', 'key': 'NEW-1'}, 201)
    return MockResponse(None, 404)


def mocked_requests_get(*args, **kwargs):
    """
    Thanks to https://stackoverflow.com/questions/15753390/how-can-i-mock-requests-and-the-response
    """
    class MockResponse:
        def __init__(
                self,
                filename,
                status_code,
                is_text_file=False,
                content_type='application/json',
        ):
            if filename:
                with open(
                    os.path.join(os.path.dirname(__file__), filename),
                    encoding='utf-8',
                ) as content:
                    if is_text_file:
                        self.content = content.read()
                    else:
                        self.content = json.load(content)
            else:
                self.json_data = None
            self.headers = {'content-type': content_type}
            self.status_code = status_code

        @property
        def text(self):
            return self.content.strip()

        def json(self):
            return self.content

        def raise_for_status(self):
            if self.status_code == 404:
                raise requests.HTTPError

    if kwargs and 'rest/api/2/search' in kwargs.get('url', ''):
        return MockResponse('data/jira_get_issues.json', 200)

    if kwargs and 'rest/api/2/issue' in kwargs.get('url', ''):
        return MockResponse('data/jira_get_issue.json', 204)

    return MockResponse(None, 404)


@patch('requests.get', side_effect=mocked_requests_get)
def test_jira_client(mock_get):
    """
    Test the Jira API client.
    """
    client = Client()
    data = client.get_issues()
    assert len(data['issues']) == 4
    assert data['issues'][0]['fields']['description']
    assert mock_get.call_args[1]['url'].endswith('rest/api/2/search')
    assert mock_get.call_args[1]['params'] == urlencode({
        'jql': 'issuetype="Suggestions"',
        'maxResults': 20,
        'startAt': 0,
    })

    data = client.request('rest/api/2/404')
    assert not data


@patch('app.jira.Client.request')
def test_jira_get_issue(mock_get):
    """
    Test the Jira API client get_issue method.
    """
    client = Client()
    issue_id = '123456'
    assert client.get_issue(issue_id)
    mock_get.assert_called_with(
        url=f'rest/api/2/issue/{issue_id}',
    )


@patch('requests.get', side_effect=mocked_requests_get)
@patch('requests.put', side_effect=mocked_requests_get)
def test_jira_update_issue(mock_put, _):
    """
    Test the Jira API client get_issue method.
    """
    client = Client()
    issue_id = '123456'
    data = {'email': 'research@acmi.net.au'}
    response = client.update_issue(issue_id, data)
    assert response['message'] == f'Updated issue: rest/api/2/issue/{issue_id}'
    assert f'rest/api/2/issue/{issue_id}' in mock_put.call_args[1]['url']
    assert mock_put.call_args[1]['data'] == \
        '{"fields": {"description": "{\\"first_name\\": \\"Simon\\"'\
        ', \\"email\\": \\"research@acmi.net.au\\"}"}}'


@patch('requests.post', side_effect=mocked_requests_post)
def test_create_issue(mock_post):
    """
    Test the create_issue method of the Jira API client.
    """
    client = Client()
    client.project_id = 'TEST'
    data = {'title': 'Test Suggestion', 'description': 'This is a test suggestion'}
    response = client.create_issue(data)
    assert response['id'] == 'new_issue_id'
    assert response['key'] == 'NEW-1'
    assert 'rest/api/2/issue' in mock_post.call_args[1]['url']


@patch('app.jira.Client.create_issue')
@patch('app.jira.Client.update_issue')
@patch('app.jira.Client.get_issues')
def test_create_or_update(mock_get_issues, mock_update_issue, mock_create_issue):
    """
    Test the create_or_update method of the Jira API client.
    """
    client = Client()

    # Case 1: Missing 'url' in data returns None
    data_no_url = {'title': 'No URL Provided'}
    result = client.create_or_update(data_no_url)
    assert result is None

    # Case 2: Data with URL where an existing issue is found (update)
    data_with_url = {'url': 'http://example.com/suggestion', 'title': 'Existing Issue'}
    mock_get_issues.return_value = {'issues': [{'id': 'existing_issue_id'}]}
    mock_update_issue.return_value = {'message': 'Updated issue'}
    result = client.create_or_update(data_with_url)
    mock_update_issue.assert_called_with('existing_issue_id', data_with_url)
    assert result == {'message': 'Updated issue'}

    # Reset the mocks to test the create path.
    mock_update_issue.reset_mock()
    mock_create_issue.reset_mock()

    # Case 3: Data with URL where no existing issue is found (create)
    mock_get_issues.return_value = {'issues': []}
    mock_create_issue.return_value = {'id': 'new_issue_id', 'key': 'NEW-1'}
    result = client.create_or_update(data_with_url)
    mock_create_issue.assert_called_with(data_with_url)
    assert result == {'id': 'new_issue_id', 'key': 'NEW-1'}
