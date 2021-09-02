# -*- coding: utf-8 -*-
"""
Qudi-CBS

This file contains a class for the Measurement Computing DAQ.

An extension to Qudi.

@author: F. Barho

Created on Wed June 6 2021
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
from time import sleep
from mcculw import ul
from mcculw.enums import ULRange, DigitalIODirection, InterfaceType
from mcculw.ul import ULError
from mcculw.device_info import DaqDeviceInfo

from core.module import Base
from core.configoption import ConfigOption


class MccDAQ(Base):
    """ Class representing the measurement computing DAQ.

    Example config for copy-paste:
        mcc_daq:
            module.Class: 'daq.measurement_computing_daq.MccDAQ'
            rinsing_pump_channel: 0
            fluidics_pump_channel: 1

    """

    # config options
    # ao channels
    rinsing_pump_channel = ConfigOption('rinsing_pump_channel', None, missing='warn')
    fluidics_pump_channel = ConfigOption('fluidics_pump_channel', None, missing='warn')

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

    # def __init__(self, *args, **kwargs):
    #     super().__init__(*args, **kwargs)

    def on_activate(self):
        """ Initialization steps when module is called.
        """
        ul.ignore_instacal()
        devices = ul.get_daq_device_inventory(InterfaceType.ANY)
        if not devices:
            raise Exception('Error: No DAQ devices found')

        print('Found', len(devices), 'DAQ device(s):')
        for device in devices:
            print('  ', device.product_name, ' (', device.unique_id, ') - ',
                  'Device ID = ', device.product_id, sep='')

        device = devices[0]
        self.board_num = 0

        # Add the first DAQ device to the UL with the specified board number
        ul.create_daq_device(self.board_num, device)

    def on_deactivate(self):
        """ Required deactivation steps.
        """
        ul.release_daq_device(self.board_num)

# ----------------------------------------------------------------------------------------------------------------------
# DAQ utility functions
# ----------------------------------------------------------------------------------------------------------------------

# Analog output channels -----------------------------------------------------------------------------------------------
    def write_to_ao_channel(self, voltage, channel):
        daq_dev_info = DaqDeviceInfo(self.board_num)
        if not daq_dev_info.supports_analog_output:
            raise Exception('Error: The DAQ device does not support '
                            'analog output')
        ao_info = daq_dev_info.get_ao_info()
        print(ao_info.supported_ranges)
        ao_range = ao_info.supported_ranges[0]
        print(ao_range)

        print('Outputting', voltage, 'Volts to channel', channel)
        # Send the value to the device (optional parameter omitted)
        ul.v_out(self.board_num, channel, ao_range, voltage)

# Analog input channels ------------------------------------------------------------------------------------------------
    # no ai channels for this daq
    def read_ai_channel(self, channel):
        daq_dev_info = DaqDeviceInfo(self.board_num)
        if not daq_dev_info.supports_analog_input:
            raise Exception('Error: The DAQ device does not support '
                            'analog input')

# Digital output channels ----------------------------------------------------------------------------------------------
    def set_up_do_channel(self):
        daq_dev_info = DaqDeviceInfo(self.board_num)
        if not daq_dev_info.supports_digital_io:
            raise Exception('Error: The DAQ device does not support '
                            'digital I/O')

        print('\nActive DAQ device: ', daq_dev_info.product_name, ' (',
              daq_dev_info.unique_id, ')\n', sep='')

        dio_info = daq_dev_info.get_dio_info()
        print(dio_info)

        # Find the first port that supports input, defaulting to None
        # if one is not found.
        port = next((port for port in dio_info.port_info if port.supports_output),
                    None)
        if not port:
            raise Exception('Error: The DAQ device does not support '
                            'digital output')

        # If the port is configurable, configure it for output.
        if port.is_port_configurable:
            ul.d_config_port(self.board_num, port.type, DigitalIODirection.OUT)

    def write_to_do_channel(self):
        pass

# Digital input channels -----------------------------------------------------------------------------------------------
    def set_up_di_channel(self):
        daq_dev_info = DaqDeviceInfo(self.board_num)
        if not daq_dev_info.supports_digital_io:
            raise Exception('Error: The DAQ device does not support digital I/O')

        dio_info = daq_dev_info.get_dio_info()
        print(dio_info)

        print(f'port info: {dio_info.port_info}')
        print([port for port in dio_info.port_info if port.supports_input])

        # Find the first port that supports input, defaulting to None
        # if one is not found.
        port = next((port for port in dio_info.port_info if port.supports_input), None)
        if not port:
            raise Exception('Error: The DAQ device does not support digital input')
        print(port)

        # If the port is configurable, configure it for input.
        if port.is_port_configurable:
            ul.d_config_port(self.board_num, port.type, DigitalIODirection.IN)

    def read_di_channel(self):
        daq_dev_info = DaqDeviceInfo(self.board_num)
        dio_info = daq_dev_info.get_dio_info()
        # port = next((port for port in dio_info.port_info if port.supports_input), None)
        ports = [port for port in dio_info.port_info if port.supports_input]
        print(ports)
        # Get a value from the digital port
        port_value = ul.d_in(self.board_num, ports[0].type)
        print(port_value)



    # def read_di(self):
    #     # By default, the example detects and displays all available devices and
    #     # selects the first device listed. Use the dev_id_list variable to filter
    #     # detected devices by device ID (see UL documentation for device IDs).
    #     # If use_device_detection is set to False, the board_num variable needs to
    #     # match the desired board number configured with Instacal.
    #     use_device_detection = True
    #     dev_id_list = []
    #     board_num = 0
    #
    #     try:
    #         if use_device_detection:
    #             self.config_first_detected_device(board_num, dev_id_list)
    #
    #         daq_dev_info = DaqDeviceInfo(board_num)
    #         if not daq_dev_info.supports_digital_io:
    #             raise Exception('Error: The DAQ device does not support '
    #                             'digital I/O')
    #
    #         print('\nActive DAQ device: ', daq_dev_info.product_name, ' (',
    #               daq_dev_info.unique_id, ')\n', sep='')
    #
    #         dio_info = daq_dev_info.get_dio_info()
    #
    #         # Find the first port that supports input, defaulting to None
    #         # if one is not found.
    #         port = next((port for port in dio_info.port_info if port.supports_input),
    #                     None)
    #         if not port:
    #             raise Exception('Error: The DAQ device does not support '
    #                             'digital input')
    #
    #         # If the port is configurable, configure it for input.
    #         if port.is_port_configurable:
    #             ul.d_config_port(board_num, port.type, DigitalIODirection.IN)
    #
    #         # Get a value from the digital port
    #         port_value = ul.d_in(board_num, port.type)
    #
    #         # Get a value from the first digital bit
    #         bit_num = 0
    #         bit_value = ul.d_bit_in(board_num, port.type, bit_num)
    #
    #         # Display the port value
    #         print(port.type.name, 'Value:', port_value)
    #         # Display the bit value
    #         print('Bit', bit_num, 'Value:', bit_value)
    #     except Exception as e:
    #         print('\n', e)
    #     finally:
    #         if use_device_detection:
    #             ul.release_daq_device(board_num)
    # #
    # def write_do():
    #     # By default, the example detects and displays all available devices and
    #     # selects the first device listed. Use the dev_id_list variable to filter
    #     # detected devices by device ID (see UL documentation for device IDs).
    #     # If use_device_detection is set to False, the board_num variable needs to
    #     # match the desired board number configured with Instacal.
    #     use_device_detection = True
    #     dev_id_list = []
    #     board_num = 0
    #
    #     try:
    #         if use_device_detection:
    #             self.config_first_detected_device(board_num, dev_id_list)
    #
    #         daq_dev_info = DaqDeviceInfo(board_num)
    #         if not daq_dev_info.supports_digital_io:
    #             raise Exception('Error: The DAQ device does not support '
    #                             'digital I/O')
    #
    #         print('\nActive DAQ device: ', daq_dev_info.product_name, ' (',
    #               daq_dev_info.unique_id, ')\n', sep='')
    #
    #         dio_info = daq_dev_info.get_dio_info()
    #
    #         # Find the first port that supports input, defaulting to None
    #         # if one is not found.
    #         port = next((port for port in dio_info.port_info if port.supports_output),
    #                     None)
    #         if not port:
    #             raise Exception('Error: The DAQ device does not support '
    #                             'digital output')
    #
    #         # If the port is configurable, configure it for output.
    #         if port.is_port_configurable:
    #             ul.d_config_port(board_num, port.type, DigitalIODirection.OUT)
    #
    #         port_value = 0xFF
    #
    #         print('Setting', port.type.name, 'to', port_value)
    #
    #         # Output the value to the port
    #         ul.d_out(board_num, port.type, port_value)
    #
    #         bit_num = 0
    #         bit_value = 0
    #         print('Setting', port.type.name, 'bit', bit_num, 'to', bit_value)
    #
    #         # Output the value to the bit
    #         ul.d_bit_out(board_num, port.type, bit_num, bit_value)
    #
    #     except Exception as e:
    #         print('\n', e)
    #     finally:
    #         if use_device_detection:
    #             ul.release_daq_device(board_num)

# ----------------------------------------------------------------------------------------------------------------------
# Various functionality of DAQ
# ----------------------------------------------------------------------------------------------------------------------

# Needle rinsing pump---------------------------------------------------------------------------------------------------
    def write_to_rinsing_pump_channel(self, voltage):
        """ Start / Stop the needle rinsing pump

        :param: float voltage: target voltage to apply to the channel

        :return: None
        """
        if voltage >= 0 and voltage <= 10: # replace by reading limits from device
            self.write_to_ao_channel(voltage, self.rinsing_pump_channel)
        else:
            self.log.warning('Voltage not in allowed range.')

# Flowcontrol pump------------------------------------------------------------------------------------------------------
    def write_to_fluidics_pump_channel(self, voltage):
        if voltage >= 0 and voltage <= 10: # replace by reading limits from device
            self.write_to_ao_channel(voltage, self.fluidics_pump_channel)
        else:
            self.log.warning('Voltage not in allowed range.')



if __name__ == '__main__':
    mcc_daq = MccDAQ()
    mcc_daq.on_activate()
    # mcc_daq.write_to_ao_channel(0, 0)
    mcc_daq.write_to_pump_ao_channel(1)
    sleep(2)
    mcc_daq.write_to_pump_ao_channel(0)

    mcc_daq.write_to_fluidics_pump_ao_channel(1)
    sleep(2)
    mcc_daq.write_to_fluidics_pump_ao_channel(0)

    mcc_daq.on_deactivate()
    # mcc_daq.config_first_detected_device(0)
    # mcc_daq.read_ai()
    # mcc_daq.read_di()
    # mcc_daq.read_value()
    # mcc_daq.run_example()
    # mcc_daq.digital_in_example()