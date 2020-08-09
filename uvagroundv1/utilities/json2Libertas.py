#!/usr/bin/env python3

"""
json2Libertas.py

Read JSON packet capture from uvagroundv1 and load the Health and Science payloads
into a MySQL database.

Copyright 2018, 2019, 2020 by Michael R. McPherson, Charlottesville, VA
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


from ground.constant import health_payload_fields, science_payload_fields
from ground.gpstime import UTCFromGps
from datetime import datetime
from pathlib import Path
import os
import configparser
import json
import mysql.connector
import math
import array
import hashlib
import random
import binascii


def main():
    home_folder_name = str(Path.home())
    json2Libertas_ini = home_folder_name + '/' + '.json2Libertas'
    config = configparser.ConfigParser()
    config.read([json2Libertas_ini])
    json_directory = config['general']['json_directory']
    mysql_user = config['general']['mysql_user']
    mysql_password = config['general']['mysql_password']
    mysql_db = config['general']['mysql_db']
    mysql_host = config['general']['mysql_host']
    libertasHealth_db = config['general']['libertasHealth_db']
    libertasScience_db = config['general']['libertasScience_db']

    sql_lS_command = 'INSERT INTO libertasScience (TIMEUTC, '
    for science_field in science_payload_fields:
        sql_lS_command += science_field[0].replace('<', '').replace('>', '') + ', '
    sql_lS_command += 'AX25_SHA256) VALUES (' + ('%s, ' * (len(science_payload_fields) + 2))
    sql_lS_command = sql_lS_command[:-2]
    sql_lS_command += ')'

    sql_lH_command = 'INSERT INTO libertasHealth (TIMEUTC, GPSTIME, GPSWEEK, '
    for health_field in health_payload_fields:
        sql_lH_command += health_field[0].replace('<', '').replace('>', '') + ', '
    sql_lH_command += 'AX25_SHA256) VALUES (' + ('%s, ' * (len(health_payload_fields) + 4))
    sql_lH_command = sql_lH_command[:-2]
    sql_lH_command += ')'

    sql_lA_command = 'INSERT INTO libertasAX25Packet (TIMEUTC, GPSTIME, GPSWEEK, SENDER, PACKET_TYPE, COMMAND, ' \
                     'SEQUENCE_NUMBER, AX25_DESTINATION, AX25_SOURCE, AX25_PACKET, AX25_SHA256) '
    sql_lA_command += 'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)'

    cnx = mysql.connector.connect(user=mysql_user, password=mysql_password, database=mysql_db, host=mysql_host)
    cursor = cnx.cursor()
    cursor.execute("DELETE FROM libertasScience")
    cnx.commit()
    cursor.execute("DELETE FROM libertasHealth")
    cnx.commit()
    cursor.execute("DELETE FROM libertasAX25Packet")
    cnx.commit()

    health_payloads = 0
    science_payloads = 0
    ax25_packets = 0
    for json_dir_entry in os.scandir(json_directory):
        print(json_dir_entry.path)
        if (json_dir_entry.path.endswith(".json") and json_dir_entry.is_file()):
            with open(json_dir_entry.path, 'r') as f:
                packet_dict = json.load(f)
            ax25_sha256 = hashlib.sha256()
            for packet in packet_dict["packets"]:
                packet_time = UTCFromGps(float(packet['gps_week']), float(packet['gps_time']))
                frac, whole = math.modf(packet_time[5])
                time_utc = datetime(packet_time[0], packet_time[1], packet_time[2],
                                    packet_time[3], packet_time[4], int(whole), int(frac * 1000000)).isoformat(' ')
                ax25_packet = array.array('B', [])
                for b in packet['ax25_packet']:
                    ax25_packet.append(int(b, 0))
                ax25_sha256.update(ax25_packet)
                if packet["packet_type"] == 'TM':
                    if packet["command"] == 'XMIT_HEALTH':
                        health_payloads += 1
                        ax25_random = str(random.random()).encode()
                        ax25_sha256.update(ax25_random)
                        ax25_digest = binascii.hexlify(ax25_sha256.digest()).decode()
                        sql_data = (packet["ground_utc"], packet['gps_time'], packet['gps_week'])
                        for health_item in health_payload_fields:
                            health_item_trimmed = health_item[0].replace('<', '').replace('>', '')
                            sql_data = sql_data + (packet['PAYLOAD0'][health_item_trimmed],)
                        sql_data = sql_data + (ax25_digest,)
                        cursor.execute(sql_lH_command, sql_data)
                        cnx.commit()
                        print(sql_data)
                    elif packet["command"] == 'XMIT_SCIENCE':
                        for i in range(2):
                            payload = 'PAYLOAD' + str(i)
                            science_payloads += 1
                            ax25_random = str(random.random()).encode()
                            ax25_sha256.update(ax25_random)
                            ax25_digest = binascii.hexlify(ax25_sha256.digest()).decode()
                            payload_time = UTCFromGps((float(packet[payload]['GPSWEEK'])+1024.0), float(packet[payload]['GPSTIME']))
                            frac, whole = math.modf(payload_time[5])
                            payload_time_utc = datetime(payload_time[0], payload_time[1], payload_time[2],
                                                payload_time[3], payload_time[4], int(whole), int(frac * 1000000)).isoformat(' ')
                            sql_data = (payload_time_utc, packet[payload]['GPSTIME'], packet[payload]['GPSWEEK'])
                            for science_item in science_payload_fields[2:]:
                                science_item_trimmed = science_item[0].replace('<', '').replace('>', '')
                                sql_data = sql_data + (packet[payload][science_item_trimmed],)
                            sql_data = sql_data + (ax25_digest,)
                            cursor.execute(sql_lS_command, sql_data)
                            cnx.commit()
                            print(sql_data)
                ax25_packets += 1
                ax25_random = str(random.random()).encode()
                ax25_sha256.update(ax25_random)
                ax25_digest = binascii.hexlify(ax25_sha256.digest()).decode()
                ax25_packet_str = str(ax25_packet)
                sql_data = (packet['ground_utc'], packet['gps_time'], packet['gps_week'], packet['sender'], packet['packet_type'],
                            packet['command'], packet['sequence_number'], packet['ax25_destination'],
                            packet['ax25_source'], ax25_packet_str, ax25_digest)
                cursor.execute(sql_lA_command, sql_data)
                cnx.commit()
    cursor.close()
    cnx.close()
    print('Health payloads processed =', health_payloads)
    print('Science payloads processed =', science_payloads)
    print('AX25 packets processed =', ax25_packets)
    exit()


if __name__ == "__main__":
    # execute only if run as a script
    main()
