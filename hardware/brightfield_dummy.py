# -*- coding: utf-8 -*-
"""
Qudi-CBS

This file contains a dummy implementation for a brightfield controller.

An extension to Qudi.

@author: F. Barho

Created on Tue March 9 2021
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
from core.module import Base
from interface.brightfield_interface import BrightfieldInterface


class BrightfieldDummy(Base, BrightfieldInterface):
    """ Class representing a brightfield controller dummy.

    Example config for copy-paste:

    brightfield_dummy:
        module.Class: 'brightfield_dummy.BrightfieldDummy'
    """

    current_intensity = 0

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

    def on_activate(self):
        """ Initialization.
        """
        pass

    def on_deactivate(self):
        """ Deactivation steps.
        """
        self.current_intensity = 0

# ----------------------------------------------------------------------------------------------------------------------
# Interface functions
# ----------------------------------------------------------------------------------------------------------------------

    def led_control(self, intensity):
        """ Set the intensity of the LED to the value intensity (in percent of max. intensity).
        :param: int intensity: percentage of maximum intensity to be applied to the LED
        :return: None
        """
        # truncate to allowed range
        value = int(min(max(intensity, 0), 99))
        self.current_intensity = value
