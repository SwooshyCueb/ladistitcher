import os
os.environ['NO_AT_BRIDGE'] = '1'
del os

from gi.repository import GLib as glib
from dbus.mainloop.glib import DBusGMainLoop as gmainloop

glib.threads_init()
dbus_native_loop = gmainloop(set_as_default=True)

del glib
del gmainloop

from .common import *
from . import ladi
from . import pa
from . import threadlocks
from . import trayicons
