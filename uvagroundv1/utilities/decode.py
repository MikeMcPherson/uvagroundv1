#!/usr/bin/env python3

"""
Decode and display packets to/from the UVa Libertas spacecraft.

Copyright 2019 by Michael R. McPherson, Charlottesville, VA
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

import os
import sys
import configparser
import binascii
import array
import time
from ground.constant import COMMAND_CODES, COMMAND_NAMES, health_payload_fields, science_payload_fields
from ground.packet_functions import SppPacket, GsCipher
from ground.packet_functions import from_bigendian, from_fake_float
from ground.packet_functions import init_ax25_header
from ground.packet_functions import ax25_callsign, to_int16, to_int32


"""
Helpers
"""


def hex_tabulate(buffer, values_per_row):
    buffer_len = len(buffer)
    buffer_string = ''
    for i in range(0, buffer_len, values_per_row):
        buffer_list = []
        for value in buffer[i:(i + values_per_row)]:
            buffer_list.append("\"0x{:02X}\"".format(value))
        buffer_string = buffer_string + '    ' + ", ".join(map(str, buffer_list))
        if (buffer_len - i) > values_per_row:
            buffer_string = buffer_string + ',\n'
        else:
            buffer_string = buffer_string + '\n'
    return buffer_string


"""
Display packet
"""


def display_packet(ax25_packet):
    global first_packet
    global health_payload_length
    global science_payload_length
    global encrypt_uplink
    global gs_cipher
    global sc_ax25_callsign
    global gs_ax25_callsign

    values_per_row = 8

    tv_header = ('  "ground_utc":"<GROUND_UTC>",\n' +
                 '  "sender":"<SENDER>", ' +
                 '"packet_type":"<PACKET_TYPE>", ' +
                 '"command":"<COMMAND>",\n')

    tv_spp = ('  "gps_week":"<GPS_WEEK>", ' +
              '"gps_time":"<GPS_TIME>", ' +
              '"sequence_number":"<SEQUENCE_NUMBER>",\n' +
              '  "packet_data_length":"<PACKET_DATA_LENGTH>",\n' +
              '  "simulated_error":"<SIMULATED_ERROR>", ' +
              '"security_trailer_valid":"<MAC_VALID>",\n')
    tv_spp_raw = ('  "<PACKET_TYPE>_data_length":"<SPP_DATA_LENGTH>",\n' +
                  '  "<PACKET_TYPE>_data":[\n<SPP_DATA>    ],\n' +
                  '  "security_trailer":[\n<MAC_DIGEST>    ],\n')

    tv_ax25 = ('  "ax25_destination":"<AX25_DESTINATION>", ' +
               '"ax25_source":"<AX25_SOURCE>", ' +
               '"ax25_packet_length":"<AX25_PACKET_LENGTH>",\n' +
               '  "ax25_packet":[\n<AX25_PACKET>    ]\n')

    if first_packet:
        print("{\n\"packets\" : [\n")
        first_packet = False
    else:
        print(",\n")
    ground_utc = time.gmtime()
    ground_utc_string = time.strftime("%Y%m%dT%H%M%SZ", ground_utc)
    tv_header = tv_header.replace('<GROUND_UTC>', ground_utc_string)
    if len(ax25_packet) >= 33:
        if ax25_packet[16] == 0x18:
            dp_packet = SppPacket('TC', dynamic=False)
        elif ax25_packet[16] == 0x08:
            dp_packet = SppPacket('TM', dynamic=False)
        elif len(ax25_packet) == 33:
            dp_packet = SppPacket('OA', dynamic=False)
        else:
            dp_packet = SppPacket('UN', dynamic=False)
        dp_packet.parse_ax25(ax25_packet)
        print("{\n")

        if dp_packet.command in COMMAND_NAMES:
            cmd_name = COMMAND_NAMES[dp_packet.command]
        else:
            cmd_name = COMMAND_NAMES[0x00]
        if dp_packet.is_oa_packet:
            packet_type = 'OA'
            tv_header = tv_header.replace('<SENDER>', 'ground')
            tv_header = tv_header.replace('<PACKET_TYPE>', packet_type)
            if dp_packet.spp_packet[16] == 0x31:
                tv_header = tv_header.replace('<COMMAND>', 'PING_RETURN_COMMAND')
            elif dp_packet.spp_packet[16] == 0x33:
                tv_header = tv_header.replace('<COMMAND>', 'RADIO_RESET_COMMAND')
            elif dp_packet.spp_packet[16] == 0x34:
                tv_header = tv_header.replace('<COMMAND>', 'PIN_TOGGLE_COMMAND')
            else:
                tv_header = tv_header.replace('<COMMAND>', 'ILLEGAL OA COMMAND')
        elif dp_packet.packet_type == 0x08:
            packet_type = 'TM'
            tv_header = tv_header.replace('<SENDER>', 'spacecraft')
            tv_header = tv_header.replace('<PACKET_TYPE>', packet_type)
            tv_header = tv_header.replace('<COMMAND>', cmd_name)
            tv_spp = tv_spp.replace('<SENDER>', 'spacecraft')
            tv_spp_raw = tv_spp_raw.replace('<PACKET_TYPE>', packet_type)
        elif dp_packet.packet_type == 0x18:
            packet_type = 'TC'
            tv_header = tv_header.replace('<SENDER>', 'ground')
            tv_header = tv_header.replace('<PACKET_TYPE>', packet_type)
            tv_header = tv_header.replace('<COMMAND>', cmd_name)
            tv_spp = tv_spp.replace('<SENDER>', 'ground')
            tv_spp_raw = tv_spp_raw.replace('<PACKET_TYPE>', packet_type)
        else:
            packet_type = 'UNKNOWN'
            tv_header = tv_header.replace('<SENDER>', 'UNKNOWN')
            tv_header = tv_header.replace('<PACKET_TYPE>', packet_type)
            tv_header = tv_header.replace('<COMMAND>', 'UNKNOWN')

        print(tv_header)

        if dp_packet.is_spp_packet:
            tv_spp = tv_spp.replace('<GPS_WEEK>', "{:d}".format(dp_packet.gps_week))
            tv_spp = tv_spp.replace('<GPS_TIME>', "{:14.7f}".format(dp_packet.gps_sow))
            tv_spp = tv_spp.replace('<SEQUENCE_NUMBER>', "{:05d}".format(dp_packet.sequence_number))
            # tv_spp = tv_spp.replace('<COMMAND>', cmd_name)

            tv_spp = tv_spp.replace('<PACKET_DATA_LENGTH>', "{:d}".format(dp_packet.packet_data_length))
            tv_spp_raw = tv_spp_raw.replace('<SPP_DATA_LENGTH>', "{:d}".format(len(dp_packet.spp_data)))
            packet_string = hex_tabulate(dp_packet.spp_data, values_per_row)
            tv_spp_raw = tv_spp_raw.replace('<SPP_DATA>', packet_string)

            if dp_packet.simulated_error:
                tv_spp = tv_spp.replace('<SIMULATED_ERROR>', 'True')
            else:
                tv_spp = tv_spp.replace('<SIMULATED_ERROR>', 'False')

            if dp_packet.validation_mask == 0:
                tv_spp = tv_spp.replace('<MAC_VALID>', 'True')
            else:
                tv_spp = tv_spp.replace('<MAC_VALID>', 'False')
            packet_string = hex_tabulate(dp_packet.mac_digest, values_per_row)
            tv_spp_raw = tv_spp_raw.replace('<MAC_DIGEST>', packet_string)

            print(tv_spp)
            print(tv_spp_raw)

            if dp_packet.spp_packet[0] == 0x08:
                if dp_packet.spp_data[0] == 0x03:
                    for n in range(dp_packet.spp_data[1]):
                        payload_begin = 2 + (science_payload_length * n)
                        payload_end = payload_begin + science_payload_length
                        packet_string = payload_decode(dp_packet.spp_data[0],
                                                       dp_packet.spp_data[payload_begin:payload_end], n)
                        print(packet_string)
                elif dp_packet.spp_data[0] == 0x02:
                    for n in range(1):
                        payload_begin = 2 + (health_payload_length * n)
                        payload_end = payload_begin + health_payload_length
                        packet_string = payload_decode(dp_packet.spp_data[0],
                                                       dp_packet.spp_data[payload_begin:payload_end], n)
                        print(packet_string)
                else:
                    packet_string = ''

    tv_ax25 = tv_ax25.replace('<AX25_DESTINATION>', ax25_callsign(ax25_packet[0:7]))
    tv_ax25 = tv_ax25.replace('<AX25_SOURCE>', ax25_callsign(ax25_packet[7:14]))
    tv_ax25 = tv_ax25.replace('<AX25_PACKET_LENGTH>', "{:d}".format(len(ax25_packet)))
    packet_string = hex_tabulate(ax25_packet, values_per_row)
    tv_ax25 = tv_ax25.replace('<AX25_PACKET>', packet_string)
    print(tv_ax25)

    print("}\n")
    return True


def payload_decode(command, payload_data, payload_number):
    science_payload_string = (
            '  "PAYLOAD<PAYLOAD_NUMBER>":{\n' +
            '    "PAYLOAD_TYPE":"SCIENCE",\n' +
            '    "GPSTIME":"<GPSTIME>", "GPSWEEK":"<GPSWEEK>",\n' +
            '    "XPOS":"<XPOS>", "YPOS":"<YPOS>", "ZPOS":"<ZPOS>",\n' +
            '    "NUMPVT":"<NUMPVT>", "PDOP":"<PDOP>",\n' +
            '    "XVEL":"<XVEL>", "YVEL":"<YVEL>", "ZVEL":"<ZVEL>",\n' +
            '    "LATITUDE":"<LATITUDE>", "LONGITUDE":"<LONGITUDE>",\n' +
            '    "FIXQUALITY":"<FIXQUALITY>", "NUMTRACKED":"<NUMTRACKED>", "HDOP":"<HDOP>",\n' +
            '    "ALTITUDE":"<ALTITUDE>",\n' +
            '    "GX":"<GX>", "GY":"<GY>", "GZ":"<GZ>",\n' +
            '    "MX":"<MX>", "MY":"<MY>", "MZ":"<MZ>",\n' +
            '    "VBCR1":"<VBCR1>", "IBCR1A":"<IBCR1A>", "IBCR1B":"<IBCR1B>",\n' +
            '    "TBCR1A":"<TBCR1A>", "TBCR1B":"<TBCR1B>",\n' +
            '    "SDBCR1A":"<SDBCR1A>", "SDBCR1B":"<SDBCR1B>",\n' +
            '    "VBCR2":"<VBCR2>", "IBCR2A":"<IBCR2A>", "IBCR2B":"<IBCR2B>",\n' +
            '    "TBCR2A":"<TBCR2A>", "TBCR2B":"<TBCR2B>",\n' +
            '    "SDBCR2A":"<SDBCR2A>", "SDBCR2B":"<SDBCR2B>",\n' +
            '    "VBCR4":"<VBCR4>", "IBCR4A":"<IBCR4A>",\n' +
            '    "TBCR4A":"<TBCR4A>",\n' +
            '    "SDBCR4A":"<SDBCR4A>", "SDBCR4B":"<SDBCR4B>"\n' +
            '  },\n'
    )
    health_payload_string = (
            '  "PAYLOAD0":{\n' +
            '    "PAYLOAD_TYPE":"HEALTH",\n' +
            '    "BROWNOUT_RESETS":"<BROWNOUT_RESETS>", "AUTO_SOFTWARE_RESETS":"<AUTO_SOFTWARE_RESETS>",\n' +
            '    "MANUAL_RESETS":"<MANUAL_RESETS>", "COMMS_WATCHDOG_RESETS":"<COMMS_WATCHDOG_RESETS>",\n' +
            '    "IIDIODE_OUT":"<IIDIODE_OUT>", "VIDIODE_OUT":"<VIDIODE_OUT>",\n' +
            '    "I3V3_DRW":"<I3V3_DRW>", "I5V_DRW":"<I5V_DRW>",\n' +
            '    "IPCM12V":"<IPCM12V>", "VPCM12V":"<VPCM12V>",\n' +
            '    "IPCMBATV":"<IPCMBATV>", "VPCKBATV":"<VPCKBATV>",\n' +
            '    "IPCM5V":"<IPCM5V>", "VPCM5V":"<VPCM5V>",\n' +
            '    "IPCM3V3":"<IPCM3V3>", "VPCM3V3":"<VPCM3V3>",\n' +
            '    "TBRD":"<TBRD>",\n' +
            '    "VSW1":"<VSW1>", "ISW1":"<ISW1>", "VSW8":"<VSW8>", "ISW8":"<ISW8>",\n' +
            '    "VSW9":"<VSW9>", "ISW9":"<ISW9>", "VSW10":"<VSW10>", "ISW10":"<ISW10>",\n' +
            '    "VBCR1":"<VBCR1>", "IBCR1A":"<IBCR1A>", "IBCR1B":"<IBCR1B>",\n' +
            '    "TBCR1A":"<TBCR1A>", "TBCR1B":"<TBCR1B>",\n' +
            '    "SDBCR1A":"<SDBCR1A>", "SDBCR1B":"<SDBCR1B>",\n' +
            '    "VBCR2":"<VBCR2>", "IBCR2A":"<IBCR2A>", "IBCR2B":"<IBCR2B>",\n' +
            '    "TBCR2A":"<TBCR2A>", "TBCR2B":"<TBCR2B>",\n' +
            '    "SDBCR2A":"<SDBCR2A>", "SDBCR2B":"<SDBCR2B>",\n' +
            '    "VBCR4":"<VBCR4>", "IBCR4A":"<IBCR4A>",\n' +
            '    "TBCR4A":"<TBCR4A>",\n' +
            '    "SDBCR4A":"<SDBCR4A>", "SDBCR4B":"<SDBCR4B>",\n' +
            '    "ANTENNA_STATUS":"<ANTENNA_STATUS>"\n' +
            '  },\n'
    )
    if command == COMMAND_CODES['XMIT_SCIENCE']:
        payload_string = science_payload_string
        payload_string = payload_string.replace('<PAYLOAD_NUMBER>', "{:1d}".format(payload_number))
        payload_fields = science_payload_fields
    elif command == COMMAND_CODES['XMIT_HEALTH']:
        payload_string = health_payload_string
        payload_fields = health_payload_fields
    else:
        payload_string = ''
        payload_fields = []
    idx = 0
    for field in payload_fields:
        if field[1] == 'LATLON':
            deg_min_int = from_bigendian(payload_data[idx:(idx + 2)], 2)
            deg_int = int(deg_min_int / 100.0)
            min_int = deg_min_int - (deg_int * 100)
            min_frac = from_bigendian(payload_data[(idx + 2):(idx + 6)], 4)
            field_value = deg_int + (from_fake_float(min_int, min_frac) / 60.0)
            if (payload_data[(idx + 6)] == 0x53) or (payload_data[(idx + 6)] == 0x57):
                field_value = -field_value
            payload_string = payload_string.replace(field[0], "{:f}".format(field_value))
            idx = idx + 7
        elif field[1] == 'DOP':
            field_value = from_fake_float(payload_data[idx],
                                          from_bigendian(payload_data[(idx + 1):(idx + 5)], 4))
            payload_string = payload_string.replace(field[0], "{:f}".format(field_value))
            idx = idx + 5
        elif field[1] == 'GPSTIME':
            field_value = from_fake_float(from_bigendian(payload_data[idx:(idx + 4)], 4),
                                          from_bigendian(payload_data[(idx + 4):(idx + 8)], 4))
            payload_string = payload_string.replace(field[0], "{:14.7f}".format(field_value))
            idx = idx + 8
        elif field[1] == 'FLOAT16':
            field_value = (int(from_bigendian(payload_data[idx:(idx + 2)], 2)) * field[2]) + field[3]
            payload_string = payload_string.replace(field[0], "{:f}".format(field_value))
            idx = idx + 2
        elif field[1] == 'INT32':
            field_value = (int(from_bigendian(payload_data[idx:(idx + 4)], 4)) * field[2]) + field[3]
            field_value = to_int32(field_value)
            payload_string = payload_string.replace(field[0], "{:d}".format(field_value))
            idx = idx + 4
        elif field[1] == 'INT16':
            field_value = (int(from_bigendian(payload_data[idx:(idx + 2)], 2)) * field[2]) + field[3]
            field_value = to_int16(field_value)
            payload_string = payload_string.replace(field[0], "{:d}".format(field_value))
            idx = idx + 2
        elif field[1] == 'UINT32':
            field_value = (int(from_bigendian(payload_data[idx:(idx + 4)], 4)) * field[2]) + field[3]
            payload_string = payload_string.replace(field[0], "{:d}".format(field_value))
            idx = idx + 4
        elif field[1] == 'UINT16':
            field_value = (int(from_bigendian(payload_data[idx:(idx + 2)], 2)) * field[2]) + field[3]
            payload_string = payload_string.replace(field[0], "{:d}".format(field_value))
            idx = idx + 2
        elif field[1] == 'UINT8':
            field_value = (int(payload_data[idx]) * field[2]) + field[3]
            payload_string = payload_string.replace(field[0], "{:d}".format(field_value))
            idx = idx + 1
        elif field[1] == 'HEX32':
            field_value = (int(from_bigendian(payload_data[idx:(idx + 4)], 4)) * field[2]) + field[3]
            payload_string = payload_string.replace(field[0], "0x{:08X}".format(field_value))
            idx = idx + 2
        elif field[1] == 'HEX16':
            field_value = (int(from_bigendian(payload_data[idx:(idx + 2)], 2)) * field[2]) + field[3]
            payload_string = payload_string.replace(field[0], "0x{:04X}".format(field_value))
            idx = idx + 2
        elif field[1] == 'HEX8':
            field_value = (int(payload_data[idx]) * field[2]) + field[3]
            payload_string = payload_string.replace(field[0], "0x{:02X}".format(field_value))
            idx = idx + 1
        else:
            field_value = 0
            payload_string = payload_string.replace(field[0], "{:d}".format(field_value))
            print('Bad Field Name')
    return payload_string


"""
Main
"""


def main():
    global first_packet
    global health_payload_length
    global science_payload_length
    global encrypt_uplink
    global gs_cipher
    global sc_ax25_callsign
    global gs_ax25_callsign

    first_packet = True
    health_payload_length = 89
    science_payload_length = 109
    tm_packet_window = 1

    script_folder_name = os.path.dirname(os.path.realpath(__file__))
    ground_ini = script_folder_name + '/' + 'ground.ini'
    keys_ini = script_folder_name + '/' + 'keys.ini'
    config = configparser.ConfigParser()
    config.read([ground_ini])
    src_callsign = config['ground']['callsign']
    src_ssid = int(config['ground']['ssid'])
    dst_callsign = config['libertas_sim']['callsign']
    dst_ssid = int(config['libertas_sim']['ssid'])
    turnaround = float(config['comms']['turnaround'])
    encrypt_uplink = config['comms'].getboolean('encrypt_uplink')
    ground_maxsize_packets = config['comms'].getboolean('ground_maxsize_packets')
    use_serial = config['comms'].getboolean('use_serial')
    uplink_simulated_error_rate = config['comms']['uplink_simulated_error_rate']
    downlink_simulated_error_rate = config['comms']['downlink_simulated_error_rate']

    config_keys = configparser.ConfigParser()
    config_keys.read([keys_ini])
    sc_mac_key = config_keys['keys']['sc_mac_key'].encode()
    gs_mac_key = config_keys['keys']['gs_mac_key'].encode()
    oa_key = config_keys['keys']['oa_key'].encode()
    gs_encryption_key = config_keys['keys']['gs_encryption_key'].encode()
    gs_iv = config_keys['keys']['gs_iv'].encode()

    logger = None

    GsCipher.mode = 'CBC'
    GsCipher.gs_encryption_key = gs_encryption_key
    GsCipher.gs_iv = gs_iv
    gs_cipher = GsCipher()
    gs_cipher.logger = logger

    ax25_header, sc_ax25_callsign, gs_ax25_callsign = init_ax25_header(dst_callsign, dst_ssid, src_callsign, src_ssid)

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

    if len(sys.argv) > 1:
        packet_filename = sys.argv[1]
        fp = open(packet_filename, 'r')
        lines = fp.readlines()
        fp.close()
        for line in lines:
            s = binascii.unhexlify(str.strip(line))
            print(s)
            ax25_packet = array.array('B', [])
            for b in s:
                ax25_packet.append(b)
            print(ax25_packet)
            display_packet(ax25_packet)
    else:
        print("Usage: decode.py input_file.txt")


if __name__ == "__main__":
    # execute only if run as a script
    main()
