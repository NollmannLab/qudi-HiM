# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains the interface for the control of a motorized filterwheel.

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
from core.interface import abstract_interface_method
from core.meta import InterfaceMetaclass


class FilterwheelInterface(metaclass=InterfaceMetaclass):
    """ This interface contains the necessary functions to be implemented for a motorized filterwheel.
    """

    @abstract_interface_method
    def get_position(self):
        """ Get the current position.
         :return int position: number of the filterwheel position that is currently set """
        pass

    @abstract_interface_method
    def set_position(self, target_position):
        """ Set the position to a given value.

        :param: int target_position: position number
        :return: int error code: ok = 0
        """
        pass

    @abstract_interface_method
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
        pass
