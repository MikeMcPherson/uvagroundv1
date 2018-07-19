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

import configparser
import logging
import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from gi.repository import GObject
import array
import time
from ground.packet_functions import receive_packet, to_bigendian, from_bigendian, to_fake_float, from_fake_float
from ground.packet_functions import is_libertas_packet, init_ax25_header, spp_wrap, spp_unwrap, lithium_wrap, \
    lithium_unwrap
from ground.packet_functions import ax25_wrap, ax25_unwrap, kiss_wrap, kiss_unwrap, ax25_callsign, validate_packet
import serial
import json
import threading
import pprint
import socket
import multiprocessing as mp
import hexdump

"""
GUI Handlers
"""


class Handler:

    def on_destroy(self, *args):
        global textview_buffer
        global p_receive_packet
        textview_buffer.insert(textview_buffer.get_end_iter(), "]\n}\n")
        p_receive_packet.terminate()
        save_file()
        Gtk.main_quit()

    def on_command(self, button):
        button_label = button.get_label().replace('...', '')
        on_command(button_label)

    def on_dialog1_cancel(self, button):
        dialog1_cancel()

    def on_dialog1_transmit(self, button):
        dialog1_transmit()

    def on_save(self, button):
        save_file()

    def on_save_as(self, button):
        save_file_as()

    def on_filechooserdialog1_cancel(self, button):
        global filechooserwindow
        global filedialog_save
        filechooserwindow.hide()
        filedialog_save = False

    def on_filechooserdialog1_save(self, button):
        global filechooserwindow
        global filedialog_save
        filechooserwindow.hide()
        filedialog_save = True

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
        global use_serial
        global rx_port
        global tx_port
        global rx_obj
        global tx_obj
        use_serial = button.get_active()
        if use_serial:
            try:
                rx_obj.close()
                tx_obj.close()
            except:
                pass
            open_serial_device()
        else:
            try:
                rx_obj.close()
            except:
                pass
            open_usrp_device()

    def on_filechooserdialog2_cancel(self, button):
        global filechooser2window
        filechooser2window.hide()

    def on_filechooserdialog2_open(self, button):
        global filechooser2window
        filechooser2window.hide()

    def on_combobox1_changed(self, button):
        global baudrates
        global rx_obj
        rx_obj.baudrate = baudrates[button.get_active()]

    def validate_entry_uint16(self, entry):
        global label11
        try:
            i = int(entry.get_text(), 0)
            label11.set_text('')
        except ValueError:
            label11.set_text('Field must be numeric.')


def dialog1_run(title, labels, defaults, tooltips):
    global argwindow
    global entry_objs
    global label_objs
    argwindow.set_title(title)
    for i in range(6):
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
            int(entry_objs[4].get_text(), 0), int(entry_objs[5].get_text(), 0)]


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


def on_command(button_label):
    global ground_sequence_number
    global dialog1_xmit
    global oa_key
    global spp_header_len
    global ax25_header

    if button_label == 'CEASE_XMIT':
        tc_data = array.array('B', [0x7F])
        tc_packet = spp_wrap('TC', tc_data, spp_header_len, ground_sequence_number, ground_station_key)
        transmit_packet(tc_packet, ax25_header, True, False)

    elif button_label == 'NOOP':
        tc_data = array.array('B', [0x09])
        tc_packet = spp_wrap('TC', tc_data, spp_header_len, ground_sequence_number, ground_station_key)
        transmit_packet(tc_packet, ax25_header, True, False)

    elif button_label == 'RESET':
        title = '"RESET" Arguments'
        labels = ['Reset mask', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A']
        defaults = ['0x0000', '0x0000', '0x0000', '0x0000', '0x0000', '0x0000']
        tooltips = ['(16-bit) Bitmask indicating which spacecraft reset operations are to be performed.',
                    'N/A', 'N/A', 'N/A', 'N/A', 'N/A']
        args = dialog1_run(title, labels, defaults, tooltips)
        if dialog1_xmit:
            tc_data = array.array('B', [0x04])
            tc_data.extend(to_bigendian(args[0], 2))
            tc_packet = spp_wrap('TC', tc_data, spp_header_len, ground_sequence_number, ground_station_key)
            transmit_packet(tc_packet, ax25_header, True, False)

    elif button_label == 'XMIT_COUNT':
        tc_data = array.array('B', [0x01])
        tc_packet = spp_wrap('TC', tc_data, spp_header_len, ground_sequence_number, ground_station_key)
        transmit_packet(tc_packet, ax25_header, False, False)

    elif button_label == 'XMIT_HEALTH':
        title = '"XMIT_HEALTH" Arguments'
        labels = ['# Payloads', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A']
        defaults = ['0xFF', '0x00', '0x00', '0x00', '0x00', '0x00']
        tooltips = [
            '(8-bit) Number of Health Payloads to be downlinked.  0xFF means downlink all outstanding payloads.',
            'N/A', 'N/A', 'N/A', 'N/A', 'N/A']
        args = dialog1_run(title, labels, defaults, tooltips)
        if dialog1_xmit:
            tc_data = array.array('B', [0x02])
            tc_data.append(args[0] & 0x00FF)
            tc_packet = spp_wrap('TC', tc_data, spp_header_len, ground_sequence_number, ground_station_key)
            transmit_packet(tc_packet, ax25_header, False, False)

    elif button_label == 'XMIT_SCIENCE':
        title = '"XMIT_SCIENCE" Arguments'
        labels = ['# Payloads', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A']
        defaults = ['0xFF', '0x00', '0x00', '0x00', '0x00', '0x00']
        tooltips = [
            '(8-bit) Number of Science Payloads to be downlinked.  0xFF means downlink all outstanding payloads.',
            'N/A', 'N/A', 'N/A', 'N/A', 'N/A']
        args = dialog1_run(title, labels, defaults, tooltips)
        if dialog1_xmit:
            tc_data = array.array('B', [0x03])
            tc_data.append(args[0] & 0x00FF)
            tc_packet = spp_wrap('TC', tc_data, spp_header_len, ground_sequence_number, ground_station_key)
            transmit_packet(tc_packet, ax25_header, False, False)

    elif button_label == 'READ_MEM':
        title = '"READ_MEM" Arguments'
        labels = ['Start address', 'End address', 'N/A', 'N/A', 'N/A', 'N/A']
        defaults = ['0x00F0', '0x00F3', '0x0000', '0x0000', '0x0000', '0x0000']
        tooltips = ['(16-bit) Start of memory address range to downlink.',
                    '(16-bit) End of memory address range to downlink.',
                    'N/A', 'N/A', 'N/A', 'N/A']
        args = dialog1_run(title, labels, defaults, tooltips)
        if dialog1_xmit:
            tc_data = array.array('B', [0x08])
            tc_data.extend(to_bigendian(args[0], 2))
            tc_data.extend(to_bigendian(args[1], 2))
            tc_packet = spp_wrap('TC', tc_data, spp_header_len, ground_sequence_number, ground_station_key)
            transmit_packet(tc_packet, ax25_header, False, False)

    elif button_label == 'WRITE_MEM':
        title = '"WRITE_MEM" Arguments'
        labels = ['Start address', 'End address',
                  'Contents 0', 'Contents 1', 'Contents 2', 'Contents 3']
        defaults = ['0x00F0', '0x00F3', '0x0000', '0x0000', '0x0000', '0x0000']
        tooltips = ['(16-bit) Start of memory address range to uplink.',
                    '(16-bit) End of memory address range to uplink.  (Limited to four memory locations for testing.)',
                    '(16-bit) Memory contents', '(16-bit) Memory contents',
                    '(16-bit) Memory contents', '(16-bit) Memory contents']
        args = dialog1_run(title, labels, defaults, tooltips)
        if dialog1_xmit:
            tc_data = array.array('B', [0x07])
            for a in args:
                tc_data.extend(to_bigendian(a, 2))
            tc_packet = spp_wrap('TC', tc_data, spp_header_len, ground_sequence_number, ground_station_key)
            transmit_packet(tc_packet, ax25_header, True, False)

    elif button_label == 'SET_COMMS':
        title = '"SET_COMMS" Arguments'
        labels = ['TM Window', 'XMIT Timeout', 'ACK Timeout', 'Sequence Window', 'Turnaround', 'N/A']
        defaults = ['0x01', '0x04', '0x0A', '0x02', '0x012C', '0x0000']
        tooltips = ['(8-bit) Number of Health or Science packets the spacecraft will transmit '
                    + 'before waiting for an ACK.  Default: 0x01.',
                    '(8-bit) Number of unacknowledged transmit windows before the spacecraft '
                    + 'ceases transmission.  Default: 0x04.',
                    '(8-bit) Number of seconds the spacecraft waits for an ACK or NAK '
                    + 'before retransmitting the last window.  Default: 0x0A.',
                    '(8-bit) Maximum allowable difference between the expected and received '
                    + 'Sequence Number.  Default: 0x02.',
                    '(16-bit) Minimum delay between transmit and receive packets.',
                    'N/A']
        args = dialog1_run(title, labels, defaults, tooltips)
        if dialog1_xmit:
            tc_data = array.array('B', [0x0B])
            for a in args[0:4]:
                tc_data.append(a & 0x00FF)
            tc_data.extend([0x00, 0x00, 0x00, 0x00])
            tc_data.extend(to_bigendian(args[4], 2))
            tc_packet = spp_wrap('TC', tc_data, spp_header_len, ground_sequence_number, ground_station_key)
            transmit_packet(tc_packet, ax25_header, True, False)

    elif button_label == 'GET_COMMS':
        tc_data = array.array('B', [0x0C])
        tc_packet = spp_wrap('TC', tc_data, spp_header_len, ground_sequence_number, ground_station_key)
        transmit_packet(tc_packet, ax25_header, False, False)

    elif button_label == 'SET_MODE':
        title = '"SET_MODE" Arguments'
        labels = ['Mode', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A']
        defaults = ['0x01', '0x00', '0x00', '0x00', '0x00', '0x00']
        tooltips = ['(8-bit) DOWNLINK=1, DATA_COLLECTION=2, LOW_POWER=3',
                    'N/A', 'N/A', 'N/A', 'N/A', 'N/A']
        args = dialog1_run(title, labels, defaults, tooltips)
        if dialog1_xmit:
            tc_data = array.array('B', [0x0A])
            tc_data.append(args[0] & 0x00FF)
            tc_packet = spp_wrap('TC', tc_data, spp_header_len, ground_sequence_number, ground_station_key)
            transmit_packet(tc_packet, ax25_header, True, False)

    elif button_label == 'GET_MODE':
        tc_data = array.array('B', [0x0D])
        tc_packet = spp_wrap('TC', tc_data, spp_header_len, ground_sequence_number, ground_station_key)
        transmit_packet(tc_packet, ax25_header, False, False)

    elif button_label == 'PING_RETURN':
        tc_packet = array.array('B', [])
        for k in oa_key:
            tc_packet.append(k)
        tc_packet.append(0x31)
        transmit_packet(tc_packet, ax25_header, False, True)

    elif button_label == 'RADIO_RESET':
        tc_packet = array.array('B', [])
        for k in oa_key:
            tc_packet.append(k)
        tc_packet.append(0x33)
        transmit_packet(tc_packet, ax25_header, False, True)

    elif button_label == 'PIN_TOGGLE':
        tc_packet = array.array('B', [])
        for k in oa_key:
            tc_packet.append(k)
        tc_packet.append(0x34)
        transmit_packet(tc_packet, ax25_header, False, True)

    else:
        print('Whoops, unrecognized button label:', button_label)


"""
Process Received Packets (thread)
"""


def process_received():
    global spp_header_len
    global expected_spacecraft_sequence_number
    global spacecraft_key
    global spacecraft_sequence_numbers
    global last_tc_packet
    global q_receive_packet
    global q_display_packet
    global COMMANDS
    global COMMANDS_R
    global health_payloads_pending
    global science_payloads_pending
    global tm_packet_window
    global transmit_timeout_count
    global ack_timeout
    global sequence_number_window
    global turnaround

    while True:
        ax25_packet = q_receive_packet.get()
        tm_packet = ax25_unwrap(ax25_packet)
        expected_spacecraft_sequence_number = expected_spacecraft_sequence_number + 1
        if expected_spacecraft_sequence_number > 65535:
            expected_spacecraft_sequence_number = 1
        validation_mask = validate_packet('TM', tm_packet, spp_header_len, expected_spacecraft_sequence_number,
                                          spacecraft_key)
        tm_data, gps_week, gpw_sow = spp_unwrap(tm_packet, spp_header_len)
        spacecraft_sequence_number = from_bigendian(tm_packet[(spp_header_len - 2):spp_header_len], 2)
        tm_command = tm_data[0]

        if tm_command == COMMAND_CODES['ACK']:
            last_tc_packet.clear()
        elif tm_command == COMMAND_CODES['NAK']:
            print('Received NAK')
        elif tm_command == COMMAND_CODES['XMIT_COUNT']:
            health_payloads_pending = from_bigendian(tm_data[1:3], 2)
            science_payloads_pending = from_bigendian(tm_data[3:5], 2)
            spacecraft_sequence_numbers.append(spacecraft_sequence_number)
            send_ack(spacecraft_sequence_numbers, spp_header_len)
            spacecraft_sequence_numbers = []
        elif tm_command == COMMAND_CODES['XMIT_HEALTH']:
            spacecraft_sequence_numbers.append(spacecraft_sequence_number)
            send_ack(spacecraft_sequence_numbers, spp_header_len)
            spacecraft_sequence_numbers = []
        elif tm_command == COMMAND_CODES['XMIT_SCIENCE']:
            spacecraft_sequence_numbers.append(spacecraft_sequence_number)
            send_ack(spacecraft_sequence_numbers, spp_header_len)
            spacecraft_sequence_numbers = []
        elif tm_command == COMMAND_CODES['READ_MEM']:
            spacecraft_sequence_numbers.append(spacecraft_sequence_number)
            send_ack(spacecraft_sequence_numbers, spp_header_len)
            spacecraft_sequence_numbers = []
        elif tm_command == COMMAND_CODES['GET_COMMS']:
            tm_packet_window = tm_data[1]
            transmit_timeout_count = tm_data[2]
            ack_timeout = tm_data[3]
            sequence_number_window = tm_data[4]
            turnaround = from_bigendian(tm_data[9:11], 2)
            spacecraft_sequence_numbers.append(spacecraft_sequence_number)
            send_ack(spacecraft_sequence_numbers, spp_header_len)
            spacecraft_sequence_numbers = []
        elif tm_command == COMMAND_CODES['GET_MODE']:
            spacecraft_mode = (tm_data[1])
            spacecraft_sequence_numbers.append(spacecraft_sequence_number)
            send_ack(spacecraft_sequence_numbers, spp_header_len)
            spacecraft_sequence_numbers = []
        else:
            pass


"""
Helpers
"""


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
    global filechooserwindow
    global filedialog_save
    global buffer_saved
    global buffer_filename
    time_utc = time.gmtime()
    time_string = time.strftime("ground%Y%m%d%H%M%S.json", time_utc)
    filechooserwindow.set_current_name(time_string)
    filechooserwindow.run()
    if filedialog_save:
        buffer_filename = filechooserwindow.get_filename()
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
    global oa_key
    global spp_header_len
    global textview
    global textview_buffer
    global first_packet
    global q_display_packet
    global COMMAND_NAMES
    global health_payload_length
    global science_payload_length
    global spacecraft_key
    global ground_station_key
    if not q_display_packet.empty():
        values_per_row = 8
        packet_type = 'UNKNOWN'
        sdlsp_key = ''
        ax25_packet = q_display_packet.get()
        is_spp_packet, is_oa_packet = is_libertas_packet('TM', ax25_packet, spp_header_len, oa_key)
        spp_packet = ax25_unwrap(ax25_packet)
        spp_data, gps_week, gps_sow = spp_unwrap(spp_packet, spp_header_len)
        if first_packet:
            textview_buffer.insert(textview_buffer.get_end_iter(), "{\n\"packets\" : [\n")
            first_packet = False
        else:
            textview_buffer.insert(textview_buffer.get_end_iter(), ",\n")
        textview_buffer.insert(textview_buffer.get_end_iter(), "{\n")

        tv_header = ('    "sender":"<SENDER>", ' +
                     '"packet_type":"<PACKET_TYPE>",\n')

        tv_spp = ('    "gps_week":"<GPS_WEEK>", ' +
                  '"gps_time":"<GPS_TIME>", ' +
                  '"sequence_number":"<SEQUENCE_NUMBER>",\n' +
                  '    "command":"<COMMAND>", ' +
                  '"<PACKET_TYPE>_data_length":"<SPP_DATA_LENGTH>",\n' +
                  '    "<PACKET_TYPE>_data":[\n<SPP_DATA>    ],\n' +
                  '    "mac_valid":"<MAC_VALID>",\n' +
                  '    "mac_digest":[\n<MAC_DIGEST>    ],\n')

        tv_ax25 = ('    "ax25_destination":"<AX25_DESTINATION>", ' +
                   '"ax25_source":"<AX25_SOURCE>", ' +
                   '"ax25_packet_length":"<AX25_PACKET_LENGTH>",\n' +
                   '    "ax25_packet":[\n<AX25_PACKET>    ]\n')

        if is_oa_packet:
            tv_header = tv_header.replace('<SENDER>', 'ground')
            tv_header = tv_header.replace('<PACKET_TYPE>', 'OA')
            if spp_packet[16] == 0x31:
                tv_header = tv_header.replace('<COMMAND>', 'PING_RETURN_COMMAND')
            elif spp_packet[16] == 0x33:
                tv_header = tv_header.replace('<COMMAND>', 'RADIO_RESET_COMMAND')
            elif spp_packet[16] == 0x34:
                tv_header = tv_header.replace('<COMMAND>', 'PIN_TOGGLE_COMMAND')
            else:
                tv_header = tv_header.replace('<COMMAND>', 'ILLEGAL OA COMMAND')
        elif spp_packet[0] == 0x08:
            packet_type = 'TM'
            tv_header = tv_header.replace('<SENDER>', 'spacecraft')
            tv_header = tv_header.replace('<PACKET_TYPE>', packet_type)
            tv_spp = tv_spp.replace('<SENDER>', 'spacecraft')
            tv_spp = tv_spp.replace('<PACKET_TYPE>', packet_type)
            sdlsp_key = spacecraft_key
        elif spp_packet[0] == 0x18:
            packet_type = 'TC'
            tv_header = tv_header.replace('<SENDER>', 'ground')
            tv_header = tv_header.replace('<PACKET_TYPE>', packet_type)
            tv_spp = tv_spp.replace('<SENDER>', 'ground')
            tv_spp = tv_spp.replace('<PACKET_TYPE>', packet_type)
            sdlsp_key = ground_station_key
        else:
            packet_type = 'UNKNOWN'
            tv_header = tv_header.replace('<SENDER>', 'spacecraft')
            tv_header = tv_header.replace('<PACKET_TYPE>', packet_type)
            sdlsp_key = ''

        textview_buffer.insert(textview_buffer.get_end_iter(), tv_header)

        if is_spp_packet:
            packet_sequence_number = from_bigendian(spp_packet[13:15], 2)
            validation_mask = validate_packet(packet_type, spp_packet, spp_header_len,
                                              packet_sequence_number, sdlsp_key)
            tv_spp = tv_spp.replace('<GPS_WEEK>', "{:d}".format(gps_week))
            tv_spp = tv_spp.replace('<GPS_TIME>', "{:14.7f}".format(gps_sow))
            tv_spp = tv_spp.replace('<SEQUENCE_NUMBER>',
                                    "{:05d}".format(
                                        int(from_bigendian(spp_packet[(spp_header_len - 2):spp_header_len], 2))))
            tv_spp = tv_spp.replace('<COMMAND>', COMMAND_NAMES[spp_data[0]])

            tv_spp = tv_spp.replace('<SPP_DATA_LENGTH>', "{:d}".format(len(spp_data)))
            packet_string = hex_tabulate(spp_data, values_per_row)
            tv_spp = tv_spp.replace('<SPP_DATA>', packet_string)

            if validation_mask == 0:
                tv_spp = tv_spp.replace('<MAC_VALID>', 'True')
            else:
                tv_spp = tv_spp.replace('<MAC_VALID>', 'False')
            packet_string = hex_tabulate(spp_packet[-32:], values_per_row)
            tv_spp = tv_spp.replace('<MAC_DIGEST>', packet_string)

            textview_buffer.insert(textview_buffer.get_end_iter(), tv_spp)

            if (spp_packet[0] == 0x08) and ((spp_data[0] == 0x02) or (spp_data[0] == 0x03)):
                for n in range(spp_data[1]):
                    payload_begin = 2 + (science_payload_length * n)
                    payload_end = payload_begin + science_payload_length
                    packet_string = payload_decode(spp_data[0], spp_data[payload_begin:payload_end], n)
                    textview_buffer.insert(textview_buffer.get_end_iter(), packet_string)

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
    global COMMAND_CODES
    science_payload_string = (
            '    "payload<PAYLOAD_NUMBER>":[\n'
            '        "payload_type":"SCIENCE",\n' +
            '        "latitude":"<LATITUDE>",\n' +
            '        "longitude":"<LONGITUDE>",\n' +
            '        "altitude":"<ALTITUDE>",\n' +
            '        "fix_quality":"<FIX_QUALITY>",\n' +
            '        "satellites_tracked":"<SATELLITES_TRACKED>",\n' +
            '        "hdop":"<HDOP>",\n' +
            '        "gps_time":"<GPS_TIME>",\n' +
            '        "gps_week":"<GPS_WEEK>",\n' +
            '        "x_pos":"<X_POS>",\n' +
            '        "y_pos":"<Y_POS>",\n' +
            '        "z_pos":"<Z_POS>",\n' +
            '        "x_vel":"<X_VEL>",\n' +
            '        "y_vel":"<Y_VEL>",\n' +
            '        "z_vel":"<Z_VEL>",\n' +
            '        "pdop":"<PDOP>",\n' +
            '        "satellites_pvt":"<SATELLITES_PVT>",\n' +
            '        "mx":"<MX>",\n' +
            '        "my":"<MY>",\n' +
            '        "mz":"<MZ>",\n' +
            '        "gx":"<GX>",\n' +
            '        "gy":"<GY>",\n' +
            '        "gz":"<GZ>",\n' +
            '        "sun_sensor_vi":"<SUN_SENSOR_VI>",\n' +
            '        "sun_sensor_i":"<SUN_SENSOR_I>",\n' +
            '        "sun_sensor_ii":"<SUN_SENSOR_II>",\n' +
            '        "sun_sensor_iii":"<SUN_SENSOR_III>",\n' +
            '        "sun_sensor_iv":"<SUN_SENSOR_IV>",\n' +
            '        "sun_sensor_v":"<SUN_SENSOR_V>"\n' +
            '    ],\n'
    )
    science_payload_fields = [
            ['<LATITUDE>', 'LATLON'],
            ['<LONGITUDE>', 'LATLON'],
            ['<ALTITUDE>', 'UINT32'],
            ['<FIX_QUALITY>', 'UINT8'],
            ['<SATELLITES_TRACKED>', 'UINT8'],
            ['<HDOP>', 'DOP'],
            ['<GPS_TIME>', 'GPSTIME'],
            ['<GPS_WEEK>', 'UINT16'],
            ['<X_POS>', 'UINT32'],
            ['<Y_POS>', 'UINT32'],
            ['<Z_POS>', 'UINT32'],
            ['<X_VEL>', 'UINT16'],
            ['<Y_VEL>', 'UINT16'],
            ['<Z_VEL>', 'UINT16'],
            ['<PDOP>', 'DOP'],
            ['<SATELLITES_PVT>', 'UINT8'],
            ['<MX>', 'UINT16'],
            ['<MY>', 'UINT16'],
            ['<MZ>', 'UINT16'],
            ['<GX>', 'UINT16'],
            ['<GY>', 'UINT16'],
            ['<GZ>', 'UINT16'],
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


def open_serial_device():
    global serial_device_name
    global rx_obj
    rx_obj = serial.Serial(serial_device_name, baudrate=4800)


def open_usrp_device():
    global rx_port
    global tx_port
    global rx_obj
    global tx_obj
    rx_obj = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    rx_obj.connect(('localhost', rx_port))
    tx_obj = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tx_obj.connect(('localhost', tx_port))


"""
Transmit and receive packets
"""


def transmit_packet(tc_packet, ax25_header, expect_ack, is_oa_packet):
    global use_serial
    global rx_obj
    global tx_obj
    global ground_sequence_number
    global last_tc_packet
    global q_display_packet
    time.sleep(float(turnaround) / 1000.0)
    ax25_packet = ax25_wrap('TC', tc_packet, ax25_header)
    if use_serial:
        lithium_packet = lithium_wrap(ax25_packet)
        rx_obj.write(lithium_packet)
    else:
        kiss_packet = kiss_wrap(ax25_packet)
        tx_obj.send(kiss_packet)
    if not is_oa_packet:
        last_sn = ground_sequence_number
        ground_sequence_number = ground_sequence_number + 1
        if ground_sequence_number > 65535:
            ground_sequence_number = 1
        if expect_ack:
            last_tc_packet.update({last_sn: tc_packet})
    q_display_packet.put(ax25_packet)


def send_ack(sequence_numbers, spp_header_len):
    global ground_sequence_number
    tc_data = array.array('B', [0x05])
    tc_data.append(len(sequence_numbers) & 0xFF)
    for s in sequence_numbers:
        tc_data.extend(to_bigendian(s, 2))
    tc_packet = spp_wrap('TC', tc_data, spp_header_len, ground_sequence_number, ground_station_key)
    transmit_packet(tc_packet, ax25_header, False, False)
    return (tc_packet)


def send_nak(sequence_numbers, spp_header_len):
    global ground_sequence_number
    tc_data = array.array('B', [0x06])
    tc_data.append(len(sequence_numbers) & 0xFF)
    for s in sequence_numbers:
        tc_data.extend(to_bigendian(s, 2))
    tc_packet = spp_wrap('TC', tc_data, spp_header_len, ground_sequence_number, ground_station_key)
    transmit_packet(tc_packet, ax25_header, False, False)
    return (tc_packet)


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
    global filechooserwindow
    global filechooser2window
    global combobox1
    global baudrates
    global radiobutton1
    global radiobutton2
    global buffer_saved
    global filedialog_save
    global entry_objs
    global label_objs
    global label11
    global ax25_destination
    global ax25_source
    global spp_header_len
    global ground_sequence_number
    global spacecraft_sequence_numbers
    global use_serial
    global serial_device_name
    global rx_port
    global tx_port
    global rx_obj
    global tx_obj
    global spacecraft_key
    global ground_station_key
    global oa_key
    global q_display_packet
    global receive_thread
    global p_receive_packet
    global q_receive_packet
    global process_thread
    global expected_spacecraft_sequence_number
    global health_payload_length
    global health_payloads_per_packet
    global health_payloads_pending
    global doing_health_payloads
    global science_payload_length
    global science_payloads_per_packet
    global science_payloads_pending
    global doing_science_payloads
    global tm_packet_window
    global transmit_timeout_count
    global ack_timeout
    global sequence_number_window
    global last_tc_packet
    global first_packet
    global COMMAND_NAMES
    global COMMAND_CODES
    global dst_callsign
    global src_callsign
    global ax25_header
    global turnaround

    COMMAND_NAMES = {
        0x05: 'ACK',
        0x06: 'NAK',
        0x7F: 'CEASE_XMIT',
        0x09: 'NOOP',
        0x04: 'RESET',
        0x01: 'XMIT_COUNT',
        0x02: 'XMIT_HEALTH',
        0x03: 'XMIT_SCIENCE',
        0x08: 'READ_MEM',
        0x07: 'WRITE_MEM',
        0x0B: 'SET_COMMS',
        0x0C: 'GET_COMMS',
        0x0A: 'SET_MODE',
        0x0D: 'GET_MODE',
        0x31: 'PING_RETURN',
        0x33: 'RADIO_RESET',
        0x34: 'PIN_TOGGLE'
    }
    COMMAND_CODES = {}
    for code, cmd in COMMAND_NAMES.items():
        COMMAND_CODES.update({cmd: code})
    serial_device_name = 'pty_libertas'
    buffer_saved = False
    filedialog_save = False
    first_packet = True
    rx_port = 9501
    tx_port = 9500
    dst_callsign = 'W4UVA '
    dst_ssid = 11
    src_callsign = 'W4UVA '
    src_ssid = 0

    my_packet_type = 0x18
    spp_header_len = 15
    ground_sequence_number = 1
    expected_spacecraft_sequence_number = 0
    spacecraft_sequence_numbers = []
    health_payload_length = 46
    health_payloads_per_packet = 4
    health_payloads_pending = 1
    doing_health_payloads = False
    science_payload_length = 83
    science_payloads_per_packet = 2
    science_payloads_pending = 1
    doing_science_payloads = False
    tm_packet_window = 1
    transmit_timeout_count = 4
    ack_timeout = 10
    sequence_number_window = 2
    last_tc_packet = {}
    baudrates = [9600, 19200, 38400, 76800, 115200]

    config = configparser.ConfigParser()
    config.read(['ground.ini'])
    debug = config['general'].getboolean('debug')
    program_name = config['general']['program_name']
    program_version = config['general']['program_version']
    use_serial = config['comms'].getboolean('use_serial')
    turnaround = float(config['comms']['turnaround']) / 1000.0
    spacecraft_key = config['comms']['spacecraft_key'].encode()
    ground_station_key = config['comms']['ground_station_key'].encode()
    oa_key = config['comms']['oa_key'].encode()

    if debug:
        logging.basicConfig(filename='ground.log', level=logging.DEBUG, format='%(asctime)s %(message)s')
    else:
        logging.basicConfig(filename='ground.log', level=logging.INFO, format='%(asctime)s %(message)s')
    logging.info('%s %s: Run started', program_name, program_version)

    ax25_header = init_ax25_header(dst_callsign, dst_ssid, src_callsign, src_ssid)

    if use_serial:
        open_serial_device()
    else:
        open_usrp_device()

    q_display_packet = mp.Queue()
    q_receive_packet = mp.Queue()

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
        builder.get_object("entry7")
    ]
    label_objs = [
        builder.get_object("label4"),
        builder.get_object("label5"),
        builder.get_object("label6"),
        builder.get_object("label7"),
        builder.get_object("label8"),
        builder.get_object("label9")
    ]
    label11 = builder.get_object("label11")
    combobox1 = builder.get_object("combobox1")
    combobox1.set_active(0)

    appwindow_title = ' '.join([program_name, program_version])
    appwindow.set_title(appwindow_title)
    appwindow.show_all()

    p_receive_packet = mp.Process(target=receive_packet, args=(my_packet_type, rx_obj, use_serial,
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
