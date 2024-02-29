#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Oct 30 11:09:20 2020

@author: fbarho

A module to control the DAQ analog output and digital output line for triggering.

The DAQ is used here to control the AOTF to select the laser wavelength and intensity

Deprecated; replaced by lasercontrol_logic. Keep it until it is checked everywhere that lasercontrol_logic works.
"""

from core.connector import Connector
from core.util.mutex import Mutex
from logic.generic_logic import GenericLogic
from qtpy import QtCore


class DAQaoLogic(GenericLogic):
    """ Controls the DAQ analog output and allows to set a digital output line for triggering
    """

    # declare connectors
    daq = Connector(interface='DaqInterface')

    # signals
    sigIntensityChanged = QtCore.Signal()  # if intensity dict is changed programmatically, this updates the GUI

    # attributes
    enabled = False

    # private attributes
    _intensity_dict = {}
    _laser_dict = {}

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        # activate if necessary
        # self.threadlock = Mutex()

    def on_activate(self):
        """ Initialisation performed during activation of the module.
        """
        self._daq = self.daq()

        self.enabled = False  # attribute to handle the on-off switching of the laser-on button

        self._laser_dict = self.get_laser_dict()
        self._intensity_dict = self.init_intensity_dict(0)

    def on_deactivate(self):
        """ Perform required deactivation. """
        pass

    def get_laser_dict(self):
        """ Retrieve the dictionary containing wavelength, channel, and voltage range from the hardware.

        exemplary entry: {'laser1': {'label': 'laser1', 'wavelength': '405 nm', 'channel': '/Dev1/AO2', 'voltage_range': [0, 10]}

        returns: dict
        """
        return self._daq.get_dict()

    def init_intensity_dict(self, value=0):
        """ creates a dictionary with the same keys as the laser dict and set an initial value for the output voltage

        example: {'laser1': 0, 'laser2': 0, 'laser3': 0, 'laser4': 0}

        returns: dict: intensity_dict
        """
        intensity_dict = {}
        for key in self._laser_dict:
            intensity_dict[key] = value

        return intensity_dict

    def reset_intensity_dict(self):
        """ resets all values of the intensity_dict to zero
        """
        # function is called from filterwheel logic before setting a new filter
        for key in self._intensity_dict:
            self._intensity_dict[key] = 0
        self.sigIntensityChanged.emit()

    def apply_voltage(self):
        self.enabled = True
        for key in self._laser_dict:
            self._daq.apply_voltage(self._intensity_dict[key] * self._laser_dict[key]['ao_voltage_range'][1] / 100, self._laser_dict[key]['channel'])
            # conversion factor: user indicates values in percent of max voltage
            # alternative: (to test which is faster)
            # self.apply_voltage_single_channel(self._intensity_dict[key] * self._laser_dict[key]['ao_voltage_range'][1] / 100, self._laser_dict[key]['channel'])

        # does the delay due to iteration matter ? (laser 4 switched on slightly after laser 1 ? ..)

    def voltage_off(self):
        self.enabled = False
        for key in self._laser_dict:
            self._daq.apply_voltage(0.0, self._laser_dict[key]['channel'])
        # note that the intensity dict is intentionnally not reset to allow easy on off switching without need to rewrite the value

    @QtCore.Slot(str, int)  # should the decorator be removed when this method is called in a task ???
    def update_intensity_dict(self, key, value):
        """ STOP! DO NOT CALL THIS FUNCTION UNLESS YOU ARE SURE THAT THE FILTER YOU ARE USING IS ADAPTED FOR THE LASER LINE YOU WANT TO SET!
        This function updates the desired intensity value that is applied to the specified output.
        In case lasers are already on, the new value is automatically applied.
        Else, it just prepares the value that will be applied when voltage output is activated.
        As the GUI contains a security mechanism to avoid setting a value to a forbidden laser (incompatible with the current filter setting),
        there is no risk when updating intensities from the GUI. However when calling this method from the iPython console, make sure what you
        are doing.

        @params: str key: identifier present in the intensity dict
        @params: int value: new intensity value (0 - 100 %) to be applied to the specified laser line
        """
        try:
            self._intensity_dict[key] = value
            # if laser is already on, the new value must be written to the daq output
            if self.enabled:
                self.apply_voltage()
        except KeyError:
            self.log.info('Specified identifier not available')
            
    # low level functions (direct access to daq functions)
    def apply_voltage_single_channel(self, voltage, channel, autostart=True, timeout=10):
        """ this method makes the low level method from the hardware directly accessible
        Writes a voltage to the specified channel.

        @params: float voltage: voltage value to be applied
        @params: str channel: analog output line such as /Dev1/AO0
        @params: bool autostart: True = task started immediately on call of start task. autostart = False can only be used if timing is configured.
        @param: int? float? timeout: RW timeout in seconds
        """
        self._daq.apply_voltage(voltage, channel, autostart, timeout)

    def send_trigger(self):
        """ """
        self._daq.send_trigger()
        
    def set_up_do_channel(self):
        """ create a digital output channel
        """
        self._daq.set_up_do_channel() 
        
    def close_do_task(self):
        """ close the digital output channel and task if there is one """
        self._daq.close_do_task()
