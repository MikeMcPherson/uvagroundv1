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
import hexdump
import random
from ground.constant import COMMAND_CODES, COMMAND_NAMES
from ground.packet_functions import SppPacket, RadioDevice, kiss_wrap, kiss_unwrap
from ground.packet_functions import receive_packet, make_ack, make_nak
from ground.packet_functions import to_bigendian, from_bigendian, to_fake_float, from_fake_float
from ground.packet_functions import init_ax25_header, sn_increment, sn_decrement
from ground.packet_functions import ax25_callsign

"""
GUI Handlers
"""


class Handler:
    filechooserwindow = None
    filedialog_save = None
    filechooser2window = None
    baudrates = None
    label11 = None
    radio = None

    def on_destroy(self, *args):
        do_save = True
        do_destroy(do_save)

    def on_quit_nosave(self, *args):
        do_save = False
        do_destroy(do_save)

    def on_command(self, button):
        button_label = button.get_label().replace('...', '')
        process_command(button_label)

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
        self.filedialog_save = False

    def on_filechooserdialog1_save(self, button):
        self.filechooserwindow.hide()
        self.filedialog_save = True

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

    def on_use_output(self, button):
        self.radio.close()
        use_serial = button.get_active()
        RadioDevice.use_serial = use_serial
        self.radio.open()

    def on_filechooserdialog2_cancel(self, button):
        self.filechooser2window.hide()

    def on_filechooserdialog2_open(self, button):
        self.filechooser2window.hide()

    def on_combobox1_changed(self, button):
        self.radio.set_baudrate = self.baudrates[button.get_active()]

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
        title = '"XMIT_HEALTH" Arguments'
        labels = ['# Payloads', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A']
        defaults = ['10', '0x00', '0x00', '0x00', '0x00', '0x00', '0x00', '0x00', '0x00']
        tooltips = [
            '(8-bit) Number of Health Payloads to be downlinked.  0xFF means downlink all outstanding payloads.',
            'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A']
        args = dialog1_run(title, labels, defaults, tooltips)
        if dialog1_xmit:
            do_transmit_packet = True
            do_sn_increment = True
            expect_ack = True
            downlink_payloads_pending = args[0]
            tc_data = array.array('B', [0x02])
            tc_data.append(downlink_payloads_pending)
            tc_packet.set_spp_data(tc_data)
            tc_packet.set_sequence_number(ground_sequence_number)

    elif button_label == 'XMIT_SCIENCE':
        title = '"XMIT_SCIENCE" Arguments'
        labels = ['# Payloads', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A']
        defaults = ['10', '0x00', '0x00', '0x00', '0x00', '0x00', '0x00', '0x00', '0x00']
        tooltips = [
            '(8-bit) Number of Science Payloads to be downlinked.  0xFF means downlink all outstanding payloads.',
            'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A']
        args = dialog1_run(title, labels, defaults, tooltips)
        if dialog1_xmit:
            do_transmit_packet = True
            do_sn_increment = True
            expect_ack = True
            downlink_payloads_pending = args[0]
            tc_data = array.array('B', [0x03])
            tc_data.append(downlink_payloads_pending)
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
        labels = ['TM Window', 'XMIT Timeout', 'ACK Timeout', 'Sequence Window', 'Spacecraft SN',
                  'Ground SN', 'Turnaround', 'N/A', 'N/A']
        defaults = ['1', '4', '10', '2', '1', '1', '1000', '0x0000', '0x0000']
        tooltips = ['(8-bit) Number of Health or Science packets the spacecraft will transmit ' +
                    'before waiting for an ACK.  Default: 0x01. Maximum: 0x14',
                    '(8-bit) Number of unacknowledged transmit windows before the spacecraft ' +
                    'ceases transmission.  Default: 0x04.',
                    '(8-bit) Number of seconds the spacecraft waits for an ACK or NAK ' +
                    'before retransmitting the last window.  Default: 0x0A.',
                    '(8-bit) Maximum allowable difference between the expected and received ' +
                    'Sequence Number.  Default: 0x02.',
                    '(16-bit) Next packet from the spacecraft will have this sequence number',
                    '(16-bit) Next packet from the ground station will have this sequence number',
                    '(16-bit) Minimum delay between transmit and receive packets.',
                    'N/A', 'N/A']
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
Process Received Packets (thread)
"""


def process_received():
    global expected_spacecraft_sequence_number
    global spacecraft_key
    global ground_station_key
    global ground_sequence_number
    global tc_packets_waiting_for_ack
    global q_receive_packet
    global q_display_packet
    global health_payloads_available
    global science_payloads_available
    global downlink_payloads_pending
    global transmit_timeout_count
    global ack_timeout
    global sequence_number_window
    global ignore_security_trailer_error
    global tm_packets_to_ack
    global tm_packets_to_nak
    global health_payloads_per_packet
    global science_payloads_per_packet

    while True:
        ax25_packet = q_receive_packet.get()
        tm_packet = SppPacket('TM', dynamic=False)
        tm_packet.parse_ax25(ax25_packet)
        if (tm_packet.validation_mask != 0) and (not ignore_security_trailer_error):
            packet_valid = False
            tm_packets_to_nak.append(tm_packet)
        else:
            packet_valid = True
            tm_packets_to_ack.append(tm_packet)

        do_transmit_packet = False
        downlink_complete = False
        command = tm_packet.command
        if command == COMMAND_CODES['ACK']:
            tc_packets_waiting_for_ack = []
            do_transmit_packet = False
        elif command == COMMAND_CODES['NAK']:
            for p in tc_packets_waiting_for_ack:
                p.transmit()
            do_transmit_packet = False
        elif command == COMMAND_CODES['XMIT_COUNT']:
            health_payloads_available = from_bigendian(tm_packet.spp_data[1:3], 2)
            science_payloads_available = from_bigendian(tm_packet.spp_data[3:5], 2)
            do_transmit_packet = True
        elif command == COMMAND_CODES['XMIT_HEALTH']:
            if packet_valid:
                if tm_packet.spp_data[1] > 0:
                    downlink_payloads_pending = downlink_payloads_pending - health_payloads_per_packet
                    health_payloads_available = health_payloads_available - health_payloads_per_packet
                else:
                    downlink_payloads_pending = 0
                if downlink_payloads_pending <= 0:
                    downlink_complete = True
            do_transmit_packet = True
        elif command == COMMAND_CODES['XMIT_SCIENCE']:
            if packet_valid:
                if tm_packet.spp_data[1] > 0:
                    downlink_payloads_pending = downlink_payloads_pending - science_payloads_per_packet
                    science_payloads_available = science_payloads_available - science_payloads_per_packet
                else:
                    downlink_payloads_pending = 0
                if downlink_payloads_pending <= 0:
                    downlink_complete = True
            do_transmit_packet = True
        elif command == COMMAND_CODES['READ_MEM']:
            do_transmit_packet = True
        elif command == COMMAND_CODES['GET_COMMS']:
            SppPacket.tm_packet_window = tm_packet.spp_data[1]
            transmit_timeout_count = tm_packet.spp_data[2]
            ack_timeout = tm_packet.spp_data[3]
            sequence_number_window = tm_packet.spp_data[4]
            turnaround = from_bigendian(tm_packet.spp_data[9:11], 2)
            SppPacket.turnaround = turnaround
            do_transmit_packet = True
        elif command == COMMAND_CODES['MAC_TEST']:
            do_transmit_packet = False
        else:
            pass

        if do_transmit_packet:
            if (((len(tm_packets_to_ack) + len(tm_packets_to_nak)) >= SppPacket.tm_packet_window) or downlink_complete):
                if len(tm_packets_to_nak) > 0:
                    tc_packet = make_nak('TC', tm_packets_to_nak)
                    tc_packet.set_sequence_number(ground_sequence_number)
                    tc_packet.transmit()
                    ground_sequence_number = sn_increment(ground_sequence_number)
                    expected_spacecraft_sequence_number = sn_increment(expected_spacecraft_sequence_number)
                else:
                    tc_packet = make_ack('TC', [])
                    tc_packet.set_sequence_number(ground_sequence_number)
                    tc_packet.transmit()
                    ground_sequence_number = sn_increment(ground_sequence_number)
                    expected_spacecraft_sequence_number = sn_increment(expected_spacecraft_sequence_number)
                tm_packets_to_ack = []
                tm_packets_to_nak = []


"""
Helpers
"""

def do_destroy(do_save):
    global textview_buffer
    global p_receive_packet
    global gs_xcvr_uhd_pid
    textview_buffer.insert(textview_buffer.get_end_iter(), "]\n}\n")
    p_receive_packet.terminate()
    if gs_xcvr_uhd_pid is not None:
        if gs_xcvr_uhd_pid.poll() is None:
            gs_xcvr_uhd_pid.kill()
    if do_save:
        save_file()
    Gtk.main_quit()


def load_file():
    global filechooser2window
    global textview2_buffer
    filechooser2window.run()
    script_filename = filechooser2window.get_filename()
    fp = open(script_filename, "r")
    json_return = json.load(fp)
    fp.close()
    start_iter = textview2_buffer.get_start_iter()
    end_iter = textview2_buffer.get_end_iter()
    textview2_buffer.delete(start_iter, end_iter)
    json_pretty = pprint.pformat(json_return['commands'])
    end_iter = textview2_buffer.get_end_iter()
    textview2_buffer.insert(end_iter, json_pretty, -1)


def script_clear():
    global textview2_buffer
    start_iter = textview2_buffer.get_start_iter()
    end_iter = textview2_buffer.get_end_iter()
    textview2_buffer.delete(start_iter, end_iter)


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
    global filedialog_save
    global buffer_saved
    global buffer_filename
    time_utc = time.gmtime()
    time_string = time.strftime("ground%Y%m%d%H%M%S.json", time_utc)
    Handler.filechooserwindow.set_current_name(time_string)
    Handler.filechooserwindow.run()
    if filedialog_save:
        buffer_filename = Handler.filechooserwindow.get_filename()
        print(buffer_filename)
        write_buffer(buffer_filename)
    buffer_saved = True


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
        buffer_string = buffer_string + '        ' + ", ".join(map(str, buffer_list))
        if (buffer_len - i) > values_per_row:
            buffer_string = buffer_string + ',\n'
        else:
            buffer_string = buffer_string + '\n'
    return(buffer_string)

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
    global spacecraft_key
    global ground_station_key

    if not q_display_packet.empty():
        values_per_row = 8
        ax25_packet = q_display_packet.get()
        if ax25_packet[16] == 0x18:
            dp_packet = SppPacket('TC', dynamic=False)
        elif ax25_packet[16] == 0x08:
            dp_packet = SppPacket('TM', dynamic=False)
        else:
            dp_packet = SppPacket('OA', dynamic=False)
        dp_packet.parse_ax25(ax25_packet)
        if first_packet:
            textview_buffer.insert(textview_buffer.get_end_iter(), "{\n\"packets\" : [\n")
            first_packet = False
        else:
            textview_buffer.insert(textview_buffer.get_end_iter(), ",\n")
        textview_buffer.insert(textview_buffer.get_end_iter(), "{\n")

        tv_header = ('    "sender":"<SENDER>", ' +
                     '"packet_type":"<PACKET_TYPE>", ' +
                     '"command":"<COMMAND>",\n')

        tv_spp = ('    "gps_week":"<GPS_WEEK>", ' +
                  '"gps_time":"<GPS_TIME>", ' +
                  '"sequence_number":"<SEQUENCE_NUMBER>",\n' +
                  '    "command":"<COMMAND>", ' +
                  '"packet_data_length":"<PACKET_DATA_LENGTH>", ' +
                  '"<PACKET_TYPE>_data_length":"<SPP_DATA_LENGTH>",\n' +
                  '    "<PACKET_TYPE>_data":[\n<SPP_DATA>    ],\n' +
                  '    "security_trailer_valid":"<MAC_VALID>",\n' +
                  '    "security_trailer":[\n<MAC_DIGEST>    ],\n')

        tv_ax25 = ('    "ax25_destination":"<AX25_DESTINATION>", ' +
                   '"ax25_source":"<AX25_SOURCE>", ' +
                   '"ax25_packet_length":"<AX25_PACKET_LENGTH>",\n' +
                   '    "ax25_packet":[\n<AX25_PACKET>    ]\n')

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
            tv_header = tv_header.replace('<COMMAND>', COMMAND_NAMES[dp_packet.command])
            tv_spp = tv_spp.replace('<SENDER>', 'spacecraft')
            tv_spp = tv_spp.replace('<PACKET_TYPE>', packet_type)
        elif dp_packet.packet_type == 0x18:
            packet_type = 'TC'
            tv_header = tv_header.replace('<SENDER>', 'ground')
            tv_header = tv_header.replace('<PACKET_TYPE>', packet_type)
            tv_header = tv_header.replace('<COMMAND>', COMMAND_NAMES[dp_packet.command])
            tv_spp = tv_spp.replace('<SENDER>', 'ground')
            tv_spp = tv_spp.replace('<PACKET_TYPE>', packet_type)
        else:
            packet_type = 'UNKNOWN'
            tv_header = tv_header.replace('<SENDER>', 'spacecraft')
            tv_header = tv_header.replace('<PACKET_TYPE>', packet_type)
            tv_header = tv_header.replace('<COMMAND>', 'UNKNOWN')

        textview_buffer.insert(textview_buffer.get_end_iter(), tv_header)

        if dp_packet.is_spp_packet:
            tv_spp = tv_spp.replace('<GPS_WEEK>', "{:d}".format(dp_packet.gps_week))
            tv_spp = tv_spp.replace('<GPS_TIME>', "{:14.7f}".format(dp_packet.gps_sow))
            tv_spp = tv_spp.replace('<SEQUENCE_NUMBER>', "{:05d}".format(dp_packet.sequence_number))
            tv_spp = tv_spp.replace('<COMMAND>', COMMAND_NAMES[dp_packet.command])

            tv_spp = tv_spp.replace('<PACKET_DATA_LENGTH>', "{:d}".format(dp_packet.packet_data_length))
            tv_spp = tv_spp.replace('<SPP_DATA_LENGTH>', "{:d}".format(len(dp_packet.spp_data)))
            packet_string = hex_tabulate(dp_packet.spp_data, values_per_row)
            tv_spp = tv_spp.replace('<SPP_DATA>', packet_string)

            if dp_packet.validation_mask == 0:
                tv_spp = tv_spp.replace('<MAC_VALID>', 'True')
            else:
                tv_spp = tv_spp.replace('<MAC_VALID>', 'False')
            packet_string = hex_tabulate(dp_packet.mac_digest, values_per_row)
            tv_spp = tv_spp.replace('<MAC_DIGEST>', packet_string)

            textview_buffer.insert(textview_buffer.get_end_iter(), tv_spp)

            if ((dp_packet.spp_packet[0] == 0x08) and (dp_packet.spp_data[0] == 0x03)):
                for n in range(dp_packet.spp_data[1]):
                    payload_begin = 2 + (science_payload_length * n)
                    payload_end = payload_begin + science_payload_length
                    packet_string = payload_decode(dp_packet.spp_data[0],
                                                   dp_packet.spp_data[payload_begin:payload_end], n)
                    textview_buffer.insert(textview_buffer.get_end_iter(), packet_string)

        tv_ax25 = tv_ax25.replace('<AX25_DESTINATION>', ax25_callsign(dp_packet.ax25_packet[0:7]))
        tv_ax25 = tv_ax25.replace('<AX25_SOURCE>', ax25_callsign(dp_packet.ax25_packet[7:14]))
        tv_ax25 = tv_ax25.replace('<AX25_PACKET_LENGTH>', "{:d}".format(len(dp_packet.ax25_packet)))

        packet_string = hex_tabulate(dp_packet.ax25_packet, values_per_row)
        tv_ax25 = tv_ax25.replace('<AX25_PACKET>', packet_string)

        textview_buffer.insert(textview_buffer.get_end_iter(), tv_ax25)

        textview_buffer.insert(textview_buffer.get_end_iter(), "}\n")
        end_mark = textview_buffer.create_mark('END', textview_buffer.get_end_iter(), True)
        textview.scroll_mark_onscreen(end_mark)
    return (True)


def payload_decode(command, payload_data, payload_number):
    science_payload_string = (
            '    "payload<PAYLOAD_NUMBER>":[\n'
            '        "payload_type":"SCIENCE",\n' +
            '        "gps_time":"<GPS_TIME>", "gps_week":"<GPS_WEEK>",\n' +
            '        "x_pos":"<X_POS>", "y_pos":"<Y_POS>", "z_pos":"<Z_POS>",\n' +
            '        "satellites_pvt":"<SATELLITES_PVT>", "pdop":"<PDOP>",\n' +
            '        "x_vel":"<X_VEL>", "y_vel":"<Y_VEL>", "z_vel":"<Z_VEL>",\n' +
            '        "latitude":"<LATITUDE>", "longitude":"<LONGITUDE>",\n' +
            '        "fix_quality":"<FIX_QUALITY>", "satellites_tracked":"<SATELLITES_TRACKED>", "hdop":"<HDOP>",\n' +
            '        "altitude":"<ALTITUDE>",\n' +
            '        "gx":"<GX>", "gy":"<GY>", "gz":"<GZ>",\n' +
            '        "mx":"<MX>", "my":"<MY>", mz":"<MZ>",\n' +
            '        "sun_sensor_vi":"<SUN_SENSOR_VI>", "sun_sensor_i":"<SUN_SENSOR_I>", "sun_sensor_ii":"<SUN_SENSOR_II>",\n' +
            '        "sun_sensor_iii":"<SUN_SENSOR_III>", "sun_sensor_iv":"<SUN_SENSOR_IV>", "sun_sensor_v":"<SUN_SENSOR_V>"\n' +
            '    ],\n'
    )
    science_payload_fields = [
            ['<GPS_TIME>', 'GPSTIME'],
            ['<GPS_WEEK>', 'UINT16'],
            ['<X_POS>', 'UINT32'],
            ['<Y_POS>', 'UINT32'],
            ['<Z_POS>', 'UINT32'],
            ['<SATELLITES_PVT>', 'UINT8'],
            ['<PDOP>', 'DOP'],
            ['<X_VEL>', 'UINT16'],
            ['<Y_VEL>', 'UINT16'],
            ['<Z_VEL>', 'UINT16'],
            ['<LATITUDE>', 'LATLON'],
            ['<LONGITUDE>', 'LATLON'],
            ['<FIX_QUALITY>', 'UINT8'],
            ['<SATELLITES_TRACKED>', 'UINT8'],
            ['<HDOP>', 'DOP'],
            ['<ALTITUDE>', 'UINT32'],
            ['<GX>', 'UINT16'],
            ['<GY>', 'UINT16'],
            ['<GZ>', 'UINT16'],
            ['<MX>', 'UINT16'],
            ['<MY>', 'UINT16'],
            ['<MZ>', 'UINT16'],
            ['<SUN_SENSOR_VI>', 'UINT16'],
            ['<SUN_SENSOR_I>', 'UINT16'],
            ['<SUN_SENSOR_II>', 'UINT16'],
            ['<SUN_SENSOR_III>', 'UINT16'],
            ['<SUN_SENSOR_IV>', 'UINT16'],
            ['<SUN_SENSOR_V>', 'UINT16']
        ]
    if command == COMMAND_CODES['XMIT_SCIENCE']:
        idx = 0
        payload_string = science_payload_string
        payload_string = payload_string.replace('<PAYLOAD_NUMBER>', "{:1d}".format(payload_number))
        for field in science_payload_fields:
            if field[1] == 'LATLON':
                field_value = from_fake_float(from_bigendian(payload_data[idx:(idx + 2)], 2),
                               from_bigendian(payload_data[(idx + 2):(idx + 6)], 4))
                if (payload_data[(idx + 6)] == 'S') or (payload_data[(idx + 6)] == 'W'):
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
            elif field[1] == 'UINT32':
                field_value = int(from_bigendian(payload_data[idx:(idx + 4)], 4))
                payload_string = payload_string.replace(field[0], "{:d}".format(field_value))
                idx = idx + 4
            elif field[1] == 'UINT16':
                field_value = int(from_bigendian(payload_data[idx:(idx + 2)], 2))
                payload_string = payload_string.replace(field[0], "{:d}".format(field_value))
                idx = idx + 2
            elif field[1] == 'UINT8':
                field_value = int(payload_data[idx])
                payload_string = payload_string.replace(field[0], "{:d}".format(field_value))
                idx = idx + 1
            else:
                field_value = 0
                payload_string = payload_string.replace(field[0], "{:d}".format(field_value))
                print('Bad Science Field Name')
    else:
        payload_string = ''
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
    global combobox1
    global radiobutton1
    global radiobutton2
    global buffer_saved
    global buffer_filename
    global filedialog_save
    global entry_objs
    global label_objs
    global spp_header_len
    global ground_sequence_number
    global spacecraft_sequence_numbers
    global q_display_packet
    global p_receive_packet
    global q_receive_packet
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
    global sequence_number_window
    global last_tc_packet
    global first_packet
    global tc_packets_waiting_for_ack
    global gs_xcvr_uhd_pid
    global ignore_security_trailer_error
    global tm_packets_to_ack
    global tm_packets_to_nak

    serial_device_name = 'pty_libertas'
    buffer_saved = False
    filedialog_save = False
    first_packet = True
    rx_server = 'localhost'
    tx_server = 'localhost'
    rx_port = 9501
    tx_port = 9500
    dst_callsign = 'W4UVA '
    dst_ssid = 11
    src_callsign = 'W4UVA '
    src_ssid = 0

    my_packet_type = 0x18
    spp_header_len = 15
    buffer_filename = ''
    ground_sequence_number = 1
    expected_spacecraft_sequence_number = 0
    spacecraft_sequence_numbers = []
    health_payload_length = 46
    health_payloads_per_packet = 4
    health_payloads_available = 1
    doing_health_payloads = False
    science_payload_length = 83
    science_payloads_per_packet = 2
    science_payloads_available = 1
    downlink_payloads_pending = 0
    doing_science_payloads = False
    tm_packet_window = 1
    transmit_timeout_count = 4
    ack_timeout = 10
    sequence_number_window = 2
    last_tc_packet = array.array('B', [])
    baudrates = [9600, 19200, 38400, 76800, 115200]
    tc_packets_waiting_for_ack = []
    tm_packets_to_ack = []
    tm_packets_to_nak = []

    config = configparser.ConfigParser()
    config.read(['ground.ini'])
    debug = config['general'].getboolean('debug')
    program_name = config['general']['program_name']
    program_version = config['general']['program_version']
    gs_xcvr_uhd = os.path.expandvars(config['comms']['gs_xcvr_uhd'])
    turnaround = float(config['comms']['turnaround'])
    spacecraft_key = config['comms']['spacecraft_key'].encode()
    ground_station_key = config['comms']['ground_station_key'].encode()
    oa_key = config['comms']['oa_key'].encode()
    ground_maxsize_packets = config['comms'].getboolean('ground_maxsize_packets')
    use_serial = config['comms'].getboolean('use_serial')
    kiss_over_serial = config['comms'].getboolean('kiss_over_serial')
    ignore_security_trailer_error = config['comms'].getboolean('ignore_security_trailer_error')

    if debug:
        logging.basicConfig(filename='ground.log', level=logging.DEBUG, format='%(asctime)s %(message)s')
    else:
        logging.basicConfig(filename='ground.log', level=logging.INFO, format='%(asctime)s %(message)s')
    logging.info('%s %s: Run started', program_name, program_version)

    if use_serial:
        gs_xcvr_uhd_pid = None
    else:
        print('Please wait while the radio starts...')
        gs_xcvr_uhd_pid = subprocess.Popen([gs_xcvr_uhd])
        time.sleep(15.0)

    ax25_header = init_ax25_header(dst_callsign, dst_ssid, src_callsign, src_ssid)
    SppPacket.ax25_header = ax25_header
    SppPacket.oa_key = oa_key
    SppPacket.use_serial = use_serial
    SppPacket.tm_packet_window = tm_packet_window
    SppPacket.turnaround = turnaround
    SppPacket.ground_maxsize_packets = ground_maxsize_packets
    SppPacket.spacecraft_key = spacecraft_key
    SppPacket.ground_station_key = ground_station_key

    RadioDevice.rx_server = rx_server
    RadioDevice.rx_port = rx_port
    RadioDevice.tx_server = tx_server
    RadioDevice.tx_port = tx_port
    RadioDevice.serial_device_name = serial_device_name
    RadioDevice.use_serial = use_serial
    RadioDevice.kiss_over_serial = kiss_over_serial

    radio = RadioDevice()
    radio.open()
    SppPacket.radio = radio

    q_receive_packet = mp.Queue()
    q_display_packet = mp.Queue()
    SppPacket.q_display_packet = q_display_packet

    builder = Gtk.Builder()
    builder.add_from_file("ground.glade")
    builder.connect_signals(Handler())
    appwindow = builder.get_object("applicationwindow1")
    textview = builder.get_object("textview1")
    textview_buffer = textview.get_buffer()
    textview.set_monospace(monospace=True)
    textview2 = builder.get_object("textview2")
    textview2_buffer = textview2.get_buffer()
    argwindow = builder.get_object("dialog1")
    filechooserwindow = builder.get_object("filechooserdialog1")
    filechooser2window = builder.get_object("filechooserdialog2")
    entry1 = builder.get_object("entry1")
    entry1.set_text(serial_device_name)
    radiobutton1 = builder.get_object("radiobutton1")
    radiobutton2 = builder.get_object("radiobutton2")
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
    combobox1 = builder.get_object("combobox1")
    combobox1.set_active(0)

    appwindow_title = ' '.join([program_name, program_version])
    appwindow.set_title(appwindow_title)
    appwindow.show_all()

    Handler.filechooserwindow = filechooserwindow
    Handler.filedialog_save = filedialog_save
    Handler.filechooser2window = filechooser2window
    Handler.baudrates = baudrates
    Handler.label11 = label11

    p_receive_packet = mp.Process(target=receive_packet, args=(my_packet_type, radio,
                                                               q_receive_packet, q_display_packet))
    p_receive_packet.start()
    process_thread = threading.Thread(name='process_received', target=process_received, daemon=True)
    process_thread.start()

    GObject.threads_init()
    GObject.timeout_add(200, display_packet)
    Gtk.main()


if __name__ == "__main__":
    # execute only if run as a script
    main()
