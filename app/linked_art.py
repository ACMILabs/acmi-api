"""
Linked Art JSON-LD representations of ACMI Public API records.

Transforms Work and Creator JSON into Linked Art 1.0 records as described
at https://linked.art/api/1.0/ and serves them via content negotiation
(Accept: application/ld+json) or the ?format=linked-art query string.
"""

import html
import json
import os
import re

from flask import Response, request

ACMI_API_ENDPOINT = os.getenv('ACMI_API_ENDPOINT', 'https://api.acmi.net.au')
LINKED_ART_CONTEXT = 'https://linked.art/ns/v1/linked-art.json'
LINKED_ART_MEDIA_TYPE = f'application/ld+json;profile="{LINKED_ART_CONTEXT}"'
LINKED_ART_FORMATS = ['linked-art', 'jsonld', 'json-ld']
GETTY_AAT_ENDPOINT = 'http://vocab.getty.edu/aat/'
WIKIDATA_ENTITY_ENDPOINT = 'http://www.wikidata.org/entity/'

# Work types that are physical objects rather than conceptual/visual works.
PHYSICAL_WORK_TYPES = ['Object']

# Creator roles performed by organisations rather than individual people.
ORGANISATION_ROLES = [
    'production company',
    'distributor',
    'production facilities',
    'funding',
    'publisher',
    'support',
    'partner',
]

# Getty AAT concepts for ACMI work types, verified against vocab.getty.edu.
# Music videos have no AAT concept, so use the broader moving images concept.
WORK_TYPE_CONCEPTS = {
    'Film': [('300136900', 'motion pictures (visual works)')],
    'TV show': [('300263432', 'television programs')],
    'Videogame': [('300256888', 'video games')],
    'Website': [('300265431', 'Web sites')],
    'Artwork': [('300133025', 'works of art')],
    'Video': [('300263857', 'moving images')],
    'Music video': [('300263857', 'moving images')],
}

# Getty AAT concepts for ACMI creator roles, verified against vocab.getty.edu.
# Unmapped roles fall back to a human-readable label on the creation event.
ROLE_CONCEPTS = {
    'director': [('300025654', 'directors')],
    'co-director': [('300025654', 'directors')],
    'producer': [('300197742', 'producers')],
    'co-producer': [('300197742', 'producers')],
    'executive producer': [('300197742', 'producers')],
    'producer/director': [('300197742', 'producers'), ('300025654', 'directors')],
    'co-producers/directors': [('300197742', 'producers'), ('300025654', 'directors')],
    'production company': [('300419391', 'production companies')],
    'distributor': [('300404885', 'distributors')],
    'editor': [('300386237', 'film editors')],
    'writer': [('300025515', 'screen writers')],
    'cinematographer': [('300025650', 'cinematographers')],
    'publisher': [('300025574', 'publishers')],
    'photographer': [('300025687', 'photographers')],
    'narrator': [('300417254', 'narrators')],
}


def aat_type(aat_id, label):
    """
    Return a reference to a Getty AAT concept.
    """
    return {
        'id': f'{GETTY_AAT_ENDPOINT}{aat_id}',
        'type': 'Type',
        '_label': label,
    }


def strip_html(text):
    """
    Remove HTML tags and entities, and collapse whitespace in a text field.
    """
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    return re.sub(r'\s+', ' ', text).strip()


def year_of(date_string):
    """
    Return the year from a date string (e.g. 2004 from 2004-01-01T11:00:00+11:00), or None.
    """
    match = re.match(r'(\d{4})', str(date_string or ''))
    return int(match.group(1)) if match else None


def timespan(begin_year, end_year=None):
    """
    Return a Linked Art TimeSpan covering whole years.
    """
    if not end_year:
        end_year = begin_year
    return {
        'type': 'TimeSpan',
        'begin_of_the_begin': f'{begin_year}-01-01T00:00:00Z',
        'end_of_the_end': f'{end_year}-12-31T23:59:59Z',
    }


def requested():
    """
    Returns True if the current request asks for a Linked Art response, either
    via the Accept header or a format= query string argument.
    """
    if request.args.get('format', '').lower() in LINKED_ART_FORMATS:
        return True
    return 'application/ld+json' in request.headers.get('Accept', '')


def linked_art_response(record):
    """
    Serialise a Linked Art record with the JSON-LD media type and profile.
    """
    return Response(
        json.dumps(record, indent=2, ensure_ascii=False),
        content_type=LINKED_ART_MEDIA_TYPE,
    )


def primary_name(content):
    """
    Return a Name classified as a Primary Name.
    """
    return {
        'type': 'Name',
        'classified_as': [aat_type('300404670', 'Primary Name')],
        'content': content,
    }


def statement(content, classification):
    """
    Return a human-readable statement (LinguisticObject) with the given classification.
    """
    return {
        'type': 'LinguisticObject',
        'classified_as': [classification],
        'content': strip_html(content),
    }


def actor_reference(creator_role):
    """
    Return a Person or Group reference for a creator role entry on a Work,
    or None if the creator doesn't have its own API record.
    """
    creator_id = creator_role.get('creator_id')
    if not creator_id:
        return None
    actor_type = 'Group' if creator_role.get('role') in ORGANISATION_ROLES else 'Person'
    return {
        'id': f'{ACMI_API_ENDPOINT}/creators/{creator_id}/',
        'type': actor_type,
        '_label': creator_role.get('name'),
    }


def creation_event(work, event_type):
    """
    Return the Creation/Production event for a Work, or None if there's no
    date, place or creator information to include.
    """
    event = {'type': event_type}

    begin_year = year_of(work.get('first_production_date'))
    end_year = None
    for production_date in work.get('production_dates') or []:
        end_year = year_of(production_date.get('to_year'))
        if end_year:
            break
    if begin_year:
        event['timespan'] = timespan(begin_year, end_year)

    places = []
    for place in work.get('production_places') or []:
        if place.get('id'):
            places.append({
                'id': f'{ACMI_API_ENDPOINT}/places/{place["id"]}/',
                'type': 'Place',
                '_label': place.get('name'),
            })
    if places:
        event['took_place_at'] = places

    parts = []
    creator_roles = (work.get('creators_primary') or []) + (work.get('creators_other') or [])
    for creator_role in creator_roles:
        actor = actor_reference(creator_role)
        if not actor:
            continue
        part = {
            'type': event_type,
            'carried_out_by': [actor],
        }
        role = creator_role.get('role')
        role_concepts = ROLE_CONCEPTS.get(role)
        if role_concepts:
            part['classified_as'] = [aat_type(*concept) for concept in role_concepts]
        elif role:
            part['_label'] = role
        parts.append(part)
    if parts:
        event['part'] = parts

    if len(event) == 1:
        return None
    return event


def work_to_linked_art(work):
    """
    Return the Linked Art representation of an ACMI Work.

    Most ACMI works are moving image works (films, TV shows, videogames),
    which Linked Art models as conceptual VisualItem records; works of
    type Object are physical items, modelled as HumanMadeObject records.
    """
    physical = work.get('type') in PHYSICAL_WORK_TYPES
    record = {
        '@context': LINKED_ART_CONTEXT,
        'id': f'{ACMI_API_ENDPOINT}/works/{work.get("id")}/',
        'type': 'HumanMadeObject' if physical else 'VisualItem',
    }
    if work.get('title'):
        record['_label'] = work['title']

    identifiers = []
    if work.get('title'):
        identifiers.append(primary_name(work['title']))
    if work.get('acmi_id'):
        identifiers.append({
            'type': 'Identifier',
            'classified_as': [aat_type('300312355', 'Accession Number')],
            'content': work['acmi_id'],
        })
    if identifiers:
        record['identified_by'] = identifiers

    work_type_concepts = WORK_TYPE_CONCEPTS.get(work.get('type'))
    if work_type_concepts:
        record['classified_as'] = [aat_type(*concept) for concept in work_type_concepts]

    statements = []
    for field in ['brief_description', 'description']:
        if work.get(field):
            description = statement(work[field], aat_type('300435416', 'Description'))
            if description['content'] and description not in statements:
                statements.append(description)
    if statements:
        record['referred_to_by'] = statements

    event = creation_event(work, 'Production' if physical else 'Creation')
    if event:
        record['produced_by' if physical else 'created_by'] = event

    part_of = work.get('part_of')
    if part_of and part_of.get('id'):
        record['part_of'] = [{
            'id': f'{ACMI_API_ENDPOINT}/works/{part_of["id"]}/',
            'type': record['type'],
            '_label': part_of.get('title'),
        }]

    return record


def creator_type(creator):
    """
    Returns Person or Group for a Creator record. Birth, death and gender
    data only exist for people; failing that, creators whose roles are all
    organisational (e.g. production company) are treated as a Group.
    """
    if creator.get('date_of_birth') or creator.get('date_of_death') or creator.get('genders'):
        return 'Person'
    roles = {role.get('role') for role in creator.get('roles_in_work') or []}
    if roles and all(role in ORGANISATION_ROLES for role in roles):
        return 'Group'
    return 'Person'


def creator_to_linked_art(creator):
    """
    Return the Linked Art representation of an ACMI Creator.
    """
    record = {
        '@context': LINKED_ART_CONTEXT,
        'id': f'{ACMI_API_ENDPOINT}/creators/{creator.get("id")}/',
        'type': creator_type(creator),
    }
    if creator.get('name'):
        record['_label'] = creator['name']

    identifiers = []
    if creator.get('name'):
        identifiers.append(primary_name(creator['name']))
    if creator.get('also_known_as'):
        identifiers.append({
            'type': 'Name',
            'content': creator['also_known_as'],
        })
    if identifiers:
        record['identified_by'] = identifiers

    if creator.get('biography'):
        biography = statement(creator['biography'], aat_type('300435422', 'Biography Statement'))
        if biography['content']:
            record['referred_to_by'] = [biography]

    if record['type'] == 'Person':
        if creator.get('date_of_birth'):
            record['born'] = {
                'type': 'Birth',
                'timespan': day_timespan(creator['date_of_birth']),
            }
        if creator.get('date_of_death'):
            record['died'] = {
                'type': 'Death',
                'timespan': day_timespan(creator['date_of_death']),
            }

    equivalents = []
    for reference in creator.get('external_references') or []:
        source = reference.get('source') or {}
        if source.get('slug') == 'wikidata' and reference.get('source_identifier'):
            equivalents.append({
                'id': f'{WIKIDATA_ENTITY_ENDPOINT}{reference["source_identifier"]}',
                'type': record['type'],
                '_label': creator.get('name'),
            })
    if equivalents:
        record['equivalent'] = equivalents

    return record


def day_timespan(date_string):
    """
    Return a Linked Art TimeSpan covering a single day (e.g. a date of birth).
    """
    return {
        'type': 'TimeSpan',
        'begin_of_the_begin': f'{date_string}T00:00:00Z',
        'end_of_the_end': f'{date_string}T23:59:59Z',
    }
