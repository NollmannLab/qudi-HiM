# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains the interface for the control of a modular valve positioner.

An extension to Qudi.

@author: JB. Fiche, F. Barho
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


class ValvePositionerInterface(metaclass=InterfaceMetaclass):
    """
    This module contains the interface for the control of a valve positioner.
    """

    @abstract_interface_method
    def get_valve_dict(self):
        """ This method retrieves a dictionary with the following entries, containing relevant information for each
        valve positioner in a daisychain:
                    {'a': {'daisychain_ID': 'a', 'name': str name, 'number_outputs': int number_outputs},
                    {'b': {'daisychain_ID': 'b', 'name': str name, 'number_outputs': int number_outputs},
                    ...
                    }

        :return: dict valve_dict: dictionary following the example shown above
        """
        pass

    @abstract_interface_method
    def get_status(self):
        """ This method reads the valve status and returns it.

        :return: dict: containing the valve ID as key and the str status code as value (N=not executed - Y=idle - *=busy)
        """
        pass

    @abstract_interface_method
    def get_valve_position(self, valve_address):
        """ This method gets the current position of the valve positioner.

        :param: str valve_address: ID of the valve positioner

        :return: int position: position of the valve positioner specified by valve_address
        """
        pass

    @abstract_interface_method
    def set_valve_position(self, valve_address, target_position):
        """ This method sets the valve position for the valve specified by valve_address.

        :param: str valve address: ID of the valve positioner (eg. "a")
        :param: int target_position: new position for the valve at valve_address

        :return: None
        """
        pass

    @abstract_interface_method
    def wait_for_idle(self):
        """ Wait for the valves to be idle. This is important when one wants to
        read the position of a valve or make sure the valves are not moving before
        starting an injection.

        :return: None
        """
        pass
