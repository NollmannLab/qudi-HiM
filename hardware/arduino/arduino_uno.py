"""
Qudi-CBS

This module contains the hardware class representing the Arduino uno.
It is used to control digital output that can be used as trigger for a connected device.

An extension to Qudi.

@author: D. Guerin, JB Fiche

Created on Tue may 18 2024.
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
import time
from core.configoption import ConfigOption


class ArduinoUno:
    _arduino_port = ConfigOption('arduino_port', None)

    def __init__(self):

        pass

    def on_activate(self, _arduino_port=None):
        try:
            arduino = serial.Serial(_arduino_port, 9600, timeout=1)
        except serial.SerialException as e:
            print(f"Erreur lors de l'ouverture du port série : {e}")
            exit()

    def on_deactivate(self):
        arduino.close()

    def send_command(self,pin, state):
        command = f'{pin}{state}\n'
        arduino.write(command.encode())
        response = arduino.readline().decode('utf-8').strip()
        print(response)

    def pin_on(self, pin):

        str(pin)
        self.send_command('1', pin)
        time.sleep(1)

    def pin_off(self, pin):

        str(pin)
        self.send_command('0', pin)
        time.sleep(1)
