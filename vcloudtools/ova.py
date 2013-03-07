import logging
log = logging.getLogger(__name__)

import tarfile


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

    def streamfile(self, fname):
        stream = self.tar.extractfile(fname)
        return stream

    def close(self):
        self.tar.close()

    def __enter__(self):
        return self

    def __exit__(self, typ, value, tb):
        self.close()
