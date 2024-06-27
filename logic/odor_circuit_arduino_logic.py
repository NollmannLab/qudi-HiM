# -*- coding: utf-8 -*-
"""
Qudi-CBS

A module to control The Fly Arena odor system from Arduino uno.

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
from core.connector import Connector
from logic.generic_logic import GenericLogic
import numpy as np

from logic.tasks.oldies.analysis_FTL_hubble import time


# ======================================================================================================================
# Logic class
# ======================================================================================================================


class OdorCircuitLogicArduino(GenericLogic):
    """ Class containing the logic to control a DAQ.
    Its main reason is to make the DAQ hardware functions accessible from the logic level.
    Due to the specific usage, no common interface is required here.

    Example config for copy-paste:

    nidaq_logic:
        module.Class: 'daq_logic.DAQLogic'
        voltage_rinsing_pump: -3
        connect:
            daq: 'nidaq_6259'
    """
    # declare connectors
    arduino_uno = Connector(interface='Base')  # no specific arduino interface required

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self._ard = None

    def on_activate(self):
        """
        Initialisation performed during activation of the module.
        """
        self._ard = self.ard()

    def on_deactivate(self):
        """ Perform required deactivation. """
        pass

    def final_valve(self, state):
        """
        @param state: (bool) ON / OFF state of the valve (1 : odor circuit on ; 0 : odor circuit off)
        """
        state = np.array([state], dtype=np.uint8)
        self._ard.pin_on('3')

    def prepare_odor(self, odor_number):
        """
        @param odor_number: number of the odor you want to inject (not use yet)
        """

        if odor_number == 1:
            odor_number=str(odor_number)
            self._ard.pin_on(odor_number, '1')
            self._ard.pin_on(odor_number+1, '1')
            self._ard.pin_on(4)
        elif odor_number == 2:
            odor_number=str(odor_number)

            pass
        elif odor_number == 3:
            odor_number=str(odor_number)

            pass
        elif odor_number == 4:
            odor_number=str(odor_number)

            pass
        else:
            pass

    def flush_odor(self):
        """
        information: final valve : { 1 : odor circuit on / 0 : odor circuit off }
        """

        self._ard.pin_on('1', '0')
        self._ard.pin_on('1', '0')
        self._ard.pin_on('1', '0')

    def Do_an_experiment(self,odor_number,waiting_time,duration):
        """
        @param odor_number: number of the odor you want to inject (not use yet)
        @param waiting_time: time in second to wait for odor to be charged
        @param duration: time in second that the experiment will take
        """

        self.prepare_odor(odor_number)
        time.sleep(waiting_time)
        self.final_valve(1)
        time.sleep(duration)
        self.flush_odor()
