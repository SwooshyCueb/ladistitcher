import dbus, subprocess, os, signal, io, threading, atexit
from gi.repository import GLib as glib

from .common import *

class ls_thread_call:
    def __init__(self, func, *args, **kwargs):
        self.func = func
        self.args = args
        self.kwargs = kwargs

class ls_thread:
    def __init__(self, autostart=True):
        self.dispatcher = glib.MainContext.new()
        self.mainloop = glib.MainLoop(context=self.dispatcher)
        self.thread = threading.Thread(target=self.mainloop.run)

        if autostart:
            self.thread.start()

    def __del__(self):
        self.stop()
        atexit.unregister(self.stop)

    def start(self):
        self.thread.start()
        while not self.mainloop.is_running():
            pass

        atexit.unregister(self.stop)
        atexit.register(self.stop)

    def stop(self):
        if self.mainloop.is_running():
            self.mainloop.quit()
            self.thread.join()

    def dispatch_call(self, func, *args, **kwargs):
        call = ls_thread_call_args(func, *args, **kwargs)

        self.dispatcher.invoke_full(glib.PRIORITY_DEFAULT, self.__run_call, call)

    def dispatch_call_priority(self, priority, func, *args, **kwargs):
        call = ls_thread_call_args(func, *args, **kwargs)

        self.dispatcher.invoke_full(priority, self.__run_call, call)

    def __run_call(self, call):
        func = call.func
        args = call.args
        kwargs = call.kwargs

        func(*args, **kwargs)

        return False

    def __run_recurring(self, call):
        func = call.func
        args = call.args
        kwargs = call.kwargs

        return func(*args, **kwargs)


class default_context_thread(ls_thread):
    def __init__(self, autostart=True):
        self.dispatcher = glib.MainContext.default()
        self.mainloop = glib.MainLoop()
        self.thread = threading.Thread(target=self.mainloop.run)


class dbus_signal_handler_thread(ls_thread):

    class __signal_data:
        def __init__(self, name, handler, args):
            self.signal_name = name
            self.signal_handler = handler
            self.signal_args = args

    def __handler_run(self, signal_data):
        signal_name = signal_data.signal_name
        signal_handler = signal_data.signal_handler
        signal_args = signal_data.signal_args
        signal_handler(*signal_args, member=signal_name)

        return False

    def connect_signal(self, interface, signal_name, handler_function):
        iface_name = iface = interface.dbus_interface
        dbus_path = interface.object_path

        # I'm almost certain there is an elegant way of doing this
        traversal = interface._obj._bus._signal_recipients_by_object_path
        if dbus_path in traversal:
            traversal = traversal[dbus_path]
            if iface_name in traversal:
                traversal = traversal[iface_name]
                if signal_name in traversal:
                    traversal = traversal[signal_name]
                    if len(traversal) > 1:
                        raise RuntimeError('dbus signal connection error')
                    elif len(traversal) == 1:
                        g[0].remove()

        def handle_signal(*args, signal):
            signal_data = self.__signal_data(signal, handler_function, args)
            self.dispatcher.invoke_full(glib.PRIORITY_DEFAULT, self.__handler_run, signal_data)


        interface.connect_to_signal(signal_name, handle_signal, member_keyword="signal")
