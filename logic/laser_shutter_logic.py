# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains the logic to control a shutter from Thorlabs. This logic was specifically written for the RAMM
setup modified with the Celesta laser source. The shutter is used to block the IR laser to reach the sample when an
acquisition is running.

An extension to Qudi.

@authors: JB. Fiche
Created on Tue January 16, 2024
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
from core.configoption import ConfigOption
from logic.generic_logic import GenericLogic
from time import sleep


# ======================================================================================================================
# Logic class
# ======================================================================================================================

class ShutterLogic(GenericLogic):
    """ Class to control the laser shutter.

    Config entry for copy-paste:

    shutter_logic:
        module.Class: 'laser_shutter_logic.ShutterLogic'
        laser_shutter: True
        connect:
            daq_logic: 'nidaq_logic'
            camera_logic: 'camera_logic'
    """
    # declare connectors
    daq_logic = Connector(interface='DAQLogic')

    # load parameters
    _shutter: bool = ConfigOption('laser_shutter', False)
    _acquisition_running: bool = False

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self._daq_logic = None
        self.shutter_initialized: bool = False

    def on_activate(self):
        """ Initialisation performed during activation of the module.
        """
        self._daq_logic = self.daq_logic()
        self.init_shutter()

    def on_deactivate(self):
        """ Perform required deactivation.
        Reset the piezo to the zero position. If a shutter for the laser is used, close the shutter.
        """
        self.close_shutter()

    def init_shutter(self):
        if self._shutter:
            self.shutter_initialized = self._daq_logic.initialize_shutter()

    def close_shutter(self):
        if self._shutter:
            self._daq_logic.write_laser_shutter(0)

    def open_shutter(self):
        if self._shutter and not self._acquisition_running:
            self._daq_logic.write_laser_shutter(1)
            abort = False
        elif self._shutter and self._acquisition_running:
            self.log.warning('An acquisition is running - the IR security shutter cannot be open.')
            abort = True
        else:
            abort = False

        return abort

    def camera_security(self, acquiring=False):
        if acquiring:
            self.close_shutter()
            sleep(0.5)
            self._acquisition_running = True
        else:
            self._acquisition_running = False


