from pywb.utils.binsearch import iter_range
from pywb.utils.loaders import SeekableTextFileReader

from cdxobject import AccessException

import urllib
import urllib2
import itertools

#=================================================================
class CDXSource(object):
    """
    Represents any cdx index source
    """
    def load_cdx(self, params):
        raise NotImplementedError('Implement in subclass')


#=================================================================
class CDXFile(CDXSource):
    """
    Represents a local plain-text .cdx file
    """
    def __init__(self, filename):
        self.filename = filename

    def load_cdx(self, params):
        source = SeekableTextFileReader(self.filename)
        return iter_range(source, params.get('key'), params.get('end_key'))

    def __str__(self):
        return 'CDX File - ' + self.filename


#=================================================================
class RemoteCDXSource(CDXSource):
    """
    Represents a remote cdx server, to which requests will be proxied.

    Only url and match type params are proxied at this time,
    the stream is passed through all other filters locally.
    """
    def __init__(self, filename, cookie=None, proxy_all=True):
        self.remote_url = filename
        self.cookie = cookie
        self.proxy_all = proxy_all

    def load_cdx(self, proxy_params):
        if self.proxy_all:
            params = proxy_params
            params['proxyAll'] = True
        else:
            # Only send url and matchType params to remote
            params = {}
            params['url'] = proxy_params['url']
            match_type = proxy_params.get('matchType')

            if match_type:
                proxy_params['matchType'] = match_type

        urlparams = urllib.urlencode(params, True)

        try:
            request = urllib2.Request(self.remote_url, urlparams)

            if self.cookie:
                request.add_header('Cookie', self.cookie)

            response = urllib2.urlopen(request)

        except urllib2.HTTPError as e:
            if e.code == 403:
                exc_msg = e.read()
                msg = ('Blocked By Robots' if 'Blocked By Robots' in exc_msg
                       else 'Excluded')

                raise AccessException(msg)
            else:
                raise

        return iter(response)

    def __str__(self):
        return 'Remote CDX Server: ' + self.remote_url


#=================================================================
class RedisCDXSource(CDXSource):
    DEFAULT_KEY_PREFIX = 'c:'

    def __init__(self, redis_url, config=None):
        import redis
        self.redis = redis.StrictRedis.from_url(redis_url)

        self.key_prefix = self.DEFAULT_KEY_PREFIX
        if config:
            self.key_prefix = config.get('redis_key_prefix', self.key_prefix)


    def load_cdx(self, params):
        """
        Load cdx from redis cache, from an ordered list

        Currently, there is no support for range queries
        Only 'exact' matchType is supported
        """
        key = params['key']

        # ensure only url/surt is part of key
        key = key.split(' ')[0]
        cdx_list = self.redis.zrange(self.key_prefix + key, 0, -1)

        # key is not part of list, so prepend to each line
        key += ' '
        cdx_list = itertools.imap(lambda x: key + x, cdx_list)
        return cdx_list