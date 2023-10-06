#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

'''
  Description:
    This script interates through all Ansible Collections which are available from the Ansible Automation 
    Hub (console.redhat.com) in both the validated content and the certified content and prints out those
    collections which have been updated or released within the asked timespan (through --timedelta <days>).

    It provides rudimentary options via a config.yml to only show updates on certain collections, repositories
    and namespaces
'''

import requests
import logging
import sys
import os
import yaml
from enum import Enum
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from argparse import ArgumentParser
from getpass import getpass
from pprint import pformat

__author__ = 'Steffen Scheib'
__copyright__ = 'Copyright 2023, Steffen Scheib'
__credits__ = ['Steffen Scheib']
__license__ = 'GPLv2 or later'
__version__ = '0.2'
__maintainer__ = 'Steffen Scheib'
__email__ = 'steffen@scheib.me'
__status__ = 'Development'

LOG = logging.getLogger(os.path.basename(os.path.splitext(__file__)[0]))
API_URL = 'https://console.redhat.com'
API_USERNAME = ''
API_PASSWORD = ''

class HttpRequestType(Enum):
    '''Representation of the different HTTP request types'''
    GET = 1
    POST = 2
    PUT = 3
    DELETE = 4


def query_api(http_request_type: HttpRequestType, location: str, data: str = None) -> dict:
  """Queries the API
  Queries the Automation Hub API and returns the result as JSON formatted string.
  HTTP types supported are: GET, POST, PUT, DELETE.

  Args:
      http_request_type (str): The HTTP request type to use. Supported are GET, POST, PUT, DELETE
      location (str): Location to query (Example: content_views/1)
      data (str, optional): The optional payload to deliver with the HTTP request

  Returns:
      dict: The resulting response from the HTTP requests as JSON formatted string (=dict)

  Raises:
      ValueError: If the first argument is None or not given
      TypeError: If the first argument is not an instance of HttpRequestType
      ValueError: If the second argument is None or not given
      TypeError: If the second argument is not an instance of ApiType
      TypeError: If the optional third argument is given, but is not a string
      ValueError: If the optional third argument is given, but is not a JSON formatted string
      ValueError: If the given HTTP request type is not supported
      HTTPError: If the request returns with an unsuccessful status code
      ConnectionError: If a connection to the  API cannot be established (DNS failure, connection
                       refused, etc)
      Timeout: If the request exceeds the maximum time in which it didn't receive any data
      RequestException: If the HTTP request fails for another reason
      RuntimeError: If the HTTP request fails for some reason
  """
  # check existence and type of the first argument
  if not http_request_type or http_request_type is None:
      raise ValueError(f'Given value for the first argument (\'http_request_type\') is empty (or None).')
  elif not isinstance(http_request_type, HttpRequestType):
      raise TypeError(f'Given value for the first argument (\'http_request_type\') is not an instance '
                      f'of HttpRequestType. Type of value is {type(http_request_type)}.')

  # check existence and type of the second argument
  if not location or location is None:
      raise ValueError(f'Given value for the second argument (\'location\') is empty (or None).')
  elif not isinstance(location, str):
      raise TypeError(f'Given value for the second argument (\'location\') is not a string. Type of value '
                      f'is {type(location)}.')

  if data is not None:
    LOG.debug(f'Using HTTP {http_request_type.name} on {API_URL + location} payload {pformat(data)}')
  else:
    LOG.debug(f'Using HTTP {http_request_type.name} on {API_URL + location}')


  # do the HTTP request
  auth = (API_USERNAME, API_PASSWORD)
  try:
      if http_request_type is HttpRequestType.GET:
          response = requests.get(API_URL + location,
                                  data=data,
                                  auth=auth,
                                  headers={'content-type': 'application/json'})
      elif http_request_type is HttpRequestType.POST:
          response = requests.post(API_URL + location,
                                   data=data,
                                   auth=auth,
                                   headers={'content-type': 'application/json'})
      elif http_request_type is HttpRequestType.PUT:
          response = requests.put(API_URL + location,
                                  data=data,
                                  auth=auth,
                                  headers={'content-type': 'application/json'})
      elif http_request_type is HttpRequestType.DELETE:
          response = requests.delete(API_URL + location,
                                     data=data,
                                     auth=auth,
                                     headers={'content-type': 'application/json'})
      else:
          raise ValueError(f'Given HTTP request type is not supported! Given is {http_request_type.name}.')

      return response.json()
      response.raise_for_status()
  except requests.exceptions.HTTPError as http_error:
      raise requests.exceptions.HTTPError(f'The HTTP {http_request_type.name} request failed with an HTTPError. '
                                          f'Following the complete error:'
                                          f' {http_error}')
  except requests.exceptions.ConnectionError as connection_error:
      raise requests.exceptions.ConnectionError(f'Unable to connect to the configured API {API_URL}. '
                                                f'Following the complete error: '
                                                f'{connection_error}')
  except requests.exceptions.ReadTimeout as read_timeout_error:
      raise requests.exceptions.ReadTimeout(f'The HTTP {http_request_type.name} request timed out.' 
                                            f'Following the complete error: {read_timeout_error}')
  except requests.exceptions.Timeout as timeout_error:
      raise requests.exceptions.Timeout(f'Timeout of the HTTP {http_request_type.name} request has been reached. '
                                        f'Following the complete error: '
                                        f'{timeout_error}')
  except requests.exceptions.RequestException as request_exception:
      raise requests.exceptions.RequestException(f'The HTTP {http_request_type.name} request failed. Following '
                                                 f'the complete error: '
                                                 f'{request_exception}')

  if not response.ok:
      raise RuntimeError(f'Last {http_request_type.name} request failed. Request returned with '
                         f'HTTP code {response.status_code}')

  # return the response as JSON
  return response.json()

parser = ArgumentParser()
parser.add_argument('--api-url', dest='api_url',
                    help='The base URL of the API',
                    default='https://console.redhat.com', required=False)
parser.add_argument('--api-username', dest='api_username',
                    help='Username to authenticate against the API',
                    required=True)
parser.add_argument('--api-password', dest='api_password',
                    help='Password for the user to authenticate against the API',
                    required=False)
parser.add_argument('--timedelta', dest='timedelta', required=False, default='7',
                    help='Days from today to report updated collections on', type=int)
parser.add_argument('--config-file', dest='config_file', required=False, default='config.yml',
                    help='Configuration file to load', type=str)
args = parser.parse_args()


# set the log level
LOG.setLevel(logging.INFO)

# create console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('[%(asctime)s] %(name)-12s %(levelname)-8s: %(funcName)-50s: %(message)s')
console_handler.setFormatter(console_formatter)
LOG.addHandler(console_handler)


if os.path.isfile(args.config_file):
  with open(args.config_file, 'r') as config:
    cfg = yaml.safe_load(config)
else:
  LOG.info(f'Configuration file {args.config_file} not found, not using any configuration file')
  cfg = None

API_URL = args.api_url
API_USERNAME = args.api_username
if args.api_password:
    API_PASSWORD = args.api_password
else:
    API_PASSWORD = getpass(f'Password for user {API_USERNAME}: ')

# set the initial href for each repository type
hrefs = {
  'validated': '/api/automation-hub/v3/plugin/ansible/content/validated/collections/index/?limit=100',
  'certified': '/api/automation-hub/v3/plugin/ansible/content/published/collections/index/?limit=100'
}

# iterate over all repositories
for collection_repo, initial_href in hrefs.items():
    # continue if config does not include the currently processed collection_repo (when given)
    if cfg \
        and 'repositories' in cfg \
        and cfg['repositories'] \
        and collection_repo not in cfg['repositories']:
        continue

    href = initial_href
    collections = list()
    while True:
        result = query_api(HttpRequestType.GET, href)

        # iterate over each collection
        for collection in result['data']:
            collection_name = collection['name']
            collection_namespace = collection['namespace']
            collection_fqcn = f'{collection_namespace}.{collection_name}'

            # skip irrelevant collections
            if cfg \
                and 'collections' in cfg \
                and cfg['collections'] \
                and collection_name not in cfg['collections'] \
                and collection_fqcn not in cfg['collections']:
                continue

            # skip irrelevant namespaces
            if cfg \
                and 'namespaces' in cfg \
                and cfg['namespaces'] \
                and collection_namespace not in cfg['namespaces']:
                continue

            # show only collection updates that are in the given time frame
            if datetime.strptime(collection['updated_at'], '%Y-%m-%dT%H:%M:%S.%fZ') <= datetime.now() - timedelta(days=args.timedelta):
                continue
            
            highest_version = collection['highest_version']
            print(f"{collection_repo}: {collection_namespace}.{collection_name} has new version {collection['highest_version']['version']} released on {collection['updated_at']}")

        # we are done once no next link is given
        if result['links']['next'] is None:
            break

        # assign new href
        href = result['links']['next']

sys.exit(0)
