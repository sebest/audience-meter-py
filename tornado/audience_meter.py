from os import path as op

import json
import tornado.web
import tornadio
import tornadio.router
import tornadio.server

ROOT = op.normpath(op.dirname(__file__))

CMD_MAX_NAMESPACE_LEN = 50
CMD_MAX_NAMESPACE_LISTEN = 20
NOTIFY_INTERVAL = 0.5 # seconds


class IndexHandler(tornado.web.RequestHandler):
    """Regular HTTP handler to serve the chatroom page"""
    def get(self, pathname):
        self.render("index.html", hostname='127.0.0.1', pathname='/%s' % pathname)

class ClientError(Exception): pass

def check_namespace_name(namespace_name):
    if not isinstance(namespace_name, unicode):
        raise ClientError('Invalid namespace value: must be a tring')
    if len(namespace_name) > CMD_MAX_NAMESPACE_LEN:
        raise ClientError('Maximum length for namespace is %d' % CMD_MAX_NAMESPACE_LEN)

def check_namespaces_names(namespaces_names):
    if not isinstance(namespaces_names, list):
        raise ClientError('Invalid listen value: must be an array')
    if len(namespaces_names) > CMD_MAX_NAMESPACE_LISTEN:
        raise ClientError('Maximum listenable namespaces is %d' % CMD_MAX_NAMESPACE_LISTEN)

    for namespace_name in namespaces_names:
        check_namespace_name(namespace_name)

class ClientsConnection(tornadio.SocketConnection):

    namespaces = {}

    def on_open(self, *args, **kwargs):
        print 'new client %s' % self

    def on_message(self, m):
        self.namespace = {}
        self.listened = set()
        self.notif = {}

        try:
            try:
                command = json.loads(m)
            except (ValueError, TypeError), e:
                raise ClientError('Invalid JSON command')

            namespace_name = command.get('join')
            if namespace_name:
                self.join(self, namespace_name)
            namespaces_names = command.get('listen')
            if namespaces_names:
                self.listen(self, namespaces_names)
        except ClientError, e:
            return self._send(self, {'err': str(e)})
        except Exception, e:
            return self._send(self, {'err': 'internal error: %s' % e})

        self.notify() # TODO use a periodic callback

    def on_close(self):
        print 'client %s gone' % self
        self.remove(self)
        self.notify() # TODO use a periodic callback

    def send_notif(self, ws):
        if ws.notif:
            self._send(ws, ws.notif)
            ws.notif = {}

    def _send(self, ws, data):
        try:
            ws.send(json.dumps(data))
        except Exception, e:
            print 'Error %s %s' % (ws, e)

    def get_namespace(self, namespace_name):
        try:
            return self.namespaces[namespace_name]
        except KeyError:
            namespace = {
                'members': 0,
                'last_notified_value': 0,
                'listeners': set(),
                'name': namespace_name,
            }
            self.namespaces[namespace_name] = namespace
            return namespace


    def clean_namespace(self, namespace):
        if not namespace['members'] and not namespace['listeners']:
            del self.namespaces[namespace['name']]

    def leave(self, ws):
        if ws.namespace:
            ws.namespace['members'] -= 1
            self.clean_namespace(ws.namespace)
            ws.namespace = None

    def unlisten(self, ws):
        for namespace_name in ws.listened:
            namespace = self.namespaces[namespace_name]
            namespace['listeners'].remove(ws)
            self.clean_namespace(namespace)
        ws.listened = set()

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
        check_namespace_name(namespace_name)

        namespace = self.get_namespace(namespace_name)
        if ws.namespace == namespace:
            return
        self.leave(ws)
        namespace['members'] += 1
        ws.namespace = namespace

    def listen(self, ws, namespaces_names):
        check_namespaces_names(namespaces_names)

        self.unlisten(ws)
        for namespace_name in namespaces_names:
            namespace = self.get_namespace(namespace_name)
            namespace['listeners'].add(ws)
            ws.listened.add(namespace_name)
            ws.notif[namespace_name] = namespace['members']
        self.send_notif(ws)

    def notify(self):
        listeners = set()
        for namespace in self.namespaces.values():
            if not namespace['listeners'] or namespace['last_notified_value'] == namespace['members']:
                continue
            for ws in namespace['listeners']:
                ws.notif[namespace['name']] = namespace['members']
                listeners.add(ws)
            namespace['last_notified_value'] = namespace['members']
        for ws in listeners:
            self.send_notif(ws)
        #gevent.spawn_later(NOTIFY_INTERVAL, self.notify)


#use the routes classmethod to build the correct resource
ClientsRouter = tornadio.get_router(ClientsConnection)

#configure the Tornado application
application = tornado.web.Application(
    [(r"/ns/(.*)", IndexHandler), ClientsRouter.route()],
    enabled_protocols = ['websocket',
                         'flashsocket',
                         'xhr-multipart',
                         'xhr-polling'],
    flash_policy_port = 843,
    flash_policy_file = op.join(ROOT, 'flashpolicy.xml'),
    socket_io_port = 8001
)

if __name__ == "__main__":
    import logging
    logging.getLogger().setLevel(logging.DEBUG)

    tornadio.server.SocketServer(application)
