# -*- coding: utf-8 -*-
"""
Qudi-CBS

This file contains a class for the ASI MS2000 translation stage.

An extension to Qudi.

@author: F. Barho

Created on Mon Oct 26 2020
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
import serial
from time import sleep, time
import re

from core.module import Base
from interface.motor_interface import MotorInterface
from interface.brightfield_interface import BrightfieldInterface
from core.configoption import ConfigOption


# ======================================================================================================================
# Hardware class
# ======================================================================================================================

class MS2000(Base, MotorInterface, BrightfieldInterface):
    """ Class representing the ASI MS 2000 xy or xyz translation stage.
    
    Example config for copy-paste:
        
    ms2000:
        module.Class: 'motor.motor_asi_ms2000.MS2000'
        com_port: 'COM4'
        first_axis_label: 'x'
        second_axis_label: 'y'
        third_axis_label: 'z'
        LED connected: False
    """
    # config options
    _com_port = ConfigOption("com_port", missing="error")
    _baud_rate = ConfigOption("baud_rate", 9600, missing="warn")

    _first_axis_label = ConfigOption("first_axis_label", "x", missing="warn")
    _second_axis_label = ConfigOption("second_axis_label", "y", missing="warn")
    # default case is intended for 2 axes stage, for 3 axes specify in config
    _third_axis_label = ConfigOption("third_axis_label", None)

    _has_led = ConfigOption("LED connected", False, missing="warn")

    # attributes
    _conversion_factor = 10.0  # user will send positions in um, stage uses 0.1 um
    axis_list = None
    _serial_connection = None
    _timeout = 30

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self._led_mode = 'Internal'

    def on_activate(self):
        """ Initialization: opening serial port and setting internal attributes.
        """
        try:
            self._serial_connection = serial.Serial(
                self._com_port, baudrate=self._baud_rate, bytesize=8, parity="N", stopbits=1, xonxoff=True
            )

            # create a list as iterator for methods that need a specified axis to apply to
            axis_list = [self._first_axis_label, self._second_axis_label, self._third_axis_label]
            self.axis_list = []
            for item in axis_list:
                if isinstance(item, str):
                    self.axis_list.append(item)

            # if the z axis is available, define the default speed for this axis
            if len(axis_list) == 3:
                self.set_velocity({'z': 1.9})

            # if the stage is also controlling the bright-field, initiate the mode to "Internal"
            if self._has_led:
                self.led_mode('Internal')

        except Exception:
            self.log.error(f'ASI MS2000 automated stage not connected. Check if device is switched on.')

    def on_deactivate(self):
        """ Close serial port when deactivating the module.
        """
        self._serial_connection.close()
        # safety check  # to explore when problem with stage arises again ..
        port_open = self._serial_connection.is_open
        t0 = time()
        while port_open:
            print('in loop')
            t1 = time() - t0
            sleep(0.5)
            # self._serial_connection.close()
            port_open = self._serial_connection.is_open
            if t1 > 5:
                break

# ----------------------------------------------------------------------------------------------------------------------
# Motor interface functions
# ----------------------------------------------------------------------------------------------------------------------

    @property
    def get_constraints(self):
        """ Retrieve the hardware constrains from the motor device.
        ASI Stage has no fixed pos_min and pos_max due to variable home position.

        :return dict constraints
        """
        constraints = {}

        axis0 = {'label': self._first_axis_label, 'unit': '0.1 um', 'vel_min': 0, 'vel_max': 7.5}

        axis1 = {'label': self._second_axis_label, 'unit': '0.1 um', 'vel_min': 0, 'vel_max': 7.5}

        constraints[axis0['label']] = axis0
        constraints[axis1['label']] = axis1

        # handle 3 axes case:
        if self._third_axis_label:
            axis2 = {'label': self._third_axis_label, 'unit': '0.1 um', 'vel_min': 0, 'vel_max': 1.9}
            constraints[axis2['label']] = axis2

        return constraints

    def move_rel(self, param_dict):
        """ Moves stage in given direction (relative movement).

        :param dict param_dict: Dictionary with axis name and step (in um units) as key - value pairs

        :return bool: error code (True: ok, False: not ok)
        """
        err = False
        try:
            for axis_label in param_dict:
                if (
                    axis_label in self.axis_list
                ):  # to ensure that only configured axes are taken into account in case param_dict indicates other axes
                    step = np.round(param_dict[axis_label] * self._conversion_factor, decimals=4)  # avoid error due to decimal overflow
                    cmd = f"R {axis_label}={step}\r"
                    self.write(cmd)
                    err = True
                else:
                    self.log.warn(f"axis {axis_label} is not configured")
        except Exception:
            self.log.error("Relative movement of ASI MS2000 translation stage is not possible.")
            
        return err

    def move_abs(self, param_dict):
        """ Moves stage to absolute position (absolute movement).

        :param dict param_dict: Dictionary with axis name and target position (in um units) as key - value pairs

        :return bool: error code (True: ok, False: error)
        """
        err = False
        try:
            for axis_label in param_dict:
                if (
                    axis_label in self.axis_list
                ):  # to ensure that only configured axes are taken into account in case param_dict indicates other axes
                    new_pos = np.round(param_dict[axis_label] * self._conversion_factor, decimals=4)  # avoid error due to decimal overflow
                    cmd = f"M {axis_label}={new_pos}\r"
                    self.write(cmd)
                    err = True
                else:
                    self.log.warn(f"axis {axis_label} is not configured")

        except Exception:
            self.log.error("Absolute movement of ASI MS2000 translation stage is not possible")

        return err

    def abort(self):
        """ Stops movement of the stage.

        Attention, the (following) command N+1 is not performed! The N+2 command is again performed.
        new tests on RAMM: following command is perfomed normally ..

        :return bool: error code (True: ok, False: error)
        """
        cmd = "\\r"
        self.write(cmd)
        # self._serial_connection.flush() # tried this, also flushInput(), to enable command N+1. does not work....
        # to be improved
        return True

    def get_pos(self, param_list=None):
        """ Gets current position of the stage.

        :param list param_list: optional, if a specific position of an axis
                                is desired, then the labels of the needed
                                axis should be passed in the param_list.
                                If nothing is passed, then from each axis the
                                position is asked.

        :return dict pos: Dictionary with axis name and current position of the translation stage
        """
        pos = {}

        if not param_list:  # get all axes
            # this list is generated above to generalize more easily in case that more axes are added
            for axis_label in self.axis_list:
                cmd = f"W {axis_label}\r"
                # [3:] -> remove the leading 'A: '
                pos[axis_label] = float(self.query(cmd)[3:]) / self._conversion_factor

        else:
            for item in param_list:
                if item in self.axis_list:
                    cmd = f"W {item}\r"
                    pos[item] = float(self.query(cmd)[3:]) / self._conversion_factor
                else:
                    self.log.warn(f'Specified axis not available: {item}')

        return pos

    def get_status(self, param_list=None):
        """ Queries if any motors are still busy moving following a serial command.

        :param list param_list: optional, if a specific status of an axis
                                is desired, then the labels of the needed
                                axis should be passed in the param_list.
                                If nothing is passed, then from each axis the
                                status is asked.
                                Not used here because all axes are treated as a unity for ASI stage.

        # :return dict: with the axis label as key and the status number as item.  (usual return type)
        :return: str status: 'N' if no motors runningm 'B' if busy
        """
        cmd = "/ \r"
        status = self.query(cmd)
        return status

    def calibrate(self, param_list=None):
        # to be defined what should be done here: AALIGN, ZEROING, HOMING ?
        """ Performs self-calibration of the axis motor drive circuit.

        :param: list param_list: param_list: optional, if a specific calibration
                        of an axis is desired, then the labels of the
                        needed axis should be passed in the param_list.
                        If nothing is passed, then all connected axis
                        will be calibrated.
        
        :return: int: error code (0:OK, -1:error)
        """
        err = -1
        if not param_list:
            for axis_label in self.axis_list:
                cmd = f"AA {axis_label}\r"
                self.write(cmd)
                err = 0

        else:
            for item in param_list:
                if item in self.axis_list:
                    cmd = f"AA {item}\r"
                    self.write(cmd)
                    err = 0
                else:
                    self.log.warn(f'Specified axis not available: {item}')
        return err

    def get_velocity(self, param_list=None):
        """ Gets the current velocity of the translation stage for the specified axes or all axes.

        :param list param_list: optional, if a specific velocity of an axis
                                is desired, then the labels of the needed
                                axis should be passed as the param_list.
                                If nothing is passed, then from each axis the
                                velocity is asked.

        :return dict: Dictionary with axis name and current velocity of the specified axis.
        """
        velo = {}

        if not param_list:
            for axis_label in self.axis_list:
                cmd = f"S {axis_label}?\r"
                velo[axis_label] = float(
                    self.query(cmd)[5:]
                )  # format from query ':A X=5.745920', remove leading X= and convert to float

        else:
            for item in param_list:
                if item in self.axis_list:
                    cmd = f"S {item}?\r"
                    velo[item] = float(self.query(cmd)[5:])
                else:
                    self.log.warn(f'Specified axis not available: {item}')

        return velo

    def set_velocity(self, param_dict):
        """ Sets the velocity at which the stage moves. 
        Velocity is set in millimeters per second. Maximum speed is 7.5 mm/s for standard 6.5 mm pitch leadscrews.
        @param (dict) param_dict: Dictionary with axis name and target velocity in mm/s
        @return (int) error code (0:OK, -1:error)
        """
        err = -1

        try:
            for axis_label in param_dict:
                if axis_label in self.axis_list:
                    new_velo = param_dict[axis_label]
                    cmd = f"S {axis_label}={new_velo}\r"
                    self.write(cmd)
                    err = 0
                else:
                    self.log.warn(f"specified axis {axis_label} not available")
        except Exception as e:
            self.log.error(f"Could not set new velocity due to the following error {e}")

        return err

    def wait_for_idle(self):
        """ Wait until a motorized stage is in idle state.
        Checks every 1 s until timeout if a motor is running from a serial command 'B' or not 'N'
        @return timeout (bool) indicate whether the timeout limit was reach while waiting for the movement to stop
        """
        status = self.get_status()
        t0 = time()
        timeout = False
        while status != "N":
            sleep(0.5)
            waiting_time = time() - t0
            status = self.get_status()
            if waiting_time >= self._timeout:
                self.log.error(f"ASI MS2000 translation stage timeout occurred after {waiting_time}s")
                timeout = True
                break

        return timeout

# ----------------------------------------------------------------------------------------------------------------------
# Additional custom functions not on the interface
# ----------------------------------------------------------------------------------------------------------------------

    def homing_xy(self):
        """ Moves the stage to homeposition on x and y axes.
        Motor stops when hardware or firmware limit switch is encountered.
        
        :return: error code (ok: 0)
        """
        cmd = "! X Y \r"
        self.write(cmd)
        return 0

    def set_to_zero(self):
        """ Sets the current position as the origin.
        
        :return: error code (ok: 0)
        """
        cmd = "Z \r"
        self.write(cmd)
        return 0

# ----------------------------------------------------------------------------------------------------------------------
# Bright-field interface functions
# ----------------------------------------------------------------------------------------------------------------------

    def led_mode(self, mode):
        """ Defines the mode of the LED, depending on the type of experiment performed. The mode can either be
        "internal" or "triggered".
        :param: str mode
        :return: none
        """
        if self._led_mode == 'Internal' and self._has_led:
            self.led_control(0)

        if mode == 'Internal' and self._has_led:
            cmd = f"TTL X=0 Y=9 \r"
            self.write(cmd)
            self.led_control(0)
        elif mode == 'Triggered' and self._has_led:
            cmd = f"TTL X=10 Y=0 \r"
            self.write(cmd)

        self._led_mode = mode

    def led_control(self, intens):
        """ Set the intensity of the LED to the value intensity (in percent of max. intensity, 0-99%).
        :param: int intensity: percentage of maximum intensity to be applied to the LED
        :return: None
        """
        if self._has_led:
            # truncate to allowed range
            value = int(min(max(intens, 0), 99))
            cmd = f"LED X={value}? \r"
            self.write(cmd)
        else:
            pass

# ----------------------------------------------------------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------------------------------------------------------

    def query(self, command):
        """ Clears the input buffer and queries an utf-8 encoded command.
        
        :param: string command: message to send to the serial port, typically in the format
        'COMMANDSHORTCUT [AXIS=value]\r'
        :return: string answer: formatted and decoded response from serial port
        """

        self._serial_connection.flushInput()
        self._serial_connection.flushOutput()
        self._serial_connection.write(command.encode())
        answer = self._serial_connection.readline().decode().strip()
        # print("ASI stage query {}".format(command))
        # print("ASI stage query return : {}".format(answer))
        return answer

    def write(self, command):
        """ Clears the input buffer and writes an utf-8 encoded command to the serial port .
        
        :param string command: message to send to the serial port, typically in the format
        'COMMANDSHORTCUT [AXIS=value]\r'
        :return: None
        """
        n_attempt = 0
        success = False

        while n_attempt < 10 and success is False:
            self._serial_connection.flushInput()
            self._serial_connection.flushOutput()
            self._serial_connection.write(command.encode())
            answer = self._serial_connection.readline().decode().strip()
            is_match = bool(re.match(":A", answer))
            if is_match is True:
                success = True
                break
            else:
                n_attempt += 1
                sleep(0.1)

        if success is False:
            print('The ASI stage is unable to execute the command : {}'. format(command))
