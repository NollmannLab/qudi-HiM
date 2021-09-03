# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains the dummy implementation of a DAQ.

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
from core.module import Base
from core.configoption import ConfigOption
from interface.lasercontrol_interface import LasercontrolInterface


class DummyDaq(Base, LasercontrolInterface):
    """ Dummy DAQ with analog output channels for the control of an OTF, and various other functions
    to simulate DAQ hardware functionality.

    Example config for copy-paste:
        dummy_daq:
            module.Class: 'daq.dummy_daq.DummyDaq'
            wavelengths:
                - '405 nm'
                - '488 nm'
                - '512 nm'
                - '633 nm'
            ao_channels:
                - '/Dev1/AO0'
                - '/Dev1/AO1'
                - '/Dev1/AO2'
                - '/Dev1/AO3'
            ao_voltage_ranges:
                - [0, 10]
                - [0, 10]
                - [0, 10]
                - [0, 10]


            # please give belonging elements in the same order in each category ao_channels, voltage_ranges, wavelengths
    """
    # config options
    _ao_channels = ConfigOption('ao_channels', missing='error')  # list  ['/Dev1/AO0', '/Dev1/AO1', ..]
    _ao_voltage_ranges = ConfigOption('ao_voltage_ranges', missing='error')  # list of lists [[0, 10], [0, 10], ..]
    _wavelengths = ConfigOption('wavelengths', missing='error')

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

    def on_activate(self):
        """ Initialization steps when module is called.
        """
        if (len(self._ao_channels) != len(self._ao_voltage_ranges)) or (len(self._ao_channels) != len(self._wavelengths)):
            self.log.error('Specify equal numbers of ao channels, voltage ranges and OTF input channels!')

    def on_deactivate(self):
        """ Required deactivation.
        """
        pass

# ----------------------------------------------------------------------------------------------------------------------
# Lasercontrol Interface functions
# ----------------------------------------------------------------------------------------------------------------------

    def get_dict(self):
        """ Retrieves the channel name and the voltage range for each analog output for laser control from the
        configuration file and associates it to the laser wavelength which is controlled by this channel.

        Make sure that the config contains all the necessary elements.

        :return: dict laser_dict
        """
        laser_dict = {}

        for i, item in enumerate(
                self._wavelengths):  # use any of the lists retrieved as config option, just to have an index variable
            label = 'laser{}'.format(i + 1)  # create a label for the i's element in the list starting from 'laser1'

            dic_entry = {'label': label,
                         'wavelength': self._wavelengths[i],
                         'channel': self._ao_channels[i],
                         'ao_voltage_range': self._ao_voltage_ranges[i]}

            laser_dict[dic_entry['label']] = dic_entry

        return laser_dict

    def apply_voltage(self, voltage, channel):
        """ Writes a voltage to the specified channel.

        :param: float voltage: voltage value to be applied
        :param: str channel: analog output line such as /Dev1/AO0

        :return: None
        """
        print(f'Applied {voltage} V to channel {channel}.')

    def set_up_do_channel(self, taskhandle, channel):
        """ Create a digital output virtual channel.

        :param: DAQmx.Taskhandle object taskhandle: pointer to the virtual channel
        :param: str channel: identifier of the physical channel, such as 'Dev1/DIO0'

        :return: None
        """
        pass

    def close_task(self, taskhandle):
        """ Stop and clear a task identified by taskhandle. Reset the taskhandle as nullpointer.
        :param: DAQmx.Taskhandle object taskhandle: pointer to the virtual channel
        """
        pass

# ----------------------------------------------------------------------------------------------------------------------
# Various functionality of DAQ
# ----------------------------------------------------------------------------------------------------------------------

    def send_trigger(self):
        """ Simulates sending a trigger.
        :return: None
        """
        self.log.info('Send trigger called')

    def write_to_rinsing_pump_channel(self, voltage):
        """ Start / Stop the needle rinsing pump by applying the target voltage.

        :param: float voltage: target voltage to apply to the pump channel

        :return: None
        """
        pass
