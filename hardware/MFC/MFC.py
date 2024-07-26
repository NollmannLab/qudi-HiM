# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains a Hardware for the odor circuit on the Fly Arena.

An extension to Qudi.

@author: D. Guerin, JB. Fiche

Created on Mon july 15, 2024
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
from sensirion_shdlc_driver import ShdlcSerialPort
from sensirion_shdlc_driver.errors import ShdlcDeviceError
from sensirion_driver_adapters.shdlc_adapter.shdlc_channel import ShdlcChannel
from sensirion_uart_sfx6xxx.device import Sfx6xxxDevice
from sensirion_uart_sfx6xxx.commands import StatusCode


class MFC(Base):

    _MFC_port = ConfigOption('MFC_port', 'COM4')
    _MFC_purge = ConfigOption('MFC_purge', 2)
    _MFC_1 = ConfigOption('MFC_1', 0)
    _MFC_2 = ConfigOption('MFC_2', 1)
    _MFC_purge_flow = ConfigOption('MFC_purge_flow', 0.3)
    _MFC_1_flow = ConfigOption('MFC_1_flow', 0.04)
    _MFC_2_flow = ConfigOption('MFC_2_flow', 0.26)


    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

    def on_activate(self):
        with ShdlcSerialPort(port=self._MFC_port, baudrate=115200) as port:
            sensor0 = Sfx6xxxDevice(ShdlcChannel(port, shdlc_address=self._MFC_1))
            sensor1 = Sfx6xxxDevice(ShdlcChannel(port, shdlc_address=self._MFC_2))
            sensor2 = Sfx6xxxDevice(ShdlcChannel(port, shdlc_address=self._MFC_purge))
            sensor0.device_reset()
            sensor1.device_reset()
            sensor2.device_reset()

    def on_deactivate(self):
        """Reset all MFCs"""
        with ShdlcSerialPort(port=self._MFC_port, baudrate=115200) as port:
            sensor0 = Sfx6xxxDevice(ShdlcChannel(port, shdlc_address=self._MFC_1))
            sensor1 = Sfx6xxxDevice(ShdlcChannel(port, shdlc_address=self._MFC_2))
            sensor2 = Sfx6xxxDevice(ShdlcChannel(port, shdlc_address=self._MFC_purge))
            sensor0.device_reset()
            sensor1.device_reset()
            sensor2.device_reset()

    def MFC_ON(self, mfc, flow):
        """open the MFC valve to calibrate the flow and read the measure value
        @param Flow : sl/min
        @param MFC : Number of the MFC
        """
        with ShdlcSerialPort(port=self._MFC_port, baudrate=115200) as port:

            if mfc == 0:
                sensor0 = Sfx6xxxDevice(ShdlcChannel(port, shdlc_address=self._MFC_1))
                Z = sensor0.set_setpoint_and_read_measured_value(flow)
                time.sleep(0.3)
                print(Z)
            elif mfc == 1:
                sensor1 = Sfx6xxxDevice(ShdlcChannel(port, shdlc_address=self._MFC_2))
                Z = sensor1.set_setpoint_and_read_measured_value(flow)
                time.sleep(0.3)
                print(Z)
            elif mfc == 2:
                sensor2 = Sfx6xxxDevice(ShdlcChannel(port, shdlc_address=self._MFC_purge))
                sensor2.set_setpoint_and_read_measured_value(flow)
            else:
                print('There is only 3 MFC')

    def MFC_OFF(self, mfc):
        """Close the MFC valve
        @param : MFC = Number of the MFC
        """
        with ShdlcSerialPort(port=self._MFC_port, baudrate=115200) as port:
            sensor0 = Sfx6xxxDevice(ShdlcChannel(port, shdlc_address=self._MFC_1))
            sensor1 = Sfx6xxxDevice(ShdlcChannel(port, shdlc_address=self._MFC_2))
            sensor2 = Sfx6xxxDevice(ShdlcChannel(port, shdlc_address=self._MFC_purge))
            if mfc == 0:
                sensor0.close_valve()

            elif mfc == 1:
                sensor1.close_valve()
            elif mfc == 2:
                sensor2.close_valve()
            else:
                print('There is only 3 MFC')

    def average_measure(self, mfc, NBmeasure):
        """Get the average measurement of the MFC valve
                @param MFC : Number of the MFC
                @param NBmeasure : Number of measurement to average
                """
        with ShdlcSerialPort(port=self._MFC_port, baudrate=115200) as port:
            sensor0 = Sfx6xxxDevice(ShdlcChannel(port, shdlc_address=self._MFC_1))
            sensor1 = Sfx6xxxDevice(ShdlcChannel(port, shdlc_address=self._MFC_2))
            sensor2 = Sfx6xxxDevice(ShdlcChannel(port, shdlc_address=self._MFC_purge))
            A=0
            if mfc == 0:
                A=sensor0.read_averaged_measured_value(NBmeasure)

            elif mfc == 1:
                A=sensor1.read_averaged_measured_value(NBmeasure)
            elif mfc == 2:
                A=sensor2.read_averaged_measured_value(NBmeasure)
            else:
                print('There is only 3 MFC')
        return A
