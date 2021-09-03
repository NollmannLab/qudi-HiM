# -*- coding: utf-8 -*-
"""
Qudi-CBS

This file contains a class for the PIFOC z axis positioning stage.

An extension to Qudi.

@author: F. Barho

Created on Tue Jan 12 2021
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
from interface.motor_interface import MotorInterface
from core.configoption import ConfigOption

from pipython import GCSDevice, pitools


# ======================================================================================================================
# Hardware class
# ======================================================================================================================

class PIFOC(Base, MotorInterface):
    """ Class representing the PIFOC z axis positioning stage.
    
    Example config for copy-paste:
        
    pifoc:
        module.Class: 'motor.motor_pifoc.PIFOC'
        controllername: 'E816'
        serialnumber: '110059675'
        pos_min: 0  # in um
        pos_max: 100  # in um
        max_step: 1  # in um
    """
    # config options
    _controllername = ConfigOption('controllername', missing='error')
    _serialnum = ConfigOption('serialnumber', missing='error')
    _pos_min = ConfigOption('pos_min', 0, missing='warn')  # in um
    _pos_max = ConfigOption('pos_max', 100, missing='warn')  # in um
    _max_step = ConfigOption('max_step', 1, missing='warn')  # in um

    # attributes
    axes = None
    pidevice = None
    _axis_label = None
    _axis_ID = None

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

    def on_activate(self):
        """ Initialization: Connection to the dll.
        """
        try:
            # initalize the dll
            self.pidevice = GCSDevice(self._controllername)
            # open the connection
            self.pidevice.ConnectUSB(serialnum=self._serialnum)
            self.log.info('connected: {}'.format(self.pidevice.qIDN().strip()))

            # Initialize the axis label and axis ID (single axis controller)
            self.axes = self.pidevice.axes  # this returns a list
            self._axis_label = self.axes[0]  # axes is actually a list of length 1 for the pifoc
            self._axis_ID = self.pidevice.GetID()
            self.log.info(f'available axis: {self._axis_label}, ID: {self._axis_ID}')

            # reference the axis
            pitools.startup(self.pidevice)

        except Exception as e:
            self.log.error(f'Physik Instrumente PIFOC: Connection failed: {e}.')

    def on_deactivate(self):
        """ Close connection when deactivating the module.
        """
        self.pidevice.CloseConnection()

# ----------------------------------------------------------------------------------------------------------------------
# Motor interface functions
# ----------------------------------------------------------------------------------------------------------------------

    def get_constraints(self):
        """ Retrieve the hardware constrains from the motor device.

        :return dict constraints
        """
        constraints = {}

        axis0 = {'label': self._axis_label,
                 'ID': self._axis_ID,
                 'unit': 'um',
                 'pos_min': self._pos_min,
                 'pos_max': self._pos_max,
                 'max_step': self._max_step
                 }

        # assign the parameter container for x to a name which will identify it
        constraints[axis0['label']] = axis0

        return constraints

    def move_rel(self, param_dict):
        """ Moves stage in given direction (relative movement).

        :param dict param_dict: Dictionary with axis name and step (in um units) as key - value pairs

        :return bool: error code (True: ok, False: not ok)
        """
        constraints = self.get_constraints()
        position = self.get_pos()  # returns an OrderedDict with one entry (one axis)
        err = False

        for i in range(len(param_dict)):
            # potentially a list of axes. real case: list of length 1 because pifoc only has one axis
            # in case a longer param_dict is given, only the entry with the right axis label will be considered
            (axis, step) = param_dict.popitem()
            step = np.round(step, decimals=4)  # avoid error due to decimal overflow
            if axis in self.axes:
                cur_pos = position[axis]  # returns just the float value of the axis
                # check if the position stays in allowed range after movement
                if abs(step) <= constraints[axis]['max_step'] and constraints[axis]['pos_min'] <= cur_pos + step <= constraints[axis]['pos_max']:
                    self.pidevice.MVR(axis, step)
                    err = True
                    if not err:
                        error_code = self.pidevice.GetError()
                        error_msg = self.pidevice.TranslateError(error_code)
                        self.log.warning(f'Could not move axis {axis} by {step}: {error_msg}.')
                else:
                    self.log.warning('Movement not possible. Allowed range exceeded')
        return err

    def move_abs(self, param_dict):
        """ Moves stage to absolute position (absolute movement).
        Use preferably the relative movement. move_abs does not implement a safety check if a too big step will be done.
        Ramps are handled in the logic modules.

        :param dict param_dict: Dictionary with axis name and target position (in um units) as key - value pairs

        :return bool: error code (True: ok, False: error)
        """
        constraints = self.get_constraints()
        err = False

        for i in range(len(param_dict)):  # potentially a list of axes. real case: list of length 1 because pifoc only has one axis
            (axis, target) = param_dict.popitem()
            target = np.round(target, decimals=4)  # avoid error due to decimal overflow
            if axis in self.axes and constraints[axis]['pos_min'] <= target <= constraints[axis]['pos_max']:  # control if the right axis is addressed
                self.pidevice.MOV(axis, target)  # MOV has no return value
                err = True  
                if not err:
                    error_code = self.pidevice.GetError()
                    error_msg = self.pidevice.TranslateError(error_code)
                    self.log.warning(f'Could not move axis {axis} to {target} : {error_msg}.')
                    # it might be needed to print a pertinent error message in case the movement was not performed because the conditions above were not met,
                    # that is, if the error does not come from the controller but due to the coded conditions 
        return err

    def abort(self):
        """ Stops movement of the stage.
        Not supported by PI Piezo stage. (command HLT is not supported by the controller type)

        :return bool: error code (True: ok, False: error)
        """
        # err = self.pidevice.HLT()  # needs eventually controller ID as argument  # HLT or STP ?
        # errorcode = self.pidevice.GetError()
        # errormsg = self.pidevice.TranslateError(errorcode)
        # if not err:
        #     self.log.warning(f'Error calling abort: {errormsg}')
        # return err
        return False

    def get_pos(self, param_list=None):
        """ Gets current position of the stage.

        :param list param_list: optional, if a specific position of an axis
                                is desired, then the labels of the needed
                                axis should be passed in the param_list.
                                If nothing is passed, then from each axis the
                                position is asked.

        :return OrderedDict: with keys being the axis labels and item the current position.
        """
        if not param_list:
            pos = self.pidevice.qPOS(self.axes)  # this returns an OrderedDict
            return pos
        else:
            for axis in param_list:
                if axis == self.axes:
                    pos = self.pidevice.qPOS(axis)
                    return pos
                else:
                    self.log.warn(f'Specified axis not available: {axis}')

    def get_status(self, param_list=None):
        """ Get the status of the position.

        :param list param_list: optional, if a specific status of an axis
                                is desired, then the labels of the needed
                                axis should be passed in the param_list.
                                If nothing is passed, then from each axis the
                                status is asked.

        :return dict: with the axis label as key and the status number as item.
        """
        err = self.pidevice.IsControllerReady()
        status_dict = {}
        status_dict[self._axis_label] = err
        return status_dict

    def calibrate(self, param_list=None):
        """ Calibrates the stage.
        Not supported by PI Piezo stage.

        :param list param_list: param_list: optional, if a specific calibration
                                of an axis is desired, then the labels of the
                                needed axis should be passed in the param_list.
                                If nothing is passed, then all connected axis
                                will be calibrated.

        :return int: error code (0:OK, -1:error)
        """
        pass

    def get_velocity(self, param_list=None):
        """ Gets the current velocity for all connected axes.
        Not supported by PI Piezo stage.

        :param list param_list: optional, if a specific velocity of an axis
                                is desired, then the labels of the needed
                                axis should be passed as the param_list.
                                If nothing is passed, then from each axis the
                                velocity is asked.

        :return dict: with the axis label as key and the velocity as item.
        """
        # vel = self.pidevice.q???(self.axis)  # test which query is the right one here..
        # return vel
        self.log.info('get_velocity not available')

    def set_velocity(self, param_dict):
        """ Write new value for velocity.
        Not supported by PI Piezo stage.

        :param dict param_dict: dictionary, which passes all the relevant
                                parameters, which should be changed. Usage:
                                 {'axis_label': <the-velocity-value>}.
                                 'axis_label' must correspond to a label given
                                 to one of the axis.

        :return int: error code (0:OK, -1:error)
        """
        self.log.info('set velocity not available')

    def wait_for_idle(self):
        """ Wait until a motorized stage is in idle state.
        :return: None
        """
        # self.log.info('old position: {}'.format(self.get_pos()))
        pitools.waitontarget(self.pidevice)
        # self.log.info('new position: {}'.format(self.get_pos()))
        return
