# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains a GUI for the odor circuit on the Fly Arena.

An extension to Qudi.

@author: D. Guerin, JB. Fiche

Created on Fry May 24, 2024
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

import logging
import os
import numpy as np
from PyQt5.QtCore import QTimer, Qt, QTime
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QFileDialog
from matplotlib import pyplot as plt
from qtpy import QtWidgets, uic, QtCore
# from qtpy.QtCore import Signal
# from scipy.stats import norm
# from datetime import datetime
from time import sleep
from core.configoption import ConfigOption
from core.connector import Connector
from gui.guibase import GUIBase

logging.basicConfig(filename='logfile.log', filemode='w', level=logging.DEBUG)
logger = logging.getLogger(__name__)


class MFCcheckWindow(QtWidgets.QDialog):
    """ Create the MFC calibration window, based on the corresponding *.ui file.
    This dialog allows the calibration of the MFCs """

    def __init__(self):
        super().__init__()
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'MFCcheck.ui')
        uic.loadUi(ui_file, self)


class MainWindow(QtWidgets.QMainWindow):
    """ Class defined for the main window for odor control.
    """

    def __init__(self, close_function):
        super().__init__()
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'odor_circuit_window1.ui')
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
    odor_logic = Connector(interface='OdorCircuitArduinoLogic')
    _Path_MFC = ConfigOption('Path_MFC', None)
    _Fluidics_off_path = ConfigOption('Fluidics_off_path', None)
    _Fluidics_on_path = ConfigOption('Fluidics_on_path', None)
    _default_quadrant_flow = ConfigOption('default_quadrant_flow', None)
    # _odors = ConfigOption('odors', None)
    _config_valves = ConfigOption('config_valve', None)
    _config_path = ConfigOption('config_path', None)

    # _path_MFC1 = ConfigOption('path_MFC1', None)
    # _path_MFC2 = ConfigOption('path_MFC2', None)
    # _path_MFCPurge = ConfigOption('path_MFCPurge', None)
    # valve_odor_1_in = 0
    # valve_odor_2_in = 0
    # valve_odor_3_in = 0
    # valve_odor_4_in = 0
    # valve_odor_1_out = 0
    # valve_odor_2_out = 0
    # valve_odor_3_out = 0
    # valve_odor_4_out = 0
    # mixing_valve = 0
    # final_valve = 0
    MFC_status = False

    sigStartFlowMeasure = QtCore.Signal()
    sigStopFlowMeasure = QtCore.Signal()
    sigChangeValveState = QtCore.Signal(str, int)
    sigStopFlowCalibration = QtCore.Signal()
    # define the default language option as English (to make sure all float have a point as a separator)
    QtCore.QLocale.setDefault(QtCore.QLocale("English"))

    # # Declaration of custom signals
    # sigMFC_ON = Signal()
    # sigMFC_OFF = Signal()
    # sigLaunchClicked = Signal()

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self.date_str = None
        # self.Caltime = 0
        # self.G = 0
        self.prep_timer: object = None
        self.start_prep_time: int = 0
        self.inject_timer: object = None
        self.start_inject_time: int = 0
        self.calibration_timer: object = None
        self.start_calibration_time: int = 0
        self.flowrate_timetraces: dict = {}
        self.flowrate_data: dict = {}
        self.measure: dict = {}
        self.t_data: list = []
        self.MFC_number: int = 0
        self.odor_number: int = 0
        self._odors: list = []
        self.preparing_odor: bool = False
        self.injecting_odor: bool = False
        self.calibrating_MFCs: bool = False
        self.selected_odor: int = 0
        self.valve_status: dict = {}
        self.pixmap_fluidics_scheme: object = None

        # self._flowrate1_timetrace = None
        # self._flowrate2_timetrace = None
        # self._flowrate3_timetrace = None
        # self._flowrate4_timetrace = None
        # self.mesure1 = None
        # self.mesure2 = None
        # self.mesure3 = None
        # self.mesure4 = None
        # self.flowrate1_data = None
        # self.flowrate2_data = None
        # self.flowrate3_data = None
        # self.flowrate4_data = None
        self._odor_logic = None
        self._mw = None
        self._MFCW = None

        # self.valves_status = {
        #     'valve_odor_1_in': '0',
        #     'valve_odor_2_in': '0',
        #     'valve_odor_3_in': '0',
        #     'valve_odor_4_in': '0',
        #     'final_valve': '0',
        #     'mixing_valve': '0',
        #     'valve_odor_1_out': '0',
        #     'valve_odor_2_out': '0',
        #     'valve_odor_3_out': '0',
        #     'valve_odor_4_out': '0'
        # }
        # self.valves_in_out = {
        #     'odor_1': ['valve_odor_1_in', 'valve_odor_1_out'],
        #     'odor_2': ['valve_odor_2_in', 'valve_odor_2_out'],
        #     'odor_3': ['valve_odor_3_in', 'valve_odor_3_out'],
        #     'odor_4': ['valve_odor_4_in', 'valve_odor_4_out']
        # }
        self._mw = MainWindow(close_function=self.close_function)  # Assuming MainWindow handles main UI
        self._mfcw = MFCcheckWindow()

        # self.pixmap1 = QPixmap(self._Fluidics_on_path)
        # self.pixmap2 = QPixmap(self._Fluidics_off_path)
        # self.pixmap1 = self.pixmap1.scaled(1101, 651, Qt.KeepAspectRatio)
        # self.pixmap2 = self.pixmap2.scaled(1101, 651, Qt.KeepAspectRatio)

    def on_activate(self):
        """ Initialize all UI elements and establish signal connections.
        """
        # Connect logic and initialize variables for the GUI
        self._odor_logic = self.odor_logic()
        self.MFC_number = self._odor_logic.MFC_number
        self.odor_number = self._odor_logic.n_odors_available
        self._odors = self._odor_logic.odor_list

        # Initialize the main window and its dockwidgets
        self._mw.centralwidget.show()
        self.init_menu()
        self.init_toolbar()
        self.init_flowcontrol_main_window()
        self.init_MFC_calibration_window()

        # Set the default flow
        self._mw.doubleSpinBox_quadrant_flow.setValue(self._default_quadrant_flow)
        self.update_arena_config()

    def on_deactivate(self):
        """ Steps of deactivation required.
        """
        self._mw.close()

# ----------------------------------------------------------------------------------------------------------------------
# Methods handling GUI windows and dockwidgets
# ----------------------------------------------------------------------------------------------------------------------
    def show(self):
        """ To make the window visible and bring it to the front.
        """
        QtWidgets.QMainWindow.show(self._mw)
        self._mw.activateWindow()
        self._mw.raise_()

    # def show_admin_Dock(self):
    #     """Show the dock widget"""
    #     self._mw.admin_dockWidget.show()
    #
    # def hide_admin_Dock(self):
    #     """Hide the dock widget"""
    #     self._mw.admin_dockWidget.hide()

    def show_MFC_calibration_window(self):
        """ Show the plot window
        """
        self._mfcw.show()

    def init_menu(self):
        """ Initialize actions controlled by menu
        """
        # self._mw.actionShow_Configuration_Dock.triggered.connect(self.show_admin_Dock)
        self._mw.actionShow_MFC_stability_check.triggered.connect(self.show_MFC_calibration_window)

    def init_toolbar(self):
        """ Initialize toolbar actions
        """
        # self._mw.actionMFC_ON_OFF.setText('MFC : OFF')
        # self._mw.actionMFC_ON_OFF.triggered.connect(self.mfc_on_off)
        self._mw.start_flow_measurement_Action.triggered.connect(self.measure_flow_clicked)
        # self.sigMFC_ON.connect(self.mfc_on)
        # self.sigMFC_OFF.connect(self._odor_logic.stop_air_flow)

        # Connect signals to logic
        self.sigStartFlowMeasure.connect(self._odor_logic.start_flow_measurement)
        self.sigStopFlowMeasure.connect(self._odor_logic.stop_flow_measurement)

        # Connect signals from logic
        self._odor_logic.sigUpdateFlowMeasurement.connect(self.update_flowrate)
        self._odor_logic.sigDisableFlowActions.connect(self.disable_flowcontrol_buttons)
        self._odor_logic.sigEnableFlowActions.connect(self.enable_flowcontrol_buttons)

    def init_MFC_calibration_window(self):
        """ Initialize actions handle by the MFC calibration window
        """
        # Initialize pushbutton
        self._mfcw.toolButton_abort_calibration.setDisabled(True)

        # Connect signals to methods
        self._mfcw.toolButton_abort_calibration.clicked.connect(self.abort_MFC_calibration)
        self._mfcw.toolButton_start_calibration.clicked.connect(self.start_MFC_calibration)
        self._mfcw.toolButton_select_folder.clicked.connect(self.select_folder)

        # initialize timer
        self.calibration_timer = QTimer()
        self.calibration_timer.timeout.connect(lambda: self.update_calibration_timer(
            self._mfcw.doubleSpinBox_calibration_duration.value()))

        # connect signal to logic
        self.sigStopFlowCalibration.connect(self._odor_logic.stop_flow_calibration)

    def init_flowcontrol_main_window(self):
        """Initialize the flowcontrol dockwidget, setting up plots, labels, and signal-slot connections.
        """
        # assign odor names & disable the empty names
        for n_odor in range(len(self._odors)):
            checkbox = getattr(self._mw, f'odor{n_odor + 1}_CheckBox', None)
            checkbox.setText(self._odors[n_odor])
            if self._odors[n_odor] == 'no odor':
                checkbox.setDisabled(True)

        # display the fluidics scheme
        self.display_fluidics_scheme(0)

        # Connect signals from pushButtons to methods
        self._mw.comboBox_quadrants_config.currentIndexChanged.connect(self.update_arena_config)
        self._mw.doubleSpinBox_quadrant_flow.editingFinished.connect(self.update_arena_config)
        self._mw.Prepare_odor_pushButton.clicked.connect(self.prepare_odor_clicked)
        self._mw.Prepare_odor_pushButton.clicked.connect(self.start_prep_timer)
        self._mw.Inject_odor_pushButton.clicked.connect(self.inject_odor_clicked)
        self._mw.Inject_odor_pushButton.clicked.connect(self.start_inject_timer)
        self._mw.Stop_odor_pushButton.clicked.connect(self.stop_odor_clicked)
        self._mw.Switch_quadrant_pushButton.clicked.connect(self.switch_quadrant_clicked)

        # Connect signals from logic
        self._odor_logic.sigUpdateValveState.connect(self.update_valves_status)
        self._odor_logic.sigUpdateValveState.connect(self.display_circuit_config)
        self._odor_logic.sigTaskStartStop.connect(self.disable_enable_GUI)
        self._odor_logic.sigTaskUpdateOdorGui.connect(self.update_GUI)
        self._odor_logic.sigStartPrepOdor.connect(self.prepare_odor_clicked)
        self._odor_logic.sigUpdatePrepTimer.connect(self.update_prep_timer_from_logic)
        self._odor_logic.sigStartInjectOdor.connect(self.inject_odor_clicked)
        self._odor_logic.sigUpdateInjectTimer.connect(self.update_injection_timer_from_logic)

        # Connect signals from checkBox to methods
        self._mw.odor1_CheckBox.toggled.connect(lambda checked: self.selected_odor_changed(1, checked))
        self._mw.odor2_CheckBox.toggled.connect(lambda checked: self.selected_odor_changed(2, checked))
        self._mw.odor3_CheckBox.toggled.connect(lambda checked: self.selected_odor_changed(3, checked))
        self._mw.odor4_CheckBox.toggled.connect(lambda checked: self.selected_odor_changed(4, checked))
        self._mw.valve_odor_1_checkBox.toggled.connect(lambda checked:
                                                       self._odor_logic.change_valve_state("odor_1", checked))
        self._mw.valve_odor_2_checkBox.toggled.connect(lambda checked:
                                                       self._odor_logic.change_valve_state("odor_2", checked))
        self._mw.valve_odor_3_checkBox.toggled.connect(lambda checked:
                                                       self._odor_logic.change_valve_state("odor_3", checked))
        self._mw.valve_odor_4_checkBox.toggled.connect(lambda checked:
                                                       self._odor_logic.change_valve_state("odor_4", checked))
        self._mw.valve_mixing_checkBox.toggled.connect(lambda checked:
                                                       self._odor_logic.change_valve_state("mixing", checked))
        self._mw.valve_switch_purge_arena_checkBox.toggled.connect(
            lambda checked: self._odor_logic.change_valve_state("switch_purge_arena", checked))
        self._mw.valve_switch_quadrants_checkBox.toggled.connect(
            lambda checked: self._odor_logic.change_valve_state("switch_quadrants", checked))
        self._mw.valve_3_way_checkBox.toggled.connect(lambda checked:
                                                      self._odor_logic.change_valve_state("3_way", checked))

        # initialize pushButtons for odor
        self.disable_enable_odor_pushbuttons()

        # initialize checkBox for valves control
        self.disable_enable_valves_checkbox(False)

        # Configure plot widget and define plot colors and labels
        plot_widget = self._mw.flowrate_PlotWidget_1
        plot_widget.setLabel('left', 'Flowrate', units='L/min')
        plot_widget.setLabel('bottom', 'Time', units='s')
        plot_widget.addLegend()
        colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)]
        labels = [f'MFC{i + 1}' for i in range(self.MFC_number)]

        # Initialize data containers for the flowchart
        self.t_data = []
        self.flowrate_data = {i: [] for i in range(self.MFC_number)}
        self.mesure_data = {i: [] for i in range(self.MFC_number)}
        self.flowrate_timetraces = {
            i: plot_widget.plot(self.t_data, self.flowrate_data[i], pen=colors[i], name=labels[i])
            for i in range(self.MFC_number)
        }

        # Initialize timers
        self.prep_timer, self.inject_timer = QTimer(), QTimer()
        self.prep_timer.timeout.connect(self.update_prep_timer)
        self.inject_timer.timeout.connect(self.update_inject_timer)

    def disable_enable_odor_pushbuttons(self, prep=True, inject=True, stop=True):
        """ Disable / Enable push buttons related to odor injection in arena """
        self._mw.Prepare_odor_pushButton.setDisabled(prep)
        self._mw.Inject_odor_pushButton.setDisabled(inject)
        self._mw.Stop_odor_pushButton.setDisabled(stop)

    def close_function(self):
        """
        This method serves as a reimplementation of the close event. Continuous measurement modes are stopped
        when the main window is closed.
        """
        if self._odor_logic.measuring_flowrate:
            self.sigStopFlowMeasure.emit()
            self._mw.start_flow_measurement_Action.setText('Start flowrate measurement')
            self._mw.start_flow_measurement_Action.setChecked(False)

    def display_fluidics_scheme(self, config):
        """ Handle the display of the valves & MFC scheme, depending on the indicated configuration
        @param config (int) indicate the configuration of the circuit
        """
        self.pixmap_fluidics_scheme = QPixmap(self._config_path[config])
        self.pixmap_fluidics_scheme = self.pixmap_fluidics_scheme.scaled(1021, 551, Qt.KeepAspectRatio,
                                                                         Qt.SmoothTransformation)
        self._mw.label_circuit_scheme.setPixmap(self.pixmap_fluidics_scheme)

# ----------------------------------------------------------------------------------------------------------------------
# Methods handling arena configuration & odors
# ----------------------------------------------------------------------------------------------------------------------
    def update_combobox_quadrant(self, index):
        self._mw.comboBox_quadrants_config.setCurrentIndex(index)

    def update_arena_config(self):
        """ Based on the comboBox value & the flow-rate setpoint for the arena (for each quadrant), compute the
        flow-rate for each MFC.
        """
        # read the comboBox to define which configuration is selected. Same for the flow which will define the expected
        # air-flow in each quadrant
        index = self._mw.comboBox_quadrants_config.currentIndex()
        flow = self._mw.doubleSpinBox_quadrant_flow.value()

        # check if measurement of flowrate is running - if yes, suspend it to allow communication with MFCs
        flowrate_measurement = self._odor_logic.measuring_flowrate
        if flowrate_measurement:
            self.sigStopFlowMeasure.emit()
            sleep(2)

        # depending on the selected config, define the air-flow setpoint values for each MFC and send it to the logic.
        # Three configurations are available :
        # 1: all MFCs are off - all valves (except the switch valve for the quadrants) are set to their initial states
        # 2: the two pairs of quadrants are handle using two different circuits - quadrants 1/3 are connected to the
        # odor circuit through MFCs 1/2/3 (air or odor, depending on the state of the final valve) and quadrants 2/4 are
        # connected to MFC 4 (air)
        # 3: all quadrants are connected to the odor circuits - MFC4 is then turned off.
        if (index == 0) or (flow == 0):
            self.disable_enable_valves_checkbox(False)
            mfc_flow = self._odor_logic.stop_air_flow()
            self.disable_enable_odor_pushbuttons()
            self.preparing_odor = False
            self.injecting_odor = False

        elif index == 1:
            self.disable_enable_valves_checkbox(True)
            mfc_flow = self._odor_logic.start_air_flow(flow, config=1)
            self.disable_enable_odor_pushbuttons(prep=False)
        else:
            self.disable_enable_valves_checkbox(True)
            mfc_flow = self._odor_logic.start_air_flow(flow, config=2)
            self.disable_enable_odor_pushbuttons(prep=False)

        # update the set-points for all MFCs
        self._mw.MFC1_setpoint.setText(f'{str(mfc_flow[0])} sL/min')
        self._mw.MFC2_setpoint.setText(f'{str(mfc_flow[1])} sL/min')
        self._mw.MFC3_setpoint.setText(f'{str(mfc_flow[2])} sL/min')
        self._mw.MFC4_setpoint.setText(f'{str(mfc_flow[3])} sL/min')

        # restart flowrate measurement if it was running
        if flowrate_measurement:
            self.sigStartFlowMeasure.emit()

    def selected_odor_changed(self, odor, state):
        """ Handle the change in the state of the odor selection checkboxes. Note that only one checkBox can be selected
        at a time.
        @param: odor (int) indicate which odor is selected (from the checkbox)
        @param: state (int) indicate whether the checkbox is checked or unchecked
        """
        if state:
            # make sure all the other checkboxes are unchecked
            for i in range(1, self.odor_number + 1):
                if i != odor:
                    checkbox = getattr(self._mw, f'odor{i}_CheckBox', None)
                    checkbox.setChecked(False)
            # define the selected odor
            self.selected_odor = odor
        else:
            self.selected_odor = 0

    def prepare_odor_clicked(self):
        """ Handle the click event to launch the odor preparation process. Note that when clicked the procedure is
        launched and can only be stopped either by using the "Stop odor" or the "Inject odor" pushButtons.
        """
        # check if one odor was selected
        if self.selected_odor == 0:
            self.log.error("You need to select at least one odor")
            self._mw.Prepare_odor_pushButton.setChecked(False)
            return

        # release the inject and stop pushbuttons
        self.disable_enable_odor_pushbuttons(prep=True, inject=False, stop=False)

        # prepare the selected odor
        # odor_prep_time = self._mw.doubleSpinBox_odor_prep_duration.value() * 60
        if not self.preparing_odor:
            self._mw.Prepare_odor_pushButton.setChecked(True)
            self._mw.Prepare_odor_pushButton.setText('Preparing odor ...')
            self._odor_logic.prepare_odor(self.selected_odor)
            self.preparing_odor = True

            # check if an injection was performed
            if self.injecting_odor:
                self._mw.Inject_odor_pushButton.setChecked(False)
                self._mw.Inject_odor_pushButton.setText('Inject odor')
                self.injecting_odor = False

    def inject_odor_clicked(self):
        """ Handle event to launch injection into the arena. Note that when clicked the procedure is
        launched and can only be stopped by using either the "Stop odor" or "Prepare odor" pushButtons
        """
        # check if an odor is already in preparation
        if not self.preparing_odor:
            self.log.error("No odor is in preparation")
            self._mw.Inject_odor_pushButton.setChecked(False)
            return

        # release the prep and stop pushbuttons
        self.disable_enable_odor_pushbuttons(prep=False, inject=True, stop=False)

        # stop the timer for odor preparation
        self.stop_prep_timer()

        # inject the selected odor in the arena
        if not self.injecting_odor:
            # release the prepare odor pushButton
            self._mw.Prepare_odor_pushButton.setChecked(False)
            self._mw.Prepare_odor_pushButton.setText('Prepare odor')

            # launch injection
            self._mw.Inject_odor_pushButton.setChecked(True)
            self._mw.Inject_odor_pushButton.setText('Injecting odor ...')
            self._odor_logic.inject_odor()
            self.injecting_odor = True
            self.preparing_odor = False

    def stop_odor_clicked(self):
        """ Stop any preparation or injection of odor
        """
        # enable pushbutton for prep and disable the others
        self.disable_enable_odor_pushbuttons(prep=False, inject=True, stop=True)

        # release the prepare odor pushButton
        self._mw.Prepare_odor_pushButton.setChecked(False)
        self._mw.Prepare_odor_pushButton.setText('Prepare odor')
        self.preparing_odor = False

        # release the inject odor pushButton
        self._mw.Inject_odor_pushButton.setChecked(False)
        self._mw.Inject_odor_pushButton.setText('Inject odor')
        self.injecting_odor = False

        # send to logic
        self._odor_logic.stop_odor(self.selected_odor)

    def switch_quadrant_clicked(self):
        """ Change the quadrants' configuration. By default, quadrants 1/3 are connected to the odor circuit and
        quadrants 2/4 to the MFC4 & 3-way valve. When the valve is activated, the quadrants 1/3 and 2/4 are inverted.
        """
        state = self._mw.Switch_quadrant_pushButton.isChecked()
        self._odor_logic.switch_quadrants(int(state))

# ----------------------------------------------------------------------------------------------------------------------
# Methods handling the timers
# ----------------------------------------------------------------------------------------------------------------------
    def start_prep_timer(self):
        """Starts the timer for the odor preparation (when the button is clicked)."""
        print("starting timer...")
        self.start_prep_time = QTime.currentTime()  # Store start time
        self.prep_timer.start(1000)  # Update every second

    def update_prep_timer(self):
        """Updates the QLineEdit with elapsed time."""
        if self.start_prep_time and self.preparing_odor:
            elapsed = self.start_prep_time.secsTo(QTime.currentTime())  # Get elapsed time in seconds
            self._mw.prep_timer_display.setText(f"{elapsed} sec")
        else:
            self.stop_prep_timer()

    def stop_prep_timer(self):
        """Stops the odor preparation timer and resets the display."""
        self.prep_timer.stop()
        self.start_prep_time = None
        self._mw.prep_timer_display.setText("")

    def start_inject_timer(self):
        """Starts the timer for the odor preparation (when the button is clicked)."""
        self.start_inject_time = QTime.currentTime()  # Store start time
        self.inject_timer.start(1000)  # Update every second

    def update_inject_timer(self):
        """Updates the QLineEdit with elapsed time."""
        if self.start_inject_time and self.injecting_odor:
            elapsed = self.start_inject_time.secsTo(QTime.currentTime())  # Get elapsed time in seconds
            self._mw.inject_timer_display.setText(f"{elapsed} sec")
        else:
            self.stop_inject_timer()

    def stop_inject_timer(self):
        """Stops the odor preparation timer and resets the display."""
        self.inject_timer.stop()
        self.start_inject_time = None
        self._mw.inject_timer_display.setText("")

    def start_calibration_timer(self):
        """Starts the timer for the MFC calibration (when the toolButton_start_calibration is clicked)."""
        self.start_calibration_time = QTime.currentTime()  # Store start time
        self.calibration_timer.start(1000)  # Update every second

    def update_calibration_timer(self, duration):
        """ Updates the QLineEdit with elapsed time.
        @param: duration (float): indicate the duration of the calibration in minutes.
        """
        if self.start_calibration_time and self.calibrating_MFCs:
            elapsed = self.start_calibration_time.secsTo(QTime.currentTime())  # Get elapsed time in seconds
            self._mfcw.calibration_timer_display.setText(f"{elapsed} sec")
            if elapsed >= duration * 60:
                self.stop_calibration_timer()
        else:
            self.stop_calibration_timer()

    def stop_calibration_timer(self):
        """ Stops the odor preparation timer and resets the display.
        """
        # reinitialize the timer
        self.calibration_timer.stop()
        self.start_calibration_time = None
        self._mfcw.calibration_timer_display.setText("")

        # send signal to logic indicating the calibration should be terminated
        self.sigStopFlowCalibration.emit()

        # stop the calibration
        self.abort_MFC_calibration()

# ----------------------------------------------------------------------------------------------------------------------
# Methods handling the valves states
# ----------------------------------------------------------------------------------------------------------------------
    @QtCore.Slot(dict)
    def update_valves_status(self, status_dict):
        """ Update the status of the valve on the GUI
        @param status_dict: (dict) indicate whether a valve is open or close
        """
        self.valve_status = status_dict
        for key in self.valve_status.keys():
            checkbox = getattr(self._mw, f'valve_{key}_checkBox', None)
            checkbox.blockSignals(True)
            if status_dict[key] == 0:
                checkbox.setChecked(False)
            else:
                checkbox.setChecked(True)
            checkbox.blockSignals(False)

    def disable_enable_valves_checkbox(self, disable):
        """ For security, the valve checkboxes will be disabled when the MFCs are ON (to avoid closing or opening a
        valve while an experiment is running). However, when the MFCs are OFF, the checkbox associated to the valves
        will remain enable to allow testing (for debugging for example).
        @param disable: (bool) True if the checkboxes need to be disabled.
        """
        for key in self.valve_status.keys():
            checkbox = getattr(self._mw, f'valve_{key}_checkBox', None)
            checkbox.setDisabled(disable)
            sleep(0.05)

    def display_circuit_config(self, status_dict):
        """ Read the status_dict and select the associated valve configuration to display an illustration of the
        fluidics circuit
        @param status_dict: (dict) indicate whether a valve is open or close
        """
        index = self._mw.comboBox_quadrants_config.currentIndex()
        if index > 0:
            # convert status dictionary into a list
            status_list = [status_dict[key] for key in status_dict.keys()]
            print(status_list)

            # compare the list to the self._config_valves
            matching_config = [n_config if config == status_list else None
                               for n_config, config in enumerate(self._config_valves)]
            print(matching_config)

            # look for the matching config that is not None
            matching_config = next((config for config in matching_config if config is not None), None)

            # display the matching config
            if matching_config is not None:
                print(f'matching_config: {matching_config}')
                print(self._config_path[matching_config])
                self.display_fluidics_scheme(matching_config)
            else:
                print(f'matching_config: {matching_config} does not exist')

        else:
            self.display_fluidics_scheme(0)

# ----------------------------------------------------------------------------------------------------------------------
# Methods handling the flow chart (live display of the MFCs flow-rate)
# ----------------------------------------------------------------------------------------------------------------------
    @QtCore.Slot()
    def disable_flowcontrol_buttons(self):
        """
        Disables flowrate measurement action button
        """
        self._mw.start_flow_measurement_Action.setDisabled(True)

    @QtCore.Slot()
    def enable_flowcontrol_buttons(self):
        """
        Enables flowrate measurement action button
        """
        self._mw.start_flow_measurement_Action.setDisabled(False)

    def measure_flow_clicked(self):
        """
        Callback of start flow measurement tool button. Handles the tool button state and initiates the start / stop
        of flowrate .
        """
        if self._odor_logic.measuring_flowrate:  # measurement already running
            self._mw.start_flow_measurement_Action.setText('Start flowrate measurement')
            self.sigStopFlowMeasure.emit()
        else:
            self._mw.start_flow_measurement_Action.setText('Stop flowrate measurement')
            self.t_data = []
            self.flowrate_data = {i: [] for i in range(self.MFC_number)}
            self.sigStartFlowMeasure.emit()

    @QtCore.Slot(list)
    def update_flowrate(self, flow_rates):
        """
        Callback of a signal emitted from logic informing the GUI about the new flowrate values.
        @param (list) flow_rates: current flow-rates retrieved from hardware MFCs
        """
        # self.G += 1
        # Update flow rate data - a maximum of 100 data points will be displayed on the time trace.
        if len(self.flowrate_data[1]) < 100:
            self.t_data.append(len(self.t_data))
            for i in range(self.MFC_number):
                self.flowrate_data[i].append(flow_rates[i])
                getattr(self._mw, f'MFC{i + 1}').setText(f'{np.around(flow_rates[i], decimals=3)} sL/min')
        else:
            self.t_data[:-1] = self.t_data[1:]
            self.t_data[-1] += 1

            for i in range(self.MFC_number):
                self.flowrate_data[i][:-1] = self.flowrate_data[i][1:]  # Shift data
                self.flowrate_data[i][-1] = flow_rates[i]

        # Update the time trace on the flow chart
        for i in range(self.MFC_number):
            self.flowrate_timetraces[i].setData(self.t_data, self.flowrate_data[i])

# ----------------------------------------------------------------------------------------------------------------------
# Methods handling the characterization / calibration of the MFCs
# ----------------------------------------------------------------------------------------------------------------------
    def start_MFC_calibration(self):
        """
        Start calibration of the MFcs flow (noise)
        """
        # disable the main window to avoid race issues and the calibration button
        self._mw.setDisabled(True)
        self._mfcw.toolButton_start_calibration.setDisabled(True)

        # initialize variables
        self.calibrating_MFCs = True
        self._mfcw.toolButton_abort_calibration.setDisabled(False)
        self.calibration_time = self._mfcw.doubleSpinBox_calibration_duration.value()
        mfc_setpoint = self._mfcw.doubleSpinBox_MFCs_setpoint.value()

        # check if measurement of flowrate is running - if yes, suspend it to allow communication with MFCs
        flowrate_measurement = self._odor_logic.measuring_flowrate
        if flowrate_measurement:
            self.sigStopFlowMeasure.emit()
            sleep(2)

        # set the configuration of the arena to ALL-OFF
        self._mw.comboBox_quadrants_config.setCurrentIndex(0)

        # launch MFCs based on the indicated setpoints - all MFCs are set to the same values
        mfc_flow = [mfc_setpoint, mfc_setpoint, mfc_setpoint, mfc_setpoint]
        self._odor_logic.start_air_flow(mfc_flow, config=1)
        self._mw.MFC1_setpoint.setText(f'{str(mfc_flow[0])} sL/min')
        self._mw.MFC2_setpoint.setText(f'{str(mfc_flow[1])} sL/min')
        self._mw.MFC3_setpoint.setText(f'{str(mfc_flow[2])} sL/min')
        self._mw.MFC4_setpoint.setText(f'{str(mfc_flow[3])} sL/min')

        # launch calibration
        hist_saving_path = os.path.join(self._mfcw.Folder_LineEdit.text(), self._mfcw.File_LineEdit.text())
        self.start_calibration_timer()
        self._odor_logic.start_flow_calibration(hist_saving_path)

    def abort_MFC_calibration(self):
        """Cancel the MFC calibration"""
        self._odor_logic.stop_flow_measurement()
        self._mw.setDisabled(False)
        self._mfcw.toolButton_abort_calibration.setDisabled(True)
        self._mfcw.toolButton_start_calibration.setDisabled(False)

    def select_folder(self):
        """ Select the folder where to save the graph """
        folder = QFileDialog.getExistingDirectory(self._mfcw, "Select Folder", "E:\DATA")
        if folder:
            self._mfcw.Folder_LineEdit.setText(folder)

# ----------------------------------------------------------------------------------------------------------------------
# helper methods for handling tasks
# ----------------------------------------------------------------------------------------------------------------------

    def disable_enable_GUI(self, disable):
        """
        When initializing a task, make sure all actions from the GUI are disabled. When task is ended, enable again all
        the actions.
        @param disable: (bool) True will disable the GUI, False will enable it after task clean up.
        """
        if disable:
            self.disable_flowcontrol_buttons()
        else:
            self.enable_flowcontrol_buttons()

        self.disable_enable_valves_checkbox(disable)
        self._mw.comboBox_quadrants_config.setDisabled(disable)
        self._mw.doubleSpinBox_quadrant_flow.setDisabled(disable)
        self._mw.Switch_quadrant_pushButton.setDisabled(disable)
        self.disable_enable_odor_pushbuttons()

    def update_GUI(self, init, odor, flow):
        """
        Update the displays of the GUI
        @param init: (bool) indicate whether the task is at the initialization or closing step
        @param odor: (int) indicate which odor was selected
        @param flow: (float) indicate the flow
        """
        if init:
            self._mw.comboBox_quadrants_config.setCurrentIndex(2)
            self._mw.doubleSpinBox_quadrant_flow.setValue(flow)
            for i in range(1, self.odor_number + 1):
                checkbox = getattr(self._mw, f'odor{i}_CheckBox', None)
                if i == odor:
                    checkbox.setChecked(True)
                else:
                    checkbox.setChecked(False)
        else:
            self._mw.comboBox_quadrants_config.setCurrentIndex(0)
            for i in range(1, self.odor_number + 1):
                checkbox = getattr(self._mw, f'odor{i}_CheckBox', None)
                checkbox.setChecked(False)

    def update_prep_timer_from_logic(self, elapsed):
        """
        This method is used from the task to update the GUI (since QTimer cannot be used in that case)
        @param elapsed: (int) indicate elapsed time in s
        """
        self._mw.prep_timer_display.setText(f"{elapsed} sec")

    def update_injection_timer_from_logic(self, elapsed):
        """
        This method is used from the task to update the GUI (since QTimer cannot be used in that case)
        @param elapsed: (int) indicate elapsed time in s
        """
        self._mw.inject_timer_display.setText(f"{elapsed} sec")

