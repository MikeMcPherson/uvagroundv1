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
from ground.packet_functions import SppPacket
from ground.packet_functions import receive_packet, make_ack, make_nak
from ground.packet_functions import to_bigendian, from_bigendian, to_fake_float, from_fake_float
from ground.packet_functions import init_ax25_header, sn_increment, sn_decrement
import serial
import hexdump
import random
import socket
import multiprocessing as mp
from inspect import currentframe
import random


def main():

    """
    Commands
    """
    COMMAND_ACK = 0x05
    COMMAND_NAK = 0x06
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

    my_packet_type = 0x08
    serial_device_name = 'pty_ground'
    spp_header_len = 15
    spacecraft_sequence_number = 1
    expected_ground_sequence_number = 0
    health_payload_length = 46
    health_payloads_per_packet = 4
    doing_health_payloads = False
    science_payload_length = 83
    science_payloads_per_packet = 2
    doing_science_payloads = False
    doing_retransmit = False
    tm_packet_window = 1
    transmit_timeout_count = 4
    ack_timeout = 10
    sequence_number_window = 2
    tm_packets_waiting_ack = []
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
    ground_maxsize_packets = config['comms'].getboolean('ground_maxsize_packets')

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
    SppPacket.ax25_header = ax25_header
    SppPacket.oa_key = oa_key
    SppPacket.ground_maxsize_packets = ground_maxsize_packets

    if use_serial:
        rx_obj = serial.Serial(serial_device_name, baudrate=9600)
        tx_obj = rx_obj
    else:
        rx_obj = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        rx_obj.connect(('gs-s-2.w4uva.org', rx_port))
        tx_obj = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tx_obj.connect(('gs-s-2.w4uva.org', tx_port))
    SppPacket.tx_obj = tx_obj

    q_receive_packet = mp.Queue()
    q_display_packet = mp.Queue()
    SppPacket.q_display_packet = q_display_packet
    p_receive_packet = mp.Process(target=receive_packet, args=(my_packet_type, rx_obj, use_serial,
                                                               q_receive_packet, q_display_packet))
    p_receive_packet.start()

    while True:
        ax25_packet = q_receive_packet.get()
        q_display_packet.get()
        tc_packet = SppPacket('TC', ground_station_key, dynamic=False)
        tc_packet.parse_ax25(ax25_packet)
        if tc_packet.is_oa_packet:
            if tc_packet.command == 0x31:
                print("Libertas received OA PING_RETURN_COMMAND")
            elif tc_packet.command == 0x33:
                print("Libertas received OA RADIO_RESET_COMMAND")
            elif tc_packet.command == 0x34:
                print("Libertas received OA PIN_TOGGLE_COMMAND, exiting...")
                p_receive_packet.terminate()
                rx_obj.close()
                tx_obj.close()
                logging.info('%s %s: Run ended', program_name, program_version)
                exit()
            else:
                print('Libertas: unrecognized OA command')
        else:
            if tc_packet.validation_mask != 0:
                tm_packet = make_nak([], spacecraft_key)
                tm_packet.set_sequence_number(spacecraft_sequence_number)
                tm_packet.transmit()
                spacecraft_sequence_number = sn_increment(spacecraft_sequence_number)
                break

            if tc_packet.command == COMMAND_ACK:
                print('Received ACK')
                if tc_packet.spp_data[1] == 0:
                    tm_packets_waiting_ack.clear()
                else:
                    tm_packets_waiting_ack.clear()
                doing_retransmit = False

            elif tc_packet.command == COMMAND_NAK:
                print('Received NAK')
                if tc_packet.spp_data[1] == 0:
                    for i in tm_packets_waiting_ack:
                        i.transmit()
                else:
                    for i in tm_packets_waiting_ack:
                        i.transmit()
                doing_retransmit = True

            # Commands requiring only ACK

            elif tc_packet.command == COMMAND_CEASE_XMIT:
                print('Received CEASE_XMIT')
                tm_packet = make_ack('TM', [], spacecraft_key)
                tm_packet.set_sequence_number(spacecraft_sequence_number)
                tm_packet.transmit()
                spacecraft_sequence_number = sn_increment(spacecraft_sequence_number)
                doing_health_payloads = False
                doing_science_payloads = False

            elif tc_packet.command == COMMAND_NOOP:
                print('Received NOOP')
                tm_packet = make_ack('TM', [], spacecraft_key)
                tm_packet.set_sequence_number(spacecraft_sequence_number)
                tm_packet.transmit()
                spacecraft_sequence_number = sn_increment(spacecraft_sequence_number)

            elif tc_packet.command == COMMAND_RESET:
                print('Received RESET')
                tm_packet = make_ack('TM', [], spacecraft_key)
                tm_packet.set_sequence_number(spacecraft_sequence_number)
                tm_packet.transmit()
                spacecraft_sequence_number = sn_increment(spacecraft_sequence_number)

            elif tc_packet.command == COMMAND_WRITE_MEM:
                print('Received WRITE_MEM')
                tm_packet = make_ack('TM', [], spacecraft_key)
                tm_packet.set_sequence_number(spacecraft_sequence_number)
                tm_packet.transmit()
                spacecraft_sequence_number = sn_increment(spacecraft_sequence_number)

            elif tc_packet.command == COMMAND_SET_MODE:
                print('Received SET_MODE')
                tm_packet = make_ack('TM', [], spacecraft_key)
                tm_packet.set_sequence_number(spacecraft_sequence_number)
                tm_packet.transmit()
                spacecraft_sequence_number = sn_increment(spacecraft_sequence_number)

            elif tc_packet.command == COMMAND_SET_COMMS:
                print('Received SET_COMMS')
                tm_packet_window = tc_packet.spp_data[1]
                transmit_timeout_count = tc_packet.spp_data[2]
                ack_timeout = tc_packet.spp_data[3]
                sequence_number_window = tc_packet.spp_data[4]
                spacecraft_sequence_number = from_bigendian(tc_packet.spp_data[5:7], 2)
                expected_ground_sequence_number = from_bigendian(tc_packet.spp_data[7:9], 2)
                turnaround = from_bigendian(tc_packet.spp_data[9:11], 2)
                tm_packet = make_ack('TM', [], spacecraft_key)
                tm_packet.set_sequence_number(spacecraft_sequence_number)
                tm_packet.transmit()

            # Commands requiring a response

            elif tc_packet.command == COMMAND_XMIT_COUNT:
                print('Received XMIT_COUNT')
                tm_packet = SppPacket('TM', spacecraft_key, dynamic=True)
                tm_packet.set_sequence_number(spacecraft_sequence_number)
                tm_data = array.array('B', [0x01])
                tm_data.extend(to_bigendian(health_payloads_pending, 2))
                tm_data.extend(to_bigendian(science_payloads_pending, 2))
                tm_packet.set_spp_data(tm_data)
                tm_packet.transmit()
                tm_packets_waiting_ack.append(tm_packet)
                spacecraft_sequence_number = sn_increment(spacecraft_sequence_number)

            elif tc_packet.command == COMMAND_READ_MEM:
                print('Received READ_MEM')
                tm_packet = SppPacket('TM', spacecraft_key, dynamic=True)
                tm_packet.set_sequence_number(spacecraft_sequence_number)
                tm_data = array.array('B', [0x01])
                for d in tc_packet.spp_data[1:5]:
                    tm_data.append(d)
                number_of_locations = ((from_bigendian(tc_packet.spp_data[3:5], 2) -
                                        from_bigendian(tc_packet.spp_data[1:3], 2)) + 1)
                for i in range(number_of_locations):
                    tm_data.append(random.randint(0, 255))
                    tm_data.append(random.randint(0, 255))
                tm_packet.set_spp_data(tm_data)
                tm_packet.transmit()
                tm_packets_waiting_ack.append(tm_packet)
                spacecraft_sequence_number = sn_increment(spacecraft_sequence_number)

            elif tc_packet.command == COMMAND_GET_COMMS:
                print('Received GET_COMMS')
                tm_packet = SppPacket('TM', spacecraft_key, dynamic=True)
                tm_packet.set_sequence_number(spacecraft_sequence_number)
                tm_data = array.array('B', [0x01])
                tm_data.append(tm_packet_window & 0xFF)
                tm_data.append(transmit_timeout_count & 0xFF)
                tm_data.append(ack_timeout & 0xFF)
                tm_data.append(sequence_number_window & 0xFF)
                tm_data.extend(to_bigendian((spacecraft_sequence_number + 1), 2))
                tm_data.extend(to_bigendian(expected_ground_sequence_number, 2))
                tm_data.extend(to_bigendian(turnaround, 2))
                tm_packet.set_spp_data(tm_data)
                tm_packet.transmit()
                tm_packets_waiting_ack.append(tm_packet)
                spacecraft_sequence_number = sn_increment(spacecraft_sequence_number)

            # Commands Health and Science packets

            elif tc_packet.command == COMMAND_XMIT_HEALTH:
                print('Received XMIT_HEALTH')
                downlink_health_payloads = tc_packet.spp_data[1]
                if health_payloads_pending > 0:
                    doing_health_payloads = True
                else:
                    doing_health_payloads = False

            elif tc_packet.command == COMMAND_XMIT_SCIENCE:
                print('Received XMIT_SCIENCE')
                downlink_science_payloads = tc_packet.spp_data[1]
                if science_payloads_pending > 0:
                    doing_science_payloads = True
                else:
                    doing_science_payloads = False

            else:
                print('Unknown tc_packet.command received')
                print(tc_packet.spp_data)
                print(tc_packet.spp_packet)

            if not doing_retransmit:
                if doing_health_payloads:
                    if health_payloads_pending > 0:
                        doing_health_payloads = False
                        tm_packet = SppPacket('TM', spacecraft_key, dynamic=True)
                        spp_data = array.array('B', [0x02])
                        payloads_this_packet = min(health_payloads_pending, health_payloads_per_packet)
                        spp_data.append(payloads_this_packet)
                        for i in range(payloads_this_packet):
                            health_payload = q_health_payloads.get()
                            for h in health_payload:
                                spp_data.append(h)
                        for i in range(payloads_this_packet, health_payloads_per_packet):
                            spp_data.extend([0x00] * health_payload_length)
                        tm_packet.set_sequence_number(spacecraft_sequence_number)
                        tm_packet.set_spp_data(spp_data)
                        tm_packet.transmit()
                        tm_packets_waiting_ack.append(tm_packet)
                        spacecraft_sequence_number = sn_increment(spacecraft_sequence_number)
                        health_payloads_pending = max((health_payloads_pending - payloads_this_packet), 0)
                        if health_payloads_pending > 0:
                            doing_health_payloads = True
                elif doing_science_payloads:
                    if science_payloads_pending > 0:
                        doing_science_payloads = False
                        tm_packet = SppPacket('TM', spacecraft_key, dynamic=True)
                        spp_data = array.array('B', [0x03])
                        payloads_this_packet = min(science_payloads_pending, science_payloads_per_packet)
                        spp_data.append(payloads_this_packet)
                        for i in range(payloads_this_packet):
                            science_payload = q_science_payloads.get()
                            for s in science_payload:
                                spp_data.append(s)
                        for i in range(payloads_this_packet, science_payloads_per_packet):
                            spp_data.extend([0x00] * science_payload_length)
                        tm_packet.set_sequence_number(spacecraft_sequence_number)
                        tm_packet.set_spp_data(spp_data)
                        tm_packet.transmit()
                        tm_packets_waiting_ack.append(tm_packet)
                        spacecraft_sequence_number = sn_increment(spacecraft_sequence_number)
                        science_payloads_pending = max((science_payloads_pending - payloads_this_packet), 0)
                        if science_payloads_pending > 0:
                            doing_science_payloads = True
                else:
                    pass


if __name__ == "__main__":
    # execute only if run as a script
    main()
