# -*- coding: utf-8 -*-
"""
Qudi-CBS

A module to control The Fly Arena odor system from NI USB-6211 DAQ.

An extension to Qudi.

@author: D. Guerin, JB. Fiche

Created on Fry may 24, 2024
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


class OdorCircuitLogic(GenericLogic):
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
    daq = Connector(interface='Base')  # no specific DAQ interface required

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self._daq = None

    def on_activate(self):
        """ Initialisation performed during activation of the module.
        """
        self._daq = self.daq()

    def on_deactivate(self):
        """ Perform required deactivation. """
        pass

    def initialize_digital_channel(self, channel):
        """ Initialize the digitial port for the daq.
        :param: float channel
        :param: string type - define whether the selected port is used as an inout or output
        """
        self._daq.set_up_do_channel(channel)

    def final_valve(self, state):
        """
        @param state: (bool) ON / OFF state of the valve (1 : odor circuit on ; 0 : odor circuit off)
        """
        state = np.array([state], dtype=np.uint8)
        self._daq.write_to_do_channel(self._daq.valve_final_taskhandle, 1, state)

    def prepare_odor(self, odor_number):
        """
               @param odor_number: number of the odor you want to inject (not use yet)
        """

        state = np.array([1], dtype=np.uint8)
        close = np.array([0], dtype=np.uint8)
        if odor_number == 1:
            self._daq.write_to_do_channel(self._daq.valve_inlet_1_taskhandle, 1, state)
            self._daq.write_to_do_channel(self._daq.valve_outlet_1_taskhandle, 1, state)
            self._daq.write_to_do_channel(self._daq.mixing_valve_taskhandle, 1, close)
        elif odor_number == 2:
            pass
        elif odor_number == 3:
            pass
        elif odor_number == 4:
            pass
        else:
            pass

    def flush_odor(self):
        """
        information: final valve : { 1 : odor circuit on / 0 : odor circuit off }
        """
        state = np.array([0], dtype=np.uint8)
        self._daq.write_to_do_channel(self._daq.valve_inlet_1_taskhandle, 1, state)
        self._daq.write_to_do_channel(self._daq.valve_outlet_1_taskhandle, 1, state)
        self._daq.write_to_do_channel(self._daq.valve_final_taskhandle, 1, state)

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
