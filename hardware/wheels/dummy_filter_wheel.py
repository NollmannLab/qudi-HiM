# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains the dummy implementation of a motorized filterwheel.

An extension to Qudi.

@author: F. Barho

Created on Tue Nov 17 2020
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
from core.configoption import ConfigOption
from interface.filterwheel_interface import FilterwheelInterface


class FilterwheelDummy(Base, FilterwheelInterface):
    """ Hardware class representing a dummy filterwheel.

    Example config for copy-paste:

    wheel_dummy:
        module.Class: 'wheels.dummy_filter_wheel.FilterwheelDummy'
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

            # please specify for all elements corresponding information in the same order.
            # allowed lasers:
            # entries corresponding to [laser1_allowed, laser2_allowed, laser3_allowed, laser4_allowed, ..]
            # see also the config for the daq ao output to associate a laser number to a wavelength
    """
    # config options
    _num_filters = ConfigOption('num_filters', 6)
    _filternames = ConfigOption('filters', missing='error')
    _positions = ConfigOption('filterpositions', missing='error')
    _allowed_lasers = ConfigOption('allowed_lasers', missing='error')

    position = np.random.randint(1, 7)  # generate an arbitrary start value from 1 to 6

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def on_activate(self):
        """ Module activation method. """
        if len(self._filternames) != self._num_filters or len(self._positions) != self._num_filters or len(self._allowed_lasers) != self._num_filters:
            self.log.warning('Please specify name, position, and allowed lasers for each filter')

    def on_deactivate(self):
        """ Module deactivation method. """
        pass

# ----------------------------------------------------------------------------------------------------------------------
# Filterwheel interface functions
# ----------------------------------------------------------------------------------------------------------------------

    def get_position(self):
        """ Get the current position.
         :return int position: number of the filterwheel position that is currently set """
        return self.position

    def set_position(self, target_position):
        """ Set the position to a given value.

        :param: int target_position: position number
        :return: int error code: ok = 0
        """
        if target_position in range(1, self._num_filters + 1):
            self.position = target_position
            err = 0
        else:  
            self.log.error(f'Can not go to filter {target_position}. Filterwheel has only {self._num_filters} positions')
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

        @returns: filter_dict
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
