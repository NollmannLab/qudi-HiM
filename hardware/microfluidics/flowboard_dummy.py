# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains the dummy implementation for a microfluidics flowboard.

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
import numpy as np
from core.module import Base
from interface.microfluidics_interface import MicrofluidicsInterface
from core.configoption import ConfigOption


class FlowboardDummy(Base, MicrofluidicsInterface):
    """ Dummy implementation of the microfluidics pump and flowrate sensor (controlled by a flowboard)

    Example config for copy-paste:

    flowboard_dummy:
        module.Class: 'microfluidics.flowboard_dummy.FlowboardDummy'
        pressure_channel_IDs:
            - 0
        sensor_channel_IDs:
            - 0

    """
    pressure_channel_IDs = ConfigOption('pressure_channel_IDs', missing='error')
    sensor_channel_IDs = ConfigOption('sensor_channel_IDs', missing='error')

    # store here the values that would normally be queried from the device
    pressure_dict = {}
    pressure_unit_dict = {}
    pressure_range_dict = {}

    sensor_unit_dict = {}
    sensor_range_dict = {}

    max_pressure = 350   # in mbar
    max_flow = 11000  # in ul/min

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

    def on_activate(self):
        """ Initialisation performed during activation of the module.
        """
        for i in range(len(self.pressure_channel_IDs)):
            self.pressure_dict[i] = 0
            self.pressure_unit_dict[i] = 'mbar'
            self.pressure_range_dict[i] = self.max_pressure

        for i in range(len(self.sensor_channel_IDs)):
            self.sensor_unit_dict[i] = 'ul/min'
            self.sensor_range_dict[i] = (-self.max_flow, self.max_flow)

    def on_deactivate(self):
        """ Deactivation steps. """
        pass

# ----------------------------------------------------------------------------------------------------------------------
# Methods for pressure channels
# ----------------------------------------------------------------------------------------------------------------------
    def set_pressure(self, param_dict):
        """ Set new pressure value to a channel.

        :param dict param_dict: dictionary specifying the channel whose pressure value shall be changed and the new pressure setpoint.
                                Usage: {'pressure_channel': <the-pressure-setpoint>}.
                                'pressure_channel' must correspond to a pressure_channel_ID given in the config
        """
        for key, value in param_dict.items():  # param_dict has the format {0: 20} for example
            if key in self.pressure_channel_IDs:
                if value <= self.max_pressure:
                    self.pressure_dict[key] = value
                else:
                    self.log.warn('Pressure not set. Target value above allowed range.')
            else:
                self.log.warn('Specified channel not available')

    def get_pressure(self, param_list=None):
        """ Gets current pressure of the corresponding channel or all channels.

        :param list param_list: optional, pressure of a specific channel or a list of channels.
                                If None, all channels are queried.
        :return dict: pressure_dict. Keys = channel IDs and values = pressure value for the channel.
        """
        if not param_list:
            return self.pressure_dict
        else:
            # select the subset of self.pressure_dict corresponding to the queried parameters
            # pressure_dict = {key: value for key, value in self.pressure_dict.items() if (key in param_list) and (key in self.pressure_channel_IDs)}
            # return pressure_dict
            pressure_dict = {}
            for channel in param_list:
                if channel in self.pressure_channel_IDs:
                    pressure_dict[channel] = self.pressure_dict[channel]
                else:
                    self.log.warn(f'Specified pressure channel not available: {channel}')
            return pressure_dict

    def get_pressure_unit(self, param_list=None):
        """ Gets pressure unit of the corresponding channel or all channels.

        :param list param_list: optional, pressure unit of a specific channel or a list of channels.
                                If None, all channels are queried.
        :return dict: pressure_unit_dict. Keys = channel IDs and values = pressure units for the channel.
        """
        if not param_list:
            return self.pressure_unit_dict
        else:
            pressure_unit_dict = {}
            for channel in param_list:
                if channel in self.pressure_channel_IDs:
                    pressure_unit_dict[channel] = self.pressure_unit_dict[channel]
                else:
                    self.log.warn(f'Specified pressure channel not available: {channel}')
            return pressure_unit_dict

    def get_pressure_range(self, param_list=None):
        """ Gets pressure range of the corresponding channel or all channels.

        :param list param_list: optional, pressure range of a specific channel or a list of channels.
                                If None, all channels are queried.
        :return dict: pressure_range_dict. Keys = channel IDs and values = pressure range as tuple for the channel.
        """
        if not param_list:
            return self.pressure_range_dict
        else:
            pressure_range_dict = {}
            for channel in param_list:
                if channel in self.pressure_channel_IDs:
                    pressure_range_dict[channel] = self.pressure_range_dict[channel]
                else:
                    self.log.warn(f'Specified pressure channel not available: {channel}')
            return pressure_range_dict

# ----------------------------------------------------------------------------------------------------------------------
# Methods for sensor channels
# ----------------------------------------------------------------------------------------------------------------------
    def get_flowrate(self, param_list=None):
        """ Gets current flowrate of the corresponding sensor channel or all sensor channels.

        :param list param_list: optional, flowrate of a specific channel or a list of channels.
                                If None, all channels are queried.
        :return dict: flowrate_dict. Keys = channel IDs and values = flowrate for the channel.
        """
        if not param_list:
            flowrates = [self.pressure_dict[channel] * 5 + 5 * np.random.normal() for channel in self.sensor_channel_IDs]
            flowrate_dict = dict(zip(self.sensor_channel_IDs, flowrates))
            return flowrate_dict
        else:
            flowrate_dict = {}
            for channel in param_list:
                if channel in self.sensor_channel_IDs:
                    flowrate_dict[channel] = self.pressure_dict[channel] * 5 + 5 *np.random.normal()
                else:
                    self.log.warn('Specified sensor channel not available')
            return flowrate_dict

    def get_sensor_unit(self, param_list=None):
        """ Gets sensor unit of the corresponding sensor channel or all sensor channels.

        :param list param_list: optional, sensor unit of a specific channel or a list of channels.
                                If None, all channels are queried.
        :return dict: sensor_unit_dict. Keys = channel IDs and values = sensor unit for the channel.
        """
        if not param_list:
            return self.sensor_unit_dict
        else:
            for channel in param_list:
                if channel in self.sensor_channel_IDs:
                    return self.sensor_unit_dict[channel]
                else:
                    self.log.warn('Specified sensor channel not available')

    def get_sensor_range(self, param_list=None):
        """ Gets sensor range of the corresponding sensor channel or all sensor channels.

        :param list param_list: optional, flowrate range of a specific channel or a list of channels.
                                If None, all channels are queried.
        :return dict: sensor_range_dict. Keys = channel IDs and values = flowrate range as tuple for the channel.
        """
        if not param_list:
            return self.sensor_range_dict
        else:
            for channel in param_list:
                if channel in self.sensor_channel_IDs:
                    return self.sensor_range_dict[channel]
                else:
                    self.log.warn('Specified sensor channel not available')
