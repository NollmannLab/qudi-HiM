"""
Qudi-CBS

This module contains the hardware class representing the Arduino uno.
It is used to control digital output that can be used as trigger for a connected device.

An extension to Qudi.

@author: D. Guerin, JB. Fiche

Created on Tue may 28, 2024
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

import time
import serial
from core.configoption import ConfigOption
from core.module import Base


class ArduinoUno(Base):

    _arduino_port = ConfigOption('arduino_port', None)
    _valve_odor_1_write = ConfigOption('valve_odor_1_write', None)
    _valve_odor_2_write = ConfigOption('valve_odor_2_write', None)
    _valve_odor_3_write = ConfigOption('valve_odor_3_write', None)
    _valve_odor_4_write = ConfigOption('valve_odor_4_write', None)
    _valve_odor_1_read = ConfigOption('valve_odor_1_read', None)
    _valve_odor_2_read = ConfigOption('valve_odor_2_read', None)
    _valve_odor_3_read = ConfigOption('valve_odor_3_read', None)
    _valve_odor_4_read = ConfigOption('valve_odor_4_read', None)
    _mixing_valve_write = ConfigOption('mixing_valve_write', None)
    _mixing_valve_read = ConfigOption('mixing_valve_read', None)
    _switch_valve_write = ConfigOption('final_valve_write', None)
    _switch_valve_read = ConfigOption('final_valve_read', None)

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self.arduino = None
        self._odor_valves_pin = {"odor_1": [self._valve_odor_1_write, self._valve_odor_1_read],
                                 "odor_2": [self._valve_odor_2_write, self._valve_odor_2_read],
                                 "odor_3": [self._valve_odor_3_write, self._valve_odor_3_read],
                                 "odor_4": [self._valve_odor_4_write, self._valve_odor_4_read]}

    def on_activate(self):
        """
        Initialize the arduino uno device
        """
        try:
            self.arduino = serial.Serial(self._arduino_port, 9600, timeout=1)
        except Exception as err:
            self.log.error(f'Could not open arduino on port {self._arduino_port}. If access refused: close every '
                           f'arduino user software. Error message : {err}')
            self.arduino.close()

    def on_deactivate(self):
        self.arduino.close()

# ======================================================================================================================
# Basic methods for communicating with Arduino
# ======================================================================================================================
    def write_to_digital_pin(self, pin, state):
        """
        Send a command to the Arduino to be decrypted and processed.
        @param pin: (int) pin number on the Arduino to which the command is addressed. This should be an integer
        representing the pin.(2 to 13)
        @param state: (bool) The state to be set for the specified pin. This should be an integer or string
        representing the desired state.
        """
        if not self.arduino.is_open:
            self.log.error("Serial connection for the Arduino is lost!")
            return None
        try:
            # Create the command string
            command = f"{pin}{state}\n"
            self.arduino.write(command.encode())
            time.sleep(0.1)

            # Read and print all available responses from the Arduino
            response = self.arduino.readline().decode().strip()
            print("Arduino:", response)
        except Exception as e:
            print(f"Error reading pin {pin}: {e}")
            return None

    def read_analog_pin(self, pin):
        """
        Read the status of the pin
        @param pin: (str) address of the analog pin to read - for example A0
        @return: pin_value (int) value of the selected pin
        """
        if not self.arduino.is_open:
            self.log.error("Serial connection for the Arduino is lost!")
            return None

        try:
            command = f"{pin}\n"
            self.arduino.write(command.encode())
            time.sleep(0.1)
            response = self.arduino.readline().decode().strip()
            print(response)

            if response.isdigit():  # Ensure response is valid
                return int(response)
            else:
                print(f"Invalid response from Arduino: {response}")
                return None
        except Exception as e:
            print(f"Error reading pin {pin}: {e}")
            return None

    def pin_on(self, pin):
        """
        Turn on a chosen pin
        @param pin: (int) address of the pin
        """
        self.write_to_digital_pin(pin, 1)

    def pin_off(self, pin):
        """
        Turn off a chosen pin
        @param pin: (int) address of the pin
        """
        self.write_to_digital_pin(pin, 0)

# ======================================================================================================================
# Specific methods for the FlyArena
# ======================================================================================================================
    def check_odor_valves(self):
        """ Check if an odor in active (meaning if the inlet & outlet valves associated to an odor are both open)
        @return: odor_active (bool) True if at least one odor is active - else return False
        """
        # check if an odor is already active (in & out valve open at the same time)
        odor_active = False
        for odor in self._odor_valves_pin.keys():
            read_valve = self.read_analog_pin(self._odor_valves_pin[odor][1])
            if read_valve > 500:
                odor_active = True
                break
        return odor_active

    def check_mixing_valve(self):
        """ Check if the mixing valve is open.
        @return: (bool) True if valve is open, else False
        """
        mixing_valve_state = self.read_analog_pin(self._mixing_valve_read)
        if mixing_valve_state > 500:
            return True
        else:
            return False

    def control_mixing_valve(self, state):
        """ Open/close the mixing valve
        @param: state (bool) indicate True to open the valve, False to close it
        @return: (bool) True if an error is encountered
        """
        # open / close the valve
        if state:
            self.pin_on(self._mixing_valve_write)
        else:
            self.pin_off(self._mixing_valve_write)

        # read the mixing valve pin and check the status corresponds to the input value
        read_state = self.check_mixing_valve()
        if read_state == state:
            return False
        else:
            self.log.warn("Mixing valve not responding properly!")
            return True
