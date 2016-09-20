# Not using this yet
'''
class a2jmidi_dbus:
    # There should only ever be one of these

    __a2jm_dbus = None
    __control = None

    def __connect(self):
        self.__a2jm_dbus = bus.get_object('org.gna.home.a2jmidid', '/')
        self.__control = dbus.Interface(self.__a2jm_dbus, 'org.gna.home.a2jmidid.control')

    def connect(self, only_if_running=False):
        try:
            self.__control.not_a_real_method()
        except dbus.exceptions.DBusException as e:
            if e._dbus_error_name == "org.freedesktop.DBus.Error.ServiceUnknown":
                self.__control = None
        except AttributeError:
            self.__control = None
        if (self.__control == None) and ((only_if_running == False) or (len(getpids('a2jmidid')) > 0)):
            self.__connect()

    def start(self):
        self.connect()
        self.__control.start()

    def stop(self):
        self.connect(only_if_running=True)
        if self.__control != None:
            try:
                self.__control.stop()
            except dbus.exceptions.DBusException:
                pass

    def kill(self):
        self.stop()
        if self.__control != None:
            try:
                self.__control.exit()
            except dbus.exceptions.DBusException:
                pass
        killall('a2jmidid')
'''