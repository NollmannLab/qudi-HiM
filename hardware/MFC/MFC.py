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


from sensirion_driver_adapters.shdlc_adapter.shdlc_channel import ShdlcChannel
from sensirion_shdlc_driver import ShdlcSerialPort
from sensirion_uart_sfx6xxx.device import Sfx6xxxDevice
from core.configoption import ConfigOption
from core.module import Base
from time import sleep


class MFC(Base):
    _MFC_port = ConfigOption('MFC_port', missing="error")
    MFC_number = ConfigOption('MFC_number', missing="error")
    MFC_names = ConfigOption('MFC_names', missing="error")
    MFC_address = ConfigOption('Daisy_chain_ids', missing="error")
    MFC_flow = ConfigOption('Default_flow', missing="error")

    # _MFC_purge = ConfigOption('MFC_purge', missing="warning", default=0)
    # _MFC_1 = ConfigOption('MFC_1', missing="warning", default=0)
    # _MFC_2 = ConfigOption('MFC_2', missing="warning", default=0)
    # _MFC_purge_flow = ConfigOption('MFC_purge_flow', 0.3)
    # _MFC_1_flow = ConfigOption('MFC_1_flow', 0.04)
    # _MFC_2_flow = ConfigOption('MFC_2_flow', 0.26)

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self._MFC_dic = {'MFC_names': self.MFC_names,
                         'MFC_id': self.MFC_address,
                         'MFC_flow': self.MFC_flow}

    def on_activate(self):
        """ Test all MFCs are connected and available
        """
        for n in range(self.MFC_number):
            with ShdlcSerialPort(port=self._MFC_port, baudrate=115200) as port:
                try:
                    sensor = Sfx6xxxDevice(ShdlcChannel(port, shdlc_address=self._MFC_dic['MFC_id'][n]))
                    sensor.device_reset()
                    self.log.info(f'Initialization for {self._MFC_dic["MFC_names"][n]} is a success')
                except:
                    self.log.warn(f'Initialization for {self._MFC_dic["MFC_names"][n]} not working')
            sleep(0.5)

    def on_deactivate(self):
        """ Reset all MFCs
        """
        for n in range(self.MFC_number):
            with ShdlcSerialPort(port=self._MFC_port, baudrate=115200) as port:
                sensor = Sfx6xxxDevice(ShdlcChannel(port, shdlc_address=self._MFC_dic['MFC_id'][n]))
                sensor.device_reset()
                self.log.warn(f'{self._MFC_dic["MFC_names"][n]} was switched off')

    def MFC_ON(self, mfc, flow):
        """open the MFC valve to calibrate the flow and read the measure value
        @param flow : sl/min - setpoint
        @param mfc : indicate the number of the MFC to turn on
        """
        with ShdlcSerialPort(port=self._MFC_port, baudrate=115200) as port:
            if mfc < self.MFC_number:
                sensor0 = Sfx6xxxDevice(ShdlcChannel(port, shdlc_address=self._MFC_dic['MFC_id'][mfc]))
                Z = sensor0.set_setpoint_and_read_measured_value(flow)
                sleep(0.3)
                print(Z)
            else:
                print(f'There is only {self.MFC_number} MFCs')

    def MFC_OFF(self, mfc):
        """Close the MFC valve
        @param mfc : indicate the number of the MFC to turn off
        """
        with ShdlcSerialPort(port=self._MFC_port, baudrate=115200) as port:
            if mfc < self.MFC_number:
                sensor = Sfx6xxxDevice(ShdlcChannel(port, shdlc_address=self._MFC_dic['MFC_id'][mfc]))
                sensor.close_valve()
            else:
                print(f'There is only {self.MFC_number} MFCs')

    def average_measure(self, mfc, n_measure):
        """Get the average measurement of the MFC valve
        @param mfc: (int) Indicate the number of the MFC to interrogate
        @param n_measure: (int) Number of measurement to average
        @return flow: (float) mean value of the flow measured
        """

        with ShdlcSerialPort(port=self._MFC_port, baudrate=115200) as port:
            if mfc < self.MFC_number:
                sensor = Sfx6xxxDevice(ShdlcChannel(port, shdlc_address=self._MFC_dic['MFC_id'][mfc]))
                flow = sensor.read_averaged_measured_value(n_measure)
            else:
                print(f'There is only {self.MFC_number} MFCs')
        return flow
