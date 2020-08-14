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
    open_config(configfile_path, configfile_name)
        Search paths in array configfile_path for configfile_name, open, and import
    get_param(param_group, param_name, param_type)
        Return value of "parameter_name"

    """

    def __init__(self):
        self.config = configparser.ConfigParser()

    def open_config(self, configfile_path, configfile_name):
        config_file_found = False
        for path in configfile_path:
            config_file = '/'.join([path, configfile_name])
            if(os.path.isfile(config_file)):
                self.config.read(config_file)
                config_file_found = True
        return config_file_found

    def get_param(self, param_group, param_name, param_type):

        if(param_type is "int"):
            return int(self.config[param_group][param_name])
        elif(param_type is "float"):
            return float(self.config[param_group][param_name])
        elif(param_type is "bool"):
            return self.config[param_group].getboolean(param_name)
        elif(param_type is "key"):
            return self.config[param_group][param_name].encode()
        elif(param_type is "path"):
            return os.path.expandvars(self.config[param_group][param_name])
        elif(param_type is "string"):
            return self.config[param_group][param_name]
        else:
            print("Unknown param_type {param_type}")
            sys.exit()
