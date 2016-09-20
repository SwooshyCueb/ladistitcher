import dbus, subprocess, os, signal, io
from dbus.mainloop.glib import DBusGMainLoop as gmainloop
from gi.repository import GLib as glib
from contextlib import contextmanager
from . import threadlocks

glib.threads_init()

dbus_dispatch_loop = glib.MainLoop()
gmainloop(set_as_default=True)

dbus_session = dbus.SessionBus()

pcolor = True
print_signals = True

try:
    os.get_terminal_size()
except OSError:
    pcolor = False

ladistitcher_dir = os.path.dirname(os.path.realpath(__file__))

def getpids(name):
    try:
        pids = subprocess.check_output(['pidof',name]).split()
    except subprocess.CalledProcessError:
        pids = []

    return pids

def killall(name):
    pids = getpids(name)

    for pid in pids:
        try:
            os.kill(int(pid), signal.SIGKILL)
        except ProcessLookupError:
            pass

def pstatus(status):
    if pcolor:
        print('\033[38;5;135m', end='')
    print('==>', end='')
    if pcolor:
        print('\033[0m', end='')
    print(' ', end='')
    if pcolor:
        print('\033[38;5;15m', end='')
    print(status, end='')
    if pcolor:
        print('\033[0m', end='')
    print('', flush=True)

def psubstatus(status):
    if pcolor:
        print('\033[38;5;97m', end='')
    print('=>', end='')
    if pcolor:
        print('\033[0m', end='')
    print(' ', end='')
    if pcolor:
        print('\033[38;5;252m', end='')
    print(status, end='')
    if pcolor:
        print('\033[0m', end='')
    print('', flush=True)

def psiggot(status):
    if print_signals == False:
        return
    if pcolor:
        print('\033[38;5;49m', end='')
    print('==>', end='')
    if pcolor:
        print('\033[0m', end='')
    print(' ', end='')
    if pcolor:
        print('\033[38;5;15m', end='')
    print(status, end='')
    if pcolor:
        print('\033[0m', end='')
    print('', flush=True)

def psiginf(status):
    if print_signals == False:
        return
    if pcolor:
        print('\033[38;5;114m', end='')
    print('=>', end='')
    if pcolor:
        print('\033[0m', end='')
    print(' ', end='')
    if pcolor:
        print('\033[38;5;252m', end='')
    print(status, end='')
    if pcolor:
        print('\033[0m', end='')
    print('', flush=True)

def dbus_bytearr_to_str(arr):
    arr = list(arr)
    ret = ''
    while arr[-1] == 0:
        del arr[-1]
    for char in arr:
        ret += str(char)
    return ret

@contextmanager
def pushd(new_dir):
    old_dir = os.getcwd()
    os.chdir(new_dir)
    yield
    os.chdir(old_dir)

def str_to_dbus_bytearr(string):
    ret = list()
    for char in string:
        ret.append(dbus.Byte(ord(char)))
    ret.append(dbus.Byte(0))
    return dbus.Array(ret)

def signalprint(*args, sender=None, destination=None, interface=None, member=None, path=None, message=None):
    psiggot("D-Bus signal received!")
    psiginf('sender: ' + str(sender))
    psiginf('destination: ' + str(destination))
    psiginf('interface: ' + str(interface))
    psiginf('member: ' + str(member))
    psiginf('path: ' + str(path))
    psiginf('message: ' + str(message))
    argn = 1
    for arg in args:
        psiginf("arg" + str(argn) + ": " + str(arg))
        argn += 1

def type_dbus_to_python(value):
    ints = [
        dbus.Int16,
        dbus.UInt16,
        dbus.Int32,
        dbus.UInt32,
        dbus.Int64,
        dbus.UInt64,
    ]
    strs = [
        dbus.String,
        dbus.ObjectPath,
    ]
    ret = None
    if type(value) in ints:
        ret = int(value)
    elif type(value) in strs:
        ret = str(value)
    elif type(value) == dbus.Double:
        ret = float(value)
    elif type(value) == dbus.Boolean:
        ret = bool(value)
    elif type(value) == dbus.Byte:
        ret = 'byte: ' + str(int(value)) + ' (0 ' + str(value) + ')'
    elif type(value) in [dbus.Array, dbus.Struct]:
        if str(value.signature) == 'y' and type(value) == dbus.Array:
            ret = dbus_bytearr_to_str(value)
        else:
            ret = []
            for item in list(value):
                ret.append(type_dbus_to_python(item))
    elif type(value) == dbus.Dictionary:
        ret = dict()
        for key, value in dict(value).items():
            ret[type_dbus_to_python(key)] = type_dbus_to_python(value)
    else:
        ret = value

    return ret

def dbus_signal_connect(interface, signal, callback, **args):
    iface = interface.dbus_interface
    path = interface.object_path
    # There's probably an easier way to do this
    g = interface._obj._bus._signal_recipients_by_object_path
    if path in g:
        g = g[path]
        if iface in g:
            g = g[iface]
            if signal in g:
                g = g[signal]
                if len(g) > 1:
                    print('More than one signal handler found for ' + signal + ' in ' + path + ', interface '+ iface, flush=True)
                    return
                g[0].remove()
    interface.connect_to_signal(signal, callback, **args)




class computeonce:

    def __init__(self, func):
        self.__doc__ = getattr(func, '__doc__')
        self.func = func

    def __get__(self, obj, cls):
        if obj is None:
            return self
        value = obj.__dict__[self.func.__name__] = self.func(obj)
        return value

from . import ladi
ladish = ladi.studio()
from . import pa
pulse = pa.pulse()
