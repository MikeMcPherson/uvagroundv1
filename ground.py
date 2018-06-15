#!/usr/bin/python3

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

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from gi.repository import GObject
import hashlib
import hmac
import array
import time
import gpstime
import serial
import json
import queue
import threading
import pprint
import socket

program_name = 'UVa Libertas Ground Station'
program_version = '1.1'


"""
GUI Handlers
"""

class Handler:
    
    def on_destroy(self, *args):
        global textview_buffer
        textview_buffer.insert(textview_buffer.get_end_iter(), "]\n}\n")
        save_file()
        Gtk.main_quit()

    def on_cease_xmit(self, button):
        cease_xmit()

    def on_noop(self, button):
        noop()

    def on_xmit_noop(self, button):
        xmit_noop()

    def on_reset(self, button):
        reset()

    def on_xmit_count(self, button):
        xmit_count()

    def on_xmit_health(self, button):
        xmit_health()

    def on_xmit_science(self, button):
        xmit_science()

    def on_read_mem(self, button):
        read_mem()

    def on_write_mem(self, button):
        write_mem()

    def on_set_comms(self, button):
        set_comms()

    def on_get_comms(self, button):
        get_comms()

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
                
    def on_use_usrp_output(self, button):
        global use_serial
        global serial_obj
        global rx_port
        global tx_port
        global rx_obj
        global tx_obj
        use_serial = False
        try:
            serial_obj.close()
        except:
            pass
        open_usrp_device()
        
        
    def on_use_serial_output(self, button):
        global use_serial
        global rx_obj
        global tx_obj
        global serial_obj
        global serial_device_name
        use_serial = True
        try:
            rx_obj.close()
            tx_obj.close()
        except:
            pass
        open_serial_device()
        
        
    def on_filechooserdialog2_cancel(self, button):
        global filechooser2window
        filechooser2window.hide()
                
    def on_filechooserdialog2_open(self, button):
        global filechooser2window
        filechooser2window.hide()
    
    def on_combobox1_changed(self, button):
        global baudrates
        global serial_obj
        serial_obj.baudrate = baudrates[button.get_active()]
                
    def validate_entry_uint16(self,entry):
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

def cease_xmit():
    tc_data = array.array('B', [0x7F, 0x00])
    tc_packet = spp_wrap('TC', tc_data, ground_sequence_number, ground_station_key)
    transmit_packet(tc_packet, True)
              

def noop():
    tc_data = array.array('B', [0x09, 0x00])
    tc_packet = spp_wrap('TC', tc_data, ground_sequence_number, ground_station_key)
    transmit_packet(tc_packet, True)
              

def xmit_noop():
    tc_data = array.array('B', [0x0A, 0x00])
    tc_packet = spp_wrap('TC', tc_data, ground_sequence_number, ground_station_key)
    transmit_packet(tc_packet, False)
              

def reset():
    global dialog1_xmit
    title = '"Reset" Arguments'
    labels = ['Reset mask', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A']
    defaults = ['0x0000', '0x0000', '0x0000', '0x0000', '0x0000', '0x0000']
    tooltips = ['(16-bit) Bitmask indicating which spacecraft reset operations are to be performed.',
                'N/A', 'N/A', 'N/A', 'N/A', 'N/A']
    args = dialog1_run(title, labels, defaults, tooltips)
    if dialog1_xmit:
        tc_data = array.array('B', [0x04, 0x02])
        tc_data.append((args[0] & 0xFF00) >> 8)
        tc_data.append(args[0] & 0x00FF)
        tc_packet = spp_wrap('TC', tc_data, ground_sequence_number, ground_station_key)
        transmit_packet(tc_packet, True)
              

def xmit_count():
    tc_data = array.array('B', [0x01, 0x00])
    tc_packet = spp_wrap('TC', tc_data, ground_sequence_number, ground_station_key)
    transmit_packet(tc_packet, False)
              

def xmit_health():
    global dialog1_xmit
    title = '"Transmit Health" Arguments'
    labels = ['# Payloads', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A']
    defaults = ['0xFF', '0x00', '0x00', '0x00', '0x00', '0x00']
    tooltips = ['(8-bit) Number of Health Payloads to be downlinked.  0xFF means downlink all outstanding payloads.',
                'N/A', 'N/A', 'N/A', 'N/A', 'N/A']
    args = dialog1_run(title, labels, defaults, tooltips)
    if dialog1_xmit:
        tc_data = array.array('B', [0x02, 0x01])
        tc_data.append(args[0] & 0x00FF)
        tc_packet = spp_wrap('TC', tc_data, ground_sequence_number, ground_station_key)
        transmit_packet(tc_packet, False)
              

def xmit_science():
    global dialog1_xmit
    title = '"Transmit Science" Arguments'
    labels = ['# Payloads', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A']
    defaults = ['0xFF', '0x00', '0x00', '0x00', '0x00', '0x00']
    tooltips = ['(8-bit) Number of Science Payloads to be downlinked.  0xFF means downlink all outstanding payloads.',
                'N/A', 'N/A', 'N/A', 'N/A', 'N/A']
    args = dialog1_run(title, labels, defaults, tooltips)
    if dialog1_xmit:
        tc_data = array.array('B', [0x03, 0x01])
        tc_data.append(args[0] & 0x00FF)
        tc_packet = spp_wrap('TC', tc_data, ground_sequence_number, ground_station_key)
        transmit_packet(tc_packet, False)
              

def read_mem():
    global dialog1_xmit
    title = '"Read Memory" Arguments'
    labels = ['Start address', 'End address', 'N/A', 'N/A', 'N/A', 'N/A']
    defaults = ['0x00F0', '0x00F3', '0x0000', '0x0000', '0x0000', '0x0000']
    tooltips = ['(16-bit) Start of memory address range to downlink.',
                '(16-bit) End of memory address range to downlink.', 
                'N/A', 'N/A', 'N/A', 'N/A']
    args = dialog1_run(title, labels, defaults, tooltips)
    if dialog1_xmit:
        tc_data = array.array('B', [0x08, 0x02])
        tc_data.append((args[0] & 0xFF00) >> 8)
        tc_data.append(args[0] & 0x00FF)
        tc_data.append((args[1] & 0xFF00) >> 8)
        tc_data.append(args[1] & 0x00FF)
        tc_packet = spp_wrap('TC', tc_data, ground_sequence_number, ground_station_key)
        transmit_packet(tc_packet, False)
              

def write_mem():
    global dialog1_xmit
    title = '"Write Memory" Arguments'
    labels = ['Start address', 'End address', 
                'Contents 0', 'Contents 1', 'Contents 2', 'Contents 3']
    defaults = ['0x00F0', '0x00F3', '0x0000', '0x0000', '0x0000', '0x0000']
    tooltips = ['(16-bit) Start of memory address range to uplink.',
                '(16-bit) End of memory address range to uplink.  (Limited to four memory locations for testing.)',
                '(16-bit) Memory contents', '(16-bit) Memory contents', 
                '(16-bit) Memory contents', '(16-bit) Memory contents']
    args = dialog1_run(title, labels, defaults, tooltips)
    if dialog1_xmit:
        tc_data = array.array('B', [0x07, 0x0C])
        for a in args:
            tc_data.append((a & 0xFF00) >> 8)
            tc_data.append(a & 0x00FF)
        tc_packet = spp_wrap('TC', tc_data, ground_sequence_number, ground_station_key)
        transmit_packet(tc_packet, True)
              

def set_comms():
    global dialog1_xmit
    title = '"Set Params" Arguments'
    labels = ['TM Window', 'XMIT Timeout', 
                'ACK Timeout', 'Sequence Window', 'Spacecraft Sequence', 'GS Sequence']
    defaults = ['0x01', '0x04', '0x0A', '0x02', '0x0000', '0x0000']
    tooltips = ['(8-bit) Number of Health or Science packets the spacecraft will transmit '
                + 'before waiting for an ACK.  Default: 0x01.',
                '(8-bit) Number of unacknowledged transmit windows before the spacecraft ' 
                + 'ceases transmission.  Default: 0x04.', 
                '(8-bit) Number of seconds the spacecraft waits for an ACK or NAK ' 
                + 'before retransmitting the last window.  Default: 0x0A.', 
                '(8-bit) Maximum allowable difference between the expected and received ' 
                + 'Sequence Number.  Default: 0x02.', 
                '(16-bit) The next packet from the spacecraft should have this Sequence Number.', 
                '(16-bit) The spacecraft should expect the next packet from the ground station ' 
                + 'to have this Sequence Number.']
    args = dialog1_run(title, labels, defaults, tooltips)
    if dialog1_xmit:
        tc_data = array.array('B', [0x0B, 0x08])
        for a in args[0:4]:
            tc_data.append(a & 0x00FF)
        for a in args[4:]:
            tc_data.append((a & 0xFF00) >> 8)
            tc_data.append(a & 0x00FF)
        tc_packet = spp_wrap('TC', tc_data, ground_sequence_number, ground_station_key)
        transmit_packet(tc_packet, True)
    
    
def get_comms():
    tc_data = array.array('B', [0x0C, 0x00])
    tc_packet = spp_wrap('TC', tc_data, ground_sequence_number, ground_station_key)
    transmit_packet(tc_packet, False)
              

"""
Process Received Packets (thread)
"""

def process_received():
    global spacecraft_sequence_number
    global spacecraft_key
    global sequence_numbers
    global last_tc_packet
    global process_queue
    global process_event
    global COMMANDS
    global COMMANDS_R
    global health_payloads_pending
    global science_payloads_pending
    global tm_packet_window
    global transmit_timeout_count
    global ack_timeout
    global sequence_number_window
    
    while True:
        process_event.wait()
        tm_packet = process_queue.get()
        process_event.clear()
        spacecraft_sequence_number += 1
        if spacecraft_sequence_number > 65535:
            spacecraft_sequence_number = 1
        validation_mask = validate_packet('TC', tm_packet, spacecraft_sequence_number, spacecraft_key)
        tm_data = spp_unwrap(tm_packet)
        tm_command = tm_data[0]
        sequence_numbers = array.array('B', tm_packet[21:23])

        if tm_command == COMMAND_CODES['ACK']:
            if tm_data[1] == 0:
                last_tc_packet.clear()
            else:
                for i in range(2, (tm_data[1] + 1), 2):
                    packet_sn = ((tm_data[i] << 8) + tm_data[i+1])
                    del last_tc_packet[packet_sn]
        elif tm_command == COMMAND_CODES['NAK']:
            print('Received NAK')       
        elif tm_command == COMMAND_CODES['TRANSMIT_COUNT']:
            if tm_data[1] == 0x04:
                health_payloads_pending = ((tm_data[2] << 8) + tm_data[3])
                science_payloads_pending = ((tm_data[4] << 8) + tm_data[5])
                send_ack(sequence_numbers)
            else:
                print('Bad TM packet TRANSMIT_COUNT')
        elif tm_command == COMMAND_CODES['TRANSMIT_HEALTH']:
            send_ack(sequence_numbers)
        elif tm_command == COMMAND_CODES['TRANSMIT_SCIENCE']:
            send_ack(sequence_numbers)
        elif tm_command == COMMAND_CODES['READ_MEMORY']:
            send_ack(sequence_numbers)
        elif tm_command == COMMAND_CODES['TRANSMIT_NOOP']:
            send_ack(sequence_numbers)
        elif tm_command == COMMAND_CODES['GET_COMMS_PARAMS']:
            if tm_data[1] == 0x08:
                tm_packet_window = (tm_data[2])
                transmit_timeout_count = (tm_data[2])
                ack_timeout = (tm_data[2])
                sequence_number_window = (tm_data[2])
                send_ack(sequence_numbers)
            else:
                print('Bad TM packet GET_COMMS_PARAMS')
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


def display_packet():
    global textview
    global textview_buffer
    global first_packet
    global display_queue
    global COMMAND_NAMES
    if display_queue.empty():
        pass
    else:
        packet = display_queue.get()
        if first_packet:
            textview_buffer.insert(textview_buffer.get_end_iter(), "{\n\"packets\" : [\n")
            first_packet = False
        else:
            textview_buffer.insert(textview_buffer.get_end_iter(), ",\n")
        textview_buffer.insert(textview_buffer.get_end_iter(), "{\n")
        
        if (packet[0] & 0b00010000) == 0:
            textview_buffer.insert(textview_buffer.get_end_iter(), "    \"sender\":\"spacecraft\",\n")    
            textview_buffer.insert(textview_buffer.get_end_iter(), "    \"packet_type\":\"TM\",\n")
        else:
            textview_buffer.insert(textview_buffer.get_end_iter(), "    \"sender\":\"ground\",\n")    
            textview_buffer.insert(textview_buffer.get_end_iter(), "    \"packet_type\":\"TC\",\n")
        
        textview_buffer.insert(textview_buffer.get_end_iter(), "    \"packet_data_length\":\"")
        textview_buffer.insert(textview_buffer.get_end_iter(), 
            "0x{:04X}".format(((int(packet[1]) << 8) + packet[2])))
        textview_buffer.insert(textview_buffer.get_end_iter(), "\",\n")
        
        textview_buffer.insert(textview_buffer.get_end_iter(), "    \"gps_week\":\"")
        textview_buffer.insert(textview_buffer.get_end_iter(), "".join(map(chr, packet[3:7])))
        textview_buffer.insert(textview_buffer.get_end_iter(), "\",\n")
        
        textview_buffer.insert(textview_buffer.get_end_iter(), "    \"gps_time\":\"")
        textview_buffer.insert(textview_buffer.get_end_iter(), "".join(map(chr, packet[7:21])))
        textview_buffer.insert(textview_buffer.get_end_iter(), "\",\n")
        
        textview_buffer.insert(textview_buffer.get_end_iter(), "    \"sequence_number\":\"")
        textview_buffer.insert(textview_buffer.get_end_iter(), 
            "0x{:04X}".format(((int(packet[21]) << 8) + packet[22])))
        textview_buffer.insert(textview_buffer.get_end_iter(), "\",\n")
        
        textview_buffer.insert(textview_buffer.get_end_iter(), "    \"command\":\"")
        textview_buffer.insert(textview_buffer.get_end_iter(), COMMAND_NAMES[packet[23]])
        textview_buffer.insert(textview_buffer.get_end_iter(), "\",\n")
        
        packet_list = []
        for p in packet[23:-32]:
            packet_list.append("\"0x{:02X}\"".format(p))
        packet_string = ", ".join(map(str, packet_list))
        if (packet[0] & 0b00010000) == 0:
            textview_buffer.insert(textview_buffer.get_end_iter(), "    \"tm_data\":[")
        else:
            textview_buffer.insert(textview_buffer.get_end_iter(), "    \"tc_data\":[")
        textview_buffer.insert(textview_buffer.get_end_iter(), packet_string)
        textview_buffer.insert(textview_buffer.get_end_iter(), "],\n")
        
        packet_list = []
        for p in packet[-32:]:
            packet_list.append("\"0x{:02X}\"".format(p))
        packet_string = ", ".join(map(str, packet_list))
        textview_buffer.insert(textview_buffer.get_end_iter(), "    \"hmac_digest\":[")
        textview_buffer.insert(textview_buffer.get_end_iter(), packet_string)
        textview_buffer.insert(textview_buffer.get_end_iter(), "]\n")
        
        textview_buffer.insert(textview_buffer.get_end_iter(), "}\n")
        end_mark = textview_buffer.create_mark('END', textview_buffer.get_end_iter(), True)
        textview.scroll_mark_onscreen(end_mark)
    return(True)


def gps_time():
    time_utc = time.gmtime()
    gps_tm = gpstime.gpsFromUTC(time_utc[0], time_utc[1], time_utc[2], time_utc[3], time_utc[4], time_utc[5])
    return(gps_tm[0], gps_tm[1])


def hmac_sign(packet, key):
    digest = hmac.new(key, msg=packet, digestmod=hashlib.sha256).digest()
    return(digest)
    
    
def open_serial_device():
    global serial_device_name
    global serial_obj
    serial_obj = serial.Serial(serial_device_name, baudrate=4800)


def open_usrp_device():
    global rx_port
    global tx_port
    global rx_obj
    global tx_obj
    rx_obj = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    rx_obj.bind(('localhost', rx_port))
    tx_obj = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tx_obj.bind(('localhost', tx_port))


"""
Transmit and receive packets
"""

def transmit_packet(tc_packet, expect_ack):
    global use_serial
    global ground_sequence_number
    global last_tc_packet
    global display_queue
    if use_serial:
        transmit_serial(tc_packet)
    last_sn = ground_sequence_number
    ground_sequence_number += 1
    if ground_sequence_number > 65535:
        ground_sequence_number = 1
    if expect_ack:
        last_tc_packet.update({last_sn:tc_packet})
    display_queue.put(tc_packet)


def transmit_serial(tc_packet):
    global serial_obj
    lithium_packet = lithium_wrap(tc_packet)
    serial_obj.write(lithium_packet)


def receive_serial():
    global serial_obj
    global display_queue
    global process_queue
    global process_event
    while True:
        serial_buffer = serial_obj.read(8)
        lithium_packet = array.array('B', [])
        for s in serial_buffer:
            lithium_packet.append(s)
        serial_buffer = serial_obj.read(lithium_packet[5] + 2)
        for s in serial_buffer:
            lithium_packet.append(s)
        tm_packet = lithium_unwrap(lithium_packet)
        display_queue.put(tm_packet)
        process_queue.put(tm_packet)
        process_event.set()


def send_ack(sequence_numbers):
    tc_data = array.array('B', [0x05, 0x00])
    if sequence_numbers.buffer_info()[1] > 0:
        for s in sequence_numbers:
            tc_data.append(s)
        tc_data[1] = (sequence_numbers.buffer_info()[1] & 0xFF)
    tc_packet = spp_wrap('TC', tc_data, ground_sequence_number, ground_station_key)
    transmit_packet(tc_packet, False)
    return(tc_packet)


def send_nak(sequence_numbers):
    tc_data = array.array('B', [0x06, 0x00])
    if sequence_numbers.buffer_info()[1] > 0:
        for s in sequence_numbers:
            tc_data.append(s)
        tc_data[1] = (sequence_numbers.buffer_info()[1] & 0xFF)
    tc_packet = spp_wrap('TC', tc_data, ground_sequence_number, ground_station_key)
    transmit_packet(tc_packet, False)
    return(tc_packet)


"""
Wrap, unwrap, and verify packets
"""

def spp_wrap(packet_type, data, sequence_number, key):
    if packet_type == 'TM':
        packet = array.array('B', [0x08, 0x00, 0x00])
    else:
        packet = array.array('B', [0x18, 0x00, 0x00])
    gps_tm = gps_time()
    gps_week = "{:04d}".format(gps_tm[0])
    gps_sow = "{:014.7f}".format(gps_tm[1])
    for c in gps_week:
        packet.append(ord(c))
    for c in gps_sow:
        packet.append(ord(c))
    packet.append((sequence_number & 0xFF00) >> 8)
    packet.append(sequence_number & 0x00FF)
    for d in data:
        packet.append(d)
    digest = hmac_sign(packet[21:], key)
    for d in digest:
        packet.append(d)
    packet_info = packet.buffer_info()
    packet[2] = packet_info[1]
    return(packet)


def spp_unwrap(packet):
    data = packet[23:-32]
    return(data)


def lithium_wrap(tc_packet):
    lithium_packet = array.array('B', [0x48, 0x65, 0x20, 0x04, 0x00, 0x00, 0x00, 0x00])
    for p in tc_packet:
        lithium_packet.append(p)
    lithium_packet.append(0x00)
    lithium_packet.append(0x00)
    lithium_packet[5] = tc_packet.buffer_info()[1]
    ck_a = 0
    ck_b = 0
    for p in lithium_packet[2:6]:
        ck_a = ck_a + p
        ck_b = ck_b + ck_a
    lithium_packet[6] = ck_a & 0xFF
    lithium_packet[7] = ck_b & 0xFF
    ck_a = 0
    ck_b = 0
    for p in lithium_packet[2:-2]:
        ck_a = ck_a + p
        ck_b = ck_b + ck_a
    lithium_packet[-2] = ck_a & 0xFF
    lithium_packet[-1] = ck_b & 0xFF
    return lithium_packet


def lithium_unwrap(lithium_packet):
    tm_packet = lithium_packet[8:-2]
    return(tm_packet)


def ax25_wrap(packet):
    global ax25_header
    ax25_packet = ax25_header
    for p in packet:
        ax25_packet.append(p)
    return(ax25_packet)


def ax25_unwrap(ax25_packet):
    packet = ax25_packet[16:]
    return(packet)
    
    
def kiss_unwrap(kiss_packet):
    


def validate_packet(packet_type, data, sequence_number, key):
    return(0)


"""
Main
"""

def main():
    global builder
    global textview
    global textview2
    global textview_buffer
    global textview2_buffer
    global output_serial
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
    global ground_sequence_number
    global use_serial
    global serial_device_name
    global serial_obj
    global rx_port
    global tx_port
    global rx_obj
    global tx_obj
    global spacecraft_key
    global ground_station_key
    global oa_key
    global display_queue
    global receive_thread
    global process_queue
    global process_thread
    global process_event
    global spacecraft_sequence_number
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

    COMMAND_NAMES = {
                        0x05 : 'ACK',
                        0x06 : 'NAK',
                        0x7F : 'CEASE_TRANSMIT',
                        0x09 : 'NOOP',
                        0x0A : 'TRANSMIT_NOOP',
                        0x04 : 'RESET',
                        0x01 : 'TRANSMIT_COUNT',
                        0x02 : 'TRANSMIT_HEALTH',
                        0x03 : 'TRANSMIT_SCIENCE',
                        0x08 : 'READ_MEMORY',
                        0x07 : 'WRITE_MEMORY',
                        0x0B : 'SET_COMMS_PARAMS',
                        0x0C : 'GET_COMMS_PARAMS'
                        }
    COMMAND_CODES = {}
    for code, cmd in COMMAND_NAMES.items():
        COMMAND_CODES.update({cmd : code})
    use_serial = False
    serial_device_name = 'pty_libertas'
    output_serial = True
    buffer_saved = False
    filedialog_save = False
    first_packet = True
    rx_port = 9501
    tx_port = 9500
    dst_callsign = 'W4UVA '
    src_callsign = 'W4UVA '
    
    ground_sequence_number = 1
    spacecraft_sequence_number = 0
    health_payload_length = 46
    health_payloads_per_packet = 4
    health_payloads_pending = 1
    doing_health_payloads = False
    science_payload_length = 76
    science_payloads_per_packet = 2
    science_payloads_pending = 1
    doing_science_payloads = False
    tm_packet_window = 1
    transmit_timeout_count = 4
    ack_timeout = 10
    sequence_number_window = 2
    last_tc_packet = {}
    baudrates = [9600, 19200, 38400, 76800, 115200]
    
    ax25_header = array.array('B', [])
    for c in dst_callsign:
        ax25_header.append(ord(c) << 1)
    ax25_header.append(0)
    for c in src_callsign:
        ax25_header.append(ord(c) << 1)
    ax25_header.append(0)
    ax25_header.append(0x03)
    ax25_header.append(0xF0)
    print(ax25_header)
    
    key_fp = open('/shared/keys/libertas_hmac_secret_keys.json', "r")
    json_return = json.load(key_fp)
    key_fp.close()
    spacecraft_key = json_return['libertas_key'].encode()
    ground_station_key = json_return['ground_station_key'].encode()
    oa_key = json_return['oa_key'].encode()
    
    if use_serial:
        open_serial_device()
    else:
        open_usrp_device()
    
    display_queue = queue.Queue()
    process_queue = queue.Queue()
    process_event = threading.Event()
    
    builder = Gtk.Builder()
    builder.add_from_file("ground.glade")
    builder.connect_signals(Handler())    
    appwindow = builder.get_object("applicationwindow1")
    textview = builder.get_object("textview1")
    textview_buffer = textview.get_buffer()
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
    
    appwindow.show_all()
    
    receive_thread = threading.Thread(name='receive_serial', target=receive_serial, daemon=True)
    receive_thread.start()
    process_thread = threading.Thread(name='process_received', target=process_received, daemon=True)
    process_thread.start()
    
    GObject.threads_init()
    GObject.timeout_add(200, display_packet)
    Gtk.main()


if __name__ == "__main__":
    # execute only if run as a script
    main()
