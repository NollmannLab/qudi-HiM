# -*- coding: utf-8 -*-
"""
Qudi-CBS

A module to control the lasers via a DAQ (analog output and digital output line for triggering), via an FPGA
or using the Lumencor celesta.

The DAQ / FPGA are used to control the AOTF to select the laser wavelength.

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
from core.connector import Connector
from logic.generic_logic import GenericLogic
from qtpy import QtCore
from core.configoption import ConfigOption

import numpy as np


# ======================================================================================================================
# Logic class
# ======================================================================================================================


class LaserControlLogic(GenericLogic):
    """ Controls the DAQ analog output and allows to set a digital output line for triggering
    or controls the FPGA output

    Example config for copy-paste:
        lasercontrol_logic:
        module.Class: 'lasercontrol_logic.LaserControlLogic'
        controllertype: 'daq'  # 'fpga'
        connect:
            controller: 'dummy_daq'
    """
    # declare connectors
    controller = Connector(interface='LasercontrolInterface')  # can be a daq, an fpga or the celesta laser source

    # config options
    controllertype = ConfigOption('controllertype', missing='error')  # allows to select between DAQ, FPGA and CELESTA

    # signals
    sigIntensityChanged = QtCore.Signal()  # if intensity dict is changed programmatically, this updates the GUI
    sigLaserStopped = QtCore.Signal()
    sigDisableLaserActions = QtCore.Signal()
    sigEnableLaserActions = QtCore.Signal()

    # attributes
    enabled = False

    # private attributes
    _intensity_dict = {}
    _laser_dict = {}

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self._controller = None

    def on_activate(self):
        """ Initialisation performed during activation of the module.
        """
        self._controller = self.controller()
        self.enabled = False  # attribute to handle the on-off switching of the laser-on button

        # Initialize the laser dictionary (wavelength, ao_range, ao_channel, etc.)
        self._laser_dict = self.get_laser_dict()
        self._intensity_dict = self.init_intensity_dict(0)

    def on_deactivate(self):
        """ Perform required deactivation. """
        pass

# ----------------------------------------------------------------------------------------------------------------------
# Methods to access the laser dictionary from hardware and to access and modify the intensity dictionary
# ----------------------------------------------------------------------------------------------------------------------

    def get_laser_dict(self):
        """ Retrieve the dictionary containing wavelength, channel, and voltage range from the hardware.

        exemplary entry: {'laser1': {'label': 'laser1', 'wavelength': '405 nm', 'channel': '/Dev1/AO2',
                                    'voltage_range': [0, 10]}  # DAQ
                         {'laser1': {'label': 'laser1', 'wavelength': '405 nm', 'channel': '405'}}
                         # FPGA. 'channel' corresponds to the registername.
                        {'laser1': {'label': 'laser1', 'wavelength': '405 nm', 'channel': 1}}
                        # Lumencor. 'channel' corresponds to the address for communicating with the celesta source.

        :return: dict laser_dict
        """
        return self._controller.get_dict()

    def init_intensity_dict(self, value=0):
        """ Create a dictionary with the same keys as the laser dict and set an initial value for the output voltage.

        :param: float value: initial value to be set as intensity. Defaults to 0.

        example: {'laser1': 0, 'laser2': 0, 'laser3': 0, 'laser4': 0}

        :return: dict: intensity_dict
        """
        intensity_dict = {}
        for key in self._laser_dict:
            intensity_dict[key] = value

        return intensity_dict

    def reset_intensity_dict(self):
        """ Resets all values of the intensity_dict to zero.
        This method is for example called from filterwheel logic before setting a new filter.
        Emits a signal to inform the GUI about modified intensities.

        :return: None
        """
        for key in self._intensity_dict:
            self._intensity_dict[key] = 0
        self.sigIntensityChanged.emit()

    @QtCore.Slot(str, float)  # should the decorator be removed when this method is called in a task ???
    def update_intensity_dict(self, key, value):
        """ DO NOT CALL THIS FUNCTION UNLESS YOU ARE SURE THAT THE FILTER YOU ARE USING IS ADAPTED FOR THE
        LASER LINE YOU WANT TO SET!
        This function updates the desired intensity value that is applied to the specified output.
        In case lasers are already on, the new value is automatically applied.
        Else, it just prepares the value that will be applied when voltage output is activated.
        As the GUI contains a security mechanism to avoid setting a value to a forbidden laser
        (incompatible with the current filter setting), there is no risk when updating intensities from the GUI.
        However when calling this method from the iPython console, make sure to activate only lasers that are allowed
        for the filter in the beam path.

        :param: str key: identifier present in the intensity dict, typically 'laser1', 'laser2', ..
        :param: float value: new intensity value (0 - 100 %) to be applied to the specified laser line

        :return: None
        """
        try:
            self._intensity_dict[key] = value
            # if laser is already on, the new value must be written to the daq output
            if self.enabled:
                self.apply_voltage()
        except KeyError:
            self.log.info('Specified identifier not available')

# ----------------------------------------------------------------------------------------------------------------------
# Methods to switch lasers on / off
# ----------------------------------------------------------------------------------------------------------------------

    def apply_voltage(self):
        """ Apply the intensities defined in the _intensity_dict to the belonging channels.

        This method is used to switch lasers on from the GUI, for this reason it iterates over all defined channels
        (no individual laser on / off button but one button for all).

        :return: None
        """
        self.enabled = True
        print('laser dict : {}'.format(self._laser_dict))

        if self.controllertype == 'daq':
            for key in self._laser_dict:
                self._controller.apply_voltage(self._intensity_dict[key] * self._laser_dict[key]['ao_voltage_range'][1] / 100,
                                    self._laser_dict[key]['channel'])
                # conversion factor: user indicates values in percent of max voltage
        elif self.controllertype == 'fpga':
            for key in self._laser_dict:
                self._controller.apply_voltage(self._intensity_dict[key], self._laser_dict[key]['channel'])
        elif self.controllertype == 'celesta':
            intensity = []
            laser_on = []
            for key in self._laser_dict:
                intensity.append(self._intensity_dict[key]*10)
                if self._intensity_dict[key] == 0:
                    laser_on.append(0)
                else:
                    laser_on.append(1)
            self._controller.apply_voltage(intensity, laser_on)
        else:
            self.log.warning('your controller type is currently not covered')

    def apply_voltage_single_channel(self, voltage, channel):
        """ This method makes the low level method from the hardware directly accessible.
        Write a voltage to the specified channel.

        :param: float voltage: voltage value to be applied
        :param: str channel: analog output line such as /Dev1/AO0

        :return: None
        """
        self._controller.apply_voltage(voltage, channel)

    def voltage_off(self):
        """ Switch all lasers off.
        The intensity dictionary is not reset, to be able to restart laser output right away.

        :return: None
        """
        self.enabled = False
        if self.controllertype == 'daq' or self.controllertype == 'fpga':
            for key in self._laser_dict:
                self._controller.apply_voltage(0.0, self._laser_dict[key]['channel'])
        elif self.controllertype == 'celesta':
            n_laser_line = len(self._laser_dict)
            intensity = np.zeros((n_laser_line,)).astype(int)
            laser_on = np.zeros((n_laser_line,)).astype(int)
            print(intensity)
            print(laser_on)
            self._controller.apply_voltage(intensity, laser_on)


# ----------------------------------------------------------------------------------------------------------------------
# Methods used in tasks for synchronization between lightsource and camera in external trigger mode
# ----------------------------------------------------------------------------------------------------------------------

# DAQ specific methods -------------------------------------------------------------------------------------------------

    def send_trigger(self):
        """ Send a sequence 0 - 1 - 0 to a digital output. Only applicable if connected device is a DAQ.
        :return None
        """
        if self.controllertype == 'daq':
            self._controller.send_trigger()
        else:
            pass

    def send_trigger_and_control_ai(self):
        """ Send a sequence 0 - 1 - 0 to a digital output, and control if the fire trigger sent by the camera
        was received. Only applicable if connected device is a DAQ.
        :return: None
        """
        if self.controllertype == 'daq':
            return self._controller.send_trigger_and_control_ai()
        else:
            pass

    def read_trigger_ai_channel(self):
        """ This method gives direct access to reading the trigger input. Read the fire trigger sent by the
        camera. Only applicable if connected device is a DAQ.
        :return: float ai_value: analog input signal read on the specified analog input.
        """
        if self.controllertype == 'daq':
            taskhandle = self._controller.trigger_read_taskhandle
            ai_value = self._controller.read_ai_channel(taskhandle)
            return ai_value
        else:
            pass

# FPGA specific methods ------------------------------------------------------------------------------------------------
        
    def close_default_session(self):
        """ This method is called before another bitfile than the default one shall be loaded. It closes the default
        session, where the default bitfile runs. Only applicable if connected device is a FPGA.
        :return: None
        """
        if self.controllertype == 'fpga':
            self._controller.close_default_session()
        else:
            pass

    def restart_default_session(self):
        """ This method allows to restart the default FPGA session. Only applicable if connected device is a FPGA.
        :return: None
        """
        if self.controllertype == 'fpga':
            self._controller.restart_default_session()
        else:
            pass

    def start_task_session(self, bitfile):
        """ Load a bitfile used for a specific task. Only applicable if connected device is a FPGA.
        :param: str bitfile: complete path to the bitfile used for the task session.
        :return: None
        """
        if self.controllertype == 'fpga':
            self._controller.start_task_session(bitfile)
        else:
            pass

    def end_task_session(self):
        """ Close the session used during a task; using another bitfile than the default one for the FPGA.
        Only applicable if connected device is a FPGA.
        :return: None
        """
        if self.controllertype == 'fpga':
            self._controller.end_task_session()
        else:
            pass

    def run_test_task_session(self, data):
        """ Exemplary method starting the execution of a session. It is necessary to call start_task_session previously
        to load the corresponding bitfile. This method allows to write the parameters to the registers of the FPGA and
        starts the execution. Create a method such as this one for each bitfile used in tasks.
        :param: data: exemplary placeholder for data that must be written to the FPGA registers for running the specific
        session.
        :return: None
        """
        if self.controllertype == 'fpga':
            self._controller.run_test_task_session(data)
        else:
            pass

    def run_multicolor_imaging_task_session(self, z_planes, wavelength, values, num_laserlines, exposure):
        """ Start the execution of the session used in multicolor imaging, where synchronization between piezo
        movement, camera acquisition and lightsources is handled using an FPGA bitfile.
        Only applicable if connected device is a FPGA.

        :param: int z_planes: number of planes in a stack to perform
        :param: list[5] wavelength: list containing five elements (according to bitfile) containing the integer
                                    identifiers [0 - 4] for the laserlines
        :param: list[5] values: list containing five elements (according to the bitfile) containing the float
                                    intensities in per cent for the laserlines given in param wavelength
        :param: int num_laserlines: number of laserlines used in the imaging experiment
        :param: float exposure: exposure time of the camera in seconds

        :return: None
        """
        if self.controllertype == 'fpga':
            self._controller.run_multicolor_imaging_task_session(z_planes, wavelength, values, num_laserlines, exposure)
        else:
            pass

# Lumencor celesta specific methods ------------------------------------------------------------------------------------
#
#     def lumencor_wakeup(self):
#         """ Wake up the lumencor celesta source when it is in standby mode. This is needed in tasks where long
#         pauses between imaging sequences might occur.
#
#         :return: None
#         """
#         if self.controllertype == 'lumencor':
#             self._controller.wakeup()
#         else:
#             pass
#
#     def lumencor_set_ttl(self, ttl_state):
#         """ Define whether the celesta source can be controlled through ttl control.
#
#         :param: bool ttl_state: True: source can be controlled by external trigger
#
#         :return: None
#         """
#         if self._controllertupe == 'lumencor:':
#             self._controller.set_ttl(ttl_state)
#         else:
#             pass

# ----------------------------------------------------------------------------------------------------------------------
# Methods to handle the user interface state
# ----------------------------------------------------------------------------------------------------------------------

    def stop_laser_output(self):
        """ Allows to stop the laser output programmatically, for example in the preparation steps of a task.
        Emits a signal to reset the state of the GUI buttons / controls. """
        if self.enabled:
            self.voltage_off()
            self.sigLaserStopped.emit()

    def disable_laser_actions(self):
        """ This method provides a security to avoid all laser related actions from GUI,
        for example during Tasks. """
        self.sigDisableLaserActions.emit()

    def enable_laser_actions(self):
        """ This method resets all laser related actions from GUI to callable state, for example after Tasks. """
        self.sigEnableLaserActions.emit()
