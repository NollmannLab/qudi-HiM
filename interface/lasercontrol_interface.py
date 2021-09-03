# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains the interface for the control of multiple laser sources.

An extension to Qudi.

@author: F. Barho

Created on Wed Feb 10 2021
-----------------------------------------------------------------------------------

Qudi is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Qudi is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Qudi. If not, see <http://www.gnu.org/licenses/>.

Copyright (c) the Qudi Developers. See the COPYRIGHT.txt file at the
top-level directory of this distribution and at <https://github.com/Ulm-IQO/qudi/>
-----------------------------------------------------------------------------------
"""
from core.interface import abstract_interface_method
from core.meta import InterfaceMetaclass


class LasercontrolInterface(metaclass=InterfaceMetaclass):
    """ This interface contains the common part for laser control by a DAQ or by an FPGA.
    """

    @abstract_interface_method
    def get_dict(self):
        """ Retrieves the channel name and the voltage range for each analog output for laser control from the
        configuration file and associates it to the laser wavelength which is controlled by this channel.

        exemplary entry: {'laser1': {'label': 'laser1', 'wavelength': '405 nm', 'channel': '/Dev1/AO2',
                            'voltage_range': [0, 10]}  # DAQ
                         {'laser1': {'label': 'laser1', 'wavelength': '405 nm', 'channel': '405'}}
                                    # FPGA. 'channel' corresponds to the registername.

        :return: dict laser_dict
        """
        pass

    @abstract_interface_method
    def apply_voltage(self, voltage, channel):
        """ Writes a voltage to the specified channel.

        :param: float voltage: voltage value to be applied
        :param: str channel: identifier of the channel (such as '/Dev1/AO0' for a DAQ or '405' (the register name) for
                            an FPGA.

        :return: None
        """
        pass
