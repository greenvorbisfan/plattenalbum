#!/usr/bin/python3
# -*- coding: utf-8 -*-
#
# mpdevil - MPD Client.
# Copyright 2020 Martin Wagner <martin.wagner.dev@gmail.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 3 of the License.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307
# USA

# MPRIS interface based on 'mpDris2' (master 19.03.2020) by Jean-Philippe Braun <eon@patapon.info>, Mantas Mikulėnas <grawity@gmail.com>

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Notify', '0.7')
from gi.repository import Gtk, Gio, Gdk, GdkPixbuf, Pango, GObject, GLib, Notify
from mpd import MPDClient, base as MPDBase
import requests
from bs4 import BeautifulSoup, Comment
import threading
import locale
import gettext
import datetime
import os
import sys
import re

# MPRIS modules
import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
import base64

DATADIR='@datadir@'
NAME='mpdevil'
VERSION='@version@'
PACKAGE=NAME.lower()
COVER_REGEX="^\.?(album|cover|folder|front).*\.(gif|jpeg|jpg|png)$"

#################
# lang settings #
#################

try:
	locale.setlocale(locale.LC_ALL, '')
	locale.bindtextdomain(PACKAGE, '@datadir@/locale')
	gettext.bindtextdomain(PACKAGE, '@datadir@/locale')
	gettext.textdomain(PACKAGE)
	gettext.install(PACKAGE, localedir='@datadir@/locale')
except locale.Error:
	print('  cannot use system locale.')
	locale.setlocale(locale.LC_ALL, 'C')
	gettext.textdomain(PACKAGE)
	gettext.install(PACKAGE, localedir='@datadir@/locale')

#########
# MPRIS #
#########

class MPRISInterface(dbus.service.Object):  # TODO emit Seeked if needed
	__introspect_interface="org.freedesktop.DBus.Introspectable"
	__prop_interface=dbus.PROPERTIES_IFACE

	# python dbus bindings don't include annotations and properties
	MPRIS2_INTROSPECTION="""<node name="/org/mpris/MediaPlayer2">
	  <interface name="org.freedesktop.DBus.Introspectable">
	    <method name="Introspect">
	      <arg direction="out" name="xml_data" type="s"/>
	    </method>
	  </interface>
	  <interface name="org.freedesktop.DBus.Properties">
	    <method name="Get">
	      <arg direction="in" name="interface_name" type="s"/>
	      <arg direction="in" name="property_name" type="s"/>
	      <arg direction="out" name="value" type="v"/>
	    </method>
	    <method name="GetAll">
	      <arg direction="in" name="interface_name" type="s"/>
	      <arg direction="out" name="properties" type="a{sv}"/>
	    </method>
	    <method name="Set">
	      <arg direction="in" name="interface_name" type="s"/>
	      <arg direction="in" name="property_name" type="s"/>
	      <arg direction="in" name="value" type="v"/>
	    </method>
	    <signal name="PropertiesChanged">
	      <arg name="interface_name" type="s"/>
	      <arg name="changed_properties" type="a{sv}"/>
	      <arg name="invalidated_properties" type="as"/>
	    </signal>
	  </interface>
	  <interface name="org.mpris.MediaPlayer2">
	    <method name="Raise"/>
	    <method name="Quit"/>
	    <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="false"/>
	    <property name="CanQuit" type="b" access="read"/>
	    <property name="CanRaise" type="b" access="read"/>
	    <property name="HasTrackList" type="b" access="read"/>
	    <property name="Identity" type="s" access="read"/>
	    <property name="DesktopEntry" type="s" access="read"/>
	    <property name="SupportedUriSchemes" type="as" access="read"/>
	    <property name="SupportedMimeTypes" type="as" access="read"/>
	  </interface>
	  <interface name="org.mpris.MediaPlayer2.Player">
	    <method name="Next"/>
	    <method name="Previous"/>
	    <method name="Pause"/>
	    <method name="PlayPause"/>
	    <method name="Stop"/>
	    <method name="Play"/>
	    <method name="Seek">
	      <arg direction="in" name="Offset" type="x"/>
	    </method>
	    <method name="SetPosition">
	      <arg direction="in" name="TrackId" type="o"/>
	      <arg direction="in" name="Position" type="x"/>
	    </method>
	    <method name="OpenUri">
	      <arg direction="in" name="Uri" type="s"/>
	    </method>
	    <signal name="Seeked">
	      <arg name="Position" type="x"/>
	    </signal>
	    <property name="PlaybackStatus" type="s" access="read">
	      <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="true"/>
	    </property>
	    <property name="LoopStatus" type="s" access="readwrite">
	      <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="true"/>
	    </property>
	    <property name="Rate" type="d" access="readwrite">
	      <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="true"/>
	    </property>
	    <property name="Shuffle" type="b" access="readwrite">
	      <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="true"/>
	    </property>
	    <property name="Metadata" type="a{sv}" access="read">
	      <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="true"/>
	    </property>
	    <property name="Volume" type="d" access="readwrite">
	      <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="false"/>
	    </property>
	    <property name="Position" type="x" access="read">
	      <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="false"/>
	    </property>
	    <property name="MinimumRate" type="d" access="read">
	      <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="true"/>
	    </property>
	    <property name="MaximumRate" type="d" access="read">
	      <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="true"/>
	    </property>
	    <property name="CanGoNext" type="b" access="read">
	      <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="true"/>
	    </property>
	    <property name="CanGoPrevious" type="b" access="read">
	      <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="true"/>
	    </property>
	    <property name="CanPlay" type="b" access="read">
	      <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="true"/>
	    </property>
	    <property name="CanPause" type="b" access="read">
	      <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="true"/>
	    </property>
	    <property name="CanSeek" type="b" access="read">
	      <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="true"/>
	    </property>
	    <property name="CanControl" type="b" access="read">
	      <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="false"/>
	    </property>
	  </interface>
	</node>"""

	# MPRIS allowed metadata tags
	allowed_tags={
		'mpris:trackid': dbus.ObjectPath,
		'mpris:length': dbus.Int64,
		'mpris:artUrl': str,
		'xesam:album': str,
		'xesam:albumArtist': list,
		'xesam:artist': list,
		'xesam:asText': str,
		'xesam:audioBPM': int,
		'xesam:comment': list,
		'xesam:composer': list,
		'xesam:contentCreated': str,
		'xesam:discNumber': int,
		'xesam:firstUsed': str,
		'xesam:genre': list,
		'xesam:lastUsed': str,
		'xesam:lyricist': str,
		'xesam:title': str,
		'xesam:trackNumber': int,
		'xesam:url': str,
		'xesam:useCount': int,
		'xesam:userRating': float,
	}

	def __init__(self, window, client, settings):
		dbus.service.Object.__init__(self, dbus.SessionBus(), "/org/mpris/MediaPlayer2")
		self._name="org.mpris.MediaPlayer2.mpdevil"

		self._bus=dbus.SessionBus()
		self._uname=self._bus.get_unique_name()
		self._dbus_obj=self._bus.get_object("org.freedesktop.DBus", "/org/freedesktop/DBus")
		self._dbus_obj.connect_to_signal("NameOwnerChanged", self._name_owner_changed_callback, arg0=self._name)

		self._window=window
		self._client=client
		self._settings=settings
		self._metadata={}

		# connect
		self._client.emitter.connect("state", self._on_state_changed)
		self._client.emitter.connect("current_song_changed", self._on_song_changed)
		self._client.emitter.connect("volume_changed", self._on_volume_changed)
		self._client.emitter.connect("repeat", self._on_loop_changed)
		self._client.emitter.connect("single", self._on_loop_changed)
		self._client.emitter.connect("random", self._on_random_changed)

	def acquire_name(self):
		self._bus_name=dbus.service.BusName(self._name, bus=self._bus, allow_replacement=True, replace_existing=True)

	def release_name(self):
		if hasattr(self, "_bus_name"):
			del self._bus_name

	def update_metadata(self):  # TODO
		"""
		Translate metadata returned by MPD to the MPRIS v2 syntax.
		http://www.freedesktop.org/wiki/Specifications/mpris-spec/metadata
		"""

		mpd_meta=self._client.wrapped_call("currentsong")
		self._metadata={}

		for tag in ('album', 'title'):
			if tag in mpd_meta:
				self._metadata['xesam:%s' % tag]=mpd_meta[tag]

		if 'id' in mpd_meta:
			self._metadata['mpris:trackid']="/org/mpris/MediaPlayer2/Track/%s" % mpd_meta['id']

		if 'time' in mpd_meta:
			self._metadata['mpris:length']=int(mpd_meta['time']) * 1000000

		if 'date' in mpd_meta:
			self._metadata['xesam:contentCreated']=mpd_meta['date'][0:4]

		if 'track' in mpd_meta:
			# TODO: Is it even *possible* for mpd_meta['track'] to be a list?
			if type(mpd_meta['track']) == list and len(mpd_meta['track']) > 0:
				track=str(mpd_meta['track'][0])
			else:
				track=str(mpd_meta['track'])

			m=re.match('^([0-9]+)', track)
			if m:
				self._metadata['xesam:trackNumber']=int(m.group(1))
				# Ensure the integer is signed 32bit
				if self._metadata['xesam:trackNumber'] & 0x80000000:
					self._metadata['xesam:trackNumber'] += -0x100000000
			else:
				self._metadata['xesam:trackNumber']=0

		if 'disc' in mpd_meta:
			# TODO: Same as above. When is it a list?
			if type(mpd_meta['disc']) == list and len(mpd_meta['disc']) > 0:
				disc=str(mpd_meta['disc'][0])
			else:
				disc=str(mpd_meta['disc'])

			m=re.match('^([0-9]+)', disc)
			if m:
				self._metadata['xesam:discNumber']=int(m.group(1))

		if 'artist' in mpd_meta:
			if type(mpd_meta['artist']) == list:
				self._metadata['xesam:artist']=mpd_meta['artist']
			else:
				self._metadata['xesam:artist']=[mpd_meta['artist']]

		if 'composer' in mpd_meta:
			if type(mpd_meta['composer']) == list:
				self._metadata['xesam:composer']=mpd_meta['composer']
			else:
				self._metadata['xesam:composer']=[mpd_meta['composer']]

		# Stream: populate some missings tags with stream's name
		if 'name' in mpd_meta:
			if 'xesam:title' not in self._metadata:
				self._metadata['xesam:title']=mpd_meta['name']
			elif 'xesam:album' not in self._metadata:
				self._metadata['xesam:album']=mpd_meta['name']

		if 'file' in mpd_meta:
			song_file=mpd_meta['file']
			self._metadata['xesam:url']="file://"+os.path.join(self._settings.get_value("paths")[self._settings.get_int("active-profile")], song_file)
			cover=Cover(self._settings, mpd_meta)
			if cover.path is None:
				self._metadata['mpris:artUrl']=None
			else:
				self._metadata['mpris:artUrl']="file://"+cover.path

		# Cast self._metadata to the correct type, or discard it
		for key, value in self._metadata.items():
			try:
				self._metadata[key]=self.allowed_tags[key](value)
			except ValueError:
				del self._metadata[key]

	__root_interface="org.mpris.MediaPlayer2"
	__root_props={
		"CanQuit": (False, None),
		"CanRaise": (True, None),
		"DesktopEntry": ("mpdevil", None),
		"HasTrackList": (False, None),
		"Identity": ("mpdevil", None),
		"SupportedUriSchemes": (dbus.Array(signature="s"), None),
		"SupportedMimeTypes": (dbus.Array(signature="s"), None)
	}

	def __get_playback_status(self):
		status=self._client.wrapped_call("status")
		return {'play': 'Playing', 'pause': 'Paused', 'stop': 'Stopped'}[status['state']]

	def __set_loop_status(self, value):
		if value == "Playlist":
			self._client.wrapped_call("repeat", 1)
			self._client.wrapped_call("single", 0)
		elif value == "Track":
			self._client.wrapped_call("repeat", 1)
			self._client.wrapped_call("single", 1)
		elif value == "None":
			self._client.wrapped_call("repeat", 0)
			self._client.wrapped_call("single", 0)
		else:
			raise dbus.exceptions.DBusException("Loop mode %r not supported" % value)
		return

	def __get_loop_status(self):
		status=self._client.wrapped_call("status")
		if int(status['repeat']) == 1:
			if int(status.get('single', 0)) == 1:
				return "Track"
			else:
				return "Playlist"
		else:
			return "None"

	def __set_shuffle(self, value):
		self._client.wrapped_call("random", value)
		return

	def __get_shuffle(self):
		if int(self._client.wrapped_call("status")['random']) == 1:
			return True
		else:
			return False

	def __get_metadata(self):
		return dbus.Dictionary(self._metadata, signature='sv')

	def __get_volume(self):
		vol=float(self._client.wrapped_call("status").get('volume', 0))
		if vol > 0:
			return vol / 100.0
		else:
			return 0.0

	def __set_volume(self, value):
		if value >= 0 and value <= 1:
			self._client.wrapped_call("setvol", int(value * 100))
		return

	def __get_position(self):
		status=self._client.wrapped_call("status")
		if 'time' in status:
			current, end=status['time'].split(':')
			return dbus.Int64((int(current) * 1000000))
		else:
			return dbus.Int64(0)

	def __get_can_next_prev(self):
		status=self._client.wrapped_call("status")
		if status['state'] == "stop":
			return False
		else:
			return True

	__player_interface="org.mpris.MediaPlayer2.Player"
	__player_props={
		"PlaybackStatus": (__get_playback_status, None),
		"LoopStatus": (__get_loop_status, __set_loop_status),
		"Rate": (1.0, None),
		"Shuffle": (__get_shuffle, __set_shuffle),
		"Metadata": (__get_metadata, None),
		"Volume": (__get_volume, __set_volume),
		"Position": (__get_position, None),
		"MinimumRate": (1.0, None),
		"MaximumRate": (1.0, None),
		"CanGoNext": (__get_can_next_prev, None),
		"CanGoPrevious": (__get_can_next_prev, None),
		"CanPlay": (True, None),
		"CanPause": (True, None),
		"CanSeek": (True, None),
		"CanControl": (True, None),
	}

	__prop_mapping={
		__player_interface: __player_props,
		__root_interface: __root_props,
	}

	@dbus.service.method(__introspect_interface)
	def Introspect(self):
		return self.MPRIS2_INTROSPECTION

	@dbus.service.signal(__prop_interface, signature="sa{sv}as")
	def PropertiesChanged(self, interface, changed_properties, invalidated_properties):
		pass

	@dbus.service.method(__prop_interface, in_signature="ss", out_signature="v")
	def Get(self, interface, prop):
		getter, setter=self.__prop_mapping[interface][prop]
		if callable(getter):
			return getter(self)
		return getter

	@dbus.service.method(__prop_interface, in_signature="ssv", out_signature="")
	def Set(self, interface, prop, value):
		getter, setter=self.__prop_mapping[interface][prop]
		if setter is not None:
			setter(self, value)

	@dbus.service.method(__prop_interface, in_signature="s", out_signature="a{sv}")
	def GetAll(self, interface):
		read_props={}
		props=self.__prop_mapping[interface]
		for key, (getter, setter) in props.items():
			if callable(getter):
				getter=getter(self)
			read_props[key]=getter
		return read_props

	def update_property(self, interface, prop):
		getter, setter=self.__prop_mapping[interface][prop]
		if callable(getter):
			value=getter(self)
		else:
			value=getter
		self.PropertiesChanged(interface, {prop: value}, [])
		return value

	# Root methods
	@dbus.service.method(__root_interface, in_signature='', out_signature='')
	def Raise(self):
		self._window.present()
		return

	@dbus.service.method(__root_interface, in_signature='', out_signature='')
	def Quit(self):
		return

	# Player methods
	@dbus.service.method(__player_interface, in_signature='', out_signature='')
	def Next(self):
		self._client.wrapped_call("next")
		return

	@dbus.service.method(__player_interface, in_signature='', out_signature='')
	def Previous(self):
		self._client.wrapped_call("previous")
		return

	@dbus.service.method(__player_interface, in_signature='', out_signature='')
	def Pause(self):
		self._client.wrapped_call("pause", 1)
		return

	@dbus.service.method(__player_interface, in_signature='', out_signature='')
	def PlayPause(self):
		status=self._client.wrapped_call("status")
		if status['state'] == 'play':
			self._client.wrapped_call("pause", 1)
		else:
			self._client.wrapped_call("play")
		return

	@dbus.service.method(__player_interface, in_signature='', out_signature='')
	def Stop(self):
		self._client.wrapped_call("stop")
		return

	@dbus.service.method(__player_interface, in_signature='', out_signature='')
	def Play(self):
		self._client.wrapped_call("play")
		return

	@dbus.service.method(__player_interface, in_signature='x', out_signature='')
	def Seek(self, offset):  # TODO
		status=self._client.wrapped_call("status")
		current, end=status['time'].split(':')
		current=int(current)
		end=int(end)
		offset=int(offset) / 1000000
		if current + offset <= end:
			position=current + offset
			if position < 0:
				position=0
			self._client.wrapped_call("seekid", int(status['songid']), position)
			self.Seeked(position * 1000000)
		return

	@dbus.service.method(__player_interface, in_signature='ox', out_signature='')
	def SetPosition(self, trackid, position):
		song=self._client.wrapped_call("currentsong")
		# FIXME: use real dbus objects
		if str(trackid) != '/org/mpris/MediaPlayer2/Track/%s' % song['id']:
			return
		# Convert position to seconds
		position=int(position) / 1000000
		if position <= int(song['time']):
			self._client.wrapped_call("seekid", int(song['id']), position)
			self.Seeked(position * 1000000)
		return

	@dbus.service.signal(__player_interface, signature='x')
	def Seeked(self, position):
		return float(position)

	@dbus.service.method(__player_interface, in_signature='', out_signature='')
	def OpenUri(self):
		return

	def _on_state_changed(self, *args):
		self.update_property('org.mpris.MediaPlayer2.Player', 'PlaybackStatus')
		self.update_property('org.mpris.MediaPlayer2.Player', 'CanGoNext')
		self.update_property('org.mpris.MediaPlayer2.Player', 'CanGoPrevious')

	def _on_song_changed(self, *args):
		self.update_metadata()
		self.update_property('org.mpris.MediaPlayer2.Player', 'Metadata')

	def _on_volume_changed(self, *args):
		self.update_property('org.mpris.MediaPlayer2.Player', 'Volume')

	def _on_loop_changed(self, *args):
		self.update_property('org.mpris.MediaPlayer2.Player', 'LoopStatus')

	def _on_random_changed(self, *args):
		self.update_property('org.mpris.MediaPlayer2.Player', 'Shuffle')

	def _name_owner_changed_callback(self, name, old_owner, new_owner):
		if name == self._name and old_owner == self._uname and new_owner != "":
			try:
				pid=self._dbus_obj.GetConnectionUnixProcessID(new_owner)
			except:
				pid=None
			loop.quit()

#################################
# small general purpose widgets #
#################################

class IntEntry(Gtk.SpinButton):
	def __init__(self, default, lower, upper, step):
		Gtk.SpinButton.__init__(self)
		adj=Gtk.Adjustment(value=default, lower=lower, upper=upper, step_increment=step)
		self.set_adjustment(adj)

	def get_int(self):
		return int(self.get_value())

	def set_int(self, value):
		self.set_value(value)

class PixelSizedIcon(Gtk.Image):
	def __init__(self, icon_name, pixel_size):
		Gtk.Image.__init__(self)
		self.set_from_icon_name(icon_name, Gtk.IconSize.BUTTON)
		if pixel_size > 0:
			self.set_pixel_size(pixel_size)

class FocusFrame(Gtk.Overlay):
	def __init__(self):
		Gtk.Overlay.__init__(self)

		self._frame=Gtk.Frame()
		self._frame.set_no_show_all(True)

		# css
		style_context=self._frame.get_style_context()
		provider=Gtk.CssProvider()
		css=b"""* {border-color: @theme_selected_bg_color; border-width: 2px;}"""
		provider.load_from_data(css)
		style_context.add_provider(provider, 800)

		self.add_overlay(self._frame)
		self.set_overlay_pass_through(self._frame, True)

	def set_widget(self, widget):
		widget.connect("focus-in-event", self._on_focus_in_event)
		widget.connect("focus-out-event", self._on_focus_out_event)

	def _on_focus_in_event(self, *args):
		self._frame.show()

	def _on_focus_out_event(self, *args):
		self._frame.hide()

class SongPopover(Gtk.Popover):
	def __init__(self, song, relative, x, y):
		Gtk.Popover.__init__(self)
		rect=Gdk.Rectangle()
		rect.x=x
		# Gtk places popovers 26px above the given position for no obvious reasons, so I move them 26px
		rect.y=y+26
		rect.width = 1
		rect.height = 1
		self.set_pointing_to(rect)
		self.set_relative_to(relative)

		# Store
		# (tag, display-value, tooltip)
		store=Gtk.ListStore(str, str, str)

		# TreeView
		treeview=Gtk.TreeView(model=store)
		treeview.set_can_focus(False)
		treeview.set_search_column(-1)
		treeview.set_tooltip_column(2)
		treeview.set_headers_visible(False)
		sel=treeview.get_selection()
		sel.set_mode(Gtk.SelectionMode.NONE)

		frame=Gtk.Frame()
		frame.add(treeview)
		frame.set_property("border-width", 3)

		# Column
		renderer_text=Gtk.CellRendererText(width_chars=50, ellipsize=Pango.EllipsizeMode.MIDDLE, ellipsize_set=True)
		renderer_text_ralign=Gtk.CellRendererText(xalign=1.0)

		column_tag=Gtk.TreeViewColumn(_("MPD-Tag"), renderer_text_ralign, text=0)
		column_tag.set_property("resizable", False)
		treeview.append_column(column_tag)

		column_value=Gtk.TreeViewColumn(_("Value"), renderer_text, text=1)
		column_value.set_property("resizable", False)
		treeview.append_column(column_value)

		# packing
		self.add(frame)

		song=ClientHelper.song_to_str_dict(song)
		for tag, value in song.items():
			tooltip=value.replace("&", "&amp;")
			if tag == "time":
				store.append([tag+":", str(datetime.timedelta(seconds=int(value))), tooltip])
			elif tag == "last-modified":
				time=datetime.datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ')
				store.append([tag+":", time.strftime('%a %d %B %Y, %H:%M UTC'), tooltip])
			else:
				store.append([tag+":", value, tooltip])
		frame.show_all()

class Cover(object):
	def __init__(self, settings, song):
		self.path=None
		if song != {}:
			song_file=song["file"]

			active_profile=settings.get_int("active-profile")

			lib_path=settings.get_value("paths")[active_profile]
			regex_str=settings.get_value("regex")[active_profile]

			if regex_str == "":
				regex=re.compile(r''+COVER_REGEX+'', flags=re.IGNORECASE)
			else:
				try:
					artist=song["albumartist"]
				except:
					artist=""
				try:
					album=song["album"]
				except:
					album=""
				regex_str=regex_str.replace("%AlbumArtist%", artist)
				regex_str=regex_str.replace("%Album%", album)
				try:
					regex=re.compile(r''+regex_str+'', flags=re.IGNORECASE)
				except:
					print("illegal regex:", regex_str)

			if song_file is not None:
				head, tail=os.path.split(song_file)
				song_dir=os.path.join(lib_path, head)
				if os.path.exists(song_dir):
					for f in os.listdir(song_dir):
						if regex.match(f):
							self.path=os.path.join(song_dir, f)
							break

	def get_pixbuf(self, size):
		if self.path is None:
			self.path=Gtk.IconTheme.get_default().lookup_icon("media-optical", size, Gtk.IconLookupFlags.FORCE_SVG).get_filename()  # fallback cover
		return GdkPixbuf.Pixbuf.new_from_file_at_size(self.path, size, size)

######################
# MPD client wrapper #
######################

class ClientHelper():
	def song_to_str_dict(song):  # converts tags with multiple values to comma separated strings
		return_song=song
		for tag, value in return_song.items():
			if type(value) == list:
				return_song[tag]=(', '.join(value))
		return return_song

	def song_to_first_str_dict(song):  # extracts the first value of multiple value tags
		return_song=song
		for tag, value in return_song.items():
			if type(value) == list:
				return_song[tag]=value[0]
		return return_song

	def extend_song_for_display(song):
		base_song={"title": _("Unknown Title"), "track": "0", "disc": "", "artist": _("Unknown Artist"), "album": _("Unknown Album"), "duration": "0.0", "date": "", "genre": ""}
		base_song.update(song)
		base_song["human_duration"]=str(datetime.timedelta(seconds=int(float(base_song["duration"])))).lstrip("0").lstrip(":")
		return base_song

	def calc_display_length(songs):
		length=float(0)
		for song in songs:
			try:
				dura=float(song["duration"])
			except:
				dura=0.0
			length=length+dura
		return str(datetime.timedelta(seconds=int(length))).lstrip("0").lstrip(":")

class MpdEventEmitter(GObject.Object):
	__gsignals__={
		'update': (GObject.SignalFlags.RUN_FIRST, None, ()),
		'disconnected': (GObject.SignalFlags.RUN_FIRST, None, ()),
		'reconnected': (GObject.SignalFlags.RUN_FIRST, None, ()),
		'current_song_changed': (GObject.SignalFlags.RUN_FIRST, None, ()),
		'state': (GObject.SignalFlags.RUN_FIRST, None, (str,)),
		'elapsed_changed': (GObject.SignalFlags.RUN_FIRST, None, (float,float,)),
		'volume_changed': (GObject.SignalFlags.RUN_FIRST, None, (float,)),
		'playlist_changed': (GObject.SignalFlags.RUN_FIRST, None, (int,)),
		'repeat': (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
		'random': (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
		'single': (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
		'consume': (GObject.SignalFlags.RUN_FIRST, None, (bool,)),
		'audio': (GObject.SignalFlags.RUN_FIRST, None, (float,int,int,)),
		'bitrate': (GObject.SignalFlags.RUN_FIRST, None, (float,))
	}

	def __init__(self):
		super().__init__()

	# gsignals
	def do_update(self):
		pass

	def do_disconnected(self):
		pass

	def do_reconnected(self):
		pass

	def do_current_file_changed(self):
		pass

	def do_state(self, state):
		pass

	def do_elapsed_changed(self, elapsed, duration):
		pass

	def do_volume_changed(self, volume):
		pass

	def do_playlist_changed(self, version):
		pass

	def do_audio(self, sampelrate, bits, channels):
		pass

	def do_bitrate(self, rate):
		pass

class Client(MPDClient):
	def __init__(self, settings):
		MPDClient.__init__(self)

		# adding vars
		self._settings=settings
		self.emitter=MpdEventEmitter()
		self._last_status={}

		#connect
		self._settings.connect("changed::active-profile", self._on_settings_changed)

	def wrapped_call(self, name, *args):
		try:
			func=getattr(self, name)
		except:
			raise ValueError
		return func(*args)

	def start(self):
		if self._disconnected_loop():
			self.emitter.emit("disconnected")
			self._disconnected_timeout_id=GLib.timeout_add(1000, self._disconnected_loop)

	def connected(self):
		try:
			self.wrapped_call("ping")
			return True
		except:
			return False

	def files_to_playlist(self, files, mode="default"):  # modes: default, play, append, enqueue
		def append(files):
			for f in files:
				self.add(f)
		def play(files):
			if files != []:
				self.clear()
				for f in files:
					self.add(f)
				self.play()
		def enqueue(files):
			status=self.status()
			if status["state"] == "stop":
				play(files)
			else:
				self.moveid(status["songid"], 0)
				current_song_file=self.playlistinfo()[0]["file"]
				try:
					self.delete((1,))  # delete all songs, but the first. bad song index possible
				except:
					pass
				for f in files:
					if f == current_song_file:
						self.move(0, (len(self.playlistinfo())-1))
					else:
						self.add(f)
		if mode == "append":
			append(files)
		elif mode == "enqueue":
			enqueue(files)
		elif mode == "play":
			play(files)
		elif mode == "default":
			if self._settings.get_boolean("force-mode"):
				play(files)
			else:
				enqueue(files)

	def album_to_playlist(self, album, artist, year, mode="default"):
		songs=self.find("album", album, "date", year, self._settings.get_artist_type(), artist)
		self.files_to_playlist([song['file'] for song in songs], mode)

	def comp_list(self, *args):  # simulates listing behavior of python-mpd2 1.0
		native_list=self.list(*args)
		if len(native_list) > 0:
			if type(native_list[0]) == dict:
				return ([l[args[0]] for l in native_list])
			else:
				return native_list
		else:
			return([])

	def get_metadata(self, uri):
		meta_base=self.lsinfo(uri)[0]
		meta_extra=self.readcomments(uri)  # contains comment tag
		meta_base.update(meta_extra)
		return meta_base

	def _main_loop(self, *args):
		try:
			status=self.status()
			diff=set(status.items())-set(self._last_status.items())
			for key, val in diff:
				if key == "elapsed":
					self.emitter.emit("elapsed_changed", float(val), float(status["duration"]))
				elif key == "bitrate":
					self.emitter.emit("bitrate", float(val))
				elif key == "songid":
					self.emitter.emit("current_song_changed")
				elif key == "state":
					self.emitter.emit("state", val)
				elif key == "audio":
					samplerate, bits, channels=val.split(':')
					self.emitter.emit("audio", float(samplerate), int(bits), int(channels))
				elif key == "volume":
					self.emitter.emit("volume_changed", float(val))
				elif key == "playlist":
					self.emitter.emit("playlist_changed", int(val))
				elif key in ["repeat", "random", "single", "consume"]:
					if val == "1":
						self.emitter.emit(key, True)
					else:
						self.emitter.emit(key, False)
			diff=set(self._last_status)-set(status)
			if "songid" in diff:
				self.emitter.emit("current_song_changed")
			if "volume" in diff:
				self.emitter.emit("volume_changed", 0)
			if "updating_db" in diff:
				self.emitter.emit("update")
			self._last_status=status
		except (MPDBase.ConnectionError, ConnectionResetError) as e:
			self.disconnect()
			self._last_status={}
			self.emitter.emit("disconnected")
			if self._disconnected_loop():
				self._disconnected_timeout_id=GLib.timeout_add(1000, self._disconnected_loop)
			return False
		return True

	def _disconnected_loop(self, *args):
		active=self._settings.get_int("active-profile")
		try:
			self.connect(self._settings.get_value("hosts")[active], self._settings.get_value("ports")[active])
			if self._settings.get_value("passwords")[active] != "":
				self.password(self._settings.get_value("passwords")[active])
		except:
			print("connect failed")
			return True
		# connect successful
		self._main_timeout_id=GLib.timeout_add(100, self._main_loop)
		self.emitter.emit("reconnected")
		return False

	def _on_settings_changed(self, *args):
		self.disconnect()

########################
# gio settings wrapper #
########################

class Settings(Gio.Settings):
	BASE_KEY="org.mpdevil"
	def __init__(self):
		super().__init__(schema=self.BASE_KEY)

		# fix profile settings
		if len(self.get_value("profiles")) < (self.get_int("active-profile")+1):
			self.set_int("active-profile", 0)
		profile_keys=[('as', "profiles", "new profile"), ('as', "hosts", "localhost"), ('ai', "ports", 6600), ('as', "passwords", ""), ('as', "paths", ""), ('as', "regex", "")]
		profile_arrays=[]
		for vtype, key, default in profile_keys:
			profile_arrays.append(self.get_value(key).unpack())
		max_len=max(len(x) for x in profile_arrays)
		for index, (vtype, key, default) in enumerate(profile_keys):
			profile_arrays[index]=(profile_arrays[index]+max_len*[default])[:max_len]
			self.set_value(key, GLib.Variant(vtype, profile_arrays[index]))

	def array_append(self, vtype, key, value):  # append to Gio.Settings (self._settings) array
		array=self.get_value(key).unpack()
		array.append(value)
		self.set_value(key, GLib.Variant(vtype, array))

	def array_delete(self, vtype, key, pos):  # delete entry of Gio.Settings (self._settings) array
		array=self.get_value(key).unpack()
		array.pop(pos)
		self.set_value(key, GLib.Variant(vtype, array))

	def array_modify(self, vtype, key, pos, value):  # modify entry of Gio.Settings (self._settings) array
		array=self.get_value(key).unpack()
		array[pos]=value
		self.set_value(key, GLib.Variant(vtype, array))

	def get_gtk_icon_size(self, key):
		icon_size=self.get_int(key)
		sizes=[(48, Gtk.IconSize.DIALOG), (32, Gtk.IconSize.DND), (24, Gtk.IconSize.LARGE_TOOLBAR), (16, Gtk.IconSize.BUTTON)]
		for pixel_size, gtk_size in sizes:
			if icon_size >= pixel_size:
				return gtk_size
		return Gtk.IconSize.INVALID

	def get_artist_type(self):
		if self.get_boolean("use-album-artist"):
			return ("albumartist")
		else:
			return ("artist")

###########
# browser #
###########

class SearchWindow(Gtk.Box):
	def __init__(self, client):
		Gtk.Box.__init__(self, orientation=Gtk.Orientation.VERTICAL)

		# adding vars
		self._client=client

		# tag switcher
		self._tags=Gtk.ComboBoxText()

		# search entry
		self._search_entry=Gtk.SearchEntry()

		# label
		self._hits_label=Gtk.Label()
		self._hits_label.set_xalign(1)

		# store
		# (track, title, artist, album, duration, file)
		self._store=Gtk.ListStore(int, str, str, str, str, str)

		# songs window
		self._songs_window=SongsWindow(self._client, self._store, 5)

		# action bar
		self._action_bar=self._songs_window.get_action_bar()
		self._action_bar.set_sensitive(False)

		# songs view
		self._songs_view=self._songs_window.get_treeview()

		# columns
		renderer_text=Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END, ellipsize_set=True)
		renderer_text_ralign=Gtk.CellRendererText(xalign=1.0)

		column_track=Gtk.TreeViewColumn(_("No"), renderer_text_ralign, text=0)
		column_track.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
		column_track.set_property("resizable", False)
		self._songs_view.append_column(column_track)

		column_title=Gtk.TreeViewColumn(_("Title"), renderer_text, text=1)
		column_title.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
		column_title.set_property("resizable", False)
		column_title.set_property("expand", True)
		self._songs_view.append_column(column_title)

		column_artist=Gtk.TreeViewColumn(_("Artist"), renderer_text, text=2)
		column_artist.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
		column_artist.set_property("resizable", False)
		column_artist.set_property("expand", True)
		self._songs_view.append_column(column_artist)

		column_album=Gtk.TreeViewColumn(_("Album"), renderer_text, text=3)
		column_album.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
		column_album.set_property("resizable", False)
		column_album.set_property("expand", True)
		self._songs_view.append_column(column_album)

		column_time=Gtk.TreeViewColumn(_("Length"), renderer_text, text=4)
		column_time.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
		column_time.set_property("resizable", False)
		self._songs_view.append_column(column_time)

		column_track.set_sort_column_id(0)
		column_title.set_sort_column_id(1)
		column_artist.set_sort_column_id(2)
		column_album.set_sort_column_id(3)
		column_time.set_sort_column_id(4)

		# connect
		self._search_entry.connect("search-changed", self._on_search_changed)
		self._tags.connect("changed", self._on_search_changed)
		self._client.emitter.connect("reconnected", self._on_reconnected)
		self._client.emitter.connect("disconnected", self._on_disconnected)

		# packing
		hbox=Gtk.Box(spacing=6)
		hbox.set_property("border-width", 6)
		hbox.pack_start(self._search_entry, True, True, 0)
		hbox.pack_end(self._tags, False, False, 0)
		self._hits_label.set_margin_end(6)
		self._action_bar.pack_end(self._hits_label)
		self.pack_start(hbox, False, False, 0)
		self.pack_start(Gtk.Separator.new(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)
		self.pack_start(self._songs_window, True, True, 0)

	def start(self):
		self._search_entry.grab_focus()

	def started(self):
		return self._search_entry.has_focus()

	def clear(self, *args):
		self._songs_view.clear()
		self._search_entry.set_text("")
		self._tags.remove_all()

	def _on_disconnected(self, *args):
		self._tags.set_sensitive(False)
		self._search_entry.set_sensitive(False)
		self.clear()

	def _on_reconnected(self, *args):
		self._tags.append_text("any")
		for tag in self._client.wrapped_call("tagtypes"):
			if not tag.startswith("MUSICBRAINZ"):
				self._tags.append_text(tag)
		self._tags.set_active(0)
		self._tags.set_sensitive(True)
		self._search_entry.set_sensitive(True)

	def _on_search_changed(self, widget):
		self._songs_view.clear()
		self._hits_label.set_text("")
		if len(self._search_entry.get_text()) > 1:
			songs=self._client.wrapped_call("search", self._tags.get_active_text(), self._search_entry.get_text())
			for s in songs:
				song=ClientHelper.extend_song_for_display(ClientHelper.song_to_str_dict(s))
				self._store.append([int(song["track"]), song["title"], song["artist"], song["album"], song["human_duration"], song["file"]])
			self._hits_label.set_text(_("%i hits") % (self._songs_view.count()))
		if self._songs_view.count() == 0:
			self._action_bar.set_sensitive(False)
		else:
			self._action_bar.set_sensitive(True)

class SongsView(Gtk.TreeView):
	def __init__(self, client, store, file_column_id):
		Gtk.TreeView.__init__(self)
		self.set_model(store)
		self.set_search_column(-1)
		self.columns_autosize()

		# add vars
		self._client=client
		self._store=store
		self._file_column_id=file_column_id

		# selection
		self._selection=self.get_selection()
		self._selection.set_mode(Gtk.SelectionMode.SINGLE)

		# connect
		self.connect("row-activated", self._on_row_activated)
		self.connect("button-press-event", self._on_button_press_event)
		self._key_press_event=self.connect("key-press-event", self._on_key_press_event)

	def clear(self):
		self._store.clear()

	def count(self):
		return len(self._store)

	def get_files(self):
		return_list=[]
		for row in self._store:
			return_list.append(row[self._file_column_id])
		return return_list

	def _on_row_activated(self, widget, path, view_column):
		self._client.wrapped_call("files_to_playlist", [self._store[path][self._file_column_id]], "play")

	def _on_button_press_event(self, widget, event):
		if event.button == 1 and event.type == Gdk.EventType.BUTTON_PRESS:
			try:
				path=widget.get_path_at_pos(int(event.x), int(event.y))[0]
				self._client.wrapped_call("files_to_playlist", [self._store[path][self._file_column_id]])
			except:
				pass
		elif event.button == 2 and event.type == Gdk.EventType.BUTTON_PRESS:
			try:
				path=widget.get_path_at_pos(int(event.x), int(event.y))[0]
				self._client.wrapped_call("files_to_playlist", [self._store[path][self._file_column_id]], "append")
			except:
				pass
		elif event.button == 3 and event.type == Gdk.EventType.BUTTON_PRESS:
			try:
				path=widget.get_path_at_pos(int(event.x), int(event.y))[0]
				file_name=self._store[path][self._file_column_id]
				pop=SongPopover(self._client.wrapped_call("get_metadata", file_name), widget, int(event.x), int(event.y))
				pop.popup()
				pop.show_all()
			except:
				pass

	def _on_key_press_event(self, widget, event):
		self.handler_block(self._key_press_event)
		if event.keyval == 112:  # p
			treeview, treeiter=self._selection.get_selected()
			if treeiter is not None:
				self._client.wrapped_call("files_to_playlist", [self._store.get_value(treeiter, self._file_column_id)])
		elif event.keyval == 97:  # a
			treeview, treeiter=self._selection.get_selected()
			if treeiter is not None:
				self._client.wrapped_call("files_to_playlist", [self._store.get_value(treeiter, self._file_column_id)], "append")
		elif event.keyval == 65383:  # menu key
			treeview, treeiter=self._selection.get_selected()
			if treeiter is not None:
				path=self._store.get_path(treeiter)
				cell=self.get_cell_area(path, None)
				file_name=self._store[path][self._file_column_id]
				pop=SongPopover(self._client.wrapped_call("get_metadata", file_name), widget, int(cell.x), int(cell.y))
				pop.popup()
				pop.show_all()
		self.handler_unblock(self._key_press_event)

class SongsWindow(Gtk.Box):
	def __init__(self, client, store, file_column_id):
		Gtk.Box.__init__(self, orientation=Gtk.Orientation.VERTICAL)

		# adding vars
		self._client=client

		# treeview
		self._songs_view=SongsView(client, store, file_column_id)

		# scroll
		scroll=Gtk.ScrolledWindow()
		scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
		scroll.add(self._songs_view)

		# buttons
		append_button=Gtk.Button(image=Gtk.Image.new_from_icon_name("list-add", Gtk.IconSize.BUTTON), label=_("Append"))
		append_button.set_tooltip_text(_("Add all titles to playlist"))
		play_button=Gtk.Button(image=Gtk.Image.new_from_icon_name("media-playback-start", Gtk.IconSize.BUTTON), label=_("Play"))
		play_button.set_tooltip_text(_("Directly play all titles"))
		enqueue_button=Gtk.Button(image=Gtk.Image.new_from_icon_name("insert-object", Gtk.IconSize.BUTTON), label=_("Enqueue"))
		enqueue_button.set_tooltip_text(_("Append all titles after the currently playing track and clear the playlist from all other songs"))

		# button box
		button_box=Gtk.ButtonBox()
		button_box.set_property("layout-style", Gtk.ButtonBoxStyle.EXPAND)

		# action bar
		self._action_bar=Gtk.ActionBar()

		# connect
		append_button.connect("clicked", self._on_append_button_clicked)
		play_button.connect("clicked", self._on_play_button_clicked)
		enqueue_button.connect("clicked", self._on_enqueue_button_clicked)

		# packing
		frame=FocusFrame()
		frame.set_widget(self._songs_view)
		frame.add(scroll)
		self.pack_start(frame, True, True, 0)
		button_box.pack_start(append_button, True, True, 0)
		button_box.pack_start(play_button, True, True, 0)
		button_box.pack_start(enqueue_button, True, True, 0)
		self._action_bar.pack_start(button_box)
		self.pack_start(self._action_bar, False, False, 0)

	def get_treeview(self):
		return self._songs_view

	def get_action_bar(self):
		return self._action_bar

	def _on_append_button_clicked(self, *args):
		self._client.wrapped_call("files_to_playlist", self._songs_view.get_files(), "append")

	def _on_play_button_clicked(self, *args):
		self._client.wrapped_call("files_to_playlist", self._songs_view.get_files(), "play")

	def _on_enqueue_button_clicked(self, *args):
		self._client.wrapped_call("files_to_playlist", self._songs_view.get_files(), "enqueue")

class AlbumDialog(Gtk.Dialog):
	def __init__(self, parent, client, settings, album, album_artist, year):
		use_csd=settings.get_boolean("use-csd")
		if use_csd:
			Gtk.Dialog.__init__(self, transient_for=parent, use_header_bar=True)
		else:
			Gtk.Dialog.__init__(self, transient_for=parent)

		# css
		style_context=self.get_style_context()
		provider=Gtk.CssProvider()
		if use_csd:
			css=b"""* {-GtkDialog-content-area-border: 0px;}"""
		else:
			css=b"""* {-GtkDialog-action-area-border: 0px;}"""
		provider.load_from_data(css)
		style_context.add_provider(provider, 800)

		# adding vars
		self._client=client
		self._settings=settings
		songs=self._client.wrapped_call("find", "album", album, "date", year, self._settings.get_artist_type(), album_artist)

		# determine size
		size=parent.get_size()
		diagonal=(size[0]**2+size[1]**2)**(0.5)
		h=diagonal//4
		w=h*5//4
		self.set_default_size(w, h)

		# title
		album_duration=ClientHelper.calc_display_length(songs)
		if year == "":
			self.set_title(album_artist+" - "+album+" ("+album_duration+")")
		else:
			self.set_title(album_artist+" - "+album+" ("+year+") ("+album_duration+")")

		# store
		# (track, title (artist), duration, file)
		store=Gtk.ListStore(int, str, str, str)
		for s in songs:
			song=ClientHelper.extend_song_for_display(s)
			if type(song["title"]) == list:  # could be impossible
				title=(', '.join(song["title"]))
			else:
				title=song["title"]
			if type(song["artist"]) == list:
				try:
					song["artist"].remove(album_artist)
				except:
					pass
				artist=(', '.join(song["artist"]))
			else:
				artist=song["artist"]
			if artist == album_artist:
				title_artist="<b>"+title+"</b>"
			else:
				title_artist="<b>"+title+"</b> - "+artist

			title_artist=title_artist.replace("&", "&amp;")
			store.append([int(song["track"]), title_artist, song["human_duration"], song["file"]])

		# songs window
		songs_window=SongsWindow(self._client, store, 3)

		# songs view
		songs_view=songs_window.get_treeview()

		# columns
		renderer_text=Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END, ellipsize_set=True)
		renderer_text_ralign=Gtk.CellRendererText(xalign=1.0)

		column_track=Gtk.TreeViewColumn(_("No"), renderer_text_ralign, text=0)
		column_track.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
		column_track.set_property("resizable", False)
		songs_view.append_column(column_track)

		column_title=Gtk.TreeViewColumn(_("Title"), renderer_text, markup=1)
		column_title.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
		column_title.set_property("resizable", False)
		column_title.set_property("expand", True)
		songs_view.append_column(column_title)

		column_time=Gtk.TreeViewColumn(_("Length"), renderer_text, text=2)
		column_time.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
		column_time.set_property("resizable", False)
		songs_view.append_column(column_time)

		# close button
		close_button=Gtk.ToggleButton(image=Gtk.Image.new_from_icon_name("window-close", Gtk.IconSize.BUTTON), label=_("Close"))

		# action bar
		action_bar=songs_window.get_action_bar()
		action_bar.pack_end(close_button)

		# connect
		close_button.connect("clicked", self._on_close_button_clicked)

		# packing
		self.vbox.pack_start(songs_window, True, True, 0)  # vbox default widget of dialogs
		self.show_all()

	def open(self):
		response=self.run()

	def _on_close_button_clicked(self, *args):
		self.destroy()

class GenreSelect(Gtk.ComboBoxText):
	def __init__(self, client):
		Gtk.ComboBoxText.__init__(self)

		# adding vars
		self._client=client

		# connect
		self._changed=self.connect("changed", self._on_changed)
		self._client.emitter.connect("disconnected", self._on_disconnected)
		self._client.emitter.connect("reconnected", self._on_reconnected)
		self._client.emitter.connect("update", self._refresh)

	def deactivate(self):
		self.set_active(0)

	def clear(self, *args):
		self.handler_block(self._changed)
		self.remove_all()
		self.handler_unblock(self._changed)

	def get_value(self):
		if self.get_active() == 0:
			return None
		else:
			return self.get_active_text()

	@GObject.Signal
	def genre_changed(self):
		pass

	def _refresh(self, *args):
		self.handler_block(self._changed)
		self.remove_all()
		self.append_text(_("all genres"))
		for genre in self._client.wrapped_call("comp_list", "genre"):
			self.append_text(genre)
		self.set_active(0)
		self.handler_unblock(self._changed)

	def _on_changed(self, *args):
		self.emit("genre_changed")

	def _on_disconnected(self, *args):
		self.set_sensitive(False)
		self.clear()

	def _on_reconnected(self, *args):
		self._refresh()
		self.set_sensitive(True)

class ArtistWindow(FocusFrame):
	def __init__(self, client, settings, genre_select):
		FocusFrame.__init__(self)

		# adding vars
		self._client=client
		self._settings=settings
		self._genre_select=genre_select

		# artistStore
		# (name, weight, initial-letter, weight-initials)
		self._store=Gtk.ListStore(str, Pango.Weight, str, Pango.Weight)

		# TreeView
		self._treeview=Gtk.TreeView(model=self._store)
		self._treeview.set_search_column(0)
		self._treeview.columns_autosize()
		self._treeview.set_property("activate-on-single-click", True)

		# Selection
		self._selection=self._treeview.get_selection()
		self._selection.set_mode(Gtk.SelectionMode.SINGLE)

		# Columns
		renderer_text_malign=Gtk.CellRendererText(xalign=0.5)
		self._column_initials=Gtk.TreeViewColumn("", renderer_text_malign, text=2, weight=3)
		self._column_initials.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
		self._column_initials.set_property("resizable", False)
		self._column_initials.set_visible(self._settings.get_boolean("show-initials"))
		self._treeview.append_column(self._column_initials)

		renderer_text=Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END, ellipsize_set=True)
		self._column_name=Gtk.TreeViewColumn("", renderer_text, text=0, weight=1)
		self._column_name.set_sizing(Gtk.TreeViewColumnSizing.AUTOSIZE)
		self._column_name.set_property("resizable", False)
		self._treeview.append_column(self._column_name)

		# scroll
		scroll=Gtk.ScrolledWindow()
		scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
		scroll.add(self._treeview)

		# connect
		self._treeview.connect("row-activated", self._on_row_activated)
		self._settings.connect("changed::use-album-artist", self._refresh)
		self._settings.connect("changed::show-initials", self._on_show_initials_settings_changed)
		self._client.emitter.connect("disconnected", self.clear)
		self._client.emitter.connect("reconnected", self._refresh)
		self._client.emitter.connect("update", self._refresh)
		self._genre_select.connect("genre_changed", self._refresh)

		self.set_widget(self._treeview)
		self.add(scroll)

	def clear(self, *args):
		self._store.clear()

	def select(self, artist):
		row_num=len(self._store)
		for i in range(0, row_num):
			path=Gtk.TreePath(i)
			if self._store[path][0] == artist:
				self._treeview.set_cursor(path, None, False)
				if self.get_selected_artists() == [artist]:
					self._treeview.set_cursor(path, None, False)
				else:
					self._treeview.row_activated(path, self._column_name)
				break

	def get_selected_artists(self):
		artists=[]
		if self._store[Gtk.TreePath(0)][1] == Pango.Weight.BOLD:
			for row in self._store:
				artists.append(row[0])
			return artists[1:]
		else:
			for row in self._store:
				if row[1] == Pango.Weight.BOLD:
					artists.append(row[0])
					break
			return artists

	def highlight_selected(self):
		for path, row in enumerate(self._store):
			if row[1] == Pango.Weight.BOLD:
				self._treeview.set_cursor(path, None, False)
				break

	@GObject.Signal
	def artists_changed(self):
		pass

	def _refresh(self, *args):
		self._selection.set_mode(Gtk.SelectionMode.NONE)
		self.clear()
		if self._settings.get_artist_type() == "albumartist":
			self._column_name.set_title(_("Album Artist"))
		else:
			self._column_name.set_title(_("Artist"))
		self._store.append([_("all artists"), Pango.Weight.BOOK, "", Pango.Weight.BOOK])
		genre=self._genre_select.get_value()
		if genre is None:
			artists=self._client.wrapped_call("comp_list", self._settings.get_artist_type())
		else:
			artists=self._client.wrapped_call("comp_list", self._settings.get_artist_type(), "genre", genre)
		current_char=""
		for artist in artists:
			try:
				if current_char == artist[0]:
					self._store.append([artist, Pango.Weight.BOOK, "", Pango.Weight.BOOK])
				else:
					self._store.append([artist, Pango.Weight.BOOK, artist[0], Pango.Weight.BOLD])
					current_char=artist[0]
			except:
				self._store.append([artist, Pango.Weight.BOOK, "", Pango.Weight.BOOK])
		self._selection.set_mode(Gtk.SelectionMode.SINGLE)

	def _on_row_activated(self, widget, path, view_column):
		for row in self._store:  # reset bold text
			row[1]=Pango.Weight.BOOK
		self._store[path][1]=Pango.Weight.BOLD
		self.emit("artists_changed")

	def _on_show_initials_settings_changed(self, *args):
		self._column_initials.set_visible(self._settings.get_boolean("show-initials"))

class AlbumView(Gtk.IconView):
	def __init__(self, client, settings, genre_select, window):
		Gtk.IconView.__init__(self)

		# adding vars
		self._settings=settings
		self._client=client
		self._genre_select=genre_select
		self._window=window
		self._button_event=(None, None)
		self.stop_flag=False

		# cover, display_label, display_label_artist, tooltip(titles), album, year, artist
		self._store=Gtk.ListStore(GdkPixbuf.Pixbuf, str, str, str, str, str, str)
		self._sort_settings()

		# iconview
		self.set_model(self._store)
		self.set_pixbuf_column(0)
		self.set_markup_column(1)
		self.set_item_width(0)
		self._tooltip_settings()

		# connect
		self.connect("item-activated", self._on_item_activated)
		self.connect("button-release-event", self._on_button_release_event)
		self.connect("button-press-event", self._on_button_press_event)
		self._key_press_event=self.connect("key-press-event", self._on_key_press_event)
		self._settings.connect("changed::show-album-view-tooltips", self._tooltip_settings)
		self._settings.connect("changed::sort-albums-by-year", self._sort_settings)

	def clear(self):
		self._store.clear()
		# workaround (scrollbar still visible after clear)
		self.set_model(None)
		self.set_model(self._store)

	def scroll_to_selected_album(self):
		song=ClientHelper.song_to_first_str_dict(self._client.wrapped_call("currentsong"))
		try:
			album=song["album"]
		except:
			album=""
		self.unselect_all()
		row_num=len(self._store)
		for i in range(0, row_num):
			path=Gtk.TreePath(i)
			treeiter=self._store.get_iter(path)
			if self._store.get_value(treeiter, 4) == album:
				self.set_cursor(path, None, False)
				self.select_path(path)
				self.scroll_to_path(path, True, 0, 0)
				break

	def _tooltip_settings(self, *args):
		if self._settings.get_boolean("show-album-view-tooltips"):
			self.set_tooltip_column(3)
		else:
			self.set_tooltip_column(-1)

	def _sort_settings(self, *args):
		if self._settings.get_boolean("sort-albums-by-year"):
			self._store.set_sort_column_id(5, Gtk.SortType.ASCENDING)
		else:
			self._store.set_sort_column_id(1, Gtk.SortType.ASCENDING)

	def _add_row(self, row):  # needed for GLib.idle
		self._store.append(row)
		return False  # stop after one run

	def populate(self, artists):
		GLib.idle_add(self._store.clear)
		# show artist names if all albums are shown
		if len(artists) > 1:
			self.set_markup_column(2)
		else:
			self.set_markup_column(1)
		# prepare albmus list (run all mpd related commands)
		albums=[]
		genre=self._genre_select.get_value()
		artist_type=self._settings.get_artist_type()
		for artist in artists:
			try:  # client cloud meanwhile disconnect
				if self.stop_flag:
					GLib.idle_add(self.emit, "done")
					return
				else:
					if genre is None:
						album_candidates=self._client.wrapped_call("comp_list", "album", artist_type, artist)
					else:
						album_candidates=self._client.wrapped_call("comp_list", "album", artist_type, artist, "genre", genre)
					for album in album_candidates:
						years=self._client.wrapped_call("comp_list", "date", "album", album, artist_type, artist)
						for year in years:
							songs=self._client.wrapped_call("find", "album", album, "date", year, artist_type, artist)
							albums.append({"artist": artist, "album": album, "year": year, "songs": songs})
					while Gtk.events_pending():
						Gtk.main_iteration_do(True)
			except MPDBase.ConnectionError:
				GLib.idle_add(self.emit, "done")
				return
		# display albums
		if self._settings.get_boolean("sort-albums-by-year"):
			albums=sorted(albums, key=lambda k: k['year'])
		else:
			albums=sorted(albums, key=lambda k: k['album'])
		size=self._settings.get_int("album-cover")
		for i, album in enumerate(albums):
			if self.stop_flag:
				break
			else:
				cover=Cover(self._settings, album["songs"][0]).get_pixbuf(size)
				# tooltip
				length_human_readable=ClientHelper.calc_display_length(album["songs"])
				try:
					discs=int(album["songs"][-1]["disc"])
				except:
					discs=1
				if discs > 1:
					tooltip=(_("%(total_tracks)i titles on %(discs)i discs (%(total_length)s)") % {"total_tracks": len(album["songs"]), "discs": discs, "total_length": length_human_readable})
				else:
					tooltip=(_("%(total_tracks)i titles (%(total_length)s)") % {"total_tracks": len(album["songs"]), "total_length": length_human_readable})
				# album label
				display_label="<b>"+album["album"]+"</b>"
				if album["year"] != "":
					display_label=display_label+" ("+album["year"]+")"
				display_label_artist=display_label+"\n"+album["artist"]
				display_label=display_label.replace("&", "&amp;")
				display_label_artist=display_label_artist.replace("&", "&amp;")
				# add album
				GLib.idle_add(self._add_row, [cover, display_label, display_label_artist, tooltip, album["album"], album["year"], album["artist"]])
				# execute pending events
				if i%16 == 0:
					while Gtk.events_pending():
						Gtk.main_iteration_do(True)
		GLib.idle_add(self.emit, "done")

	def _path_to_playlist(self, path, mode="default"):
		album=self._store[path][4]
		year=self._store[path][5]
		artist=self._store[path][6]
		self._client.wrapped_call("album_to_playlist", album, artist, year, mode)

	def _open_album_dialog(self, path):
		if self._client.connected():
			album=self._store[path][4]
			year=self._store[path][5]
			artist=self._store[path][6]
			album_dialog=AlbumDialog(self._window, self._client, self._settings, album, artist, year)
			album_dialog.open()
			album_dialog.destroy()

	@GObject.Signal
	def done(self):
		self.stop_flag=False

	def _on_button_press_event(self, widget, event):
		path=widget.get_path_at_pos(int(event.x), int(event.y))
		if event.type == Gdk.EventType.BUTTON_PRESS:
			self._button_event=(event.button, path)

	def _on_button_release_event(self, widget, event):
		path=widget.get_path_at_pos(int(event.x), int(event.y))
		if path is not None:
			if self._button_event == (event.button, path):
				if event.button == 1 and event.type == Gdk.EventType.BUTTON_RELEASE:
					self._path_to_playlist(path)
				elif event.button == 2 and event.type == Gdk.EventType.BUTTON_RELEASE:
					self._path_to_playlist(path, "append")
				elif event.button == 3 and event.type == Gdk.EventType.BUTTON_RELEASE:
					self._open_album_dialog(path)

	def _on_key_press_event(self, widget, event):
		self.handler_block(self._key_press_event)
		if event.keyval == 112:  # p
			paths=self.get_selected_items()
			if len(paths) != 0:
				self._path_to_playlist(paths[0])
		elif event.keyval == 97:  # a
			paths=self.get_selected_items()
			if len(paths) != 0:
				self._path_to_playlist(paths[0], "append")
		elif event.keyval == 65383:  # menu key
			paths=self.get_selected_items()
			if len(paths) != 0:
				self._open_album_dialog(paths[0])
		self.handler_unblock(self._key_press_event)

	def _on_item_activated(self, widget, path):
		treeiter=self._store.get_iter(path)
		selected_album=self._store.get_value(treeiter, 4)
		selected_album_year=self._store.get_value(treeiter, 5)
		selected_artist=self._store.get_value(treeiter, 6)
		self._client.wrapped_call("album_to_playlist", selected_album, selected_artist, selected_album_year, "play")

class AlbumWindow(FocusFrame):
	def __init__(self, client, settings, genre_select, window):
		FocusFrame.__init__(self)

		# adding vars
		self._settings=settings
		self._client=client
		self._artists=[]
		self._done=True
		self._pending=[]

		# iconview
		self._iconview=AlbumView(client, settings, genre_select, window)

		# scroll
		scroll=Gtk.ScrolledWindow()
		scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
		scroll.add(self._iconview)

		# connect
		self._iconview.connect("done", self._on_done)
		genre_select.connect("genre_changed", self.clear)
		self._client.emitter.connect("update", self.clear)
		self._client.emitter.connect("disconnected", self.clear)
		self._settings.connect("changed::album-cover", self._on_settings_changed)
		self._settings.connect("changed::use-album-artist", self.clear)

		self.set_widget(self._iconview)
		self.add(scroll)

	def clear(self, *args):
		if self._done:
			self._iconview.clear()
		elif not self.clear in self._pending:
			self._iconview.stop_flag=True
			self._pending.append(self.clear)

	def refresh(self, artists=[]):
		if artists != []:
			self._artists=artists
		if self._done:
			self._done=False
			self._iconview.populate(self._artists)
		elif not self.refresh in self._pending:
			self._iconview.stop_flag=True
			self._pending.append(self.refresh)

	def scroll_to_selected_album(self):
		if self._done:
			self._iconview.scroll_to_selected_album()
		elif not self.scroll_to_selected_album in self._pending:
			self._pending.append(self.scroll_to_selected_album)

	def _on_done(self, *args):
		self._done=True
		pending=self._pending
		self._pending=[]
		for p in pending:
			try:
				p()
			except:
				pass

	def _on_settings_changed(self, *args):
		def callback():
			self.refresh(self._artists)
			return False
		GLib.idle_add(callback)

class Browser(Gtk.Paned):
	def __init__(self, client, settings, window):
		Gtk.Paned.__init__(self)  # paned1
		self.set_orientation(Gtk.Orientation.HORIZONTAL)

		# adding vars
		self._client=client
		self._settings=settings
		self._use_csd=self._settings.get_boolean("use-csd")

		if self._use_csd:
			self._icon_size=0
		else:
			self._icon_size=self._settings.get_int("icon-size-sec")

		# widgets
		self._icons={}
		icons_data=["go-previous-symbolic", "system-search-symbolic"]
		for data in icons_data:
			self._icons[data]=PixelSizedIcon(data, self._icon_size)

		self.back_to_album_button=Gtk.Button(image=self._icons["go-previous-symbolic"])
		self.back_to_album_button.set_tooltip_text(_("Back to current album"))
		self.search_button=Gtk.ToggleButton(image=self._icons["system-search-symbolic"])
		self.search_button.set_tooltip_text(_("Search"))
		self.genre_select=GenreSelect(self._client)
		self._artist_window=ArtistWindow(self._client, self._settings, self.genre_select)
		self._search_window=SearchWindow(self._client)
		self._album_window=AlbumWindow(self._client, self._settings, self.genre_select, window)

		# connect
		self.back_to_album_button.connect("clicked", self.back_to_album)
		self.search_button.connect("toggled", self._on_search_toggled)
		self._artist_window.connect("artists_changed", self._on_artists_changed)
		if not self._use_csd:
			self._settings.connect("changed::icon-size-sec", self._on_icon_size_changed)
		self._client.emitter.connect("disconnected", self._on_disconnected)
		self._client.emitter.connect("reconnected", self._on_reconnected)

		# packing
		self._stack=Gtk.Stack()
		self._stack.set_transition_type(1)
		self._stack.add_named(self._album_window, "albums")
		self._stack.add_named(self._search_window, "search")

		if self._use_csd:
			self.pack1(self._artist_window, False, False)
		else:
			hbox=Gtk.Box(spacing=6)
			hbox.set_property("border-width", 6)
			hbox.pack_start(self.back_to_album_button, False, False, 0)
			hbox.pack_start(self.genre_select, True, True, 0)
			hbox.pack_start(self.search_button, False, False, 0)
			box1=Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
			box1.pack_start(hbox, False, False, 0)
			box1.pack_start(Gtk.Separator.new(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)
			box1.pack_start(self._artist_window, True, True, 0)
			self.pack1(box1, False, False)
		self.pack2(self._stack, True, False)

		self.set_position(self._settings.get_int("paned1"))

	def save_settings(self):
		self._settings.set_int("paned1", self.get_position())

	def search_started(self):
		return self._search_window.started()

	def back_to_album(self, *args):
		def callback():
			try:
				song=ClientHelper.song_to_first_str_dict(self._client.wrapped_call("currentsong"))
				if song == {}:
					return False
			except MPDBase.ConnectionError:
				return False
			self.search_button.set_active(False)
			# get artist name
			try:
				artist=song[self._settings.get_artist_type()]
			except:
				try:
					artist=song["artist"]
				except:
					artist=""
			# deactivate genre filter to show all artists (if needed)
			try:
				if song['genre'] != self.genre_select.get_value():
					self.genre_select.deactivate()
			except:
				self.genre_select.deactivate()
			# select artist
			if len(self._artist_window.get_selected_artists()) <= 1:  # one artist selected
				self._artist_window.select(artist)
			else:  # all artists selected
				self.search_button.set_active(False)
				self._artist_window.highlight_selected()
			self._album_window.scroll_to_selected_album()
			return False
		GLib.idle_add(callback)  # ensure it will be executed even when albums are still loading

	def _on_search_toggled(self, widget):
		if widget.get_active():
			self._stack.set_visible_child_name("search")
			self._search_window.start()
		else:
			self._stack.set_visible_child_name("albums")

	def _on_reconnected(self, *args):
		self.back_to_album()
		self.back_to_album_button.set_sensitive(True)
		self.search_button.set_sensitive(True)

	def _on_disconnected(self, *args):
		self.back_to_album_button.set_sensitive(False)
		self.search_button.set_active(False)
		self.search_button.set_sensitive(False)

	def _on_artists_changed(self, *args):
		self.search_button.set_active(False)
		artists=self._artist_window.get_selected_artists()
		self._album_window.refresh(artists)

	def _on_icon_size_changed(self, *args):
		pixel_size=self._settings.get_int("icon-size-sec")
		for icon in self._icons.values():
			icon.set_pixel_size(pixel_size)

######################
# playlist and cover #
######################

class LyricsWindow(Gtk.Overlay):
	def __init__(self, client, settings):
		Gtk.Overlay.__init__(self)

		# adding vars
		self._settings=settings
		self._client=client

		# widgets
		text_view=Gtk.TextView()
		text_view.set_editable(False)
		text_view.set_left_margin(5)
		text_view.set_bottom_margin(5)
		text_view.set_cursor_visible(False)
		text_view.set_wrap_mode(Gtk.WrapMode.WORD)
		text_view.set_justification(Gtk.Justification.CENTER)
		self._text_buffer=text_view.get_buffer()

		# scroll
		scroll=Gtk.ScrolledWindow()
		scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
		scroll.add(text_view)

		# frame
		frame=FocusFrame()
		frame.set_widget(text_view)
		style_context=frame.get_style_context()
		provider=Gtk.CssProvider()
		css=b"""* {border: 0px; background-color: @theme_base_color; opacity: 0.9;}"""
		provider.load_from_data(css)
		style_context.add_provider(provider, 800)

		# close button
		close_button=Gtk.ToggleButton(image=Gtk.Image.new_from_icon_name("window-close-symbolic", Gtk.IconSize.BUTTON))
		close_button.set_margin_top(6)
		close_button.set_margin_end(6)
		style_context=close_button.get_style_context()
		style_context.add_class("circular")

		close_button.set_halign(2)
		close_button.set_valign(1)

		# connect
		self._song_changed=self._client.emitter.connect("current_song_changed", self._refresh)
		self.connect("destroy", self._remove_handlers)
		close_button.connect("clicked", self._on_close_button_clicked)

		# packing
		frame.add(scroll)
		self.add(frame)
		self.add_overlay(close_button)

		self.show_all()
		self._refresh()
		GLib.idle_add(text_view.grab_focus)  # focus textview

	def _display_lyrics(self, current_song):
		GLib.idle_add(self._text_buffer.set_text, _("searching..."), -1)
		try:
			text=self._get_lyrics(current_song["artist"], current_song["title"])
		except:
			text=_("lyrics not found")
		GLib.idle_add(self._text_buffer.set_text, text, -1)

	def _refresh(self, *args):
		update_thread=threading.Thread(target=self._display_lyrics, kwargs={"current_song": ClientHelper.song_to_first_str_dict(self._client.wrapped_call("currentsong"))}, daemon=True)
		update_thread.start()

	def _get_lyrics(self, singer, song):  # partially copied from PyLyrics 1.1.0
		# Replace spaces with _
		singer=singer.replace(' ', '_')
		song=song.replace(' ', '_')
		r=requests.get('http://lyrics.wikia.com/{0}:{1}'.format(singer,song))
		s=BeautifulSoup(r.text)
		# Get main lyrics holder
		lyrics=s.find("div",{'class':'lyricbox'})
		if lyrics is None:
			raise ValueError("Song or Singer does not exist or the API does not have Lyrics")
			return None
		# Remove Scripts
		[s.extract() for s in lyrics('script')]
		# Remove Comments
		comments=lyrics.findAll(text=lambda text:isinstance(text, Comment))
		[comment.extract() for comment in comments]
		# Remove span tag (Needed for instrumantal)
		if lyrics.span is not None:
			lyrics.span.extract()
		# Remove unecessary tags
		for tag in ['div','i','b','a']:
			for match in lyrics.findAll(tag):
				match.replaceWithChildren()
		# Get output as a string and remove non unicode characters and replace <br> with newlines
		output=str(lyrics).encode('utf-8', errors='replace')[22:-6:].decode("utf-8").replace('\n','').replace('<br/>','\n')
		try:
			return output
		except:
			return output.encode('utf-8')

	def _on_close_button_clicked(self, *args):
		self.destroy()

	def _remove_handlers(self, *args):
		self._client.emitter.disconnect(self._song_changed)

class AudioType(Gtk.Label):
	def __init__(self, client):
		Gtk.Label.__init__(self)

		# adding vars
		self._client=client
		self._init_vars()

		# connect
		self._client.emitter.connect("audio", self._on_audio)
		self._client.emitter.connect("bitrate", self._on_bitrate)
		self._client.emitter.connect("current_song_changed", self._on_song_changed)
		self._client.emitter.connect("disconnected", self.clear)
		self._client.emitter.connect("state", self._on_state)

	def clear(self, *args):
		self.set_text("")
		self._init_vars()

	def _init_vars(self):
		self.freq=0
		self.res=0
		self.chan=0
		self.brate=0
		self.file_type=""

	def _refresh(self, *args):
		string=_("%(bitrate)s kb/s, %(frequency)s kHz, %(resolution)i bit, %(channels)i channels, %(file_type)s") % {"bitrate": str(self.brate), "frequency": str(self.freq), "resolution": self.res, "channels": self.chan, "file_type": self.file_type}
		self.set_text(string)

	def _on_audio(self, emitter, freq, res, chan):
		self.freq=freq/1000
		self.res=res
		self.chan=chan
		self._refresh()

	def _on_bitrate(self, emitter, brate):
		self.brate=brate
		self._refresh()

	def _on_song_changed(self, *args):
		try:
			self.file_type=self._client.wrapped_call("currentsong")["file"].split('.')[-1]
			self._refresh()
		except:
			pass

	def _on_state(self, emitter, state):
		if state == "stop":
			self.clear()

class MainCover(Gtk.Frame):
	def __init__(self, client, settings, window):
		Gtk.Frame.__init__(self)
		# diable auto resize
		self.set_halign(3)
		self.set_valign(3)
		# css
		style_context=self.get_style_context()
		provider=Gtk.CssProvider()
		css=b"""* {background-color: @theme_base_color; border-radius: 6px;}"""
		provider.load_from_data(css)
		style_context.add_provider(provider, 800)

		# adding vars
		self._client=client
		self._settings=settings
		self._window=window

		# event box
		event_box=Gtk.EventBox()
		event_box.set_property("border-width", 6)

		# cover
		self._cover=Gtk.Image.new()
		size=self._settings.get_int("track-cover")
		self._cover.set_from_pixbuf(Cover(self._settings, {}).get_pixbuf(size))  # set to fallback cover
		# set default size
		self._cover.set_size_request(size, size)

		# connect
		event_box.connect("button-press-event", self._on_button_press_event)
		self._client.emitter.connect("current_song_changed", self._refresh)
		self._settings.connect("changed::track-cover", self._on_settings_changed)

		event_box.add(self._cover)
		self.add(event_box)

	def clear(self, *args):
		self._cover.set_from_pixbuf(Cover(self._settings, {}).get_pixbuf(self._settings.get_int("track-cover")))
		self.song_file=None

	def _refresh(self, *args):
		current_song=self._client.wrapped_call("currentsong")
		self._cover.set_from_pixbuf(Cover(self._settings, current_song).get_pixbuf(self._settings.get_int("track-cover")))

	def _on_button_press_event(self, widget, event):
		if self._client.connected():
			song=ClientHelper.song_to_first_str_dict(self._client.wrapped_call("currentsong"))
			if song != {}:
				try:
					artist=song[self._settings.get_artist_type()]
				except:
					try:
						artist=song["artist"]
					except:
						artist=""
				try:
					album=song["album"]
				except:
					album=""
				try:
					album_year=song["date"]
				except:
					album_year=""
				if event.button == 1 and event.type == Gdk.EventType.BUTTON_PRESS:
					self._client.wrapped_call("album_to_playlist", album, artist, album_year)
				elif event.button == 2 and event.type == Gdk.EventType.BUTTON_PRESS:
					self._client.wrapped_call("album_to_playlist", album, artist, album_year, "append")
				elif event.button == 3 and event.type == Gdk.EventType.BUTTON_PRESS:
					album_dialog=AlbumDialog(self._window, self._client, self._settings, album, artist, album_year)
					album_dialog.open()
					album_dialog.destroy()

	def _on_settings_changed(self, *args):
		size=self._settings.get_int("track-cover")
		self._cover.set_size_request(size, size)
		self.song_file=None
		self._refresh()

class PlaylistWindow(Gtk.Box):
	def __init__(self, client, settings):
		Gtk.Box.__init__(self, orientation=Gtk.Orientation.VERTICAL)

		# adding vars
		self._client=client
		self._settings=settings
		self._playlist_version=None
		self._icon_size=self._settings.get_int("icon-size-sec")

		# buttons
		self._icons={}
		icons_data=["go-previous-symbolic", "edit-clear-symbolic"]
		for data in icons_data:
			self._icons[data]=PixelSizedIcon(data, self._icon_size)

		provider=Gtk.CssProvider()
		css=b"""* {min-height: 8px;}"""  # allow further shrinking
		provider.load_from_data(css)

		self._back_to_song_button=Gtk.Button(image=self._icons["go-previous-symbolic"])
		self._back_to_song_button.set_tooltip_text(_("Scroll to current song"))
		self._back_to_song_button.set_relief(Gtk.ReliefStyle.NONE)
		style_context=self._back_to_song_button.get_style_context()
		style_context.add_provider(provider, 800)
		self._clear_button=Gtk.Button(image=self._icons["edit-clear-symbolic"])
		self._clear_button.set_tooltip_text(_("Clear playlist"))
		self._clear_button.set_relief(Gtk.ReliefStyle.NONE)
		style_context=self._clear_button.get_style_context()
		style_context.add_class("destructive-action")
		style_context.add_provider(provider, 800)

		# Store
		# (track, disc, title, artist, album, duration, date, genre, file, weight)
		self._store=Gtk.ListStore(str, str, str, str, str, str, str, str, str, Pango.Weight)

		# TreeView
		self._treeview=Gtk.TreeView(model=self._store)
		self._treeview.set_search_column(2)
		self._treeview.set_property("activate-on-single-click", True)

		# selection
		self._selection=self._treeview.get_selection()
		self._selection.set_mode(Gtk.SelectionMode.SINGLE)

		# Columns
		renderer_text=Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END, ellipsize_set=True)
		renderer_text_ralign=Gtk.CellRendererText(xalign=1.0)
		self._columns=[None, None, None, None, None, None, None, None]

		self._columns[0]=Gtk.TreeViewColumn(_("No"), renderer_text_ralign, text=0, weight=9)
		self._columns[1]=Gtk.TreeViewColumn(_("Disc"), renderer_text_ralign, text=1, weight=9)
		self._columns[2]=Gtk.TreeViewColumn(_("Title"), renderer_text, text=2, weight=9)
		self._columns[3]=Gtk.TreeViewColumn(_("Artist"), renderer_text, text=3, weight=9)
		self._columns[4]=Gtk.TreeViewColumn(_("Album"), renderer_text, text=4, weight=9)
		self._columns[5]=Gtk.TreeViewColumn(_("Length"), renderer_text, text=5, weight=9)
		self._columns[6]=Gtk.TreeViewColumn(_("Year"), renderer_text, text=6, weight=9)
		self._columns[7]=Gtk.TreeViewColumn(_("Genre"), renderer_text, text=7, weight=9)

		for column in self._columns:
			column.set_property("resizable", True)
			column.set_min_width(30)

		self._load_settings()

		# scroll
		scroll=Gtk.ScrolledWindow()
		scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
		scroll.add(self._treeview)

		# frame
		frame=FocusFrame()
		frame.set_widget(self._treeview)
		frame.add(scroll)

		# audio infos
		audio=AudioType(self._client)
		audio.set_xalign(1)
		audio.set_ellipsize(Pango.EllipsizeMode.END)

		# playlist info
		self._playlist_info=Gtk.Label()
		self._playlist_info.set_xalign(0)
		self._playlist_info.set_ellipsize(Pango.EllipsizeMode.END)

		# action bar
		action_bar=Gtk.ActionBar()
		action_bar.pack_start(self._back_to_song_button)
		self._playlist_info.set_margin_start(3)
		action_bar.pack_start(self._playlist_info)
		audio.set_margin_end(3)
		audio.set_margin_start(12)
		action_bar.pack_end(self._clear_button)
		action_bar.pack_end(audio)

		# connect
		self._treeview.connect("row-activated", self._on_row_activated)
		self._key_press_event=self._treeview.connect("key-press-event", self._on_key_press_event)
		self._treeview.connect("button-press-event", self._on_button_press_event)
		self._back_to_song_button.connect("clicked", self.scroll_to_selected_title)
		self._clear_button.connect("clicked", self._on_clear_button_clicked)

		self._client.emitter.connect("playlist_changed", self._on_playlist_changed)
		self._client.emitter.connect("current_song_changed", self._on_song_changed)
		self._client.emitter.connect("disconnected", self._on_disconnected)
		self._client.emitter.connect("reconnected", self._on_reconnected)

		self._settings.connect("changed::column-visibilities", self._load_settings)
		self._settings.connect("changed::column-permutation", self._load_settings)
		self._settings.connect("changed::icon-size-sec", self._on_icon_size_changed)

		# packing
		self.pack_start(frame, True, True, 0)
		self.pack_end(action_bar, False, False, 0)

	def clear(self, *args):
		self._playlist_info.set_text("")
		self._store.clear()
		self._playlist_version=None

	def scroll_to_selected_title(self, *args):
		treeview, treeiter=self._selection.get_selected()
		if treeiter is not None:
			path=treeview.get_path(treeiter)
			self._treeview.scroll_to_cell(path, None, True, 0.25)

	def save_settings(self):  # only saves the column sizes
		columns=self._treeview.get_columns()
		permutation=self._settings.get_value("column-permutation").unpack()
		sizes=[0] * len(permutation)
		for i in range(len(permutation)):
			sizes[permutation[i]]=columns[i].get_width()
		self._settings.set_value("column-sizes", GLib.Variant("ai", sizes))

	def _load_settings(self, *args):
		columns=self._treeview.get_columns()
		for column in columns:
			self._treeview.remove_column(column)
		sizes=self._settings.get_value("column-sizes").unpack()
		visibilities=self._settings.get_value("column-visibilities").unpack()
		for i in self._settings.get_value("column-permutation"):
			if sizes[i] > 0:
				self._columns[i].set_fixed_width(sizes[i])
			self._columns[i].set_visible(visibilities[i])
			self._treeview.append_column(self._columns[i])

	def _refresh_playlist_info(self):
		songs=self._client.wrapped_call("playlistinfo")
		if songs == []:
			self._playlist_info.set_text("")
		else:
			whole_length_human_readable=ClientHelper.calc_display_length(songs)
			self._playlist_info.set_text(_("%(total_tracks)i titles (%(total_length)s)") % {"total_tracks": len(songs), "total_length": whole_length_human_readable})

	def _refresh_selection(self, scroll=True):  # Gtk.TreePath(len(self._store) is used to generate an invalid TreePath (needed to unset cursor)
		self._treeview.set_cursor(Gtk.TreePath(len(self._store)), None, False)
		for row in self._store:  # reset bold text
			row[9]=Pango.Weight.BOOK
		try:
			song=self._client.wrapped_call("status")["song"]
			path=Gtk.TreePath(int(song))
			self._selection.select_path(path)
			self._store[path][9]=Pango.Weight.BOLD
			if scroll:
				self.scroll_to_selected_title()
		except:
			self._selection.unselect_all()

	def _remove_song(self, path):
		self._client.wrapped_call("delete", path)  # bad song index possible
		self._store.remove(self._store.get_iter(path))
		self._playlist_version=self._client.wrapped_call("status")["playlist"]

	def _on_key_press_event(self, widget, event):
		self._treeview.handler_block(self._key_press_event)
		if event.keyval == 65535:  # entf
			treeview, treeiter=self._selection.get_selected()
			if treeiter is not None:
				path=self._store.get_path(treeiter)
				try:
					self._remove_song(path)
				except:
					pass
		elif event.keyval == 65383:  # menu key
			treeview, treeiter=self._selection.get_selected()
			if treeiter is not None:
				path=self._store.get_path(treeiter)
				cell=self._treeview.get_cell_area(path, None)
				file_name=self._store[path][8]
				pop=SongPopover(self._client.wrapped_call("get_metadata", file_name), widget, int(cell.x), int(cell.y))
				pop.popup()
				pop.show_all()
		self._treeview.handler_unblock(self._key_press_event)

	def _on_button_press_event(self, widget, event):
		if event.button == 2 and event.type == Gdk.EventType.BUTTON_PRESS:
			try:
				path=widget.get_path_at_pos(int(event.x), int(event.y))[0]
				self._remove_song(path)
			except:
				pass
		elif event.button == 3 and event.type == Gdk.EventType.BUTTON_PRESS:
			try:
				path=widget.get_path_at_pos(int(event.x), int(event.y))[0]
				pop=SongPopover(self._client.wrapped_call("get_metadata", self._store[path][8]), widget, int(event.x), int(event.y))
				pop.popup()
			except:
				pass

	def _on_row_activated(self, widget, path, view_column):
		self._client.wrapped_call("play", path)

	def _on_playlist_changed(self, emitter, version):
		songs=[]
		if self._playlist_version is not None:
			songs=self._client.wrapped_call("plchanges", self._playlist_version)
		else:
			songs=self._client.wrapped_call("playlistinfo")
		if songs != []:
			self._playlist_info.set_text("")
			for s in songs:
				song=ClientHelper.extend_song_for_display(ClientHelper.song_to_str_dict(s))
				try:
					treeiter=self._store.get_iter(song["pos"])
					self._store.set(treeiter, 0, song["track"], 1, song["disc"], 2, song["title"], 3, song["artist"], 4, song["album"], 5, song["human_duration"], 6, song["date"], 7, song["genre"], 8, song["file"], 9, Pango.Weight.BOOK)
				except:
					self._store.append([song["track"], song["disc"], song["title"], song["artist"], song["album"], song["human_duration"], song["date"], song["genre"], song["file"], Pango.Weight.BOOK])
		for i in reversed(range(int(self._client.wrapped_call("status")["playlistlength"]), len(self._store))):
			treeiter=self._store.get_iter(i)
			self._store.remove(treeiter)
		self._refresh_playlist_info()
		if self._playlist_version is None or songs != []:
			self._refresh_selection()
		self._playlist_version=version

	def _on_song_changed(self, *args):
		if self._client.wrapped_call("status")["state"] == "play":
			self._refresh_selection()
		else:
			self._refresh_selection(False)

	def _on_clear_button_clicked(self, *args):
		self._client.clear()

	def _on_disconnected(self, *args):
		self.clear()
		self._back_to_song_button.set_sensitive(False)
		self._clear_button.set_sensitive(False)

	def _on_reconnected(self, *args):
		self._back_to_song_button.set_sensitive(True)
		self._clear_button.set_sensitive(True)

	def _on_icon_size_changed(self, *args):
		pixel_size=self._settings.get_int("icon-size-sec")
		for icon in self._icons.values():
			icon.set_pixel_size(pixel_size)

class CoverLyricsOSD(Gtk.Overlay):
	def __init__(self, client, settings, window):
		Gtk.Overlay.__init__(self)

		# adding vars
		self._client=client
		self._settings=settings
		self._window=window

		# cover
		self._main_cover=MainCover(self._client, self._settings, self._window)
		self._main_cover.set_property("border-width", 3)

		# lyrics button
		self._lyrics_button=Gtk.Button(image=Gtk.Image.new_from_icon_name("media-view-subtitles-symbolic", Gtk.IconSize.BUTTON))
		self._lyrics_button.set_tooltip_text(_("Show lyrics"))
		style_context=self._lyrics_button.get_style_context()
		style_context.add_class("circular")

		# revealer
		# workaround to get tooltips in overlay
		self._revealer=Gtk.Revealer()
		self._revealer.set_halign(2)
		self._revealer.set_valign(1)
		self._revealer.set_margin_top(6)
		self._revealer.set_margin_end(6)
		self._revealer.add(self._lyrics_button)

		# packing
		self.add(self._main_cover)
		self.add_overlay(self._revealer)

		# connect
		self._lyrics_button.connect("clicked", self._on_lyrics_clicked)
		self._client.emitter.connect("disconnected", self._on_disconnected)
		self._client.emitter.connect("reconnected", self._on_reconnected)
		self._settings.connect("changed::show-lyrics-button", self._on_settings_changed)

		self._on_settings_changed()  # hide lyrics button

	def show_lyrics(self, *args):
		if self._lyrics_button.get_sensitive():
			self._lyrics_button.emit("clicked")

	def _on_reconnected(self, *args):
		self._lyrics_button.set_sensitive(True)

	def _on_disconnected(self, *args):
		self._lyrics_button.set_sensitive(False)
		self._main_cover.clear()
		try:
			self._lyrics_win.destroy()
		except:
			pass

	def _on_lyrics_clicked(self, widget):
		self._lyrics_button.set_sensitive(False)
		self._lyrics_win=LyricsWindow(self._client, self._settings)
		def on_destroy(*args):
			self._lyrics_button.set_sensitive(True)
		self._lyrics_win.connect("destroy", on_destroy)
		self.add_overlay(self._lyrics_win)

	def _on_settings_changed(self, *args):
		if self._settings.get_boolean("show-lyrics-button"):
			self._revealer.set_reveal_child(True)
		else:
			self._revealer.set_reveal_child(False)

class CoverPlaylistWindow(Gtk.Paned):
	def __init__(self, client, settings, window):
		Gtk.Paned.__init__(self)  # paned0

		# adding vars
		self._client=client
		self._settings=settings

		# widgets
		self._cover_lyrics_osd=CoverLyricsOSD(self._client, self._settings, window)
		self._playlist_window=PlaylistWindow(self._client, self._settings)

		# packing
		self.pack1(self._cover_lyrics_osd, False, False)
		self.pack2(self._playlist_window, True, False)

		self.set_position(self._settings.get_int("paned0"))

	def show_lyrics(self, *args):
		self._cover_lyrics_osd.show_lyrics()

	def save_settings(self):
		self._settings.set_int("paned0", self.get_position())
		self._playlist_window.save_settings()

###################
# settings dialog #
###################

class GeneralSettings(Gtk.Box):
	def __init__(self, settings):
		Gtk.Box.__init__(self, orientation=Gtk.Orientation.VERTICAL, spacing=6)
		self.set_property("border-width", 18)

		# adding vars
		self._settings=settings
		self._settings_handlers=[]

		# int_settings
		int_settings={}
		int_settings_data=[(_("Main cover size:"), (100, 1200, 10), "track-cover"),\
				(_("Album view cover size:"), (50, 600, 10), "album-cover"),\
				(_("Action bar icon size:"), (16, 64, 2), "icon-size"),\
				(_("Secondary icon size:"), (16, 64, 2), "icon-size-sec")]
		for data in int_settings_data:
			int_settings[data[2]]=(Gtk.Label(), IntEntry(self._settings.get_int(data[2]), data[1][0], data[1][1], data[1][2]))
			int_settings[data[2]][0].set_label(data[0])
			int_settings[data[2]][0].set_xalign(0)
			int_settings[data[2]][1].connect("value-changed", self._on_int_changed, data[2])
			self._settings_handlers.append(self._settings.connect("changed::"+data[2], self._on_int_settings_changed, int_settings[data[2]][1]))

		# combo_settings
		combo_settings={}
		combo_settings_data=[(_("Sort albums by:"), _("name"), _("year"), "sort-albums-by-year"), \
					(_("Position of playlist:"), _("bottom"), _("right"), "playlist-right")]
		for data in combo_settings_data:
			combo_settings[data[3]]=(Gtk.Label(), Gtk.ComboBoxText())
			combo_settings[data[3]][0].set_label(data[0])
			combo_settings[data[3]][0].set_xalign(0)
			combo_settings[data[3]][1].set_entry_text_column(0)
			combo_settings[data[3]][1].append_text(data[1])
			combo_settings[data[3]][1].append_text(data[2])
			if self._settings.get_boolean(data[3]):
				combo_settings[data[3]][1].set_active(1)
			else:
				combo_settings[data[3]][1].set_active(0)
			combo_settings[data[3]][1].connect("changed", self._on_combo_changed, data[3])
			self._settings_handlers.append(self._settings.connect("changed::"+data[3], self._on_combo_settings_changed, combo_settings[data[3]][1]))

		# check buttons
		check_buttons={}
		check_buttons_data=[(_("Use Client-side decoration"), "use-csd"), \
				(_("Show stop button"), "show-stop"), \
				(_("Show lyrics button"), "show-lyrics-button"), \
				(_("Show initials in artist view"), "show-initials"), \
				(_("Show tooltips in album view"), "show-album-view-tooltips"), \
				(_("Use 'Album Artist' tag"), "use-album-artist"), \
				(_("Send notification on title change"), "send-notify"), \
				(_("Stop playback on quit"), "stop-on-quit"), \
				(_("Play selected albums and titles immediately"), "force-mode")]

		for data in check_buttons_data:
			check_buttons[data[1]]=Gtk.CheckButton(label=data[0])
			check_buttons[data[1]].set_active(self._settings.get_boolean(data[1]))
			check_buttons[data[1]].set_margin_start(12)
			check_buttons[data[1]].connect("toggled", self._on_toggled, data[1])
			self._settings_handlers.append(self._settings.connect("changed::"+data[1], self._on_check_settings_changed, check_buttons[data[1]]))

		# headings
		view_heading=Gtk.Label()
		view_heading.set_markup(_("<b>View</b>"))
		view_heading.set_xalign(0)
		behavior_heading=Gtk.Label()
		behavior_heading.set_markup(_("<b>Behavior</b>"))
		behavior_heading.set_xalign(0)

		# view grid
		view_grid=Gtk.Grid()
		view_grid.set_row_spacing(6)
		view_grid.set_column_spacing(12)
		view_grid.set_margin_start(12)
		view_grid.add(int_settings["track-cover"][0])
		view_grid.attach_next_to(int_settings["album-cover"][0], int_settings["track-cover"][0], Gtk.PositionType.BOTTOM, 1, 1)
		view_grid.attach_next_to(int_settings["icon-size"][0], int_settings["album-cover"][0], Gtk.PositionType.BOTTOM, 1, 1)
		view_grid.attach_next_to(int_settings["icon-size-sec"][0], int_settings["icon-size"][0], Gtk.PositionType.BOTTOM, 1, 1)
		view_grid.attach_next_to(combo_settings["playlist-right"][0], int_settings["icon-size-sec"][0], Gtk.PositionType.BOTTOM, 1, 1)
		view_grid.attach_next_to(int_settings["track-cover"][1], int_settings["track-cover"][0], Gtk.PositionType.RIGHT, 1, 1)
		view_grid.attach_next_to(int_settings["album-cover"][1], int_settings["album-cover"][0], Gtk.PositionType.RIGHT, 1, 1)
		view_grid.attach_next_to(int_settings["icon-size"][1], int_settings["icon-size"][0], Gtk.PositionType.RIGHT, 1, 1)
		view_grid.attach_next_to(int_settings["icon-size-sec"][1], int_settings["icon-size-sec"][0], Gtk.PositionType.RIGHT, 1, 1)
		view_grid.attach_next_to(combo_settings["playlist-right"][1], combo_settings["playlist-right"][0], Gtk.PositionType.RIGHT, 1, 1)

		# behavior grid
		behavior_grid=Gtk.Grid()
		behavior_grid.set_row_spacing(6)
		behavior_grid.set_column_spacing(12)
		behavior_grid.set_margin_start(12)
		behavior_grid.add(combo_settings["sort-albums-by-year"][0])
		behavior_grid.attach_next_to(combo_settings["sort-albums-by-year"][1], combo_settings["sort-albums-by-year"][0], Gtk.PositionType.RIGHT, 1, 1)

		# connect
		self.connect("destroy", self._remove_handlers)

		# packing
		box=Gtk.Box(spacing=12)
		box.pack_start(check_buttons["use-csd"], False, False, 0)
		box.pack_start(Gtk.Label(label=_("(restart required)"), sensitive=False), False, False, 0)
		self.pack_start(view_heading, False, False, 0)
		self.pack_start(box, False, False, 0)
		self.pack_start(check_buttons["show-stop"], False, False, 0)
		self.pack_start(check_buttons["show-lyrics-button"], False, False, 0)
		self.pack_start(check_buttons["show-initials"], False, False, 0)
		self.pack_start(check_buttons["show-album-view-tooltips"], False, False, 0)
		self.pack_start(view_grid, False, False, 0)
		self.pack_start(behavior_heading, False, False, 0)
		self.pack_start(check_buttons["use-album-artist"], False, False, 0)
		self.pack_start(check_buttons["send-notify"], False, False, 0)
		self.pack_start(check_buttons["stop-on-quit"], False, False, 0)
		self.pack_start(check_buttons["force-mode"], False, False, 0)
		self.pack_start(behavior_grid, False, False, 0)

	def _remove_handlers(self, *args):
		for handler in self._settings_handlers:
			self._settings.disconnect(handler)

	def _on_int_settings_changed(self, settings, key, entry):
		entry.set_value(settings.get_int(key))

	def _on_combo_settings_changed(self, settings, key, combo):
		if settings.get_boolean(key):
			combo.set_active(1)
		else:
			combo.set_active(0)

	def _on_check_settings_changed(self, settings, key, button):
		button.set_active(settings.get_boolean(key))

	def _on_int_changed(self, widget, key):
		self._settings.set_int(key, widget.get_int())

	def _on_combo_changed(self, box, key):
		active=box.get_active()
		if active == 0:
			self._settings.set_boolean(key, False)
		else:
			self._settings.set_boolean(key, True)

	def _on_toggled(self, widget, key):
		self._settings.set_boolean(key, widget.get_active())

class ProfileSettings(Gtk.Grid):
	def __init__(self, parent, settings):
		Gtk.Grid.__init__(self)
		self.set_row_spacing(6)
		self.set_column_spacing(12)
		self.set_property("border-width", 18)

		# adding vars
		self._settings=settings
		self._gui_modification=False  # indicates whether the settings were changed from the settings dialog

		# widgets
		self._profiles_combo=Gtk.ComboBoxText(hexpand=True)
		self._profiles_combo.set_entry_text_column(0)

		add_button=Gtk.Button(label=None, image=Gtk.Image(stock=Gtk.STOCK_ADD))
		delete_button=Gtk.Button(label=None, image=Gtk.Image(stock=Gtk.STOCK_DELETE))
		add_delete_buttons=Gtk.ButtonBox()
		add_delete_buttons.set_property("layout-style", Gtk.ButtonBoxStyle.EXPAND)
		add_delete_buttons.pack_start(add_button, True, True, 0)
		add_delete_buttons.pack_start(delete_button, True, True, 0)

		self._profile_entry=Gtk.Entry(hexpand=True)
		self._host_entry=Gtk.Entry(hexpand=True)
		self._port_entry=IntEntry(0, 0, 65535, 1)
		address_entry=Gtk.Box(spacing=6)
		address_entry.pack_start(self._host_entry, True, True, 0)
		address_entry.pack_start(self._port_entry, False, False, 0)
		self._password_entry=Gtk.Entry(hexpand=True)
		self._password_entry.set_visibility(False)
		self._path_entry=Gtk.Entry(hexpand=True)
		self._path_select_button=Gtk.Button(image=Gtk.Image(stock=Gtk.STOCK_OPEN))
		path_box=Gtk.Box(spacing=6)
		path_box.pack_start(self._path_entry, True, True, 0)
		path_box.pack_start(self._path_select_button, False, False, 0)
		self._regex_entry=Gtk.Entry(hexpand=True)
		self._regex_entry.set_property("placeholder-text", COVER_REGEX)
		self._regex_entry.set_tooltip_text(_("The first image in the same directory as the song file matching this regex will be displayed. %AlbumArtist% and %Album% will be replaced by the corresponding tags of the song."))

		profiles_label=Gtk.Label(label=_("Profile:"))
		profiles_label.set_xalign(1)
		profile_label=Gtk.Label(label=_("Name:"))
		profile_label.set_xalign(1)
		host_label=Gtk.Label(label=_("Host:"))
		host_label.set_xalign(1)
		password_label=Gtk.Label(label=_("Password:"))
		password_label.set_xalign(1)
		path_label=Gtk.Label(label=_("Music lib:"))
		path_label.set_xalign(1)
		regex_label=Gtk.Label(label=_("Cover regex:"))
		regex_label.set_xalign(1)

		# connect
		add_button.connect("clicked", self._on_add_button_clicked)
		delete_button.connect("clicked", self._on_delete_button_clicked)
		self._path_select_button.connect("clicked", self._on_path_select_button_clicked, parent)
		self._profiles_combo.connect("changed", self._on_profiles_changed)
		self.entry_changed_handlers=[]
		self.entry_changed_handlers.append((self._profile_entry, self._profile_entry.connect("changed", self._on_profile_entry_changed)))
		self.entry_changed_handlers.append((self._host_entry, self._host_entry.connect("changed", self._on_host_entry_changed)))
		self.entry_changed_handlers.append((self._port_entry, self._port_entry.connect("value-changed", self._on_port_entry_changed)))
		self.entry_changed_handlers.append((self._password_entry, self._password_entry.connect("changed", self._on_password_entry_changed)))
		self.entry_changed_handlers.append((self._path_entry, self._path_entry.connect("changed", self._on_path_entry_changed)))
		self.entry_changed_handlers.append((self._regex_entry, self._regex_entry.connect("changed", self._on_regex_entry_changed)))
		self._settings_handlers=[]
		self._settings_handlers.append(self._settings.connect("changed::profiles", self._on_settings_changed))
		self._settings_handlers.append(self._settings.connect("changed::hosts", self._on_settings_changed))
		self._settings_handlers.append(self._settings.connect("changed::ports", self._on_settings_changed))
		self._settings_handlers.append(self._settings.connect("changed::passwords", self._on_settings_changed))
		self._settings_handlers.append(self._settings.connect("changed::paths", self._on_settings_changed))
		self._settings_handlers.append(self._settings.connect("changed::regex", self._on_settings_changed))
		self.connect("destroy", self._remove_handlers)

		self._profiles_combo_reload()
		self._profiles_combo.set_active(0)

		# packing
		self.add(profiles_label)
		self.attach_next_to(profile_label, profiles_label, Gtk.PositionType.BOTTOM, 1, 1)
		self.attach_next_to(host_label, profile_label, Gtk.PositionType.BOTTOM, 1, 1)
		self.attach_next_to(password_label, host_label, Gtk.PositionType.BOTTOM, 1, 1)
		self.attach_next_to(path_label, password_label, Gtk.PositionType.BOTTOM, 1, 1)
		self.attach_next_to(regex_label, path_label, Gtk.PositionType.BOTTOM, 1, 1)
		self.attach_next_to(self._profiles_combo, profiles_label, Gtk.PositionType.RIGHT, 2, 1)
		self.attach_next_to(add_delete_buttons, self._profiles_combo, Gtk.PositionType.RIGHT, 1, 1)
		self.attach_next_to(self._profile_entry, profile_label, Gtk.PositionType.RIGHT, 2, 1)
		self.attach_next_to(address_entry, host_label, Gtk.PositionType.RIGHT, 2, 1)
		self.attach_next_to(self._password_entry, password_label, Gtk.PositionType.RIGHT, 2, 1)
		self.attach_next_to(path_box, path_label, Gtk.PositionType.RIGHT, 2, 1)
		self.attach_next_to(self._regex_entry, regex_label, Gtk.PositionType.RIGHT, 2, 1)

	def _block_entry_changed_handlers(self, *args):
		for obj, handler in self.entry_changed_handlers:
			obj.handler_block(handler)

	def _unblock_entry_changed_handlers(self, *args):
		for obj, handler in self.entry_changed_handlers:
			obj.handler_unblock(handler)

	def _profiles_combo_reload(self, *args):
		self._block_entry_changed_handlers()

		self._profiles_combo.remove_all()
		for profile in self._settings.get_value("profiles"):
			self._profiles_combo.append_text(profile)

		self._unblock_entry_changed_handlers()

	def _remove_handlers(self, *args):
		for handler in self._settings_handlers:
			self._settings.disconnect(handler)

	def _on_settings_changed(self, *args):
		if self._gui_modification:
			self._gui_modification=False
		else:
			self._profiles_combo_reload()
			self._profiles_combo.set_active(0)

	def _on_add_button_clicked(self, *args):
		model=self._profiles_combo.get_model()
		self._settings.array_append('as', "profiles", "new profile ("+str(len(model))+")")
		self._settings.array_append('as', "hosts", "localhost")
		self._settings.array_append('ai', "ports", 6600)
		self._settings.array_append('as', "passwords", "")
		self._settings.array_append('as', "paths", "")
		self._settings.array_append('as', "regex", "")
		self._profiles_combo_reload()
		new_pos=len(model)-1
		self._profiles_combo.set_active(new_pos)

	def _on_delete_button_clicked(self, *args):
		pos=self._profiles_combo.get_active()
		self._settings.array_delete('as', "profiles", pos)
		self._settings.array_delete('as', "hosts", pos)
		self._settings.array_delete('ai', "ports", pos)
		self._settings.array_delete('as', "passwords", pos)
		self._settings.array_delete('as', "paths", pos)
		self._settings.array_delete('as', "regex", pos)
		if len(self._settings.get_value("profiles")) == 0:
			self._on_add_button_clicked()
		else:
			self._profiles_combo_reload()
			new_pos=max(pos-1,0)
			self._profiles_combo.set_active(new_pos)

	def _on_profile_entry_changed(self, *args):
		self._gui_modification=True
		pos=self._profiles_combo.get_active()
		self._settings.array_modify('as', "profiles", pos, self._profile_entry.get_text())
		self._profiles_combo_reload()
		self._profiles_combo.set_active(pos)

	def _on_host_entry_changed(self, *args):
		self._gui_modification=True
		self._settings.array_modify('as', "hosts", self._profiles_combo.get_active(), self._host_entry.get_text())

	def _on_port_entry_changed(self, *args):
		self._gui_modification=True
		self._settings.array_modify('ai', "ports", self._profiles_combo.get_active(), self._port_entry.get_int())

	def _on_password_entry_changed(self, *args):
		self._gui_modification=True
		self._settings.array_modify('as', "passwords", self._profiles_combo.get_active(), self._password_entry.get_text())

	def _on_path_entry_changed(self, *args):
		self._gui_modification=True
		self._settings.array_modify('as', "paths", self._profiles_combo.get_active(), self._path_entry.get_text())

	def _on_regex_entry_changed(self, *args):
		self._gui_modification=True
		self._settings.array_modify('as', "regex", self._profiles_combo.get_active(), self._regex_entry.get_text())

	def _on_path_select_button_clicked(self, widget, parent):
		dialog=Gtk.FileChooserDialog(title=_("Choose directory"), transient_for=parent, action=Gtk.FileChooserAction.SELECT_FOLDER)
		dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
		dialog.add_buttons(Gtk.STOCK_OK, Gtk.ResponseType.OK)
		dialog.set_default_size(800, 400)
		dialog.set_current_folder(self._settings.get_value("paths")[self._profiles_combo.get_active()])
		response=dialog.run()
		if response == Gtk.ResponseType.OK:
			self._gui_modification=True
			self._settings.array_modify('as', "paths", self._profiles_combo.get_active(), dialog.get_filename())
			self._path_entry.set_text(dialog.get_filename())
		dialog.destroy()

	def _on_profiles_changed(self, *args):
		active=self._profiles_combo.get_active()
		self._block_entry_changed_handlers()

		self._profile_entry.set_text(self._settings.get_value("profiles")[active])
		self._host_entry.set_text(self._settings.get_value("hosts")[active])
		self._port_entry.set_int(self._settings.get_value("ports")[active])
		self._password_entry.set_text(self._settings.get_value("passwords")[active])
		self._path_entry.set_text(self._settings.get_value("paths")[active])
		self._regex_entry.set_text(self._settings.get_value("regex")[active])

		self._unblock_entry_changed_handlers()

class PlaylistSettings(Gtk.Box):
	def __init__(self, settings):
		Gtk.Box.__init__(self, orientation=Gtk.Orientation.VERTICAL, spacing=6)
		self.set_property("border-width", 18)

		# adding vars
		self._settings=settings

		# label
		label=Gtk.Label(label=_("Choose the order of information to appear in the playlist:"))
		label.set_line_wrap(True)
		label.set_xalign(0)

		# Store
		# (toggle, header, actual_index)
		self._store=Gtk.ListStore(bool, str, int)

		# TreeView
		treeview=Gtk.TreeView(model=self._store)
		treeview.set_search_column(-1)
		treeview.set_reorderable(True)
		treeview.set_headers_visible(False)

		# selection
		self._selection=treeview.get_selection()

		# Column
		renderer_text=Gtk.CellRendererText()
		renderer_toggle=Gtk.CellRendererToggle()

		column_toggle=Gtk.TreeViewColumn("", renderer_toggle, active=0)
		treeview.append_column(column_toggle)

		column_text=Gtk.TreeViewColumn("", renderer_text, text=1)
		treeview.append_column(column_text)

		# fill store
		self._headers=[_("No"), _("Disc"), _("Title"), _("Artist"), _("Album"), _("Length"), _("Year"), _("Genre")]
		self._fill()

		# scroll
		scroll=Gtk.ScrolledWindow()
		scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
		scroll.add(treeview)
		frame=Gtk.Frame()
		frame.add(scroll)

		# Toolbar
		toolbar=Gtk.Toolbar()
		style_context=toolbar.get_style_context()
		style_context.add_class("inline-toolbar")
		self._up_button=Gtk.ToolButton.new(Gtk.Image.new_from_icon_name("go-up-symbolic", Gtk.IconSize.SMALL_TOOLBAR))
		self._up_button.set_sensitive(False)
		self._down_button=Gtk.ToolButton.new(Gtk.Image.new_from_icon_name("go-down-symbolic", Gtk.IconSize.SMALL_TOOLBAR))
		self._down_button.set_sensitive(False)
		toolbar.insert(self._up_button, 0)
		toolbar.insert(self._down_button, 1)

		# column chooser
		column_chooser=Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
		column_chooser.pack_start(frame, True, True, 0)
		column_chooser.pack_start(toolbar, False, False, 0)

		# connect
		self._row_deleted=self._store.connect("row-deleted", self._save_permutation)
		renderer_toggle.connect("toggled", self._on_cell_toggled)
		self._up_button.connect("clicked", self._on_up_button_clicked)
		self._down_button.connect("clicked", self._on_down_button_clicked)
		self._selection.connect("changed", self._set_button_sensitivity)
		self._settings_handlers=[]
		self._settings_handlers.append(self._settings.connect("changed::column-visibilities", self._on_visibilities_changed))
		self._settings_handlers.append(self._settings.connect("changed::column-permutation", self._on_permutation_changed))
		self.connect("destroy", self._remove_handlers)

		# packing
		self.pack_start(label, False, False, 0)
		self.pack_start(column_chooser, True, True, 0)

	def _fill(self, *args):
		visibilities=self._settings.get_value("column-visibilities").unpack()
		for actual_index in self._settings.get_value("column-permutation"):
			self._store.append([visibilities[actual_index], self._headers[actual_index], actual_index])

	def _save_permutation(self, *args):
		permutation=[]
		for row in self._store:
			permutation.append(row[2])
		self._settings.set_value("column-permutation", GLib.Variant("ai", permutation))

	def _set_button_sensitivity(self, *args):
		treeiter=self._selection.get_selected()[1]
		if treeiter is None:
			self._up_button.set_sensitive(False)
			self._down_button.set_sensitive(False)
		else:
			path=self._store.get_path(treeiter)
			if self._store.iter_next(treeiter) is None:
				self._up_button.set_sensitive(True)
				self._down_button.set_sensitive(False)
			elif not path.prev():
				self._up_button.set_sensitive(False)
				self._down_button.set_sensitive(True)
			else:
				self._up_button.set_sensitive(True)
				self._down_button.set_sensitive(True)

	def _remove_handlers(self, *args):
		for handler in self._settings_handlers:
			self._settings.disconnect(handler)

	def _on_cell_toggled(self, widget, path):
		self._store[path][0]=not self._store[path][0]
		self._settings.array_modify('ab', "column-visibilities", self._store[path][2], self._store[path][0])

	def _on_up_button_clicked(self, *args):
		treeiter=self._selection.get_selected()[1]
		path=self._store.get_path(treeiter)
		path.prev()
		prev=self._store.get_iter(path)
		self._store.move_before(treeiter, prev)
		self._set_button_sensitivity()
		self._save_permutation()

	def _on_down_button_clicked(self, *args):
		treeiter=self._selection.get_selected()[1]
		path=self._store.get_path(treeiter)
		next=self._store.iter_next(treeiter)
		self._store.move_after(treeiter, next)
		self._set_button_sensitivity()
		self._save_permutation()

	def _on_visibilities_changed(self, *args):
		visibilities=self._settings.get_value("column-visibilities").unpack()
		for i, actual_index in enumerate(self._settings.get_value("column-permutation")):
			self._store[i][0]=visibilities[actual_index]

	def _on_permutation_changed(self, *args):
		equal=True
		perm=self._settings.get_value("column-permutation")
		for i, e in enumerate(self._store):
			if e[2] != perm[i]:
				equal=False
				break
		if not equal:
			self._store.handler_block(self._row_deleted)
			self._store.clear()
			self._fill()
			self._store.handler_unblock(self._row_deleted)

class SettingsDialog(Gtk.Dialog):
	def __init__(self, parent, settings):
		use_csd=settings.get_boolean("use-csd")
		if use_csd:
			Gtk.Dialog.__init__(self, title=_("Settings"), transient_for=parent, use_header_bar=True)
			# css
			style_context=self.get_style_context()
			provider=Gtk.CssProvider()
			css=b"""* {-GtkDialog-content-area-border: 0px;}"""
			provider.load_from_data(css)
			style_context.add_provider(provider, 800)
		else:
			Gtk.Dialog.__init__(self, title=_("Settings"), transient_for=parent)
			self.add_button(Gtk.STOCK_OK, Gtk.ResponseType.OK)
		self.set_default_size(500, 400)

		# widgets
		general=GeneralSettings(settings)
		profiles=ProfileSettings(parent, settings)
		playlist=PlaylistSettings(settings)

		# packing
		tabs=Gtk.Notebook()
		tabs.append_page(general, Gtk.Label(label=_("General")))
		tabs.append_page(profiles, Gtk.Label(label=_("Profiles")))
		tabs.append_page(playlist, Gtk.Label(label=_("Playlist")))
		vbox=self.get_content_area()
		vbox.set_spacing(6)
		vbox.pack_start(tabs, True, True, 0)

		self.show_all()

###################
# control widgets #
###################

class PlaybackControl(Gtk.ButtonBox):
	def __init__(self, client, settings):
		Gtk.ButtonBox.__init__(self, spacing=6)
		self.set_property("layout-style", Gtk.ButtonBoxStyle.EXPAND)

		# adding vars
		self._client=client
		self._settings=settings
		self._icon_size=self._settings.get_int("icon-size")

		# widgets
		self._icons={}
		icons_data=["media-playback-start-symbolic", "media-playback-stop-symbolic", "media-playback-pause-symbolic", \
				"media-skip-backward-symbolic", "media-skip-forward-symbolic"]
		for data in icons_data:
			self._icons[data]=PixelSizedIcon(data, self._icon_size)

		self.play_button=Gtk.Button(image=self._icons["media-playback-start-symbolic"])
		self.stop_button=Gtk.Button(image=self._icons["media-playback-stop-symbolic"])
		self.prev_button=Gtk.Button(image=self._icons["media-skip-backward-symbolic"])
		self.next_button=Gtk.Button(image=self._icons["media-skip-forward-symbolic"])

		# connect
		self.play_button.connect("clicked", self._on_play_clicked)
		self.stop_button.connect("clicked", self._on_stop_clicked)
		self.prev_button.connect("clicked", self._on_prev_clicked)
		self.next_button.connect("clicked", self._on_next_clicked)
		self._settings.connect("changed::show-stop", self._on_settings_changed)
		self._settings.connect("changed::icon-size", self._on_icon_size_changed)
		self._client.emitter.connect("state", self._on_state)

		# packing
		self.pack_start(self.prev_button, True, True, 0)
		self.pack_start(self.play_button, True, True, 0)
		if self._settings.get_boolean("show-stop"):
			self.pack_start(self.stop_button, True, True, 0)
		self.pack_start(self.next_button, True, True, 0)

	def _on_state(self, emitter, state):
		if state == "play":
			self.play_button.set_image(self._icons["media-playback-pause-symbolic"])
			self.prev_button.set_sensitive(True)
			self.next_button.set_sensitive(True)
		elif state == "pause":
			self.play_button.set_image(self._icons["media-playback-start-symbolic"])
			self.prev_button.set_sensitive(True)
			self.next_button.set_sensitive(True)
		else:
			self.play_button.set_image(self._icons["media-playback-start-symbolic"])
			self.prev_button.set_sensitive(False)
			self.next_button.set_sensitive(False)

	def _on_play_clicked(self, widget):
		if self._client.connected():
			status=self._client.wrapped_call("status")
			if status["state"] == "play":
				self._client.wrapped_call("pause", 1)
			elif status["state"] == "pause":
				self._client.wrapped_call("pause", 0)
			else:
				try:
					self._client.wrapped_call("play")
				except:
					pass

	def _on_stop_clicked(self, widget):
		if self._client.connected():
			self._client.wrapped_call("stop")

	def _on_prev_clicked(self, widget):
		if self._client.connected():
			self._client.wrapped_call("previous")

	def _on_next_clicked(self, widget):
		if self._client.connected():
			self._client.wrapped_call("next")

	def _on_settings_changed(self, *args):
		if self._settings.get_boolean("show-stop"):
			self.pack_start(self.stop_button, True, True, 0)
			self.reorder_child(self.stop_button, 2)
			self.stop_button.show()
		else:
			self.remove(self.stop_button)

	def _on_icon_size_changed(self, *args):
		pixel_size=self._settings.get_int("icon-size")
		for icon in self._icons.values():
			icon.set_pixel_size(pixel_size)

class SeekBar(Gtk.Box):
	def __init__(self, client):
		Gtk.Box.__init__(self)
		self.set_hexpand(True)

		# adding vars
		self._client=client
		self._seek_time="10"  # seek increment in seconds
		self._update=True
		self._jumped=False

		# labels
		self._elapsed=Gtk.Label()
		self._elapsed.set_width_chars(5)
		self._rest=Gtk.Label()
		self._rest.set_width_chars(6)

		# progress bar
		self.scale=Gtk.Scale.new_with_range(orientation=Gtk.Orientation.HORIZONTAL, min=0, max=100, step=0.001)
		self.scale.set_show_fill_level(True)
		self.scale.set_restrict_to_fill_level(False)
		self.scale.set_draw_value(False)

		# css (scale)
		style_context=self.scale.get_style_context()
		provider=Gtk.CssProvider()
		css=b"""scale fill { background-color: @theme_selected_bg_color; }"""
		provider.load_from_data(css)
		style_context.add_provider(provider, 800)

		# event boxes
		self._elapsed_event_box=Gtk.EventBox()
		self._rest_event_box=Gtk.EventBox()

		# connect
		self._elapsed_event_box.connect("button-press-event", self._on_elapsed_button_press_event)
		self._rest_event_box.connect("button-press-event", self._on_rest_button_press_event)
		self.scale.connect("change-value", self._on_change_value)
		self.scale.connect("scroll-event", self._dummy)  # disable mouse wheel
		self.scale.connect("button-press-event", self._on_scale_button_press_event)
		self.scale.connect("button-release-event", self._on_scale_button_release_event)
		self._client.emitter.connect("disconnected", self._on_disconnected)
		self._client.emitter.connect("reconnected", self._on_reconnected)
		self._client.emitter.connect("state", self._on_state)
		self._client.emitter.connect("elapsed_changed", self._refresh)

		# packing
		self._elapsed_event_box.add(self._elapsed)
		self._rest_event_box.add(self._rest)
		self.pack_start(self._elapsed_event_box, False, False, 0)
		self.pack_start(self.scale, True, True, 0)
		self.pack_end(self._rest_event_box, False, False, 0)

	def _dummy(self, *args):
		return True

	def seek_forward(self):
		self._client.wrapped_call("seekcur", "+"+self._seek_time)

	def seek_backward(self):
		self._client.wrapped_call("seekcur", "-"+self._seek_time)

	def _refresh(self, emitter, elapsed, duration):
		if elapsed > duration:  # fix display error
			elapsed=duration
		fraction=(elapsed/duration)*100
		if self._update:
			self.scale.set_value(fraction)
			self._elapsed.set_text(str(datetime.timedelta(seconds=int(elapsed))).lstrip("0").lstrip(":"))
			self._rest.set_text("-"+str(datetime.timedelta(seconds=int(duration-elapsed))).lstrip("0").lstrip(":"))
		self.scale.set_fill_level(fraction)

	def _enable(self, *args):
		self.scale.set_range(0, 100)
		self.set_sensitive(True)

	def _disable(self, *args):
		self.set_sensitive(False)
		self.scale.set_range(0, 0)
		self._elapsed.set_text("00:00")
		self._rest.set_text("-00:00")

	def _on_scale_button_press_event(self, widget, event):
		if event.button == 1 and event.type == Gdk.EventType.BUTTON_PRESS:
			self._update=False
			self.scale.set_has_origin(False)
		if event.button == 3 and event.type == Gdk.EventType.BUTTON_PRESS:
			self._jumped=False

	def _on_scale_button_release_event(self, widget, event):
		if event.button == 1:
			self._update=True
			self.scale.set_has_origin(True)
			status=self._client.wrapped_call("status")
			if self._jumped:  # actual seek
				duration=float(status["duration"])
				factor=(self.scale.get_value()/100)
				pos=(duration*factor)
				self._client.wrapped_call("seekcur", pos)
				self._jumped=False
			else:
				self._refresh(None, float(status["elapsed"]), float(status["duration"]))

	def _on_change_value(self, range, scroll, value):  # value is inaccurate
		if scroll == Gtk.ScrollType.STEP_BACKWARD:
			self.seek_backward()
		elif scroll == Gtk.ScrollType.STEP_FORWARD:
			self.seek_forward()
		elif scroll == Gtk.ScrollType.JUMP:
			status=self._client.wrapped_call("status")
			duration=float(status["duration"])
			factor=(value/100)
			if factor > 1:  # fix display error
				factor=1
			elapsed=(factor*duration)
			self._elapsed.set_text(str(datetime.timedelta(seconds=int(elapsed))).lstrip("0").lstrip(":"))
			self._rest.set_text("-"+str(datetime.timedelta(seconds=int(duration-elapsed))).lstrip("0").lstrip(":"))
			self._jumped=True

	def _on_elapsed_button_press_event(self, widget, event):
		if event.button == 1 and event.type == Gdk.EventType.BUTTON_PRESS:
			self.seek_backward()
		elif event.button == 3 and event.type == Gdk.EventType.BUTTON_PRESS:
			self.seek_forward()

	def _on_rest_button_press_event(self, widget, event):
		if event.button == 1 and event.type == Gdk.EventType.BUTTON_PRESS:
			self.seek_forward()
		elif event.button == 3 and event.type == Gdk.EventType.BUTTON_PRESS:
			self.seek_backward()

	def _on_state(self, emitter, state):
		if state == "stop":
			self._disable()
		else:
			self._enable()

	def _on_reconnected(self, *args):
		self._enable()

	def _on_disconnected(self, *args):
		self._disable()

class PlaybackOptions(Gtk.Box):
	def __init__(self, client, settings):
		Gtk.Box.__init__(self, spacing=6)

		# adding vars
		self._client=client
		self._settings=settings
		self._icon_size=self._settings.get_int("icon-size")

		# widgets
		self._icons={}
		icons_data=["media-playlist-shuffle-symbolic", "media-playlist-repeat-symbolic", "zoom-original-symbolic", "edit-cut-symbolic"]
		for data in icons_data:
			self._icons[data]=PixelSizedIcon(data, self._icon_size)

		self._random_button=Gtk.ToggleButton(image=self._icons["media-playlist-shuffle-symbolic"])
		self._random_button.set_tooltip_text(_("Random mode"))
		self._repeat_button=Gtk.ToggleButton(image=self._icons["media-playlist-repeat-symbolic"])
		self._repeat_button.set_tooltip_text(_("Repeat mode"))
		self._single_button=Gtk.ToggleButton(image=self._icons["zoom-original-symbolic"])
		self._single_button.set_tooltip_text(_("Single mode"))
		self._consume_button=Gtk.ToggleButton(image=self._icons["edit-cut-symbolic"])
		self._consume_button.set_tooltip_text(_("Consume mode"))
		self._volume_button=Gtk.VolumeButton()
		self._volume_button.set_property("use-symbolic", True)
		self._volume_button.set_property("size", self._settings.get_gtk_icon_size("icon-size"))

		# connect
		self._random_button_toggled=self._random_button.connect("toggled", self._set_option, "random")
		self._repeat_button_toggled=self._repeat_button.connect("toggled", self._set_option, "repeat")
		self._single_button_toggled=self._single_button.connect("toggled", self._set_option, "single")
		self._consume_button_toggled=self._consume_button.connect("toggled", self._set_option, "consume")
		self._volume_button_changed=self._volume_button.connect("value-changed", self._set_volume)
		self._repeat_changed=self._client.emitter.connect("repeat", self._repeat_refresh)
		self._random_changed=self._client.emitter.connect("random", self._random_refresh)
		self._single_changed=self._client.emitter.connect("single", self._single_refresh)
		self._consume_changed=self._client.emitter.connect("consume", self._consume_refresh)
		self._volume_changed=self._client.emitter.connect("volume_changed", self._volume_refresh)
		self._client.emitter.connect("disconnected", self._on_disconnected)
		self._client.emitter.connect("reconnected", self._on_reconnected)
		self._settings.connect("changed::icon-size", self._on_icon_size_changed)

		# packing
		ButtonBox=Gtk.ButtonBox()
		ButtonBox.set_property("layout-style", Gtk.ButtonBoxStyle.EXPAND)
		ButtonBox.pack_start(self._repeat_button, True, True, 0)
		ButtonBox.pack_start(self._random_button, True, True, 0)
		ButtonBox.pack_start(self._single_button, True, True, 0)
		ButtonBox.pack_start(self._consume_button, True, True, 0)
		self.pack_start(ButtonBox, True, True, 0)
		self.pack_start(self._volume_button, True, True, 0)

	def _set_option(self, widget, option):
		if widget.get_active():
			self._client.wrapped_call(option, "1")
		else:
			self._client.wrapped_call(option, "0")

	def _set_volume(self, widget, value):
		self._client.wrapped_call("setvol", str(int(value*100)))

	def _repeat_refresh(self, emitter, val):
		self._repeat_button.handler_block(self._repeat_button_toggled)
		self._repeat_button.set_active(val)
		self._repeat_button.handler_unblock(self._repeat_button_toggled)

	def _random_refresh(self, emitter, val):
		self._random_button.handler_block(self._random_button_toggled)
		self._random_button.set_active(val)
		self._random_button.handler_unblock(self._random_button_toggled)

	def _single_refresh(self, emitter, val):
		self._single_button.handler_block(self._single_button_toggled)
		self._single_button.set_active(val)
		self._single_button.handler_unblock(self._single_button_toggled)

	def _consume_refresh(self, emitter, val):
		self._consume_button.handler_block(self._consume_button_toggled)
		self._consume_button.set_active(val)
		self._consume_button.handler_unblock(self._consume_button_toggled)

	def _volume_refresh(self, emitter, volume):
		self._volume_button.handler_block(self._volume_button_changed)
		self._volume_button.set_value(volume/100)
		self._volume_button.handler_unblock(self._volume_button_changed)

	def _on_icon_size_changed(self, *args):
		pixel_size=self._settings.get_int("icon-size")
		for icon in self._icons.values():
			icon.set_pixel_size(pixel_size)
		self._volume_button.set_property("size", self._settings.get_gtk_icon_size("icon-size"))

	def _on_reconnected(self, *args):
		self.set_sensitive(True)

	def _on_disconnected(self, *args):
		self.set_sensitive(False)
		self._repeat_refresh(None, False)
		self._random_refresh(None, False)
		self._single_refresh(None, False)
		self._consume_refresh(None, False)
		self._volume_refresh(None, 0)

#################
# other dialogs #
#################

class ServerStats(Gtk.Dialog):
	def __init__(self, parent, client, settings):
		use_csd=settings.get_boolean("use-csd")
		if use_csd:
			Gtk.Dialog.__init__(self, title=_("Stats"), transient_for=parent, use_header_bar=True)
			# css
			style_context=self.get_style_context()
			provider=Gtk.CssProvider()
			css=b"""* {-GtkDialog-content-area-border: 0px;}"""
			provider.load_from_data(css)
			style_context.add_provider(provider, 800)
		else:
			Gtk.Dialog.__init__(self, title=_("Stats"), transient_for=parent)
			self.add_button(Gtk.STOCK_OK, Gtk.ResponseType.OK)
		self.set_resizable(False)

		# Store
		# (tag, value)
		store=Gtk.ListStore(str, str)

		# TreeView
		treeview=Gtk.TreeView(model=store)
		treeview.set_can_focus(False)
		treeview.set_search_column(-1)
		treeview.set_headers_visible(False)

		# selection
		sel=treeview.get_selection()
		sel.set_mode(Gtk.SelectionMode.NONE)

		# Column
		renderer_text=Gtk.CellRendererText()
		renderer_text_ralign=Gtk.CellRendererText(xalign=1.0)

		column_tag=Gtk.TreeViewColumn("", renderer_text_ralign, text=0)
		treeview.append_column(column_tag)

		column_value=Gtk.TreeViewColumn("", renderer_text, text=1)
		treeview.append_column(column_value)

		store.append(["protocol:", str(client.mpd_version)])

		stats=client.wrapped_call("stats")
		for key in stats:
			print_key=key+":"
			if key == "uptime" or key == "playtime" or key == "db_playtime":
				store.append([print_key, str(datetime.timedelta(seconds=int(stats[key])))])
			elif key == "db_update":
				store.append([print_key, str(datetime.datetime.fromtimestamp(int(stats[key])))])
			else:
				store.append([print_key, stats[key]])
		frame=Gtk.Frame()
		frame.add(treeview)
		self.vbox.pack_start(frame, True, True, 0)
		self.vbox.set_spacing(6)
		self.show_all()
		self.run()

class AboutDialog(Gtk.AboutDialog):
	def __init__(self, window):
		Gtk.AboutDialog.__init__(self, transient_for=window, modal=True)
		self.set_program_name(NAME)
		self.set_version(VERSION)
		self.set_comments(_("A small MPD client written in python"))
		self.set_authors(["Martin Wagner"])
		self.set_website("https://github.com/SoongNoonien/mpdevil")
		self.set_copyright("\xa9 2020 Martin Wagner")
		self.set_logo_icon_name(PACKAGE)

###############
# main window #
###############

class ProfileSelect(Gtk.ComboBoxText):
	def __init__(self, client, settings):
		Gtk.ComboBoxText.__init__(self)

		# adding vars
		self._client=client
		self._settings=settings

		# connect
		self._changed=self.connect("changed", self._on_changed)
		self._settings.connect("changed::profiles", self._refresh)
		self._settings.connect("changed::hosts", self._refresh)
		self._settings.connect("changed::ports", self._refresh)
		self._settings.connect("changed::passwords", self._refresh)
		self._settings.connect("changed::paths", self._refresh)

		self._refresh()

	def _refresh(self, *args):
		self.handler_block(self._changed)
		self.remove_all()
		for profile in self._settings.get_value("profiles"):
			self.append_text(profile)
		self.set_active(self._settings.get_int("active-profile"))
		self.handler_unblock(self._changed)

	def _on_changed(self, *args):
		active=self.get_active()
		self._settings.set_int("active-profile", active)

class MainWindow(Gtk.ApplicationWindow):
	def __init__(self, app, client, settings):
		Gtk.ApplicationWindow.__init__(self, title=("mpdevil"), application=app)
		Notify.init("mpdevil")
		self.set_icon_name("mpdevil")
		self.set_default_size(settings.get_int("width"), settings.get_int("height"))

		# adding vars
		self._client=client
		self._settings=settings
		self._use_csd=self._settings.get_boolean("use-csd")
		if self._use_csd:
			self._icon_size=0
		else:
			self._icon_size=self._settings.get_int("icon-size")

		# MPRIS
		DBusGMainLoop(set_as_default=True)
		self._dbus_service=MPRISInterface(self, self._client, self._settings)

		# actions
		save_action=Gio.SimpleAction.new("save", None)
		save_action.connect("activate", self._on_save)
		self.add_action(save_action)

		settings_action=Gio.SimpleAction.new("settings", None)
		settings_action.connect("activate", self._on_settings)
		self.add_action(settings_action)

		stats_action=Gio.SimpleAction.new("stats", None)
		stats_action.connect("activate", self._on_stats)
		self.add_action(stats_action)

		self._update_action=Gio.SimpleAction.new("update", None)
		self._update_action.connect("activate", self._on_update)
		self.add_action(self._update_action)

		self._help_action=Gio.SimpleAction.new("help", None)
		self._help_action.connect("activate", self._on_help)
		self.add_action(self._help_action)

		# widgets
		self._icons={}
		icons_data=["open-menu-symbolic"]
		for data in icons_data:
			self._icons[data]=PixelSizedIcon(data, self._icon_size)

		self._browser=Browser(self._client, self._settings, self)
		self._cover_playlist_window=CoverPlaylistWindow(self._client, self._settings, self)
		self._profile_select=ProfileSelect(self._client, self._settings)
		self._profile_select.set_tooltip_text(_("Select profile"))
		self._playback_control=PlaybackControl(self._client, self._settings)
		self._seek_bar=SeekBar(self._client)
		playback_options=PlaybackOptions(self._client, self._settings)

		# menu
		subsection=Gio.Menu()
		subsection.append(_("Settings"), "win.settings")
		subsection.append(_("Help"), "win.help")
		subsection.append(_("About"), "app.about")
		subsection.append(_("Quit"), "app.quit")

		menu=Gio.Menu()
		menu.append(_("Save window layout"), "win.save")
		menu.append(_("Update database"), "win.update")
		menu.append(_("Server stats"), "win.stats")
		menu.append_section(None, subsection)

		menu_button=Gtk.MenuButton.new()
		menu_popover=Gtk.Popover.new_from_model(menu_button, menu)
		menu_button.set_popover(menu_popover)
		menu_button.set_tooltip_text(_("Menu"))
		menu_button.set_image(image=self._icons["open-menu-symbolic"])

		# action bar
		action_bar=Gtk.ActionBar()
		action_bar.pack_start(self._playback_control)
		action_bar.pack_start(self._seek_bar)
		action_bar.pack_start(playback_options)

		# connect
		self._settings.connect("changed::profiles", self._on_settings_changed)
		self._settings.connect("changed::playlist-right", self._on_playlist_pos_settings_changed)
		if not self._use_csd:
			self._settings.connect("changed::icon-size", self._on_icon_size_changed)
		self._client.emitter.connect("current_song_changed", self._on_song_changed)
		self._client.emitter.connect("disconnected", self._on_disconnected)
		self._client.emitter.connect("reconnected", self._on_reconnected)
		# unmap space
		binding_set=Gtk.binding_set_find('GtkTreeView')
		Gtk.binding_entry_remove(binding_set, 32, Gdk.ModifierType.MOD2_MASK)
		# map space play/pause
		self.connect("key-press-event", self._on_key_press_event)

		# packing
		self._paned2=Gtk.Paned()
		self._paned2.set_position(self._settings.get_int("paned2"))
		self._on_playlist_pos_settings_changed()  # set orientation
		self._paned2.pack1(self._browser, True, False)
		self._paned2.pack2(self._cover_playlist_window, False, False)
		vbox=Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
		vbox.pack_start(self._paned2, True, True, 0)
		vbox.pack_start(action_bar, False, False, 0)

		if self._use_csd:
			self._header_bar=Gtk.HeaderBar()
			self._header_bar.set_show_close_button(True)
			self._header_bar.set_title("mpdevil")
			self.set_titlebar(self._header_bar)
			self._header_bar.pack_start(self._browser.back_to_album_button)
			self._header_bar.pack_start(self._browser.genre_select)
			self._header_bar.pack_end(menu_button)
			self._header_bar.pack_end(self._profile_select)
			self._header_bar.pack_end(self._browser.search_button)
		else:
			action_bar.pack_start(Gtk.Separator.new(orientation=Gtk.Orientation.VERTICAL))
			action_bar.pack_start(self._profile_select)
			action_bar.pack_start(menu_button)

		self.add(vbox)

		self.show_all()
		if self._settings.get_boolean("maximize"):
			self.maximize()
		self._on_settings_changed()  # hide profiles button
		self._client.start()  # connect client

	def _on_song_changed(self, *args):
		song=self._client.wrapped_call("currentsong")
		if song == {}:
			if self._use_csd:
				self._header_bar.set_title("mpdevil")
				self._header_bar.set_subtitle("")
			else:
				self.set_title("mpdevil")
		else:
			song=ClientHelper.extend_song_for_display(ClientHelper.song_to_str_dict(song))
			if song["date"] == "":
				date=""
			else:
				date=" ("+song["date"]+")"
			if self._use_csd:
				self._header_bar.set_title(song["title"]+" - "+song["artist"])
				self._header_bar.set_subtitle(song["album"]+date)
			else:
				self.set_title(song["title"]+" - "+song["artist"]+" - "+song["album"]+date)
			if self._settings.get_boolean("send-notify"):
				if not self.is_active() and self._client.wrapped_call("status")["state"] == "play":
					notify=Notify.Notification.new(song["title"], song["artist"]+"\n"+song["album"]+date)
					pixbuf=Cover(self._settings, song).get_pixbuf(400)
					notify.set_image_from_pixbuf(pixbuf)
					notify.show()

	def _on_reconnected(self, *args):
		self._dbus_service.acquire_name()
		self._playback_control.set_sensitive(True)

	def _on_disconnected(self, *args):
		self._dbus_service.release_name()
		if self._use_csd:
			self._header_bar.set_title("mpdevil")
			self._header_bar.set_subtitle("(not connected)")
		else:
			self.set_title("mpdevil (not connected)")
		self.songid_playing=None
		self._playback_control.set_sensitive(False)

	def _on_key_press_event(self, widget, event):
		ctrl = (event.state & Gdk.ModifierType.CONTROL_MASK)
		if ctrl:
			if event.keyval == 108:  # ctrl + l
				self._cover_playlist_window.show_lyrics()
		else:
			if event.keyval == 32:  # space
				if not self._browser.search_started():
					self._playback_control.play_button.grab_focus()
			elif event.keyval == 269025044:  # AudioPlay
				self._playback_control.play_button.grab_focus()
				self._playback_control.play_button.emit("clicked")
			elif event.keyval == 269025047:  # AudioNext
				self._playback_control.next_button.grab_focus()
				self._playback_control.next_button.emit("clicked")
			elif event.keyval == 43 or event.keyval == 65451:  # +
				if not self._browser.search_started():
					self._playback_control.next_button.grab_focus()
					self._playback_control.next_button.emit("clicked")
			elif event.keyval == 269025046:  # AudioPrev
				self._playback_control.prev_button.grab_focus()
				self._playback_control.prev_button.emit("clicked")
			elif event.keyval == 45 or event.keyval == 65453:  # -
				if not self._browser.search_started():
					self._playback_control.prev_button.grab_focus()
					self._playback_control.prev_button.emit("clicked")
			elif event.keyval == 65307:  # esc
				self._browser.back_to_album()
			elif event.keyval == 65450:  # *
				if not self._browser.search_started():
					self._seek_bar.scale.grab_focus()
					self._seek_bar.seek_forward()
			elif event.keyval == 65455:  # /
				if not self._browser.search_started():
					self._seek_bar.scale.grab_focus()
					self._seek_bar.seek_backward()
			elif event.keyval == 65474:  # F5
				self._update_action.emit("activate", None)
			elif event.keyval == 65470:  # F1
				self._help_action.emit("activate", None)

	def _on_save(self, action, param):
		size=self.get_size()
		self._settings.set_int("width", size[0])
		self._settings.set_int("height", size[1])
		self._settings.set_boolean("maximize", self.is_maximized())
		self._browser.save_settings()
		self._cover_playlist_window.save_settings()
		self._settings.set_int("paned2", self._paned2.get_position())

	def _on_settings(self, action, param):
		settings=SettingsDialog(self, self._settings)
		settings.run()
		settings.destroy()

	def _on_stats(self, action, param):
		if self._client.connected():
			stats=ServerStats(self, self._client, self._settings)
			stats.destroy()

	def _on_update(self, action, param):
		if self._client.connected():
			self._client.wrapped_call("update")

	def _on_help(self, action, param):
		Gtk.show_uri_on_window(self, "https://github.com/SoongNoonien/mpdevil/wiki/Usage", Gdk.CURRENT_TIME)

	def _on_settings_changed(self, *args):
		if len(self._settings.get_value("profiles")) > 1:
			self._profile_select.set_property("visible", True)
		else:
			self._profile_select.set_property("visible", False)

	def _on_playlist_pos_settings_changed(self, *args):
		if self._settings.get_boolean("playlist-right"):
			self._cover_playlist_window.set_orientation(Gtk.Orientation.VERTICAL)
			self._paned2.set_orientation(Gtk.Orientation.HORIZONTAL)
		else:
			self._cover_playlist_window.set_orientation(Gtk.Orientation.HORIZONTAL)
			self._paned2.set_orientation(Gtk.Orientation.VERTICAL)

	def _on_icon_size_changed(self, *args):
		pixel_size=self._settings.get_int("icon-size")
		for icon in self._icons.values():
			icon.set_pixel_size(pixel_size)

###################
# Gtk application #
###################

class mpdevil(Gtk.Application):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, application_id="org.mpdevil", flags=Gio.ApplicationFlags.FLAGS_NONE, **kwargs)
		self._settings=Settings()
		self._client=Client(self._settings)
		self._window=None

	def do_activate(self):
		if not self._window:  # allow just one instance
			self._window=MainWindow(self, self._client, self._settings)
			self._window.connect("delete-event", self._on_delete_event)
		self._window.present()

	def do_startup(self):
		Gtk.Application.do_startup(self)

		action=Gio.SimpleAction.new("about", None)
		action.connect("activate", self._on_about)
		self.add_action(action)

		action=Gio.SimpleAction.new("quit", None)
		action.connect("activate", self._on_quit)
		self.add_action(action)

	def _on_delete_event(self, *args):
		if self._settings.get_boolean("stop-on-quit") and self._client.connected():
			self._client.wrapped_call("stop")
		self.quit()

	def _on_about(self, action, param):
		dialog=AboutDialog(self._window)
		dialog.run()
		dialog.destroy()

	def _on_quit(self, action, param):
		if self._settings.get_boolean("stop-on-quit") and self._client.connected():
			self._client.wrapped_call("stop")
		self.quit()

if __name__ == '__main__':
	app=mpdevil()
	app.run(sys.argv)

