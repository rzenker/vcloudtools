import logging
log = logging.getLogger(__name__)

import threading
from urlparse import urlparse

CONNECTIONS = threading.local().connections = []

def request(method, url, _raise=True, *args, **kwargs):

    urlobj = urlparse(url)
    baseurl = '{}://{}'.format(urlobj.scheme, urlobj.netloc)
    client = None
    for client in CONNECTIONS:
        if baseurl in client._baseurls:
            break

    if not client:
        raise Exception('active client not found for {}'.format(baseurl))

    if not client.logged_in:
        # session timeouts...
        log.info('session timeout.. reconnecting to {}'.format(baseurl))
        client.login()

    #log.info("requesting {}".format(url))
    kwargs.setdefault('headers', {})
    kwargs['headers'].setdefault('Accept', 'application/*+xml;version=5.1')
    return client.req(method, url, _raise=_raise, *args, **kwargs)
