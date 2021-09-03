# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains the hardware class representing a Thorlabs fast filterwheel.

An extension to Qudi.

@author: F. Barho

Created on Tue Jun 30 2020
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
import thorlabs_apt as apt
from core.module import Base
from interface.filterwheel_interface import FilterwheelInterface
from core.configoption import ConfigOption


class ThorlabsFastFilterWheel(Base, FilterwheelInterface):
    """ Hardware class representing the Thorlabs fast filterwheel.
    6 positions

    Example config for copy-paste:

    thorlabs_fast_wheel:
        module.Class: 'wheels.thorlabs_fast_filter_wheel.ThorlabsFastFilterWheel'
        serial_num: 40846334
        num_filters: 6
        filterpositions:
            - 1
            - 2
            - 3
            - 4
            - 5
            - 6
        filters:
            - '700 +/- 37 nm'
            - '600 +/- 25 nm'
            - '488 - 491 / 561 nm'
            - '525 +/- 22.5 nm'
            - '617 +/- 36 nm'
            - '460 +/- 25 nm'
        allowed_lasers:
            - [True, True, True, True]
            - [True, True, True, True]
            - [True, True, True, True]
            - [True, True, True, True]
            - [True, True, True, False]
            - [True, False, True, True]
    """
    # config options
    serial_number = ConfigOption('serial_num', missing='error')
    _num_filters = ConfigOption('num_filters', 6)
    _filternames = ConfigOption('filters', missing='error')
    _positions = ConfigOption('filterpositions', missing='error')
    _allowed_lasers = ConfigOption('allowed_lasers', missing='error')

    # attributes
    _position_dict = {}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._motor = None

    def on_activate(self):
        """ Module activation method. """
        # devices = apt.list_available_devices()
        # print(devices)
        self._motor = apt.Motor(self.serial_number)
        self.move_home()
        self._position_dict = self.init_position_dict()

    def on_deactivate(self):
        """ Disconnect from hardware on deactivation. """
        pass

# ----------------------------------------------------------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------------------------------------------------------

    def init_position_dict(self):
        """ Initialize the dictionary containing filter positions as key and corresponding angles of the wheel as
        values.
        :return dict position_dict: {1: 0, 2: 300, 3: 240, 4: 180, 5: 120, 6: 60} for a standard wheel with
                                    6 filters
        """
        pos_dict = {}
        for i in range(self._num_filters):
            if i == 0:
                pos_dict[i+1] = -360/self._num_filters * i
            else:
                pos_dict[i+1] = -360/self._num_filters * i + 360
        return pos_dict
    # try to combine this to one single formula calculating values between 0 and 359

# Functions from Thorlabs apt library ----------------------------------------------------------------------------------
    def move_home(self):
        """ Move the motor to its home position and wait until the home position is reached (blocking = True)
         """
        self._motor.move_home(blocking=True)

    def move_by(self, angle):
        """ Perform a relative movement and wait until the target position is reached.
        :param: float angle: rotation angle
        :return: None
        """
        self._motor.move_by(angle, blocking=True)

    def move_to(self, position):
        """ Perform an absolute movement and wait until the target position is reached.
        :param: float position: target position in degree
        :return: None
        """
        self._motor.move_to(position)

    def get_motor_position(self):
        """ Read the current motor position.
        :return: float motor_pos: current rotation angle in degree
        """
        motor_pos = self._motor.position
        return motor_pos

# ----------------------------------------------------------------------------------------------------------------------
# Filterwheel interface functions
# ----------------------------------------------------------------------------------------------------------------------

    def get_position(self):
        """ Get the current position, from 1 to num_filters.
        :return int position: number of the filterwheel position that is currently set """
        motor_pos = np.round(self._motor.position, decimals=0)  # round to integer value for angle
        inv_dict = dict([(value, key) for key, value in self._position_dict.items()])
        try:
            pos = inv_dict[motor_pos]
        except KeyError:
            self.log.warning('Filter position does not correspond to a valid position. Please reset filterwheel to home position.')
            pos = 0
        return pos

    def set_position(self, target_position):
        """ Set the position to a given value.
        The wheel will take the shorter path. If upward or downward are equivalent, the wheel take the upward path.

        :param: int target_position: position number
        :return: int error code: ok = 0
        """
        if target_position < self._num_filters + 1:
            motor_pos = self._position_dict[target_position]
            self.move_to(motor_pos)
            err = 0
        else:
            self.log.error('Can not go to filter {0}. Filterwheel has only {1} positions'.format(target_position, self._num_filters))
            err = -1
        return err

    def get_filter_dict(self):
        """ Retrieves a dictionary with the following entries:
                    {'filter1': {'label': 'filter1', 'name': str(name), 'position': 1, 'lasers': bool list},
                     'filter2': {'label': 'filter2', 'name': str(name), 'position': 2, 'lasers': bool list},
                    ...
                    }

                    # all positions of the filterwheel must be defined even when empty.
                    Match the dictionary key 'filter1' to the position 1 etc.

        :return: dict filter_dict
        """
        filter_dict = {}

        for i, item in enumerate(
                self._filternames):  # use any of the lists retrieved as config option, just to have an index variable
            label = 'filter{}'.format(i + 1)  # create a label for the i's element in the list starting from 'filter1'

            dic_entry = {'label': label,
                         'name': self._filternames[i],
                         'position': self._positions[i],
                         'lasers': self._allowed_lasers[i]}

            filter_dict[dic_entry['label']] = dic_entry

        return filter_dict
