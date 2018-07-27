#!/usr/bin/env python3

"""
Utilities to wrap, unwrap, and verify packets.

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
import time
from ground.chaskey import chaskey
from ground.gpstime import gpsFromUTC
import serial
import socket
import hexdump
import random
import inspect
from functools import wraps


class RadioDevice:
    use_serial = None
    kiss_over_serial = None
    rx_server = None
    rx_port = None
    rx_obj = None
    tx_server = None
    tx_port = None
    tx_obj = None
    serial_device_name = None

    def open(self):
        if self.use_serial:
            self.rx_obj = serial.Serial(self.serial_device_name, baudrate=9600)
            self.tx_obj = self.rx_obj
        else:
            rx_addr = (self.rx_server, self.rx_port)
            tx_addr = (self.tx_server, self.tx_port)
            self.rx_obj = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.rx_obj.connect(rx_addr)
            self.tx_obj = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tx_obj.connect(tx_addr)

    def close(self):
        try:
            self.rx_obj.close()
            self.tx_obj.close()
        except:
            pass

    def set_baudrate(self, baudrate):
        self.rx_obj.baudrate = baudrate

    def receive(self):
        if self.use_serial:
            serial_buffer = self.rx_obj.read(8)
            rcv_packet = array.array('B', [])
            for s in serial_buffer:
                rcv_packet.append(s)
            serial_buffer = self.rx_obj.read(rcv_packet[5] + 2)
            for s in serial_buffer:
                rcv_packet.append(s)
        else:
            rcv_string = self.rx_obj.recv(1024)
            rcv_packet = array.array('B', [])
            for c in rcv_string:
                rcv_packet.append(c)
        if self.use_serial:
            ax25_packet = lithium_unwrap(rcv_packet)
        else:
            ax25_packet = kiss_unwrap(rcv_packet)
        return ax25_packet

    def transmit(self, ax25_packet):
        if self.use_serial:
            xmit_packet = lithium_wrap(ax25_packet)
        else:
            xmit_packet = kiss_wrap(ax25_packet)
        if self.use_serial:
            self.tx_obj.write(xmit_packet)
        else:
            self.tx_obj.send(xmit_packet)


def pre_post(f):
    @wraps(f)
    def wrapper(self, *args, **kw):
        if hasattr(self, 'pre') and inspect.ismethod(self.pre):
            self.pre()
        result = f(self, *args, **kw)
        if hasattr(self, 'post') and inspect.ismethod(self.post):
            self.post()
        return result
    return wrapper


class SppPacket:
    ax25_header = None
    oa_key = None
    radio = None
    turnaround = None
    q_display_packet = None
    ground_maxsize_packets = None
    mac_digest_len = 16
    spacecraft_key = None
    ground_station_key = None
    tm_packet_window = None

    def __init__(self, packet_type, dynamic):
        if packet_type == 'TC':
            self.packet_type = 0x18
            self.dynamic = dynamic
            self.key = self.ground_station_key
        elif packet_type == 'TM':
            self.packet_type = 0x08
            self.dynamic = dynamic
            self.key = self.spacecraft_key
        elif packet_type == 'OA':
            self.packet_type = 0
            self.dynamic = False
        else:
            self.packet_type = 0
            self.dynamic = False
        self.is_spp_packet = False
        self.is_oa_packet = False
        self.packet_data_length = 0
        self.gps_week, self.gps_sow = gps_time()
        self.sequence_number = 0
        self.spp_data = []
        self.command = 0
        self.expected_sequence_number = 0
        self.validation_mask = 0
        self.mac_digest = array.array('B', [])
        self.spp_packet = array.array('B', [])
        self.ax25_packet = array.array('B', [])
        if self.dynamic:
            self.post()

    def pre(self):
        if self.dynamic:
            pass

    def post(self):
        if self.dynamic:
            self.__spp_wrap()
            self.__ax25_wrap()
            self.__is_libertas_packet()
            self.__validate_packet()

    @pre_post
    def set_sequence_number(self, sequence_number):
        self.sequence_number = sequence_number

    @pre_post
    def set_spp_data(self, spp_data):
        self.spp_data = spp_data

    def parse_ax25(self, ax25_received):
        self.ax25_packet = ax25_received
        self.__ax25_unwrap()
        self.__is_libertas_packet()
        if self.is_spp_packet:
            self.__spp_unwrap()
            self.__validate_packet()
        else:
            self.command = self.ax25_packet[(16 + len(self.oa_key))]

    def set_oa_command(self, command):
        self.ax25_packet = array.array('B', [])
        self.ax25_packet.extend(self.ax25_header)
        for k in self.oa_key:
            self.ax25_packet.append(k)
        self.ax25_packet.append(command)
        self.command = command

    def transmit(self):
        time.sleep(float(self.turnaround) / 1000.0)
        self.radio.transmit(self.ax25_packet)
        self.q_display_packet.put(self.ax25_packet)

    def __spp_wrap(self):
        self.packet_data_length = 28 + len(self.spp_data) - 1
        self.spp_packet = array.array('B', [])
        self.spp_packet.append(self.packet_type)
        self.spp_packet.extend(to_bigendian(self.packet_data_length, 2))
        self.spp_packet.extend(spp_time_encode(self.gps_week, self.gps_sow))
        self.spp_packet.extend(to_bigendian(self.sequence_number, 2))
        self.spp_packet.extend(self.spp_data)
        self.mac_digest = mac_sign(self.spp_packet[13:], self.key)
        self.spp_packet.extend(self.mac_digest)

    def __spp_unwrap(self):
        self.packet_type = self.spp_packet[0]
        self.packet_data_length = from_bigendian(self.spp_packet[1:3], 2)
        self.gps_week, self.gps_sow = spp_time_decode(self.spp_packet[3:13])
        self.sequence_number = from_bigendian(self.spp_packet[13:15], 2)
        self.spp_data = self.spp_packet[15:(15 + (self.packet_data_length + 1) -12 - self.mac_digest_len)]
        self.command = self.spp_data[0]
        self.mac_digest = self.spp_packet[-self.mac_digest_len:]

    def __ax25_wrap(self):
        self.ax25_packet = array.array('B', [])
        self.ax25_packet.extend(self.ax25_header)
        self.ax25_packet.extend(self.spp_packet)
        if self.ground_maxsize_packets and (self.packet_type == 0x18):
            padding = 253 - len(self.ax25_packet)
            if padding > 0:
                self.ax25_packet.extend([0x00] * padding)

    def __ax25_unwrap(self):
        packet_data_length = from_bigendian(self.ax25_packet[17:19], 2)
        if self.ground_maxsize_packets and (self.packet_type == 0x18):
            padding = len(self.ax25_packet) - (16 + 3 + (packet_data_length + 1))
            if padding > 0:
                self.ax25_packet = self.ax25_packet[:(-padding)]
        self.ax25_header = self.ax25_packet[:16]
        self.spp_packet = self.ax25_packet[16:]

    def __is_libertas_packet(self):
        self.is_spp_packet = False
        self.is_oa_packet = True
        for idx, c in enumerate(self.oa_key):
            if c != self.ax25_packet[(idx + 16)]:
                self.is_oa_packet = False
        if (self.ax25_packet[32] < 0x30) or (self.ax25_packet[32] > 0x34):
            self.is_oa_packet = False
        if not self.is_oa_packet:
            self.is_spp_packet = True
            packet_min_len = 48
            if len(self.ax25_packet) < packet_min_len:
                self.is_spp_packet = False
            if (self.ax25_packet[14] != 0x03) or (self.ax25_packet[15] != 0xF0):
                self.is_spp_packet = False

    def __validate_packet(self):
        mac_scope = self.spp_packet[13:-self.mac_digest_len]
        validation_digest = mac_sign(mac_scope, self.key)
        self.validation_mask = 0b00000000
        for idx, v in enumerate(self.mac_digest):
            if v != validation_digest[idx]:
                self.validation_mask = self.validation_mask | 0b00000001


def sn_increment(sequence_number):
    sequence_number = sequence_number + 1
    if sequence_number > 65535:
        sequence_number = 1
    return sequence_number


def sn_decrement(sequence_number):
    sequence_number = sequence_number - 1
    if sequence_number == 0:
        sequence_number = 1
    return(sequence_number)


def to_bigendian(input_integer, num_bytes):
    output_bigendian = array.array('B', [])
    if num_bytes == 4:
        output_bigendian.append((input_integer & 0xFF000000) >> 24)
        output_bigendian.append((input_integer & 0x00FF0000) >> 16)
    output_bigendian.append((input_integer & 0xFF00) >> 8)
    output_bigendian.append((input_integer & 0x00FF))
    return(output_bigendian)


def from_bigendian(input_bigendian, num_bytes):
    output_integer = 0
    for i in range(num_bytes):
        output_integer = output_integer + (input_bigendian[i] << ((num_bytes - i - 1) * 8))
    return(output_integer)


def to_fake_float(input_float, whole_bytes, fract_bytes):
    return


def from_fake_float(whole_part, fract_part):
    return_float = float("{:d}".format(whole_part) + '.' + "{:07d}".format(fract_part))
    return(return_float)


def gps_time():
    time_utc = time.gmtime()
    gps_tm = gpsFromUTC(time_utc[0], time_utc[1], time_utc[2], time_utc[3], time_utc[4], time_utc[5])
    return(gps_tm[0], gps_tm[1])


def mac_sign(packet, key):
    digest = chaskey(key, 16, packet).digest()
    return(digest)


def make_ack(packet_type, packets_to_ack):
    packet = SppPacket(packet_type, dynamic=True)
    spp_data = array.array('B', [0x05])
    packet.set_spp_data(spp_data)
    return packet


def make_nak(packet_type, packets_to_nak):
    packet = SppPacket(packet_type, dynamic=True)
    spp_data = array.array('B', [0x06])
    if packet_type == 'TC':
        if len(packets_to_nak) > 0:
            spp_data.append(len(packets_to_nak))
            for p in packets_to_nak:
                spp_data.extend(to_bigendian(p.sequence_number, 2))
        else:
            spp_data.append(0x00)
    packet.set_spp_data(spp_data)
    return packet


def receive_packet(my_packet_type, radio, q_receive_packet, q_display_packet):
    while True:
        ax25_packet = radio.receive()
        if ax25_packet[16] != my_packet_type:
            # if (random.random() <= 0.5) and (len(ax25_packet) >= 64) and (ax25_packet[16] == 0x08):
            #     xor_idx = random.randrange(29, len(ax25_packet))
            #     ax25_packet[xor_idx] = ax25_packet[xor_idx] ^ 0xFF
            #     print('Simulated receive error, xor_idx, before/after', xor_idx, ax25_packet[xor_idx] ^ 0xFF,
            #           ax25_packet[xor_idx])
            q_receive_packet.put(ax25_packet)
            q_display_packet.put(ax25_packet)


def init_ax25_header(dst_callsign, dst_ssid, src_callsign, src_ssid):
    ax25_header = array.array('B', [])
    for c in dst_callsign:
        ax25_header.append(ord(c) << 1)
    ax25_header.append((dst_ssid << 1) | 0b01100000)
    for c in src_callsign:
        ax25_header.append(ord(c) << 1)
    ax25_header.append((src_ssid << 1) | 0b01100001)
    ax25_header.append(0x03)
    ax25_header.append(0xF0)
    return(ax25_header)


def ax25_callsign(b_callsign):
    c_callsign = ''
    for b in b_callsign[0:6]:
        c_callsign = c_callsign + chr((b & 0b11111110) >> 1)
    c_callsign = c_callsign + '-'
    c_callsign = c_callsign + str((b_callsign[6] & 0b00011110) >> 1)
    c_callsign = c_callsign.replace(' ','')
    return(c_callsign)


def spp_time_encode(gps_week, gps_sow):
    spp_time_array = array.array('B', [])
    temp_sow = "{:14.7f}".format(gps_sow).split('.')
    gps_sow_int = int(temp_sow[0])
    gps_sow_fract = int(temp_sow[1])
    spp_time_array.extend(to_bigendian(gps_week, 2))
    spp_time_array.extend(to_bigendian(gps_sow_int, 4))
    spp_time_array.extend(to_bigendian(gps_sow_fract, 4))
    return(spp_time_array)
    

def spp_time_decode(spp_time_array):
    gps_week = from_bigendian(spp_time_array[0:2], 2)
    gps_sow_int = from_bigendian(spp_time_array[2:6], 4)
    gps_sow_fract = from_bigendian(spp_time_array[6:10], 4)
    gps_sow = float("{:06d}".format(gps_sow_int) + '.' + "{:07d}".format(gps_sow_fract))
    return(gps_week, gps_sow)


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


FEND = 0xC0
FESC = 0xDB
TFEND = 0xDC
TFESC = 0xDD

def kiss_wrap(ax25_packet):
    kiss_packet = array.array('B', [FEND, 0x00])
    for p in ax25_packet:
        if p == FEND:
            kiss_packet.append(FESC)
            kiss_packet.append(TFEND)
        elif p == FESC:
            kiss_packet.append(FESC)
            kiss_packet.append(TFESC)
        else:
            kiss_packet.append(p)
    kiss_packet.append(FEND)
    return kiss_packet


def kiss_unwrap(kiss_packet):
    ax25_packet = array.array('B', [])
    fesc_found = False
    for b in kiss_packet[2:-1]:
        if fesc_found:
            if b == TFESC:
                ax25_packet.append(FESC)
            elif b == TFEND:
                ax25_packet.append(FEND)
            else:
                print('KISS error')
            fesc_found = False
        elif b == FESC:
            fesc_found = True
        else:
            ax25_packet.append(b)
    return ax25_packet
