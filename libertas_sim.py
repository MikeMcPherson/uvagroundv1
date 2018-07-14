#!/usr/bin/python3

"""
Libertas Simulator V1.0
Simple communications simulator for the UVa Libertas spacecraft.

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

import array
from ground.ptools import init_ax25_header,spp_wrap,spp_unwrap,lithium_wrap,lithium_unwrap
from ground.ptools import ax25_wrap,ax25_unwrap,kiss_wrap,kiss_unwrap,ax25_callsign,validate_packet
import ground.gpstime
import serial
import json
import random
import socket
import hexdump


"""
Transmit and receive packets
"""

def transmit_packet(packet, ax25_header, sequence_number, tx_obj, use_serial):
    ax25_packet = ax25_wrap(packet, ax25_header)
    if use_serial:
        lithium_packet = lithium_wrap(ax25_packet)
        tx_obj.write(lithium_packet)
    else:
        kiss_packet = kiss_wrap(ax25_packet)
        tx_obj.send(kiss_packet)
    sequence_number += 1
    if sequence_number > 65535:
        sequence_number = 1
    return(sequence_number)


def receive_packet(rx_obj, use_serial, oa_key):
    if use_serial:
        serial_buffer = rx_obj.read(8)
        lithium_packet = array.array('B', [])
        for s in serial_buffer:
            lithium_packet.append(s)
        serial_buffer = rx_obj.read(lithium_packet[5] + 2)
        for s in serial_buffer:
            lithium_packet.append(s)
        ax25_packet = lithium_unwrap(lithium_packet)
    else:
        kiss_string = rx_obj.recv(1024)
        kiss_packet = array.array('B', [])
        for c in kiss_string:
            kiss_packet.append(c)
        ax25_packet = kiss_unwrap(kiss_packet)
    packet = ax25_unwrap(ax25_packet)
    oa_packet = False
    if len(packet) == 17:
        oa_packet = True
        for idx, c in enumerate(oa_key):
            if c != packet[idx]:
                oa_packet = False
    return(packet, oa_packet)


def send_ack(sequence_numbers, sequence_number, ax25_header, spp_header_len, key, tx_obj, use_serial):
    data = array.array('B', [0x05, 0x00])
    if sequence_numbers.buffer_info()[1] > 0:
        for s in sequence_numbers:
            data.append(s)
        data[1] = (sequence_numbers.buffer_info()[1] & 0xFF)
    tm_packet = spp_wrap('TM', data, spp_header_len, sequence_number, key)
    sequence_number = transmit_packet(tm_packet, ax25_header, sequence_number, tx_obj, use_serial)
    return(tm_packet, sequence_number)


def send_nak(sequence_numbers, sequence_number, ax25_header, spp_header_len, key, tx_obj, use_serial):
    data = array.array('B', [0x06, 0x00])
    if sequence_numbers.buffer_info()[1] > 0:
        for s in sequence_numbers:
            data.append(s)
        data[1] = (sequence_numbers.buffer_info()[1] & 0xFF)
    tm_packet = spp_wrap('TM', data, spp_header_len, sequence_number, key)
    (last_tm_packet, sequence_number) = transmit_packet(tm_packet, ax25_header, sequence_number, 
                                                        tx_obj, use_serial)
    return(tm_packet, sequence_number)


def transmit_health_packet(health, health_payload_length, health_payloads_pending, 
                            sequence_number, ax25_header, spp_header_len, key, tx_obj, use_serial):
    data = array.array('B', [0x02])
    payloads_this_packet = min(health_payloads_pending, 4)
    data.append((payloads_this_packet * health_payload_length) + 1)
    data.append(payloads_this_packet)
    for i in range(payloads_this_packet):
        for h in health:
            data.append(h)
    tm_packet = spp_wrap('TM', data, spp_header_len, sequence_number, key)
    sequence_number = transmit_packet(tm_packet, ax25_header, sequence_number, tx_obj, use_serial) 
    health_payloads_pending = max((health_payloads_pending - payloads_this_packet), 0)                     
    return(tm_packet, sequence_number, health_payloads_pending)


def transmit_science_packet(science, science_payload_length, science_payloads_pending, 
                            sequence_number, ax25_header, spp_header_len, key, tx_obj, use_serial):
    data = array.array('B', [0x03])
    payloads_this_packet = min(science_payloads_pending, 2)
    data.append((payloads_this_packet * science_payload_length) + 1)
    data.append(payloads_this_packet)
    for i in range(payloads_this_packet):
        for s in science:
            data.append(s)
    tm_packet = spp_wrap('TM', data, spp_header_len, sequence_number, key)
    sequence_number = transmit_packet(tm_packet, ax25_header, sequence_number, tx_obj, use_serial) 
    science_payloads_pending = max((science_payloads_pending - payloads_this_packet), 0)                     
    return(tm_packet, sequence_number, science_payloads_pending)


"""
Main
"""

def main():
    
    """
    Commands
    """
    COMMAND_ACK = 0x05
    COMMAND_CEASE_XMIT = 0x7F
    COMMAND_NOOP = 0x09
    COMMAND_RESET = 0x04
    COMMAND_XMIT_COUNT = 0x01
    COMMAND_XMIT_HEALTH = 0x02
    COMMAND_XMIT_SCIENCE = 0x03
    COMMAND_READ_MEM = 0x08
    COMMAND_WRITE_MEM = 0x07
    COMMAND_SET_COMMS = 0x0B
    COMMAND_GET_COMMS = 0x0C
    
    program_name = 'Libertas Simulator'
    program_version = 'V1.0'
    serial_device_name = 'pty_ground'
    spp_header_len = 15
    spacecraft_sequence_number = 1
    ground_sequence_number = 0
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
    last_tm_packet = {}
    use_serial = False
    rx_port = 9501
    tx_port = 9500
    dst_callsign = 'W4UVA '
    dst_ssid = 0
    src_callsign = 'W4UVA '
    src_ssid = 11
    
    print(program_name, ' ', program_version)
    
    health = array.array('B', [])
    for i in range(health_payload_length):
        health.append(random.randint(0, 255))
    science = array.array('B', [])
    for i in range(science_payload_length):
        science.append(random.randint(0, 255))
    
    key_fp = open('/shared/keys/libertas_hmac_secret_keys.json', "r")
    json_return = json.load(key_fp)
    key_fp.close()
    spacecraft_key = json_return['libertas_key'].encode()
    ground_station_key = json_return['ground_station_key'].encode()
    oa_key = json_return['oa_key'].encode()
    oa_packet = False
    
    ax25_header = init_ax25_header(dst_callsign, dst_ssid, src_callsign, src_ssid)
    
    if use_serial:
        rx_obj = serial.Serial(serial_device_name, baudrate=9600)
        tx_obj = rx_obj
    else:
        rx_obj = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        rx_obj.connect(('gs-s-2.w4uva.org', rx_port))
        tx_obj = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tx_obj.connect(('gs-s-2.w4uva.org', tx_port))
    
    while True:
        (tc_packet, oa_packet) = receive_packet(rx_obj, use_serial, oa_key)
        validation_mask = validate_packet('TC', tc_packet, spp_header_len, ground_sequence_number, ground_station_key)
        if validation_mask != 0:
            spacecraft_sequence_number = send_nak(sequence_numbers, sequence_number, ax25_header, 
                                                    spp_header_len, spacecraft_key, tx_obj, use_serial)
            break
        if not oa_packet:
            ground_sequence_number = ground_sequence_number + 1
            if ground_sequence_number > 65535:
                ground_sequence_number = 1
            tc_data, gps_week, gps_sow = spp_unwrap(tc_packet, spp_header_len)
            tc_command = tc_data[0]
            sequence_numbers = array.array('B', tc_packet[(spp_header_len - 2):spp_header_len])
        if oa_packet:
            if tc_packet[16] == 0x31:
                print("Libertas received OA PING_RETURN_COMMAND")
            elif tc_packet[16] == 0x33:
                print("Libertas received OA RADIO_RESET_COMMAND")
            elif tc_packet[16] == 0x34:
                print("Libertas received OA PIN_TOGGLE_COMMAND")
            else:
                print("Libertas received OA invalid command")
        elif tc_packet[0] == 0x08:
            print("Libertas received my own packet")
        elif tc_command == COMMAND_ACK:
            if tc_data[1] == 0:
                last_tm_packet.clear()
            else:
                for i in range(2, (tc_data[1] + 1), 2):
                    packet_sn = ((tc_data[i] << 8) + tc_data[i+1])
                    del last_tm_packet[packet_sn]
                        
        elif tc_command == COMMAND_CEASE_XMIT:
            print('Received Cease Transmit')
            last_sn = spacecraft_sequence_number
            (tm_packet, spacecraft_sequence_number) = send_ack(sequence_numbers, 
                spacecraft_sequence_number, ax25_header, spp_header_len, spacecraft_key, tx_obj, use_serial)
            exit()
                      
        elif tc_command == COMMAND_NOOP:
            print('Received NOOP')
            last_sn = spacecraft_sequence_number
            (tm_packet, spacecraft_sequence_number) = send_ack(sequence_numbers, 
                spacecraft_sequence_number, ax25_header, spp_header_len, spacecraft_key, tx_obj, use_serial)
         
        elif tc_command == COMMAND_RESET:
            print('Received Reset')
            last_sn = spacecraft_sequence_number
            (tm_packet, spacecraft_sequence_number) = send_ack(sequence_numbers, 
                spacecraft_sequence_number, ax25_header, spp_header_len, spacecraft_key, tx_obj, use_serial)
                      
        elif tc_command == COMMAND_XMIT_COUNT:
            print('Received Transmit Count Pending Packets')
            data = array.array('B', [0x01, 0x04])
            data.append((health_payloads_pending & 0xFF00) >> 8)
            data.append(health_payloads_pending & 0xFF)
            data.append((science_payloads_pending & 0xFF00) >> 8)
            data.append(science_payloads_pending & 0xFF)
            tm_packet = spp_wrap('TM', data, spp_header_len, spacecraft_sequence_number, spacecraft_key)
            last_sn = spacecraft_sequence_number
            spacecraft_sequence_number = transmit_packet(tm_packet, ax25_header, spacecraft_sequence_number, 
                                                            tx_obj, use_serial)
            last_tm_packet.update({last_sn:last_tm_packet})
                      
        elif tc_command == COMMAND_XMIT_HEALTH:
            print('Received Transmit Health Packets')
            last_sn = spacecraft_sequence_number
            (tm_packet, spacecraft_sequence_number, health_payloads_pending) = transmit_health_packet(health, 
                health_payload_length, health_payloads_pending, spacecraft_sequence_number, ax25_header, spp_header_len, 
                spacecraft_key, tx_obj, use_serial)
            last_tm_packet.update({last_sn:last_tm_packet})
        
        elif tc_command == COMMAND_XMIT_SCIENCE:
            print('Received Transmit Science Packets')
            last_sn = spacecraft_sequence_number
            (tm_packet, spacecraft_sequence_number, science_payloads_pending) = transmit_science_packet(science, 
                science_payload_length, science_payloads_pending, spacecraft_sequence_number, ax25_header, spp_header_len, 
                spacecraft_key, tx_obj, use_serial)
            last_tm_packet.update({last_sn:last_tm_packet})
                      
        elif tc_command == COMMAND_READ_MEM:
            print('Received Read Memory')
            data = array.array('B', [0x08, 0x00])
            for d in tc_data[2:6]:
                data.append(d)
            number_of_locations = ((((tc_data[4] << 8) + tc_data[5]) - ((tc_data[2] << 8) + tc_data[3])) + 1)
            data[1] = (4 + (number_of_locations * 2))
            for i in range(number_of_locations):
                data.append(random.randint(0, 255))
                data.append(random.randint(0, 255))
            tm_packet = spp_wrap('TM', data, spp_header_len, spacecraft_sequence_number, spacecraft_key)
            last_sn = spacecraft_sequence_number
            spacecraft_sequence_number = transmit_packet(tm_packet, ax25_header, spacecraft_sequence_number, 
                                                            tx_obj, use_serial)
            last_tm_packet.update({last_sn:last_tm_packet})
                      
        elif tc_command == COMMAND_WRITE_MEM:
            print('Received Write Memory')
            last_sn = spacecraft_sequence_number
            (tm_packet, spacecraft_sequence_number) = send_ack(sequence_numbers, 
                spacecraft_sequence_number, ax25_header, spp_header_len, spacecraft_key, tx_obj, use_serial)

        elif tc_command == COMMAND_SET_COMMS:
            print('Received Set Comms Params')
            tm_packet_window = tc_data[2]
            transmit_timeout_count = tc_data[3]
            ack_timeout = tc_data[4]
            sequence_number_window = tc_data[5]
            spacecraft_sequence_number = ((tc_data[6] << 8) + tc_data[7])
            ground_sequence_number = ((tc_data[8] << 8) + tc_data[9])
            last_sn = spacecraft_sequence_number
            (tm_packet, spacecraft_sequence_number) = send_ack(sequence_numbers, 
                spacecraft_sequence_number, ax25_header, spp_header_len, spacecraft_key, tx_obj, use_serial)
                
        elif tc_command == COMMAND_GET_COMMS:
            print('Received Get Comms Params')
            data = array.array('B', [0x0C, 0x08])
            data.append(tm_packet_window)
            data.append(transmit_timeout_count)
            data.append(ack_timeout)
            data.append(sequence_number_window)
            data.append(((spacecraft_sequence_number + 1) & 0xFF00) >> 8)
            data.append((spacecraft_sequence_number + 1) & 0xFF)
            data.append((ground_sequence_number & 0xFF00) >> 8)
            data.append(ground_sequence_number & 0xFF)
            tm_packet = spp_wrap('TM', data, spp_header_len, spacecraft_sequence_number, spacecraft_key)
            last_sn = spacecraft_sequence_number
            spacecraft_sequence_number = transmit_packet(tm_packet, ax25_header, spacecraft_sequence_number, 
                                                            tx_obj, use_serial)
            last_tm_packet.update({last_sn:last_tm_packet})
        
        else:
            print('Unknown tc_command received')
            print(tc_data)
            print(tc_packet)
            
        if doing_health_payloads:
            if health_payloads_pending > 0:
                last_sn = spacecraft_sequence_number
                (tm_packet, spacecraft_sequence_number, health_payloads_pending) = transmit_health_packet(
                    health, health_payload_length, health_payloads_pending, 
                    spacecraft_sequence_number, ax25_header, spp_header_len, spacecraft_key, tx_obj, use_serial)
                last_tm_packet.update({last_sn:tm_packet})
        elif doing_science_payloads:
            if science_payloads_pending > 0:
                last_sn = spacecraft_sequence_number
                (tm_packet, spacecraft_sequence_number, science_payloads_pending) = transmit_science_packet(
                    science, science_payload_length, science_payloads_pending, 
                    spacecraft_sequence_number, ax25_header, spp_header_len, spacecraft_key, tx_obj, use_serial)
                last_tm_packet.update({last_sn:tm_packet})
        else:
            noop = 1
        
              

if __name__ == "__main__":
    # execute only if run as a script
    main()
