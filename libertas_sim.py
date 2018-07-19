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

import configparser
import logging
import array
import time
from ground.packet_functions import receive_packet, to_bigendian, from_bigendian, to_fake_float, from_fake_float
from ground.packet_functions import is_libertas_packet, init_ax25_header, spp_wrap, spp_unwrap
from ground.packet_functions import lithium_wrap, lithium_unwrap
from ground.packet_functions import ax25_wrap, ax25_unwrap, kiss_wrap, kiss_unwrap, ax25_callsign, validate_packet
import serial
import random
import socket
import multiprocessing as mp
from inspect import currentframe

"""
Transmit and receive packets
"""


def transmit_packet(packet, ax25_header, sequence_number, tx_obj, use_serial, turnaround):
    time.sleep(float(turnaround) / 1000.0)
    ax25_packet = ax25_wrap('TM', packet, ax25_header)
    if use_serial:
        lithium_packet = lithium_wrap(ax25_packet)
        tx_obj.write(lithium_packet)
    else:
        kiss_packet = kiss_wrap(ax25_packet)
        tx_obj.send(kiss_packet)
    sequence_number = sequence_number + 1
    if sequence_number > 65535:
        sequence_number = 1
    return sequence_number


def send_ack(ground_sequence_numbers, sequence_number, ax25_header, spp_header_len, key, tx_obj, use_serial, turnaround):
    data = array.array('B', [0x05])
    tm_packet = spp_wrap('TM', data, spp_header_len, sequence_number, key)
    sequence_number = transmit_packet(tm_packet, ax25_header, sequence_number, tx_obj, use_serial, turnaround)
    return tm_packet, sequence_number


def send_nak(ground_sequence_numbers, sequence_number, ax25_header, spp_header_len, key, tx_obj, use_serial, turnaround):
    data = array.array('B', [0x06])
    tm_packet = spp_wrap('TM', data, spp_header_len, sequence_number, key)
    sequence_number = transmit_packet(tm_packet, ax25_header, sequence_number, tx_obj, use_serial, turnaround)
    return (tm_packet, sequence_number)


def transmit_health_packet(q_health_payloads, health_payload_length, health_payloads_pending,
                           sequence_number, ax25_header, spp_header_len, key, tx_obj, use_serial, turnaround):
    data = array.array('B', [0x02])
    payloads_this_packet = min(health_payloads_pending, 4)
    data.append(payloads_this_packet)
    for i in range(payloads_this_packet):
        health_payload = q_health_payloads.get()
        for h in health_payload:
            data.append(h)
    for i in range(payloads_this_packet, 4):
        data.extend([0x00] * health_payload_length)
    tm_packet = spp_wrap('TM', data, spp_header_len, sequence_number, key)
    sequence_number = transmit_packet(tm_packet, ax25_header, sequence_number, tx_obj, use_serial, turnaround)
    health_payloads_pending = max((health_payloads_pending - payloads_this_packet), 0)
    return (tm_packet, sequence_number, health_payloads_pending)


def transmit_science_packet(q_science_payloads, science_payload_length, science_payloads_pending,
                            sequence_number, ax25_header, spp_header_len, key, tx_obj, use_serial, turnaround):
    data = array.array('B', [0x03])
    payloads_this_packet = min(science_payloads_pending, 2)
    data.append(payloads_this_packet)
    for i in range(payloads_this_packet):
        science_payload = q_science_payloads.get()
        for s in science_payload:
            data.append(s)
    for i in range(payloads_this_packet, 2):
        data.extend([0x00] * science_payload_length)
    tm_packet = spp_wrap('TM', data, spp_header_len, sequence_number, key)
    sequence_number = transmit_packet(tm_packet, ax25_header, sequence_number, tx_obj, use_serial, turnaround)
    science_payloads_pending = max((science_payloads_pending - payloads_this_packet), 0)
    return (tm_packet, sequence_number, science_payloads_pending)


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
    COMMAND_SET_MODE = 0x0A
    COMMAND_GET_MODE = 0x0D

    program_name = 'Libertas Simulator'
    program_version = 'V1.1'
    my_packet_type = 0x08
    serial_device_name = 'pty_ground'
    spp_header_len = 15
    spacecraft_sequence_number = 1
    expected_ground_sequence_number = 0
    ground_sequence_numbers = []
    health_payload_length = 46
    health_payloads_per_packet = 4
    doing_health_payloads = False
    science_payload_length = 83
    science_payloads_per_packet = 2
    doing_science_payloads = False
    tm_packet_window = 1
    transmit_timeout_count = 4
    ack_timeout = 10
    sequence_number_window = 2
    spacecraft_mode = 1
    last_tm_packet = {}
    rx_port = 9501
    tx_port = 9500
    dst_callsign = 'W4UVA '
    dst_ssid = 0
    src_callsign = 'W4UVA '
    src_ssid = 11

    cf = currentframe()
    config = configparser.ConfigParser()
    config.read(['ground.ini'])
    debug = config['libertas_sim'].getboolean('debug')
    program_name = config['libertas_sim']['program_name']
    program_version = config['libertas_sim']['program_version']
    use_serial = config['comms'].getboolean('use_serial')
    turnaround = int(config['comms']['turnaround'])
    spacecraft_key = config['comms']['spacecraft_key'].encode()
    ground_station_key = config['comms']['ground_station_key'].encode()
    oa_key = config['comms']['oa_key'].encode()

    if debug:
        logging.basicConfig(filename='ground.log', level=logging.DEBUG, format='%(asctime)s %(message)s')
    else:
        logging.basicConfig(filename='ground.log', level=logging.INFO, format='%(asctime)s %(message)s')
    logging.info('%s %s: Run started', program_name, program_version)

    q_health_payloads = mp.Queue()
    q_science_payloads = mp.Queue()

    health_payloads_pending = 11
    for p in range(health_payloads_pending):
        health_payload = array.array('B', [])
        for i in range(health_payload_length):
            health_payload.append(random.randint(0, 255))
        q_health_payloads.put(health_payload)

    science_payloads_pending = 11
    for p in range(science_payloads_pending):
        science_payload = array.array('B', [])
        for i in range(science_payload_length):
            science_payload.append(random.randint(0, 255))
        q_science_payloads.put(science_payload)

    ax25_header = init_ax25_header(dst_callsign, dst_ssid, src_callsign, src_ssid)

    if use_serial:
        rx_obj = serial.Serial(serial_device_name, baudrate=9600)
        tx_obj = rx_obj
    else:
        rx_obj = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        rx_obj.connect(('gs-s-2.w4uva.org', rx_port))
        tx_obj = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tx_obj.connect(('gs-s-2.w4uva.org', tx_port))

    q_receive_packet = mp.Queue()
    q_display_packet = mp.Queue()
    p_receive_packet = mp.Process(target=receive_packet, args=(my_packet_type, rx_obj, use_serial,
                                                               q_receive_packet, q_display_packet))
    p_receive_packet.start()

    while True:
        ax25_packet = q_receive_packet.get()
        is_spp_packet, is_oa_packet = is_libertas_packet('TC', ax25_packet, spp_header_len, oa_key)
        tc_packet = ax25_unwrap(ax25_packet)
        if is_oa_packet:
            tc_command = tc_packet[16]
            if tc_command == 0x31:
                print("Libertas received OA PING_RETURN_COMMAND")
            elif tc_command == 0x33:
                print("Libertas received OA RADIO_RESET_COMMAND")
            elif tc_command == 0x34:
                print("Libertas received OA PIN_TOGGLE_COMMAND")
            else:
                print('Libertas: unrecognized OA command')
        else:
            expected_ground_sequence_number = expected_ground_sequence_number + 1
            if expected_ground_sequence_number > 65535:
                expected_ground_sequence_number = 1
            ground_sequence_numbers.append(from_bigendian(tc_packet[(spp_header_len - 2):spp_header_len], 2))
            validation_mask = validate_packet('TC', tc_packet, spp_header_len, expected_ground_sequence_number,
                                              ground_station_key)
            if validation_mask != 0:
                print('Libertas: failed HMAC check')
                spacecraft_sequence_number = send_nak(ground_sequence_numbers, spacecraft_sequence_number, ax25_header,
                                                      spp_header_len, spacecraft_key, tx_obj, use_serial, turnaround)
                break
            tc_data, gps_week, gps_sow = spp_unwrap(tc_packet, spp_header_len)
            tc_command = tc_data[0]
            if tc_command == COMMAND_ACK:
                print('Received ACK')
                if tc_data[1] == 0:
                    last_tm_packet.clear()
                    ground_sequence_numbers = []
                else:
                    for i in range(tc_data[1]):
                        ack_sn = from_bigendian(tc_data[(i * 2) + 2:(i * 2) + 4], 2)
                        del last_tm_packet[ack_sn]
                        ground_sequence_numbers.remove(ack_sn)

            elif tc_command == COMMAND_CEASE_XMIT:
                print('Received CEASE_XMIT')
                last_sn = spacecraft_sequence_number
                (tm_packet, spacecraft_sequence_number) = send_ack(ground_sequence_numbers,
                                                                   spacecraft_sequence_number, ax25_header, spp_header_len,
                                                                   spacecraft_key, tx_obj, use_serial, turnaround)
                p_receive_packet.terminate()
                rx_obj.close()
                tx_obj.close()
                logging.info('%s %s: Run ended', program_name, program_version)
                exit()

            elif tc_command == COMMAND_NOOP:
                print('Received NOOP')
                last_sn = spacecraft_sequence_number
                (tm_packet, spacecraft_sequence_number) = send_ack(ground_sequence_numbers,
                                                                   spacecraft_sequence_number, ax25_header, spp_header_len,
                                                                   spacecraft_key, tx_obj, use_serial, turnaround)

            elif tc_command == COMMAND_RESET:
                print('Received RESET')
                last_sn = spacecraft_sequence_number
                (tm_packet, spacecraft_sequence_number) = send_ack(ground_sequence_numbers,
                                                                   spacecraft_sequence_number, ax25_header, spp_header_len,
                                                                   spacecraft_key, tx_obj, use_serial, turnaround)

            elif tc_command == COMMAND_XMIT_COUNT:
                print('Received XMIT_COUNT')
                tm_data = array.array('B', [0x01])
                tm_data.extend(to_bigendian(health_payloads_pending, 2))
                tm_data.extend(to_bigendian(science_payloads_pending, 2))
                tm_packet = spp_wrap('TM', tm_data, spp_header_len, spacecraft_sequence_number, spacecraft_key)
                last_sn = spacecraft_sequence_number
                spacecraft_sequence_number = transmit_packet(tm_packet, ax25_header, spacecraft_sequence_number,
                                                             tx_obj, use_serial, turnaround)
                last_tm_packet.update({last_sn: last_tm_packet})

            elif tc_command == COMMAND_XMIT_HEALTH:
                print('Received XMIT_HEALTH')
                doing_health_payloads = False
                downlink_health_payloads = tc_data[1]
                last_sn = spacecraft_sequence_number
                (tm_packet, spacecraft_sequence_number, health_payloads_pending) = transmit_health_packet(
                    q_health_payloads, health_payload_length, health_payloads_pending,
                    spacecraft_sequence_number, ax25_header, spp_header_len,
                    spacecraft_key, tx_obj, use_serial, turnaround)
                if health_payloads_pending > 0:
                    doing_health_payloads = True
                last_tm_packet.update({last_sn: last_tm_packet})

            elif tc_command == COMMAND_XMIT_SCIENCE:
                print('Received XMIT_SCIENCE')
                doing_science_payloads = False
                downlink_science_payloads = tc_data[1]
                last_sn = spacecraft_sequence_number
                (tm_packet, spacecraft_sequence_number, science_payloads_pending) = transmit_science_packet(
                    q_science_payloads, science_payload_length, science_payloads_pending,
                    spacecraft_sequence_number, ax25_header, spp_header_len,
                    spacecraft_key, tx_obj, use_serial, turnaround)
                if science_payloads_pending > 0:
                    doing_science_payloads = True
                last_tm_packet.update({last_sn: last_tm_packet})

            elif tc_command == COMMAND_READ_MEM:
                print('Received READ_MEM')
                tm_data = array.array('B', [0x08])
                for d in tc_data[1:5]:
                    tm_data.append(d)
                number_of_locations = ((from_bigendian(tc_data[3:5], 2) - from_bigendian(tc_data[1:3], 2)) + 1)
                for i in range(number_of_locations):
                    tm_data.append(random.randint(0, 255))
                    tm_data.append(random.randint(0, 255))
                tm_packet = spp_wrap('TM', tm_data, spp_header_len, spacecraft_sequence_number, spacecraft_key)
                last_sn = spacecraft_sequence_number
                spacecraft_sequence_number = transmit_packet(tm_packet, ax25_header, spacecraft_sequence_number,
                                                             tx_obj, use_serial, turnaround)
                last_tm_packet.update({last_sn: last_tm_packet})

            elif tc_command == COMMAND_WRITE_MEM:
                print('Received WRITE_MEM')
                last_sn = spacecraft_sequence_number
                (tm_packet, spacecraft_sequence_number) = send_ack(ground_sequence_numbers,
                                                                   spacecraft_sequence_number, ax25_header, spp_header_len,
                                                                   spacecraft_key, tx_obj, use_serial, turnaround)

            elif tc_command == COMMAND_SET_COMMS:
                print('Received SET_COMMS')
                tm_packet_window = tc_data[1]
                transmit_timeout_count = tc_data[2]
                ack_timeout = tc_data[3]
                sequence_number_window = tc_data[4]
                spacecraft_sequence_number = from_bigendian(tc_data[5:7], 2)
                expected_ground_sequence_number = from_bigendian(tc_data[7:9], 2)
                turnaround = from_bigendian(tc_data[9:11], 2)
                last_sn = spacecraft_sequence_number
                (tm_packet, spacecraft_sequence_number) = send_ack(ground_sequence_numbers,
                                                                   spacecraft_sequence_number, ax25_header, spp_header_len,
                                                                   spacecraft_key, tx_obj, use_serial, turnaround)

            elif tc_command == COMMAND_GET_COMMS:
                print('Received GET_COMMS')
                tm_data = array.array('B', [0x0C])
                tm_data.append(tm_packet_window & 0xFF)
                tm_data.append(transmit_timeout_count & 0xFF)
                tm_data.append(ack_timeout & 0xFF)
                tm_data.append(sequence_number_window & 0xFF)
                tm_data.extend(to_bigendian((spacecraft_sequence_number + 1), 2))
                tm_data.extend(to_bigendian(expected_ground_sequence_number, 2))
                tm_data.extend(to_bigendian(turnaround, 2))
                tm_packet = spp_wrap('TM', tm_data, spp_header_len, spacecraft_sequence_number, spacecraft_key)
                last_sn = spacecraft_sequence_number
                spacecraft_sequence_number = transmit_packet(tm_packet, ax25_header, spacecraft_sequence_number,
                                                             tx_obj, use_serial, turnaround)
                last_tm_packet.update({last_sn: last_tm_packet})

            elif tc_command == COMMAND_SET_MODE:
                print('Received SET_MODE')
                spacecraft_mode = tc_data[1]
                last_sn = spacecraft_sequence_number
                (tm_packet, spacecraft_sequence_number) = send_ack(ground_sequence_numbers,
                                                                   spacecraft_sequence_number, ax25_header, spp_header_len,
                                                                   spacecraft_key, tx_obj, use_serial, turnaround)

            elif tc_command == COMMAND_GET_MODE:
                print('Received GET_MODE')
                tm_data = array.array('B', [0x0D])
                tm_data.append(spacecraft_mode & 0xFF)
                tm_packet = spp_wrap('TM', tm_data, spp_header_len, spacecraft_sequence_number, spacecraft_key)
                last_sn = spacecraft_sequence_number
                spacecraft_sequence_number = transmit_packet(tm_packet, ax25_header, spacecraft_sequence_number,
                                                             tx_obj, use_serial, turnaround)
                last_tm_packet.update({last_sn: last_tm_packet})

            else:
                print('Unknown tc_command received')
                print(tc_data)
                print(tc_packet)

            if doing_health_payloads:
                if health_payloads_pending > 0:
                    doing_health_payloads = False
                    last_sn = spacecraft_sequence_number
                    (tm_packet, spacecraft_sequence_number, health_payloads_pending) = transmit_health_packet(
                        q_health_payloads, health_payload_length, health_payloads_pending,
                        spacecraft_sequence_number, ax25_header, spp_header_len, spacecraft_key, tx_obj, use_serial, turnaround)
                    if health_payloads_pending > 0:
                        doing_health_payloads = True
                    last_tm_packet.update({last_sn: tm_packet})
            elif doing_science_payloads:
                if science_payloads_pending > 0:
                    doing_science_payloads = False
                    last_sn = spacecraft_sequence_number
                    (tm_packet, spacecraft_sequence_number, science_payloads_pending) = transmit_science_packet(
                        q_science_payloads, science_payload_length, science_payloads_pending,
                        spacecraft_sequence_number, ax25_header, spp_header_len, spacecraft_key, tx_obj, use_serial, turnaround)
                    if science_payloads_pending > 0:
                        doing_science_payloads = True
                    last_tm_packet.update({last_sn: tm_packet})
            else:
                pass


if __name__ == "__main__":
    # execute only if run as a script
    main()
