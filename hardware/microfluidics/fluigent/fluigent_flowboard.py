# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains the hardware class representing the Fluigent flowboard.

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
import Fluigent.SDK as fgt  # only supported on Windows
from core.module import Base
from interface.microfluidics_interface import MicrofluidicsInterface
from core.configoption import ConfigOption


class FluigentFlowboard(Base, MicrofluidicsInterface):
    """ Hardware class representing the Fluigent Microfluidics Controller (Flowboard).

    Example config for copy-paste:

    fluigent_flowboard:
        module.Class: 'microfluidics.fluigent.fluigent_flowboard.FluigentFlowboard'
        pressure_channel_IDs:
            - 0
        sensor_channel_IDs:
            - 0
    """
    # config options
    pressure_channel_IDs = ConfigOption('pressure_channel_IDs', missing='error')
    sensor_channel_IDs = ConfigOption('sensor_channel_IDs', missing='error')

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

    def on_activate(self):
        """ Initialisation performed during activation of the module, connecting the flowboard.
        """
        # Detect all controllers
        SNs, types = fgt.fgt_detect()
        controller_count = len(SNs)
        self.log.debug('Number of controllers detected: {}'.format(controller_count))

        # initialize controllers
        fgt.fgt_init()
        # add here the check if an error was raised during fgt_init and write a comprehensible error message to the log.

        num_pressure_channels = fgt.fgt_get_pressureChannelCount()
        if num_pressure_channels < len(self.pressure_channel_IDs):
            self.log.warning('Less pressure channels detected than given in config file!')

        num_sensor_channels = fgt.fgt_get_sensorChannelCount()
        if num_sensor_channels < len(self.sensor_channel_IDs):
            self.log.warning('Less sensor channels detected than given in config file!')

        # ## Get detailed information about all controllers
        #
        # controllerInfoArray = fgt.fgt_get_controllersInfo()
        # for i, controllerInfo in enumerate(controllerInfoArray):
        #     print('Controller info at index: {}'.format(i))
        #     print(controllerInfo)
        #
        # ## Get detailed information about all pressure channels
        #
        # pressureInfoArray = fgt.fgt_get_pressureChannelsInfo()
        # for i, pressureInfo in enumerate(pressureInfoArray):
        #     print('Pressure channel info at index: {}'.format(i))
        #     print(pressureInfo)
        # #
        # # ## Get detailed information about all sensor channels
        # #
        # sensorInfoArray, sensorTypeArray = fgt.fgt_get_sensorChannelsInfo()
        # for i, sensorInfo in enumerate(sensorInfoArray):
        #     print('Sensor channel info at index: {}'.format(i))
        #     print(sensorInfo)
        #     print("Sensor type: {}".format(sensorTypeArray[i]))
        #

    def on_deactivate(self):
        """ Close connection to hardware. """
        fgt.fgt_close()

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
                max_pressure = self.get_pressure_range([key])[key][1]  # the second value [1] in the pressure range tuple is the maximum
                if value <= max_pressure:  # check if target value in allowed range
                    fgt.fgt_set_pressure(key, value)
                else:
                    self.log.warn('Pressure not set. Target value above allowed range.')
            else:
                self.log.warn('Specified pressure channel not available')

    def get_pressure(self, param_list=None):
        """ Gets current pressure of the corresponding channel or all channels.

        :param list param_list: optional, pressure of a specific channel or a list of channels.
                                If None, all channels are queried.
        :return dict: pressure_dict. Keys = channel IDs and values = pressure value for the channel.
        """
        if not param_list:
            pressures = [fgt.fgt_get_pressure(channel) for channel in self.pressure_channel_IDs]
            pressure_dict = dict(zip(self.pressure_channel_IDs, pressures))
            return pressure_dict
        else:
            pressure_dict = {}
            for channel in param_list:
                if channel in self.pressure_channel_IDs:
                    pressure = fgt.fgt_get_pressure(channel)
                    pressure_dict[channel] = pressure
                else:
                    self.log.warn('Specified pressure channel not available')
            return pressure_dict

    def get_pressure_unit(self, param_list=None):
        """ Gets pressure unit of the corresponding channel or all channels.

        :param list param_list: optional, pressure unit of a specific channel or a list of channels.
                                If None, all channels are queried.
        :return dict: pressure_unit_dict. Keys = channel IDs and values = pressure units for the channel.
        """
        if not param_list:
            pressure_units = [fgt.fgt_get_pressureUnit(channel) for channel in self.pressure_channel_IDs]
            pressure_unit_dict = dict(zip(self.pressure_channel_IDs, pressure_units))
            return pressure_unit_dict
        else:
            pressure_unit_dict = {}
            for channel in param_list:
                if channel in self.pressure_channel_IDs:
                    pressure_unit = fgt.fgt_get_pressureUnit(channel)
                    pressure_unit_dict[channel] = pressure_unit
                else:
                    self.log.warn('Specified pressure channel not available')
            return pressure_unit_dict

    def get_pressure_range(self, param_list=None):
        """ Gets pressure range of the corresponding channel or all channels.

        :param list param_list: optional, pressure range of a specific channel or a list of channels.
                                If None, all channels are queried.
        :return dict: pressure_range_dict. Keys = channel IDs and values = pressure range as tuple for the channel.
        """
        if not param_list:
            pressure_range = [fgt.fgt_get_pressureRange(channel) for channel in self.pressure_channel_IDs]
            pressure_range_dict = dict(zip(self.pressure_channel_IDs, pressure_range))
            return pressure_range_dict
        else:
            pressure_range_dict = {}
            for channel in param_list:
                if channel in self.pressure_channel_IDs:
                    pressure_range = fgt.fgt_get_pressureRange(channel)
                    pressure_range_dict[channel] = pressure_range
                else:
                    self.log.warn('Specified pressure channel not available')
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
            flowrates = [fgt.fgt_get_sensorValue(channel) for channel in self.sensor_channel_IDs]
            flowrate_dict = dict(zip(self.sensor_channel_IDs, flowrates))
            return flowrate_dict
        else:
            flowrate_dict = {}
            for channel in param_list:
                if channel in self.sensor_channel_IDs:
                    flowrate = fgt.fgt_get_sensorValue(channel)
                    flowrate_dict[channel] = flowrate
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
            sensor_units = [fgt.fgt_get_sensorUnit(channel) for channel in self.sensor_channel_IDs]
            sensor_unit_dict = dict(zip(self.sensor_channel_IDs, sensor_units))
            return sensor_unit_dict
        else:
            sensor_unit_dict = {}
            for channel in param_list:
                if channel in self.sensor_channel_IDs:
                    sensor_unit = fgt.fgt_get_sensorUnit(channel)
                    sensor_unit_dict[channel] = sensor_unit
                else:
                    self.log.warn('Specified sensor channel not available')
            return sensor_unit_dict

    def get_sensor_range(self, param_list=None):
        """ Gets sensor range of the corresponding sensor channel or all sensor channels.

        :param list param_list: optional, flowrate range of a specific channel or a list of channels.
                                If None, all channels are queried.
        :return dict: sensor_range_dict. Keys = channel IDs and values = flowrate range as tuple for the channel.
        """
        if not param_list:
            sensor_range = [fgt.fgt_get_sensorRange(channel) for channel in self.sensor_channel_IDs]
            sensor_range_dict = dict(zip(self.sensor_channel_IDs, sensor_range))
            return sensor_range_dict
        else:
            sensor_range_dict = {}
            for channel in param_list:
                if channel in self.sensor_channel_IDs:
                    sensor_range = fgt.fgt_get_sensorRange(channel)
                    sensor_range_dict[channel] = sensor_range
                else:
                    self.log.warn('Specified sensor channel not available')
            return sensor_range_dict


# to do: use of error codes and exception handling
