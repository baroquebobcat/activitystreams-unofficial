#!/usr/bin/python
"""ActivityStreams API handler classes.

Implements the OpenSocial ActivityStreams REST API:
http://opensocial-resources.googlecode.com/svn/spec/2.0.1/Social-API-Server.xml#ActivityStreams-Service

Request paths are of the form /user_id/group_id/app_id/activity_id, where
each element is optional. user_id may be @me. group_id may be @all, @friends
(currently identical to @all), or @self. app_id may be @app, but it doesn't
matter, it's currently ignored.

The supported query parameters are startIndex and count, which are handled as
described in OpenSocial (above) and OpenSearch.

Other relevant activity REST APIs:
http://status.net/wiki/Twitter-compatible_API
http://wiki.activitystrea.ms/w/page/25347165/StatusNet%20Mapping
https://developers.google.com/+/api/latest/activities/list
"""

__author__ = ['Ryan Barrett <activitystreams@ryanb.org>']

try:
  import json
except ImportError:
  import simplejson as json
import logging
import re
import os
import urllib
import webapp2
from webob import exc

import appengine_config
import facebook
import source
import twitter
import util

from google.appengine.ext.webapp.util import run_wsgi_app

# maps app id to source class
SOURCE = {
  'facebook-activitystreams': facebook.Facebook,
  'twitter-activitystreams': twitter.Twitter,
  }.get(appengine_config.APP_ID)

XML_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<response>%s</response>
"""
ITEMS_PER_PAGE = 100

# default values for each part of the API request path, e.g. /@me/@self/@all/...
PATH_DEFAULTS = ((source.ME,), (source.ALL, source.FRIENDS), (source.APP,), ())
MAX_PATH_LEN = len(PATH_DEFAULTS)


class Handler(webapp2.RequestHandler):
  """Base class for ActivityStreams API handlers.

  Attributes:
    source: Source subclass
  """

  def __init__(self, *args, **kwargs):
    super(Handler, self).__init__(*args, **kwargs)
    self.source = SOURCE(self)

  def get(self):
    """Handles an API GET.

    Request path is of the form /user_id/group_id/app_id/activity_id , where
    each element is an optional string object id.
    """
    # parse path
    args = urllib.unquote(self.request.path).strip('/').split('/')
    if len(args) > MAX_PATH_LEN:
      raise exc.HTTPNotFound()
    elif args == ['']:
      args = []

    # handle default path elements
    args = [None if a in defaults else a
            for a, defaults in zip(args, PATH_DEFAULTS)]
    paging_params = self.get_paging_params()

    # extract format
    format = self.request.get('format', 'json')
    if format not in ('json', 'atom', 'xml'):
      raise exc.HTTPBadRequest('Invalid format: %s, expected json, atom, xml' %
                               format)

    # get activities and build response
    total_results, activities = self.source.get_activities(*args, **paging_params)
    response = {'startIndex': paging_params['start_index'],
                'itemsPerPage': len(activities),
                'totalResults': total_results,
                # TODO: this is just for compatibility with
                # http://activitystreamstester.appspot.com/
                # the OpenSocial spec says to use entry instead, so switch back
                # to that eventually
                'items': activities,
                'filtered': False,
                'sorted': False,
                'updatedSince': False,
                }

    # encode and write response
    if format == 'json':
      self.response.headers['Content-Type'] = 'application/json'
      self.response.out.write(json.dumps(response, indent=2))
    else:
      self.response.headers['Content-Type'] = 'text/xml'
      self.response.out.write(XML_TEMPLATE % util.to_xml(response))

  def get_paging_params(self):
    """Extracts, normalizes and returns the startIndex and count query params.

    Returns:
      dict with 'start_index' and 'count' keys mapped to integers
    """
    start_index = self.get_positive_int('startIndex')
    count = self.get_positive_int('count')

    if count == 0:
      count = ITEMS_PER_PAGE - start_index
    else:
      count = min(count, ITEMS_PER_PAGE)

    return {'start_index': start_index, 'count': count}

  def get_positive_int(self, param):
    try:
      val = self.request.get(param, 0)
      val = int(val)
      assert val >= 0
      return val
    except (ValueError, AssertionError):
      raise exc.HTTPBadRequest('Invalid %s: %s (should be positive int)' %
                               (param, val))


application = webapp2.WSGIApplication([('.*', Handler)],
                                      debug=appengine_config.DEBUG)

def main():
  run_wsgi_app(application)


if __name__ == '__main__':
  main()
