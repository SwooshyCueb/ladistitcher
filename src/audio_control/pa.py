from pprint import pprint
import threading, weakref
import subprocess, dbus, fcntl, os, io
from configparser import ConfigParser
from time import sleep, monotonic

from .common import *
from . import ladi

from . import dbus_threads

pulse_signal_thread = dbus_threads.dbus_signal_handler_thread()

class err(Exception):
    pass

class not_yet_implemented(err):
    pass

class pulse:

    class __module():
        def __init__(self, core, path):
            self.core = core
            self.path = path
            self.__module_dbus = self.core._pulse__dbus.get_object(object_path=self.path)
            self.__module = dbus.Interface(self.__module_dbus, 'org.PulseAudio.Core1.Module')
            self.__props = dbus.Interface(self.__module_dbus, 'org.freedesktop.DBus.Properties')
            self.name = str(self.__props.Get('org.PulseAudio.Core1.Module', 'Name'))

        def unload(self):
            with self.core.pa_locks['ModuleRemoved'].exit_when(lambda: self.path not in self.core.loaded_modules):
                self.__module.Unload()

    class __pa_device(ladi.client):
        def __init__(self, core, path, member):
            super().__init__()
            self.core = core
            self.path = path

            self.type = 'pulse'

            if member == "NewSource":
                self.pa_type = "source"
            elif member == "NewSink":
                self.pa_type = 'sink'
            else:
                self.pa_type = 'undf'

            self.__device_dbus = self.core._pulse__dbus.get_object(object_path=path)
            self.__device = dbus.Interface(self.__device_dbus, 'org.PulseAudio.Core1.Device')
            self.__props = dbus.Interface(self.__device_dbus, 'org.freedesktop.DBus.Properties')
            props = type_dbus_to_python(self.__props.GetAll('org.PulseAudio.Core1.Device'))
            self.pulse_name_internal = props['Name']
            if 'OwnerModule' in props:
                self.__module_path = props['OwnerModule']
            else:
                self.__module_path = None

            if 'device.class' in props['PropertyList']:
                self.pa_class = props['PropertyList']['device.class']
            elif 'device.api' in props['PropertyList']:
                self.pa_class = props['PropertyList']['device.api']

            if self.pa_class == 'jack':
                self.name = props['PropertyList']['jack.client_name']

            self.pulse_name = props['PropertyList']['device.description']

        @property
        def module(self):
            return self.core.loaded_modules[self.__module_path]

        def set_pulse_name(self, name):
            # Rather than listen for PropertyListUpdated, let's just do everything here
            self.pulse_name = name

            # We can't update proplist using dbus?
            #props = self.__props.Get('org.PulseAudio.Core1.Device', 'PropertyList')
            #props['device.description'] = str_to_dbus_bytearr(name)
            #props = self.__props.Set('org.PulseAudio.Core1.Device', 'PropertyList', props)

            # This is not the way I want to do this
            pacmd = subprocess.Popen('pacmd', stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, bufsize=1)
            fcntl.fcntl(pacmd.stdout, fcntl.F_SETFL, fcntl.fcntl(pacmd.stdout, fcntl.F_GETFL) | os.O_NONBLOCK)
            fcntl.fcntl(pacmd.stderr, fcntl.F_SETFL, fcntl.fcntl(pacmd.stderr, fcntl.F_GETFL) | os.O_NONBLOCK)
            cmd  = 'update-' + self.pa_type + '-proplist '
            cmd += self.pulse_name_internal + ' '
            cmd += 'device.description="' + name + '"'
            print(cmd, file=pacmd.stdin, flush=True)
            outstd, outerr = pacmd.communicate()


        def _consume_client(self, client):
            self.id = client.id
            self.ports = client.ports
            self.room = client.room

            for key, port in self.ports.items():
                port.client = weakref.proxy(self)

        def remove(self):
            with self.core.pa_locks[self.pa_type.title() + 'Removed'].exit_when(lambda: self.pulse_name_internal not in self.core.devices):
                self.module.unload()

        def set_volume(self, vol, as_percentage=True):
            if as_percentage:
                vol = int((vol/100) * 65536)
            vol = dbus.Array([dbus.UInt32(vol)])
            self.__props.Set('org.PulseAudio.Core1.Device', 'Volume', vol)

        def set_mute(self, mute):
            mute = dbus.Boolean(mute)
            self.__props.Set('org.PulseAudio.Core1.Device', 'Mute', mute)


    def __newdev(self, path, member):
        path = str(path)

        #psiggot("Got D-Bus signal: " + member)
        #psiginf("path: " + path)

        with self.pa_locks[member]:
            try:
                dev = self.__pa_device(self, path, member)
            except not_yet_implemented:
                pass
            else:
                self.devices[dev.pulse_name_internal] = dev
                self.devpathmap[dev.path] = weakref.proxy(dev)
            finally:
                self.pa_locks[member].notify_all()

    def __devgone(self, path, member):
        path = str(path)

        #psiggot("Got D-Bus signal: " + member)
        #psiginf("path: " + path)

        with self.pa_locks[member]:
            if (path in self.devpathmap) and (self.devpathmap[path].pulse_name_internal in self.devices):
                del self.devices[self.devpathmap[path].pulse_name_internal]
                del self.devpathmap[path]
            self.pa_locks[member].notify_all()

    # Doing this by signal allows us to catch any modules loaded that we did not explicitly load ourselves
    def __newmodule(self, path, member):
        path = str(path)

        #psiggot("Got D-Bus signal: " + member)
        #psiginf("path: " + path)

        with self.pa_locks[member]:
            mod = self.__module(self, path)
            self.loaded_modules[path] = mod
            #psiginf('name: ' + mod.name)
            #self.pa_locks[member].notify_all()

    def __modulegone(self, path, member):
        path = str(path)

        #psiggot("Got D-Bus signal: " + member)
        #psiginf("path: " + path)

        with self.pa_locks[member]:
            if path in self.loaded_modules:
                del self.loaded_modules[path]
            else:
                #uhhhhhhh
                pass
            self.pa_locks[member].notify_all()

    def cmd(self, cmd):
        print(cmd, file=self.pacmd.stdin, flush=True)

    def load_module(self, module, params={}, wait=True):
        module = 'module-' + module
        for key, value in params.items():
            if type(value) == bool:
                params[key] = str(int(value))
            elif type(value) in [list, tuple]:
                params[key] = ','.join(value)
            elif type(value) != str:
                params[key] = str(value)

        with self.pa_locks['NewModule']:
            path = str(self.__core.LoadModule(module, params))
            #mod = self.__module(self, path)
            #self.loaded_modules[path] = mod
            #self.pa_locks['NewModule'].notify_all()
            if wait:
                self.pa_locks['NewModule'].wait_for(lambda: path in self.loaded_modules)

    def __connect_to_signal(self, signal_name, function):
        self.__core.ListenForSignal(signal_name, [])
        signal_name = signal_name[signal_name.rfind('.')+1:]
        pulse_signal_thread.connect_signal(self.__core, signal_name, function)

    def __init__(self):
        self.__dbus = self.__core_dbus = self.__core = self.__props = None
        self.pa_locks = {
            'ModuleRemoved':    threadlocks.signal_cond(),
            'NewSink':          threadlocks.signal_cond(),
            'NewSource':        threadlocks.signal_cond(),
            'NewModule':        threadlocks.signal_cond(),
            'SinkRemoved':      threadlocks.signal_cond(),
            'SourceRemoved':    threadlocks.signal_cond(),
        }

    def __connect(self):
        try:
            lookup_dbus = dbus_session.get_object('org.PulseAudio1', '/org/pulseaudio/server_lookup1')
        except dbus.exceptions.DBusException as e:
            if e._dbus_error_name == "org.freedesktop.DBus.Error.ServiceUnknown":
                self.__start()
                lookup_dbus = dbus_session.get_object('org.PulseAudio1', '/org/pulseaudio/server_lookup1')
            else:
                raise

        lookup = dbus.Interface(lookup_dbus, 'org.freedesktop.DBus.Properties')
        # Pulseaudio's way of doing D-Bus is different.
        self.__dbus = dbus.connection.Connection(lookup.Get('org.PulseAudio.ServerLookup1', "Address"))
        self.__core_dbus = self.__dbus.get_object(object_path='/org/pulseaudio/core1')
        self.__core = dbus.Interface(self.__core_dbus, 'org.PulseAudio.Core1')
        self.__props = dbus.Interface(self.__core_dbus, 'org.freedesktop.DBus.Properties')

        self.__connect_to_signal("org.PulseAudio.Core1.ModuleRemoved", self.__modulegone)
        self.__connect_to_signal("org.PulseAudio.Core1.NewSink", self.__newdev)
        self.__connect_to_signal("org.PulseAudio.Core1.NewSource", self.__newdev)
        self.__connect_to_signal("org.PulseAudio.Core1.SinkRemoved", self.__devgone)
        self.__connect_to_signal("org.PulseAudio.Core1.SourceRemoved", self.__devgone)
        self.__connect_to_signal("org.PulseAudio.Core1.NewModule", self.__newmodule)



    def __start(self):
        with pushd(os.path.realpath('pulse')):
            with open('daemon.conf.in', mode='r+t', encoding='utf-8') as daemoncfg_f:
                daemoncfg_in = daemoncfg_f.read()
            daemoncfg_cp = ConfigParser()
            daemoncfg_cp.read_string('[root]\n' + daemoncfg_in)
            daemoncfg_cp['root']['default-script-file'] = os.getcwd() + '/startup.pa'
            with open('daemon.conf', mode='w+t', encoding='utf-8') as daemoncfg_f, io.StringIO() as daemoncfg_io:
                daemoncfg_cp.write(daemoncfg_io)
                daemoncfg_io.seek(0)
                daemoncfg_io.readline()
                daemoncfg_f.write(daemoncfg_io.read())

        clientcfg_abs = os.path.abspath(os.path.realpath('pulse/client.conf'))
        daemoncfg_abs = os.path.abspath(os.path.realpath('pulse/daemon.conf'))
        with pushd(os.path.realpath(os.path.expanduser('~/.config/pulse'))):
            clientcfg_rel = os.path.relpath(clientcfg_abs)
            daemoncfg_rel = os.path.relpath(daemoncfg_abs)
            try:
                clientcfg_target_abs = os.path.abspath(os.path.realpath(os.readlink('client.conf')))
            except FileNotFoundError:
                clientcfg_target_abs = None
            except OSError:
                os.unlink('client.conf')
                clientcfg_target_abs = None
            try:
                daemoncfg_target_abs = os.path.abspath(os.path.realpath(os.readlink('daemon.conf')))
            except FileNotFoundError:
                daemoncfg_target_abs = None
            except OSError:
                os.unlink('daemon.conf')
                daemoncfg_target_abs = None
            if clientcfg_target_abs != clientcfg_abs:
                if clientcfg_target_abs != None:
                    os.unlink('client.conf')
                os.symlink(clientcfg_rel, 'client.conf')
            if daemoncfg_target_abs != daemoncfg_abs:
                if daemoncfg_target_abs != None:
                    os.unlink('daemon.conf')
                os.symlink(daemoncfg_rel, 'daemon.conf')
        subprocess.run(['pulseaudio',
            '--start',  # Start server
            '-D',       # Daemonize
            #'--log-target=stderr',
            #'-L', 'module-dbus-protocol',
            #'-n'        # Do not load any startup scripts
            ])

        sleep(3)

    def connect(self, only_if_running=False):
        self.devices = dict()
        self.devpathmap = dict()
        #self.warmup_modules = dict()
        self.loaded_modules = dict()

        try:
            self.__core.not_a_real_method()
        except dbus.exceptions.DBusException as e:
            if e._dbus_error_name in ["org.freedesktop.DBus.Error.ServiceUnknown", 'org.freedesktop.DBus.Error.Disconnected']:
                self.__core = None
        except AttributeError:
            self.__core = None
        if (self.__core != None) or ((only_if_running == True) and (len(getpids('pulseaudio')) <= 0)):
            return

        self.__connect()

        modules = type_dbus_to_python(self.__props.Get('org.PulseAudio.Core1', 'Modules'))
        for module in modules:
            module = self.__module(self, module)
            self.loaded_modules[module.path] = module


        sources = list(self.__props.Get('org.PulseAudio.Core1', 'Sources'))
        sinks = list(self.__props.Get('org.PulseAudio.Core1', 'Sinks'))
        for source in sources:
            try:
                source = self.__pa_device(self, str(source), 'NewSource')
            except not_yet_implemented:
                pass
            self.devices[source.pulse_name_internal] = source
            self.devpathmap[source.path] = weakref.proxy(source)
        for sink in sinks:
            try:
                sink = self.__pa_device(self, str(sink), 'NewSink')
            except not_yet_implemented:
                pass
            self.devices[sink.pulse_name_internal] = sink
            self.devpathmap[sink.path] = weakref.proxy(sink)

    def start(self):

        self.connect()

        self.pacmd = subprocess.Popen('pacmd', stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, bufsize=1)
        fcntl.fcntl(self.pacmd.stdout, fcntl.F_SETFL, fcntl.fcntl(self.pacmd.stdout, fcntl.F_GETFL) | os.O_NONBLOCK)
        fcntl.fcntl(self.pacmd.stderr, fcntl.F_SETFL, fcntl.fcntl(self.pacmd.stderr, fcntl.F_GETFL) | os.O_NONBLOCK)

    def reset(self, only_if_running=False):

        self.connect(only_if_running)

        for dev in self.devices.items():
            if (dev.pulse_name_internal == 'auto_null') or (dev.pulse_name_internal[dev.pulse_name_internal.rfind('.')+1:] == 'monitor'):
                continue
            dev.remove()

    def create_input(self, pulse_name, idstr, num_channels=2, autoconnect=False, channel_map=None):
        with ladish.room_locks['PortAppeared'].exit_when(lambda: (jack_name in ladish.graph) and (len(ladish[jack_name].ports) >= num_channels)), self.pa_locks['NewSource']:
            jack_name = "pa_capture_" + idstr
            pulse_name_internal = "JACK_" + idstr
            params={'source_name': pulse_name_internal,
                    'channels': num_channels,
                    'connect': autoconnect,
                    'client_name': jack_name}
            if channel_map != None:
                params['channel_map'] = channel_map
            self.load_module('jack-source', params=params, wait=False)

            self.pa_locks['NewSource'].wait_for(lambda: pulse_name_internal in self.devices)

            stream = self.devices[pulse_name_internal]
            self.devices[pulse_name_internal] = weakref.proxy(stream)

            stream.set_pulse_name(pulse_name)

        stream._consume_client(ladish[jack_name])
        ladish[jack_name] = stream

        return stream

    def create_output(self, pulse_name, idstr, num_channels=2, autoconnect=False, channel_map=None):
        with ladish.room_locks['PortAppeared'].exit_when(lambda: (jack_name in ladish.graph) and (len(ladish[jack_name].ports) >= num_channels)), self.pa_locks['NewSink']:
            jack_name = "pa_playback_" + idstr
            pulse_name_internal = "JACK_" + idstr
            params={'sink_name': pulse_name_internal,
                    'channels': num_channels,
                    'connect': autoconnect,
                    'client_name': jack_name}
            if channel_map != None:
                params['channel_map'] = channel_map
            self.load_module('jack-sink', params=params, wait=False)

            self.pa_locks['NewSink'].wait_for(lambda: pulse_name_internal in self.devices)

            stream = self.devices[pulse_name_internal]
            self.devices[pulse_name_internal] = weakref.proxy(stream)

            stream.set_pulse_name(pulse_name)

        stream._consume_client(ladish[jack_name])
        stream.set_mute(False)
        stream.set_volume(100)
        ladish[jack_name] = stream

        return stream

    def set_default_input(self, source):
        # cannot be set via dbus if not previously set somewhere else
        try:
            self.__props.Set('org.PulseAudio.Core1', 'FallbackSource', dbus.ObjectPath(source.path))
        except dbus.exceptions.DBusException as e:
            if e._dbus_error_name != "org.PulseAudio.Core1.NoSuchPropertyError":
                raise
            self.cmd('set-default-source ' + source.pulse_name_internal)
        # It would seem there is currently no way to set this with dbus if it has not already been set


    def set_default_output(self, sink):
        # cannot be set via dbus if not previously set somewhere else
        try:
            self.__props.Set('org.PulseAudio.Core1', 'FallbackSink', dbus.ObjectPath(sink.path))
        except dbus.exceptions.DBusException as e:
            if e._dbus_error_name != "org.PulseAudio.Core1.NoSuchPropertyError":
                raise
            self.cmd('set-default-sink ' + sink.pulse_name_internal)

    def stop(self):
        subprocess.run(['pulseaudio', '-k'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
