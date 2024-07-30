# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains a GUI for the odor circuit on the Fly Arena.

An extension to Qudi.

@author: D. Guerin, JB. Fiche

Created on Wen july 16, 2024
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
from core.module import Base


class MotorControl(Base):

    _port = ConfigOption('port', 'COM14')

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        try:
            self.ser = serial.Serial(self._port, 9600, timeout=5)
            time.sleep(2)
        except serial.SerialException as e:
            print(f"Error communicating with the motor: {e}")

    def on_activate(self):
        """
        Initialize the arduino uno device
        """
        pass

    def on_deactivate(self):
        """
        close properly the connection between the elegoo and the computer
        """
        self.ser.close()

    def command(self,command):
        """
        Send a command to the elegoo.
        typical command :
        send_command("forward")
        send_command("backward")
        """

        self.ser.flushInput()
        self.ser.write((command + '\n').encode())
        print(f"Command sent: {command}")

        response = self.ser.readline().decode().strip()
        if response:
            print(f"Response received: {response}")
        else:
            print("No response received")

    def send_command(self, command):
        try:
            self.command(command)
        except serial.SerialException as e:
            self.ser = serial.Serial(self._port, 9600, timeout=5)
            time.sleep(2)
            self.command(command)




