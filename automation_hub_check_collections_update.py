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
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

__author__ = 'Steffen Scheib'
__copyright__ = 'Copyright 2026, Steffen Scheib'
__credits__ = ['Steffen Scheib']
__license__ = 'GPLv2 or later'
__version__ = '0.3.0'
__maintainer__ = 'Steffen Scheib'
__email__ = 'steffen@scheib.me'
__status__ = 'Development'

LOG = logging.getLogger(os.path.basename(os.path.splitext(__file__)[0]))
API_URL = 'https://console.redhat.com'
SSO_TOKEN_URL = 'https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token'
SSO_SCOPE = 'api.console'
CLIENT_ID = ''
CLIENT_SECRET = ''
ACCESS_TOKEN = ''
ACCESS_TOKEN_EXPIRES_AT = None
HTTP_SESSION = None
CONNECT_TIMEOUT = 30
READ_TIMEOUT = 60

class HttpRequestType(Enum):
    '''Representation of the different HTTP request types'''
    GET = 1
    POST = 2
    PUT = 3
    DELETE = 4


def create_http_session(proxy: str = None) -> requests.Session:
  '''Create a shared HTTP session with retries and optional proxy settings.'''
  session = requests.Session()
  retry = Retry(
      total=3,
      connect=3,
      read=3,
      backoff_factor=1,
      status_forcelist=[429, 500, 502, 503, 504],
      allowed_methods=['GET', 'POST', 'PUT', 'DELETE'],
      raise_on_status=False,
  )
  adapter = HTTPAdapter(max_retries=retry)
  session.mount('https://', adapter)
  session.mount('http://', adapter)

  if proxy:
      session.proxies.update({'http': proxy, 'https': proxy})

  return session


def request_timeout() -> tuple:
  '''Return connect/read timeout tuple for HTTP requests.'''
  return (CONNECT_TIMEOUT, READ_TIMEOUT)


def handle_request_exception(http_request_type: HttpRequestType, request_exception: Exception) -> None:
  '''Convert request exceptions into clearer, actionable errors.'''
  if isinstance(request_exception, requests.exceptions.ConnectTimeout):
      raise requests.exceptions.ConnectTimeout(
          f'Connection to {API_URL} timed out after {CONNECT_TIMEOUT}s while performing '
          f'HTTP {http_request_type.name}. Authentication with Red Hat SSO succeeded, so this '
          f'is a network connectivity issue. {NETWORK_ERROR_HINT}'
      ) from request_exception

  if isinstance(request_exception, requests.exceptions.ConnectionError):
      raise requests.exceptions.ConnectionError(
          f'Unable to connect to {API_URL} while performing HTTP {http_request_type.name}. '
          f'{NETWORK_ERROR_HINT} Original error: {request_exception}'
      ) from request_exception

  if isinstance(request_exception, requests.exceptions.ReadTimeout):
      raise requests.exceptions.ReadTimeout(
          f'The HTTP {http_request_type.name} request to {API_URL} timed out after '
          f'{READ_TIMEOUT}s. Original error: {request_exception}'
      ) from request_exception

  if isinstance(request_exception, requests.exceptions.Timeout):
      raise requests.exceptions.Timeout(
          f'Timeout of the HTTP {http_request_type.name} request to {API_URL} has been reached. '
          f'Original error: {request_exception}'
      ) from request_exception

  if isinstance(request_exception, requests.exceptions.HTTPError):
      raise requests.exceptions.HTTPError(
          f'The HTTP {http_request_type.name} request to {API_URL} failed with an HTTPError. '
          f'Original error: {request_exception}'
      ) from request_exception

  raise requests.exceptions.RequestException(
      f'The HTTP {http_request_type.name} request to {API_URL} failed. '
      f'Original error: {request_exception}'
  ) from request_exception


def perform_api_request(http_request_type: HttpRequestType, url: str, headers: dict, data: str = None):
  '''Execute one HTTP request against the Automation Hub API.'''
  request_kwargs = {
      'headers': headers,
      'timeout': request_timeout(),
  }
  if data is not None:
      request_kwargs['data'] = data

  if http_request_type is HttpRequestType.GET:
      return HTTP_SESSION.get(url, **request_kwargs)
  if http_request_type is HttpRequestType.POST:
      return HTTP_SESSION.post(url, **request_kwargs)
  if http_request_type is HttpRequestType.PUT:
      return HTTP_SESSION.put(url, **request_kwargs)
  if http_request_type is HttpRequestType.DELETE:
      return HTTP_SESSION.delete(url, **request_kwargs)

  raise ValueError(f'Given HTTP request type is not supported! Given is {http_request_type.name}.')


def get_access_token(force_refresh: bool = False) -> str:
  '''
  Obtain or refresh a Red Hat SSO access token for service account authentication.

  Tokens expire after 15 minutes. This function caches the token and refreshes it
  automatically when it is missing or about to expire

  Returns:
      str: A valid OAuth access token.

  Raises:
      ValueError: If service account credentials are not configured.
      HTTPError: If the token request fails.
      RequestException: If the token request fails for another reason.
  '''
  global ACCESS_TOKEN, ACCESS_TOKEN_EXPIRES_AT

  if not CLIENT_ID or not CLIENT_SECRET:
      raise ValueError('Service account client ID and client secret must be configured')

  if not force_refresh and ACCESS_TOKEN and ACCESS_TOKEN_EXPIRES_AT:
      if datetime.now() < ACCESS_TOKEN_EXPIRES_AT - timedelta(seconds=60):
          return ACCESS_TOKEN

  LOG.debug('Requesting a new access token from Red Hat SSO')
  try:
      response = HTTP_SESSION.post(
          SSO_TOKEN_URL,
          data={
              'grant_type': 'client_credentials',
              'client_id': CLIENT_ID,
              'client_secret': CLIENT_SECRET,
              'scope': SSO_SCOPE,
          },
          headers={'content-type': 'application/x-www-form-urlencoded'},
          timeout=request_timeout(),
      )
      response.raise_for_status()
      token_data = response.json()
  except requests.exceptions.HTTPError as http_error:
      raise requests.exceptions.HTTPError(
          f'Failed to obtain access token from Red Hat SSO, complete error: {http_error}'
      ) from http_error
  except requests.exceptions.ConnectTimeout as connect_timeout_error:
      raise requests.exceptions.ConnectTimeout(
          f'Connection to Red Hat SSO timed out after {CONNECT_TIMEOUT}s. {NETWORK_ERROR_HINT}'
      ) from connect_timeout_error
  except requests.exceptions.RequestException as request_exception:
      raise requests.exceptions.RequestException(
          f'Failed to obtain access token from Red Hat SSO, complete error: {request_exception}'
      ) from request_exception

  if 'access_token' not in token_data:
      raise RuntimeError(
          f'Red Hat SSO token response did not contain an access token: {pformat(token_data)}'
      )

  ACCESS_TOKEN = token_data['access_token']
  expires_in = token_data.get('expires_in', 900)
  ACCESS_TOKEN_EXPIRES_AT = datetime.now() + timedelta(seconds=int(expires_in))
  return ACCESS_TOKEN


def query_api(http_request_type: HttpRequestType, location: str, data: str = None) -> dict:
  '''
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
  '''
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
  headers = {
      'content-type': 'application/json',
      'Authorization': f'Bearer {get_access_token()}',
  }
  url = API_URL + location
  try:
      response = perform_api_request(http_request_type, url, headers, data)

      if response.status_code == 401:
          headers['Authorization'] = f'Bearer {get_access_token(force_refresh=True)}'
          response = perform_api_request(http_request_type, url, headers, data)

      response.raise_for_status()
  except requests.exceptions.RequestException as request_exception:
      handle_request_exception(http_request_type, request_exception)

  if not response.ok:
      raise RuntimeError(f'Last {http_request_type.name} request failed. Request returned with '
                         f'HTTP code {response.status_code}')

  # return the response as JSON
  return response.json()

parser = ArgumentParser()
parser.add_argument('--api-url', dest='api_url',
                    help='The base URL of the API',
                    default='https://console.redhat.com', required=False)
parser.add_argument('--client-id', dest='client_id',
                    help='Service account client ID (or set REDHAT_CLIENT_ID)',
                    default=os.environ.get('REDHAT_CLIENT_ID'),
                    required=False)
parser.add_argument('--client-secret', dest='client_secret',
                    help='Service account client secret (or set REDHAT_CLIENT_SECRET)',
                    default=os.environ.get('REDHAT_CLIENT_SECRET'),
                    required=False)
parser.add_argument('--timedelta', dest='timedelta', required=False, default='7',
                    help='Days from today to report updated collections on', type=int)
parser.add_argument('--config-file', dest='config_file', required=False, default='config.yml',
                    help='Configuration file to load', type=str)
parser.add_argument('--connect-timeout', dest='connect_timeout', required=False, default=30, type=int,
                    help='Seconds to wait while establishing a connection')
parser.add_argument('--read-timeout', dest='read_timeout', required=False, default=60, type=int,
                    help='Seconds to wait for an API response after connecting')
parser.add_argument('--proxy', dest='proxy', required=False,
                    default=os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy'),
                    help='HTTPS proxy URL (or set HTTPS_PROXY)')
parser.add_argument('--verbose', dest='verbose', action='store_true',
                    help='Enable debug logging')
args = parser.parse_args()


# set the log level
LOG.setLevel(logging.DEBUG if args.verbose else logging.INFO)

# create console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG if args.verbose else logging.INFO)
console_formatter = logging.Formatter('[%(asctime)s] %(name)-12s %(levelname)-8s: %(funcName)-50s: %(message)s')
console_handler.setFormatter(console_formatter)
LOG.addHandler(console_handler)

if os.path.isfile(args.config_file):
  with open(args.config_file, 'r') as config:
    cfg = yaml.safe_load(config)
else:
  LOG.info(f'Configuration file {args.config_file} not found, not using any configuration file')
  cfg = None

API_URL = args.api_url.rstrip('/')
CONNECT_TIMEOUT = args.connect_timeout
READ_TIMEOUT = args.read_timeout
HTTP_SESSION = create_http_session(args.proxy)
if args.proxy:
    LOG.info(f'Using HTTPS proxy: {args.proxy}')

if not args.client_id:
    LOG.error('Service account client ID is required. Pass --client-id or set REDHAT_CLIENT_ID.')
    sys.exit(1)

CLIENT_ID = args.client_id
if args.client_secret:
    CLIENT_SECRET = args.client_secret
else:
    CLIENT_SECRET = getpass(f'Client secret for service account {CLIENT_ID}: ')

try:
    get_access_token()
except (requests.exceptions.RequestException, RuntimeError, ValueError) as auth_error:
    LOG.error(f'Authentication failed for service account {CLIENT_ID}: {auth_error}')
    sys.exit(1)

LOG.info('Successfully authenticated with Red Hat SSO')

# set the initial href for each repository type
hrefs = {
  'validated': '/api/automation-hub/v3/plugin/ansible/content/validated/collections/index/?limit=100',
  'certified': '/api/automation-hub/v3/plugin/ansible/content/published/collections/index/?limit=100'
}

try:
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
        if 'errors' in result:
            LOG.error(f'API request failed for service account {CLIENT_ID}: {result["errors"]}')
            sys.exit(1)

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

            last_update = query_api(HttpRequestType.GET, collection['highest_version']['href'])['updated_at']

            # show only collection updates that are in the given time frame
            if datetime.strptime(last_update, '%Y-%m-%dT%H:%M:%S.%fZ') <= datetime.now() - timedelta(days=args.timedelta):
                continue

            collection_date = datetime.strptime(collection['updated_at'], '%Y-%m-%dT%H:%M:%S.%fZ').strftime(cfg.get('output_date_format', '%Y-%m-%d'))

            highest_version = collection['highest_version']
            print(f"{collection_repo}: {collection_namespace}.{collection_name}: Version {collection['highest_version']['version']} released on {collection_date}")

        # we are done once no next link is given
        if result['links']['next'] is None:
            break

        # assign new href
        href = result['links']['next']

except requests.exceptions.RequestException as request_error:
  LOG.error(request_error)
  sys.exit(1)

sys.exit(0)
