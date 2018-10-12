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

import json


def main():
    with open('ground20181012151206.json', 'r') as f:
        packet_dict = json.load(f)

    for packet in packet_dict["packets"]:
        print(packet["packet_type"], packet["command"])


if __name__ == "__main__":
    # execute only if run as a script
    main()
