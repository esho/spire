from glob import glob
from threading import Lock
from time import sleep

from scheme import *

from spire.core import Assembly
from spire.exceptions import TemporaryStartupError
from spire.support.logs import LogHelper, configure_logging
from spire.util import enumerate_tagged_methods, recursive_merge, topological_sort

COMPONENTS_SCHEMA = Sequence(Object(name='component', nonnull=True),
    name='components', unique=True)

PARAMETERS_SCHEMA = Structure({
    'name': Text(),
    'startup_attempts': Integer(default=12),
    'startup_enabled': Boolean(default=True),
    'startup_timeout': Integer(default=5),
}, name='parameters')

log = LogHelper('spire.runtime')

class Runtime(object):
    """A spire runtime."""

    guard = Lock()
    runtime = None

    def __new__(cls, *args, **params):
        with Runtime.guard:
            if Runtime.runtime:
                raise Exception('runtime already instantiated')

            Runtime.runtime = super(Runtime, cls).__new__(cls, *args, **params)
            return Runtime.runtime

    def __init__(self, configuration=None, assembly=None):
        self.assembly = assembly or Assembly.current()
        self.components = {}
        self.configuration = {}
        self.parameters = {}

        if configuration:
            self.configure(configuration)

    def configure(self, configuration):
        if isinstance(configuration, basestring):
            configuration = Format.read(configuration, quiet=True)
            if not configuration:
                return

        includes = configuration.pop('include', None)
        if includes:
            for pattern in includes:
                for include in sorted(glob(pattern)):
                    self.configure(include)

        recursive_merge(self.configuration, configuration)
        return self

    def deploy(self):
        configuration = self.configuration
        if 'logging' in configuration:
            configure_logging(configuration['logging'])

        parameters = configuration.get('spire') or {}
        self.parameters = PARAMETERS_SCHEMA.process(parameters)

        components = configuration.get('components')
        if components:
            components = COMPONENTS_SCHEMA.process(components, serialized=True)

        config = configuration.get('configuration')
        if config:
            self.assembly.configure(config)

        for component in components:
            self.components[component.identity] = self.assembly.instantiate(component)
        return self

    def reload(self):
        pass

    def startup(self):
        if not self.parameters['startup_enabled']:
            log('warning', 'skipping startup of components')
            return

        attempts = self.parameters['startup_attempts']
        timeout = self.parameters['startup_timeout']

        for component in self.components.itervalues():
            methods = enumerate_tagged_methods(component, 'onstartup', True)
            if methods:
                log('info', 'initiating startup of %s', component.identity)
                for method in self._sort_methods(methods):
                    self._execute_startup_method(component, method, attempts, timeout)
                log('info', 'finished startup of %s', component.identity)

    def _execute_startup_method(self, component, method, attempts, timeout):
        params = (method.__name__, component.identity)
        log('info', 'executing %s for startup of %s' % params)

        for _ in range(attempts - 1):
            try:
                method()
            except TemporaryStartupError:
                log('warning', 'execution of %s for startup of %s delayed' % params)
                sleep(timeout)
            except Exception:
                log('exception', 'execution of %s for startup of %s raised exception' % params)
                break
            else:
                log('info', 'execution of %s for startup of %s completed' % params)
                break
        else:
            log('error', 'execution of %s for startup of %s timed out' % params)

    def _sort_methods(self, methods):
        methods = dict((method.__name__, method) for method in methods)
        graph = {}

        for method in methods.itervalues():
            edges = set()
            for name in method.after:
                if name in methods:
                    edges.add(methods[name])
            graph[method] = edges

        return topological_sort(graph)

def current_runtime():
    return Runtime.runtime

def onstartup(after=None):
    if isinstance(after, basestring):
        after = after.split(' ') if after else None
    if not after:
        after = []

    def decorator(method):
        method.after = after
        method.onstartup = True
        return method
    return decorator
