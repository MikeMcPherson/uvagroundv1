#!/usr/bin/env python3

"""
Simple ground station for the UVa Libertas spacecraft.

Copyright 2018 by Michael R. McPherson, Charlottesville, VA
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
import subprocess
import configparser
import logging
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from gi.repository import GObject
import array
import time
import serial
import json
import threading
import pprint
import socket
import multiprocessing as mp
from queue import Empty
import hexdump
import random
from nltk import word_tokenize
from ground.constant import COMMAND_CODES, COMMAND_NAMES, health_payload_fields, science_payload_fields
from ground.packet_functions import SppPacket, RadioDevice, GsCipher, SequencerDevice, kiss_wrap, kiss_unwrap
from ground.packet_functions import receive_packet, make_ack, make_nak
from ground.packet_functions import to_bigendian, from_bigendian, to_fake_float, from_fake_float
from ground.packet_functions import init_ax25_header, init_ax25_badpacket, sn_increment, sn_decrement
from ground.packet_functions import ax25_callsign, to_int16, to_int32


"""
GUI Handlers
"""

class Handler:
    filechooserwindow = None
    filedialog1_save = False
    filechooser2window = None
    filedialog2_save = False
    label11 = None
    radio = None
    sequencer = None
    display_spp = True
    display_ax25 = True

    def on_destroy(self, *args):
        do_save = True
        do_destroy(do_save)

    def on_quit_nosave(self, *args):
        do_save = False
        do_destroy(do_save)

    def on_command(self, button):
        button_label = button.get_label().replace('...', '')
        process_command(button_label)

    def on_show_spp(self, button):
        if button.get_active():
            Handler.display_spp = True
        else:
            Handler.display_spp = False

    def on_show_ax25(self, button):
        if button.get_active():
            Handler.display_ax25 = True
        else:
            Handler.display_ax25 = False

    def on_rf_amp(self, button, state):
        SequencerDevice.rf_amp_enabled = state
        if state:
            self.sequencer.txamp_enable()
        else:
            self.sequencer.txamp_disable()

    def on_uhf_preamp(self, button, state):
        SequencerDevice.uhf_preamp_enabled = state
        if state:
            self.sequencer.uhf_preamp_on()
        else:
            self.sequencer.uhf_preamp_off()

    def on_dialog1_cancel(self, button):
        dialog1_cancel()

    def on_dialog1_transmit(self, button):
        dialog1_transmit()

    def on_save(self, button):
        save_file()

    def on_save_as(self, button):
        save_file_as()

    def on_filechooserdialog1_cancel(self, button):
        self.filechooserwindow.hide()
        Handler.filedialog1_save = False

    def on_filechooserdialog1_save(self, button):
        self.filechooserwindow.hide()
        Handler.filedialog1_save = True

    def on_load(self, button):
        load_file()

    def on_run(self, button):
        pass

    def on_pause(self, button):
        pass

    def on_stop(self, button):
        pass

    def on_clear(self, button):
        script_clear()

    def on_filechooserdialog2_cancel(self, button):
        self.filechooser2window.hide()
        Handler.filedialog2_save = False

    def on_filechooserdialog2_open(self, button):
        self.filechooser2window.hide()
        Handler.filedialog2_save = True

    def validate_entry_uint16(self, entry):
        try:
            i = int(entry.get_text(), 0)
            self.label11.set_text('')
        except ValueError:
            self.label11.set_text('Field must be numeric.')


def dialog1_run(title, labels, defaults, tooltips):
    global argwindow
    global entry_objs
    global label_objs
    argwindow.set_title(title)
    for i in range(9):
        label_objs[i].set_label(labels[i])
        entry_objs[i].set_text(defaults[i])
        label_objs[i].set_tooltip_text(tooltips[i])
        entry_objs[i].set_tooltip_text(tooltips[i])
        if labels[i] == 'N/A':
            label_objs[i].set_visible(False)
            entry_objs[i].set_visible(False)
        else:
            label_objs[i].set_visible(True)
            entry_objs[i].set_visible(True)
    argwindow.run()
    return [int(entry_objs[0].get_text(), 0), int(entry_objs[1].get_text(), 0),
            int(entry_objs[2].get_text(), 0), int(entry_objs[3].get_text(), 0),
            int(entry_objs[4].get_text(), 0), int(entry_objs[5].get_text(), 0),
            int(entry_objs[6].get_text(), 0), int(entry_objs[7].get_text(), 0),
            int(entry_objs[8].get_text(), 0)]

def dialog1_transmit():
    global argwindow
    global dialog1_xmit
    argwindow.hide()
    dialog1_xmit = True


def dialog1_cancel():
    global argwindow
    global dialog1_xmit
    argwindow.hide()
    dialog1_xmit = False


"""
Ground Commands
"""


def process_command(button_label):
    global ground_sequence_number
    global dialog1_xmit
    global tc_packets_waiting_for_ack
    global downlink_payloads_pending
    global health_payloads_per_packet
    global science_payloads_per_packet
    global dump_mode

    do_transmit_packet = False
    do_sn_increment = False
    expect_ack = False
    tc_packet = SppPacket('TC', dynamic=True)

    if button_label == 'CEASE_XMIT':
        tc_data = array.array('B', [0x7F])
        tc_packet.set_spp_data(tc_data)
        tc_packet.set_sequence_number(ground_sequence_number)
        do_transmit_packet = True
        do_sn_increment = True
        expect_ack = True

    elif button_label == 'NOOP':
        tc_data = array.array('B', [0x09])
        tc_packet.set_spp_data(tc_data)
        tc_packet.set_sequence_number(ground_sequence_number)
        do_transmit_packet = True
        do_sn_increment = True
        expect_ack = True

    elif button_label == 'RESET':
        title = '"RESET" Arguments'
        labels = ['Reset mask', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A']
        defaults = ['0x0000', '0x0000', '0x0000', '0x0000', '0x0000', '0x0000', '0x0000', '0x0000', '0x0000']
        tooltips = ['(16-bit) Bitmask indicating which spacecraft reset operations are to be performed.',
                    'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A']
        args = dialog1_run(title, labels, defaults, tooltips)
        if dialog1_xmit:
            do_transmit_packet = True
            do_sn_increment = True
            expect_ack = True
            tc_data = array.array('B', [0x04])
            tc_data.extend(to_bigendian(args[0], 2))
            tc_packet.set_spp_data(tc_data)
            tc_packet.set_sequence_number(ground_sequence_number)

    elif button_label == 'XMIT_COUNT':
        tc_data = array.array('B', [0x01])
        tc_packet.set_spp_data(tc_data)
        tc_packet.set_sequence_number(ground_sequence_number)
        do_transmit_packet = True
        do_sn_increment = True
        expect_ack = True

    elif button_label == 'XMIT_HEALTH':
        # title = '"XMIT_HEALTH" Arguments'
        # labels = ['# Packets', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A']
        # defaults = ['1', '0x00', '0x00', '0x00', '0x00', '0x00', '0x00', '0x00', '0x00']
        # tooltips = [
        #     '(8-bit) Number of Health Packets to be downlinked.  0xFF means DUMP all outstanding payloads.',
        #     'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A']
        # args = dialog1_run(title, labels, defaults, tooltips)
        # if dialog1_xmit:
        #     do_transmit_packet = True
        #     do_sn_increment = True
        #     if args[0] == 0xFF:
        #         expect_ack = False
        #         downlink_payloads_pending = 0xFF
        #         dump_mode = True
        #     else:
        #         expect_ack = True
        #         downlink_payloads_pending = args[0] * health_payloads_per_packet
        #         dump_mode = False
        #     tc_data = array.array('B', [0x02])
        #     tc_data.append(args[0])
        #     tc_packet.set_spp_data(tc_data)
        #     tc_packet.set_sequence_number(ground_sequence_number)
        #
        # For Libertas, Health payloads always 1
        args = [1]
        do_transmit_packet = True
        do_sn_increment = True
        expect_ack = True
        downlink_payloads_pending = args[0] * health_payloads_per_packet
        dump_mode = False
        tc_data = array.array('B', [0x02])
        tc_data.append(args[0])
        tc_packet.set_spp_data(tc_data)
        tc_packet.set_sequence_number(ground_sequence_number)

    elif button_label == 'XMIT_SCIENCE':
        title = '"XMIT_SCIENCE" Arguments'
        labels = ['# Packets', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A']
        defaults = ['10', '0x00', '0x00', '0x00', '0x00', '0x00', '0x00', '0x00', '0x00']
        tooltips = [
            '(8-bit) Number of Science Packets to be downlinked.  0xFF means DUMP all outstanding payloads.',
            'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A']
        args = dialog1_run(title, labels, defaults, tooltips)
        if dialog1_xmit:
            do_transmit_packet = True
            do_sn_increment = True
            if args[0] == 0xFF:
                expect_ack = False
                downlink_payloads_pending = 0xFF
                dump_mode = True
            else:
                expect_ack = True
                downlink_payloads_pending = args[0] * science_payloads_per_packet
                dump_mode = False
            tc_data = array.array('B', [0x03])
            tc_data.append(args[0])
            tc_packet.set_spp_data(tc_data)
            tc_packet.set_sequence_number(ground_sequence_number)

    elif button_label == 'READ_MEM':
        title = '"READ_MEM" Arguments'
        labels = ['Start address', 'End address', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A']
        defaults = ['0x00F0', '0x00F3', '0x0000', '0x0000', '0x0000', '0x0000', '0x0000', '0x0000', '0x0000']
        tooltips = ['(16-bit) Start of memory address range to downlink.',
                    '(16-bit) End of memory address range to downlink.',
                    'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A']
        args = dialog1_run(title, labels, defaults, tooltips)
        if dialog1_xmit:
            do_transmit_packet = True
            do_sn_increment = True
            expect_ack = True
            tc_data = array.array('B', [0x08])
            tc_data.extend(to_bigendian(args[0], 2))
            tc_data.extend(to_bigendian(args[1], 2))
            tc_packet.set_spp_data(tc_data)
            tc_packet.set_sequence_number(ground_sequence_number)

    elif button_label == 'WRITE_MEM':
        title = '"WRITE_MEM" Arguments'
        labels = ['Start address', 'End address',
                  'Contents 0', 'Contents 1', 'Contents 2', 'Contents 3', 'N/A', 'N/A', 'N/A']
        defaults = ['0x00F0', '0x00F3', '0x0000', '0x0000', '0x0000', '0x0000', '0x0000', '0x0000', '0x0000']
        tooltips = ['(16-bit) Start of memory address range to uplink.',
                    '(16-bit) End of memory address range to uplink.  (Limited to four memory locations for testing.)',
                    '(16-bit) Memory contents', '(16-bit) Memory contents',
                    '(16-bit) Memory contents', '(16-bit) Memory contents', 'N/A', 'N/A', 'N/A']
        args = dialog1_run(title, labels, defaults, tooltips)
        if dialog1_xmit:
            do_transmit_packet = True
            do_sn_increment = True
            expect_ack = True
            tc_data = array.array('B', [0x07])
            for a in args:
                tc_data.extend(to_bigendian(a, 2))
            tc_packet.set_spp_data(tc_data)
            tc_packet.set_sequence_number(ground_sequence_number)

    elif button_label == 'SET_COMMS':
        title = '"SET_COMMS" Arguments'
        labels = ['TM Window', 'XMIT Max Retries', 'ACK Timeout', 'Sequence Window', 'Spacecraft SN',
                  'Ground SN', 'Turnaround', 'Transmit Power', 'N/A']
        defaults = ['1', '4', '5', '2', '0', '0', '1000', '125', '0x0000']
        tooltips = ['(8-bit) Number of Health or Science packets the spacecraft will transmit ' +
                    'before waiting for an ACK.  Default: 1. Maximum: 20',
                    '(8-bit) Number of unacknowledged transmit windows before the spacecraft ' +
                    'ceases transmission.  Default: 4.',
                    '(8-bit) Number of seconds the spacecraft waits for an ACK or NAK ' +
                    'before retransmitting the last window.  Default: 5 seconds.',
                    '(8-bit) Maximum allowable difference between the expected and received ' +
                    'Sequence Number.  Default: 2.',
                    '(16-bit) Next packet from the spacecraft will have this sequence number',
                    '(16-bit) Next packet from the ground station will have this sequence number',
                    '(16-bit) Minimum delay between transmit and receive packets.',
                    '(8-bit) Spacecraft transmit power, Default: 125 (produces approx. 1W)', 'N/A']
        args = dialog1_run(title, labels, defaults, tooltips)
        if dialog1_xmit:
            do_transmit_packet = True
            do_sn_increment = True
            expect_ack = True
            tc_data = array.array('B', [0x0B])
            tm_packet_window = max(1, min(args[0], 20))
            tc_data.append(tm_packet_window)
            SppPacket.tm_packet_window = tm_packet_window
            for a in args[1:4]:
                tc_data.append(a & 0x00FF)
            tc_data.extend(to_bigendian(args[4], 2))
            tc_data.extend(to_bigendian(args[5], 2))
            tc_data.extend(to_bigendian(args[6], 2))
            tc_data.append(args[7])
            tc_packet.set_spp_data(tc_data)
            tc_packet.set_sequence_number(ground_sequence_number)

    elif button_label == 'GET_COMMS':
        tc_data = array.array('B', [0x0C])
        tc_packet.set_spp_data(tc_data)
        tc_packet.set_sequence_number(ground_sequence_number)
        do_transmit_packet = True
        do_sn_increment = True
        expect_ack = True

    elif button_label == 'SET_MODE':
        title = '"SET_MODE" Arguments'
        labels = ['Mode', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A']
        defaults = ['2', '0x00', '0x00', '0x00', '0x00', '0x00', '0x00', '0x00', '0x00']
        tooltips = ['(8-bit) DATA_COLLECTION=2, LOW_POWER=3',
                    'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A']
        args = dialog1_run(title, labels, defaults, tooltips)
        if dialog1_xmit:
            do_transmit_packet = True
            do_sn_increment = True
            expect_ack = True
            tc_data = array.array('B', [0x0A])
            tc_data.append(args[0] & 0x00FF)
            tc_packet.set_spp_data(tc_data)
            tc_packet.set_sequence_number(ground_sequence_number)

    elif button_label == 'MAC_TEST':
        tc_data = array.array('B', [0x0E])
        tc_packet.set_spp_data(tc_data)
        tc_packet.set_sequence_number(ground_sequence_number)
        do_transmit_packet = True
        do_sn_increment = True
        expect_ack = True

    elif button_label == 'PING_RETURN':
        tc_packet = SppPacket('OA', dynamic=True)
        tc_packet.set_oa_command(0x31)
        do_transmit_packet = True
        do_sn_increment = False
        expect_ack = False

    elif button_label == 'RADIO_RESET':
        tc_packet = SppPacket('OA', dynamic=True)
        tc_packet.set_oa_command(0x33)
        do_transmit_packet = True
        do_sn_increment = False
        expect_ack = False

    elif button_label == 'PIN_TOGGLE':
        tc_packet = SppPacket('OA', dynamic=True)
        tc_packet.set_oa_command(0x34)
        do_transmit_packet = True
        do_sn_increment = False
        expect_ack = False

    else:
        print('Whoops, unrecognized button label:', button_label)
        do_transmit_packet = False
        do_sn_increment = False
        expect_ack = False

    if do_transmit_packet:
        tc_packet.transmit()
    if do_sn_increment:
        ground_sequence_number = sn_increment(ground_sequence_number)
    if expect_ack:
        tc_packets_waiting_for_ack.append(tc_packet)


"""
Process received packets
"""

def process_received():
    global expected_spacecraft_sequence_number
    global ground_sequence_number
    global tc_packets_waiting_for_ack
    global q_receive_packet
    global q_display_packet
    global health_payloads_available
    global science_payloads_available
    global downlink_payloads_pending
    global transmit_timeout_count
    global ack_timeout
    global max_retries
    global sequence_number_window
    global tm_packets_to_ack
    global tm_packets_to_nak
    global health_payloads_per_packet
    global science_payloads_per_packet
    global my_packet_type
    global dump_mode
    global ax25_badpacket

    tm_packets_to_ack = []
    tm_packets_to_nak = []
    retry_count = -1
    while True:
        try:
            ax25_packet = q_receive_packet.get(True, ack_timeout)
        except Empty:
            ax25_packet = array.array('B', ax25_badpacket)
        if ax25_packet is None:
            print('Socket closed')
            exit(1)

        do_transmit_packet = False
        downlink_complete = False
        if len(ax25_packet) < 48:
            padding = 48 - len(ax25_packet)
            ax25_packet.extend([0x00] * padding)
        tm_packet = SppPacket('TM', dynamic=False)
        tm_packet.parse_ax25(ax25_packet)
        if tm_packet.command != 0xFF:
            q_display_packet.put(ax25_packet)
        if (tm_packet.validation_mask != 0) and (tm_packet.command != 0xFF):
            if retry_count < 0:
                retry_count = max_retries + 1
            tm_packet.set_sequence_number(expected_spacecraft_sequence_number)
            expected_spacecraft_sequence_number = sn_increment(expected_spacecraft_sequence_number)
            if not dump_mode:
                tm_packets_to_nak.append(tm_packet)
        else:
            command = tm_packet.command
            if command == 0xFF:
                do_transmit_packet = False
            elif command == COMMAND_CODES['ACK']:
                tc_packets_waiting_for_ack = []
                expected_spacecraft_sequence_number = sn_increment(tm_packet.sequence_number)
                do_transmit_packet = False
                downlink_complete = True
            elif command == COMMAND_CODES['NAK']:
                for p in tc_packets_waiting_for_ack:
                    p.simulated_error = False
                    p.transmit()
                do_transmit_packet = False
                downlink_complete = True
            elif command == COMMAND_CODES['XMIT_COUNT']:
                tc_packets_waiting_for_ack = []
                expected_spacecraft_sequence_number = sn_increment(tm_packet.sequence_number)
                health_payloads_available = from_bigendian(tm_packet.spp_data[1:3], 2)
                science_payloads_available = from_bigendian(tm_packet.spp_data[3:5], 2)
                do_transmit_packet = True
                downlink_complete = True
                tm_packets_to_ack.append(tm_packet)
            elif command == COMMAND_CODES['XMIT_HEALTH']:
                tc_packets_waiting_for_ack = []
                expected_spacecraft_sequence_number = sn_increment(tm_packet.sequence_number)
                downlink_payloads_pending = downlink_payloads_pending - health_payloads_per_packet
                health_payloads_available = health_payloads_available - health_payloads_per_packet
                if downlink_payloads_pending <= 0:
                    downlink_payloads_pending = 0
                    downlink_complete = True
                do_transmit_packet = True
                if not dump_mode:
                    tm_packets_to_ack.append(tm_packet)
            elif command == COMMAND_CODES['XMIT_SCIENCE']:
                tc_packets_waiting_for_ack = []
                expected_spacecraft_sequence_number = sn_increment(tm_packet.sequence_number)
                downlink_payloads_pending = downlink_payloads_pending - science_payloads_per_packet
                science_payloads_available = science_payloads_available - science_payloads_per_packet
                if downlink_payloads_pending <= 0:
                    downlink_payloads_pending = 0
                    downlink_complete = True
                do_transmit_packet = True
                if not dump_mode:
                    tm_packets_to_ack.append(tm_packet)
            elif command == COMMAND_CODES['READ_MEM']:
                tc_packets_waiting_for_ack = []
                expected_spacecraft_sequence_number = sn_increment(tm_packet.sequence_number)
                do_transmit_packet = True
                downlink_complete = True
                tm_packets_to_ack.append(tm_packet)
            elif command == COMMAND_CODES['GET_COMMS']:
                tc_packets_waiting_for_ack = []
                expected_spacecraft_sequence_number = sn_increment(tm_packet.sequence_number)
                do_transmit_packet = True
                downlink_complete = True
                tm_packets_to_ack.append(tm_packet)
            elif command == COMMAND_CODES['MAC_TEST']:
                tc_packets_waiting_for_ack = []
                expected_spacecraft_sequence_number = sn_increment(tm_packet.sequence_number)
                do_transmit_packet = False
                downlink_complete = True
            else:
                pass

            if do_transmit_packet and (not dump_mode):
                if (((len(tm_packets_to_ack) + len(tm_packets_to_nak)) >= SppPacket.tm_packet_window) or
                        downlink_complete):
                    if len(tm_packets_to_nak) > 0:
                        retry_count = retry_count - 1
                        if retry_count == 0:
                            tc_packet = SppPacket('TC', dynamic=True)
                            tc_data = array.array('B', [0x7F])
                            tc_packet.set_spp_data(tc_data)
                            tc_packet.set_sequence_number(ground_sequence_number)
                            tc_packet.transmit()
                            ground_sequence_number = sn_increment(ground_sequence_number)
                            retry_count = -1
                            continue
                        tc_packet = make_nak('TC', tm_packets_to_nak)
                        tc_packet.set_sequence_number(ground_sequence_number)
                        tc_packet.transmit()
                        ground_sequence_number = sn_increment(ground_sequence_number)
                    else:
                        retry_count = -1
                        tc_packet = make_ack('TC', [])
                        tc_packet.set_sequence_number(ground_sequence_number)
                        tc_packet.transmit()
                        ground_sequence_number = sn_increment(ground_sequence_number)
                    tm_packets_to_ack = []
                    tm_packets_to_nak = []


"""
Helpers
"""

def do_destroy(do_save):
    global textview_buffer
    global p_receive_packet
    global gs_xcvr_uhd_pid
    global sequencer
    sequencer.shutdown()
    textview_buffer.insert(textview_buffer.get_end_iter(), "]\n}\n")
    p_receive_packet.terminate()
    if gs_xcvr_uhd_pid is not None:
        if gs_xcvr_uhd_pid.poll() is None:
            gs_xcvr_uhd_pid.kill()
    time_utc = time.gmtime()
    iq_file_string = time.strftime("/zfs0/iqfiles/%Y%m%dT%H%M%SZ.iq", time_utc)
    try:
        os.rename('/zfs0/iqfiles/pass_iq.tmp', iq_file_string)
    except:
        pass
    if do_save:
        save_file()
    Gtk.main_quit()


def save_file():
    global textview
    global buffer_saved
    global buffer_filename
    if first_packet is False:
        if buffer_saved:
            write_buffer(buffer_filename)
        else:
            save_file_as()


def save_file_as():
    global buffer_saved
    global buffer_filename
    time_utc = time.gmtime()
    time_string = time.strftime("ground%Y%m%dT%H%M%SZ.json", time_utc)
    Handler.filechooserwindow.set_current_name(time_string)
    Handler.filechooserwindow.run()
    if Handler.filedialog1_save:
        buffer_filename = Handler.filechooserwindow.get_filename()
        write_buffer(buffer_filename)
        buffer_saved = True
    else:
        buffer_saved = False


def write_buffer(buffer_filename):
    global textview
    fobj = open(buffer_filename, "w")
    textview_buffer = textview.get_buffer().get_text(textview.get_buffer().get_start_iter(),
                                                     textview.get_buffer().get_end_iter(), True)
    fobj.write(textview_buffer)
    fobj.close()


def hex_tabulate(buffer, values_per_row):
    buffer_len = len(buffer)
    buffer_string = ''
    for i in range(0, buffer_len, values_per_row):
        buffer_list = []
        for value in buffer[i:(i + values_per_row)]:
            buffer_list.append("\"0x{:02X}\"".format(value))
        buffer_string = buffer_string + '    ' + ", ".join(map(str, buffer_list))
        if (buffer_len - i) > values_per_row:
            buffer_string = buffer_string + ',\n'
        else:
            buffer_string = buffer_string + '\n'
    return(buffer_string)


"""
Scripting
"""

def load_file():
    global filechooser2window
    global textview2_buffer
    filechooser2window.run()
    if Handler.filedialog2_save:
        script_filename = filechooser2window.get_filename()
        fp = open(script_filename, 'r')
        lines = fp.readlines()
        fp.close()
        start_iter = textview2_buffer.get_start_iter()
        end_iter = textview2_buffer.get_end_iter()
        textview2_buffer.delete(start_iter, end_iter)
        commands = []
        for line in lines:
            command_tokens = word_tokenize(line)
            if len(command_tokens) > 0:
                if command_tokens[0] != '#':
                    command_line = (' ').join(command_tokens) + '\n'
                    start_iter = textview2_buffer.get_end_iter()
                    textview2_buffer.insert(start_iter, command_line, -1)
                    end_iter = textview2_buffer.get_end_iter()
                    commands.append([command_tokens, start_iter, end_iter])

        Handler.filedialog2_save = False


def script_clear():
    global textview2_buffer
    start_iter = textview2_buffer.get_start_iter()
    end_iter = textview2_buffer.get_end_iter()
    textview2_buffer.delete(start_iter, end_iter)


"""
Display packet in scrolling window
"""


def display_packet():
    global textview
    global textview_buffer
    global first_packet
    global q_display_packet
    global health_payload_length
    global science_payload_length
    global encrypt_uplink
    global gs_cipher
    global sc_ax25_callsign
    global gs_ax25_callsign

    values_per_row = 8

    if not q_display_packet.empty():
        tv_header = ('  "ground_utc":"<GROUND_UTC>",\n' +
                     '  "sender":"<SENDER>", ' +
                     '"packet_type":"<PACKET_TYPE>", ' +
                     '"command":"<COMMAND>",\n')

        tv_spp = ('  "gps_week":"<GPS_WEEK>", ' +
                  '"gps_time":"<GPS_TIME>", ' +
                  '"sequence_number":"<SEQUENCE_NUMBER>",\n' +
                  '  "packet_data_length":"<PACKET_DATA_LENGTH>",\n' +
                  '  "simulated_error":"<SIMULATED_ERROR>", ' +
                  '"security_trailer_valid":"<MAC_VALID>",\n')
        tv_spp_raw = ('  "<PACKET_TYPE>_data_length":"<SPP_DATA_LENGTH>",\n' +
                      '  "<PACKET_TYPE>_data":[\n<SPP_DATA>    ],\n' +
                      '  "security_trailer":[\n<MAC_DIGEST>    ],\n')

        tv_ax25 = ('  "ax25_destination":"<AX25_DESTINATION>", ' +
                   '"ax25_source":"<AX25_SOURCE>", ' +
                   '"ax25_packet_length":"<AX25_PACKET_LENGTH>",\n' +
                   '  "ax25_packet":[\n<AX25_PACKET>    ]\n')

        ax25_packet = q_display_packet.get()
        if first_packet:
            textview_buffer.insert(textview_buffer.get_end_iter(), "{\n\"packets\" : [\n")
            first_packet = False
        else:
            textview_buffer.insert(textview_buffer.get_end_iter(), ",\n")
        ground_utc = time.gmtime()
        ground_utc_string = time.strftime("%Y%m%dT%H%M%SZ", ground_utc)
        tv_header = tv_header.replace('<GROUND_UTC>', ground_utc_string)
        if len(ax25_packet) >= 33:
            if ax25_packet[16] == 0x18:
                dp_packet = SppPacket('TC', dynamic=False)
            elif ax25_packet[16] == 0x08:
                dp_packet = SppPacket('TM', dynamic=False)
            elif len(ax25_packet) == 33:
                dp_packet = SppPacket('OA', dynamic=False)
            else:
                dp_packet = SppPacket('UN', dynamic=False)
            dp_packet.parse_ax25(ax25_packet)
            textview_buffer.insert(textview_buffer.get_end_iter(), "{\n")

            if dp_packet.command in COMMAND_NAMES:
                cmd_name = COMMAND_NAMES[dp_packet.command]
            else:
                cmd_name = COMMAND_NAMES[0x00]
            if dp_packet.is_oa_packet:
                packet_type = 'OA'
                tv_header = tv_header.replace('<SENDER>', 'ground')
                tv_header = tv_header.replace('<PACKET_TYPE>', packet_type)
                if dp_packet.spp_packet[16] == 0x31:
                    tv_header = tv_header.replace('<COMMAND>', 'PING_RETURN_COMMAND')
                elif dp_packet.spp_packet[16] == 0x33:
                    tv_header = tv_header.replace('<COMMAND>', 'RADIO_RESET_COMMAND')
                elif dp_packet.spp_packet[16] == 0x34:
                    tv_header = tv_header.replace('<COMMAND>', 'PIN_TOGGLE_COMMAND')
                else:
                    tv_header = tv_header.replace('<COMMAND>', 'ILLEGAL OA COMMAND')
            elif dp_packet.packet_type == 0x08:
                packet_type = 'TM'
                tv_header = tv_header.replace('<SENDER>', 'spacecraft')
                tv_header = tv_header.replace('<PACKET_TYPE>', packet_type)
                tv_header = tv_header.replace('<COMMAND>', cmd_name)
                tv_spp = tv_spp.replace('<SENDER>', 'spacecraft')
                tv_spp_raw = tv_spp_raw.replace('<PACKET_TYPE>', packet_type)
            elif dp_packet.packet_type == 0x18:
                packet_type = 'TC'
                tv_header = tv_header.replace('<SENDER>', 'ground')
                tv_header = tv_header.replace('<PACKET_TYPE>', packet_type)
                tv_header = tv_header.replace('<COMMAND>', cmd_name)
                tv_spp = tv_spp.replace('<SENDER>', 'ground')
                tv_spp_raw = tv_spp_raw.replace('<PACKET_TYPE>', packet_type)
            else:
                packet_type = 'UNKNOWN'
                tv_header = tv_header.replace('<SENDER>', 'UNKNOWN')
                tv_header = tv_header.replace('<PACKET_TYPE>', packet_type)
                tv_header = tv_header.replace('<COMMAND>', 'UNKNOWN')

            textview_buffer.insert(textview_buffer.get_end_iter(), tv_header)

            if dp_packet.is_spp_packet:
                tv_spp = tv_spp.replace('<GPS_WEEK>', "{:d}".format(dp_packet.gps_week))
                tv_spp = tv_spp.replace('<GPS_TIME>', "{:14.7f}".format(dp_packet.gps_sow))
                tv_spp = tv_spp.replace('<SEQUENCE_NUMBER>', "{:05d}".format(dp_packet.sequence_number))
                # tv_spp = tv_spp.replace('<COMMAND>', cmd_name)

                tv_spp = tv_spp.replace('<PACKET_DATA_LENGTH>', "{:d}".format(dp_packet.packet_data_length))
                tv_spp_raw = tv_spp_raw.replace('<SPP_DATA_LENGTH>', "{:d}".format(len(dp_packet.spp_data)))
                packet_string = hex_tabulate(dp_packet.spp_data, values_per_row)
                tv_spp_raw = tv_spp_raw.replace('<SPP_DATA>', packet_string)

                if dp_packet.simulated_error:
                    tv_spp = tv_spp.replace('<SIMULATED_ERROR>', 'True')
                else:
                    tv_spp = tv_spp.replace('<SIMULATED_ERROR>', 'False')

                if dp_packet.validation_mask == 0:
                    tv_spp = tv_spp.replace('<MAC_VALID>', 'True')
                else:
                    tv_spp = tv_spp.replace('<MAC_VALID>', 'False')
                packet_string = hex_tabulate(dp_packet.mac_digest, values_per_row)
                tv_spp_raw = tv_spp_raw.replace('<MAC_DIGEST>', packet_string)

                textview_buffer.insert(textview_buffer.get_end_iter(), tv_spp)
                if Handler.display_spp:
                    textview_buffer.insert(textview_buffer.get_end_iter(), tv_spp_raw)

                if dp_packet.spp_packet[0] == 0x08:
                    if dp_packet.spp_data[0] == 0x03:
                        for n in range(dp_packet.spp_data[1]):
                            payload_begin = 2 + (science_payload_length * n)
                            payload_end = payload_begin + science_payload_length
                            packet_string = payload_decode(dp_packet.spp_data[0],
                                                           dp_packet.spp_data[payload_begin:payload_end], n)
                            textview_buffer.insert(textview_buffer.get_end_iter(), packet_string)
                    elif dp_packet.spp_data[0] == 0x02:
                        for n in range(1):
                            payload_begin = 2 + (health_payload_length * n)
                            payload_end = payload_begin + health_payload_length
                            packet_string = payload_decode(dp_packet.spp_data[0],
                                                           dp_packet.spp_data[payload_begin:payload_end], n)
                            textview_buffer.insert(textview_buffer.get_end_iter(), packet_string)
                    else:
                        packet_string = ''

        if Handler.display_ax25:
            tv_ax25 = tv_ax25.replace('<AX25_DESTINATION>', ax25_callsign(ax25_packet[0:7]))
            tv_ax25 = tv_ax25.replace('<AX25_SOURCE>', ax25_callsign(ax25_packet[7:14]))
            tv_ax25 = tv_ax25.replace('<AX25_PACKET_LENGTH>', "{:d}".format(len(ax25_packet)))
            packet_string = hex_tabulate(ax25_packet, values_per_row)
            tv_ax25 = tv_ax25.replace('<AX25_PACKET>', packet_string)
            textview_buffer.insert(textview_buffer.get_end_iter(), tv_ax25)

        textview_buffer.insert(textview_buffer.get_end_iter(), "}\n")
        end_mark = textview_buffer.create_mark('END', textview_buffer.get_end_iter(), True)
        textview.scroll_mark_onscreen(end_mark)
    return (True)


def payload_decode(command, payload_data, payload_number):
    science_payload_string = (
            '  "PAYLOAD<PAYLOAD_NUMBER>":{\n' +
            '    "PAYLOAD_TYPE":"SCIENCE",\n' +
            '    "GPSTIME":"<GPSTIME>", "GPSWEEK":"<GPSWEEK>",\n' +
            '    "XPOS":"<XPOS>", "YPOS":"<YPOS>", "ZPOS":"<ZPOS>",\n' +
            '    "NUMPVT":"<NUMPVT>", "PDOP":"<PDOP>",\n' +
            '    "XVEL":"<XVEL>", "YVEL":"<YVEL>", "ZVEL":"<ZVEL>",\n' +
            '    "LATITUDE":"<LATITUDE>", "LONGITUDE":"<LONGITUDE>",\n' +
            '    "FIXQUALITY":"<FIXQUALITY>", "NUMTRACKED":"<NUMTRACKED>", "HDOP":"<HDOP>",\n' +
            '    "ALTITUDE":"<ALTITUDE>",\n' +
            '    "GX":"<GX>", "GY":"<GY>", "GZ":"<GZ>",\n' +
            '    "MX":"<MX>", "MY":"<MY>", "MZ":"<MZ>",\n' +
            '    "VBCR1":"<VBCR1>", "IBCR1A":"<IBCR1A>", "IBCR1B":"<IBCR1B>",\n' +
            '    "TBCR1A":"<TBCR1A>", "TBCR1B":"<TBCR1B>",\n' +
            '    "SDBCR1A":"<SDBCR1A>", "SDBCR1B":"<SDBCR1B>",\n' +
            '    "VBCR2":"<VBCR2>", "IBCR2A":"<IBCR2A>", "IBCR2B":"<IBCR2B>",\n' +
            '    "TBCR2A":"<TBCR2A>", "TBCR2B":"<TBCR2B>",\n' +
            '    "SDBCR2A":"<SDBCR2A>", "SDBCR2B":"<SDBCR2B>",\n' +
            '    "VBCR4":"<VBCR4>", "IBCR4A":"<IBCR4A>",\n' +
            '    "TBCR4A":"<TBCR4A>",\n' +
            '    "SDBCR4A":"<SDBCR4A>", "SDBCR4B":"<SDBCR4B>"\n' +
            '  },\n'
    )
    health_payload_string = (
            '  "PAYLOAD0":{\n' +
            '    "PAYLOAD_TYPE":"HEALTH",\n' +
            '    "BROWNOUT_RESETS":"<BROWNOUT_RESETS>", "AUTO_SOFTWARE_RESETS":"<AUTO_SOFTWARE_RESETS>",\n' +
            '    "MANUAL_RESETS":"<MANUAL_RESETS>", "COMMS_WATCHDOG_RESETS":"<COMMS_WATCHDOG_RESETS>",\n' +
            '    "IIDIODE_OUT":"<IIDIODE_OUT>", "VIDIODE_OUT":"<VIDIODE_OUT>",\n' +
            '    "I3V3_DRW":"<I3V3_DRW>", "I5V_DRW":"<I5V_DRW>",\n' +
            '    "IPCM12V":"<IPCM12V>", "VPCM12V":"<VPCM12V>",\n' +
            '    "IPCMBATV":"<IPCMBATV>", "VPCKBATV":"<VPCKBATV>",\n' +
            '    "IPCM5V":"<IPCM5V>", "VPCM5V":"<VPCM5V>",\n' +
            '    "IPCM3V3":"<IPCM3V3>", "VPCM3V3":"<VPCM3V3>",\n' +
            '    "TBRD":"<TBRD>",\n' +
            '    "VSW1":"<VSW1>", "ISW1":"<ISW1>", "VSW8":"<VSW8>", "ISW8":"<ISW8>",\n' +
            '    "VSW9":"<VSW9>", "ISW9":"<ISW9>", "VSW10":"<VSW10>", "ISW10":"<ISW10>",\n' +
            '    "VBCR1":"<VBCR1>", "IBCR1A":"<IBCR1A>", "IBCR1B":"<IBCR1B>",\n' +
            '    "TBCR1A":"<TBCR1A>", "TBCR1B":"<TBCR1B>",\n' +
            '    "SDBCR1A":"<SDBCR1A>", "SDBCR1B":"<SDBCR1B>",\n' +
            '    "VBCR2":"<VBCR2>", "IBCR2A":"<IBCR2A>", "IBCR2B":"<IBCR2B>",\n' +
            '    "TBCR2A":"<TBCR2A>", "TBCR2B":"<TBCR2B>",\n' +
            '    "SDBCR2A":"<SDBCR2A>", "SDBCR2B":"<SDBCR2B>",\n' +
            '    "VBCR4":"<VBCR4>", "IBCR4A":"<IBCR4A>",\n' +
            '    "TBCR4A":"<TBCR4A>",\n' +
            '    "SDBCR4A":"<SDBCR4A>", "SDBCR4B":"<SDBCR4B>",\n' +
            '    "ANTENNA_STATUS":"<ANTENNA_STATUS>"\n' +
            '  },\n'
    )
    if command == COMMAND_CODES['XMIT_SCIENCE']:
        payload_string = science_payload_string
        payload_string = payload_string.replace('<PAYLOAD_NUMBER>', "{:1d}".format(payload_number))
        payload_fields = science_payload_fields
    elif command == COMMAND_CODES['XMIT_HEALTH']:
        payload_string = health_payload_string
        payload_fields = health_payload_fields
    else:
        payload_string = ''
        payload_fields = []
    idx = 0
    for field in payload_fields:
        if field[1] == 'LATLON':
            deg_min_int = from_bigendian(payload_data[idx:(idx + 2)], 2)
            deg_int = int(deg_min_int / 100.0)
            min_int = deg_min_int - (deg_int * 100)
            min_frac = from_bigendian(payload_data[(idx + 2):(idx + 6)], 4)
            field_value = deg_int + (from_fake_float(min_int, min_frac) / 60.0)
            if (payload_data[(idx + 6)] == 0x53) or (payload_data[(idx + 6)] == 0x57):
                field_value = -field_value
            payload_string = payload_string.replace(field[0], "{:f}".format(field_value))
            idx = idx + 7
        elif field[1] == 'DOP':
            field_value = from_fake_float(payload_data[idx],
                                          from_bigendian(payload_data[(idx + 1):(idx + 5)], 4))
            payload_string = payload_string.replace(field[0], "{:f}".format(field_value))
            idx = idx + 5
        elif field[1] == 'GPSTIME':
            field_value = from_fake_float(from_bigendian(payload_data[idx:(idx + 4)], 4),
                                          from_bigendian(payload_data[(idx + 4):(idx + 8)], 4))
            payload_string = payload_string.replace(field[0], "{:14.7f}".format(field_value))
            idx = idx + 8
        elif field[1] == 'FLOAT16':
            field_value = (int(from_bigendian(payload_data[idx:(idx + 2)], 2)) * field[2]) + field[3]
            payload_string = payload_string.replace(field[0], "{:f}".format(field_value))
            idx = idx + 2
        elif field[1] == 'INT32':
            field_value = (int(from_bigendian(payload_data[idx:(idx + 4)], 4)) * field[2]) + field[3]
            field_value = to_int32(field_value)
            payload_string = payload_string.replace(field[0], "{:d}".format(field_value))
            idx = idx + 4
        elif field[1] == 'INT16':
            field_value = (int(from_bigendian(payload_data[idx:(idx + 2)], 2)) * field[2]) + field[3]
            field_value = to_int16(field_value)
            payload_string = payload_string.replace(field[0], "{:d}".format(field_value))
            idx = idx + 2
        elif field[1] == 'UINT32':
            field_value = (int(from_bigendian(payload_data[idx:(idx + 4)], 4)) * field[2]) + field[3]
            payload_string = payload_string.replace(field[0], "{:d}".format(field_value))
            idx = idx + 4
        elif field[1] == 'UINT16':
            field_value = (int(from_bigendian(payload_data[idx:(idx + 2)], 2)) * field[2]) + field[3]
            payload_string = payload_string.replace(field[0], "{:d}".format(field_value))
            idx = idx + 2
        elif field[1] == 'UINT8':
            field_value = (int(payload_data[idx]) * field[2]) + field[3]
            payload_string = payload_string.replace(field[0], "{:d}".format(field_value))
            idx = idx + 1
        elif field[1] == 'HEX32':
            field_value = (int(from_bigendian(payload_data[idx:(idx + 4)], 4)) * field[2]) + field[3]
            payload_string = payload_string.replace(field[0], "0x{:08X}".format(field_value))
            idx = idx + 2
        elif field[1] == 'HEX16':
            field_value = (int(from_bigendian(payload_data[idx:(idx + 2)], 2)) * field[2]) + field[3]
            payload_string = payload_string.replace(field[0], "0x{:04X}".format(field_value))
            idx = idx + 2
        elif field[1] == 'HEX8':
            field_value = (int(payload_data[idx]) * field[2]) + field[3]
            payload_string = payload_string.replace(field[0], "0x{:02X}".format(field_value))
            idx = idx + 1
        else:
            field_value = 0
            payload_string = payload_string.replace(field[0], "{:d}".format(field_value))
            print('Bad Field Name')
    return (payload_string)


"""
Main
"""


def main():
    global builder
    global textview
    global textview2
    global textview_buffer
    global textview2_buffer
    global argwindow
    global filechooser2window
    global checkbutton1
    global checkbutton2
    global switch1
    global switch2
    global buffer_saved
    global buffer_filename
    global entry_objs
    global label_objs
    global spp_header_len
    global ground_sequence_number
    global spacecraft_sequence_numbers
    global q_display_packet
    global p_receive_packet
    global q_receive_packet
    global encrypt_uplink
    global gs_cipher
    global expected_spacecraft_sequence_number
    global health_payload_length
    global health_payloads_per_packet
    global health_payloads_available
    global doing_health_payloads
    global science_payload_length
    global science_payloads_per_packet
    global science_payloads_available
    global downlink_payloads_pending
    global doing_science_payloads
    global transmit_timeout_count
    global ack_timeout
    global max_retries
    global sequence_number_window
    global spacecraft_transmit_power
    global last_tc_packet
    global first_packet
    global tc_packets_waiting_for_ack
    global gs_xcvr_uhd_pid
    global tm_packets_to_ack
    global tm_packets_to_nak
    global my_packet_type
    global dump_mode
    global sc_ax25_callsign
    global gs_ax25_callsign
    global ax25_badpacket
    global sequencer

    buffer_saved = False
    filedialog_save = False
    first_packet = True
    ops_mode = None
    radio_server = False
    rx_hostname = 'localhost'
    tx_hostname = 'localhost'
    rx_port = 18500
    tx_port = 18500

    dump_mode = False
    my_packet_type = 0x18
    their_packet_type = 0x08
    spp_header_len = 15
    buffer_filename = ''
    ground_sequence_number = 1
    expected_spacecraft_sequence_number = 0
    spacecraft_sequence_numbers = []
    health_payload_length = 89
    health_payloads_per_packet = 4
    health_payloads_available = 1
    doing_health_payloads = False
    science_payload_length = 109
    science_payloads_per_packet = 2
    science_payloads_available = 1
    downlink_payloads_pending = 0
    doing_science_payloads = False
    tm_packet_window = 1
    transmit_timeout_count = 4
    ack_timeout = 5
    max_retries = 4
    sequence_number_window = 2
    spacecraft_transmit_power = 0x7D
    last_tc_packet = array.array('B', [])
    tc_packets_waiting_for_ack = []
    tm_packets_to_ack = []
    tm_packets_to_nak = []
    autostart_radio = None
    sequencer_enable = True
    sequencer_hostname = None

    script_folder_name = os.path.dirname(os.path.realpath(__file__))
    ground_ini = script_folder_name + '/' + 'ground.ini'
    keys_ini = script_folder_name + '/' + 'keys.ini'
    ground_glade = script_folder_name + '/' + 'ground.glade'
    config = configparser.ConfigParser()
    config.read([ground_ini])
    debug = config['ground'].getboolean('debug')
    program_name = config['ground']['program_name']
    program_version = config['ground']['program_version']
    src_callsign = config['ground']['callsign']
    ops_mode = config['ground']['ops_mode']
    if ops_mode.upper() == 'LOCAL':
        rx_hostname = config['ground']['rx_hostname_local']
        tx_hostname = config['ground']['tx_hostname_local']
        rx_port = int(config['ground']['rx_port_local'])
        tx_port = int(config['ground']['tx_port_local'])
        sequencer_enable = True
        autostart_radio = True
    elif ops_mode.upper() == 'SIM':
        rx_hostname = config['ground']['rx_hostname_sim']
        tx_hostname = config['ground']['tx_hostname_sim']
        rx_port = int(config['ground']['rx_port_sim'])
        tx_port = int(config['ground']['tx_port_sim'])
        sequencer_enable = False
        autostart_radio = False
    elif ops_mode.upper() == 'VTGS':
        rx_hostname = config['ground']['rx_hostname_vtgs']
        tx_hostname = config['ground']['tx_hostname_vtgs']
        rx_port = int(config['ground']['rx_port_vtgs'])
        tx_port = int(config['ground']['tx_port_vtgs'])
        sequencer_enable = False
        autostart_radio = False
    else:
        print('Invalid ops_mode')
        exit()
    src_ssid = int(config['ground']['ssid'])
    dst_callsign = config['libertas_sim']['callsign']
    dst_ssid = int(config['libertas_sim']['ssid'])
    gs_xcvr_uhd = os.path.expandvars(config['comms']['gs_xcvr_uhd'])
    turnaround = float(config['comms']['turnaround'])
    sequencer_hostname = config['ground']['sequencer_hostname']
    encrypt_uplink = config['comms'].getboolean('encrypt_uplink')
    ground_maxsize_packets = config['comms'].getboolean('ground_maxsize_packets')
    use_serial = config['comms'].getboolean('use_serial')
    serial_device_name = config['comms']['serial_device_name']
    serial_device_baudrate = int(config['comms']['serial_device_baudrate'])
    use_lithium_cdi = config['comms'].getboolean('use_lithium_cdi')
    uplink_simulated_error_rate = config['comms']['uplink_simulated_error_rate']
    downlink_simulated_error_rate = config['comms']['downlink_simulated_error_rate']

    config_keys = configparser.ConfigParser()
    config_keys.read([keys_ini])
    sc_mac_key = config_keys['keys']['sc_mac_key'].encode()
    gs_mac_key = config_keys['keys']['gs_mac_key'].encode()
    oa_key = config_keys['keys']['oa_key'].encode()
    gs_encryption_key = config_keys['keys']['gs_encryption_key'].encode()
    gs_iv = config_keys['keys']['gs_iv'].encode()

    if debug:
        logging.basicConfig(filename='ground.log', level=logging.DEBUG, format='%(asctime)s %(message)s')
    else:
        logging.basicConfig(filename='ground.log', level=logging.INFO, format='%(asctime)s %(message)s')
    logging.info('%s %s: Run started', program_name, program_version)
    logger = mp.log_to_stderr()
    logger.setLevel(logging.INFO)
    # Example: logger.info('Text to log from process %s with pid %s' % (p.name, p.pid))

    if use_serial:
        gs_xcvr_uhd_pid = None
    else:
        if autostart_radio:
            print('Please wait while the radio starts... ', gs_xcvr_uhd)
            # sb_context_id = statusbar1.get_context_id('radio')
            # statusbar1.push(sb_context_id, 'Please wait while the radio starts...')
            gs_xcvr_uhd_pid = subprocess.Popen([gs_xcvr_uhd])
            # time.sleep(5)
            # statusbar1.pop(sb_context_id)
        else:
            gs_xcvr_uhd_pid = None

    GsCipher.mode = 'CBC'
    GsCipher.gs_encryption_key = gs_encryption_key
    GsCipher.gs_iv = gs_iv
    gs_cipher = GsCipher()
    gs_cipher.logger = logger

    ax25_header, sc_ax25_callsign, gs_ax25_callsign = init_ax25_header(dst_callsign, dst_ssid, src_callsign, src_ssid)
    ax25_badpacket = init_ax25_badpacket(ax25_header, their_packet_type)

    SppPacket.ax25_header = ax25_header
    SppPacket.oa_key = oa_key
    SppPacket.use_serial = use_serial
    SppPacket.tm_packet_window = tm_packet_window
    SppPacket.turnaround = turnaround
    SppPacket.ground_maxsize_packets = ground_maxsize_packets
    SppPacket.sc_mac_key = sc_mac_key
    SppPacket.gs_mac_key = gs_mac_key
    SppPacket.encrypt_uplink = encrypt_uplink
    SppPacket.gs_cipher = gs_cipher
    SppPacket.gs_ax25_callsign = gs_ax25_callsign
    SppPacket.sc_ax25_callsign = sc_ax25_callsign
    SppPacket.uplink_simulated_error_rate = float(uplink_simulated_error_rate) / 100.0
    SppPacket.downlink_simulated_error_rate = float(downlink_simulated_error_rate) / 100.0
    SppPacket.logger = logger

    RadioDevice.radio_server = radio_server
    RadioDevice.rx_hostname = rx_hostname
    RadioDevice.rx_port = rx_port
    RadioDevice.tx_hostname = tx_hostname
    RadioDevice.tx_port = tx_port
    RadioDevice.serial_device_name = serial_device_name
    RadioDevice.serial_device_baudrate = serial_device_baudrate
    RadioDevice.use_serial = use_serial
    RadioDevice.use_lithium_cdi = use_lithium_cdi
    RadioDevice.logger = logger

    SequencerDevice.logger = logger
    sequencer = SequencerDevice(sequencer_enable, sequencer_hostname)
    Handler.sequencer = sequencer

    radio = RadioDevice()
    radio.ack_timeout = ack_timeout * 1.25
    radio.max_retries = max_retries
    radio.open()
    SppPacket.radio = radio
    RadioDevice.sequencer = sequencer

    q_receive_packet = mp.Queue()
    q_display_packet = mp.Queue()
    SppPacket.q_display_packet = q_display_packet

    builder = Gtk.Builder()
    builder.add_from_file(ground_glade)
    builder.connect_signals(Handler())
    appwindow = builder.get_object("applicationwindow1")
    textview = builder.get_object("textview1")
    textview_buffer = textview.get_buffer()
    textview.set_monospace(monospace=True)
    # textview2 = builder.get_object("textview2")
    # textview2_buffer = textview2.get_buffer()
    argwindow = builder.get_object("dialog1")
    filechooserwindow = builder.get_object("filechooserdialog1")
    filechooser2window = builder.get_object("filechooserdialog2")
    checkbutton1 = builder.get_object('checkbutton1')
    checkbutton1.set_active(True)
    checkbutton2 = builder.get_object('checkbutton2')
    checkbutton2.set_active(True)
    switch1 = builder.get_object('switch1')
    switch1.set_active(True)
    switch2 = builder.get_object('switch2')
    switch2.set_active(True)
    statusbar1 = builder.get_object('statusbar1')
    entry_objs = [
        builder.get_object("entry2"),
        builder.get_object("entry3"),
        builder.get_object("entry4"),
        builder.get_object("entry5"),
        builder.get_object("entry6"),
        builder.get_object("entry7"),
        builder.get_object("entry8"),
        builder.get_object("entry9"),
        builder.get_object("entry10")
    ]
    label_objs = [
        builder.get_object("label4"),
        builder.get_object("label5"),
        builder.get_object("label6"),
        builder.get_object("label7"),
        builder.get_object("label8"),
        builder.get_object("label9"),
        builder.get_object("label16"),
        builder.get_object("label17"),
        builder.get_object("label18")
    ]
    label11 = builder.get_object("label11")

    appwindow_title = ' '.join([program_name, program_version])
    appwindow.set_title(appwindow_title)
    appwindow.show_all()

    Handler.filechooserwindow = filechooserwindow
    Handler.filedialog1_save = filedialog_save
    Handler.filechooser2window = filechooser2window
    Handler.label11 = label11

    p_receive_packet = mp.Process(target=receive_packet, name='receive_packet', args=(gs_ax25_callsign, radio, q_receive_packet, logger, sequencer))
    p_receive_packet.start()
    process_thread = threading.Thread(name='process_received', target=process_received, daemon=True)
    process_thread.start()

    os.nice(20)

    GObject.threads_init()
    GObject.timeout_add(500, display_packet)
    Gtk.main()


if __name__ == "__main__":
    # execute only if run as a script
    main()
