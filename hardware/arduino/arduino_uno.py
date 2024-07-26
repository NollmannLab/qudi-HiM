"""
Qudi-CBS

This module contains the hardware class representing the Arduino uno.
It is used to control digital output that can be used as trigger for a connected device.

An extension to Qudi.

@author: D. Guerin, JB. Fiche

Created on Tue may 28, 2024.
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
import logging

logging.basicConfig(filename='logfile.log', filemode='w', level=logging.DEBUG)
logger = logging.getLogger(__name__)


class ArduinoUno(Base):
    _arduino_port = ConfigOption('arduino_port', None)

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        try:
            self.arduino = serial.Serial(self._arduino_port, 9600, timeout=1)
        except Exception as err:
            logger.error('if could not open port : Verify that the arduino is connected on COM3, if access refused: close every arduino user software')
            self.arduino.close()

    def on_activate(self):
        """initialize the arduino uno device
        """
        pass

    def on_deactivate(self):
        pass

    def send_command(self, pin, state):
        """Send a command to the Arduino to be decrypted and processed.
        @param pin: The pin number on the Arduino to which the command is addressed.
        This should be an integer or string representing the pin.(2 to 13)
        @param state: (bool : on/off) The state to be set for the specified pin.
        This should be an integer or string representing the desired state.
        """
        # Create the command string
        command = f"{pin}{state}\n"
        # Send the command to the Arduino
        self.arduino.write(command.encode())
        # Wait for a response from the Arduino
        time.sleep(0.1)
        # Read and print all available responses from the Arduino
        while self.arduino.in_waiting:
            response = self.arduino.readline().decode().strip()
            print("Arduino:", response)


    def pin_on(self, pin):
        """turn on a choosen pin"""
        self.send_command(pin, 1)

    def pin_off(self, pin):
        """turn off a choosen pin"""
        self.send_command(pin, 0)
