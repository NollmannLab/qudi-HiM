# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains a dummy implementation as connector on experimental setups where the filter position cannot be
changed. (Multiband filter)

An extension to Qudi.

@author: F. Barho
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

from core.module import Base
from core.configoption import ConfigOption
from interface.filterwheel_interface import FilterwheelInterface


class NoFilterDummy(Base, FilterwheelInterface):
    """ This class is used as placeholder connector for experimental setups without filterwheel.

    Example config for copy-paste:

    nofilter_dummy:
        module.Class: 'wheels.dummy_nofilter.NoFilterDummy'
        num_filters: 1
        filterpositions:
            - 1
        filters:
            - 'quad-band filter'
        allowed_lasers:
            - [True, True, True, True]

            # please specify for all elements corresponding information in the same order.
    """
    # config options
    _num_filters = ConfigOption('num_filters', 1)
    _filternames = ConfigOption('filters', missing='error')
    _positions = ConfigOption('filterpositions', missing='error')
    _allowed_lasers = ConfigOption('allowed_lasers', missing='error')

    position = 1

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
         :return int position: constant position = 1 """
        return self.position

    def set_position(self, target_value):
        """ Set the position to a given value. Not applicable here.

        :param: int target_position: position number
        :return: int error code: ok = 0
        """
        return 0

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
