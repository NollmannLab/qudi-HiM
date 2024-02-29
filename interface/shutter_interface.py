# -*- coding: utf-8 -*-
"""
Qudi-CBS

This file contains the Qudi Interface for a shutter (created for the RAMM microscope).

This module was available in Qudi original version and was modified.

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


class ShutterInterface(metaclass=InterfaceMetaclass):
    """ This interface is used to control a laser shutter.
    """
    # set the internal attributes _full_width, _full_height,
    # and, if has_temp returns true: _default_temperature
    # if has_shutter returns true: _shutter

# ----------------------------------------------------------------------------------------------------------------------
# Getter and setter methods
# ----------------------------------------------------------------------------------------------------------------------

    @abstract_interface_method
    def camera_security(self):
        """ Retrieve an identifier of the camera that the GUI can print.

        :return: string name: name for the camera
        """
        pass

