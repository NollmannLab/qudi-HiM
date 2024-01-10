# -*- coding: utf-8 -*-
"""
Qudi-CBS

A module to control the Celesta Lumencor laser source and the FPGA. This logic was specifically designed for the RAMM
setup and required to avoid changing the lasercontrol logic. The idea is to combine within the same logic all the
functionalities associated to the Lumencor (intensity control) and FPGA (synchronization with the camera).

An extension to Qudi.

@author: JB. Fiche

Created on Wed Jan 10 2024
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
from interface.lasercontrol_interface import LasercontrolInterface
from qtpy import QtCore
from core.configoption import ConfigOption
from time import sleep


# ======================================================================================================================
# Logic class
# ======================================================================================================================

class CelestaFPGALogic(GenericLogic, LasercontrolInterface):
    """ Controls the DAQ analog output and allows to set a digital output line for triggering
    or controls the FPGA output

    Example config for copy-paste:
        celestafpga_logic:
            module.Class: 'celestafpga_logic.CelestaFPGALogic'
            connect:
                celesta: 'celesta'
                fpga: 'nifpga'
    """

    # declare the hardware we need to connect to the logic
    celesta = Connector(interface='LasercontrolInterface')
    nifpga = Connector(interface='LasercontrolInterface')

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self._celesta = None
        self._fpga = None

    def on_activate(self):
        """ Initialisation performed during activation of the module.
        """
        self._celesta = self.celesta()
        self._fpga = self.nifpga()

    def on_deactivate(self):
        """ Perform required deactivation. """
        pass

    def get_dict(self):
        self._celesta.get_dict()

    def apply_voltage(self, voltage, channel):
        self._celesta.apply_voltage(voltage, channel)

