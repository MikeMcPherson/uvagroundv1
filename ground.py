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
from ground.ptools import is_valid_packet, init_ax25_header,spp_wrap,spp_unwrap,lithium_wrap,lithium_unwrap
from ground.ptools import ax25_wrap,ax25_unwrap,kiss_wrap,kiss_unwrap,ax25_callsign,validate_packet
import serial
import json
import queue
import threading
import pprint
import socket

program_name = 'UVa Libertas Ground Station'
program_version = 'V1.1'


"""
GUI Handlers
"""

class Handler:
    
    def on_destroy(self, *args):
        global textview_buffer
        textview_buffer.insert(textview_buffer.get_end_iter(), "]\n}\n")
        save_file()
        Gtk.main_quit()

    def on_command(self, button):
        button_label = button.get_label().replace('...','')
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

    def on_use_output(self,button):
        global use_serial
        global serial_obj
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
                serial_obj.close()
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

def on_command(button_label):
    global dialog1_xmit
    global oa_key
    global spp_header_len

    if button_label == 'CEASE_XMIT':
        tc_data = array.array('B', [0x7F, 0x00])
        tc_packet = spp_wrap('TC', tc_data, spp_header_len, ground_sequence_number, ground_station_key)
        transmit_packet(tc_packet, ax25_header, True, False)
                  
    elif button_label == 'NOOP':
        tc_data = array.array('B', [0x09, 0x00])
        tc_packet = spp_wrap('TC', tc_data, spp_header_len, ground_sequence_number, ground_station_key)
        transmit_packet(tc_packet, ax25_header, True, False)
                  
    elif button_label == 'RESET':
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
            tc_packet = spp_wrap('TC', tc_data, spp_header_len, ground_sequence_number, ground_station_key)
            transmit_packet(tc_packet, ax25_header, True, False)
                  
    elif button_label == 'XMIT_COUNT':
        tc_data = array.array('B', [0x01, 0x00])
        tc_packet = spp_wrap('TC', tc_data, spp_header_len, ground_sequence_number, ground_station_key)
        transmit_packet(tc_packet, ax25_header, False, False)
                  
    elif button_label == 'XMIT_HEALTH':
        title = '"Transmit Health" Arguments'
        labels = ['# Payloads', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A']
        defaults = ['0xFF', '0x00', '0x00', '0x00', '0x00', '0x00']
        tooltips = ['(8-bit) Number of Health Payloads to be downlinked.  0xFF means downlink all outstanding payloads.',
                    'N/A', 'N/A', 'N/A', 'N/A', 'N/A']
        args = dialog1_run(title, labels, defaults, tooltips)
        if dialog1_xmit:
            tc_data = array.array('B', [0x02, 0x01])
            tc_data.append(args[0] & 0x00FF)
            tc_packet = spp_wrap('TC', tc_data, spp_header_len, ground_sequence_number, ground_station_key)
            transmit_packet(tc_packet, ax25_header, False, False)
                  
    elif button_label == 'XMIT_SCIENCE':
        title = '"Transmit Science" Arguments'
        labels = ['# Payloads', 'N/A', 'N/A', 'N/A', 'N/A', 'N/A']
        defaults = ['0xFF', '0x00', '0x00', '0x00', '0x00', '0x00']
        tooltips = ['(8-bit) Number of Science Payloads to be downlinked.  0xFF means downlink all outstanding payloads.',
                    'N/A', 'N/A', 'N/A', 'N/A', 'N/A']
        args = dialog1_run(title, labels, defaults, tooltips)
        if dialog1_xmit:
            tc_data = array.array('B', [0x03, 0x01])
            tc_data.append(args[0] & 0x00FF)
            tc_packet = spp_wrap('TC', tc_data, spp_header_len, ground_sequence_number, ground_station_key)
            transmit_packet(tc_packet, ax25_header, False, False)
                  
    elif button_label == 'READ_MEM':
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
            tc_packet = spp_wrap('TC', tc_data, spp_header_len, ground_sequence_number, ground_station_key)
            transmit_packet(tc_packet, ax25_header, False, False)
                  
    elif button_label == 'WRITE_MEM':
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
            tc_packet = spp_wrap('TC', tc_data, spp_header_len, ground_sequence_number, ground_station_key)
            transmit_packet(tc_packet, ax25_header, True, False)
                  
    elif button_label == 'SET_COMMS':
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
            tc_packet = spp_wrap('TC', tc_data, spp_header_len, ground_sequence_number, ground_station_key)
            transmit_packet(tc_packet, ax25_header, True, False)
        
    elif button_label == 'GET_COMMS':
        tc_data = array.array('B', [0x0C, 0x00])
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
        validation_mask = validate_packet('TC', tm_packet, spp_header_len, spacecraft_sequence_number, 
                                            spacecraft_key)
        tm_data, gps_week, gpw_sow = spp_unwrap(tm_packet, spp_header_len)
        tm_command = tm_data[0]
        sequence_numbers = array.array('B', tm_packet[(spp_header_len - 2):spp_header_len])

        if tm_command == COMMAND_CODES['ACK']:
            if tm_data[1] == 0:
                last_tc_packet.clear()
            else:
                for i in range(2, (tm_data[1] + 1), 2):
                    packet_sn = ((tm_data[i] << 8) + tm_data[i+1])
                    del last_tc_packet[packet_sn]
        elif tm_command == COMMAND_CODES['NAK']:
            print('Received NAK')       
        elif tm_command == COMMAND_CODES['XMIT_COUNT']:
            if tm_data[1] == 0x04:
                health_payloads_pending = ((tm_data[2] << 8) + tm_data[3])
                science_payloads_pending = ((tm_data[4] << 8) + tm_data[5])
                send_ack(sequence_numbers, spp_header_len)
            else:
                print('Bad TM packet XMIT_COUNT')
        elif tm_command == COMMAND_CODES['XMIT_HEALTH']:
            send_ack(sequence_numbers, spp_header_len)
        elif tm_command == COMMAND_CODES['XMIT_SCIENCE']:
            send_ack(sequence_numbers, spp_header_len)
        elif tm_command == COMMAND_CODES['READ_MEM']:
            send_ack(sequence_numbers, spp_header_len)
        elif tm_command == COMMAND_CODES['GET_COMMS']:
            if tm_data[1] == 0x08:
                tm_packet_window = (tm_data[2])
                transmit_timeout_count = (tm_data[2])
                ack_timeout = (tm_data[2])
                sequence_number_window = (tm_data[2])
                send_ack(sequence_numbers, spp_header_len)
            else:
                print('Bad TM packet GET_COMMS')
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


"""
Display packet in scrolling window
"""

def display_packet():
    global oa_key
    global spp_header_len
    global textview
    global textview_buffer
    global first_packet
    global display_queue
    global COMMAND_NAMES
    if not display_queue.empty():
        ax25_packet = display_queue.get()
        is_spp_packet, is_oa_packet = is_valid_packet('TM', ax25_packet, spp_header_len, oa_key)
        spp_packet = ax25_unwrap(ax25_packet)
        spp_data, gps_week, gps_sow = spp_unwrap(spp_packet, spp_header_len)
        if first_packet:
            textview_buffer.insert(textview_buffer.get_end_iter(), "{\n\"packets\" : [\n")
            first_packet = False
        else:
            textview_buffer.insert(textview_buffer.get_end_iter(), ",\n")
        textview_buffer.insert(textview_buffer.get_end_iter(), "{\n")
        
        tv_header = ('    "sender":"<SENDER>",\n' + 
            '    "packet_type":"<PACKET_TYPE>",\n')

        tv_spp = ('    "gps_week":"<GPS_WEEK>",\n' + 
            '    "gps_time":"<GPS_TIME>",\n' + 
            '    "sequence_number":"<SEQUENCE_NUMBER>",\n' + 
            '    "command":"<COMMAND>",\n' + 
            '    "<PACKET_TYPE>_data_length":"<SPP_DATA_LENGTH>",\n' + 
            '    "<PACKET_TYPE>_data":[<SPP_DATA>],\n' + 
            '    "hmac_digest":[<HMAC_DIGEST>],\n')
                
        tv_ax25 = ('    "ax25_destination":"<AX25_DESTINATION>",\n' + 
            '    "ax25_source":"<AX25_SOURCE>",\n' + 
            '    "ax25_packet_length":"<AX25_PACKET_LENGTH>",\n' + 
            '    "ax25_packet":[<AX25_PACKET>]\n')
            
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
            tv_header = tv_header.replace('<SENDER>', 'spacecraft')    
            tv_header = tv_header.replace('<PACKET_TYPE>', 'TM')
            tv_spp = tv_spp.replace('<SENDER>', 'spacecraft')    
            tv_spp = tv_spp.replace('<PACKET_TYPE>', 'TM')
        elif spp_packet[0] == 0x18:
            tv_header = tv_header.replace('<SENDER>', 'ground')    
            tv_header = tv_header.replace('<PACKET_TYPE>', 'TC')
            tv_spp = tv_spp.replace('<SENDER>', 'ground')    
            tv_spp = tv_spp.replace('<PACKET_TYPE>', 'TC')
        else:
            tv_header = tv_header.replace('<SENDER>', 'spacecraft')    
            tv_header = tv_header.replace('<PACKET_TYPE>', 'UNKNOWN')
        
        textview_buffer.insert(textview_buffer.get_end_iter(), tv_header)
        
        if is_spp_packet:
            tv_spp = tv_spp.replace('<GPS_WEEK>', "{:d}".format(gps_week))
            tv_spp = tv_spp.replace('<GPS_TIME>', "{:14.7f}".format(gps_sow))
            tv_spp = tv_spp.replace('<SEQUENCE_NUMBER>', 
                "{:05d}".format(((int(spp_packet[(spp_header_len - 2)]) << 8) + 
                spp_packet[(spp_header_len - 1)])))
            tv_spp = tv_spp.replace('<COMMAND>', COMMAND_NAMES[spp_packet[spp_header_len]])
            
            tv_spp = tv_spp.replace('<SPP_DATA_LENGTH>', "{:d}".format(len(spp_data)))           
            packet_list = []
            for p in spp_data:
                packet_list.append("\"0x{:02X}\"".format(p))
            packet_string = ", ".join(map(str, packet_list))
            tv_spp = tv_spp.replace('<SPP_DATA>', packet_string)
            
            packet_list = []
            for p in spp_packet[-32:]:
                packet_list.append("\"0x{:02X}\"".format(p))
            packet_string = ", ".join(map(str, packet_list))
            tv_spp = tv_spp.replace('<HMAC_DIGEST>', packet_string)
            
            textview_buffer.insert(textview_buffer.get_end_iter(), tv_spp)
            
            packet_string = payload_decode(spp_data)
            textview_buffer.insert(textview_buffer.get_end_iter(), packet_string)

        tv_ax25 = tv_ax25.replace('<AX25_DESTINATION>', ax25_callsign(ax25_packet[0:7]))
        tv_ax25 = tv_ax25.replace('<AX25_SOURCE>', ax25_callsign(ax25_packet[7:14]))
        tv_ax25 = tv_ax25.replace('<AX25_PACKET_LENGTH>', "{:d}".format(len(ax25_packet)))
        
        packet_list = []
        for p in ax25_packet:
            packet_list.append("\"0x{:02X}\"".format(p))
        packet_string = ", ".join(map(str, packet_list))
        tv_ax25 = tv_ax25.replace('<AX25_PACKET>', packet_string)

        textview_buffer.insert(textview_buffer.get_end_iter(), tv_ax25)
            
        textview_buffer.insert(textview_buffer.get_end_iter(), "}\n")
        end_mark = textview_buffer.create_mark('END', textview_buffer.get_end_iter(), True)
        textview.scroll_mark_onscreen(end_mark)
    return(True)


def payload_decode(spp_data):
    global COMMAND_CODES
    command = spp_data[0]
    if command == COMMAND_CODES['XMIT_SCIENCE']:
        packet_string = ('    "latitude":"<LATITUDE>",\n' + 
            '    "latitude":"<LATITUDE>",\n' + 
            '    "latitude":"<LATITUDE>",\n' + 
            '    "latitude":"<LATITUDE>",\n' + 
            '    "latitude":"<LATITUDE>",\n' + 
            '    "latitude":"<LATITUDE>",\n' + 
            '    "latitude":"<LATITUDE>",\n' + 
            '    "latitude":"<LATITUDE>",\n' + 
            '    "latitude":"<LATITUDE>",\n' + 
            '    "latitude":"<LATITUDE>",\n')
    else:
        packet_string = ''
    return(packet_string)


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
    rx_obj.connect(('localhost', rx_port))
    tx_obj = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tx_obj.connect(('localhost', tx_port))


"""
Transmit and receive packets
"""

def transmit_packet(tc_packet, ax25_header, expect_ack, is_oa_packet):
    global use_serial
    global ground_sequence_number
    global last_tc_packet
    global display_queue
    ax25_packet = ax25_wrap('TC', tc_packet, ax25_header)
    if use_serial:
        lithium_packet = lithium_wrap(ax25_packet)
        transmit_serial(lithium_packet)
    else:
        kiss_packet = kiss_wrap(ax25_packet)
        transmit_usrp(kiss_packet)
    if not is_oa_packet:
        last_sn = ground_sequence_number
        ground_sequence_number += 1
        if ground_sequence_number > 65535:
            ground_sequence_number = 1
        if expect_ack:
            last_tc_packet.update({last_sn:tc_packet})
    display_queue.put(ax25_packet)


def transmit_serial(lithium_packet):
    global serial_obj
    serial_obj.write(lithium_packet)


def transmit_usrp(kiss_packet):
    global rx_obj
    global tx_obj
    tx_obj.send(kiss_packet)


def receive_packet():
    global use_serial
    global display_queue
    global process_queue
    global process_event
    while True:
        if use_serial:
            lithium_packet = receive_serial()
            ax25_packet = lithium_unwrap(lithium_packet)
        else:
            kiss_packet = receive_usrp()
            ax25_packet = kiss_unwrap(kiss_packet)
        tm_packet = ax25_unwrap(ax25_packet)
        if (len(tm_packet) > 0) and (tm_packet[0] != 0x18):
            display_queue.put(ax25_packet)
            process_queue.put(tm_packet)
            process_event.set()


def receive_serial():
    global serial_obj
    serial_buffer = serial_obj.read(8)
    lithium_packet = array.array('B', [])
    for s in serial_buffer:
        lithium_packet.append(s)
    serial_buffer = serial_obj.read(lithium_packet[5] + 2)
    for s in serial_buffer:
        lithium_packet.append(s)
    return(lithium_packet)


def receive_usrp():
    global rx_obj
    global tx_obj
    packet = rx_obj.recv(1024)
    return(packet)
    

def send_ack(sequence_numbers, spp_header_len):
    tc_data = array.array('B', [0x05, 0x00])
    if sequence_numbers.buffer_info()[1] > 0:
        for s in sequence_numbers:
            tc_data.append(s)
        tc_data[1] = (sequence_numbers.buffer_info()[1] & 0xFF)
    tc_packet = spp_wrap('TC', tc_data, spp_header_len, ground_sequence_number, ground_station_key)
    transmit_packet(tc_packet, ax25_header, False, False)
    return(tc_packet)


def send_nak(sequence_numbers, spp_header_len):
    tc_data = array.array('B', [0x06, 0x00])
    if sequence_numbers.buffer_info()[1] > 0:
        for s in sequence_numbers:
            tc_data.append(s)
        tc_data[1] = (sequence_numbers.buffer_info()[1] & 0xFF)
    tc_packet = spp_wrap('TC', tc_data, spp_header_len, ground_sequence_number, ground_station_key)
    transmit_packet(tc_packet, ax25_header, False, False)
    return(tc_packet)


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
                        0x7F : 'CEASE_XMIT',
                        0x09 : 'NOOP',
                        0x04 : 'RESET',
                        0x01 : 'XMIT_COUNT',
                        0x02 : 'XMIT_HEALTH',
                        0x03 : 'XMIT_SCIENCE',
                        0x08 : 'READ_MEM',
                        0x07 : 'WRITE_MEM',
                        0x0B : 'SET_COMMS',
                        0x0C : 'GET_COMMS',
                        0x0A : 'SET_MODE',
                        0x0D : 'GET_MODE'
                       }
    COMMAND_CODES = {}
    for code, cmd in COMMAND_NAMES.items():
        COMMAND_CODES.update({cmd : code})
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
    
    spp_header_len = 15
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
    
    config = configparser.ConfigParser()
    config.read(['ground.ini'])
    debug = config['general'].getboolean('debug')
    use_serial = config['comms'].getboolean('use_serial')
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
    
    receive_thread = threading.Thread(name='receive_packet', target=receive_packet, daemon=True)
    receive_thread.start()
    process_thread = threading.Thread(name='process_received', target=process_received, daemon=True)
    process_thread.start()
    
    GObject.threads_init()
    GObject.timeout_add(200, display_packet)
    Gtk.main()


if __name__ == "__main__":
    # execute only if run as a script
    main()
