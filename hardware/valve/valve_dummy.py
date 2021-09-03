# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains a class representing a modular valve positioner dummy implementation.

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
from time import sleep
from core.module import Base
from interface.valvepositioner_interface import ValvePositionerInterface
from core.configoption import ConfigOption


class ValveDummy(Base, ValvePositionerInterface):
    """ Dummy implementation of a modular valve positioner.

    Example config for copy-paste:

    valve_dummy:
        module.Class: 'valve.valve_dummy.ValveDummy'
        num_valves: 3
        daisychain_ID:
            - 'a'
            - 'b'
            - 'c'
        name:
            - 'Buffer 8-way valve'
            - 'RT rinsing 2-way valve'
            - 'Syringe 2-way valve'
        number_outputs:
            - 8
            - 2
            - 2
        valve_positions:
            - - '1'
              - '2'
              - '3'
              - '4'
              - '5'
              - '6'
              - '7'
              - '8'
            - - '1: Rinse needle'
              - '2: Inject probe'
            - - '1: Syringe'
              - '2: Pump'

    # please specify for all elements corresponding information in the same order,
    # starting from the first valve in the daisychain (valve 'a')

    """
    # config options
    _num_valves = ConfigOption('num_valves', missing='warn')
    _valve_names = ConfigOption('name', missing='warn')
    _daisychain_IDs = ConfigOption('daisychain_ID', missing='warn')
    _number_outputs = ConfigOption('number_outputs', missing='warn')
    valve_positions = ConfigOption('valve_positions', [])

    init_pos = 1  # initial  position for all valves
    position_dict = {}  # store the positions in this dictionary instead of retrieving them from hardware

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

    def on_activate(self):
        """ Initialisation performed during activation of the module. """
        # initialize the position_dict using the initial position
        for i in range(self._num_valves):
            self.set_valve_position(self._daisychain_IDs[i], self.init_pos)

    def on_deactivate(self):
        """ Perform required deactivation. """
        pass

# ----------------------------------------------------------------------------------------------------------------------
# Valvepositioner interface functions
# ----------------------------------------------------------------------------------------------------------------------

    def get_valve_dict(self):
        """ This method retrieves a dictionary with the following entries, containing relevant information for each
        valve positioner in a daisychain:
                    {'a': {'daisychain_ID': 'a', 'name': str name, 'number_outputs': int number_outputs},
                    {'b': {'daisychain_ID': 'b', 'name': str name, 'number_outputs': int number_outputs},
                    ...
                    }

        :return: dict valve_dict: dictionary following the example shown above
        """
        valve_dict = {}

        for i in range(self._num_valves):
            dic_entry = {'daisychain_ID': self._daisychain_IDs[i],
                         'name': self._valve_names[i],
                         'number_outputs': self._number_outputs[i],
                         }

            valve_dict[dic_entry['daisychain_ID']] = dic_entry

        return valve_dict

    def get_status(self):
        """ This method reads the valve status and returns it.

        :return: dict: containing the valve ID as key and the str status code as value (N=not executed - Y=idle - *=busy)
        """
        status = ['Y'] * len(self._daisychain_IDs)
        status_dict = dict(zip(self._daisychain_IDs, status))
        return status_dict

    def get_valve_position(self, valve_address):
        """ This method gets the current position of the valve positioner.

        :param: str valve_address: ID of the valve positioner

        :return: int position: position of the valve positioner specified by valve_address
        """
        if valve_address in self._daisychain_IDs:
            return self.position_dict[valve_address]
        else:
            self.log.warn(f'Valve {valve_address} not available.')

    def set_valve_position(self, valve_address, target_position):
        """ This method sets the valve position for the valve specified by valve_address.

        :param: str valve address: ID of the valve positioner (eg. "a")
        :param: int target_position: new position for the valve at valve_address

        :return: None
        """
        if valve_address in self._daisychain_IDs:
            max_pos = self.get_valve_dict()[valve_address]['number_outputs']
            if target_position > max_pos:
                self.log.warn(f'Target position out of range for valve {valve_address}. Position not set.')
            else:
                self.position_dict[valve_address] = target_position
                self.log.info(f'Set {self.get_valve_dict()[valve_address]["name"]} to position {target_position}')
        else:
            self.log.warn(f'Valve {valve_address} not available.')

    def wait_for_idle(self):
        """ Wait for the valves to be idle. This is important when one wants to
        read the position of a valve or make sure the valves are not moving before
        starting an injection.

        :return: None
        """
        sleep(0.5)
