#!/usr/bin/python3

"""
ConfigRead

Read configuration file and return parameter values on demand..

Copyright 2020 by Michael R. McPherson, Charlottesville, VA
mailto:mcpherson@acm.org
http://www.kq9p.us

This program is free software; you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free
Software Foundation; either version 3 of the License, or (at your option) any
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
import sys
import configparser

class ConfigRead:
    """Read configuration file and return parameter values on demand.

    Attributes
    ----------
    None

    Methods
    -------
    get_param(param_group, param_name)
        Return value of "parameter_name"

    """

    def __init__(self, configfile_path, configfile_name):
        self.config = configparser.ConfigParser()
        for path in configfile_path:
            config_file = '/'.join[path, configfile_name]
            if(os.path.isfile(config_file)):
                self.config.read(config_file)
        print(f"Unable to find configuration file {configfile_name}")
        sys.exit()


    def get_param(self, param_group, param_name):
        return self.config[param_group][param_name]
