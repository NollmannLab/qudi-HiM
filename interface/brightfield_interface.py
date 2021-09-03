# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains the interface for the control of a white light source.

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
from core.interface import abstract_interface_method
from core.meta import InterfaceMetaclass


class BrightfieldInterface(metaclass=InterfaceMetaclass):
    """
    This module contains the interface for the control of a white light source.
    """

    @abstract_interface_method
    def led_control(self, intensity):
        """ Set the intensity of the LED to the value intensity (in percent of max. intensity).
        :param: int intensity: percentage of maximum intensity to be applied to the LED
        :return: None
        """
        pass
