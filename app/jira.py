"""
Jira integration.

From Website2020
https://github.com/ACMILabs/website2020/blob/development/backend/acmi/jira/client.py
"""

import json
import os
from urllib.parse import urlencode, urljoin

import requests
from requests.auth import HTTPBasicAuth


class Client:
    """Client for sending data to Jira."""

    def __init__(self):
        """Initialise arguments."""
        self.server = os.getenv('JIRA_API_URL')
        self.username = os.getenv('JIRA_USERNAME')
        self.token = os.getenv('JIRA_TOKEN')
        self.project_id = os.getenv('JIRA_PROJECT_ID')
        self.issue_type = 'Suggestions'

    def request(self, url, data=None, method=None, params=None):
        """Send a request to the Jira API.

        :param url: str - URL to post to
        :param data: dict - data to post
        :param method: str - get or post method
        :param params: dict - params to add to the request
        :return: json response from Jira
        :rtype: dict
        """
        try:
            if not method:
                method = 'get'
            auth = HTTPBasicAuth(self.username, self.token)
            if data:
                data = json.dumps(data)
            headers = {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
            }
            full_url = urljoin(self.server, url)
            response = getattr(requests, method)(
                url=full_url,
                auth=auth,
                data=data,
                headers=headers,
                params=params,
            )
            response.raise_for_status()
        except (
                requests.exceptions.HTTPError,
                requests.exceptions.Timeout,
                requests.exceptions.ConnectionError) as exception:
            print(f'Error: {exception}')
            return None
        if method == 'put' and response.status_code == 204:
            # Jira API doesn't return any JSON for a successful update
            return {'message': f'Updated issue: {url}'}
        return response.json()

    def get_issues(self, page=1, per_page=20, query=None):
        """
        Get all Jira issues.

        :rtype: dict
        """
        page = max(page, 1)
        params = {
            'jql': f'issuetype="{self.issue_type}"',
            'maxResults': per_page,
            'startAt': (page - 1) * per_page,
        }
        if query:
            params['jql'] = f'{params["jql"]} AND description~"{query}"'
        return self.request(url='rest/api/2/search', params=urlencode(params))

    def get_issue(self, issue_id):
        """
        Get a Jira issue.

        :param issue_id: int - Jira Issue ID
        :rtype: dict
        """
        return self.request(url=f'rest/api/2/issue/{issue_id}')

    def update_issue(self, issue_id, data):
        """
        Update a Jira issue with new data.

        :param issue_id: int - Jira Issue ID
        :param data: dict - JSON data to save to the Jira issue
        :rtype: dict
        """
        jira_issue = self.get_issue(issue_id)
        description = json.loads(jira_issue['fields']['description'])
        description.update(data)
        payload = {
            'fields': {
                'description': json.dumps(description),
            },
        }
        return self.request(url=f'rest/api/2/issue/{issue_id}', method='put', data=payload)

    def create_issue(self, data):
        """Create a Jira issue."""
        issue_dict = {
            'fields': {
                'project': {'key': self.project_id},
                'summary': "ACMI suggestion",
                'description': json.dumps(data, indent=4),
                'issuetype': {'name': self.issue_type},
            },
        }
        return self.request(url='rest/api/2/issue', method='post', data=issue_dict)

    def create_or_update(self, data):
        """
        Create or update a Jira issue by its data, unique by the suggestion URL.
        """
        if not data.get('url'):
            return None
        response = self.get_issues(query=data.get('url'))
        if response and response.get('issues'):
            return self.update_issue(response.get('issues')[0]['id'], data)
        return self.create_issue(data)
