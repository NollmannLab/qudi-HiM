#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Oct 23 08:00:40 2020

@author: barho

This file contains a class for the NI-DAQ M series.

It is used to control the analog output channels of the DAQ
and allows to set up a digital output that can be used as trigger for a connected device.

This module is an extension to the hardware code base of Qudi software 
obtained from <https://github.com/Ulm-IQO/qudi/> 
"""

# import nidaqmx
import PyDAQmx as daq  # this only runs on systems where the niDAQmx library is available
from core.module import Base
from interface.lasercontrol_interface import LasercontrolInterface
from core.configoption import ConfigOption
import numpy as np
from time import sleep


class NIDAQMSeries(Base, LasercontrolInterface):
    """ National Instruments DAQ that controls the lasers via an OTF.
    
    Example config for copy-paste:
        nidaq_6259:
            module.Class: 'daq.national_instruments_m_series.NIDAQMSeries'
            wavelengths:
                - '405 nm'
                - '488 nm'
                - '561 nm'
                - '641 nm'
            ao_channels:
                - '/Dev1/AO0'
                - '/Dev1/AO2'
                - '/Dev1/AO1'
                - '/Dev1/AO3'
            ao_voltage_ranges: 
                - [0, 10]
                - [0, 10]
                - [0, 10]
                - [0, 10]
            read_write_timeout: 10
            do_channel: '/Dev1/port0/line2'  # 'Dev1/port0/line2'
            ai_channel: '/Dev1/AI0'
            
            # please indicate belonging elements in the same order in each category wavelengths, ao_channels, voltage_ranges
            # order preferentially by increasing wavelength (this will result in an ordered gui)
    """
    
    # config
    _wavelengths = ConfigOption('wavelengths', missing='error')
    _ao_channels = ConfigOption('ao_channels', missing='error')
    _ao_voltage_ranges = ConfigOption('ao_voltage_ranges', missing='error')
    _do_channel = ConfigOption('do_channel', missing='warn')
    _ai_channel = ConfigOption('ai_channel', missing='warn')
    # timeout for the Read or/and write process in s
    _RWTimeout = ConfigOption('read_write_timeout', default=10)

    # def __init__(self, config, **kwargs):
    #     super().__init__(config=config, **kwargs)

    def on_activate(self):
        """ Initialization steps when module is called.
        """
        # initialize taskhandles for ao and do tasks
        self.ao_taskhandles = list()
        self.digital_out_taskhandle = None
        self.analog_in_taskhandle = None
        
        # control if the config was correctly specified
        if (len(self._ao_channels) != len(self._ao_voltage_ranges)) or (len(self._ao_channels) != len(self._wavelengths)):
            self.log.error('Specify equal numbers of ao channels, voltage ranges and OTF input channels!')

        # create analog output tasks and channels
        if self._start_analog_output() < 0:
            self.log.error('Failed to start analog output')
            raise Exception('Failed to start analog output')

    def _start_analog_output(self):
        """ Creates for each physical channel a task and its virtual channel

        @returns: error code: ok = 0, error = -1
        """
        try:
            # create a dictionary with physical channel name as key and a pointer as value {'/Dev1/AO0': c_void_p(None), ... }
            taskhandles = dict([(name, daq.TaskHandle(0)) for name in self._ao_channels])
            
            # if an analog task is already running, stop it first (safety if one of the created pointers already points somewhere) 
            for channel in self._ao_channels: 
                if taskhandles[channel].value is not None: 
                    # stop analog output task
                    daq.DAQmxStopTask(taskhandles[channel])
                    # delete the configuration of the analog task
                    daq.DAQmxClearTask(taskhandles[channel])
                    # set the task handle to None as a safety
                    taskhandles[channel].value = None
            
            # create an individual task and a channel per analog output 
            for n, channel in enumerate(self._ao_channels):
                daq.DAQmxCreateTask('', daq.byref(taskhandles[channel])) 
                daq.DAQmxCreateAOVoltageChan(taskhandles[channel], channel, '', self._ao_voltage_ranges[n][0], self._ao_voltage_ranges[n][1], daq.DAQmx_Val_Volts, None) 
            self.ao_taskhandles = taskhandles
        except:
            self.log.exception('Error starting analog output task.')
            return -1
        return 0

    def on_deactivate(self):
        """ Shut down the NI card.
        """
        # clear the task
        try:
            self.close_do_task()  # ends the digital output task in case one was still configured
            for channel in self._ao_channels:
                daq.DAQmxClearTask(self.ao_taskhandles[channel])
                self.ao_taskhandles[channel].value = None  # reset it to nullpointer
            # print(self.ao_taskhandles)
        except:
            self.log.exception('Could not clear AO Out Task.')
       
    def apply_voltage(self, voltage, channel, autostart=True, timeout=10):
        """ Writes a voltage to the specified channel.

        @params: float voltage: voltage value to be applied
        @params: str channel: analog output line such as /Dev1/AO0
        @params: bool autostart: True = task started immediately on call of start task. autostart = False can only be used if timing is configured.
        @param: float timeout: RW timeout in seconds

        @returns: None
        """
        daq.WriteAnalogScalarF64(self.ao_taskhandles[channel], autostart, timeout, voltage, None)  # parameters passed in: taskHandle, autoStart, timeout, value, reserved
        daq.DAQmxStartTask(self.ao_taskhandles[channel])
        daq.DAQmxStopTask(self.ao_taskhandles[channel])

    def get_dict(self):
        """ Retrieves the channel name and the corresponding voltage range for each analog output from the
        configuration file and associates it to the laser wavelength which is controlled by this channel.

        Make sure that the config contains all the necessary elements.

        @returns: laser_dict
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

    def set_up_do_channel(self):
        """ create a task and its virtual channel for the digital output
        
        @return: int error code: ok = 0, error = -1
        """
        if self.digital_out_taskhandle is not None:
            self.log.info('Digital output already set')
            return -1
        else:
            task = daq.TaskHandle()
            daq.DAQmxCreateTask('DigitalOut', daq.byref(task))
            daq.DAQmxCreateDOChan(task, self._do_channel, '', daq.DAQmx_Val_ChanForAllLines)  # last argument: line grouping
            self.digital_out_taskhandle = task  # keep the taskhandle accessible
            return 0
        
    def close_do_task(self):
        """ close the digital output task if there is one
        """
        if self.digital_out_taskhandle is not None:
            task = self.digital_out_taskhandle
            try:
                daq.DAQmxStopTask(task)
                daq.DAQmxClearTask(task)
                self.digital_out_taskhandle = None
            except:
                self.log.exception('Could not close digital output task')
        else:
            pass
        
    def write_to_do_channel(self, num_samp, digital_write):
        """ use the digital output as trigger """
        num_samples_per_channel = daq.c_int32(num_samp)   # write 2 samples per channel
#        digital_write1 = np.array([1,1,1,1,1,1,1,1], dtype=np.uint8)
        digital_read = daq.c_int32()
        daq.DAQmxStartTask(self.digital_out_taskhandle)
        daq.DAQmxWriteDigitalLines(self.digital_out_taskhandle,  # taskhandle
                                num_samples_per_channel,   # number of samples to write per channel
                                True,   # autostart 
                                self._RWTimeout,   # time to wait to write all the samples
                                daq.DAQmx_Val_GroupByChannel,   # dataLayout: non-interleaved: all samples for first channel, all samples for second channel, ...
                                digital_write,   # array of 32 bit integer samples to write to the task  
                                daq.byref(digital_read),  # samples per channel successfully written
                                None)  # reserved for futur use       
        daq.DAQmxStopTask(self.digital_out_taskhandle)
        
    def send_trigger(self):
        """ sends a sequence of digital output values [0, 1, 0] as trigger
        
        This method uses a waiting time to ensure that the signal can be received 
        (typical application: camera acquisition triggered by daq)
        """
        self.write_to_do_channel(1, np.array([0], dtype=np.uint8))
        sleep(0.001)  # waiting time in s
        self.write_to_do_channel(1, np.array([1], dtype=np.uint8))
        sleep(0.001)  # waiting time in s
        self.write_to_do_channel(1, np.array([0], dtype=np.uint8))
        sleep(0.001)  # waiting time in s
        
        
        
    def set_up_ai_channel(self):
        """ create a task and its virtual channel for the analog input
        
        @return: int error code: ok = 0, error = -1
        """
        if self.analog_in_taskhandle is not None:
            self.log.info('Analog input already open')
            return -1
        else:
            task = daq.TaskHandle()
            daq.DAQmxCreateTask('AnalogIn', daq.byref(task))
            daq.DAQmxCreateAIVoltageChan(task, self._ai_channel, '' ,daq.DAQmx_Val_RSE, 0.0, 10.0, daq.DAQmx_Val_Volts, None) 
            self.analog_in_taskhandle = task  # keep the taskhandle accessible
            return 0
        
    def close_ai_task(self):
        """ close the analog input task if there is one
        """
        if self.analog_in_taskhandle is not None:
            task = self.analog_in_taskhandle
            try:
                daq.DAQmxStopTask(task)
                daq.DAQmxClearTask(task)
                self.analog_in_taskhandle = None
            except:
                self.log.exception('Could not close analog input task')
        else:
            pass
        
    def read_ai_channel(self):
        """
        """
        data = np.zeros((1,), dtype=np.float64)
        read = daq.c_int32()
        daq.DAQmxStartTask(self.analog_in_taskhandle)
        daq.DAQmxReadAnalogF64(self.analog_in_taskhandle,   # taskhandle
                           1,  # num_samples per channel # default value -1: all available samples
                           self._RWTimeout,  # timeout
                           daq.DAQmx_Val_GroupByChannel,  # fillMode
                           data,  # the array to rea samples into, organized according to fillMode
                           1,  # the size of the array in samples into which samples are read
                           daq.byref(read), # the actual number of samples read from each channel
                           None)  # reserved
        daq.DAQmxStopTask(self.analog_in_taskhandle)
        return data[0]
        

    def send_trigger_and_control_ai(self):
        """ sends a sequence of digital output values [0, 1, 0] as trigger
        
        This method uses a waiting time to ensure that the signal can be received 
        (typical application: camera acquisition triggered by daq)
        """
        if self.analog_in_taskhandle is None:
            self.log.info('No analog input task configured')
        else:
            self.write_to_do_channel(1, np.array([0], dtype=np.uint8))
            sleep(0.001)  # waiting time in s
            self.write_to_do_channel(1, np.array([1], dtype=np.uint8))
            sleep(0.001)  # waiting time in s
            ai_read = self.read_ai_channel()
            if ai_read > 2.5:
                self.write_to_do_channel(1, np.array([0], dtype=np.uint8))
                sleep(0.001)  # waiting time in s
                return 0
            else:
                self.log.info('fire not received')
                self.write_to_do_channel(1, np.array([0], dtype=np.uint8))
                sleep(0.001)  # waiting time in s
                return -1

