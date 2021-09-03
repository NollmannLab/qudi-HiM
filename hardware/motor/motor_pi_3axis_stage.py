# -*- coding: utf-8 -*-
"""
Qudi-CBS

This file contains a class for the Physik Instrumente 2 or 3 axes stage.

An extension to Qudi.

@author: F. Barho

Created on Wed Mars 3 2021
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

class PIMotorStage(Base, MotorInterface):
    """ Class representing the PI 2 or 3 axes positioning motor stage

    Example config for copy-paste:

    pi_stage:
        module.Class: 'motor.motor_pi_3axis_stage.PIMotorStage'
        daisychain_connection: True
        serialnumber_master:  '0019550121'
        first_axis_controllername: 'C-863'
        second_axis_controllername: 'C-863'
        third_axis_controllername: 'C-863'
        first_axis_label: 'x'
        second_axis_label: 'y'
        third_axis_label: 'z'
        first_axis_daisychain_id: 2  # number of the device in the daisy chain (sorted by increasing serial number of the controller)
        second_axis_daisychain_id: 3
        third_axis_daisychain_id: 1
        first_axis_type: 'linear'
        second_axis_type: 'linear'  # 'rotation'
        third_axis_type: 'linear'
    """
    # config options
    _daisychain_connection = ConfigOption('daisychain_connection', missing='error')
    _serialnum_master = ConfigOption('serialnumber_master', missing='error')
    _serialnum_second_axis = ConfigOption('serialnumber_second_axis')  # optional; only needed if individual connections
    _serialnum_third_axis = ConfigOption('serialnumber_third_axis')  # optional; only needed if individual connections
    _first_axis_controllername = ConfigOption('first_axis_controllername', missing='error')
    _second_axis_controllername = ConfigOption('second_axis_controllername', missing='error')
    _third_axis_controllername = ConfigOption('third_axis_controllername', None)
    _first_axis_label = ConfigOption('first_axis_label', missing='error')
    _second_axis_label = ConfigOption('second_axis_label', missing='error')
    _third_axis_label = ConfigOption('third_axis_label', None)
    _first_axis_daisychain_id = ConfigOption('first_axis_daisychain_id')  # optional; only needed if daisychain connection
    _second_axis_daisychain_id = ConfigOption('second_axis_daisychain_id')  # optional; only needed if daisychain connection
    _third_axis_daisychain_id = ConfigOption('third_axis_daisychain_id')   # optional; only needed if daisychain connection
    _first_axis_type = ConfigOption('first_axis_type', 'linear', missing='warn')
    _second_axis_type = ConfigOption('second_axis_type', 'linear', missing='warn')
    _third_axis_type = ConfigOption('third_axis_type', None)

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self.first_axis_label = None
        self.second_axis_label = None
        self.third_axis_label = None
        self.pidevice_1st_axis = None
        self.pidevice_2nd_axis = None
        self.pidevice_3rd_axis = None
        self.daisychainid = None
        self.first_axis_ID = None
        self.second_axis_ID = None
        self.third_axis_ID = None

    def on_activate(self):
        """ Initialization: Connection to the dll for all axes.
        Connection can be opened as daisychain or using individual USB connections. This is specified in the config.
        2 or 3 axes can be configured. Daisychain version covers however only the 3 axes case in this version.
        """
        try:
            self.first_axis_label = self._first_axis_label
            self.second_axis_label = self._second_axis_label
            self.third_axis_label = self._third_axis_label

            self.pidevice_1st_axis = GCSDevice(self._first_axis_controllername)  # 1st axis controller # master device if daisy chain
            self.pidevice_2nd_axis = GCSDevice(self._second_axis_controllername)  # 2nd axis controller
            if self._third_axis_controllername:
                self.pidevice_3rd_axis = GCSDevice(self._third_axis_controllername)  # 3rd axis controller

            if self._daisychain_connection:
                # open the daisy chain connection
                self.pidevice_1st_axis.OpenUSBDaisyChain(description=self._serialnum_master)
                self.daisychainid = self.pidevice_1st_axis.dcid
                print(f'Daisychainid: {self.daisychainid}')
                # controllers are ordered with increasing serial number in the daisy chain
                # this is why z is connected as first
                # do we need to programmatically sort by nth_axis_daisychain id ??
                self.pidevice_3rd_axis.ConnectDaisyChainDevice(self._third_axis_daisychain_id, self.daisychainid)  # SN 019550119
                self.pidevice_1st_axis.ConnectDaisyChainDevice(self._first_axis_daisychain_id, self.daisychainid)  # SN 019550121
                self.pidevice_2nd_axis.ConnectDaisyChainDevice(self._second_axis_daisychain_id, self.daisychainid)  # SN 019550124

            else:
                # version with individual connections
                self.pidevice_1st_axis.ConnectUSB(serialnum=self._serialnum_master)
                self.pidevice_2nd_axis.ConnectUSB(serialnum=self._serialnum_second_axis)
                if self.pidevice_3rd_axis:
                    self.pidevice_3rd_axis.ConnectUSB(serialnum=self._serialnum_third_axis)

            print('\n{}:\n{}'.format(self.pidevice_1st_axis.GetInterfaceDescription(), self.pidevice_1st_axis.qIDN()))
            print('\n{}:\n{}'.format(self.pidevice_2nd_axis.GetInterfaceDescription(), self.pidevice_2nd_axis.qIDN()))
            if self.pidevice_3rd_axis:
                print('\n{}:\n{}'.format(self.pidevice_3rd_axis.GetInterfaceDescription(), self.pidevice_3rd_axis.qIDN()))

            # initialization of all axes
            print('Initializing PI stage ...')
            # servo on
            pitools.startup(self.pidevice_1st_axis)
            pitools.startup(self.pidevice_2nd_axis)
            if self.pidevice_3rd_axis:
                pitools.startup(self.pidevice_3rd_axis)
            print('Please wait ... ')

            # the IDs are needed to address the axes in the dll functions
            self.first_axis_ID = self.pidevice_1st_axis.axes[0]    # each controller is connected to one stage; so just take the first element
            # print(self.first_axis_ID)
            self.second_axis_ID = self.pidevice_2nd_axis.axes[0]
            # print(self.second_axis_ID)
            if self.pidevice_3rd_axis:
                self.third_axis_ID = self.pidevice_3rd_axis.axes[0]
                # print(self.third_axis_ID)

            self.calibrate()
            print('done!')

        except Exception as e:
            self.log.error(f'Physik Instrumente stage: Connection failed: {e}.')

    def on_deactivate(self):
        """ Close connection when deactivating the module.
        """
        # go to position (0, 0, 0) or (0, 0)
        if self.pidevice_3rd_axis:
            # first move z to default position and wait until reached
            self.pidevice_3rd_axis.MOV(self.third_axis_ID, 0.0)
            pitools.waitontarget(self.pidevice_3rd_axis, axes=self.third_axis_ID)
        # when z is at safety position, xy move can be done
        self.pidevice_1st_axis.MOV(self.first_axis_ID, 0.0)
        self.pidevice_2nd_axis.MOV(self.second_axis_ID, 0.0)
        pitools.waitontarget(self.pidevice_1st_axis, axes=self.first_axis_ID)
        pitools.waitontarget(self.pidevice_2nd_axis, axes=self.second_axis_ID)

        if self._daisychain_connection:
            self.pidevice_1st_axis.CloseDaisyChain()  # check if connection always done with controller corresponding to 1st axis
            self.pidevice_1st_axis.CloseConnection()

        else:
            self.pidevice_1st_axis.CloseConnection()
            self.pidevice_2nd_axis.CloseConnection()
            if self.pidevice_3rd_axis:
                self.pidevice_3rd_axis.CloseConnection()

# ----------------------------------------------------------------------------------------------------------------------
# Motor interface functions
# ----------------------------------------------------------------------------------------------------------------------

    def get_constraints(self):
        """ Retrieve the hardware constrains from the motor device.

        @return dict: dict with constraints for the motor hardware

        Provides all the constraints for each axis of a motorized stage
        (like total travel distance, velocity, ...)
        Each axis has its own dictionary, where the label is used as the
        identifier throughout the whole module. The dictionaries for each axis
        are again grouped together in a constraints dictionary in the form

            {'<label_axis0>': axis0 }

        where axis0 is again a dict with the possible values defined below. The
        possible keys in the constraint are defined here in the interface file.
        If the hardware does not support the values for the constraints, then
        insert just None. If you are not sure about the meaning, look in other
        hardware files to get an impression.
        """
        constraints = {}

        # retrieve information from hardware
        pos_min_x = self.pidevice_1st_axis.qTMN()[self.first_axis_ID]
        pos_max_x = self.pidevice_1st_axis.qTMX()[self.first_axis_ID]
        vel_min_x = 0  # self.pidevice_c863_x.q
        vel_max_x = 20  # self.pidevice_c863_x.q  # need to find the command

        axis0 = {}
        axis0['label'] = self.first_axis_label   # it is very crucial that this label coincides with the label set in the config.
        axis0['type'] = self._first_axis_type
        if self._first_axis_type == 'rotation':
            unit = 'degree'
        else:
            unit = 'm'
        axis0['unit'] = unit     # the SI units, only possible m or degree
        axis0['ramp'] = None    # do we need this ?
        axis0['pos_min'] = pos_min_x
        axis0['pos_max'] = pos_max_x
        axis0['pos_step'] = pos_max_x
        axis0['vel_min'] = vel_min_x
        axis0['vel_max'] = vel_max_x
        axis0['vel_step'] = 0.01  # can this also be queried ?
        axis0['acc_min'] = None  # do we need this ?
        axis0['acc_max'] = None
        axis0['acc_step'] = None

        # retrieve information from hardware
        pos_min_y = self.pidevice_2nd_axis.qTMN()[self.second_axis_ID]
        pos_max_y = self.pidevice_2nd_axis.qTMX()[self.second_axis_ID]
        vel_min_y = 0  # self.pidevice_c863_y.q
        vel_max_y = 20  # self.pidevice_c863_y.q  # need to find the command

        axis1 = {}
        axis1['label'] = self.second_axis_label    # it is very crucial that this label coincides with the label set in the config.
        axis1['tupe'] = self._second_axis_type
        if self._second_axis_type == 'rotation':
            unit = 'degree'
        else:
            unit = 'm'
        axis1['unit'] = unit    # the SI units, only possible m or degree
        axis1['ramp'] = None    # do we need this ?
        axis1['pos_min'] = pos_min_y
        axis1['pos_max'] = pos_max_y
        axis1['pos_step'] = pos_max_y  # allow to go directly from low limit to maximum
        axis1['vel_min'] = vel_min_y
        axis1['vel_max'] = vel_max_y
        axis1['vel_step'] = 0.01  # can this also be queried ?
        axis1['acc_min'] = None  # do we need this ?
        axis1['acc_max'] = None
        axis1['acc_step'] = None

        # assign the parameter container for each axis to a name which will identify it
        constraints[axis0['label']] = axis0
        constraints[axis1['label']] = axis1

        if self.pidevice_3rd_axis:
            # retrieve information from hardware
            pos_min_z = self.pidevice_3rd_axis.qTMN()[self.third_axis_ID]
            pos_max_z = self.pidevice_3rd_axis.qTMX()[self.third_axis_ID]
            vel_min_z = 0  # self.pidevice_c863_z.q
            vel_max_z = 20  # self.pidevice_c863_z.q  # need to find the command

            axis2 = {}
            axis2['label'] = self.third_axis_label   # it is very crucial that this label coincides with the label set in the config.
            axis2['type'] = self._third_axis_type
            if self._third_axis_type == 'rotation':
                unit = 'degree'
            else:
                unit = 'm'
            axis2['unit'] = unit    # the SI units, only possible m or degree
            axis2['ramp'] = None    # do we need this ?
            axis2['pos_min'] = pos_min_z
            axis2['pos_max'] = pos_max_z
            axis2['pos_step'] = pos_max_z  # can this also be queried from the hardware ? if not just set a reasonable value
            axis2['vel_min'] = vel_min_z
            axis2['vel_max'] = vel_max_z
            axis2['vel_step'] = 0.01  # can this also be queried ?
            axis2['acc_min'] = None  # do we need this ?
            axis2['acc_max'] = None
            axis2['acc_step'] = None

            constraints[axis2['label']] = axis2

        return constraints

    def move_rel(self,  param_dict):
        """ Moves stage in given direction (relative movement).

        :param dict param_dict: Dictionary with axis name and step (in mm units) as key - value pairs

        :return bool: error code (True: ok, False: not ok)
        """
        err = False
        constraints = self.get_constraints()
        cur_pos = self.get_pos()
        for key, value in param_dict.items():  # param_dict has the format {'x': 20, 'y': 0, 'z': 10} for example
            value = np.round(value, decimals=4)  # avoid error due to decimal overflow
            if key == self.first_axis_label:
                if value <= constraints[self.first_axis_label]['pos_step'] and constraints[self.first_axis_label]['pos_min'] <= cur_pos[self.first_axis_label] + value <= constraints[self.first_axis_label]['pos_max']:
                    self.pidevice_1st_axis.MVR(self.first_axis_ID, value)
                    err = True
                else:
                    print('Target value not in allowed range. Relative movement not done.')
            elif key == self.second_axis_label:
                if value <= constraints[self.second_axis_label]['pos_step'] and constraints[self.second_axis_label]['pos_min'] <= cur_pos[self.second_axis_label] + value <= constraints[self.second_axis_label]['pos_max']:
                    self.pidevice_2nd_axis.MVR(self.second_axis_ID, value)
                    err = True
                else:
                    print('Target value not in allowed range. Relative movement not done.')
            elif key == self.third_axis_label:
                if value <= constraints[self.third_axis_label]['pos_step'] and constraints[self.third_axis_label]['pos_min'] <= cur_pos[self.third_axis_label] + value <= constraints[self.third_axis_label]['pos_max']:
                    self.pidevice_3rd_axis.MVR(self.third_axis_ID, value)
                    err = True
                else:
                    print('Target value not in allowed range. Relative movement not done.')
            else:
                print('Given axis not available: {key}.')

        return err

    def move_abs(self, param_dict):
        """ Moves stage to absolute position (absolute movement)

        :param dict param_dict: Dictionary with axis name and target position (in um units) as key - value pairs

        :return bool: error code (True: ok, False: error)
        """
        err = False
        constraints = self.get_constraints()
        for key, value in param_dict.items():
            value = np.round(value, decimals=4)  # avoid error due to decimal overflow
            if key == self.first_axis_label:
                if constraints[self.first_axis_label]['pos_min'] <= value <= constraints[self.first_axis_label]['pos_max']:
                    self.pidevice_1st_axis.MOV(self.first_axis_ID, value)
                    err = True
                else:
                    print('Target value not in allowed range. Absolute movement not done.')
            elif key == self.second_axis_label:
                if constraints[self.second_axis_label]['pos_min'] <= value <= constraints[self.second_axis_label]['pos_max']:
                    self.pidevice_2nd_axis.MOV(self.second_axis_ID, value)
                    err = True
                else:
                    print('Target value not in allowed range. Absolute movement not done.')
            elif key == self.third_axis_label:
                if constraints[self.third_axis_label]['pos_min'] <= value <= constraints[self.third_axis_label]['pos_max']:
                    self.pidevice_3rd_axis.MOV(self.third_axis_ID, value)
                    err = True
                else:
                    print('Target value not in allowed range. Absolute movement not done.')
            else:
                print('Given axis not available.')
        return err

    def abort(self):
        """ Stops movement of the stage.

        :return bool: error code (True: ok, False: error)
        """
        self.pidevice_1st_axis.HLT(noraise=True)  # noraise option silences GCSerror 10
        self.pidevice_2nd_axis.HLT(noraise=True)
        if self.pidevice_3rd_axis:
            self.pidevice_3rd_axis.HLT(noraise=True)
        print('Movement aborted.')
        return True

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
            x_pos = self.pidevice_1st_axis.qPOS()[self.first_axis_ID]  # qPOS returns OrderedDict, we just need the value for the single axis
            y_pos = self.pidevice_2nd_axis.qPOS()[self.second_axis_ID]
            positions = [x_pos, y_pos]
            keys = [self.first_axis_label, self.second_axis_label]
            if self.pidevice_3rd_axis:
                z_pos = self.pidevice_3rd_axis.qPOS()[self.third_axis_ID]
                positions.append(z_pos)
                keys.append(self.third_axis_label)

            pos_dict = dict(zip(keys, positions))
            return pos_dict
        else:
            pos_dict = {}
            for item in param_list:
                if item == self.first_axis_label:
                    x_pos = self.pidevice_1st_axis.qPOS()[self.first_axis_ID]
                    pos_dict[item] = x_pos
                elif item == self.second_axis_label:
                    y_pos = self.pidevice_2nd_axis.qPOS()[self.second_axis_ID]
                    pos_dict[item] = y_pos
                elif item == self.third_axis_label:
                    z_pos = self.pidevice_3rd_axis.qPOS()[self.third_axis_ID]
                    pos_dict[item] = z_pos
                else:
                    print('Given axis not available: {item}.')
            return pos_dict

    def get_status(self, param_list=None):
        """ Get the status of the position.

        :param list param_list: optional, if a specific status of an axis
                                is desired, then the labels of the needed
                                axis should be passed in the param_list.
                                If nothing is passed, then from each axis the
                                status is asked.

        :return dict: with the axis label as key and the status as item.
        """
        if not param_list:
            x_status = self.pidevice_1st_axis.qONT()[self.first_axis_ID]
            y_status = self.pidevice_2nd_axis.qONT()[self.second_axis_ID]
            on_target = [x_status, y_status]
            keys = [self.first_axis_label, self.second_axis_label]
            if self.pidevice_3rd_axis:
                z_status = self.pidevice_3rd_axis.qONT()[self.third_axis_ID]
                on_target.append(z_status)
                keys.append(self.third_axis_label)
            status_dict = dict(zip(keys, on_target))
            return status_dict
        else:
            status_dict = {}
            for item in param_list:
                if item == self.first_axis_label:
                    x_status = self.pidevice_1st_axis.qONT()[self.first_axis_ID]
                    status_dict[item] = x_status
                elif item == self.second_axis_label:
                    y_status = self.pidevice_2nd_axis.qONT()[self.second_axis_ID]
                    status_dict[item] = y_status
                elif item == self.third_axis_label:
                    z_status = self.pidevice_3rd_axis.qONT()[self.third_axis_ID]
                    status_dict[item] = z_status
                else:
                    print('Given axis not available.')
            return status_dict

    def calibrate(self, param_list=None):
        """ Calibrates the stage.

        @param dict param_list: param_list: optional, if a specific calibration
                                of an axis is desired, then the labels of the
                                needed axis should be passed in the param_list.
                                If nothing is passed, then all connected axis
                                will be calibrated.

        @return int: error code (0:OK, -1:error)

        After calibration the stage moves to home position which will be the
        zero point for the passed axis. The calibration procedure will be
        different for each stage.
        """
        # RON: sets referencing mode for given axis
        # FNL: fast move to negative limit  # not possible for rotation axis
        # FRF: fast move to reference switch
        err = -1
        if not param_list:
            # 3rd axis is typically z. Calibrate and move first z to negative limit
            if self.pidevice_3rd_axis:
                self.pidevice_3rd_axis.RON(self.third_axis_ID, values=1)
                if self._third_axis_type == 'rotation':
                    self.pidevice_3rd_axis.FRF(self.third_axis_ID)
                else:
                    self.pidevice_3rd_axis.FNL(self.third_axis_ID)
                pitools.waitontarget(self.pidevice_3rd_axis, axes=self.third_axis_ID)

            self.pidevice_1st_axis.RON(self.first_axis_ID, values=1)
            if self._first_axis_type == 'rotation':
                self.pidevice_1st_axis.FRF(self.first_axis_ID)
            else:
                self.pidevice_1st_axis.FNL(self.first_axis_ID)

            self.pidevice_2nd_axis.RON(self.second_axis_ID, values=1)
            if self._second_axis_type == 'rotation':
                self.pidevice_2nd_axis.FRF(self.second_axis_ID)
            else:
                self.pidevice_2nd_axis.FNL(self.second_axis_ID)

            pitools.waitontarget(self.pidevice_1st_axis, axes=self.first_axis_ID)
            pitools.waitontarget(self.pidevice_2nd_axis, axes=self.second_axis_ID)
            err = 0

        else:
            for item in param_list:
                if item == self.first_axis_label:
                    self.pidevice_1st_axis.RON(self.first_axis_ID, values=1)
                    if self._first_axis_type == 'rotation':
                        self.pidevice_1st_axis.FRF(self.first_axis_ID)
                    else:
                        self.pidevice_1st_axis.FNL(self.first_axis_ID)
                    pitools.waitontarget(self.pidevice_1st_axis, axes=self.first_axis_ID)
                    err = 0
                elif item == self.second_axis_label:
                    self.pidevice_2nd_axis.RON(self.second_axis_ID, values=1)
                    if self._second_axis_type == 'rotation':
                        self.pidevice_2nd_axis.FRF(self.second_axis_ID)
                    else:
                        self.pidevice_2nd_axis.FNL(self.second_axis_ID)
                    pitools.waitontarget(self.pidevice_2nd_axis, axes=self.second_axis_ID)
                    err = 0
                elif item == self.third_axis_label:
                    self.pidevice_3rd_axis.RON(self.third_axis_ID, values=1)
                    if self._third_axis_type == 'rotation':
                        self.pidevice_3rd_axis.FRF(self.third_axis_ID)
                    else:
                        self.pidevice_3rd_axis.FNL(self.third_axis_ID)
                    pitools.waitontarget(self.pidevice_3rd_axis, axes=self.third_axis_ID)
                    err = 0
                else:
                    print('Given axis not available.')
        return err

    def get_velocity(self, param_list=None):
        """ Gets the current velocity for all connected axes.

        :param: dict param_list: optional, if a specific velocity of an axis
                                is desired, then the labels of the needed
                                axis should be passed as the param_list.
                                If nothing is passed, then from each axis the
                                velocity is asked.

        :return: dict vel_dict: dictionary with the axis label as key and the velocity as item.
        """
        if not param_list:
            x_vel = self.pidevice_1st_axis.qVEL()[self.first_axis_ID]  # qVEL returns OrderedDict, we just need the value for the single axis
            y_vel = self.pidevice_2nd_axis.qVEL()[self.second_axis_ID]
            velocity = [x_vel, y_vel]
            keys = [self.first_axis_label, self.second_axis_label]
            if self.pidevice_3rd_axis:
                z_vel = self.pidevice_3rd_axis.qVEL()[self.third_axis_ID]
                velocity.append(z_vel)
                keys.append(self.third_axis_label)

            vel_dict = dict(zip(keys, velocity))
            return vel_dict
        else:
            vel_dict = {}
            for item in param_list:
                if item == self.first_axis_label:
                    x_vel = self.pidevice_1st_axis.qVEL()[self.first_axis_ID]
                    vel_dict[item] = x_vel
                elif item == self.second_axis_label:
                    y_vel = self.pidevice_2nd_axis.qVEL()[self.second_axis_ID]
                    vel_dict[item] = y_vel
                elif item == self.third_axis_label:
                    z_vel = self.pidevice_3rd_axis.qVEL()[self.third_axis_ID]
                    vel_dict[item] = z_vel
                else:
                    print('Given axis not available.')
            return vel_dict

    def set_velocity(self, param_dict):
        """ Write new value for velocity.

        :param: dict param_dict: dictionary, which passes all the relevant
                                parameters, which should be changed. Usage:
                                 {'axis_label': <the-velocity-value>}.
                                 'axis_label' must correspond to a label given
                                 to one of the axis.

        :return: int: error code (0:OK, -1:error)
        """
        err = -1
        constraints = self.get_constraints()
        for key, value in param_dict.items():  # param_dict has the format {'x': 20, 'y': 0, 'z': 10} for example
            if key == self.first_axis_label:
                if constraints[self.first_axis_label]['vel_min'] <= value <= constraints[self.first_axis_label]['vel_max']:
                    self.pidevice_1st_axis.VEL(self.first_axis_ID, value)
                    err = 0
                else:
                    print('Target value not in allowed range. Velocity not set.')
            elif key == self.second_axis_label:
                if constraints[self.second_axis_label]['vel_min'] <= value <= constraints[self.second_axis_label]['vel_max']:
                    self.pidevice_2nd_axis.VEL(self.second_axis_ID, value)
                    err = 0
                else:
                    print('Target value not in allowed range. Velocity not set.')
            elif key == self.third_axis_label:
                if constraints[self.third_axis_label]['vel_min'] <= value <= constraints[self.third_axis_label]['vel_max']:
                    self.pidevice_3rd_axis.VEL(self.third_axis_ID, value)
                    err = 0
                else:
                    print('Target value not in allowed range. Velocity not set.')
            else:
                print('Given axis not available.')

        return err

    def wait_for_idle(self):
        """ Wait until a motorized stage is in idle state.
        :return: None
        """
        pitools.waitontarget(self.pidevice_1st_axis, axes=self.first_axis_ID)
        pitools.waitontarget(self.pidevice_2nd_axis, axes=self.second_axis_ID)
        if self.pidevice_3rd_axis:
            pitools.waitontarget(self.pidevice_3rd_axis, axes=self.third_axis_ID)


# if __name__ == '__main__':
#     pistage = PIMotorStage()
#     pistage.on_activate()
#     init_pos = pistage.get_pos()
#     print(f'init_pos: {init_pos}')
#     pistage.pidevice_c863_x.MOV(pistage.x_axis_ID, 10.0)
#     pitools.waitontarget(pistage.pidevice_c863_x, axes=pistage.x_axis_ID)
#     print('moved')
#     pistage.pidevice_c863_x.MOV(pistage.x_axis_ID, 15.0)
#     pitools.waitontarget(pistage.pidevice_c863_x, axes=pistage.x_axis_ID)
#     print('moved')
#     constraints = pistage.get_constraints()
#     print(constraints)
#     pos = pistage.get_pos()
#     print(pos)
#     x_pos = pistage.get_pos(['x'])
#     print(x_pos)
#     yz_pos = pistage.get_pos(['y', 'z'])
#     print(yz_pos)
#     f_pos = pistage.get_pos(['f'])
#     print(f_pos)
#     xf_pos = pistage.get_pos(['x', 'f'])
#     print(xf_pos)
#
#     vel = pistage.get_velocity()
#     print(f'velocity {vel}')
#     x_vel = pistage.get_velocity(['x'])
#     print(x_vel)
#     yz_vel = pistage.get_velocity(['y', 'z'])
#     print(yz_vel)
#     f_vel = pistage.get_velocity('f')
#     print(f_vel)
#     xf_vel = pistage.get_velocity(['x', 'f'])
#     print(xf_vel)
#
#     pistage.move_abs({'x': 20})
#     pos = pistage.get_pos()
#     print(pos)
#
#     pistage.move_rel({'x': 5, 'y': 7, 'z': 1})
#     pos = pistage.get_pos()
#     print(pos)
#
#     pistage.move_rel({'x': 199, 'y': 7, 'z': 1})
#     pos = pistage.get_pos()
#     print(pos)
#
#     err = pistage.pidevice_c863_x.MVR(pistage.x_axis_ID, 5)
#     print(err)
#
#     err = pistage.pidevice_c863_x.HLT(noraise=True)
#     print(err)
#
#     pos = pistage.get_pos()
#     print(pos)
#
#     pistage.calibrate()
#
#     pistage.move_abs({'x': 17, 'y': 7, 'z': 0})
#
#     pistage.calibrate({'x'})
#
#     ready_x = pistage.pidevice_c863_x.IsControllerReady()
#     print(ready_x)
#
#     ready_y = pistage.pidevice_c863_y.IsControllerReady()
#     print(ready_y)
#
#
#     pistage.on_deactivate()

# query min max speed
# qOVL, qVLS ?? to test
