import argparse
from datetime import datetime
import logging
import requests
import time
from functools import reduce
from imageledger import forms, licenses

from django.conf import settings

from elasticsearch import Elasticsearch, helpers, RequestsHttpConnection
from elasticsearch.exceptions import ConnectionError
from aws_requests_auth.aws_auth import AWSRequestsAuth
from elasticsearch_dsl.connections import connections
from elasticsearch_dsl import DocType, String, Date, Nested, Boolean, \
    analyzer, InnerObjectWrapper, Completion, Search, Q

CHUNK_SIZE = 1000

MAX_CONNECTION_RETRIES = 10
RETRY_WAIT = 5  # Number of sections to wait before retrying
TIMEOUT = 30

log = logging.getLogger()

class Results(object):
    """A simple object prototype for collections of results"""

    def __init__(self, page=0, pages=0):
        self.page = page
        self.pages = pages
        self.items = []

class Image(DocType):
    title = String(analyzer="english")
    identifier = String(index="not_analyzed")
    creator = String()
    creator_url = String(index="not_analyzed")
    tags = String(multi=True)
    created_on = Date()
    url = String(index="not_analyzed")
    thumbnail = String(index="not_analyzed")
    provider = String(index="not_analyzed")
    source = String(index="not_analyzed")
    license = String(index="not_analyzed")
    license_version = String()
    foreign_landing_url = String(index="not_analyzed")
    removed_from_source = Boolean()

    class Meta:
        index = settings.ELASTICSEARCH_INDEX

def db_image_to_index(db_image):
    """Map an Image record to a record in the ESL DSL."""
    image = Image(title=db_image.title,
                  creator=db_image.creator,
                  created_on=db_image.created_on,
                  creator_url=db_image.creator_url,
                  identifier=db_image.identifier,
                  url=db_image.url,
                  thumbnail=db_image.thumbnail,
                  provider=db_image.provider,
                  source=db_image.source,
                  license=db_image.license,
                  foreign_landing_url=db_image.foreign_landing_url,
                  removed_from_source=db_image.removed_from_source,
                  _id=db_image.identifier,
                  tags=db_image.tags_list)
    return image

def init_es(timeout=TIMEOUT):
    log.info("connecting to %s %s", settings.ELASTICSEARCH_URL, settings.ELASTICSEARCH_PORT)
    auth = AWSRequestsAuth(aws_access_key=settings.AWS_ACCESS_KEY_ID,
                           aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                           aws_host=settings.ELASTICSEARCH_URL,
                           aws_region='us-west-1',
                           aws_service='es')
    auth.encode = lambda x: bytes(x.encode('utf-8'))
    es = Elasticsearch(host=settings.ELASTICSEARCH_URL,
                       port=settings.ELASTICSEARCH_PORT,
                       connection_class=RequestsHttpConnection,
                       timeout=timeout,
                       max_retries=10, retry_on_timeout=True,
                       http_auth=auth)
    return es

def do_search(request):
    s = Search(index=settings.ELASTICSEARCH_INDEX)
    s = s.extra(track_scores=True)
    form = forms.SearchForm(request.GET)
    results = Results(page=1)

    if form.is_valid():
        if form.cleaned_data.get('search'):
            per_page = int(form.cleaned_data.get('per_page') or forms.RESULTS_PER_PAGE_DEFAULT)
            and_queries = []
            or_queries = []

            # Search fields
            if 'title' in form.cleaned_data.get('search_fields'):
                or_queries.append(Q("query_string",
                                    default_operator="AND",
                                    fields=["title"],
                                    query=form.cleaned_data['search']))
            if 'tags' in form.cleaned_data.get('search_fields'):
                or_queries.append(Q("query_string",
                                    default_operator="AND",
                                    fields=["tags"],
                                    query=form.cleaned_data['search']))
            if 'creator' in form.cleaned_data.get('search_fields'):
                or_queries.append(Q("query_string",
                                    default_operator="AND",
                                    fields=["creator"],
                                    query=form.cleaned_data['search']))

            # Limit to explicit providers first, and then to work providers second, if provided.
            # If provider is supplied, work providers is ignored. TODO revisit this logic as it
            # could be confusing to end users
            work_providers = set()
            if form.cleaned_data.get('work_types'):
                for t in form.cleaned_data.get('work_types'):
                    for p in settings.WORK_TYPES[t]:
                        work_providers.add(p)

            limit_to_providers = form.cleaned_data.get('providers') or work_providers

            for provider in limit_to_providers:
                and_queries.append(
                                Q('bool',
                                should=[Q("term", provider=provider)]
                                ))

            # License limitations
            license_filters = []
            if form.cleaned_data.get('licenses'):
                # If there's a license restriction, unpack the licenses and search for them
                l_groups = form.cleaned_data.get('licenses')
                license_values = []
                for l_group in l_groups:
                    license_values.append([l.lower() for l in licenses.LICENSE_GROUPS[l_group]])
                license_filters = list(reduce(set.intersection, map(set, license_values)))

            for license_filter in license_filters:
                and_queries.append(
                            Q('bool', should=[Q("term", license=license_filter)])
                        )

            if len(or_queries) > 0 or len(and_queries) > 0:
                q = Q('bool',
                      should=or_queries,
                      must=Q('bool',
                             should=and_queries),
                      minimum_should_match=1)

                s = s.query(q)
                response = s.execute()
                results.pages = int(int(response.hits.total) / per_page)
                results.page = form.cleaned_data['page'] or 1
                start = (results.page - 1) * per_page
                end = start + per_page
                for r in s[start:end]:
                    results.items.append(r)

                # We need the providers catalog for the new search result gallery.
                results.providers = settings.PROVIDERS
    else:
        form = forms.SearchForm(initial=forms.SearchForm.initial_data)

    return { 
            "results": results,
            "form": form
        }


def init(timeout=TIMEOUT):
    """Initialize all search objects"""
    es = init_es(timeout=timeout)
    connections.add_connection('default', es)
    log.debug("Initializing search objects for connection %s:%s", settings.ELASTICSEARCH_URL, settings.ELASTICSEARCH_PORT)
    return es
