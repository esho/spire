from __future__ import absolute_import

from scheme import Format

from spire.wsgi.util import Dispatcher, Mount
from spire.component import Registry

try:
    import uwsgi
except ImportError:
    uwsgi = None

class Driver(object):
    def __init__(self):
        Registry.configure(self._load_configuration())
        Registry.deploy()

        self.dispatcher = Dispatcher()
        for unit in Registry.collate(Mount):
            self.dispatcher.mount(unit.configuration['path'], unit)

    def __call__(self, environ, start_response):
        return self.dispatcher.dispatch(environ, start_response)

    def _load_configuration(self):
        for key in ('yaml', 'yml', 'json'):
            filename = uwsgi.opt.get(key)
            if filename:
                break
        else:
            raise RuntimeError()

        configuration = Format.read(filename)
        if 'spire' in configuration:
            return configuration['spire']
        else:
            raise RuntimeError()

if uwsgi:
    uwsgi.applications = {'': Driver()}