#!/usr/bin/env python3

"""
Sequencer GUI for UVa ground station.

Copyright 2019 by Michael R. McPherson, Charlottesville, VA
mailto:mcpherson@acm.org
http://www.kq9p.us

This program is free software; you can redistribute it and/or modify it under
the terms of the GNU Lesser General Public License as published by the Free
Software Foundation; either version 2 of the License, or (at your option) any
later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE.  See the GNU Lesser General Public License for more
details.

You should have received a copy of the GNU General Public License along with
this program. If not, see <http://www.gnu.org/licenses/>.
"""

__author__ = 'Michael R. McPherson <mcpherson@acm.org>'

import os
import configparser
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from gi.repository import GObject
import time
import logging
from ground.packet_functions import SequencerDevice


"""
GUI Handlers
"""

class Handler:
    logger = None
    sequencer = None

    def on_destroy(self, *args):
        self.sequencer.shutdown()
        Gtk.main_quit()

    def on_switch_pa(self, button, state):
        if state:
            self.sequencer.rf_amp_tx()
        else:
            self.sequencer.rf_amp_rx()

    def on_switch_uhf_lna(self, button, state):
        if state:
            self.sequencer.uhf_preamp_off()
        else:
            self.sequencer.uhf_preamp_on()

    def on_radiobutton1(self, button):
        if button.get_active():
            self.sequencer.coaxialSwitchSet(1)

    def on_radiobutton2(self, button):
        if button.get_active():
            self.sequencer.coaxialSwitchSet(2)

    def on_radiobutton3(self, button):
        if button.get_active():
            self.sequencer.coaxialSwitchSet(3)

"""
Main
"""

def main():

    script_folder_name = os.path.dirname(os.path.realpath(__file__))
    ground_ini = script_folder_name + '/' + 'ground.ini'
    sequencer_gui_glade = script_folder_name + '/' + 'sequencer_gui.glade'
    config = configparser.ConfigParser()
    config.read([ground_ini])
    program_name = 'Sequencer'
    program_version = config['ground']['program_version']
    sequencer_relay_delay = float(config['ground']['sequencer_relay_delay'])

    SequencerDevice.relayDelay = sequencer_relay_delay
    sequencer = SequencerDevice()
    Handler.sequencer = sequencer

    builder = Gtk.Builder()
    builder.add_from_file(sequencer_gui_glade)
    builder.connect_signals(Handler())
    appwindow = builder.get_object("applicationwindow1")
    switch_pa = builder.get_object('switch_pa')
    switch_pa.set_active(False)
    sequencer.rf_amp_rx()
    switch_uhf_lna = builder.get_object('switch_uhf_lna')
    switch_uhf_lna.set_active(False)
    sequencer.uhf_preamp_on()
    radiobutton1 = builder.get_object('radiobutton1')
    radiobutton1.set_active(True)
    sequencer.coaxialSwitchSet(1)
    appwindow_title = ' '.join([program_name, program_version])
    appwindow.set_title(appwindow_title)
    appwindow.show_all()

    Gtk.main()


if __name__ == "__main__":
    # execute only if run as a script
    main()
