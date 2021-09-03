# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module interface for a microfluidics controller.

An extension to Qudi.

@author: F. Barho
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


class MicrofluidicsInterface(metaclass=InterfaceMetaclass):
    """ This interface is used to control a microfluidics system.
    """

    @abstract_interface_method
    def set_pressure(self, param_dict):
        """ Set new pressure value to a channel.

        :param dict param_dict: dictionary specifying the channel whose pressure value shall be changed and the new pressure setpoint.
                                Usage: {'pressure_channel': <the-pressure-setpoint>}.
                                'pressure_channel' must correspond to a pressure_channel_ID given in the config
        """
        pass

    @abstract_interface_method
    def get_pressure(self, param_list=None):
        """ Gets current pressure of the corresponding channel or all channels.

        :param list param_list: optional, pressure of a specific channel or a list of channels.
                                If None, all channels are queried.
        :return dict: pressure_dict. Keys = channel IDs and values = pressure value for the channel.
        """
        pass

    @abstract_interface_method
    def get_pressure_unit(self, param_list=None):
        """ Gets pressure unit of the corresponding channel or all channels.

        :param list param_list: optional, pressure unit of a specific channel or a list of channels.
                                If None, all channels are queried.
        :return dict: pressure_unit_dict. Keys = channel IDs and values = pressure units for the channel.
        """
        pass

    @abstract_interface_method
    def get_pressure_range(self, param_list=None):
        """ Gets pressure range of the corresponding channel or all channels.

        :param list param_list: optional, pressure range of a specific channel or a list of channels.
                                If None, all channels are queried.
        :return dict: pressure_range_dict. Keys = channel IDs and values = pressure range as tuple for the channel.
        """
        pass

    @abstract_interface_method
    def get_flowrate(self, param_list=None):
        """ Gets current flowrate of the corresponding sensor channel or all sensor channels.

        :param list param_list: optional, flowrate of a specific channel or a list of channels.
                                If None, all channels are queried.
        :return dict: flowrate_dict. Keys = channel IDs and values = flowrate for the channel.
        """
        pass

    @abstract_interface_method
    def get_sensor_unit(self, param_list=None):
        """ Gets sensor unit of the corresponding sensor channel or all sensor channels.

        :param list param_list: optional, sensor unit of a specific channel or a list of channels.
                                If None, all channels are queried.
        :return dict: sensor_unit_dict. Keys = channel IDs and values = sensor unit for the channel.
        """
        pass

    @abstract_interface_method
    def get_sensor_range(self, param_list=None):
        """ Gets sensor range of the corresponding sensor channel or all sensor channels.

        :param list param_list: optional, flowrate range of a specific channel or a list of channels.
                                If None, all channels are queried.
        :return dict: sensor_range_dict. Keys = channel IDs and values = flowrate range as tuple for the channel.
        """
        pass


