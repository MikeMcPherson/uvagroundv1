#!/usr/bin/python3

"""
Libertas Simulator V1.0
Simple communications simulator for the UVa Libertas spacecraft.

Copyright 2018, 2020 by Michael R. McPherson, Charlottesville, VA
mailto:mcpherson@acm.org
http://www.kq9p.us

This program is free software; you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free
Software Foundation; either version 2 of the License, or (at your option) any
later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE.  See the GNU General Public License for more
details.

You should have received a copy of the GNU General Public License along with
this program. If not, see <http://www.gnu.org/licenses/>.
"""

__author__ = 'Michael R. McPherson <mcpherson@acm.org>'

import os
import configparser
import logging
import array
import serial
import hexdump
import random
import socket
import multiprocessing as mp
from queue import Empty
from inspect import currentframe
import random
from ground.packet_functions import SppPacket, RadioDevice, GsCipher
from ground.packet_functions import receive_packet, make_ack, make_nak
from ground.packet_functions import to_bigendian, from_bigendian, to_fake_float, from_fake_float
from ground.packet_functions import init_ax25_header, init_ax25_badpacket, sn_increment, sn_decrement


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
    COMMAND_MAC_TEST = 0x0E
    COMMAND_TIMEOUT_FAKE_PACKET = 0xFF

    my_packet_type = 0x08
    their_packet_type = 0x18
    serial_device_name = 'pty_ground'
    spp_header_len = 15
    spacecraft_sequence_number = 1
    expected_ground_sequence_number = 0
    health_payload_length = 89
    health_payloads_per_packet = 1
    downlink_health_payloads = 0
    doing_health_payloads = False
    science_payload_length = 109
    science_payloads_per_packet = 2
    downlink_science_payloads = 0
    doing_science_payloads = False
    doing_retransmit = False
    tm_packet_window = 1
    transmit_timeout_count = 4
    ack_timeout = 5
    max_retries = 4
    sequence_number_window = 2
    spacecraft_transmit_power = 125
    tm_packets_waiting_ack = []
    radio_server = False
    rx_hostname = 'localhost'
    tx_hostname = 'localhost'
    rx_port = 19500
    tx_port = 19500

    cf = currentframe()
    script_folder_name = os.path.dirname(os.path.realpath(__file__))
    ground_ini = script_folder_name + '/' + 'ground.ini'
    keys_ini = script_folder_name + '/' + 'keys.ini'
    config = configparser.ConfigParser()
    config.read([ground_ini])
    debug = config['libertas_sim'].getboolean('debug')
    program_name = config['libertas_sim']['program_name']
    program_version = config['libertas_sim']['program_version']
    radio_server = config['libertas_sim'].getboolean('radio_server')
    rx_hostname = config['libertas_sim']['rx_hostname']
    tx_hostname = config['libertas_sim']['tx_hostname']
    rx_port = int(config['libertas_sim']['rx_port'])
    tx_port = int(config['libertas_sim']['tx_port'])
    dst_callsign = config['ground']['callsign']
    dst_ssid = int(config['ground']['ssid'])
    src_callsign = config['libertas_sim']['callsign']
    src_ssid = int(config['libertas_sim']['ssid'])
    turnaround = int(config['comms']['turnaround'])
    encrypt_uplink = config['comms'].getboolean('encrypt_uplink')
    ground_maxsize_packets = config['comms'].getboolean('ground_maxsize_packets')
    use_serial = config['comms'].getboolean('use_serial')
    serial_device_name = config['comms']['serial_device_name']
    use_lithium_cdi = config['comms'].getboolean('use_lithium_cdi')

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

    q_health_payloads = mp.Queue()
    q_science_payloads = mp.Queue()

    health_payloads_pending = 40
    for p in range(health_payloads_pending):
        health_payload = array.array('B', [])
        for i in range(health_payload_length):
            health_payload.append(random.randint(0, 255))
        q_health_payloads.put(health_payload)

    science_payloads_pending = 40
    for p in range(science_payloads_pending):
        science_payload = array.array('B', [])
        for i in range(science_payload_length):
            science_payload.append(random.randint(0, 255))
        q_science_payloads.put(science_payload)

    GsCipher.mode = 'CBC'
    GsCipher.gs_encryption_key = gs_encryption_key
    GsCipher.gs_iv = gs_iv
    gs_cipher = GsCipher()
    gs_cipher.logger = logger

    ax25_header, gs_ax25_callsign, sc_ax25_callsign = init_ax25_header(dst_callsign, dst_ssid, src_callsign, src_ssid)
    ax25_badpacket = init_ax25_badpacket(ax25_header, their_packet_type)

    SppPacket.ax25_header = ax25_header
    SppPacket.oa_key = oa_key
    SppPacket.ground_maxsize_packets = ground_maxsize_packets
    SppPacket.turnaround = turnaround
    SppPacket.sc_mac_key = sc_mac_key
    SppPacket.gs_mac_key = gs_mac_key
    SppPacket.encrypt_uplink = encrypt_uplink
    SppPacket.gs_cipher = gs_cipher
    SppPacket.gs_ax25_callsign = gs_ax25_callsign
    SppPacket.sc_ax25_callsign = sc_ax25_callsign
    SppPacket.logger = logger

    RadioDevice.radio_server = radio_server
    RadioDevice.rx_hostname = rx_hostname
    RadioDevice.rx_port = rx_port
    RadioDevice.tx_hostname = tx_hostname
    RadioDevice.tx_port = tx_port
    RadioDevice.serial_device_name = serial_device_name
    RadioDevice.use_serial = use_serial
    RadioDevice.use_lithium_cdi = use_lithium_cdi

    radio = RadioDevice()
    radio.ack_timeout = ack_timeout
    radio.max_retries = max_retries
    radio.logger = logger
    radio.open()
    SppPacket.radio = radio

    q_receive_packet = mp.Queue()
    q_display_packet = mp.Queue()
    SppPacket.q_display_packet = q_display_packet

    p_receive_packet = mp.Process(target=receive_packet, name='receive_packet', args=(sc_ax25_callsign, radio,
                                                                                      q_receive_packet, logger))
    p_receive_packet.daemon = True
    p_receive_packet.start()
    logger.info("%s %s", program_name, program_version)

    while True:
        try:
            ax25_packet = q_receive_packet.get(True, ack_timeout)
        except Empty:
            ax25_packet = 0xFF
        if ax25_packet is None:
            logger.info('Socket closed')
            exit()
        elif ax25_packet == 0xFF:
            ax25_packet = array.array('B', ax25_badpacket)

        if len(ax25_packet) < 17:
            print('Short packet')
            hexdump.hexdump(ax25_packet)
            tm_packet = make_nak('TM', [])
            tm_packet.set_sequence_number(spacecraft_sequence_number)
            tm_packet.transmit()
            spacecraft_sequence_number = sn_increment(spacecraft_sequence_number)
        else:
            tc_packet = SppPacket('TC', dynamic=False)
            tc_packet.parse_ax25(ax25_packet)
            if tc_packet.is_oa_packet:
                if tc_packet.command == 0x31:
                    print("Libertas received OA PING_RETURN_COMMAND")
                elif tc_packet.command == 0x33:
                    print("Libertas received OA RADIO_RESET_COMMAND")
                elif tc_packet.command == 0x34:
                    print("Libertas received OA PIN_TOGGLE_COMMAND, exiting...")
                    p_receive_packet.terminate()
                    radio.close()
                    logging.info('%s %s: Run ended', program_name, program_version)
                    exit()
                else:
                    print('Unrecognized OA command', tc_packet.command)
            else:
                if (tc_packet.validation_mask != 0) and (len(tm_packets_waiting_ack) > 0):
                    tm_packet = make_nak('TM', [])
                    tm_packet.set_sequence_number(spacecraft_sequence_number)
                    tm_packet.transmit()
                    spacecraft_sequence_number = sn_increment(spacecraft_sequence_number)
                else:
                    if tc_packet.command == COMMAND_TIMEOUT_FAKE_PACKET:
                        pass

                    elif tc_packet.command == COMMAND_ACK:
                        print('Received ACK')
                        tm_packets_waiting_ack.clear()
                        doing_retransmit = False

                    elif tc_packet.command == COMMAND_NAK:
                        print('Received NAK')
                        if tc_packet.spp_data[1] == 0:
                            tm_packet = make_ack('TM', [])
                            tm_packet.set_sequence_number(spacecraft_sequence_number)
                            tm_packet.transmit()
                            spacecraft_sequence_number = sn_increment(spacecraft_sequence_number)
                            tm_packets_waiting_ack.clear()
                            doing_health_payloads = False
                            doing_science_payloads = False
                        else:
                            for i in tm_packets_waiting_ack:
                                i.transmit()
                        doing_retransmit = True

                    # Commands requiring only ACK

                    elif tc_packet.command == COMMAND_CEASE_XMIT:
                        print('Received CEASE_XMIT')
                        tm_packet = make_ack('TM', [])
                        tm_packet.set_sequence_number(spacecraft_sequence_number)
                        tm_packet.transmit()
                        spacecraft_sequence_number = sn_increment(spacecraft_sequence_number)
                        tm_packets_waiting_ack.clear()
                        doing_health_payloads = False
                        doing_science_payloads = False

                    elif tc_packet.command == COMMAND_NOOP:
                        print('Received NOOP')
                        tm_packet = make_ack('TM', [])
                        tm_packet.set_sequence_number(spacecraft_sequence_number)
                        tm_packet.transmit()
                        spacecraft_sequence_number = sn_increment(spacecraft_sequence_number)

                    elif tc_packet.command == COMMAND_RESET:
                        print('Received RESET')
                        tm_packet = make_ack('TM', [])
                        tm_packet.set_sequence_number(spacecraft_sequence_number)
                        tm_packet.transmit()
                        spacecraft_sequence_number = sn_increment(spacecraft_sequence_number)

                    elif tc_packet.command == COMMAND_WRITE_MEM:
                        print('Received WRITE_MEM')
                        tm_packet = make_ack('TM', [])
                        tm_packet.set_sequence_number(spacecraft_sequence_number)
                        tm_packet.transmit()
                        spacecraft_sequence_number = sn_increment(spacecraft_sequence_number)

                    elif tc_packet.command == COMMAND_SET_MODE:
                        print('Received SET_MODE')
                        tm_packet = make_ack('TM', [])
                        tm_packet.set_sequence_number(spacecraft_sequence_number)
                        tm_packet.transmit()
                        spacecraft_sequence_number = sn_increment(spacecraft_sequence_number)

                    elif tc_packet.command == COMMAND_SET_COMMS:
                        print('Received SET_COMMS')
                        tm_packet_window = tc_packet.spp_data[1]
                        transmit_timeout_count = tc_packet.spp_data[2]
                        ack_timeout = tc_packet.spp_data[3]
                        sequence_number_window = tc_packet.spp_data[4]
                        temp = from_bigendian(tc_packet.spp_data[5:7], 2)
                        if temp > 0:
                            spacecraft_sequence_number = temp
                        temp = from_bigendian(tc_packet.spp_data[7:9], 2)
                        if temp > 0:
                            expected_ground_sequence_number = temp
                        turnaround = from_bigendian(tc_packet.spp_data[9:11], 2)
                        spacecraft_transmit_power = tc_packet.spp_data[11]
                        SppPacket.turnaround = turnaround
                        tm_packet = make_ack('TM', [])
                        tm_packet.set_sequence_number(spacecraft_sequence_number)
                        tm_packet.transmit()
                        spacecraft_sequence_number = sn_increment(spacecraft_sequence_number)

                    # Commands requiring a response

                    elif tc_packet.command == COMMAND_XMIT_COUNT:
                        print('Received XMIT_COUNT')
                        tm_packet = SppPacket('TM', dynamic=True)
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
                        tm_packet = SppPacket('TM', dynamic=True)
                        tm_packet.set_sequence_number(spacecraft_sequence_number)
                        tm_data = array.array('B', [0x08])
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
                        tm_packet = SppPacket('TM', dynamic=True)
                        tm_packet.set_sequence_number(spacecraft_sequence_number)
                        tm_data = array.array('B', [0x0C])
                        tm_data.append(tm_packet_window & 0xFF)
                        tm_data.append(transmit_timeout_count & 0xFF)
                        tm_data.append(ack_timeout & 0xFF)
                        tm_data.append(sequence_number_window & 0xFF)
                        tm_data.extend(to_bigendian((spacecraft_sequence_number + 1), 2))
                        tm_data.extend(to_bigendian(expected_ground_sequence_number, 2))
                        tm_data.extend(to_bigendian(turnaround, 2))
                        tm_data.append(spacecraft_transmit_power)
                        tm_packet.set_spp_data(tm_data)
                        tm_packet.transmit()
                        tm_packets_waiting_ack.append(tm_packet)
                        spacecraft_sequence_number = sn_increment(spacecraft_sequence_number)

                    elif tc_packet.command == COMMAND_MAC_TEST:
                        print('Received MAC_TEST')
                        for i in range(208):
                            tm_packet = SppPacket('TM', dynamic=True)
                            tm_packet.set_sequence_number(spacecraft_sequence_number)
                            tm_data = array.array('B', [0x0E])
                            temp_data = array.array('B', [])
                            for j in range(i):
                                temp_data.append(j + 2)
                            tm_data.extend(temp_data)
                            tm_packet.set_spp_data(tm_data)
                            tm_packet.transmit()
                            spacecraft_sequence_number = sn_increment(spacecraft_sequence_number)

                    # Commands Health and Science packets

                    elif tc_packet.command == COMMAND_XMIT_HEALTH:
                        print('Received XMIT_HEALTH')
                        if tc_packet.spp_data[1] == 0xFF:
                            print('Dump mode')
                            downlink_health_payloads = health_payloads_pending
                            dump_mode = True
                        else:
                            downlink_health_payloads = min((tc_packet.spp_data[1] * health_payloads_per_packet),
                                                           health_payloads_pending)
                            dump_mode = False
                        doing_health_payloads = True

                    elif tc_packet.command == COMMAND_XMIT_SCIENCE:
                        print('Received XMIT_SCIENCE')
                        if tc_packet.spp_data[1] == 0xFF:
                            print('Dump mode')
                            downlink_science_payloads = science_payloads_pending
                            dump_mode = True
                        else:
                            downlink_science_payloads = min((tc_packet.spp_data[1] * science_payloads_per_packet),
                                                            science_payloads_pending)
                            dump_mode = False
                        doing_science_payloads = True

                    else:
                        print('Unknown tc_packet.command received', tc_packet.command)
                        tm_packet = make_nak('TM', [])
                        tm_packet.set_sequence_number(spacecraft_sequence_number)
                        tm_packet.transmit()
                        spacecraft_sequence_number = sn_increment(spacecraft_sequence_number)

                    if not doing_retransmit:
                        if doing_health_payloads:
                            if dump_mode:
                                rep_count = downlink_health_payloads
                            else:
                                rep_count = tm_packet_window
                            for reps in range(rep_count):
                                doing_health_payloads = False
                                tm_packet = SppPacket('TM', dynamic=True)
                                spp_data = array.array('B', [0x02])
                                if downlink_health_payloads > 0:
                                    payloads_this_packet = min(downlink_health_payloads, health_payloads_per_packet)
                                    spp_data.append(payloads_this_packet)
                                    for i in range(payloads_this_packet):
                                        health_payload = q_health_payloads.get()
                                        for h in health_payload:
                                            spp_data.append(h)
                                    for i in range(payloads_this_packet, health_payloads_per_packet):
                                        spp_data.extend([0x00] * health_payload_length)
                                    health_payloads_pending = max((health_payloads_pending - payloads_this_packet), 0)
                                    downlink_health_payloads = max((downlink_health_payloads - payloads_this_packet), 0)
                                    if downlink_health_payloads > 0:
                                        doing_health_payloads = True
                                else:
                                    spp_data.append(0x00)
                                    doing_health_payloads = False
                                tm_packet.set_sequence_number(spacecraft_sequence_number)
                                tm_packet.set_spp_data(spp_data)
                                tm_packet.transmit()
                                print('Sent XMIT_HEALTH')
                                if not dump_mode:
                                    tm_packets_waiting_ack.append(tm_packet)
                                spacecraft_sequence_number = sn_increment(spacecraft_sequence_number)
                                if not doing_health_payloads:
                                    break
                        elif doing_science_payloads:
                            if dump_mode:
                                rep_count = downlink_science_payloads
                            else:
                                rep_count = tm_packet_window
                            for reps in range(rep_count):
                                doing_science_payloads = False
                                tm_packet = SppPacket('TM', dynamic=True)
                                spp_data = array.array('B', [0x03])
                                if downlink_science_payloads > 0:
                                    payloads_this_packet = min(downlink_science_payloads, science_payloads_per_packet)
                                    spp_data.append(payloads_this_packet)
                                    for i in range(payloads_this_packet):
                                        science_payload = q_science_payloads.get()
                                        for s in science_payload:
                                            spp_data.append(s)
                                    for i in range(payloads_this_packet, science_payloads_per_packet):
                                        spp_data.extend([0x00] * science_payload_length)
                                    science_payloads_pending = max((science_payloads_pending - payloads_this_packet), 0)
                                    downlink_science_payloads = max((downlink_science_payloads - payloads_this_packet), 0)
                                    if downlink_science_payloads > 0:
                                        doing_science_payloads = True
                                else:
                                    spp_data.append(0x00)
                                    doing_science_payloads = False
                                tm_packet.set_sequence_number(spacecraft_sequence_number)
                                tm_packet.set_spp_data(spp_data)
                                tm_packet.transmit()
                                print('Sent XMIT_SCIENCE')
                                if not dump_mode:
                                    tm_packets_waiting_ack.append(tm_packet)
                                spacecraft_sequence_number = sn_increment(spacecraft_sequence_number)
                                if not doing_science_payloads:
                                    break
                        else:
                            pass


if __name__ == "__main__":
    # execute only if run as a script
    main()
