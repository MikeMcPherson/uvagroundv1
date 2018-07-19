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
import hashlib
import hmac
from ground.chaskey import chaskey
from ground.gpstime import gpsFromUTC
import hexdump


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


def hmac_sign(packet, key):
    # digest = hmac.new(key, msg=packet, digestmod=hashlib.sha256).digest()
    digest = chaskey(key[:16], 16, packet).digest()
    digest = digest + (b'\x00' * 16)
    return(digest)
    
    
def receive_packet(my_packet_type, rx_obj, use_serial, q_receive_packet, q_display_packet):
    while True:
        if use_serial:
            serial_buffer = rx_obj.read(8)
            rcv_packet = array.array('B', [])
            for s in serial_buffer:
                rcv_packet.append(s)
            serial_buffer = rx_obj.read(rcv_packet[5] + 2)
            for s in serial_buffer:
                rcv_packet.append(s)
        else:
            rcv_string = rx_obj.recv(1024)
            rcv_packet = array.array('B', [])
            for c in rcv_string:
                rcv_packet.append(c)
        if len(rcv_packet) >= 20:
            if use_serial:
                ax25_packet = lithium_unwrap(rcv_packet)
            else:
                ax25_packet = kiss_unwrap(rcv_packet)
            if ax25_packet[16] != my_packet_type:
                q_receive_packet.put(ax25_packet)
                q_display_packet.put(ax25_packet)


def is_libertas_packet(packet_type, ax25_packet, spp_header_len, oa_key):
    is_spp_packet = False
    is_oa_packet = True
    for idx, c in enumerate(oa_key):
        if c != ax25_packet[(idx + 16)]:
            is_oa_packet = False
    if (ax25_packet[32] < 0x30) or (ax25_packet[32] > 0x34):
        is_oa_packet = False
    if not is_oa_packet:
        is_spp_packet = True
        packet_min_len = 64
        if len(ax25_packet) < packet_min_len:
            is_spp_packet = False
        if (ax25_packet[14] != 0x03) or (ax25_packet[15] != 0xF0):
            is_spp_packet = False
    return(is_spp_packet, is_oa_packet)


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
    

def spp_wrap(packet_type, data, spp_header_len, sequence_number, key):
    if packet_type == 'TM':
        packet = array.array('B', [0x08, 0x00, 0x00])
    else:
        packet = array.array('B', [0x18, 0x00, 0x00])
    gps_tm = gps_time()
    packet.extend(spp_time_encode(gps_tm[0], gps_tm[1]))
    packet.extend(to_bigendian(sequence_number, 2))
    for d in data:
        packet.append(d)
    hmac_scope = packet[(spp_header_len - 2):]
    digest = hmac_sign(hmac_scope, key)
    packet.extend(digest)
    packet_info = packet.buffer_info()
    packet[2] = packet_info[1] - 3 - 1
    return(packet)


def spp_unwrap(packet, spp_header_len):
    data = packet[spp_header_len:-32]
    gps_week, gps_sow = spp_time_decode(packet[3:13])
    return(data, gps_week, gps_sow)
    
    
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


def ax25_wrap(packet_type, packet, ax25_header):
    ax25_packet = array.array('B', [])
    for h in ax25_header:
        ax25_packet.append(h)
    for p in packet:
        ax25_packet.append(p)
    if packet_type == 'TC':
        padding = 253 - len(ax25_packet)
        if padding > 0:
            ax25_packet.extend([0x00]*padding)
    return(ax25_packet)


def ax25_unwrap(ax25_packet):
    packet_data_length = from_bigendian(ax25_packet[17:19], 2)
    padding = len(ax25_packet) - (16 + 3 + (packet_data_length + 1))
    if padding > 0:
        ax25_packet = ax25_packet[:(-padding)]
    packet = ax25_packet[16:]
    return(packet)
    

FEND = 0xC0
FESC = 0xDB
TFEND = 0xDC
TFESC = 0xDD

def kiss_wrap(packet):
    kiss_packet = array.array('B', [FEND, 0x00])
    for p in packet:
        if p == FEND:
            kiss_packet.append(FESC)
            kiss_packet.append(TFEND)
        elif p == FESC:
            kiss_packet.append(FESC)
            kiss_packet.append(TFESC)
        else:
            kiss_packet.append(p)
    kiss_packet.append(FEND)
    return(kiss_packet)


def kiss_unwrap(kiss_packet):
    packet = array.array('B', [])
    for idx, k in enumerate(kiss_packet[2:]):
        if k == FEND:
            pass
        elif k == FESC:
            if (kiss_packet[idx + 3] == TFEND) or (kiss_packet[idx + 3] == TFESC):
                continue
        else:
            packet.append(k)
    return(packet)


def ax25_callsign(b_callsign):
    c_callsign = ''
    for b in b_callsign[0:6]:
        c_callsign = c_callsign + chr((b & 0b11111110) >> 1)
    c_callsign = c_callsign + '-'
    c_callsign = c_callsign + str((b_callsign[6] & 0b00011110) >> 1)
    c_callsign = c_callsign.replace(' ','')
    return(c_callsign)


def validate_packet(packet_type, packet, spp_header_len, sequence_number, key):
    hmac_scope = packet[(spp_header_len - 2):-32]
    ground_digest = packet[-32:]
    validation_digest = hmac_sign(hmac_scope, key)
    validation_mask = 0
    for idx, v in enumerate(ground_digest):
        if v != validation_digest[idx]:
            validation_mask = validation_mask | 0b00000001
    return(validation_mask)
