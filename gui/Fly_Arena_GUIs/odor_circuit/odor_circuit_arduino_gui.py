# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains a GUI for the odor circuit on the Fly Arena.

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

import os
from typing import Dict

import numpy as np
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget
from qtpy import QtWidgets, uic, QtCore
from qtpy.QtCore import Signal
import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt
from core.configoption import ConfigOption
from gui.guibase import GUIBase
from core.connector import Connector
import logging

logging.basicConfig(filename='logfile.log', filemode='w', level=logging.DEBUG)
logger = logging.getLogger(__name__)


class MainWindow(QtWidgets.QMainWindow):
    """ Class defined for the main window for odor control.
    """

    def __init__(self, close_function):
        super().__init__()
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'odor_circuit_window.ui')
        uic.loadUi(ui_file, self)
        self.close_function = close_function
        self.show()

    def closeEvent(self, event):
        self.close_function()
        event.accept()


class OdorCircuitGUI(GUIBase):
    """ Main GUI class to handle interactions with MFCs and Valves.
    """
    # connector
    odor_circuit_arduino_logic = Connector(interface='OdorCircuitArduinoLogic')

    _valve_odor_1_in = ConfigOption('valve_odor_1_in', 3)
    _valve_odor_2_in = ConfigOption('valve_odor_2_in', 12)
    _valve_odor_3_in = ConfigOption('valve_odor_3_in', 11)
    _valve_odor_4_in = ConfigOption('valve_odor_4_in', 10)
    _valve_odor_1_out = ConfigOption('valve_odor_1_in', 7)
    _valve_odor_2_out = ConfigOption('valve_odor_2_in', 6)
    _valve_odor_3_out = ConfigOption('valve_odor_3_in', 5)
    _valve_odor_4_out = ConfigOption('valve_odor_4_in', 4)
    _mixing_valve = ConfigOption('mixing_valve', 9)
    _final_valve = ConfigOption('final_valve', 8)
    _path_MFC1 = ConfigOption('path_MFC1', None)
    _path_MFC2 = ConfigOption('path_MFC2', None)
    _path_MFCPurge = ConfigOption('path_MFCPurge', None)
    valve_odor_1_in = 0
    valve_odor_2_in = 0
    valve_odor_3_in = 0
    valve_odor_4_in = 0
    valve_odor_1_out = 0
    valve_odor_2_out = 0
    valve_odor_3_out = 0
    valve_odor_4_out = 0
    mixing_valve = 0
    final_valve = 0
    MFC_status = False

    sigStartFlowMeasure = QtCore.Signal()
    sigStopFlowMeasure = QtCore.Signal()
    # define the default language option as English (to make sure all float have a point as a separator)
    QtCore.QLocale.setDefault(QtCore.QLocale("English"))

    # Declaration of custom signals
    sigButton1Clicked = Signal()
    sigButton2Clicked = Signal()
    sigButton3Clicked = Signal()
    sigButton4Clicked = Signal()
    sigButton5Clicked = Signal()
    sigButton6Clicked = Signal()
    sigButton7Clicked = Signal()
    sigMFC_ON = Signal()
    sigMFC_OFF = Signal()
    sigActivateClicked = Signal()
    pixmap1 = QPixmap('C:/Users/sCMOS-1/qudi-cbs/gui/Fly_Arena_GUIs/odor_circuit/image/Schema fluidic odors off.PNG')
    pixmap2 = QPixmap('C:/Users/sCMOS-1/qudi-cbs/gui/Fly_Arena_GUIs/odor_circuit/image/Schema fluidic odors on.PNG')

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self._odor_circuit_arduino_logic = None
        self._mw = None
        self._dw = None
        self.valves_status = {
            'valve_odor_1_in': '0',
            'valve_odor_2_in': '0',
            'valve_odor_3_in': '0',
            'valve_odor_4_in': '0',
            'final_valve': '0',
            'mixing_valve': '0',
            'valve_odor_1_out': '0',
            'valve_odor_2_out': '0',
            'valve_odor_3_out': '0',
            'valve_odor_4_out': '0'
        }
        self.valves_in_out = {
            'odor_1': ['valve_odor_1_in', 'valve_odor_1_out'],
            'odor_2': ['valve_odor_2_in', 'valve_odor_2_out'],
            'odor_3': ['valve_odor_3_in', 'valve_odor_3_out'],
            'odor_4': ['valve_odor_4_in', 'valve_odor_4_out']
        }
        self._mw = MainWindow(close_function=self.close_function)  # Assuming MainWindow handles main UI
        self._dw = QtWidgets.QDockWidget()  # Initialize QDockWidget

        if isinstance(self._mw, MainWindow):
            self._mw.label_5.setPixmap(self.pixmap1)  # Set pixmap for label_5 in MainWindow
        else:
            print("Error: _mw is not an instance of MainWindow")

        if isinstance(self._dw, QtWidgets.QDockWidget):
            self.label_5 = QLabel()
            self._dw.setWidget(self.label_5)  # Set label_5 within _dw
            self.label_5.setPixmap(self.pixmap1)  # Set initial pixmap for label_5 in _dw
        else:
            print("Error: _dw is not initialized correctly or is None")

        self.pixmap1 = QPixmap('C:/Users/sCMOS-1/qudi-cbs/gui/Fly_Arena_GUIs/odor_circuit/image/Schema fluidic odors on.PNG')
        self.pixmap2 = QPixmap('C:/Users/sCMOS-1/qudi-cbs/gui/Fly_Arena_GUIs/odor_circuit/image/Schema fluidic odors off.PNG')

        self._mw.label_5.setPixmap(self.pixmap1)  # Set pixmap for label_5 in MainWindow
        self.label_5 = QLabel()
        self._dw.setWidget(self.label_5)  # Set label_5 within _dw
        self.label_5.setPixmap(self.pixmap2)  # Set initial pixmap for label_5 in _dw

    def on_activate(self):
        """ Initialize all UI elements and establish signal connections.
        """
        self._odor_circuit_arduino_logic = self.odor_circuit_arduino_logic()

        # Window
        self._mw = MainWindow(self.close_function)
        self._mw.centralwidget.hide()  # everything is in dockwidgets

        self.init_flowcontrol()
        self._mw.label_5.setPixmap(self.pixmap2)
        # Connecting signals of the buttons to the methods.
        self._mw.toolButton_1.clicked.connect(self.on_button1_clicked)
        self._mw.toolButton_2.clicked.connect(self.on_button2_clicked)
        self._mw.toolButton_3.clicked.connect(self.on_button3_clicked)
        self._mw.toolButton_4.clicked.connect(self.on_button4_clicked)
        self._mw.toolButton_5.clicked.connect(self.on_button5_clicked)
        self._mw.toolButton_6.clicked.connect(self.on_button6_clicked)
        self._mw.toolButton_7.clicked.connect(self.on_button7_clicked)
        self._mw.Activate.clicked.connect(self.ActivateClicked)
        self._mw.checkBox.stateChanged.connect(self.check_box_changed)
        self._mw.checkBox_2.stateChanged.connect(self.check_box_changed)
        self._mw.checkBox_M.stateChanged.connect(self.check_box_changed)
        self._mw.checkBox_F.stateChanged.connect(self.check_box_changed)
        self._mw.checkBox_3.stateChanged.connect(self.check_box_changed)
        self._mw.checkBox_4.stateChanged.connect(self.check_box_changed)
        self._mw.checkBox_5.stateChanged.connect(self.check_box_changed)
        self._mw.checkBox_6.stateChanged.connect(self.check_box_changed)
        self._mw.checkBox_7.stateChanged.connect(self.check_box_changed)
        self._mw.checkBox_8.stateChanged.connect(self.check_box_changed)
        self.disable_odor_buttons()
        # Connect custom signals to functions.
        self.sigButton1Clicked.connect(lambda: self._odor_circuit_arduino_logic.prepare_odor(1))
        self.sigButton2Clicked.connect(lambda: self._odor_circuit_arduino_logic.prepare_odor(2))
        self.sigButton3Clicked.connect(lambda: self._odor_circuit_arduino_logic.prepare_odor(3))
        self.sigButton4Clicked.connect(lambda: self._odor_circuit_arduino_logic.prepare_odor(4))
        self.sigButton5Clicked.connect(lambda: self._odor_circuit_arduino_logic.valve(self._final_valve, 1))
        self.sigButton6Clicked.connect(lambda: self._odor_circuit_arduino_logic.flush_odor())
        self.sigButton7Clicked.connect(lambda: self.on_deactivate())
        self.sigActivateClicked.connect(lambda: self.ActivateClicked)

    def on_deactivate(self):
        """ Steps of deactivation required.
        """

        self._odor_circuit_arduino_logic.flush_odor()
        self._mw.toolButton_1.clicked.disconnect()
        self._mw.toolButton_2.clicked.disconnect()
        self._mw.toolButton_3.clicked.disconnect()
        self._mw.toolButton_4.clicked.disconnect()
        self._mw.toolButton_5.clicked.disconnect()
        self._mw.toolButton_6.clicked.disconnect()
        self._mw.toolButton_7.clicked.disconnect()
        self._mw.Activate.clicked.disconnect()
        self._mw.close()

    def show(self):
        """ To make the window visible and bring it to the front.
        """
        QtWidgets.QMainWindow.show(self._mw)
        self._mw.activateWindow()
        self._mw.raise_()

    def init_flowcontrol(self):
        """ This method initializes the flowcontrol dockwidget.
        It initializes the line plot and sets an adapted text on the labels on the flowcontrol dockwidget.
        It establishes the signal-slot connections for the toolbar actions.
        """
        # initialize the line plot
        # data for flowrate plot initialization
        self.t_data = []
        self.flowrate1_data = []
        self.flowrate2_data = []
        self.flowrate3_data = []
        # create a reference to the line object (this is returned when calling plot method of pg.PlotWidget)
        self._mw.flowrate_PlotWidget_1.setLabel('left', 'Flowrate', units='L/min')
        self._mw.flowrate_PlotWidget_1.setLabel('bottom', 'Time', units='s')
        self._mw.actionMFC_ON_OFF.setText('MFC : OFF')

        self._mw.flowrate_PlotWidget_1.addLegend()

        # Initial plot setup
        self._flowrate1_timetrace = self._mw.flowrate_PlotWidget_1.plot(self.t_data, self.flowrate1_data,
                                                                        pen=(255, 0, 0), name='MFC1')
        self._flowrate2_timetrace = self._mw.flowrate_PlotWidget_1.plot(self.t_data, self.flowrate2_data,
                                                                        pen=(0, 255, 0), name='MFC2')
        self._flowrate3_timetrace = self._mw.flowrate_PlotWidget_1.plot(self.t_data, self.flowrate3_data,
                                                                        pen=(0, 0, 255), name='MFC_purge')

        # toolbar actions: internal signals
        self._mw.start_flow_measurement_Action.triggered.connect(self.measure_flow_clicked)
        self._mw.actionMFC_ON_OFF.triggered.connect(self.mfc_on_off)
        # signals to logic
        self.sigStartFlowMeasure.connect(self._odor_circuit_arduino_logic.start_flow_measurement)
        self.sigStopFlowMeasure.connect(self._odor_circuit_arduino_logic.stop_flow_measurement)

        # signals from logic
        self._odor_circuit_arduino_logic.sigUpdateFlowMeasurement.connect(self.update_flowrate)
        self._odor_circuit_arduino_logic.sigDisableFlowActions.connect(self.disable_flowcontrol_buttons)
        self._odor_circuit_arduino_logic.sigEnableFlowActions.connect(self.enable_flowcontrol_buttons)
        self.sigMFC_ON.connect(self.mfc_on)
        self.sigMFC_OFF.connect(self._odor_circuit_arduino_logic.close_air)

    def check_valves(self, valves_status):
        '''Check valves status to permit the MFC2 to turn on'''

        count_on_associations = 0
        active_associations = []

        # Check associations where both in and out valves are '1'
        for odor, (in_valve, out_valve) in self.valves_in_out.items():
            if valves_status[in_valve] == '1' and valves_status[out_valve] == '1':
                count_on_associations += 1
                active_associations.append(odor)
            elif valves_status[in_valve] == '1' and valves_status[out_valve] == '0':
                logger.error(f"You need to open {out_valve}")
                return 0
            elif valves_status[out_valve] == '1' and valves_status[in_valve] == '0':
                logger.error(f"You need to open {in_valve}")
                return 0

        # Determine action based on mixing valve status and count of active associations
        if count_on_associations > 1:
            logger.error('You need to close all but one pair of valves')
            return 0
        elif count_on_associations == 1 and valves_status['mixing_valve'] == '1':
            logger.error(f'MFC2 cannot operate because {active_associations[0]} and the mixing valve are both on.')
            return 0
        elif count_on_associations == 1 and valves_status['mixing_valve'] == '0':
            logger.info(f'MFC2 operates for {active_associations[0]}')
            return 1
        elif count_on_associations == 0 and valves_status['mixing_valve'] == '1':
            logger.info('MFC2 operates with mixing valve.')
            return 1
        elif count_on_associations == 0 and valves_status['mixing_valve'] == '0':
            logger.error('You need to open the Mixing Valve first')
            return 0

    def ActivateClicked(self):

        self.sigActivateClicked.emit()
        self._mw.checkBox_M.setChecked(True)
        self._mw.checkBox.setDisabled(True)
        self._mw.checkBox_2.setDisabled(True)
        self._mw.checkBox_3.setDisabled(True)
        self._mw.checkBox_4.setDisabled(True)
        self._mw.checkBox_5.setDisabled(True)
        self._mw.checkBox_6.setDisabled(True)
        self._mw.checkBox_7.setDisabled(True)
        self._mw.checkBox_8.setDisabled(True)
        self._mw.checkBox_M.setDisabled(True)
        self._mw.checkBox_F.setDisabled(True)
        self.enable_odor_buttons()

    def on_button1_clicked(self):
        """ Open valves for odor 1 in and out
        """
        logger.info("Odor 1 chosen")
        self.sigButton1Clicked.emit()
        self.disable_odor_buttons()
        self.valves_status['valve_odor_1_in'] = '1'
        self.valves_status['valve_odor_1_out'] = '1'
        self.valves_status['mixing_valve'] = '0'
        self.update_valve_label(self._mw.label_1in, 1)
        self.update_valve_label(self._mw.label_1out, 1)
        self._mw.checkBox_M.setChecked(False)

    def on_button2_clicked(self):
        """ Open valves for odor 2 in and out
        """
        logger.info("Odor 2 chosen")
        self.sigButton2Clicked.emit()
        self.disable_odor_buttons()
        self.valves_status['valve_odor_2_in'] = '1'
        self.valves_status['valve_odor_2_out'] = '1'
        self.valves_status['mixing_valve'] = '0'
        self.update_valve_label(self._mw.label_2in, 1)
        self.update_valve_label(self._mw.label_2out, 1)
        self._mw.checkBox_M.setChecked(False)

    def on_button3_clicked(self):
        """ Open valves for odor 3 in and out
        """
        logger.info("Odor 3 chosen")
        self.sigButton3Clicked.emit()
        self.disable_odor_buttons()
        self.valves_status['valve_odor_3_in'] = '1'
        self.valves_status['valve_odor_3_out'] = '1'
        self.valves_status['mixing_valve'] = '0'
        self.update_valve_label(self._mw.label_3in, 1)
        self.update_valve_label(self._mw.label_3out, 1)
        self._mw.checkBox_M.setChecked(False)

    def on_button4_clicked(self):
        """ Open valves for odor 4 in and out
        """
        logger.info("Odor 4 chosen")
        self.sigButton4Clicked.emit()
        self.disable_odor_buttons()
        self.valves_status['valve_odor_4_in'] = '1'
        self.valves_status['valve_odor_4_out'] = '1'
        self.valves_status['mixing_valve'] = '0'
        self.update_valve_label(self._mw.label_4in, 1)
        self.update_valve_label(self._mw.label_4out, 1)
        self._mw.checkBox_M.setChecked(False)
    def on_button5_clicked(self):
        """ Open the final valve to send odor
        """
        logger.info("Sending odor...")
        self.sigButton5Clicked.emit()
        self._mw.toolButton_5.setDisabled(True)
        self.valves_status['final_valve'] = '1'
        self.update_final_valve_label(1)


    def on_button6_clicked(self):
        """ Wipe the odor from the fly arena
        """
        logger.info("Cleaning system in progress...")
        self.sigButton6Clicked.emit()
        self.enable_odor_buttons()
        self._mw.toolButton_5.setDisabled(False)
        self._odor_circuit_arduino_logic.flush_odor()
        self.valves_status['valve_odor_1_in'] = '0'
        self.valves_status['valve_odor_1_out'] = '0'
        self.valves_status['valve_odor_2_in'] = '0'
        self.valves_status['valve_odor_2_out'] = '0'
        self.valves_status['valve_odor_3_in'] = '0'
        self.valves_status['valve_odor_3_out'] = '0'
        self.valves_status['valve_odor_4_in'] = '0'
        self.valves_status['valve_odor_4_out'] = '0'
        self.valves_status['mixing_valve'] = '0'
        self.update_valve_label(self._mw.label_1in, 0)
        self.update_valve_label(self._mw.label_1out, 0)
        self.update_valve_label(self._mw.label_2in, 0)
        self.update_valve_label(self._mw.label_2out, 0)
        self.update_valve_label(self._mw.label_3in, 0)
        self.update_valve_label(self._mw.label_3out, 0)
        self.update_valve_label(self._mw.label_4in, 0)
        self.update_valve_label(self._mw.label_4out, 0)
        self.update_final_valve_label(0)
        self._mw.checkBox.setDisabled(False)
        self._mw.checkBox_2.setDisabled(False)
        self._mw.checkBox_3.setDisabled(False)
        self._mw.checkBox_4.setDisabled(False)
        self._mw.checkBox_5.setDisabled(False)
        self._mw.checkBox_6.setDisabled(False)
        self._mw.checkBox_7.setDisabled(False)
        self._mw.checkBox_8.setDisabled(False)
        self._mw.checkBox_M.setDisabled(False)
        self._mw.checkBox_F.setDisabled(False)
        self._mw.checkBox_M.setChecked(False)

    def on_button7_clicked(self):
        """ Shutdown properly the system
        """
        self.sigButton7Clicked.emit()
        self._odor_circuit_arduino_logic.flush_odor()
        self.valves_status['valve_odor_1_in'] = '0'
        self.valves_status['valve_odor_1_out'] = '0'
        self.valves_status['valve_odor_2_in'] = '0'
        self.valves_status['valve_odor_2_out'] = '0'
        self.valves_status['valve_odor_3_in'] = '0'
        self.valves_status['valve_odor_3_out'] = '0'
        self.valves_status['valve_odor_4_in'] = '0'
        self.valves_status['valve_odor_4_out'] = '0'
        self.valves_status['mixing_valve'] = '0'
        self.valves_status['final_valve'] = '0'
        self.update_valve_label(self._mw.label_1in, 0)
        self.update_valve_label(self._mw.label_1out, 0)
        self.update_valve_label(self._mw.label_2in, 0)
        self.update_valve_label(self._mw.label_2out, 0)
        self.update_valve_label(self._mw.label_3in, 0)
        self.update_valve_label(self._mw.label_3out, 0)
        self.update_valve_label(self._mw.label_4in, 0)
        self.update_valve_label(self._mw.label_4out, 0)
        self.update_valve_label(self._mw.label_M, 1)
        self.update_final_valve_label(0)
        self._mw.checkBox.setDisabled(False)
        self._mw.checkBox_2.setDisabled(False)
        self._mw.checkBox_3.setDisabled(False)
        self._mw.checkBox_4.setDisabled(False)
        self._mw.checkBox_5.setDisabled(False)
        self._mw.checkBox_6.setDisabled(False)
        self._mw.checkBox_7.setDisabled(False)
        self._mw.checkBox_8.setDisabled(False)
        self._mw.checkBox_M.setDisabled(False)
        self._mw.checkBox_F.setDisabled(False)

    def update_valve_label(self, label, state):
        """ Update the valve label to show 'opened' or 'closed'. """
        if state == 1:
            label.setText("Open")
        else:
            label.setText("Close")

    def update_final_valve_label(self, state):
        """ Update the final valve label to change background image. """
        if state == 1:
            self._mw.label_5.setPixmap(self.pixmap1)
        else:
            self._mw.label_5.setPixmap(self.pixmap2)

    def check_box_changed(self, state):
        '''Check the state of the valves box and turn on or off the devise
        if check, turn on; if unchecked, turn off.'''
        sender = self.sender()  # Get the QCheckBox that emitted the signal

        if sender == self._mw.checkBox:
            if state == 2:  # Qt.Checked
                self._odor_circuit_arduino_logic.valve(self._valve_odor_1_in, 1)
                self.valves_status['valve_odor_1_in'] = '1'
                self.update_valve_label(self._mw.label_1in, 1)
            else:
                self._odor_circuit_arduino_logic.valve(self._valve_odor_1_in, 0)
                self.valves_status['valve_odor_1_in'] = '0'
                self.update_valve_label(self._mw.label_1in, 0)
        elif sender == self._mw.checkBox_2:
            if state == 2:  # Qt.Checked
                self._odor_circuit_arduino_logic.valve(self._valve_odor_1_out, 1)
                self.valves_status['valve_odor_1_out'] = '1'
                self.update_valve_label(self._mw.label_1out, 1)
            else:
                self._odor_circuit_arduino_logic.valve(self._valve_odor_1_out, 0)
                self.valves_status['valve_odor_1_out'] = '0'
                self.update_valve_label(self._mw.label_1out, 0)
        elif sender == self._mw.checkBox_3:
            if state == 2:  # Qt.Checked
                self._odor_circuit_arduino_logic.valve(self._valve_odor_2_in, 1)
                self.valves_status['valve_odor_2_in'] = '1'
                self.update_valve_label(self._mw.label_2in, 1)
            else:
                self._odor_circuit_arduino_logic.valve(self._valve_odor_2_in, 0)
                self.valves_status['valve_odor_2_in'] = '0'
                self.update_valve_label(self._mw.label_2in, 0)
        elif sender == self._mw.checkBox_4:
            if state == 2:  # Qt.Checked
                self._odor_circuit_arduino_logic.valve(self._valve_odor_2_out, 1)
                self.valves_status['valve_odor_2_out'] = '1'
                self.update_valve_label(self._mw.label_2out, 1)
            else:
                self._odor_circuit_arduino_logic.valve(self._valve_odor_2_out, 0)
                self.valves_status['valve_odor_2_out'] = '0'
                self.update_valve_label(self._mw.label_2out, 0)
        elif sender == self._mw.checkBox_5:
            if state == 2:  # Qt.Checked
                self._odor_circuit_arduino_logic.valve(self._valve_odor_3_in, 1)
                self.valves_status['valve_odor_3_in'] = '1'
                self.update_valve_label(self._mw.label_3in, 1)
            else:
                self._odor_circuit_arduino_logic.valve(self._valve_odor_3_in, 0)
                self.valves_status['valve_odor_3_in'] = '0'
                self.update_valve_label(self._mw.label_3in, 0)
        elif sender == self._mw.checkBox_6:
            if state == 2:  # Qt.Checked
                self._odor_circuit_arduino_logic.valve(self._valve_odor_3_out, 1)
                self.valves_status['valve_odor_3_out'] = '1'
                self.update_valve_label(self._mw.label_3out, 1)
            else:
                self._odor_circuit_arduino_logic.valve(self._valve_odor_3_out, 0)
                self.valves_status['valve_odor_3_out'] = '0'
                self.update_valve_label(self._mw.label_3out, 0)
        elif sender == self._mw.checkBox_7:
            if state == 2:  # Qt.Checked
                self._odor_circuit_arduino_logic.valve(self._valve_odor_4_in, 1)
                self.valves_status['valve_odor_4_in'] = '1'
                self.update_valve_label(self._mw.label_4in, 1)
            else:
                self._odor_circuit_arduino_logic.valve(self._valve_odor_4_in, 0)
                self.valves_status['valve_odor_4_in'] = '0'
                self.update_valve_label(self._mw.label_4in, 0)
        elif sender == self._mw.checkBox_8:
            if state == 2:  # Qt.Checked
                self._odor_circuit_arduino_logic.valve(self._valve_odor_4_out, 1)
                self.valves_status['valve_odor_4_out'] = '1'
                self.update_valve_label(self._mw.label_4out, 1)
            else:
                self._odor_circuit_arduino_logic.valve(self._valve_odor_4_out, 0)
                self.valves_status['valve_odor_4_out'] = '0'
                self.update_valve_label(self._mw.label_4out, 0)
        elif sender == self._mw.checkBox_F:
            if state == 2:  # Qt.Checked
                self._odor_circuit_arduino_logic.valve(self._final_valve, 1)
                self.valves_status['final_valve_valve'] = '1'
                self.update_final_valve_label(1)
            else:
                self._odor_circuit_arduino_logic.valve(self._final_valve, 0)
                self.valves_status['final_valve_valve'] = '0'
                self.update_final_valve_label(0)
        elif sender == self._mw.checkBox_M:
            if state == 2:  # Qt.Checked
                self._odor_circuit_arduino_logic.valve(self._mixing_valve, 1)
                self.valves_status['mixing_valve'] = '1'
                self.update_valve_label(self._mw.label_M, 1)
            else:
                self._odor_circuit_arduino_logic.valve(self._mixing_valve, 0)
                self.valves_status['mixing_valve'] = '0'
                self.update_valve_label(self._mw.label_M, 0)

    def mfc_on(self):
        value1 = self._mw.doubleSpinBox.value()
        value2 = self._mw.doubleSpinBox_2.value()
        value3 = self._mw.doubleSpinBox_3.value()
        self._odor_circuit_arduino_logic.open_air(value1, value2, value3)

    def mfc_on_off(self):
        """ Turn the MFCs on or off switching the MFC status
        """
        Permission = self.check_valves(self.valves_status)
        if not self.MFC_status:
            if Permission == 1:
                logger.info("Opening air...")
                self.sigMFC_ON.emit()
                self._mw.actionMFC_ON_OFF.setText('MFC : ON')
                self.MFC_status = True
                self.update_valve_label(self._mw.label_MFCpurge, 1)
                self.update_valve_label(self._mw.label_MFC1, 1)
                self.update_valve_label(self._mw.label_MFC2, 1)
            else:
                logger.info("Permission denied")
        else:
            logger.info("Closing air...")
            self._mw.actionMFC_ON_OFF.setText('MFC : OFF')
            self.sigMFC_OFF.emit()
            self.MFC_status = False
            self.update_valve_label(self._mw.label_MFCpurge, 0)
            self.update_valve_label(self._mw.label_MFC1, 0)
            self.update_valve_label(self._mw.label_MFC2, 0)

    def disable_odor_buttons(self):
        """ Disables buttons, to not mix all odors.
        """
        self._mw.toolButton_1.setDisabled(True)
        self._mw.toolButton_2.setDisabled(True)
        self._mw.toolButton_3.setDisabled(True)
        self._mw.toolButton_4.setDisabled(True)

    def enable_odor_buttons(self):
        """ Enables buttons, to inject a new odor.
        """
        self._mw.toolButton_1.setDisabled(False)
        self._mw.toolButton_2.setDisabled(False)
        self._mw.toolButton_3.setDisabled(False)
        self._mw.toolButton_4.setDisabled(False)

    # ----------------------------------------------------------------------------------------------------------------------
    # Slots related to the flowcontrol
    # ----------------------------------------------------------------------------------------------------------------------

    def measure_flow_clicked(self):
        """ Callback of start flow measurement toolbutton. Handles the toolbutton state and initiates the start / stop
        of flowrate .
        """
        if self._odor_circuit_arduino_logic.measuring_flowrate:  # measurement already running
            self._mw.start_flow_measurement_Action.setText('Start flowrate measurement')
            self.sigStopFlowMeasure.emit()
            self._mw.actionMFC_ON_OFF.setDisabled(False)
            #np.savetxt(self._path_MFC1, self.flowrate1_data)
            #np.savetxt(self._path_MFC2, self.flowrate2_data)
            #np.savetxt(self._path_MFCPurge, self.flowrate3_data)
        else:
            self._mw.start_flow_measurement_Action.setText('Stop flowrate measurement')
            self.t_data = []
            self.flowrate1_data = []
            self.flowrate2_data = []
            self.flowrate3_data = []
            self.sigStartFlowMeasure.emit()
            self._mw.actionMFC_ON_OFF.setDisabled(True)

    @QtCore.Slot(list, list, list)
    def update_flowrate(self, flowrate1, flowrate2, flowrate3):
        """ Callback of a signal emitted from logic informing the GUI about the new flowrate values.
        :param float flowrate1: current flowrate retrieved from hardware
        """
        self.update_flowrate_timetrace(flowrate1[0], flowrate2[0], flowrate3[0])

    def update_flowrate_timetrace(self, flowrate1, flowrate2, flowrate3):
        """ Add a new data point to the  flowrate timetraces.
        :param float flowrate1: current flowrate retrieved from hardware
        """

        if len(self.flowrate1_data) < 100:
            self.t_data.append(len(self.t_data))
            self.flowrate1_data.append(flowrate1)
            self.flowrate2_data.append(flowrate2)
            self.flowrate3_data.append(flowrate3)

        else:
            self.t_data[:-1] = self.t_data[1:]
            self.t_data[-1] += 1

            self.flowrate1_data[:-1] = self.flowrate1_data[1:]  # shift data one position to the left
            self.flowrate1_data[-1] = flowrate1
            self.flowrate2_data[:-1] = self.flowrate2_data[1:]  # shift data one position to the left
            self.flowrate2_data[-1] = flowrate2
            self.flowrate3_data[:-1] = self.flowrate3_data[1:]  # shift data one position to the left
            self.flowrate3_data[-1] = flowrate3

        self._flowrate1_timetrace.setData(self.t_data, self.flowrate1_data)  # t axis running with time
        self._flowrate2_timetrace.setData(self.t_data, self.flowrate2_data)
        self._flowrate3_timetrace.setData(self.t_data, self.flowrate3_data)

    @QtCore.Slot()
    def disable_flowcontrol_buttons(self):
        """ Disables flowrate measurement  """

        self._mw.start_flow_measurement_Action.setDisabled(True)

    @QtCore.Slot()
    def enable_flowcontrol_buttons(self):
        """ Enables flowcontrol toolbuttons. """
        self._mw.start_flow_measurement_Action.setDisabled(False)

    def close_function(self):
        """ This method serves as a reimplementation of the close event. Continuous measurement modes are stopped
        when the main window is closed. """
        if self._odor_circuit_arduino_logic.measuring_flowrate:
            self.sigStopFlowMeasure.emit()
            self._mw.start_flow_measurement_Action.setText('Start flowrate measurement')
            self._mw.start_flow_measurement_Action.setChecked(False)
