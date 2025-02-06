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

import serial
from core.configoption import ConfigOption
from core.module import Base
from time import time, sleep


class ArduinoUno(Base):

    n_odor_available = ConfigOption('n_odor_available', missing='error')
    _arduino_port = ConfigOption('arduino_port', missing='error')
    _valve_odor_1_write = ConfigOption('valve_odor_1_write', missing='error')
    _valve_odor_2_write = ConfigOption('valve_odor_2_write', missing='error')
    _valve_odor_3_write = ConfigOption('valve_odor_3_write', missing='error')
    _valve_odor_4_write = ConfigOption('valve_odor_4_write', missing='error')
    _valve_odor_1_read = ConfigOption('valve_odor_1_read', missing='error')
    _valve_odor_2_read = ConfigOption('valve_odor_2_read', missing='error')
    _valve_odor_3_read = ConfigOption('valve_odor_3_read', missing='error')
    _valve_odor_4_read = ConfigOption('valve_odor_4_read', missing='error')
    _mixing_valve_write = ConfigOption('mixing_valve_write', missing='error')
    _mixing_valve_read = ConfigOption('mixing_valve_read', missing='error')
    _switch_valve_write = ConfigOption('switch_purge_arena_valve_write', missing='error')
    _switch_valve_read = ConfigOption('switch_purge_arena_valve_read', missing='error')
    _3_way_valve_write = ConfigOption('3_way_valve_write', missing='error')
    _3_way_valve_read = ConfigOption('3_way_valve_read', missing='error')
    _switch_quadrant_valve_write = ConfigOption('switch_quadrant_valve_write', missing='error')
    _switch_quadrant_valve_read = ConfigOption('switch_quadrant_valve_read', missing='error')
    _shutter_write = ConfigOption('shutter_write', missing='error')
    _shutter_read = ConfigOption('shutter_read', missing='error')

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self.arduino = None
        self.valve_pin = {"odor_1": [self._valve_odor_1_write, self._valve_odor_1_read],
                          "odor_2": [self._valve_odor_2_write, self._valve_odor_2_read],
                          "odor_3": [self._valve_odor_3_write, self._valve_odor_3_read],
                          "odor_4": [self._valve_odor_4_write, self._valve_odor_4_read],
                          "mixing": [self._mixing_valve_write, self._mixing_valve_read],
                          "switch_purge_arena": [self._switch_valve_write, self._switch_valve_read],
                          "3_way": [self._3_way_valve_write, self._3_way_valve_read],
                          "switch_quadrants": [self._switch_quadrant_valve_write, self._switch_quadrant_valve_read]}

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
            sleep(0.1)

            # Read and print all available responses from the Arduino
            response = self.arduino.readline().decode().strip()
            print("Arduino:", response)
        except Exception as e:
            print(f"Error reading pin {pin}: {e}")
            return None

    def read_digital_analog_pin(self, pin):
        """
        Read the status of the pin
        @param pin: (str) address of the analog pin to read - for example A0
        @return: response (int) value of the selected pin
        """
        if not self.arduino.is_open:
            self.log.error("Serial connection for the Arduino is lost!")
            return None

        try:
            command = f"{pin}\n"
            self.arduino.write(command.encode())
            sleep(0.1)
            response = self.arduino.readline().decode().strip()
            if response.isdigit():  # Ensure response is valid
                return response
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
    def check_valve_state(self, code):
        """ Check if the selected valve is OPEN (return TRUE) or CLOSE (return FALSE)
        @param: code (str) indicate the name of the selected valve in the dictionary
        @return: (bool) True if the valves for the selected odor are open - else False
        """
        if code in self.valve_pin.keys():
            read_valve = self.read_digital_analog_pin(self.valve_pin[code][1])

            if self.valve_pin[code][1][0] == "A":
                if int(read_valve) > 500:
                    return True
                else:
                    return False

            elif self.valve_pin[code][1][0] == "D":
                if int(read_valve) == 1:
                    return True
                else:
                    return False
            else:
                self.log.error(f"The format of the pin {self.valve_pin[code][1][0]} is not conform!")

        else:
            self.log.error(f"The code {code} indicated does not correspond to any valve")
            return False

    def change_valve_state(self, code, state):
        """ Open/close the selected valve
        @param code: (str) indicate the name of the selected valve in the dictionary
        @param state: (bool) indicate True to open the valve, False to close it
        @return: (bool) True if an error is encountered
        """
        print(f"{code} and {state}")
        if code in self.valve_pin.keys():
            # open / close the valve
            if state:
                self.pin_on(self.valve_pin[code][0])
            else:
                self.pin_off(self.valve_pin[code][0])

            # read the mixing valve pin and check the status corresponds to the input value
            read_state = self.check_valve_state(code)
            if read_state == state:
                return False
            else:
                self.log.warn(f"The valve {code} is not responding properly!")
                return True
        else:
            self.log.error(f"The code {code} indicated does not correspond to any valve")
            return True

    def shutter(self):
        """ Open/close the shutter
        """
        self.pin_on(self._shutter_write)
        sleep(0.5)
        self.pin_off(self._shutter_write)