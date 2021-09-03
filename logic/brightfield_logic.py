# -*- coding: utf-8 -*-
"""
Qudi-CBS

A module for controlling a white light source.

An extension to Qudi.

@author: F. Barho
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
from qtpy import QtCore
from core.util.mutex import Mutex


class BrightfieldLogic(GenericLogic):
    """
    Class to control a white light source.

    Example config for copy-paste:

    brightfield_logic:
        module.Class: 'brightfield_logic.BrightfieldLogic'
        connect:
            controller: 'ms2000'
    """

    # declare connectors
    controller = Connector(interface='BrightfieldInterface')

    # signals
    sigBrightfieldStopped = QtCore.Signal()

    # attributes
    enabled = False

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

        # threading  # might be needed here
        # self._threadlock = Mutex()

    def on_activate(self):
        """ Initialisation performed during activation of the module. """
        self._controller = self.controller()
        # led off on start
        self.led_off()

    def on_deactivate(self):
        """ Required deactivation steps. """
        self.led_off()

    def led_control(self, intensity):
        """ Output an intensity to the lightsource controller.
        :param float intensity: intensity value
        """
        self.enabled = True
        self._controller.led_control(intensity)

    def led_off(self):
        """ Switch off the light source. """
        self.enabled = False
        self._controller.led_control(0)
        self.sigBrightfieldStopped.emit()
        # emit this signal if led_off is programmatically called to reset GUI toolbutton state

    def led_on_max(self):
        """ Output the maximum intensity to the lightsource controller. """
        self.enabled = True
        self.led_control(99)
        # value may need to be read from config is this should be used for another light source than the LED controlled by ASI stage

    def update_intensity(self, intensity):
        """ Output a new intensity setting to the lightsource controller in case the source is in on-state.
        :param float intensity: new intensity value
        """
        if self.enabled:
            self.led_control(intensity)