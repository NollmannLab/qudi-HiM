# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains a GUI for the odor circuit on the Fly Arena.

An extension to Qudi.

@author: D. Guerin, JB. Fiche

Created on Fry july 18, 2024
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
from core.module import Base


class MotorControl(Base):

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        ser = serial.Serial(, 9600)
        time.sleep(2)

    def on_activate(self):
        pass
    def on_deactivate(self):
        self.ser.close()

    def send_command(self, command):
        self.ser.write((command + '\n').encode())
        print(f"Command sent: {command}")

    """Envoyer des commandes
        send_command("forward")
        time.sleep(2)

        send_command("backward")
        time.sleep(2)

        send_command("speed10")
        time.sleep(2)

        send_command("speed20")
        time.sleep(2)"""



