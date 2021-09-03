# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains the logic to control a modular valve positioner (MVP)

An extension to Qudi.

@author: F. Barho

Created on Thu Mars 4 2021
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
from qtpy import QtCore
from logic.generic_logic import GenericLogic
from core.connector import Connector


class ValveLogic(GenericLogic):
    """
    Class containing the logic to control the valve positioner.

    Example config for copy-paste:

    valve_logic:
        module.Class: 'valve_logic.ValveLogic'
        connect:
            valves: 'valve_dummy'
    """
    # declare connectors
    valves = Connector(interface='ValvePositionerInterface')

    # signals
    sigPositionChanged = QtCore.Signal(str, int)
    sigDisableValvePositioning = QtCore.Signal()
    sigEnableValvePositioning = QtCore.Signal()

    # attributes
    valve_dict = {}
    valve_names = []
    max_positions = []
    valve_IDs = []
    valve_positions = []  # a list of lists containing customised entries for the GUI Comboboxes, optionally given in hardware's config

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self._valves = None

    def on_activate(self):
        """ Initialisation performed during activation of the module.
        """
        # connector
        self._valves = self.valves()

        # initialization of attributes according to hardware configuration
        self.valve_dict = self._valves.get_valve_dict()
        self.valve_names = [self.valve_dict[key]['name'] for key in self.valve_dict]
        self.max_positions = [self.valve_dict[key]['number_outputs'] for key in self.valve_dict]
        self.valve_IDs = [self.valve_dict[key]['daisychain_ID'] for key in self.valve_dict]
        self.valve_positions = self._valves.valve_positions

    def on_deactivate(self):
        """ Perform required deactivation. """
        pass

# ----------------------------------------------------------------------------------------------------------------------
# Getter and setter methods
# ----------------------------------------------------------------------------------------------------------------------

    def get_valve_position(self, valve_id):
        """ Read the valve position of the specified valve.
        :param str valve_id: identifier of the valve, such as 'a', 'b', ..
        :return int position
        """
        return self._valves.get_valve_position(valve_id)

    def set_valve_position(self, valve_id, position):
        """ Set the position of the specified valve.
        :param str valve_id: identifier of the valve, such as 'a', 'b', ..
        :param int position: target position for the valve
        :return None
        """
        self._valves.set_valve_position(valve_id, position)
        self.sigPositionChanged.emit(valve_id, position)  # signal to update gui when position changed by direct call to this function

    def get_valve_dict(self):
        """ Get the dictionary specified in the hardware modules config entry, containing daisy chain id, valve name
        and number of outputs.
        :return dict valve_dict
        """
        return self._valves.get_valve_dict()

# ----------------------------------------------------------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------------------------------------------------------

    def wait_for_idle(self):
        """ Wait for valves to be set to position.
        :return None
        """
        self._valves.wait_for_idle()

# ----------------------------------------------------------------------------------------------------------------------
# Methods to handle the user interface state
# ----------------------------------------------------------------------------------------------------------------------

    def disable_valve_positioning(self):
        """ This method provides a security to avoid modifying the valve position from GUI, for example during Tasks. """
        self.sigDisableValvePositioning.emit()

    def enable_valve_positioning(self):
        """ This method resets the valve positioning comboboxes on GUI to callable state, for example after Tasks. """
        self.sigEnableValvePositioning.emit()
