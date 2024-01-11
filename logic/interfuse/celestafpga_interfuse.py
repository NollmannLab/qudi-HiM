# -*- coding: utf-8 -*-
"""
Qudi-CBS

A module to control the Celesta Lumencor laser source and the FPGA. This interfuse logic was specifically designed for
the RAMM setup. The idea is to combine within the same logic all the functionalities associated to the Lumencor
(intensity control) and FPGA (synchronization with the camera).

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
from core.module import Base
from interface.lasercontrol_interface import LasercontrolInterface
from qtpy import QtCore
from core.configoption import ConfigOption
from time import sleep


# ======================================================================================================================
# Logic class
# ======================================================================================================================

class CelestaFPGA(GenericLogic, LasercontrolInterface):
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
    fpga = Connector(interface='LasercontrolInterface')

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self._celesta = None
        self._fpga = None

    def on_activate(self):
        """ Initialisation performed during activation of the module.
        """
        self._celesta = self.celesta()
        self._fpga = self.fpga()

    def on_deactivate(self):
        """ Perform required deactivation. """
        pass

# ----------------------------------------------------------------------------------------------------------------------
# Methods associated to Celesta
# ----------------------------------------------------------------------------------------------------------------------

    def get_dict(self):
        return self._celesta.get_dict()

    def apply_voltage(self, voltage, channel):
        self._celesta.apply_voltage(voltage, channel)

    def wakeup(self):
        self._celesta.wakeup()

    def set_ttl(self, ttl_state):
        self._celesta.set_ttl(ttl_state)

# ----------------------------------------------------------------------------------------------------------------------
# Methods associated to FPGA
# ----------------------------------------------------------------------------------------------------------------------
    def close_default_session(self):
        self._fpga.close_default_session()

    def restart_default_session(self):
        self._fpga.restart_default_session()

    def start_task_session(self, bitfile):
        self._fpga.start_task_session(bitfile)

    def end_task_session(self):
        self._fpga.end_task_session()

    def run_test_task_session(self, data):
        self._fpga.run_test_task_session(data)

    def run_multicolor_imaging_task_session(self, z_planes, wavelength, values, num_laserlines, exposure):
        self._fpga.run_multicolor_imaging_task_session(z_planes, wavelength, values, num_laserlines, exposure)

    def run_celesta_multicolor_imaging_task_session(self, z_planes, wavelength, num_laserlines, exposure):
        self._fpga.run_celesta_multicolor_imaging_task_session(z_planes, wavelength, num_laserlines, exposure)