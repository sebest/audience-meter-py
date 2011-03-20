import os
import json
from string import Template
from websocket import WebSocketWSGI

class Clients(object):

    def __init__(self):
        self.namespaces = {}

    def handle(self, ws):
        while True:
            m = ws.wait()
            if m is None:
                self.remove(ws)
                return

            command = json.loads(m)
            namespace_name = command.get('join')
            if namespace_name:
                self.join(ws, namespace_name)
            namespaces_names = command.get('listen')
            if namespaces_names:
                self.listen(ws, namespaces_names)

    def send(self, ws, data):
        ws.send(json.dumps(data))

    def get_namespace(self, namespace_name):
        try:
            return self.namespaces[namespace_name]
        except KeyError:
            namespace = {
                'members': 0,
                'listeners': [],
                'name': namespace_name,
            }
            self.namespaces[namespace_name] = namespace
            return namespace


    def clean_namespace(self, namespace):
        if not namespace['members'] and not namespace['listeners']:
            del self.namespaces[namespace['name']]

    def leave(self, ws):
        if hasattr(ws, 'namespace'):
            ws.namespace['members'] -= 1
            self.clean_namespace(ws.namespace)
            delattr(ws, 'namespace')

    def unlisten(self, ws):
        if hasattr(ws, 'listened'):
            for namespace in ws.listened:
                try:
                    namespace['listeners'].remove(ws)
                except ValueError:
                    continue
                self.clean_namespace(namespace)
            delattr(ws, 'listened')

    def stats(self):
        return dict([(namespace['name'], namespace['members']) for namespace in self.namespaces.values()])

    def info(self, namespace_name):
        try:
            return self.namespaces[namespace_name]['members']
        except KeyError:
            return 0

    def remove(self, ws):
        self.leave(ws)
        self.unlisten(ws)

    def join(self, ws, namespace_name):
        namespace = self.get_namespace(namespace_name)
        if namespace and hasattr(ws, 'namespace'):
            if ws.namespace == namespace:
                return
            self.leave(ws)
        namespace['members'] += 1
        ws.namespace = namespace

    def listen(self, ws, namespaces_names):
        self.unlisten(ws)
        ws.listeners = []
        info = {}
        for namespace_name in namespaces_names:
            namespace = self.get_namespace(namespace_name)
            namespace['listeners'].append(ws)
            info[namespace_name] = namespace['members']
        self.send(ws, info)

    def notify(self):
        listeners = []
        for namespace in self.namespaces.values():
            if not namespace['listeners'] or namespace['last_notified_value'] == namespace['members']:
                continue
            for listener in namespace['listeners']:
                if not hasattr(listener, 'buffer_notif'):
                    listener.buffer_notif = {}
                listener.buffer_notif[namespace['name']] = namespace['members']
            namespace['last_notified_value'] = namespace['members']
            listeners += namespace['listeners'] 

        for listener in listeners:
            if hasattr(listener, 'buffer_notif'):
                listener.send(listener.buffer_notif)
                delattr(listener, 'buffer_notif')

clients = Clients()
wsapp = WebSocketWSGI(clients.handle)
def app(environ, start_response):
    path = environ['PATH_INFO']
    if path == '/stats.json':
        data = json.dumps(clients.stats())
    elif path.endswith('.json'):
        return wsapp(environ, start_response)
    else:
        data = open(os.path.join(
                         os.path.dirname(__file__), 
                         'demo.html')).read()
        data = Template(data).substitute(hostname=environ['HTTP_HOST'], pathname=path)
    start_response('200 OK', [('Content-Type', 'text/html'),
                             ('Content-Length', len(data))])
    return [data]
