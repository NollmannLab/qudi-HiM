# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains the hardware class representing the National Instruments M-Series DAQ.
It is used to control the analog output channels of the DAQ and allows to set up digital output / input
that can be used as trigger for a connected device.

An extension to Qudi.

@author: F. Barho

Created on Tue Jun 30 2020.
Modified by JB Fiche the 15-01-2024 to add new channels controlling the IR laser shutter for the RAMM setup.
Modified by D Guerin the 24-05-2024 to add valve confi for the Fly Arena
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
import PyDAQmx as daq  # this only runs on systems where the niDAQmx library is available
from core.module import Base
from interface.lasercontrol_interface import LasercontrolInterface
from core.configoption import ConfigOption
import numpy as np
from time import sleep, time


class NIDAQMSeries(Base, LasercontrolInterface):
    """ National Instruments DAQ that controls the lasers via an OTF.

    Example config for copy-paste:
        (example for PALM setup)
        nidaq_6259:
            module.Class: 'daq.national_instruments_daq.NIDAQMSeries'
            read_write_timeout: 10
            ao_voltage_range: [0, 10]  # in V
            lasercontrol: True
            wavelengths:
                - '405 nm'
                - '488 nm'
                - '561 nm'
                - '641 nm'
            laser_ao_channels:
                - '/Dev1/AO0'
                - '/Dev1/AO2'
                - '/Dev1/AO1'
                - '/Dev1/AO3'
            trigger_do_channel: '/Dev1/port0/line2'
            trigger_ai_channel: '/Dev1/AI0'

            # please indicate belonging elements in the same order in the categories wavelengths, laser_ao_channels
            # order preferentially by increasing wavelength (this will result in an ordered gui)

        (example for RAMM setup)
        nidaq_6259:
            module.Class: 'daq.national_instruments_daq.NIDAQMSeries'
            read_write_timeout: 10  # in s
            ao_voltage_range: [0, 10]  # in V
            lasercontrol: False
            # ao channels
            piezo_write_ao_channel: 'Dev1/AO1'
            pump_write_ao_channel: 'Dev1/AO0'
            # ai channels
            piezo_read_ai_channel: 'Dev1/AI0'
            # do channels
            start_acquisition_do_channel: '/Dev1/port0/line7'  # DIO3
            # di channels
            acquisition_done_di_channel: '/Dev1/port0/line8'  # DIO4

    """
    # config options
    _rw_timeout = ConfigOption('read_write_timeout', default=10)  # in s
    _ao_voltage_range = ConfigOption('ao_voltage_range', default=(0, 10))
    _lasercontrol = ConfigOption('lasercontrol', default=None)

    # config options used for PALM setup
    _wavelengths = ConfigOption('wavelengths', None)
    _laser_write_ao_channels = ConfigOption('laser_ao_channels', None)
    _trigger_write_do_channel = ConfigOption('trigger_do_channel', None)
    _trigger_read_ai_channel = ConfigOption('trigger_ai_channel', None)

    # config options used for RAMM setup
    _piezo_read_ai_channel = ConfigOption('piezo_read_ai_channel', None)
    _piezo_write_ao_channel = ConfigOption('piezo_write_ao_channel', None)
    _pump_write_ao_channel = ConfigOption('pump_write_ao_channel', None)
    _start_acquisition_do_channel = ConfigOption('start_acquisition_do_channel', None)
    _acquisition_done_di_channel = ConfigOption('acquisition_done_di_channel', None)
    _shutter_write_do_channel = ConfigOption('shutter_write_channel', None)
    _shutter_read_di_channel = ConfigOption('shutter_read_channel', None)

    # config options used for the Fly Arena
    _valve_inlet_1 = ConfigOption('valve_inlet_1', None)
    _valve_outlet_1 = ConfigOption('valve_outlet_1', None)
    _valve_final = ConfigOption('valve_final', None)
    _mixing_valve = ConfigOption('mixing_valve', None)

    # add here eventually other used channels following the naming convention used above

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self.valve_inlet_1_taskhandle = None
        self.valve_outlet_1_taskhandle = None
        self.valve_final_taskhandle = None
        self.mixing_valve_taskhandle = None
        self.laser_ao_taskhandles = {}  # or None
        self.trigger_read_taskhandle = None
        self.trigger_write_taskhandle = None
        self.piezo_read_taskhandle = None
        self.piezo_write_taskhandle = None
        self.pump_write_taskhandle = None
        self.start_acquisition_taskhandle = None
        self.acquisition_done_taskhandle = None
        self.shutter_write_taskhandle = None
        self.shutter_read_taskhandle = None

    def on_activate(self):
        """ Initialization steps when module is called.
        Create taskhandles for all physical channels specified in the configuration and set up the channel according
        to its type.

        :return: None
        """
        # create different tasks if given in config
        if self._lasercontrol:
            # control if the config was correctly specified
            if len(self._laser_write_ao_channels) != len(self._wavelengths):
                self.log.error('Specify equal numbers of laser ao channels and OTF input channels!')

            # create laser analog output tasks and channels
            if self.start_laser_analog_output() < 0:
                self.log.error('Failed to start analog output for lasercontrol')
                raise Exception('Failed to start analog output')

        if self._trigger_write_do_channel:
            try:
                self.trigger_write_taskhandle = self.create_taskhandle()
                self.set_up_do_channel(self.trigger_write_taskhandle,
                                       self._trigger_write_do_channel, name="trigger")
                print('Trigger write digital out channel created!')
            except Exception as err:
                print(f"Unexpected {err}, {type(err)}")
                self.log.error(f'Failed to create do channel for the trigger : {err}')

        if self._trigger_read_ai_channel:
            try:
                self.trigger_read_taskhandle = self.create_taskhandle()
                self.set_up_ai_channel(self.trigger_read_taskhandle, self._trigger_read_ai_channel, self._ao_voltage_range)
                print('Trigger read analog in channel created!')
            except Exception as err:
                print(f"Unexpected {err}, {type(err)}")
                self.log.error(f'Failed to create ai channel for trigger : {err}')

        if self._piezo_write_ao_channel:
            try:
                self.piezo_write_taskhandle = self.create_taskhandle()
                self.set_up_ao_channel(self.piezo_write_taskhandle, self._piezo_write_ao_channel, self._ao_voltage_range)
                print('Piezo write created!')
            except Exception as err:
                print(f"Unexpected {err}, {type(err)}")
                self.log.error(f'Failed to create ao channel for the piezo : {err}')

        if self._piezo_read_ai_channel:
            try:
                self.piezo_read_taskhandle = self.create_taskhandle()
                self.set_up_ai_channel(self.piezo_read_taskhandle, self._piezo_read_ai_channel, self._ao_voltage_range)
                print('Piezo read created!')
            except Exception as err:
                print(f"Unexpected {err}, {type(err)}")
                self.log.error(f'Failed to create ai channel for the piezo : {err}')

        if self._pump_write_ao_channel:
            try:
                self.pump_write_taskhandle = self.create_taskhandle()
                self.set_up_ao_channel(self.pump_write_taskhandle, self._pump_write_ao_channel, [-10, 10])
                # custom ao voltage range for this channel !
                print('Pump write created!')
            except Exception as err:
                print(f"Unexpected {err}, {type(err)}")
                self.log.error(f'Failed to create ao channel for the pump : {err}')

        if self._start_acquisition_do_channel:
            try:
                self.start_acquisition_taskhandle = self.create_taskhandle()
                self.set_up_do_channel(self.start_acquisition_taskhandle, self._start_acquisition_do_channel)  # DIO3 in bitfile for fpga
                print('Start acquisition digital out channel created!')
            except Exception as err:
                print(f"Unexpected {err}, {type(err)}")
                self.log.error(f'Failed to create do channel for starting the acquisition : {err}')

        if self._acquisition_done_di_channel:
            try:
                self.acquisition_done_taskhandle = self.create_taskhandle()
                self.set_up_di_channel(self.acquisition_done_taskhandle, self._acquisition_done_di_channel)
                print('Acquisition done digital in channel created')
            except Exception as err:
                print(f"Unexpected {err}, {type(err)}")
                self.log.error(f'Failed to create di channel to detect the end of acquisition : {err}')

        if self._shutter_write_do_channel:
            try:
                self.shutter_write_taskhandle = self.create_taskhandle()
                self.set_up_do_channel(self.shutter_write_taskhandle, self._shutter_write_do_channel, name="shutter")
                print('Shutter write digital in channel created')
            except Exception as err:
                print(f"Unexpected {err}, {type(err)}")
                print(f'Failed to create do channel for shutter : {err}')

        if self._shutter_read_di_channel:
            try:
                self.shutter_read_taskhandle = self.create_taskhandle()
                self.set_up_di_channel(self.shutter_read_taskhandle, self._shutter_read_di_channel, name="shutter")
                print('Shutter read digital in channel created')
            except Exception as err:
                print(f"Unexpected {err}, {type(err)}")
                print(f'Failed to create di channel for shutter : {err}')

        if self._valve_inlet_1:
            try:
                self.valve_inlet_1_taskhandle = self.create_taskhandle()
                self.set_up_do_channel(self.valve_inlet_1_taskhandle, self._valve_inlet_1, name="valve_in_1")
                print('valve 1 inlet digital in channel created')
            except Exception as err:
                print(f"Unexpected {err}, {type(err)}")
                print(f'Failed to create di channel for valve 1 inlet : {err}')

        if self._valve_outlet_1:
            try:
                self.valve_outlet_1_taskhandle = self.create_taskhandle()
                self.set_up_do_channel(self.valve_outlet_1_taskhandle, self._valve_outlet_1, name="valve_out_1")
                print('valve 1 oulet digital in channel created')
            except Exception as err:
                print(f"Unexpected {err}, {type(err)}")
                print(f'Failed to create di channel for valve 1 outlet: {err}')

        if self._valve_final:
            try:
                self.valve_final_taskhandle = self.create_taskhandle()
                self.set_up_do_channel(self.valve_final_taskhandle, self._valve_final, name="valve_final")
                print('valve final in channel created')
            except Exception as err:
                print(f"Unexpected {err}, {type(err)}")
                print(f'Failed to create di channel for final valve : {err}')

        if self._mixing_valve:
            try:
                self.mixing_valve_taskhandle = self.create_taskhandle()
                self.set_up_do_channel(self.mixing_valve_taskhandle, self._mixing_valve, name="mixing_valve")
                print('mixing valve digital in channel created')
            except Exception as err:
                print(f"Unexpected {err}, {type(err)}")
                print(f'Failed to create di channel for mixing valve : {err}')


    def on_deactivate(self):
        """ Required deactivation when module is closed. Close all tasks and reset taskhandles to null pointers.
        """
        if self._lasercontrol:
            try:
                for channel in self._laser_write_ao_channels:
                    self.close_task(self.laser_ao_taskhandles[channel])
            except Exception as err:
                print(f"Unexpected {err}, {type(err)}")
                self.log.exception('Could not clear laser analog out task.')

        if self._trigger_write_do_channel:
            try:
                self.close_task(self.trigger_write_taskhandle)
            except Exception as err:
                print(f"Unexpected {err}, {type(err)}")
                print('Failed to close do channel')

        if self._trigger_read_ai_channel:
            try:
                self.close_task(self.trigger_read_taskhandle)
            except Exception as err:
                print(f"Unexpected {err}, {type(err)}")
                print('Failed to close ai channel')

        if self._piezo_write_ao_channel:
            try:
                self.close_task(self.piezo_write_taskhandle)
            except Exception as err:
                print(f"Unexpected {err}, {type(err)}")
                print('Failed to close ao channel')

        if self._piezo_read_ai_channel:
            try:
                self.close_task(self.piezo_read_taskhandle)
            except Exception as err:
                print(f"Unexpected {err}, {type(err)}")
                print('Failed to close ai channel')

        if self._pump_write_ao_channel:
            try:
                self.close_task(self.pump_write_taskhandle)
            except Exception as err:
                print(f"Unexpected {err}, {type(err)}")
                print('Failed to close ao channel')

        if self._start_acquisition_do_channel:
            try:
                self.close_task(self.start_acquisition_taskhandle)
            except Exception as err:
                print(f"Unexpected {err}, {type(err)}")
                print('Failed to close do channel')

        if self._acquisition_done_di_channel:
            try:
                self.close_task(self.acquisition_done_taskhandle)
            except Exception as err:
                print(f"Unexpected {err}, {type(err)}")
                print('Failed to close di channel')

        if self._shutter_write_do_channel:
            try:
                self.close_task(self.shutter_write_taskhandle)
            except Exception as err:
                print(f"Unexpected {err}, {type(err)}")
                print('Failed to close do channel for shutter')

        if self._shutter_read_di_channel:
            try:
                self.close_task(self.shutter_read_taskhandle)
            except Exception as err:
                print(f"Unexpected {err}, {type(err)}")
                print('Failed to close di channel for shutter')

        if self._valve_inlet_1:
            try:
                self.close_task(self.valve_inlet_1_taskhandle)
            except Exception as err:
                print(f"Unexpected {err}, {type(err)}")
                print('Failed to close di channel for valve_inlet_1')

        if self._valve_outlet_1:
            try:
                self.close_task(self.valve_outlet_1_taskhandle)
            except Exception as err:
                print(f"Unexpected {err}, {type(err)}")
                print('Failed to close di channel for valve_outlet_1')

        if self._valve_final:
            try:
                self.close_task(self.valve_final_taskhandle)
            except Exception as err:
                print(f"Unexpected {err}, {type(err)}")
                print('Failed to close di channel for valve_final')

        if self._mixing_valve:
            try:
                self.close_task(self.mixing_valve_taskhandle)
            except Exception as err:
                print(f"Unexpected {err}, {type(err)}")
                print('Failed to close di channel for mixing_valve')

        # continue here closing tasks if additional channels are added in the config

# ----------------------------------------------------------------------------------------------------------------------
# DAQ utility functions
# ----------------------------------------------------------------------------------------------------------------------

# Analog output channels -----------------------------------------------------------------------------------------------
    @staticmethod
    def set_up_ao_channel(taskhandle, channel, voltage_range):
        """ Create an analog output virtual channel.

        :param: DAQmx.Taskhandle object taskhandle: pointer to the virtual channel
        :param: str channel: identifier of the physical channel, such as 'Dev1/AO0'
        :param: tuple (float, float) voltage_range: allowed range of voltages for the channel

        :return: None
        """
        daq.DAQmxCreateTask('', daq.byref(taskhandle))
        daq.DAQmxCreateAOVoltageChan(taskhandle, channel, '', voltage_range[0], voltage_range[1], daq.DAQmx_Val_Volts, None)

    def write_to_ao_channel(self, taskhandle, voltage, timeout=None, autostart=True):
        """ Write a voltage to an analog output virtual channel.

        :param: DAQmx.Taskhandle object taskhandle: pointer to the virtual channel
        :param: float voltage: target voltage value to apply to the channel
        :param: float timeout: read / write timeout for reading a channel / writing to a channel in seconds
        :param: bool autostart: True: output starts directly. False can only be used if timing is configured (not the case here)

        :return: None
        """
        if timeout is None:
            timeout = self._rw_timeout

        daq.WriteAnalogScalarF64(taskhandle, autostart, timeout, voltage,
                                 None)  # parameters passed in: taskHandle, autoStart, timeout, value, reserved
        daq.DAQmxStartTask(taskhandle)
        daq.DAQmxStopTask(taskhandle)

# Analog input channels ------------------------------------------------------------------------------------------------
    @staticmethod
    def set_up_ai_channel(taskhandle, channel, voltage_range):
        """ Create an analog input virtual channel.

        :param: DAQmx.Taskhandle object taskhandle: pointer to the virtual channel
        :param: str channel: identifier of the physical channel, such as 'Dev1/AI0'
        :param: tuple (float, float) voltage_range: allowed range of voltages for the channel

        :return: None
        """
        daq.DAQmxCreateTask('', daq.byref(taskhandle))
        daq.DAQmxCreateAIVoltageChan(taskhandle, channel, '', daq.DAQmx_Val_RSE, voltage_range[0], voltage_range[1],
                                     daq.DAQmx_Val_Volts, None)

    def read_ai_channel(self, taskhandle):
        """ Read a value from an analog input virtual channel.

        :param: DAQmx.Taskhandle object taskhandle: pointer to the virtual channel

        :return: float data: value read from the ai channel
        """
        data = np.zeros((1,), dtype=np.float64)
        read = daq.c_int32()
        daq.DAQmxStartTask(taskhandle)
        daq.DAQmxReadAnalogF64(taskhandle,   # taskhandle
                           1,  # num_samples per channel # default value -1: all available samples
                           self._rw_timeout,  # timeout
                           daq.DAQmx_Val_GroupByChannel,  # fillMode
                           data,  # the array to read samples into, organized according to fillMode
                           1,  # the size of the array in samples into which samples are read
                           daq.byref(read),  # the actual number of samples read from each channel
                           None)  # reserved
        daq.DAQmxStopTask(taskhandle)
        return data[0]

# Digital output channels ----------------------------------------------------------------------------------------------
    @staticmethod
    def set_up_do_channel(taskhandle, channel, name=""):
        """ Create a digital output virtual channel.

        :param: DAQmx.Taskhandle object taskhandle: pointer to the virtual channel
        :param: str channel: identifier of the physical channel, such as 'Dev1/DIO0'

        :return: None
        """
        daq.DAQmxCreateTask(f'DigitalOut_{name}', daq.byref(taskhandle))
        daq.DAQmxCreateDOChan(taskhandle, channel, '', daq.DAQmx_Val_ChanForAllLines)  # last argument: line grouping

    def write_to_do_channel(self, taskhandle, num_samp, digital_write):
        """ Write a value to a digital output virtual channel.

        :param: DAQmx.Taskhandle object taskhandle: pointer to the virtual channel
        :param: int num_samp: number of values to write
        :param: np.ndarray digital_write: np array containing the values to write, using dtype=np.uint8

        :return: float digital_read: samples successfully written
        """
        num_samples_per_channel = daq.c_int32(num_samp)
        digital_read = daq.c_int32()
        daq.DAQmxStartTask(taskhandle)
        daq.DAQmxWriteDigitalLines(taskhandle,  # taskhandle
                                   num_samples_per_channel,  # number of samples to write per channel
                                   True,  # autostart
                                   self._rw_timeout,  # time to wait to write all the samples
                                   daq.DAQmx_Val_GroupByChannel,
                                   # dataLayout: non-interleaved: all samples for first channel, all samples for second channel, ...
                                   digital_write,  # array of 32 bit integer samples to write to the task
                                   daq.byref(digital_read),  # samples per channel successfully written
                                   None)  # reserved for futur use
        daq.DAQmxStopTask(taskhandle)
        return digital_read  # or digital_read.value ??  # maybe not needed

# Digital input channels -----------------------------------------------------------------------------------------------
    @staticmethod
    def set_up_di_channel(taskhandle, channel, name=""):
        """ Create a digital input virtual channel.

        :param: DAQmx.Taskhandle object taskhandle: pointer to the virtual channel
        :param: str channel: identifier of the physical channel, such as 'Dev1/DIO0'

        :return: None
        """
        daq.DAQmxCreateTask(f'DigitalIn_{name}', daq.byref(taskhandle))
        daq.DAQmxCreateDIChan(taskhandle, channel, '', daq.DAQmx_Val_ChanPerLine)  # last argument: line grouping

    def read_di_channel(self, taskhandle, num_samp):
        """ Read a value from a digital input virtual channel.

        :param: DAQmx.Taskhandle object taskhandle: pointer to the virtual channel
        :param: int num_samp: number of values to write

        :return: float data: values read from the digital input channel
        """
        num_samples_per_channel = daq.c_int32(num_samp)
        sampsPerChanRead = daq.c_int32()
        numBytesPerSamp = daq.c_int32()
        data = np.zeros((num_samp,), dtype=np.uint8)
        daq.DAQmxStartTask(taskhandle)
        daq.DAQmxReadDigitalLines(taskhandle, num_samples_per_channel, self._rw_timeout, daq.DAQmx_Val_GroupByChannel, data,
                                  num_samp, sampsPerChanRead, numBytesPerSamp, None)
        daq.DAQmxStopTask(taskhandle)
        return data

# Method for all types of channels -------------------------------------------------------------------------------------
    @staticmethod
    def close_task(taskhandle):
        """ Stop and clear a task identified by taskhandle. Reset the taskhandle as nullpointer.
        :param: DAQmx.Taskhandle object taskhandle: pointer to the virtual channel
        """
        daq.DAQmxStopTask(taskhandle)
        daq.DAQmxClearTask(taskhandle)
        taskhandle.value = None

# ----------------------------------------------------------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def create_taskhandle():
        """ Create a new taskhandle object.

        :return: DAQmx.Taskhandle object taskhandle
        """
        taskhandle = daq.TaskHandle()
        if taskhandle.value is not None:
            # stop analog output task
            daq.DAQmxStopTask(taskhandle)
            # delete the configuration of the analog task
            daq.DAQmxClearTask(taskhandle)
            # set the task handle to None as a safety
            taskhandle.value = None
        return taskhandle

    def start_laser_analog_output(self):
        """ Creates for each physical channel used for laser control a task and its virtual channel.

        :return: error code: ok = 0, error = -1
        """
        try:
            # create a dictionary with physical channel name as key and a pointer as value {'/Dev1/AO0': c_void_p(None), ... }
            self.laser_ao_taskhandles = dict([(name, self.create_taskhandle()) for name in self._laser_write_ao_channels])

            # create an individual task and a channel per analog output
            for channel in self._laser_write_ao_channels:
                daq.DAQmxCreateTask('', daq.byref(self.laser_ao_taskhandles[channel]))
                daq.DAQmxCreateAOVoltageChan(self.laser_ao_taskhandles[channel], channel, '', self._ao_voltage_range[0],
                                             self._ao_voltage_range[1], daq.DAQmx_Val_Volts, None)
        except Exception:
            self.log.exception('Error starting analog output task.')
            return -1
        return 0

# ----------------------------------------------------------------------------------------------------------------------
# Lasercontrol Interface functions
# ----------------------------------------------------------------------------------------------------------------------

    def apply_voltage(self, voltage, channel):
        """ Writes a voltage to the specified channel.

        :param: float voltage: voltage value to be applied
        :param: str channel: analog output line such as /Dev1/AO0

        :return: None
        """
        self.write_to_ao_channel(self.laser_ao_taskhandles[channel], voltage)

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
                         'channel': self._laser_write_ao_channels[i],
                         'ao_voltage_range': self._ao_voltage_range}

            laser_dict[dic_entry['label']] = dic_entry

        return laser_dict

# ----------------------------------------------------------------------------------------------------------------------
# Various functionality of DAQ
# ----------------------------------------------------------------------------------------------------------------------

# functions used on PALM setup -----------------------------------------------------------------------------------------

    def send_trigger(self):
        """ This method sends a sequence of digital output values [0, 1, 0] as trigger.

        It uses a waiting time to ensure that the signal can be received
        (typical application: camera acquisition triggered by daq)

        :return: None
        """
        self.write_to_do_channel(self.trigger_write_taskhandle, 1, np.array([0], dtype=np.uint8))
        sleep(0.001)  # waiting time in s
        self.write_to_do_channel(self.trigger_write_taskhandle, 1, np.array([1], dtype=np.uint8))
        sleep(0.001)  # waiting time in s
        self.write_to_do_channel(self.trigger_write_taskhandle, 1, np.array([0], dtype=np.uint8))
        sleep(0.001)  # waiting time in s

    def send_trigger_and_control_ai(self):
        """ This method sends a sequence of digital output values [0, 1, 0] as trigger, and verifies if the analog
        input signal (typically fire trigger of camera) was received before resetting the digital output to 0.
        If not received, digital output is also reset to 0 in order to be able to continue normally,
        but the user is informed that the input was not received.

        This method uses a waiting time to ensure that the signal can be received
        (typical application: camera acquisition triggered by daq)

        :return: int error code: 0 = ok, -1 = analog in signal not received
        """
        if self.trigger_read_taskhandle is None:
            self.log.info('No analog input task configured')
        else:
            self.write_to_do_channel(self.trigger_write_taskhandle, 1, np.array([0], dtype=np.uint8))
            sleep(0.001)  # waiting time in s
            self.write_to_do_channel(self.trigger_write_taskhandle, 1, np.array([1], dtype=np.uint8))
            sleep(0.001)  # waiting time in s
            ai_read = self.read_ai_channel(self.trigger_read_taskhandle)
            if ai_read > 2.5:
                self.write_to_do_channel(self.trigger_write_taskhandle, 1, np.array([0], dtype=np.uint8))
                sleep(0.001)  # waiting time in s
                return 0
            else:
                self.log.info('fire not received')
                self.write_to_do_channel(self.trigger_write_taskhandle, 1, np.array([0], dtype=np.uint8))
                sleep(0.001)  # waiting time in s
                return -1

# functions used on RAMM setup -----------------------------------------------------------------------------------------

    def read_piezo(self):
        """ Read the voltage applied to the channel controlling the piezo.

        :return: float value: voltage applied to the piezo.
        """
        value = self.read_ai_channel(self.piezo_read_taskhandle)
        return value

    def move_piezo(self, pos):
        """ Move the piezo to the indicated position.

        :param: float position: expected position of the piezo

        :return: None
        """
        if 0 <= pos <= 90:
            voltage = pos/10
            self.write_to_ao_channel(self.piezo_write_taskhandle, voltage)
        else:
            self.log.warning('Piezo target position out of boundaries')

    def write_to_rinsing_pump_channel(self, voltage):
        """ Start / Stop the needle rinsing pump by applying the target voltage.

        :param: float voltage: target voltage to apply to the pump channel

        :return: None
        """
        if -10 <= voltage <= 10:  # allow here a different range from the ao range given in config.
            self.write_to_ao_channel(self.pump_write_taskhandle, voltage)
        else:
            self.log.warning('Voltage not in allowed range.')

    def write_laser_shutter(self, state):
        """ Control the state of the laser shutter placed in front of the IR laser.

        @param state: (int) 0 = close the shutter / 1 = open the shutter
        """
        if state:
            self.write_to_do_channel(self.shutter_write_taskhandle, 1, np.array([1], dtype=np.uint8))
        else:
            self.write_to_do_channel(self.shutter_write_taskhandle, 1, np.array([0], dtype=np.uint8))

    def read_laser_shutter(self):
        """ Read the state of the laser shutter. In the TSC001 default mode, trigger input and output have opposite
         senses. Therefore, when the shutter is open (trigger IN equal to 1), trigger OUT will be equal to 0.

        @return: shutter_state(bool): 0 : shutter is close / 1 : shutter is open
        """
        shutter_state = 1 - self.read_di_channel(self.shutter_read_taskhandle, 1)[0]
        return shutter_state