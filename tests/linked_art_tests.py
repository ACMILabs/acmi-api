import json
from unittest.mock import mock_open, patch

import app.api as acmi_api
from app import linked_art


def load_json(file_path):
    """
    Load JSON test data from the filesystem.
    """
    with open(file_path, 'rb') as json_file:
        return json.load(json_file)


def mock_work():
    """
    Mocked individual Work json data.
    """
    with open('tests/data/linked_art_work.json', 'rb') as json_file:
        return mock_open(read_data=json_file.read())


def mock_creator():
    """
    Mocked individual Creator json data.
    """
    with open('tests/data/creator_34373.json', 'rb') as json_file:
        return mock_open(read_data=json_file.read())


def test_work_to_linked_art():
    """
    Test a Work is transformed to a valid Linked Art VisualItem record.
    """
    work = load_json('tests/data/linked_art_work.json')
    record = linked_art.work_to_linked_art(work)

    assert record['@context'] == 'https://linked.art/ns/v1/linked-art.json'
    assert record['id'] == 'https://api.acmi.net.au/works/116936/'
    assert record['type'] == 'VisualItem'
    assert record['_label'] == 'Love My Way: Only Mortal'

    names = [item for item in record['identified_by'] if item['type'] == 'Name']
    identifiers = [item for item in record['identified_by'] if item['type'] == 'Identifier']
    assert names[0]['content'] == 'Love My Way: Only Mortal'
    assert names[0]['classified_as'][0]['id'] == 'http://vocab.getty.edu/aat/300404670'
    assert identifiers[0]['content'] == 'B2001950'
    assert identifiers[0]['classified_as'][0]['id'] == 'http://vocab.getty.edu/aat/300312355'

    assert record['classified_as'][0]['id'] == 'http://vocab.getty.edu/aat/300263432'
    assert record['classified_as'][0]['_label'] == 'television programs'

    description = record['referred_to_by'][0]
    assert description['type'] == 'LinguisticObject'
    assert description['classified_as'][0]['id'] == 'http://vocab.getty.edu/aat/300435416'
    assert '<p>' not in description['content']
    assert '&#8216;' not in description['content']
    assert description['content'].startswith('The groundbreaking')
    assert '‘Love My Way’' in description['content']


def test_work_to_linked_art_creation():
    """
    Test the Creation event of a Linked Art Work record.
    """
    work = load_json('tests/data/linked_art_work.json')
    creation = linked_art.work_to_linked_art(work)['created_by']

    assert creation['type'] == 'Creation'
    assert creation['timespan']['begin_of_the_begin'] == '2004-01-01T00:00:00Z'
    assert creation['timespan']['end_of_the_end'] == '2005-12-31T23:59:59Z'
    assert creation['took_place_at'][0]['id'] == 'https://api.acmi.net.au/places/3/'
    assert creation['took_place_at'][0]['_label'] == 'Australia'

    assert len(creation['part']) == 2, 'Creators without their own API record should be skipped'
    director, production_company = creation['part']
    assert director['carried_out_by'][0]['id'] == 'https://api.acmi.net.au/creators/83676/'
    assert director['carried_out_by'][0]['type'] == 'Person'
    assert director['classified_as'][0]['id'] == 'http://vocab.getty.edu/aat/300025654'
    assert production_company['carried_out_by'][0]['type'] == 'Group'
    assert production_company['classified_as'][0]['id'] == 'http://vocab.getty.edu/aat/300419391'


def test_physical_work_to_linked_art():
    """
    Test Works of type Object become HumanMadeObject records with a Production event.
    """
    work = {
        'id': 1,
        'title': 'Bell & Howell Filmo camera',
        'type': 'Object',
        'first_production_date': '1923-01-01T00:00:00+11:00',
        'creators_primary': [
            {'name': 'Bell & Howell', 'creator_id': 2, 'role': 'production company'},
        ],
    }
    record = linked_art.work_to_linked_art(work)
    assert record['type'] == 'HumanMadeObject'
    assert 'created_by' not in record
    assert record['produced_by']['type'] == 'Production'
    assert record['produced_by']['part'][0]['type'] == 'Production'


def test_work_part_of():
    """
    Test a Work that is part of another Work links to its parent.
    """
    work = {
        'id': 2,
        'title': 'Episode one',
        'type': 'TV show',
        'part_of': {'id': 3, 'title': 'The series'},
    }
    record = linked_art.work_to_linked_art(work)
    assert record['part_of'][0]['id'] == 'https://api.acmi.net.au/works/3/'
    assert record['part_of'][0]['type'] == 'VisualItem'
    assert record['part_of'][0]['_label'] == 'The series'


def test_minimal_work_to_linked_art():
    """
    Test a Work with minimal data still produces a valid record.
    """
    record = linked_art.work_to_linked_art({'id': 1})
    assert record['@context'] == 'https://linked.art/ns/v1/linked-art.json'
    assert record['id'] == 'https://api.acmi.net.au/works/1/'
    assert record['type'] == 'VisualItem'
    optional_keys = [
        '_label', 'identified_by', 'classified_as', 'referred_to_by', 'created_by', 'part_of',
    ]
    for key in optional_keys:
        assert key not in record


def test_creator_to_linked_art():
    """
    Test a Creator is transformed to a valid Linked Art Person record.
    """
    creator = load_json('tests/data/creator_34373.json')
    record = linked_art.creator_to_linked_art(creator)

    assert record['@context'] == 'https://linked.art/ns/v1/linked-art.json'
    assert record['id'] == 'https://api.acmi.net.au/creators/34373/'
    assert record['type'] == 'Person'
    assert record['_label'] == 'Agnes Varda'

    primary_name, alternate_name = record['identified_by']
    assert primary_name['content'] == 'Agnes Varda'
    assert primary_name['classified_as'][0]['id'] == 'http://vocab.getty.edu/aat/300404670'
    assert alternate_name['content'] == 'Arlette Varda'

    biography = record['referred_to_by'][0]
    assert biography['classified_as'][0]['id'] == 'http://vocab.getty.edu/aat/300435422'
    assert record['born']['timespan']['begin_of_the_begin'] == '1928-05-30T00:00:00Z'
    assert record['died']['timespan']['begin_of_the_begin'] == '2019-03-29T00:00:00Z'
    assert record['equivalent'][0]['id'] == 'http://www.wikidata.org/entity/Q229990'
    assert record['equivalent'][0]['type'] == 'Person'


def test_organisation_to_linked_art():
    """
    Test a Creator whose roles are all organisational becomes a Group record.
    """
    creator = {
        'id': 83675,
        'name': 'Foxtel',
        'date_of_birth': None,
        'genders': [],
        'roles_in_work': [
            {'role': 'production company'},
            {'role': 'distributor'},
        ],
    }
    record = linked_art.creator_to_linked_art(creator)
    assert record['type'] == 'Group'
    assert 'born' not in record
    assert 'died' not in record


def test_creator_type_defaults_to_person():
    """
    Test Creators without birth, death, gender or organisational role data become a Person.
    """
    assert linked_art.creator_type({'roles_in_work': [{'role': 'director'}]}) == 'Person'
    assert linked_art.creator_type({}) == 'Person'


@patch('builtins.open', mock_work())
def test_work_api_linked_art_format():
    """
    Test the Work API returns Linked Art JSON-LD for the format= argument.
    """
    with acmi_api.application.test_client() as client:
        response = client.get('/works/116936/?format=linked-art')
        assert response.status_code == 200
        assert response.content_type == linked_art.LINKED_ART_MEDIA_TYPE
        assert response.json['@context'] == 'https://linked.art/ns/v1/linked-art.json'
        assert response.json['type'] == 'VisualItem'


@patch('builtins.open', mock_work())
def test_work_api_linked_art_accept_header():
    """
    Test the Work API returns Linked Art JSON-LD via content negotiation.
    """
    with acmi_api.application.test_client() as client:
        response = client.get(
            '/works/116936/',
            headers={'Accept': linked_art.LINKED_ART_MEDIA_TYPE},
        )
        assert response.status_code == 200
        assert response.content_type == linked_art.LINKED_ART_MEDIA_TYPE
        assert response.json['id'] == 'https://api.acmi.net.au/works/116936/'


@patch('builtins.open', mock_work())
def test_work_api_default_format_unchanged():
    """
    Test the Work API still returns ACMI JSON by default.
    """
    with acmi_api.application.test_client() as client:
        response = client.get('/works/116936/', content_type='application/json')
        assert response.status_code == 200
        assert response.content_type == 'application/json'
        assert '@context' not in response.json
        assert response.json['acmi_id'] == 'B2001950'


@patch('builtins.open', mock_creator())
def test_creator_api_linked_art_format():
    """
    Test the Creator API returns Linked Art JSON-LD for the format= argument.
    """
    with acmi_api.application.test_client() as client:
        response = client.get('/creators/34373/?format=linked-art')
        assert response.status_code == 200
        assert response.content_type == linked_art.LINKED_ART_MEDIA_TYPE
        assert response.json['type'] == 'Person'
        assert response.json['_label'] == 'Agnes Varda'


@patch('builtins.open', mock_work())
def test_cors_header():
    """
    Test responses include the open CORS header required by Linked Art.
    """
    with acmi_api.application.test_client() as client:
        response = client.get('/works/116936/')
        assert response.headers['Access-Control-Allow-Origin'] == '*'
