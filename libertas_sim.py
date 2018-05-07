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

import hashlib
import hmac
import array
import time
import gpstime
import serial
import json
import random


"""
Helpers
"""

def gps_time():
    time_utc = time.gmtime(time.time())
    gps_tm = gpstime.gpsFromUTC(time_utc[0], time_utc[1], time_utc[2], time_utc[3], time_utc[4], time_utc[5])
    return(gps_tm[0], gps_tm[1])


def hmac_sign(packet, key):
    digest = hmac.new(key, msg=packet, digestmod=hashlib.sha256).digest()
    return(digest)


"""
Transmit and receive packets
"""

def transmit_serial(packet, sequence_number, serial_obj):
    lithium_packet = lithium_wrap(packet)
    serial_obj.write(lithium_packet)
    sequence_number += 1
    if sequence_number > 65535:
        sequence_number = 1
    return(sequence_number)


def receive_serial(serial_obj):
    serial_buffer = serial_obj.read(8)
    lithium_packet = array.array('B', [])
    for s in serial_buffer:
        lithium_packet.append(s)
    serial_buffer = serial_obj.read(lithium_packet[5] + 2)
    for s in serial_buffer:
        lithium_packet.append(s)
    packet = lithium_unwrap(lithium_packet)
    return(packet)


def send_ack(sequence_numbers, sequence_number, key, serial_obj):
    data = array.array('B', [0x05, 0x00])
    if sequence_numbers.buffer_info()[1] > 0:
        for s in sequence_numbers:
            data.append(s)
        data[1] = (sequence_numbers.buffer_info()[1] & 0xFF)
    packet = spp_wrap('TM', data, sequence_number, key)
    sequence_number = transmit_serial(packet, sequence_number, serial_obj)
    return(packet, sequence_number)


def send_nak(sequence_numbers, sequence_number, key, serial_obj):
    data = array.array('B', [0x06, 0x00])
    if sequence_numbers.buffer_info()[1] > 0:
        for s in sequence_numbers:
            data.append(s)
        data[1] = (sequence_numbers.buffer_info()[1] & 0xFF)
    packet = spp_wrap('TM', data, sequence_number, key)
    (last_tm_packet, sequence_number) = transmit_serial(packet, sequence_number, serial_obj)
    return(packet, sequence_number)


def transmit_health_packet(health, health_payload_length, health_payloads_pending, 
                            sequence_number, key, serial_obj):
    data = array.array('B', [0x02])
    payloads_this_packet = min(health_payloads_pending, 4)
    data.append((payloads_this_packet * health_payload_length) + 1)
    data.append(payloads_this_packet)
    for i in range(payloads_this_packet):
        for h in health:
            data.append(h)
    tm_packet = spp_wrap('TM', data, sequence_number, key)
    sequence_number = transmit_serial(tm_packet, sequence_number, serial_obj) 
    health_payloads_pending = max((health_payloads_pending - payloads_this_packet), 0)                     
    return(tm_packet, sequence_number, health_payloads_pending)


def transmit_science_packet(science, science_payload_length, science_payloads_pending, 
                            sequence_number, key, serial_obj):
    data = array.array('B', [0x03])
    payloads_this_packet = min(science_payloads_pending, 2)
    data.append((payloads_this_packet * science_payload_length) + 1)
    data.append(payloads_this_packet)
    for i in range(payloads_this_packet):
        for s in science:
            data.append(s)
    tm_packet = spp_wrap('TM', data, sequence_number, key)
    sequence_number = transmit_serial(tm_packet, sequence_number, serial_obj) 
    science_payloads_pending = max((science_payloads_pending - payloads_this_packet), 0)                     
    return(tm_packet, sequence_number, science_payloads_pending)


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


def lithium_wrap(packet):
    lithium_packet = array.array('B', [0x48, 0x65, 0x20, 0x04, 0x00, 0x00, 0x00, 0x00])
    for p in packet:
        lithium_packet.append(p)
    lithium_packet.append(0x00)
    lithium_packet.append(0x00)
    lithium_packet[5] = packet.buffer_info()[1]
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
    return(lithium_packet)


def lithium_unwrap(lithium_packet):
    packet = lithium_packet[8:-2]
    return(packet)


def validate_packet(packet_type, data, sequence_number, key):
    return(0)


"""
Main
"""

def main():
    
    """
    Commands
    """
    COMMAND_ACK = 0x05
    COMMAND_CEASE_TRANSMIT = 0x7F
    COMMAND_NOOP = 0x09
    COMMAND_TRANSMIT_NOOP = 0x0A
    COMMAND_RESET = 0x04
    COMMAND_TRANSMIT_COUNT = 0x01
    COMMAND_TRANSMIT_HEALTH = 0x02
    COMMAND_TRANSMIT_SCIENCE = 0x03
    COMMAND_READ_MEMORY = 0x08
    COMMAND_WRITE_MEMORY = 0x07
    COMMAND_SET_COMMS_PARAMS = 0x0B
    COMMAND_GET_COMMS_PARAMS = 0x0C
    
    program_name = 'Libertas Simulator'
    program_version = 'V1.0'
    serial_device_name = 'pty_ground'
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
    
    serial_obj = serial.Serial(serial_device_name, baudrate=4800)
    
    while True:
        tc_packet = receive_serial(serial_obj)
        ground_sequence_number += 1
        if ground_sequence_number > 65535:
            ground_sequence_number = 1
        validation_mask = validate_packet('TC', tc_packet, ground_sequence_number, ground_station_key)
        tc_data = spp_unwrap(tc_packet)
        tc_command = tc_data[0]
        sequence_numbers = array.array('B', tc_packet[21:23])

        if tc_command == COMMAND_ACK:
            if tc_data[1] == 0:
                last_tm_packet.clear()
            else:
                for i in range(2, (tc_data[1] + 1), 2):
                    packet_sn = ((tc_data[i] << 8) + tc_data[i+1])
                    del last_tm_packet[packet_sn]
                        
        elif tc_command == COMMAND_CEASE_TRANSMIT:
            print('Received Cease Transmit')
            last_sn = spacecraft_sequence_number
            (tm_packet, spacecraft_sequence_number) = send_ack(sequence_numbers, 
                spacecraft_sequence_number, spacecraft_key, serial_obj)
            exit()
                      
        elif tc_command == COMMAND_NOOP:
            print('Received NOOP')
            last_sn = spacecraft_sequence_number
            (tm_packet, spacecraft_sequence_number) = send_ack(sequence_numbers, 
                spacecraft_sequence_number, spacecraft_key, serial_obj)
                      
        elif tc_command == COMMAND_TRANSMIT_NOOP:
            print('Received Transmit NOOP')
            data = array.array('B', [0x0A, 0x00])
            tm_packet = spp_wrap('TM', data, spacecraft_sequence_number, spacecraft_key)
            last_sn = spacecraft_sequence_number
            spacecraft_sequence_number = transmit_serial(tm_packet, spacecraft_sequence_number, serial_obj)
            last_tm_packet.update({last_sn:last_tm_packet})
                      
        elif tc_command == COMMAND_RESET:
            print('Received Reset')
            last_sn = spacecraft_sequence_number
            (tm_packet, spacecraft_sequence_number) = send_ack(sequence_numbers, 
                spacecraft_sequence_number, spacecraft_key, serial_obj)
                      
        elif tc_command == COMMAND_TRANSMIT_COUNT:
            print('Received Transmit Count Pending Packets')
            data = array.array('B', [0x01, 0x04])
            data.append((health_payloads_pending & 0xFF00) >> 8)
            data.append(health_payloads_pending & 0xFF)
            data.append((science_payloads_pending & 0xFF00) >> 8)
            data.append(science_payloads_pending & 0xFF)
            tm_packet = spp_wrap('TM', data, spacecraft_sequence_number, spacecraft_key)
            last_sn = spacecraft_sequence_number
            spacecraft_sequence_number = transmit_serial(tm_packet, spacecraft_sequence_number, serial_obj)
            last_tm_packet.update({last_sn:last_tm_packet})
                      
        elif tc_command == COMMAND_TRANSMIT_HEALTH:
            print('Received Transmit Health Packets')
            last_sn = spacecraft_sequence_number
            (tm_packet, spacecraft_sequence_number, health_payloads_pending) = transmit_health_packet(health, 
                health_payload_length, health_payloads_pending, spacecraft_sequence_number, 
                spacecraft_key, serial_obj)
            last_tm_packet.update({last_sn:last_tm_packet})
        
        elif tc_command == COMMAND_TRANSMIT_SCIENCE:
            print('Received Transmit Science Packets')
            last_sn = spacecraft_sequence_number
            (tm_packet, spacecraft_sequence_number, science_payloads_pending) = transmit_science_packet(science, 
                science_payload_length, science_payloads_pending, spacecraft_sequence_number, 
                spacecraft_key, serial_obj)
            last_tm_packet.update({last_sn:last_tm_packet})
                      
        elif tc_command == COMMAND_READ_MEMORY:
            print('Received Read Memory')
            data = array.array('B', [0x08, 0x00])
            for d in tc_data[2:6]:
                data.append(d)
            number_of_locations = ((((tc_data[4] << 8) + tc_data[5]) - ((tc_data[2] << 8) + tc_data[3])) + 1)
            data[1] = (4 + (number_of_locations * 2))
            for i in range(number_of_locations):
                data.append(random.randint(0, 255))
                data.append(random.randint(0, 255))
            tm_packet = spp_wrap('TM', data, spacecraft_sequence_number, spacecraft_key)
            last_sn = spacecraft_sequence_number
            spacecraft_sequence_number = transmit_serial(tm_packet, spacecraft_sequence_number, serial_obj)
            last_tm_packet.update({last_sn:last_tm_packet})
                      
        elif tc_command == COMMAND_WRITE_MEMORY:
            print('Received Write Memory')
            last_sn = spacecraft_sequence_number
            (tm_packet, spacecraft_sequence_number) = send_ack(sequence_numbers, 
                spacecraft_sequence_number, spacecraft_key, serial_obj)

        elif tc_command == COMMAND_SET_COMMS_PARAMS:
            print('Received Set Comms Params')
            tm_packet_window = tc_data[2]
            transmit_timeout_count = tc_data[3]
            ack_timeout = tc_data[4]
            sequence_number_window = tc_data[5]
            spacecraft_sequence_number = ((tc_data[6] << 8) + tc_data[7])
            ground_sequence_number = ((tc_data[8] << 8) + tc_data[9])
            last_sn = spacecraft_sequence_number
            (tm_packet, spacecraft_sequence_number) = send_ack(sequence_numbers, 
                spacecraft_sequence_number, spacecraft_key, serial_obj)
                
        elif tc_command == COMMAND_GET_COMMS_PARAMS:
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
            tm_packet = spp_wrap('TM', data, spacecraft_sequence_number, spacecraft_key)
            last_sn = spacecraft_sequence_number
            spacecraft_sequence_number = transmit_serial(tm_packet, spacecraft_sequence_number, serial_obj)
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
                    spacecraft_sequence_number, spacecraft_key, serial_obj)
                last_tm_packet.update({last_sn:tm_packet})
        elif doing_science_payloads:
            if science_payloads_pending > 0:
                last_sn = spacecraft_sequence_number
                (tm_packet, spacecraft_sequence_number, science_payloads_pending) = transmit_science_packet(
                    science, science_payload_length, science_payloads_pending, 
                    spacecraft_sequence_number, spacecraft_key, serial_obj)
                last_tm_packet.update({last_sn:tm_packet})
        else:
            noop = 1
        
              

if __name__ == "__main__":
    # execute only if run as a script
    main()
