#!/usr/bin/env python

# TODOs:
# Implement non-templated rooms or custom templates in ladish, use them here
# Full graph tracking
# Turn this into a daemon? D-Bus service with tray applet(s) for volume control and easy gladish/pavucontrol access? (WIP)
# MIDI stuff?
# JACK monitors on pulseaudio side?
# Figure out pulseaudio filters and role ducking
# Implement device proplist updating over dbus in pulse
# Conditional lock timeouts (WIP)
# Other ports on usb audio?
# HDMI audio?
# Use this as a basis for a ladish module?
# Exception subclasses (WIP)
# Actual center channel isolation for 2.0 to 5.1 upmixing

from pprint import pprint
import dbus
import subprocess, os, signal, sys, codecs
from distutils.spawn import find_executable as which
from time import sleep
from gi.repository import GLib as glib
from dbus.mainloop.glib import DBusGMainLoop as gmainloop
import dbus.service
import threading
import weakref
import inspect
import fcntl
import pyudev

from audio_control import *

applet = trayicons.trayapplet()
udev_context = pyudev.Context()

dbus_name_parts = ['oss', 'kitsinger', 'ladistitcher']
dbus_name_base = '.'.join(dbus_name_parts)
dbus_path_base = '/' + '/'.join(dbus_name_parts)

class dbus_service_class:

    def run(self):
        self.bus_name = dbus.service.BusName(dbus_name_base, dbus_session)
        self.dbus_control = self.service_object(self.bus_name)

    class NotYetImplemented(dbus.DBusException):
        _dbus_error_name = dbus_name_base + '.NotYetImplemented'

    class service_object(dbus.service.Object):
        object_path = dbus_path_base + '/Service'

        def __init__(self, conn):
            super().__init__(conn, self.object_path)

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
        def Halt(self):
            raise NotYetImplemented

        @dbus.service.method(iface_name, in_signature='', out_signature='')
        def Kill(self):
            raise NotYetImplemented

        # Signals
        ######################
        @dbus.service.signal(iface_name, signature='s')
        def StatusChanged(self, status):
            pass

        @dbus.service.signal(iface_name, signature='')
        def CleanExit(self):
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

dbus_service = dbus_service_class()

class jalv:

    def __init__(self, lv2name):
        self.lv2 = lv2name
        self.control = dict()

    def set_control(self, param, value):
        self.control[param] = value

    def get_cmd(self):
        cmd = 'jalv'
        for key, value in self.control.items():
            cmd += ' -c ' + key + '=' + str(value)
        cmd += ' ' + self.lv2
        return cmd

def bye(retcode=0):
    dbus_dispatch_loop.quit()
    dbus_client_loop.quit()
    applet.gtkstop()
    sys.exit(retcode)

def sigint_handler(signal, frame):
    bye(signal)

# Kills everything, even D-Bus daemons. Does not continue running.
def abort():
    pstatus('Killing audio system and related daemons...')
    killall('ladishd')
    killall('jmcore')
    killall('ladiconfd')
    killall('pulseaudio')
    killall('jackdbus')
    killall('jackd')
    bye()

# Kills pulseaudio, stops ladish and jack
def halt():
    pstatus('Stopping audio systems...')
    pulse.stop()
    ladish.stop()

# Deinitializes pulseaudio, stops ladish and jack
def stop():
    pstatus('Deinitializing audio systems...')
    pulse.reset()
    ladish.stop()

def start():
    pstatus('Starting ladish D-Bus session...')
    ladish.start()

    pstatus('Starting Pulseaudio daemon...')
    pulse.start()

# TODO: detect connection status for individual interfaces
def connect(only_if_running=False):
    pstatus('Grabbing D-Bus sessions...')
    pulse.connect(only_if_running)
    ladish.connect(only_if_running)

def alsa_refresh():
    pstatus('Refreshing ALSA...')
    subprocess.run(['alsactl', '-L', 'kill', 'rescan'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(['alsactl', '-L', 'restore'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(['alsactl', '-L', 'nrestore'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def alsa_config():
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

def alsa_config_jack(extern_present=False):
    pstatus('Configuring ALSA...')
    with pushd(os.path.realpath(os.path.expanduser('~/.config/audio/alsa'))), open('jackports.conf', mode='w+t', encoding='utf-8') as ajportcfg:

        ajportcfg.write('onboard_out {\n')
        for key, item in ladish['Onboard Playback'].ports.items():
            ajportcfg.write('  ' + key + ' "' + item.jmcore_client + ':' + item.jmcore_name + '"\n')
        ajportcfg.write('}\n\n')

        ajportcfg.write('onboard_in {\n')
        for key, item in ladish['Onboard Capture'].ports.items():
            ajportcfg.write('  ' + key + ' "' + item.jmcore_client + ':' + item.jmcore_name + '"\n')
        ajportcfg.write('}\n\n')

        ajportcfg.write('upmixer40 {\n')
        for key, item in ladish['2.0 to 4.0 upmixer'].ports.items():
            ajportcfg.write('  ' + key + ' "' + item.jmcore_client + ':' + item.jmcore_name + '"\n')
        ajportcfg.write('}\n\n')

        if extern_present:
            ajportcfg.write('extern_out {\n')
            for key, item in ladish['External Playback'].ports.items():
                ajportcfg.write('  ' + key + ' "' + item.jmcore_client + ':' + item.jmcore_name + '"\n')
            ajportcfg.write('}\n\n')

            ajportcfg.write('extern_in {\n')
            for key, item in ladish['External Capture'].ports.items():
                ajportcfg.write('  ' + key + ' "' + item.jmcore_client + ':' + item.jmcore_name + '"\n')
            ajportcfg.write('}\n\n')

            ajportcfg.write('upmixer51 {\n')
            for key, item in ladish['2.0 to 5.1 upmixer'].ports.items():
                ajportcfg.write('  ' + key + ' "' + item.jmcore_client + ':' + item.jmcore_name + '"\n')
            ajportcfg.write('}\n\n')

    alsa_refresh()

def jack_config(extern_present=False):
    pstatus('Performing JACK offline configuration...')
    ladish.set_engine_param('driver', 'alsa')
    if extern_present:
        ladish.set_driver_param('device', 'extern')
    else:
        ladish.set_driver_param('device', 'onboard')
    ladish.set_driver_param('capture')
    ladish.set_driver_param('playback')
    ladish.set_driver_param('rate', 48000)
    ladish.set_driver_param('period', 1024)
    ladish.set_driver_param('nperiods', 2)
    ladish.set_driver_param('hwmon', False)
    ladish.set_driver_param('hwmeter', False)
    ladish.set_driver_param('duplex', True)
    ladish.set_driver_param('softmode', False)
    ladish.set_driver_param('monitor', False)
    ladish.set_driver_param('dither', 'n')
    ladish.set_driver_param('inchannels', 2)
    if extern_present:
        ladish.set_driver_param('outchannels', 6)
    else:
        ladish.set_driver_param('outchannels', 4)
    ladish.set_driver_param('shorts', False)
    ladish.set_driver_param('input-latency')
    ladish.set_driver_param('output-latency')
    ladish.set_driver_param('midi-driver')
    ladish.set_engine_param('name')
    ladish.set_engine_param('realtime', True)
    ladish.set_engine_param('temporary', False)
    ladish.set_engine_param('client-timeout', 500)

def jack_plumbing(extern_present=False):
    pstatus('Taking care of some JACK plumbing...')

    sysout = ladish['Hardware Playback']
    sysin = ladish['Hardware Capture']

    pa_int_mic = pulse.devices["JACK_int_mic"]
    pa_int_40 = pulse.devices["JACK_int_40"]
    pa_int_20 = pulse.devices["JACK_int_20"]
    if extern_present:
        pa_ext_mic = pulse.devices["JACK_ext_mic"]
        pa_ext_51 = pulse.devices["JACK_ext_51"]
        pa_ext_20 = pulse.devices["JACK_ext_20"]

    if extern_present:
        sysout.rename('External Playback')
        sysin.rename('External Capture')
    else:
        sysout.rename('Onboard Playback')
        sysin.rename('Onboard Capture')

    sysout['playback_1'].rename('front-left')
    sysout['playback_2'].rename('front-right')
    sysout['playback_3'].rename('rear-left')
    sysout['playback_4'].rename('rear-right')
    if extern_present:
        sysout['playback_5'].rename('front-center')
        sysout['playback_6'].rename('lfe')
    sysin['capture_1'].rename('front-left')
    sysin['capture_2'].rename('front-right')

    if extern_present:
        sysin.set_pos(1320, 1120)
        pa_ext_mic.set_pos(1460, 1120)
        pa_ext_51.set_pos(1320, 950)
        sysout.set_pos(1760, 950)
        pa_ext_20.set_pos(1320, 1060)
        pa_int_40.set_pos(1320, 1200)
        pa_int_20.set_pos(1320, 1280)
        pa_int_mic.set_pos(1460, 1340)
    else:
        pa_int_40.set_pos(1360, 960)
        sysout.set_pos(1720, 960)
        pa_int_20.set_pos(1360, 1070)
        sysin.set_pos(1360, 1270)
        pa_int_mic.set_pos(1720, 1270)

    if extern_present:
        psubstatus('Bridging onboard audio...')

        app_onboard_out = ladish.run_app('Onboard Playback', 'alsa_out -d onboard -c 4 -j "Onboard Playback" -q 4', wait_on_ports=4)

        app_onboard_in = ladish.run_app('Onboard Capture', 'alsa_in -d onboard -c 2 -j "Onboard Capture" -q 4', wait_on_ports=2)

        app_onboard_out['playback_1'].rename('front-left')
        app_onboard_out['playback_2'].rename('front-right')
        app_onboard_out['playback_3'].rename('rear-left')
        app_onboard_out['playback_4'].rename('rear-right')
        app_onboard_in['capture_1'].rename('front-left')
        app_onboard_in['capture_2'].rename('front-right')

        pa_int_40['front-left' ].connect(app_onboard_out['front-left' ])
        pa_int_40['front-right'].connect(app_onboard_out['front-right'])
        pa_int_40['rear-left'  ].connect(app_onboard_out['rear-left'  ])
        pa_int_40['rear-right' ].connect(app_onboard_out['rear-right' ])
        app_onboard_in['front-left' ].connect(pa_int_mic['front-left' ])
        app_onboard_in['front-right'].connect(pa_int_mic['front-right'])

        app_onboard_out.set_pos(1760, 1200)
        app_onboard_in.set_pos(1320, 1340)


    psubstatus('Setting up stereo to quadraphonic upmixer...')
    with ladish.room_locks['PortAppeared']:
        upmixer40 = ladish.create_room('2.0 to 4.0 upmixer', 'Stereo to 4.0 Upmixer')
        def check():
            if len(upmixer40.ports) < 6:
                return False
            return True
        ladish.room_locks['PortAppeared'].wait_for(check)

    upmixer40['Capture']['left' ].connect(upmixer40['Playback']['front-left' ])
    upmixer40['Capture']['right'].connect(upmixer40['Playback']['front-right'])
    upmixer40['Capture']['left' ].connect(upmixer40['Playback']['rear-left'  ])
    upmixer40['Capture']['right'].connect(upmixer40['Playback']['rear-right' ])
    pa_int_20['front-left' ].connect(upmixer40['left' ])
    pa_int_20['front-right'].connect(upmixer40['right'])

    if extern_present:
        upmixer40['front-left' ].connect(app_onboard_out['front-left' ])
        upmixer40['front-right'].connect(app_onboard_out['front-right'])
        upmixer40['rear-left'  ].connect(app_onboard_out['rear-left'  ])
        upmixer40['rear-right' ].connect(app_onboard_out['rear-right' ])

        upmixer40.set_pos(1600, 1280)
    else:
        upmixer40['front-left' ].connect(sysout['front-left' ])
        upmixer40['front-right'].connect(sysout['front-right'])
        upmixer40['rear-left'  ].connect(sysout['rear-left'  ])
        upmixer40['rear-right' ].connect(sysout['rear-right' ])

        upmixer40.set_pos(1530, 1070)

    upmixer40['Capture' ].set_pos(1400, 1150)
    upmixer40['Playback'].set_pos(1690, 1150)

    if extern_present:
        psubstatus('Initializing stereo to 5.1 upmixer...')
        with ladish.room_locks['PortAppeared']:
            upmixer51 = ladish.create_room('2.0 to 5.1 upmixer', 'Stereo to 5.1 Upmixer')
            def check():
                if len(upmixer51.ports) < 8:
                    return False
                return True
            ladish.room_locks['PortAppeared'].wait_for(check)

        upmixer51['Capture']['left' ].connect(upmixer51['Playback']['front-left' ])
        upmixer51['Capture']['right'].connect(upmixer51['Playback']['front-right'])
        upmixer51['Capture']['left' ].connect(upmixer51['Playback']['rear-left'  ])
        upmixer51['Capture']['right'].connect(upmixer51['Playback']['rear-right' ])
        pa_ext_20['front-left' ].connect(upmixer51['left' ])
        pa_ext_20['front-right'].connect(upmixer51['right'])
        upmixer51['front-left'  ].connect(sysout['front-left'  ])
        upmixer51['front-right' ].connect(sysout['front-right' ])
        upmixer51['rear-left'   ].connect(sysout['rear-left'   ])
        upmixer51['rear-right'  ].connect(sysout['rear-right'  ])
        upmixer51['front-center'].connect(sysout['front-center'])
        upmixer51['lfe'         ].connect(sysout['lfe'         ])

        upmixer51.set_pos(1600, 1060)

        upmixer51['Capture' ].set_pos(1330, 960)
        upmixer51['Playback'].set_pos(1790, 960)

        pstatus('Starting pulseaudio 2.0 to 5.1 LFE processing programs...')

        lv2_trnsntdsgnr = jalv('http://calf.sourceforge.net/plugins/TransientDesigner')
        lv2_trnsntdsgnr.set_control('level_in', '0.61')
        lv2_trnsntdsgnr.set_control('level_out', '0.475')
        lv2_trnsntdsgnr.set_control('mix', '0.8')
        lv2_trnsntdsgnr.set_control('attack_boost', '0.44')
        lv2_trnsntdsgnr.set_control('release_time', '21.46')
        lv2_trnsntdsgnr.set_control('release_boost', '0.26')
        lv2_trnsntdsgnr.set_control('lopass', '164')
        lv2_trnsntdsgnr.set_control('lp_mode', '3')
        lv2_trnsntdsgnr.set_control('lookahead', '28')
        app_trnsntdsgnr = upmixer51.run_app('Transient Designer', lv2_trnsntdsgnr.get_cmd(), wait_on_ports=4)

        upmixer51['Capture']['left' ].connect(app_trnsntdsgnr['in_l'])
        upmixer51['Capture']['right'].connect(app_trnsntdsgnr['in_r'])

        app_trnsntdsgnr.set_pos(1420, 1110)

        lv2_bassenhance = jalv('http://calf.sourceforge.net/plugins/BassEnhancer')
        lv2_bassenhance.set_control('level_in', '0.82')
        lv2_bassenhance.set_control('amount', '1.32')
        lv2_bassenhance.set_control('drive', '5')
        lv2_bassenhance.set_control('freq', '160')
        lv2_bassenhance.set_control('floor_active', '1')
        lv2_bassenhance.set_control('floor', '15')
        lv2_bassenhance.set_control('blend', '-4')
        app_bassenhance = upmixer51.run_app('Bass Enhancer', lv2_bassenhance.get_cmd(), wait_on_ports=4)

        app_bassenhance['out_l'].connect(upmixer51['Playback']['lfe'])
        app_bassenhance['out_r'].connect(upmixer51['Playback']['lfe'])

        app_bassenhance.set_pos(1660, 1110)

        lv2_lowpassfilt = jalv('http://calf.sourceforge.net/plugins/Filter')
        lv2_lowpassfilt.set_control('mode', '1')
        lv2_lowpassfilt.set_control('freq', '194')
        lv2_lowpassfilt.set_control('res', '2.7')
        lv2_lowpassfilt.set_control('inertia', '13')
        app_lowpassfilt = upmixer51.run_app('Low Pass Filter', lv2_lowpassfilt.get_cmd(), wait_on_ports=4)

        app_trnsntdsgnr['out_l'].connect(app_lowpassfilt['in_l'])
        app_trnsntdsgnr['out_r'].connect(app_lowpassfilt['in_r'])
        app_lowpassfilt['out_l'].connect(app_bassenhance['in_l'])
        app_lowpassfilt['out_r'].connect(app_bassenhance['in_r'])

        app_lowpassfilt.set_pos(1550, 1110)

        # TODO: Some sort of center channel isolation, rather than just downmixing
        # See: http://www.moitah.net/download/latest/dsp_centercut.zip
        # See: center cut from virtualdub
        lv2_centerchiso = jalv('http://calf.sourceforge.net/plugins/StereoTools')
        lv2_centerchiso.set_control('mode', '5')
        lv2_centerchiso.set_control('level_out', '0.5')
        lv2_centerchiso.set_control('slev', '-1')
        app_centerchiso = upmixer51.run_app('Center Isolator', lv2_centerchiso.get_cmd(), wait_on_ports=4)

        upmixer51['Capture']['left' ].connect(app_centerchiso['in_l'])
        upmixer51['Capture']['right'].connect(app_centerchiso['in_r'])
        app_centerchiso['out_l'].connect(upmixer51['Playback']['front-center'])
        app_centerchiso['out_r'].connect(upmixer51['Playback']['front-center'])

        app_centerchiso.set_pos(1520, 1040)

def ladish_config():
    pstatus('Performing ladish offline configuration...')
    ladish.set_param('/org/ladish/daemon/shell', 'bash')
    ladish.set_param('/org/ladish/daemon/notify', True)
    ladish.set_param('/org/ladish/daemon/studio_autostart', False)

def pulse_config_online(extern_present=False):
    pstatus('Performing Pulseaudio online configuration...')
    psubstatus('Creating JACK sinks and sources...')
    pa_int_mic = pulse.create_input("Microphone (onboard)", "int_mic", autoconnect=not(extern_present))
    pa_int_40 = pulse.create_output("Audio Out (onboard) (Quadraphonic)", "int_40", num_channels=4, channel_map=['front-left', 'front-right', 'rear-left', 'rear-right'], autoconnect=not(extern_present))
    pa_int_20 = pulse.create_output("Audio Out (onboard) (Stereo)", "int_20")
    if extern_present:
        pa_ext_mic = pulse.create_input("Microphone (external)", "ext_mic", autoconnect=True)
        pa_ext_51 = pulse.create_output("Audio Out (external) (5.1 surround sound)", "ext_51", num_channels=6, channel_map=['front-left', 'front-right', 'rear-left', 'rear-right', 'front-center', 'lfe'], autoconnect=True)
        pa_ext_20 = pulse.create_output("Audio Out (external) (Stereo)", "ext_20")

    psubstatus('Setting default sinks...')
    if extern_present:
        pulse.set_default_output(pa_ext_20)
        pulse.set_default_input(pa_ext_mic)
    else:
        pulse.set_default_output(pa_int_20)
        pulse.set_default_input(pa_int_mic)

def main():
    global applet

    os.chdir(os.path.dirname(os.path.realpath(__file__)))

    signal.signal(signal.SIGINT, sigint_handler)

    # Quick and dirty logging of stdout and stderr to file
    # while still actually printing to stdout an stderr
    logfile = open('ladistitcher.log', 'w')

    termout = codecs.getwriter('utf-8')(sys.stdout.detach())
    termerr = codecs.getwriter('utf-8')(sys.stderr.detach())

    class lsout:
        def write(self, message):
            print(message, file=termout, flush=True, end='')
            print(message, file=logfile, flush=True, end='')

        def flush(self):
            print('', file=termout, flush=True, end='')
            print('', file=logfile, flush=True, end='')

    class lserr:
        def write(self, message):
            print(message, file=termerr, flush=True, end='')
            print(message, file=logfile, flush=True, end='')

        def flush(self):
            print('', file=termerr, flush=True, end='')
            print('', file=logfile, flush=True, end='')

    sys.stdout = lsout()
    sys.stderr = lserr()

    if sys.stdin.__class__.__name__ != 'CDbgInputStream':
        sys.stdin = codecs.getwriter('utf-8')(sys.stdin.detach())

    if sys.argv[-1] not in ['abort', 'kill', 'halt', 'stop', 'deinit']:
        dbus_service.run()
        applet.gtkmain()

    dispatch_thread = threading.Thread(target=dbus_dispatch_loop.run, name='dbus_dispatch')
    dispatch_thread.start()

    if sys.argv[-1] in ['abort', 'kill']:
        abort()

    # TODO: Don't start daemons if not running until after arg parsing is complete
    connect()

    # TODO: D-Bus signal for this
    if sys.argv[-1] in ['stop', 'deinit']:
        stop()
        bye()

    # TODO: D-Bus signal for this
    if sys.argv[-1] == 'halt':
        halt()
        bye()

    # TODO: Pulse deinitialization shouldn't start pulse here
    stop()

    pstatus('Determining external interface presence...')
    udev_enum = udev_context.list_devices(subsystem='sound', ID_VENDOR='0d8c', ID_MODEL_ID='0102')
    is_extern_present = bool(len(list(udev_enum)))
    if is_extern_present:
        psubstatus('External interface present.')
    else:
        psubstatus('External interface not present.')

    alsa_config()


    setup(is_extern_present)


def setup(extern_present):
    connect()

    jack_config(extern_present)
    ladish_config()

    stop()

    alsa_refresh()

    start()

    pulse_config_online(extern_present)

    jack_plumbing(extern_present)

    alsa_config_jack(extern_present)

    pstatus('Waiting for queued tasks to wrap up...')
    sleep(3)

    pstatus("Done!")

    #mainloop.quit()

if __name__ == '__main__':
    main()

# potential applet icons:
#
# mate:
# mdu-category-peripheral
# mdu-category-multipath
# dconf-editor
#
# oxygen:
# emblem-mounted
#
# Azenis:
# emblem-sound
# audio-card
#
# deepin:
# audio-volume-*
# audio-volume-*-symbolic
#
# elementary:
# audio-volume-*-symbolic
#
# Flattr:
# audio-volume-*
# emblem-mounted
#
# clarity-dark_canus, clarity-lux_violaceus:
# audio-volume-*
