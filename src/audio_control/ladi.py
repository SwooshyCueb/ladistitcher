import threading, dbus, weakref, inspect, re
from time import sleep
from pprint import pprint
import uuid, tempfile
import xml.etree.ElementTree as xml

from .common import *
from . import dbus_threads
#import pa

ladi_signal_thread = dbus_threads.dbus_signal_handler_thread()

class err(Exception):
    pass

class ladish_started_without_jack(err):
    pass

class ladish_already_started(err):
    pass

class _room_interface:

    # Ensure derivative classes have access to base class methods/variables
    def __set_pdvars(self):
        deriv_start = self.__class__.__name__
        if deriv_start[0] != '_':
            deriv_start = '_' + deriv_start
        for baseclass in self.__class__.__bases__:
            base_start = baseclass.__name__
            if base_start[0] != '_':
                base_start = '_' + base_start
            for member in inspect.getmembers(self):
                if member[0].startswith(base_start):
                    func = getattr(self, member[0])
                    fname = re.sub('^' + base_start, deriv_start, member[0])
                    if fname[0] != '_':
                        fname = '_' + fname
                    if not hasattr(self, fname):
                        setattr(self, fname, func)

    # Get private variable from deriviative class
    def __get_pdvar(self, var):
        pdvar = self.__class__.__name__ + var
        if pdvar[0] != "_":
            pdvar = '_' + pdvar
        return getattr(self, pdvar)

    def __init__(self):
        self.room_locks = {
            'AppAdded2':            threadlocks.signal_cond(),
            'AppRemoved':           threadlocks.signal_cond(),
            'AppStateChanged2':     threadlocks.signal_cond(),
            'ClientAppeared':       threadlocks.signal_cond(),
            'ClientDisappeared':    threadlocks.signal_cond(),
            'ClientRenamed':        threadlocks.signal_cond(),
            'GraphChanged':         threadlocks.signal_cond(),
            'PortAppeared':         threadlocks.signal_cond(),
            'PortDisappeared':      threadlocks.signal_cond(),
            'PortRenamed':          threadlocks.signal_cond(),
            'PortsConnected':       threadlocks.signal_cond(),
            'PortsDisconnected':    threadlocks.signal_cond(),
        }

        self.graph = dict()

        self.__set_pdvars()

    def __connect_common(self, room_dbus):
        self.__graphmgr = dbus.Interface(room_dbus, 'org.ladish.GraphManager')
        self.__graphviz = dbus.Interface(room_dbus, 'org.ladish.GraphDict')
        self.__appsprvsr = dbus.Interface(room_dbus, 'org.ladish.AppSupervisor')
        self.__patchbay = dbus.Interface(room_dbus, 'org.jackaudio.JackPatchbay')
        ladi_signal_thread.connect_signal(self.__appsprvsr, "AppAdded2", self.__newapp)
        ladi_signal_thread.connect_signal(self.__appsprvsr, "AppRemoved", self.__appgone)
        ladi_signal_thread.connect_signal(self.__appsprvsr, "AppStateChanged2", self.__appstate)
        ladi_signal_thread.connect_signal(self.__patchbay, "ClientAppeared", self.__newclient)
        ladi_signal_thread.connect_signal(self.__patchbay, "ClientDisappeared", self.__clientgone)
        ladi_signal_thread.connect_signal(self.__patchbay, "ClientRenamed", self.__clientrename)
        ladi_signal_thread.connect_signal(self.__patchbay, "PortAppeared", self.__newport)
        ladi_signal_thread.connect_signal(self.__patchbay, "PortDisappeared", self.__portgone)
        ladi_signal_thread.connect_signal(self.__patchbay, "PortRenamed", self.__portrename)
        ladi_signal_thread.connect_signal(self.__patchbay, "PortsConnected", self.__portconnect)
        ladi_signal_thread.connect_signal(self.__patchbay, "PortsDisconnected", self.__portdisconnect)

        # Explicitly set private attributes of derivative class
        deriv = self.__class__.__name__
        if deriv[0] != '_':
            deriv = '_' + deriv
        setattr(self, deriv + '__graphmgr', self.__graphmgr)
        setattr(self, deriv + '__appsprvsr', self.__appsprvsr)
        setattr(self, deriv + '__patchbay', self.__patchbay)


    def __getitem__(self, item):
        if type(item) != str:
            TypeError('Key must be a str')
        if item in self.graph:
            return self.graph[item]
        raise KeyError('No client with name ' + item)

    def __setitem__(self, item, value):
        if client not in (value.__class__.__bases__ + (value.__class__,)):
            raise TypeError('must be a client')
        if type(item) != str:
            raise TypeError('must set by client name')
        value.room = weakref.proxy(self)
        self.graph[item] = value

    def __delitem__(self, item):
        raise RuntimeError("cannot delete clients this way")

    def __contains__(self, item):
        if type(item) != str:
            raise TypeError
        if item in self.graph:
            return True
        else:
            return False

    def __newclient(self, new_graph_version, id, name, member):
        name = str(name)
        id = int(id)

        #psiggot("Got D-Bus signal: " + member)
        #psiginf("id: " + str(id))
        #psiginf("name: " + name)

        with self.room_locks[member]:
            if name not in self.graph:
                self.graph[name] = client()
                self.graph[name].name = name
            self.graph[name].id = id
            self.graph[name].room = weakref.proxy(self)
            self.room_locks[member].notify_all()

    def __newapp(self, n1, id, name, running, in_terminal, applevel, member):
        name = str(name)
        id = int(id)
        running = bool(running)
        applevel = int(applevel)

        #psiggot("Got D-Bus signal: " + member)
        #psiginf("id: " + str(id))
        #psiginf("name: " + name)
        #psiginf("running: " + str(running))
        #psiginf("applevel: " + str(applevel))

        with self.room_locks[member]:
            if name in self.graph:
                self.graph[name] = app(self.graph[name])
            else:
                self.graph[name] = app()
                self.graph[name].name = name
            self.graph[name].app_id = id
            self.graph[name].level = applevel
            self.graph[name].running = running
            # todo: cmd using GetAppProperties
            self.room_locks[member].notify_all()

    def __newport(self, n1, n2, cname, id, name, flags, typeval, member):
        id = int(id)
        name = str(name)
        cname = str(cname)

        #psiggot("Got D-Bus signal: " + member + " (LADI")
        #psiginf("client: " + cname)
        #psiginf("id: " + str(id))
        #psiginf("name: " + name)

        with self.room_locks[member]:
            newport = port()
            newport.name = name
            newport.id = id
            newport.client = weakref.proxy(self.graph[cname])
            if flags & 1:
                newport.direction = 'in'
            elif flags & 2:
                newport.direction = 'out'
            else:
                print('Port ' + cname + ':' + name + ' of unknown direction with flags value ' + str(flags))
            if typeval == 0:
                newport.type = 'audio'
            elif typeval == 1:
                newport.type = 'midi'
            else:
                print('Port ' + cname + ':' + name + ' of unknown type ' + str(typeval))

            if type(self) == room:
                jmcore_ports = self.room._studio__jmcore_ports
            else:
                jmcore_ports = self._studio__jmcore_ports

            if len(jmcore_ports) > 0:
                jmcp = jmcore_ports.pop(0)
                newport.jmcore_name = jmcp.name
                newport.jmcore_client = jmcp.client

            self.graph[cname].ports[name] = newport
            self.room_locks[member].notify_all()

    def __portrename(self, n1, cid, cname, id, oldname, newname, member):
        cname = str(cname)
        oldname = str(oldname)
        newname = str(newname)

        #psiggot("Got D-Bus singal: " + member)
        #psiginf("client: " + cname)
        #psiginf("id: " + str(id))
        #psiginf("old name: " + oldname)
        #psiginf("new name: " + newname)

        with self.room_locks[member]:
            p = self.graph[cname].ports[oldname]
            del self.graph[cname].ports[oldname]
            p.name = newname
            self.graph[cname].ports[newname] = p
            self.room_locks[member].notify_all()

    def __clientrename(self, n1, id, oldname, newname, member):
        oldname = str(oldname)
        newname = str(newname)

        #psiggot("Got D-Bus singal: " + member)
        #psiginf("id: " + str(id))
        #psiginf("old name: " + oldname)
        #psiginf("new name: " + newname)

        with self.room_locks[member]:
            c = self.graph[oldname]
            del self.graph[oldname]
            c.name = newname
            self.graph[newname] = c
            self.room_locks[member].notify_all()

    def __portconnect(self, n1, cid1, client1, pid1, port1, cid2, client2, pid2, port2, conn_id, member):
        client1 = str(client1)
        port1 = str(port1)
        client2 = str(client2)
        port2 = str(port2)

        #psiggot("Got D-Bus signal: " + member)
        #psiginf("client 1: " + client1)
        #psiginf("port 1: " + port1)
        #psiginf("client 2: " + client2)
        #psiginf("port 2: " + port2)

        with self.room_locks[member]:
            self[client1][port1].connections[conn_id] = weakref.proxy(self[client2][port2])
            self[client2][port2].connections[conn_id] = weakref.proxy(self[client1][port1])
            self.room_locks[member].notify_all()

    def __portdisconnect(self, n1, cid1, client1, pid1, port1, cid2, client2, pid2, port2, conn_id, member):
        client1 = str(client1)
        port1 = str(port1)
        client2 = str(client2)
        port2 = str(port2)

        #psiggot("Got D-Bus signal: " + member)
        #psiginf("client 1: " + client1)
        #psiginf("port 1: " + port1)
        #psiginf("client 2: " + client2)
        #psiginf("port 2: " + port2)

        with self.room_locks[member]:
            try:
                del self[client1][port1].connections[conn_id]
                del self[client2][port2].connections[conn_id]
            except KeyError:
                pass
            self.room_locks[member].notify_all()

    def __appstate(self, n1, id, name, running, in_terminal, applevel, member):
        id = int(id)
        name = str(name)
        running = bool(running)
        applevel = int(applevel)

        psiggot("Got D-Bus signal: " + member)
        psiginf("id: " + str(id))
        psiginf("name: " + name)
        psiginf("running: " + str(running))
        psiginf("applevel: " + str(applevel))

        with self.room_locks[member]:
            try:
                self.graph[name].running = running
            except KeyError:
                pass
            self.room_locks[member].notify_all()

    def __clientgone(self, n1, id, name, member):
        id = int(id)
        name = str(name)

        #psiggot("Got D-Bus signal: " + member)
        #psiginf("id: " + str(id))
        #psiginf("name: " + name)

        with self.room_locks[member]:
            try:
                if type(self.graph[name].type) in ['standard', 'pulse']:
                    del self.graph[name]
                else:
                    self.graph[name].id = -1
            except KeyError:
                pass
            self.room_locks[member].notify_all()

    def __portgone(self, n1, cid, cname, id, name, member):
        id = int(id)
        cname = str(cname)
        name = str(name)

        #psiggot("Got D-Bus signal: " + member)
        #psiginf("client: " + cname)
        #psiginf("id: " + str(id))
        #psiginf("name: " + name)

        # FIXME: This will cause exceptions when we don't have a graph built
        with self.room_locks[member]:
            try:
                del self.graph[cname].ports[name]
            except KeyError:
                pass
            self.room_locks[member].notify_all()

    def __appgone(self, n1, id, member):
        id = int(id)

        #psiggot("Got D-Bus signal: " + member)
        #psiginf("id: " + str(id))

        with self.room_locks[member]:
            for cname, c in self.graph.items():
                if c.type == 'app' and c.app_id == id:
                    del self.graph[cname]
                    break
            self.room_locks[member].notify_all()

    def run_app(self, name, cmd, level=0, wait_on_ports=0):
        level = str(level)
        appsprvsr = self.__get_pdvar('__appsprvsr')
        with self.room_locks['ClientAppeared'].exit_when(lambda: (name in self.graph) and (self.graph[name].id != -1)):
            appsprvsr.RunCustom2(False, cmd, name, level)

        with self.room_locks['PortAppeared']:
            self.room_locks['PortAppeared'].wait_for(lambda: len(self[name].ports) >= wait_on_ports)

        return weakref.proxy(self.graph[name])

class client:

    def __init__(self):
        self.name = ''
        self.id = -1
        self.type = 'standard'
        self.path = None
        self.ports = dict()
        self.room = None

    def __getitem__(self, item):
        if type(item) != str:
            raise TypeError('Key must be a str')
        if item in self.ports:
            return self.ports[item]
        raise KeyError('No port with name ' + item)

    def __setitem__(self, item, value):
        if type(value) != port:
            raise TypeError('must be a port')
        if type(item) != str:
            raise TypeError('must set by port name')
        value.client = weakref.proxy(self)
        self.ports[item] = value

    def __delitem__(self, item):
        raise RuntimeError("cannot delete ports this way")

    def __contains__(self, item):
        if type(item) != str:
            raise TypeError
        if item in self.ports:
            return True
        else:
            return False

    def set_pos(self, x, y):
        graphviz = self.room._room_interface__graphviz
        graphviz.Set(dbus.UInt32(1), dbus.UInt64(self.id), 'http://ladish.org/ns/canvas/x', str(x))
        graphviz.Set(dbus.UInt32(1), dbus.UInt64(self.id), 'http://ladish.org/ns/canvas/y', str(y))

    def rename(self, newname):
        cname = self.room.__class__.__name__
        if cname[0] != '_':
            cname = '_' + cname
        graphmgr = getattr(self.room, cname + '__graphmgr')
        with self.room.room_locks['ClientRenamed'].exit_when(lambda: (oldname not in self.room.graph) and (newname in self.room.graph)):
            oldname = self.name
            graphmgr.RenameClient(dbus.UInt64(self.id), newname)

class port:
    def __init__(self):
        self.name = ''
        self.id = -1
        self.direction = None
        self.type = None
        self.connections = dict()
        self.client = None
        self.jmcore_client = None
        self.jmcore_name = None

    def rename(self, newname):
        cname = self.client.room.__class__.__name__
        if cname[0] != '_':
            cname = '_' + cname
        graphmgr = getattr(self.client.room, cname + '__graphmgr')
        with self.client.room.room_locks['PortRenamed'].exit_when(lambda: (oldname not in self.client.ports) and (newname in self.client.ports)):
            oldname = self.name
            graphmgr.RenamePort(dbus.UInt64(self.id), newname)

    def connect(self, connectee):
        cname = self.client.room.__class__.__name__
        if cname[0] != '_':
            cname = '_' + cname
        patchbay = getattr(self.client.room, cname + '__patchbay')
        patchbay.ConnectPortsByID(dbus.UInt64(self.id), dbus.UInt64(connectee.id))
        #TODO: fix the problem in ladish where the old port name is returned so we can start keeping track of connections and use a conditional lock here


class room(_room_interface, client):

    def __init__(self, path):
        client.__init__(self)
        self.type = 'room'
        self.path = path
        self.graph = dict()

        _room_interface.__init__(self)

        self.__room_dbus = dbus_session.get_object('org.ladish', path)
        self.__control = dbus.Interface(self.__room_dbus, 'org.ladish.Room')
        self.__connect_common(self.__room_dbus)

        for dbus_client in self.__patchbay.GetGraph(0)[1]:
            cname = str(dbus_client[1])
            self.graph[cname] = client()
            self.graph[cname].name = cname
            self.graph[cname].id = int(dbus_client[0])
            self.graph[cname].room = weakref.proxy(self)
            for dbus_port in dbus_client[2]:
                newport = port()
                newport.name = str(dbus_port[1])
                newport.id = int(dbus_port[0])
                newport.client = weakref.proxy(self.graph[cname])
                if (int(dbus_port[2]) & 1):
                    newport.direction = 'in'
                elif (int(dbus_port[2]) & 2):
                    newport.direction = 'out'
                if (int(dbus_port[3]) == 0):
                    newport.type = 'audio'
                elif (int(dbus_port[3]) == 1):
                    newport.type = 'midi'
                self.graph[cname].ports[newport.name] = newport

    def __getitem__(self, item):
        if type(item) != str:
            TypeError('Key must be a str')
        if item in self.ports:
            return self.ports[item]
        elif item in self.graph:
            return self.graph[item]
        else:
            KeyError('No port or client with name ' + item)

    def __setitem__(self, item, value):
        if type(item) != str:
            raise TypeError('must set by port or client name')
        if type(value) in reftypes:
            raise TypeError('cannot set to a weak reference')
        elif type(value) == port:
            value.client = weakref.proxy(self)
            self.ports[item] = value
        elif client in (value.__class__.__bases__ + (value.__class__,)):
            value.room = weakref.proxy(self)
            self.graph[item] = value
        else:
            raise TypeError('must be a port or client')

    def __delitem__(self, item):
        raise RuntimeError("cannot delete ports or clients this way")

    def __contains__(self, item):
        if type(item) != str:
            raise TypeError
        if item in self.ports or item in self.graph:
            return True
        else:
            return False

class app(client):

    def __init__(self, base_client=None):
        if base_client == None:
            super().__init__()
        else:
            self.name = base_client.name
            self.id = base_client.id
            self.path = base_client.path
            self.ports = base_client.ports
            for key, p in self.ports.items():
                p.client = weakref.proxy(self)
            self.room = base_client.room
        self.type = 'app'
        self.app_id = -1
        self.level = 0
        self.cmd = ''
        self.running = False
        self.do_not_relaunch = False


class studio(_room_interface):
    # There should only ever be one of these

    class __jmcore_port():
        def __init__(self):
            self.name = None
            self.client = None

    __jdbus = None
    __ldbus_control = None
    __ldbus_studio = None
    __jackcontrol = None
    __jpatchbay = None
    __sessionmgr = None
    __jtransport = None
    __ladicontrol = None
    __config = None
    __studio = None

    jack_locks = {
        'ServerStarted':    threadlocks.signal_lock(),
        'ServerStopped':    threadlocks.signal_lock(),
    }
    studio_locks = {
        'CleanExit':        threadlocks.signal_lock(),
        'RoomAppeared':     threadlocks.signal_cond(),
        'RoomChanged':      threadlocks.signal_cond(),
        'RoomDisappeared':  threadlocks.signal_cond(),
        'StudioStarted':    threadlocks.signal_lock(),
        'StudioStopped':    threadlocks.signal_lock(),
    }

    def __init__(self):
        super().__init__()
        self.__jmcore_ports = []

    def __jacksignal(self, member):
        self.jack_locks[member].signal()

    def __newroom(self, path, info, member):
        path = str(path)
        name = str(info['name'])
        template = str(info['template'])

        psiggot("Got D-Bus signal: " + member)
        psiginf("path: " + path)
        psiginf("name: " + name)

        with self.studio_locks[member]:
            newroom = room(path)
            newroom.name = name
            if newroom.name in self.graph:
                preroom = self.graph[name]
                newroom.id = preroom.id
            self.graph[name] = newroom
            self.studio_locks[member].notify_all()

    def __roomstate(self, path, info, member):
        path = str(path)
        name = str(info['name'])
        template = str(info['template'])

        #psiggot("Got D-Bus signal: " + member)
        #psiginf("path: " + path)
        #psiginf("name: " + name)

        with self.studio_locks[member]:
            self.studio_locks[member].notify_all()

    def __roomgone(self, path, info, member):
        path = str(path)
        name = str(info['name'])
        template = str(info['template'])

        #psiggot("Got D-Bus signal: " + member)
        #psiginf("path: " + path)
        #psiginf("name: " + name)

        with self.studio_locks[member]:
            try:
                del self.graph[name]
            except KeyError:
                pass
            self.studio_locks[member].notify_all()

    def __jnewport(self, n1, n2, cname, id, name, flags, typeval, member):
        id = int(id)
        name = str(name)
        cname = str(cname)

        #psiggot("Got D-Bus signal: " + member + " (JACK)")
        #psiginf("client: " + cname)
        #psiginf("id: " + str(id))
        #psiginf("name: " + name)

        jmcp = self.__jmcore_port()
        jmcp.name = name
        jmcp.client = cname

        # A ladish room is really just a series of port pairs.
        self.__jmcore_ports.append(jmcp)


    def __connect_jack(self):
        self.__jdbus = dbus_session.get_object('org.jackaudio.service', '/org/jackaudio/Controller')
        self.__jackcontrol = dbus.Interface(self.__jdbus, 'org.jackaudio.JackControl')
        self.__config = dbus.Interface(self.__jdbus, 'org.jackaudio.Configure')
        self.__sessionmgr = dbus.Interface(self.__jdbus, 'org.jackaudio.SessionManager')
        self.__jtransport = dbus.Interface(self.__jdbus, 'org.jackaudio.JackTransport')
        self.__jpatchbay = dbus.Interface(self.__jdbus, 'org.jackaudio.JackPatchbay')
        ladi_signal_thread.connect_signal(self.__jackcontrol, "ServerStarted", self.__jacksignal)
        ladi_signal_thread.connect_signal(self.__jackcontrol, "ServerStopped", self.__jacksignal)
        ladi_signal_thread.connect_signal(self.__jpatchbay, "PortAppeared", self.__jnewport)

    def __connect_ladi(self):
        self.__ldbus_control = dbus_session.get_object('org.ladish', '/org/ladish/Control')
        self.__ldbus_studio = dbus_session.get_object('org.ladish', '/org/ladish/Studio')
        self.__ldbus_conf = dbus_session.get_object('org.ladish.conf', '/org/ladish/conf')
        self.__ladicontrol = dbus.Interface(self.__ldbus_control, 'org.ladish.Control')
        self.__studio = dbus.Interface(self.__ldbus_studio, 'org.ladish.Studio')
        self.__ladiconf = dbus.Interface(self.__ldbus_conf, 'org.ladish.conf')
        self.__connect_common(self.__ldbus_studio)
        ladi_signal_thread.connect_signal(self.__ladicontrol, "CleanExit", self.__ladisignal)
        ladi_signal_thread.connect_signal(self.__studio, "RoomAppeared", self.__newroom)
        ladi_signal_thread.connect_signal(self.__studio, "RoomChanged", self.__roomstate)
        ladi_signal_thread.connect_signal(self.__studio, "RoomDisappeared", self.__roomgone)
        #ladi_signal_thread.connect_signal(self.__studio, "RoomChanged", signalprint, sender_keyword="sender", destination_keyword="destination", interface_keyword="interface", path_keyword="path", message_keyword="message")
        #ladi_signal_thread.connect_signal(self.__studio, "RoomDisappeared", signalprint, sender_keyword="sender", destination_keyword="destination", interface_keyword="interface", path_keyword="path", message_keyword="message")
        #ladi_signal_thread.connect_signal(self.__studio, "StudioCrashed", signalprint, sender_keyword="sender", destination_keyword="destination", interface_keyword="interface", path_keyword="path", message_keyword="message")
        ladi_signal_thread.connect_signal(self.__studio, "StudioStarted", self.__ladisignal)
        ladi_signal_thread.connect_signal(self.__studio, "StudioStopped", self.__ladisignal)


    def __connect(self):
        self.__connect_jack()
        self.__connect_ladi()

    def __ladisignal(self, member):
        self.studio_locks[member].release()

    def connect_jack(self, only_if_running=False):
        try:
            self.__jackcontrol.not_a_real_method()
        except dbus.exceptions.DBusException as e:
            if e._dbus_error_name in ["org.freedesktop.DBus.Error.ServiceUnknown", 'org.freedesktop.DBus.Error.Disconnected']:
                self.__jackcontrol = None
        except AttributeError:
            self.__jackcontrol = None
        if (self.__jackcontrol == None) and ((only_if_running == False) or (len(getpids('jackdbus')) > 0)):
            self.__connect_jack()

    def connect_ladi(self, only_if_running=False):
        try:
            self.__ladicontrol.not_a_real_method()
        except dbus.exceptions.DBusException as e:
            if e._dbus_error_name in ["org.freedesktop.DBus.Error.ServiceUnknown", 'org.freedesktop.DBus.Error.Disconnected']:
                self.__ladicontrol = None
        except AttributeError:
            self.__ladicontrol = None
        if (self.__ladicontrol == None) and ((only_if_running == False) or (len(getpids('ladishd')) > 0)):
            self.__connect_ladi()

    def connect(self, only_if_running=False):
        self.connect_jack(only_if_running)
        self.connect_ladi(only_if_running)

    def start(self):
        # Is ladish already running?
        try:
            self.connect_ladi(only_if_running=True)
            if self.__ladicontrol != None and self.__studio.IsStarted():
                raise ladish_already_started
        except dbus.exceptions.DBusException as e:
            if e._dbus_error_name == 'org.freedesktop.DBus.Error.UnknownMethod':
                pass

        # stop jack if it's already started
        self.connect_jack(only_if_running=True)
        if self.__jackcontrol != None and self.__jackcontrol.IsStarted():
            try:
                with jack_locks['ServerStopped']:
                    self.__jackcontrol.StopServer()
            except dbus.exceptions.DBusException:
                pass
        killall('jackd')

        # Start ladish
        self.connect_ladi()
        with self.studio_locks['StudioStarted']:
            self.__ladicontrol.NewStudio('GE70-2QE Audio System')
            self.__studio.Start()

        # Did ladish start JACK?
        self.connect_jack(only_if_running=True)
        if self.__jackcontrol == None or not(self.__jackcontrol.IsStarted()):
            raise ladish_started_without_jack

        self.connect_jack()


    def stop(self):
        # Stop ladish
        try:
            self.connect_ladi(only_if_running=True)
            if self.__ladicontrol != None and self.__studio.IsStarted():
                try:
                    with self.studio_locks['StudioStopped']:
                        self.__studio.Stop()
                        self.__studio.Unload()
                except dbus.exceptions.DBusException as e:
                    pass
        except dbus.exceptions.DBusException as e:
            if e._dbus_error_name == 'org.freedesktop.DBus.Error.UnknownMethod':
                pass
        # Stop JACK, if it's somehow still running
        self.connect_jack(only_if_running=True)
        if self.__jackcontrol != None and self.__jackcontrol.IsStarted():
            try:
                with jack_locks['ServerStopped']:
                    self.__jackcontrol.StopServer()
            except dbus.exceptions.DBusException:
                pass
        killall('jackd')
        self.__sessionmgr = self.__jtransport = self.__jpatchbay = None

    def set_param(self, section, param, value=None):
        if section.find('/') != -1:
            if type(param) == bool:
                param = str(param).lower()
            else:
                param = str(param)
            self.__ladiconf.set(section, param)
            return


        if value == None:
            self.__config.ResetParameterValue([section, param])

            checks = 0
            while True:
                checks += 1
                if checks == 10:
                    break
                if self.__config.GetParameterValue([section, param])[0]:
                    sleep(1)
                    continue
            return

        psubstatus("Setting " + section + " parameter " + param + " to " + str(value) + "...")
        typechar = str(self.__config.GetParameterInfo([section, param])[0])[0]
        if typechar == 'y':
            if type(value) == str:
                value = ord(value)
            value = dbus.Byte(value)
        if typechar == 'b':
            value = dbus.Boolean(value)
        elif typechar == 'n':
            value = dbus.Int16(value)
        elif typechar == 'q':
            value = dbus.UInt16(value)
        elif typechar == 'i':
            value = dbus.Int32(value)
        elif typechar == 'u':
            value = dbus.UInt32(value)
        elif typechar == 'x':
            value = dbus.Int64(value)
        elif typechar == 't':
            value = dbus.UInt64(value)
        elif typechar == 'd':
            value = dbus.Double(value)
        elif typechar == 'h':
            value = dbus.types.UnixFd(value)
        elif typechar == 's':
            value = dbus.String(value)
        elif typechar == 'o':
            value = dbus.ObjectPath(value)
        elif typechar == 'a':
            value = dbus.Array(value)
        elif typechar == '(':
            value = dbus.Struct(value)
        elif typechar == '{':
            value = dbus.Dictionary(value)

        self.__config.SetParameterValue([section, param], value)

        checks = 0
        while True:
            checks += 1
            if checks == 10:
                break
            is_set, pdef, val = self.__config.GetParameterValue([section, param])
            if (is_set == False) or (val != value):
                sleep(1)
                continue
            else:
                break

    def set_engine_param(self, param, value=None):
        self.set_param('engine', param, value)

    def set_driver_param(self, param, value=None):
        self.set_param('driver', param, value)

    # TODO: Implement template-less rooms in ladish, use them here
    def create_room(self, name, template):
        with self.room_locks['ClientAppeared'].exit_when(lambda: (name in self.graph) and (self[name].id != -1)):
            self.__studio.CreateRoom(name, template)

        return weakref.proxy(self.graph[name])
