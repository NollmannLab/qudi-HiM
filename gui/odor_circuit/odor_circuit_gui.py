# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains a GUI for the focus tools (manual focus using simple piezo positioning, and autofocus routines).

An extension to Qudi.

@author: D. Guerin, JB. Fiche
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
import sys
import os
from qtpy import QtWidgets, uic, QtCore
from qtpy.QtCore import Signal
from gui.guibase import GUIBase
from core.connector import Connector

# Define the path to the .ui file
this_dir = os.path.dirname(__file__)
ui_file = os.path.join(this_dir, 'odor_circuit_window.ui')


class ButtonWindow(QtWidgets.QDialog):
    """ Class defined for the main window with buttons.
    """

    def __init__(self):
        super().__init__()
        uic.loadUi(ui_file, self)
        self.show()


class OdorCircuitGUI(GUIBase):
    """ Main GUI class to handle interactions with buttons.
    """
    # define the default language option as English (to make sure all float have a point as a separator)
    QtCore.QLocale.setDefault(QtCore.QLocale("English"))

    # connector
    Odor_circuit_logic = Connector(interface='OdorCircuitLogic')

    # Declaration of custom signals
    sigButton1Clicked = Signal()
    sigButton2Clicked = Signal()
    sigButton3Clicked = Signal()
    sigButton4Clicked = Signal()
    sigButton5Clicked = Signal()
    sigButton6Clicked = Signal()

    # attributes
    _odor_circuit_logic = None


    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self._mw = None

    def on_activate(self):
        """ Initialize all UI elements and establish signal connections.
        """
        self._odor_circuit_logic = self.odor_circuit_logic()

        #Window
        self._mw = ButtonWindow()

        # Connecting signals of the buttons to the methods.
        self._mw.pushButton.clicked.connect(self.on_button1_clicked)
        self._mw.pushButton_2.clicked.connect(self.on_button2_clicked)
        self._mw.pushButton_3.clicked.connect(self.on_button3_clicked)
        self._mw.pushButton_4.clicked.connect(self.on_button4_clicked)
        self._mw.pushButton_5.clicked.connect(self.on_button5_clicked)
        self._mw.pushButton_6.clicked.connect(self.on_button6_clicked)

        # Connect custom signals to functions.
        self.sigButton1Clicked.connect(self._odor_circuit_logic.prepare_odor(1))
        self.sigButton2Clicked.connect(self._odor_circuit_logic.prepare_odor(2))
        self.sigButton3Clicked.connect(self._odor_circuit_logic.prepare_odor(3))
        self.sigButton4Clicked.connect(self._odor_circuit_logic.prepare_odor(4))
        self.sigButton5Clicked.connect(self._odor_circuit_logic.final_valve(1))
        self.sigButton6Clicked.connect(self._odor_circuit_logic.flush_odor())

    def on_button1_clicked(self):
        """ First odor
        """
        print("Odor 1 chosen")
        self.sigButton1Clicked.emit()

    def on_button2_clicked(self):
        """ Second odor
        """
        print("Odor 2 chosen")
        self.sigButton2Clicked.emit()

    def on_button3_clicked(self):
        """ Third Odor
        """
        print("Odor 3 chosen")
        self.sigButton3Clicked.emit()

    def on_button4_clicked(self):
        """ Fourth Odor
        """
        print("Odor 4 chosen")
        self.sigButton4Clicked.emit()
    def on_button5_clicked(self):
        """ Open the final valve to send odor
        """
        print("Sending odor")
        self.sigButton5Clicked.emit()
    def on_button6_clicked(self):
        """ Wipe the odor from th fly arena
        """
        print("Cleaning system in progress...")
        self.sigButton6Clicked.emit()

    def on_deactivate(self):
        """ Steps of deactivation required.
        """
        self._mw.pushButton.clicked.disconnect()
        self._mw.pushButton_2.clicked.disconnect()
        self._mw.pushButton_3.clicked.disconnect()
        self._mw.pushButton_4.clicked.disconnect()
        self._mw.pushButton_5.clicked.disconnect()
        self._mw.pushButton_6.clicked.disconnect()
        self._mw.close()

    def show(self):
        """ To make the window visible and bring it to the front of all other windows.
        """
        QtWidgets.QMainWindow.show(self._mw)
        self._mw.activateWindow()
        self._mw.raise_()