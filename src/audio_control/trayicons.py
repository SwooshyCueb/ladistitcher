import sys, os, threading, subprocess

import gi, codecs, io
from pprint import pprint

gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')

from gi.repository import Gtk as gtk
from gi.repository import GLib as glib
from gi.repository import Gio as gio
from gi.repository import Gdk as gdk

import alsaaudio
from time import sleep

from .common import *

class trayapplet:

    class icons:

        class onboard:
            active = dict()
            muted = dict()

        class extern:
            active = dict()
            muted = dict()

        apps = dict()

        #emblem = gio.Emblem.new(gio.FileIcon.new(gio.File.new_for_path(ladistitcher_dir + '/icons/status/plugged-emblem.svg')))
        emblem = gio.Emblem.new(gio.FileIcon.new(gio.File.new_for_path(ladistitcher_dir + '/icons/Usb-01.svg')))

        for step in range(0, 101, 10):
            onboard.active[step] = gio.FileIcon.new(gio.File.new_for_path(ladistitcher_dir + '/icons/status/audio-volume-' + str(step).zfill(3) + '.svg'))
            onboard.muted[step] = gio.FileIcon.new(gio.File.new_for_path(ladistitcher_dir + '/icons/status/audio-volume-' + str(step).zfill(3) + '-muted.svg'))

            extern.active[step] = gio.EmblemedIcon.new(onboard.active[step], emblem)
            extern.muted[step] = gio.EmblemedIcon.new(onboard.muted[step], emblem)

    class tray:
        onboard = gtk.StatusIcon()
        extern = gtk.StatusIcon()

    class menu:
        class icons:
            pavucontrol = gio.FileIcon.new(gio.File.new_for_path(ladistitcher_dir + '/icons/pavucontrol.svg'))
            gladish = gio.FileIcon.new(gio.File.new_for_path(ladistitcher_dir + '/icons/jack.svg'))

        class options:
            class ladi_options:
                item = gtk.MenuItem()
                menu = gtk.Menu()

                show_notifications = gtk.CheckMenuItem()
                show_notifications.set_label("Show notifications")
                show_notifications.show()
                menu.append(show_notifications)

                item.set_label("LADI options")
                item.set_submenu(menu)
                item.show()

            class jack_options:
                item = gtk.MenuItem()
                menu = gtk.Menu()

                item.set_label("JACK options")
                item.set_submenu(menu)
                #item.show()

            class pulse_options:
                item = gtk.MenuItem()
                menu = gtk.Menu()

                item.set_label("Pulseaudio options")
                item.set_submenu(menu)
                #item.show()

            item = gtk.MenuItem()
            menu = gtk.Menu()

            monitor_for_plug = gtk.CheckMenuItem()
            monitor_for_plug.set_label("Watch for external device hotplug")
            monitor_for_plug.show()
            menu.append(monitor_for_plug)

            relaunch_apps = gtk.CheckMenuItem()
            relaunch_apps.set_label("Relaunch crashed apps")
            relaunch_apps.show()
            menu.append(relaunch_apps)

            sep_1 = gtk.SeparatorMenuItem()
            sep_1.show()
            menu.append(sep_1)

            menu.append(ladi_options.item)
            menu.append(jack_options.item)
            menu.append(pulse_options.item)

            item.set_label("Options")
            item.set_submenu(menu)
            item.show()

        class actions:
            class icons:
                audio_card = gio.FileIcon.new(gio.File.new_for_path(ladistitcher_dir + '/icons/audio-card.svg'))
                reinitialize = gio.FileIcon.new(gio.File.new_for_path(ladistitcher_dir + '/icons/refresh.svg'))
                stop = gio.FileIcon.new(gio.File.new_for_path(ladistitcher_dir + '/icons/stop.svg'))
                start = gio.FileIcon.new(gio.File.new_for_path(ladistitcher_dir + '/icons/play.svg'))
                unplug = gio.FileIcon.new(gio.File.new_for_path(ladistitcher_dir + '/icons/unplug.svg'))

            item = gtk.MenuItem()
            menu = gtk.Menu()

            restart_proxies = gtk.ImageMenuItem()
            restart_proxies.set_image(gtk.Image.new_from_gicon(icons.audio_card, gtk.IconSize.SMALL_TOOLBAR))
            restart_proxies.set_label('Restart ALSA proxies')
            restart_proxies.show()
            restart_proxies.set_sensitive(False)
            menu.append(restart_proxies)

            prep_for_plug = gtk.ImageMenuItem()
            prep_for_plug.set_image(gtk.Image.new_from_gicon(icons.unplug, gtk.IconSize.SMALL_TOOLBAR))
            prep_for_plug.set_label("Prepare for external interface unplug")
            prep_for_plug.show()
            prep_for_plug.set_sensitive(False)
            menu.append(prep_for_plug)

            start = gtk.ImageMenuItem()
            start.set_image(gtk.Image.new_from_gicon(icons.start, gtk.IconSize.SMALL_TOOLBAR))
            start.set_label("Start audio systems")
            #start.show()
            menu.append(start)

            stop = gtk.ImageMenuItem()
            stop.set_image(gtk.Image.new_from_gicon(icons.stop, gtk.IconSize.SMALL_TOOLBAR))
            stop.set_label("Stop audio systems")
            #stop.show()
            menu.append(stop)

            reinitialize = gtk.ImageMenuItem()
            reinitialize.set_image(gtk.Image.new_from_gicon(icons.reinitialize, gtk.IconSize.SMALL_TOOLBAR))
            reinitialize.set_label("Reinitialize audio systems")
            reinitialize.show()
            reinitialize.set_sensitive(False)
            menu.append(reinitialize)

            item.set_label("Actions")
            item.set_submenu(menu)
            item.show()

        widget = gtk.Menu()

        mute = gtk.CheckMenuItem()
        mute.set_label("Mute")
        mute.show()
        widget.append(mute)

        sep_1 = gtk.SeparatorMenuItem()
        sep_1.show()

        widget.append(sep_1)

        pavucontrol = gtk.ImageMenuItem()
        pavucontrol.set_image(gtk.Image.new_from_gicon(icons.pavucontrol, gtk.IconSize.SMALL_TOOLBAR))
        pavucontrol.set_label("Launch Pulseaudio Volume Control")
        pavucontrol.show()
        widget.append(pavucontrol)

        gladish = gtk.ImageMenuItem()
        gladish.set_image(gtk.Image.new_from_gicon(icons.gladish, gtk.IconSize.SMALL_TOOLBAR))
        gladish.set_label("Launch gladish")
        gladish.show()
        widget.append(gladish)

        sep_2 = gtk.SeparatorMenuItem()
        sep_2.show()

        widget.append(sep_2)

        widget.append(options.item)

        widget.append(actions.item)

        popup = widget.popup

    class mixers:
        onboard = alsaaudio.Mixer(device='onboard')
        extern = None

    def __init__(self):

        self.tray.onboard.set_from_gicon(self.icons.onboard.muted[100])
        self.tray.onboard.set_tooltip_markup('<b>Onboard audio</b>\n<small>Master: 100%</small>')
        self.tray.onboard.connect('popup-menu', self.on_right_click)
        self.tray.onboard.connect('button-press-event', self.on_button_press)
        self.tray.onboard.connect('scroll-event', self.on_scroll)

        self.menu.mute.connect('toggled', self.toggle_mute)
        self.menu.pavucontrol.connect('activate', self.launch_pavucontrol)
        self.menu.gladish.connect('activate', self.launch_gladish)

    def on_right_click(self, icon, event_button, event_time):
        self.tempmixer = None
        if icon == self.tray.onboard:
            mixer = alsaaudio.Mixer(device='onboard')
        else:
            mixer = alsaaudio.Mixer(device='extern', control='Speaker')

        self.menu.mute.set_active(bool(mixer.getmute()[0]))
        self.tempmixer = mixer
        self.menu.popup(None, None, gtk.StatusIcon.position_menu, icon, event_button, event_time)

    def on_button_press(self, icon, event_button):
        if event_button.button == 2:
            if icon == self.tray.onboard:
                self.tempmixer = alsaaudio.Mixer(device='onboard')
            else:
                self.tempmixer = alsaaudio.Mixer(device='extern', control='Speaker')

            self.toggle_mute()

    def toggle_mute(self, *a):
        if self.tempmixer == None:
            return
        self.tempmixer.setmute(not self.tempmixer.getmute()[0])
        self.update_status()

    def on_scroll(self, icon, event_scroll):
        if icon == self.tray.onboard:
            mixer = alsaaudio.Mixer(device='onboard')
        else:
            mixer = alsaaudio.Mixer(device='extern', control='Speaker')

        vol = mixer.getvolume()[0]
        if event_scroll.direction == gdk.ScrollDirection.UP:
            mixer.setvolume(max(0, min(vol+3, 100)))
        elif event_scroll.direction == gdk.ScrollDirection.DOWN:
            mixer.setvolume(max(0, min(vol-3, 100)))

        self.update_status()


    def update_status(self):
        self.mixers.onboard = alsaaudio.Mixer(device='onboard')
        vol = self.mixers.onboard.getvolume()[0]
        mute = self.mixers.onboard.getmute()[0]
        if mute:
            self.tray.onboard.set_tooltip_markup('<b>Onboard audio</b>\n<small>Master: <b>Muted</b> (' + str(vol) + '%)</small>')
            self.tray.onboard.set_from_gicon(self.icons.onboard.muted[round(vol, -1)])
        else:
            self.tray.onboard.set_tooltip_markup('<b>Onboard audio</b>\n<small>Master: <b>' + str(vol) + '%</b></small>')
            self.tray.onboard.set_from_gicon(self.icons.onboard.active[round(vol, -1)])

        try:
            self.mixers.extern = alsaaudio.Mixer(device='extern', control='Speaker')
        except alsaaudio.ALSAAudioError:
            return

        vol = self.mixers.extern.getvolume()[0]
        mute = self.mixers.extern.getmute()[0]
        if mute:
            self.tray.extern.set_tooltip_markup('<b>USB audio</b>\n<small>Master: <b>Muted</b> (' + str(vol) + '%)</small>')
            self.tray.extern.set_from_gicon(self.icons.extern.muted[round(vol, -1)])
        else:
            self.tray.extern.set_tooltip_markup('<b>USB audio</b>\n<small>Master: <b>' + str(vol) + '%</b></small>')
            self.tray.extern.set_from_gicon(self.icons.extern.active[round(vol, -1)])

    def launch_pavucontrol(self, *a):
        subprocess.Popen(['pavucontrol'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def launch_gladish(self, *a):
        subprocess.Popen(['gladish'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


    def detect_volume_change(self):
        while gtk.main_level():
            self.update_status()
            sleep(5)

    def gtkmain(self):
        self.gtkthread = threading.Thread(target=gtk.main, name='gtkmain')
        self.gtkthread.start()
        self.iconthread = threading.Thread(target=self.detect_volume_change, name='iconupd')
        self.iconthread.start()

    def gtkstop(self):
        gtk.main_quit()

