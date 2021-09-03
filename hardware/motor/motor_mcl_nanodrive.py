# -*- coding: utf-8 -*-
"""
Qudi-CBS

This file contains a class for the Mad city labs piezo controller.

An extension to Qudi.

@author: F. Barho

Created on Mon Feb 1 2021
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
import ctypes
import numpy as np
from core.module import Base
from interface.motor_interface import MotorInterface
from core.configoption import ConfigOption


# error codes  # maybe transform into error dict
MCL_SUCCESS             = 0   # Task has been completed successfully.
MCL_GENERAL_ERROR       = -1  # These errors generally occur due to an internal sanity check failing.
MCL_DEV_ERROR		    = -2  # A problem occurred when transferring data to the Nano-Drive.  It is likely that the Nano-Drive will have to be 	 power cycled to correct these errors.
MCL_DEV_NOT_ATTACHED	= -3  # The Nano-Drive cannot complete the task because it is not attached.
MCL_USAGE_ERROR		    = -4  # Using a function from the library which the Nano-Drive does not support causes these errors.
MCL_DEV_NOT_READY	    = -5  # The Nano-Drive is currently completing or waiting to complete another task.
MCL_ARGUMENT_ERROR	    = -6  # An argument is out of range or a required pointer is equal to NULL.
MCL_INVALID_AXIS		= -7  # Attempting an operation on an axis that does not exist in the Nano-Drive.
MCL_INVALID_HANDLE	    = -8  # The handle is not valid.  Or at least is not valid in this instance of the DLL.


# ======================================================================================================================
# Hardware class
# ======================================================================================================================

class MCLNanoDrive(Base, MotorInterface):
    """ Class representing the MCL Nano-Drive piezo controller.

    Example config for copy-paste:

    mcl:
        module.Class: 'motor.motor_mcl_nanodrive.MCLNanoDrive'
        dll_location: 'C:\\Program Files\\Mad City Labs\\NanoDrive\\Madlib.dll'   # path to library file
        pos_min: 0  # in um
        pos_max: 80  # in um
        max_step: 1  # in um

        found help with return type of MCL_SingleReadZ here:
        https://github.com/ScopeFoundry/HW_mcl_stage/blob/master/mcl_nanodrive.py
    """
    # config options
    dll_location = ConfigOption('dll_location', missing='error')
    _pos_min = ConfigOption('pos_min', 0, missing='warn')  # in um
    _pos_max = ConfigOption('pos_max', 80, missing='warn')  # in um
    _max_step = ConfigOption('max_step', 1, missing='warn')  # in um

    # attributes
    handle = None
    _axis_label = None
    _axis_ID = None

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self.dll = None

    def on_activate(self):
        """ Initialization: Connection to the dll.
        """
        self.dll = ctypes.cdll.LoadLibrary(self.dll_location)

        # set return types of certain functions
        self.dll.MCL_SingleReadZ.restype = ctypes.c_double

        # get handle of connected Nanodrive
        handle = self.dll.MCL_InitHandle()
        if handle == 0:
            self.log.error('Failed to initialize MCL Nanodrive. Check if device is switched on.')
        else:
            self.handle = handle

        num = self.dll.MCL_NumberOfCurrentHandles()
        self.log.debug(f'{num} Nanodrives connected.')

        self._axis_label = 'Z'  # one axis controller. Set this arbitrarily to be conform with motor interface
        self._axis_ID = self.handle  # not really needed .. just for conformity with pifoc get_constraints function.

    def on_deactivate(self):
        """ Close connection when deactivating the module.
        """
        handle = ctypes.c_int(self.handle)
        self.dll.MCL_ReleaseHandle(handle)

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
                 'max_step': self._max_step}

        # assign the parameter container for to a name which will identify it
        constraints[axis0['label']] = axis0

        return constraints

    def move_rel(self, param_dict):
        """ Moves stage in given direction (relative movement).

        :param dict param_dict: Dictionary with axis name and step (in um units) as key - value pairs

        :return bool: error code (True: ok, False: not ok)
        """
        # this version is for a param_dict with one entry.
        constraints = self.get_constraints()
        (_, position) = self.get_pos().popitem()  # get_pos returns a dict {axis_label: position}

        (axis, step) = param_dict.popitem()
        step = np.round(step, decimals=4)  # avoid error due to decimal overflow

        if axis == self._axis_label and abs(step) <= constraints[axis]['max_step'] and constraints[axis]['pos_min'] <= position + step <= constraints[axis]['pos_max']:
            new_pos = ctypes.c_double(position + step)
            err = self.dll.MCL_SingleWriteZ(new_pos, self.handle)
            if err == MCL_SUCCESS:
                return True
            else:
                self.log.warning(f'Could not move axis {axis} by {step}: {err}.')
                return False

    def move_abs(self, param_dict):
        """ Moves stage to absolute position (absolute movement).
        Use preferably the relative movement. move_abs does not implement a safety check if a too big step will be done.
        Ramps are handled in the logic modules.

        :param dict param_dict: Dictionary with axis name and target position (in um units) as key - value pairs

        :return bool: error code (True: ok, False: error)
        """
        # this version is for a param_dict with one entry.
        constraints = self.get_constraints()
        (_, position) = self.get_pos().popitem()  # get_pos returns a dict {axis_label: position}

        (axis, new_pos) = param_dict.popitem()
        new_pos = np.round(new_pos, decimals=4)  # avoid error due to decimal overflow

        if axis == self._axis_label and constraints[axis]['pos_min'] <= new_pos <= constraints[axis]['pos_max']:
            new_pos = ctypes.c_double(new_pos)
            err = self.dll.MCL_SingleWriteZ(new_pos, self.handle)
            if err == MCL_SUCCESS:
                return True
            else:
                self.log.warning(f'Could not move axis {axis} to position {position}: {err}.')
                return False

    def abort(self):
        """ Stops movement of the stage.
        Not supported by MCL Piezo stage.

        :return bool: error code (True: ok, False: error)
        """
        return False

    def get_pos(self, param_list=None):
        """ Gets current position of the stage.

        :param list param_list: optional, if a specific position of an axis
                                is desired, then the labels of the needed
                                axis should be passed in the param_list.
                                If nothing is passed, then from each axis the
                                position is asked.

        :return dict: with keys being the axis labels and item the current position.
        """
        if not param_list:
            cur_pos = self.dll.MCL_SingleReadZ(self.handle)
            if cur_pos < 0:  # then this corresponds to an error code
                self.log.warn(f'error reading position: {cur_pos}')
            else:
                pos = {}
                pos[self._axis_label] = cur_pos
                return pos
        else:
            for axis in param_list:
                if axis in self._axis_label:
                    cur_pos = self.dll.MCL_SingleReadZ(self.handle)
                    if cur_pos < 0:
                        self.log.warn(f'error reading position: {cur_pos}')
                    else:
                        pos = {}
                        pos[self._axis_label] = cur_pos
                        return pos
                else:
                    self.log.warn(f'Specified axis not available: {axis}')

    def get_status(self, param_list=None):
        """ Get the status of the position.
        Not supported by MCL Piezo stage.

        :param list param_list: optional, if a specific status of an axis
                                is desired, then the labels of the needed
                                axis should be passed in the param_list.
                                If nothing is passed, then from each axis the
                                status is asked.

        :return dict: with the axis label as key and the status number as item.
        """
        pass

    def calibrate(self, param_list=None):
        """ Calibrates the stage.
        Not supported by MCL Piezo stage.

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
        Not supported by MCL Piezo stage.

        :param list param_list: optional, if a specific velocity of an axis
                                is desired, then the labels of the needed
                                axis should be passed as the param_list.
                                If nothing is passed, then from each axis the
                                velocity is asked.

        :return dict: with the axis label as key and the velocity as item.
        """
        self.log.info('get velocity not available')

    def set_velocity(self, param_dict):
        """ Write new value for velocity.
        Not supported by MCL Piezo stage.

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
        pass
