#!/usr/bin/env python3

"""
json2Libertas.py

Read JSON packet capture from uvagroundv1 and load the Health and Science payloads
into a MySQL database.

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


from ground.constant import health_payload_fields, science_payload_fields
from ground.gpstime import UTCFromGps
import datetime
import configparser
import json
import mysql.connector
import math


def main():
    config = configparser.ConfigParser()
    config.read(['json2Libertas.ini'])
    mysql_user = config['general']['mysql_user']
    mysql_password = config['general']['mysql_password']
    mysql_db = config['general']['mysql_db']
    libertasHealth_db = config['general']['libertasHealth_db']
    libertasScience_db = config['general']['libertasScience_db']

    sql_lS_command = 'INSERT INTO libertasScience (timeUTC, '
    for science_field in science_payload_fields[2:]:
        sql_lS_command += science_field[0].replace('<', '').replace('>', '') + ', '
    sql_lS_command = sql_lS_command[:-2]
    sql_lS_command += ') VALUES (' + ('%s, ' * len(science_payload_fields[2:]))
    sql_lS_command = sql_lS_command[:-2]
    sql_lS_command += ')'

    sql_lH_command = 'INSERT INTO libertasHealth (timeUTC, '
    for health_field in health_payload_fields[2:]:
        sql_lH_command += health_field[0].replace('<', '').replace('>', '') + ', '
    sql_lH_command = sql_lH_command[:-2]
    sql_lH_command += ') VALUES (' + ('%s, ' * len(health_payload_fields[2:]))
    sql_lH_command = sql_lH_command[:-2]
    sql_lH_command += ')'

    cnx = mysql.connector.connect(user=mysql_user, password=mysql_password, database=mysql_db)
    cursor = cnx.cursor()
    cursor.execute("DELETE FROM libertasScience")
    cnx.commit()
    cursor.execute("DELETE FROM libertasHealth")
    cnx.commit()

    with open('ground20181013024844.json', 'r') as f:
        packet_dict = json.load(f)
    records = 0
    for packet in packet_dict["packets"]:
        if packet["packet_type"] == 'TM':
            if packet["command"] == 'XMIT_HEALTH':
                print('health')
                records += 1
                packet_time = UTCFromGps(float(packet['gps_week']), float(packet['gps_time']))
                frac, whole = math.modf(packet_time[5])
                time_utc = datetime.datetime(packet_time[0], packet_time[1], packet_time[2],
                                             packet_time[3], packet_time[4], int(whole), int(frac * 1000000))
                sql_data = (time_utc,)
                print(sql_data)
                # sql_data = sql_data + \
                #             ("{:.2f}".format(battery_voltage_b1),
                #             "{:.2f}".format(battery_voltage_b2),
                #             "{:.2f}".format(battery_voltage_b3),
                #             "{:.2f}".format(battery_voltage_b4))
                # cursor.execute(sql_command, sql_data)
                # cnx.commit()
            elif packet["command"] == 'XMIT_SCIENCE':
                print('science')
    cursor.close()
    cnx.close()


if __name__ == "__main__":
    # execute only if run as a script
    main()
