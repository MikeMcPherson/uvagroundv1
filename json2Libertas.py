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

import configparser
import json
import mysql.connector


sql_lS_command = ('INSERT INTO libertasScience '
                    '(timeUTC, '
                    'XPOS, '
                    'YPOS, '
                    'ZPOS, '
                    'NUMPVT, '
                    'PDOP, '
                    'XVEL, '
                    'YVEL, '
                    'ZVEL, '
                    'LATITUDE, '
                    'LONGITUDE, '
                    'FIXQUALITY, '
                    'NUMTRACKED, '
                    'HDOP, '
                    'ALTITUDE, '
                    'GX, '
                    'GY, '
                    'GZ, '
                    'MX, '
                    'MY, '
                    'MZ, '
                    'VBCR1, '
                    'IBCR1A, '
                    'IBCR1B, '
                    'TBCR1A, '
                    'TBCR1B, '
                    'SDBCR1A, '
                    'SDBCR1B, '
                    'VBCR2, '
                    'IBCR2A, '
                    'IBCR2B, '
                    'TBCR2A, '
                    'TBCR2B, '
                    'SDBCR2A, '
                    'SDBCR2B, '
                    'VBCR4, '
                    'IBCR4A, '
                    'TBCR4A, '
                    'SDBCR4A, '
                    'SDBCR4B) '
                    'VALUES '
                    '(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '
                    '%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)')


def main():

    config = configparser.ConfigParser()
    config.read(['json2Libertas.ini'])
    mysql_user = config['general']['mysql_user']
    mysql_password = config['general']['mysql_password']
    mysql_db = config['general']['mysql_db']
    libertasHealth_db = config['general']['libertasHealth_db']
    libertasScience_db = config['general']['libertasScience_db']

    cnx = mysql.connector.connect(user=mysql_user, password=mysql_password, database=mysql_db)
    cursor = cnx.cursor()
    cursor.execute("DELETE FROM libertasScience")
    cnx.commit()
    cursor.execute("DELETE FROM libertasHealth")
    cnx.commit()

    with open('ground20181012151206.json', 'r') as f:
        packet_dict = json.load(f)
    records = 0
    for packet in packet_dict["packets"]:
        if packet["packet_type"] == 'TM':
            if packet["command"] == 'XMIT_HEALTH':
                print('health')
                records += 1
                seconds = float(row[0][12:14]) + random.random()
                time_utc = (row[0][:4] + '-' + row[0][4:6] + '-' + row[0][6:8] + 'T'
                            + row[0][8:10] + ':' + row[0][10:12] + ':' + '{:010.7f}'.format(seconds) + 'Z')
                sql_data = ("{:s}".format(time_utc),)
                sql_data = sql_data + \
                            ("{:.2f}".format(battery_voltage_b1),
                            "{:.2f}".format(battery_voltage_b2),
                            "{:.2f}".format(battery_voltage_b3),
                            "{:.2f}".format(battery_voltage_b4))
                cursor.execute(sql_command, sql_data)
                cnx.commit()
            elif packet["command"] == 'XMIT_SCIENCE':
                print('science')
    cursor.close()
    cnx.close()


if __name__ == "__main__":
    # execute only if run as a script
    main()
