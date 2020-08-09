#!/usr/bin/env python3

"""
Simple ground station for the UVa Libertas spacecraft.

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
Main
"""


def main():

    radio_server = False
    rx_hostname = 'localhost'
    tx_hostname = 'localhost'
    rx_port = 18500
    tx_port = 18500

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
    rx_hostname = config['ground']['rx_hostname']
    tx_hostname = config['ground']['tx_hostname']
    rx_port = int(config['ground']['rx_port'])
    tx_port = int(config['ground']['tx_port'])
    src_ssid = int(config['ground']['ssid'])
    sequencer_relay_delay = float(config['ground']['sequencer_relay_delay'])
    dst_callsign = config['libertas_sim']['callsign']
    dst_ssid = int(config['libertas_sim']['ssid'])
    turnaround = float(config['comms']['turnaround'])
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

    GsCipher.mode = 'CBC'
    GsCipher.gs_encryption_key = gs_encryption_key
    GsCipher.gs_iv = gs_iv
    gs_cipher = GsCipher()
    gs_cipher.logger = logger

    ax25_header, sc_ax25_callsign, gs_ax25_callsign = init_ax25_header(dst_callsign, dst_ssid, src_callsign, src_ssid)
    ax25_badpacket = init_ax25_badpacket(ax25_header, their_packet_type)

    turnaround = 0
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

    radio = RadioDevice()
    radio.ack_timeout = ack_timeout * 1.25
    radio.max_retries = max_retries
    radio.open()
    SppPacket.radio = radio
    RadioDevice.sequencer = None

    q_receive_packet = mp.Queue()
    q_display_packet = mp.Queue()
    SppPacket.q_display_packet = q_display_packet

    tc_packet = SppPacket('TC', dynamic=True)
    tc_data = array.array('B', [0x09])
    tc_packet.set_spp_data(tc_data)
    tc_packet.set_sequence_number(ground_sequence_number)
    while True:
        tc_packet.transmit()
        ground_sequence_number = sn_increment(ground_sequence_number)
        time.sleep(0.200)


if __name__ == "__main__":
    # execute only if run as a script
    main()
