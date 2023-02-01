# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains a class representing a Hamilton modular valve positioner (MVP).

An extension to Qudi.

@author: JB. Fiche

Created on Mon Nov 16 2020
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
import serial
from time import sleep

from core.module import Base
from interface.valvepositioner_interface import ValvePositionerInterface
from core.configoption import ConfigOption


class HamiltonValve(Base, ValvePositionerInterface):
    """ Class representing the Hamilton MVP
    
    Example config for copy-paste:
        
    hamilton_mvc:
        module.Class: 'valve.hamilton_valve.HamiltonValve'
        com_port: 'COM1'
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
            - - '1': Rinse needle
              - '2': Inject probe
            - - '1': Syringe
              - '2': Pump

    # please specify for all elements corresponding information in the same order,
    # starting from the first valve in the daisychain (valve 'a')
    """
    # config options
    _com_port = ConfigOption("com_port", missing="error")
    _num_valves = ConfigOption('num_valves', missing='warn')
    _valve_names = ConfigOption('name', missing='warn')
    _daisychain_IDs = ConfigOption('daisychain_ID', missing='warn')
    _number_outputs = ConfigOption('number_outputs', missing='warn')
    valve_positions = ConfigOption('valve_positions', [])  # optional; if labels instead of only valve numbers on the GUI are desired

    _valve_state = {}  # dictionary holding the valve names as keys and their status as values # {'a': status_valve1, ..}
    
    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self._serial_connection = None

    def on_activate(self):
        """ Initialization: open the serial port.
        """
        try:
            self._serial_connection = serial.Serial(self._com_port, baudrate=9600, bytesize=serial.SEVENBITS, parity=serial.PARITY_ODD, stopbits=serial.STOPBITS_ONE, timeout=1.0)
            sleep(2)  # keep 2 s time delay to ensure that communication has been established
        except serial.SerialException:
            self.log.error(f'Hamilton MVP not connected. Check if device is switched on.')
            return
        
        # initialization of the daisy chain
        cmd = "1a\r"
        self.write(cmd)
        
        # add the initialisation of every valve. In the daisy chain, the valves 
        # are referenced by a letter, starting with "a". The valve status dictionary
        # is created during this process.
        for n in range(self._num_valves):
            cmd = chr(n+97) + "LXR\r"
            self.write(cmd)
            # self._valve_state[chr(n+97)] = 'Idle'
        self.wait_for_idle()
        print('Hamilton valves initialization OK')
        self._valve_state = self.get_status()

    def on_deactivate(self):
        """ Close serial port when deactivating the module.
        """
        self._serial_connection.close()

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
        for n in range(self._num_valves):
            cmd = chr(n+97) + "F\r"
            self.write(cmd)
            status = self.read()

            self._valve_state[chr(n+97)] = status
        return self._valve_state

    def get_valve_position(self, valve_address):
        """ This method gets the current position of the valve positioner.

        :param: str valve_address: ID of the valve positioner

        :return: int position: position of the valve positioner specified by valve_address
        """
        if valve_address in self._daisychain_IDs:
            cmd = valve_address + "LQP\r"
            self.write(cmd)
            pos = self.read()
            return int(pos)
        else:
            self.log.warn(f'Valve {valve_address} not available.')

    def set_valve_position(self, valve_address, target_position):
        """ This method sets the valve position for the valve specified by valve_address.

        :param: str valve address: ID of the valve positioner (eg. "a")
        :param: int target_position: new position for the valve at valve_address

        :return: None
        """
        if valve_address in self._daisychain_IDs:
            start_pos = self.get_valve_position(valve_address)
            max_pos = self.get_valve_dict()[valve_address]['number_outputs']
            if target_position > max_pos:
                self.log.warn(f'Target position out of range for valve {valve_address}. Position not set.')
            else:
                if (start_pos > target_position and abs(target_position - start_pos) < max_pos/2) or (start_pos < target_position and abs(target_position-start_pos) > max_pos/2):
                    cmd = valve_address + "LP1" + str(target_position) + "R\r"
                else:
                    cmd = valve_address + "LP0" + str(target_position) + "R\r"
                self.write(cmd)
                self.log.info(f'Set {self.get_valve_dict()[valve_address]["name"]} to position {target_position}')
        else:
            self.log.warn(f'Valve {valve_address} not available.')

    def wait_for_idle(self):
        """ Wait for the valves to be idle. This is important when one wants to
        read the position of a valve or make sure the valves are not moving before
        starting an injection.

        :return: None
        """
        self.get_status()
        for n in range(self._num_valves):
            while self._valve_state[chr(n+97)] != "Y":
                sleep(0.5)
                self.get_status()
                # this waits on valve 'a' until idle before moving to the next one

# ----------------------------------------------------------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------------------------------------------------------

    def write(self, command):
        """ Clears the input buffer and writes an utf-8 encoded command to the serial port 
        
        :param: str command: message to send to the serial port
        """
        self._serial_connection.flushInput()
        self._serial_connection.write(command.encode())
        
    def read(self):
        """ Read the buffer of the valve. The first line does not contain relevant
        information. Only the second line is useful.

        :return: str output: text read from the valve buffer
        """
        self._serial_connection.read()
        output = self._serial_connection.read()
        output = output.decode('utf-8')
        # output = self._serial_connection.read().decode('utf-8')
        return output

# To do: for the moment no time out for the wait for idle -> should add one.
# add try except in on_activate
