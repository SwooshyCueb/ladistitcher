'''
from .common import *
import dbus, dbus.service
import subprocess, threading

from gi.repository import GLib as glib

dbus_name_parts = ['oss', 'kitsinger', 'ladistitcher']
dbus_name_base = '.'.join(dbus_name_parts)
dbus_path_base = '/' + '/'.join(dbus_name_parts)

class NotYetImplemented(dbus.DBusException):
    _dbus_error_name = dbus_name_base + '.NotYetImplemented'

class ladistitcher_error(Exception):
    pass

class ladistitcher(dbus.service.Object):
    object_path = dbus_path_base + '/Service'
    dbus_service_thread = None
    dbus_service_loop = None
    dbus_service_conn = None

    class state:
        status = 'Stopped'

    class alsa:
        @staticmethod
        def refresh(print_status=True):
            if print_status:
                pstatus('Refreshing ALSA...')
            subprocess.run(['alsactl', '-L', 'kill', 'rescan'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(['alsactl', '-L', 'restore'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(['alsactl', '-L', 'nrestore'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        @staticmethod
        def init(print_status=True):
            if print_status:
                pstatus('Configuring ALSA...')
            with pushd(os.path.realpath('alsa')), open('asound.conf', mode='w+t', encoding='utf-8') as alsacfg:
                print('locations {', file=alsacfg)
                print('  cfgdir ' + os.getcwd(), file=alsacfg)
                print('}', file=alsacfg)
                print('', file=alsacfg)

                print('@hooks [{', file=alsacfg)
                print('  func load', file=alsacfg)
                print('  files [{', file=alsacfg)
                print('    @func concat', file=alsacfg)
                print('    strings [', file=alsacfg)
                print('      {', file=alsacfg)
                print('        @func refer', file=alsacfg)
                print('        name locations.cfgdir', file=alsacfg)
                print('      }', file=alsacfg)
                print('      "/asound.conf.d/"', file=alsacfg)
                print('    ]', file=alsacfg)
                print('  }]', file=alsacfg)
                print('}]', file=alsacfg)

            asound_abs = os.path.abspath(os.path.realpath('alsa/asound.conf'))
            with pushd(os.path.realpath(os.path.expanduser('~'))):
                asound_rel = os.path.relpath(asound_abs)
                try:
                    os.unlink('.asoundrc')
                except FileNotFoundError:
                    pass
                os.symlink(asound_rel, '.asoundrc')


    def __init__(self):
        pass

    def run_dbus_service(self):
        if self.dbus_service_loop != None and self.dbus_service_loop.is_running():
            return False

        if self.dbus_service_conn == None:
            gcontext = glib.MainContext.new()
            self.dbus_service_loop = glib.MainLoop(context=gcontext)

            sbus = dbus.SessionBus(mainloop=self.dbus_service_loop)
            self.dbus_service_conn = dbus.service.BusName(dbus_name_base, sbus)

        self.dbus_service_thread = threading.Thread(target=self.dbus_service_loop.run, name='dbus_service')

        dbus.service.Object.__init__(self, self.dbus_service_conn, self.object_path)

        self.dbus_service_thread.start()

        # TODO: implement timeout
        while self.dbus_service_loop.is_running == False:
            pass

    def stop_dbus_service(self):
        if self.dbus_service_loop == None or not self.dbus_service_loop.is_running():
            return False

        self.dbus_service_loop.quit()

        # TODO: timeout
        if threading.current_thread() != self.dbus_service_thread:
            self.dbus_service_thread.join()

    # Control Interface
    ######################################
    iface_name = dbus_name_base + '.Control'

    # Methods
    ######################
    @dbus.service.method(iface_name, in_signature='', out_signature='s')
    def GetStatus(self):
        raise NotYetImplemented

    @dbus.service.method(iface_name, in_signature='', out_signature='')
    def Start(self):
        raise NotYetImplemented

    @dbus.service.method(iface_name, in_signature='', out_signature='')
    def Deinitialize(self):
        raise NotYetImplemented

    @dbus.service.method(iface_name, in_signature='', out_signature='')
    def Reinitialize(self):
        raise NotYetImplemented

    @dbus.service.method(iface_name, in_signature='', out_signature='')
    def Stop(self):
        raise NotYetImplemented

    @dbus.service.method(iface_name, in_signature='', out_signature='')
    def Kill(self):
        raise NotYetImplemented

    @dbus.service.method(iface_name, in_signature='', out_signature='')
    def Exit(self):
        raise NotYetImplemented

    # Signals
    ######################
    @dbus.service.signal(iface_name, signature='s')
    def StatusChanged(self, status):
        pass

    @dbus.service.signal(iface_name, signature='')
    def DaemonExit(self):
        pass

    @dbus.service.signal(iface_name, signature='s')
    def Mayday(self, message):
        pass

    # Configuration Interface
    ######################################
    iface_name = dbus_name_base + '.Config'

    # Methods
    ######################
    @dbus.service.method(iface_name, in_signature='sv', out_signature='')
    def Set(self, param, value):
        raise NotYetImplemented

    @dbus.service.method(iface_name, in_signature='s', out_signature='v')
    def Get(self, param):
        raise NotYetImplemented

    @dbus.service.method(iface_name, in_signature='', out_signature='a{sv}')
    def GetAll(self):
        raise NotYetImplemented

    @dbus.service.method(iface_name, in_signature='', out_signature='')
    def FlushConfig(self):
        raise NotYetImplemented

    @dbus.service.method(iface_name, in_signature='', out_signature='b')
    def ReloadConfig(self):
        raise NotYetImplemented

    # Signals
    ######################
    @dbus.service.signal(iface_name, signature='sv')
    def ConfigChanged(self, param, value):
        pass

    @dbus.service.signal(iface_name, signature='')
    def ConfigSaved(self):
        pass

    @dbus.service.signal(iface_name, signature='')
    def ConfigLoaded(self):
        pass
'''
