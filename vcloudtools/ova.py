import logging
log = logging.getLogger(__name__)

import tarfile

from vcloudtools.vcloud import fromstring

class OVA(object):

    def __init__(self, filename):
        self.tar = tarfile.open(filename)

    @property
    def descriptor(self):
        for fname in self.tar.getnames():
            if fname.endswith('.ovf'):
                stream = self.tar.extractfile(fname)
                data = stream.read()
                stream.close()
                return data

    @property
    def descriptor_etree(self):
        return fromstring(self.descriptor)

    def streamfile(self, fname):
        stream = self.tar.extractfile(fname)
        return stream

    @property
    def networks(self):
        networks = []
        for element in self.descriptor.iter():
            if element.tag == envelopetag('Network'):
                networks.append(element.get(envelopetag('name')))
        return networks


    def close(self):
        self.tar.close()

    def __enter__(self):
        return self

    def __exit__(self, typ, value, tb):
        self.close()

def envelopetag(tag):
    return '{{http://schemas.dmtf.org/ovf/envelope/1}}{}'.format(tag)

def ovftag(tag):
    return '{{http://www.vmware.com/schema/ovf}}{}'.format(tag)
