# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains a GUI that allows to control the fluidics devices
(valve positioners, pump, flow rate measurement, probes positioning).

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
import os
from qtpy import QtCore
from qtpy import QtGui
from qtpy import QtWidgets
from qtpy import uic
from functools import partial
import numpy as np

from gui.guibase import GUIBase
from core.connector import Connector
from core.configoption import ConfigOption


# ======================================================================================================================
# Dialog and main windows
# ======================================================================================================================

class Position1SettingDialog(QtWidgets.QDialog):
    """ Create the SettingsDialog window, based on the corresponding *.ui file.
    This dialog allows to define the origin of the probe positining system, i.e. the position of the first probe. """

    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_position1_settings.ui')

        # Load it
        super(Position1SettingDialog, self).__init__()
        uic.loadUi(ui_file, self)


class FluidicsWindow(QtWidgets.QMainWindow):
    """ Class defined for the main window (not the module).
    """
    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_fluidics.ui')

        # Load it
        super().__init__()
        uic.loadUi(ui_file, self)
        self.show()


class FluidicsWindowCE(FluidicsWindow):
    """ Fluidics Window child class that reimplements the close event.
    The aim is to stop the continuously running modes such as the flowrate measurement mode when the window is closed.
    """
    def __init__(self, close_function):
        super().__init__()
        self.close_function = close_function

    def closeEvent(self, event):
        self.close_function()
        event.accept()

# ======================================================================================================================
# GUI class
# ======================================================================================================================


class FluidicsGUI(GUIBase):
    """ Class for the GUI that allows to control the fluidics devices.

    Example config for copy-paste:

    Fluidics Control:
        module.Class: 'fluidics.fluidics_gui.FluidicsGUI'
        pos1_x_default: 12.0
        pos1_y_default: 4.5
        pos1_z_default: 89.0
        connect:
            valve_logic: 'valve_logic'
            flowcontrol_logic: 'flowcontrol_logic'
            positioning_logic: 'positioning_logic'
    """

    # connector to logic modules
    valve_logic = Connector(interface='ValveLogic')
    flowcontrol_logic = Connector(interface='FlowcontrolLogic')
    positioning_logic = Connector(interface='PositioningLogic')

    # config options
    pos1_x_default = ConfigOption('pos1_x_default', 0)
    pos1_y_default = ConfigOption('pos1_y_default', 0)
    pos1_z_default = ConfigOption('pos1_z_default', 0)

    # Signals
    # signals for valve settings
    sigSetValvePosition = QtCore.Signal(str, int)

    # signals for flowcontrol actions
    sigSetPressure = QtCore.Signal(float)
    sigStartFlowMeasure = QtCore.Signal()
    sigStopFlowMeasure = QtCore.Signal()
    sigStartVolumeMeasurement = QtCore.Signal(int, int)
    sigStopVolumeMeasurement = QtCore.Signal()
    sigStartRinsing = QtCore.Signal(int)
    sigStopRinsing = QtCore.Signal()

    # signals for positioning actions
    sigSetPos1 = QtCore.Signal(tuple)
    sigMoveStage = QtCore.Signal(tuple)
    sigMoveToTarget = QtCore.Signal(int)
    sigStopMovement = QtCore.Signal()

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self._valve_logic = None
        self._flow_logic = None
        self._positioning_logic = None
        self._mw = None

    def on_activate(self):
        """ Required initialization steps.
        """
        # connectors to the logic
        self._valve_logic = self.valve_logic()
        self._flow_logic = self.flowcontrol_logic()
        self._positioning_logic = self.positioning_logic()

        # create an instance of the Main Window
        self._mw = FluidicsWindowCE(self.close_function)
        self._mw.centralwidget.hide()  # everything is in dockwidgets

        # menu actions
        self._mw.close_MenuAction.triggered.connect(self._mw.close)

        # initialize settings dialog
        self.init_position1_settings_ui()

        # initialize the valve control dockwidget
        self.init_valve_control()

        # initialize the flow control dockwidget and its toolbar
        self.init_flowcontrol()

        # initialize the positioning dockwidget and its toolbar
        self.init_positioning()

        # open a message box to validate that needle cover has been removed
        text = 'Please check if needle cover has been removed!'
        QtWidgets.QMessageBox.information(self._mw, 'Safety check', text, QtWidgets.QMessageBox.Ok)

    def on_deactivate(self):
        """ Deinitialisation performed during deactivation of the module.
        """
        self._mw.close()

    def show(self):
        """Make window visible and put it above all other windows.
        """
        QtWidgets.QMainWindow.show(self._mw)
        self._mw.activateWindow()
        self._mw.raise_()

# ----------------------------------------------------------------------------------------------------------------------
# Methods to initialize the dockwidgets and their toolbars
# ----------------------------------------------------------------------------------------------------------------------

    def init_valve_control(self):
        """ This method initialized the valve control dockwidget.
        It creates the widgets in the valve dockwidget depending on the number of valves specified in hardware config.
        Establishes signal-slot connections.
        """
        # create widgets according to number of valves configured.
        self.valve_Labels = []
        self.valve_ComboBoxes = []
        for i in range(len(self._valve_logic.valve_names)):
            valve_label = QtWidgets.QLabel(self._valve_logic.valve_names[i])
            self.valve_Labels.append(valve_label)
            valve_combobox = QtWidgets.QComboBox()
            self.valve_ComboBoxes.append(valve_combobox)
            if not self._valve_logic.valve_positions:
                self.valve_ComboBoxes[i].addItems([str(n+1) for n in range(self._valve_logic.max_positions[i])])
            else:  # using the optional list of valve positions containing information where each valve port goes to
                self.valve_ComboBoxes[i].addItems(self._valve_logic.valve_positions[i])
            self._mw.formLayout.addRow(self.valve_Labels[i], self.valve_ComboBoxes[i])

            # set current index according to actual position of valve on start
            valve_combobox.setCurrentIndex(self._valve_logic.get_valve_position(self._valve_logic.valve_IDs[i])-1)

        # internal signals
        for i in range(len(self.valve_ComboBoxes)):
            self.valve_ComboBoxes[i].activated.connect(partial(self.change_valve_position, i))

        # signals to logic
        self.sigSetValvePosition.connect(self._valve_logic.set_valve_position)

        # signals from logic
        self._valve_logic.sigPositionChanged.connect(self.update_combobox_index)
        self._valve_logic.sigDisableValvePositioning.connect(self.disable_valve_positioning)
        self._valve_logic.sigEnableValvePositioning.connect(self.enable_valve_positioning)

    def init_flowcontrol(self):
        """ This method initializes the flowcontrol dockwidget.
        It initializes the line plot and sets an adapted text on the labels on the flowcontrol dockwidget.
        It establishes the signal-slot connections for the toolbar actions.
        """
        # initialize the line plot
        # data for flowrate plot initialization
        self.t_data = []
        self.flowrate_data = []
        self.pressure_data = []

        # create a reference to the line object (this is returned when calling plot method of pg.PlotWidget)
        self._mw.flowrate_PlotWidget.setLabel('left', 'Flowrate', units='ul/min')
        # self._mw.flowrate_PlotWidget.setLabel('left', 'Pressure', units='mbar')
        self._mw.flowrate_PlotWidget.setLabel('bottom', 'Time', units='s')
        self._mw.flowrate_PlotWidget.addLegend()
        self._flowrate_timetrace = self._mw.flowrate_PlotWidget.plot(self.t_data, self.flowrate_data, pen=(255, 0, 0), name='flowrate')
        self._pressure_timetrace = self._mw.flowrate_PlotWidget.plot(self.t_data, self.pressure_data, pen=(0, 0, 255), name='pressure')

        # set text to unit labels
        self._mw.pressure_unit_Label.setText(self._flow_logic.get_pressure_unit()[0])  # first element of the returned list. For multiplexing case, more widgets would be created and another list element affected.
        self._mw.pressure_unit_Label2.setText(self._flow_logic.get_pressure_unit()[0])
        self._mw.flowrate_unit_Label.setText(self._flow_logic.get_flowrate_unit()[0])

        # toolbar actions: internal signals
        self._mw.set_pressure_Action.triggered.connect(self.set_pressure_clicked)
        self._mw.start_flow_measurement_Action.triggered.connect(self.measure_flow_clicked)
        self._mw.volume_measurement_Action.triggered.connect(self.measure_volume_clicked)
        self._mw.rinsing_Action.triggered.connect(self.start_rinsing_clicked)

        # signals to logic
        self.sigSetPressure.connect(self._flow_logic.set_pressure)
        self.sigStartFlowMeasure.connect(self._flow_logic.start_flow_measurement)
        self.sigStopFlowMeasure.connect(self._flow_logic.stop_flow_measurement)
        self.sigStartVolumeMeasurement.connect(self._flow_logic.start_volume_measurement)
        self.sigStopVolumeMeasurement.connect(self._flow_logic.stop_volume_measurement)
        self.sigStartRinsing.connect(self._flow_logic.start_rinsing)
        self.sigStopRinsing.connect(self._flow_logic.stop_rinsing)

        # signals from logic
        self._flow_logic.sigUpdateFlowMeasurement.connect(self.update_flowrate_and_pressure)
        self._flow_logic.sigUpdatePressureSetpoint.connect(self.update_pressure_setpoint)
        self._flow_logic.sigUpdateVolumeMeasurement.connect(self.update_volume_and_time)
        self._flow_logic.sigTargetVolumeReached.connect(self.reset_volume_measurement_button)
        self._flow_logic.sigRinsingFinished.connect(self.reset_rinsing_action_button)
        self._flow_logic.sigDisableFlowActions.connect(self.disable_flowcontrol_buttons)
        self._flow_logic.sigEnableFlowActions.connect(self.enable_flowcontrol_buttons)

    def init_positioning(self):
        """ This method initializes the positioning dockwidget.
        It initializes the indicators with the specified axis labels and displays the current stage position.
        It establishes the signal-slot connections for the toolbar actions.
        """
        if self._positioning_logic.origin is None:
            self._mw.go_to_position_Action.setDisabled(True)

        # initialize indicators
        self._mw.first_axis_Label.setText(self._positioning_logic.first_axis_label)
        self._mw.second_axis_Label.setText(self._positioning_logic.second_axis_label)
        self._mw.third_axis_Label.setText(self._positioning_logic.third_axis_label)
        stage_position = self._positioning_logic.get_position()
        self._mw.x_axis_position_LineEdit.setText('{:.3f}'.format(stage_position[0]))
        self._mw.y_axis_position_LineEdit.setText('{:.3f}'.format(stage_position[1]))
        self._mw.z_axis_position_LineEdit.setText('{:.3f}'.format(stage_position[2]))

        self._mw.probe_position_LineEdit.setText('Please calibrate !')

        # initialize spinboxes depending on connected hardware
        constraints = self._positioning_logic.get_hardware_constraints()

        x_min = constraints['x']['pos_min']
        x_max = constraints['x']['pos_max']
        y_min = constraints['y']['pos_min']
        y_max = constraints['y']['pos_max']
        z_min = constraints['z']['pos_min']
        z_max = constraints['z']['pos_max']

        self._mw.x_axis_position_DSpinBox.setMinimum(x_min)
        self._mw.x_axis_position_DSpinBox.setMaximum(x_max)

        self._mw.y_axis_position_DSpinBox.setMinimum(y_min)
        self._mw.y_axis_position_DSpinBox.setMaximum(y_max)

        self._mw.z_axis_position_DSpinBox.setMinimum(z_min)
        self._mw.z_axis_position_DSpinBox.setMaximum(z_max)

        probe_max = self._positioning_logic.num_probes
        self._mw.target_probe_position_SpinBox.setMaximum(probe_max)

        # toolbar actions
        self._mw.move_stage_Action.triggered.connect(self.move_stage_clicked)
        self._mw.set_position1_Action.triggered.connect(self.open_calibration_settings)
        self._mw.go_to_position_Action.triggered.connect(self.go_to_position_clicked)

        # signals to logic
        self.sigMoveStage.connect(self._positioning_logic.start_move_stage)
        self.sigMoveToTarget.connect(self._positioning_logic.start_move_to_target)
        self.sigSetPos1.connect(self._positioning_logic.set_origin)
        self.sigStopMovement.connect(self._positioning_logic.abort_movement)

        # signals from logic
        self._positioning_logic.sigUpdatePosition.connect(self.update_stage_position)
        self._positioning_logic.sigStageMoved.connect(self.stage_movement_finished)
        self._positioning_logic.sigOriginDefined.connect(self.origin_defined)
        self._positioning_logic.sigStageMovedToTarget.connect(self.update_target_position)
        self._positioning_logic.sigStageStopped.connect(self.stage_stopped)
        self._positioning_logic.sigDisablePositioningActions.connect(self.disable_positioning_actions)
        self._positioning_logic.sigEnablePositioningActions.connect(self.enable_positioning_actions)

# ----------------------------------------------------------------------------------------------------------------------
# Methods belonging to the position1 settings window
# ----------------------------------------------------------------------------------------------------------------------

    def init_position1_settings_ui(self):
        """ Definition, configuration and initialization of the settings dialog that allows to calibrate the position
        of the first probe (= position 1).
        """
        # Create the settings window
        self._pos1_sd = Position1SettingDialog()
        # update the labels according to connected hardware
        self._pos1_sd.label.setText(self._positioning_logic.first_axis_label)
        self._pos1_sd.label_2.setText(self._positioning_logic.second_axis_label)
        self._pos1_sd.label_3.setText(self._positioning_logic.third_axis_label)

        # Connect the action of the settings window with the code:
        self._pos1_sd.accepted.connect(self.set_position1)  # ok button
        self._pos1_sd.rejected.connect(self.sd_set_default_values)  # cancel button

        # start with default values
        self.sd_set_default_values()

    def set_position1(self):
        """ Callback of the settings dialog ok button.
        Transfers the new defined coordinates of the position 1 to the logic module."""
        x_pos = self._pos1_sd.x_pos_DSpinBox.value()
        y_pos = self._pos1_sd.y_pos_DSpinBox.value()
        z_pos = self._pos1_sd.z_pos_DSpinBox.value()
        position1 = (x_pos, y_pos, z_pos)
        self.sigSetPos1.emit(position1)

    def sd_set_default_values(self):
        """ Callback of the settings dialog cancel button.
        Resets default values. """
        self._pos1_sd.x_pos_DSpinBox.setValue(self.pos1_x_default)
        self._pos1_sd.y_pos_DSpinBox.setValue(self.pos1_y_default)
        self._pos1_sd.z_pos_DSpinBox.setValue(self.pos1_z_default)
# end of position1 settings window related methods ---------------------------------------------------------------------

# ----------------------------------------------------------------------------------------------------------------------
# Slots related to the positioning
# ----------------------------------------------------------------------------------------------------------------------

# Methods for stage movement--------------------------------------------------------------------------------------------
    @QtCore.Slot()
    def move_stage_clicked(self):
        """ Callback of move_stage toolbutton. Handles the state of the toolbutton and sends a signal to the logic
        to either do a movement or to stop it depending on the current state.
        """
        if self._positioning_logic.moving:  # stage already in movement, will be stopped by clicking the toolbutton
            self._mw.move_stage_Action.setText('Move Stage')
            if self._positioning_logic.origin is not None:  # allow access to go to target toolbutton when position 1 has been defined
                self._mw.go_to_position_Action.setDisabled(False)
            self.sigStopMovement.emit()
        else:
            self._mw.move_stage_Action.setText('Stop moving')
            self._mw.go_to_position_Action.setDisabled(True)
            x_pos = self._mw.x_axis_position_DSpinBox.value()
            y_pos = self._mw.y_axis_position_DSpinBox.value()
            z_pos = self._mw.z_axis_position_DSpinBox.value()
            position = (x_pos, y_pos, z_pos)
            self.sigMoveStage.emit(position)

    @QtCore.Slot()
    def go_to_position_clicked(self):
        """ Callback of go_to_position toolbutton. Handles the state of the toolbutton and sends a signal to the logic
        to either do a movement to a target position (position of a probe) or to stop the movement depending on the
        current state.
        """
        if self._positioning_logic.moving:  # stage already in movement
            self._mw.go_to_position_Action.setText('Go to Target')
            self._mw.move_stage_Action.setDisabled(False)
            self.sigStopMovement.emit()
        else:
            self._mw.go_to_position_Action.setText('Stop moving')
            self._mw.move_stage_Action.setDisabled(True)
            position = self._mw.target_probe_position_SpinBox.value()  # position is an integer
            self.sigMoveToTarget.emit(position)

    @QtCore.Slot(tuple)
    def stage_movement_finished(self, position):
        """ Callback of sigStageMoved in logic module. Movement is finished and toolbutton state needs to be reset.
        Updates the current position indicators.

        :param: tuple (float, float, float) position: current position of the stage
        """
        self._mw.move_stage_Action.setChecked(False)
        self._mw.move_stage_Action.setText('Move Stage')
        if self._positioning_logic.origin is not None:
            self._mw.go_to_position_Action.setDisabled(False)
        self.update_stage_position(position)

    @QtCore.Slot(tuple)
    def stage_stopped(self, position):
        """ Callback of sigStageStopped in logic module. Movement has been aborted by user.
        Toolbutton state needs to be reset. Updates the current position indicators (stage and target).

        :param: tuple (float, float, float) position: current position of the stage
        """
        self._mw.move_stage_Action.setDisabled(False)
        self._mw.move_stage_Action.setText('Move Stage')
        self._mw.move_stage_Action.setChecked(False)
        if self._positioning_logic.origin is not None:
            self._mw.go_to_position_Action.setDisabled(False)
            self._mw.go_to_position_Action.setText('Go to Target')
            self._mw.go_to_position_Action.setChecked(False)
        self.update_stage_position(position)

# Methods for to update the position and target indicators -------------------------------------------------------------
    @QtCore.Slot(tuple)
    def update_stage_position(self, position):
        """ Callback of sigUpdatePosition in logic module. This updates the current position indicators.

        :param: tuple (float, float, float) position: current position of the stage
        """
        self._mw.x_axis_position_LineEdit.setText('{:.3f}'.format(position[0]))
        self._mw.y_axis_position_LineEdit.setText('{:.3f}'.format(position[1]))
        self._mw.z_axis_position_LineEdit.setText('{:.3f}'.format(position[2]))
        # set the current position of the injections probe to its indicator if the stage coordinates correspond to a position
        xy_pos = (position[0], position[1])
        if xy_pos in self._positioning_logic._probe_xy_position_dict.keys():
            self._mw.probe_position_LineEdit.setText(str(self._positioning_logic._probe_xy_position_dict[xy_pos]))
        elif self._positioning_logic.origin is None:
            pass  # keep the default text if position1 is not yet defined
        else:
            self._mw.probe_position_LineEdit.setText('Not at a probe XY position')

    @QtCore.Slot(tuple, int)
    def update_target_position(self, position, target_position):
        """ Callback of sigStageMovedToTarget in logic module. Movement is finished and toolbutton state needs to be reset.
        Update the current position indicators (stage and target).

        :param: tuple (float, float, float) position: current position of the stage
        :param: int target_position: current target position (=number of the probe) corresponding to the stage position
        """
        self._mw.go_to_position_Action.setChecked(False)
        self._mw.go_to_position_Action.setText('Go to Target')
        self._mw.move_stage_Action.setDisabled(False)
        # set the setpoint and the indicator widgets to the current position accordingly to the target
        self._mw.x_axis_position_DSpinBox.setValue(position[0])
        self._mw.y_axis_position_DSpinBox.setValue(position[1])
        self._mw.z_axis_position_DSpinBox.setValue(position[2])
        self._mw.x_axis_position_LineEdit.setText('{:.3f}'.format(position[0]))
        self._mw.y_axis_position_LineEdit.setText('{:.3f}'.format(position[1]))
        self._mw.z_axis_position_LineEdit.setText('{:.3f}'.format(position[2]))
        self._mw.probe_position_LineEdit.setText(str(target_position))

# Methods related to the definition of position 1 ----------------------------------------------------------------------
    @QtCore.Slot()
    def open_calibration_settings(self):
        """ Callback of set_position1 toolbutton. Opens a dialog to set position 1 as origin. """
        self._pos1_sd.exec_()

    @QtCore.Slot()
    def origin_defined(self):
        """ Callback of the signal sigOriginDefined in the logic module. Enables the functionality that can only be used
        when an origin is defined (addressing stage positions via the probe number).
        """
        self._mw.go_to_position_Action.setDisabled(False)
        position = self._positioning_logic.get_position()
        xy_pos = (position[0], position[1])
        if xy_pos in self._positioning_logic._probe_xy_position_dict.keys():
            self._mw.probe_position_LineEdit.setText(str(self._positioning_logic._probe_xy_position_dict[xy_pos]))
        else:
            self._mw.probe_position_LineEdit.setText('Not at a probe XY position')

# Disable/Enable user interface actions --------------------------------------------------------------------------------
    @QtCore.Slot()
    def disable_positioning_actions(self):
        """ Callback of the signal sigDisablePositioningActions in the logic module. Disables positioning toolbuttons.
        """
        self._mw.move_stage_Action.setDisabled(True)
        self._mw.set_position1_Action.setDisabled(True)
        self._mw.go_to_position_Action.setDisabled(True)

    @QtCore.Slot()
    def enable_positioning_actions(self):
        """ Callback of the signal sigEnablePositioningActions in the logic module. Enables positioning toolbuttons.
        """
        self._mw.move_stage_Action.setDisabled(False)
        self._mw.set_position1_Action.setDisabled(False)
        if self._positioning_logic.origin is not None:
            self._mw.go_to_position_Action.setDisabled(False)

# ----------------------------------------------------------------------------------------------------------------------
# Slots related to the flowcontrol
# ----------------------------------------------------------------------------------------------------------------------

    @QtCore.Slot()
    def set_pressure_clicked(self):
        """ Callback of the set pressure toolbutton. Retrieves the setpoint value from the spinbox and sends a
        signal to the logic.
        """
        pressure = self._mw.pressure_setpoint_DSpinBox.value()
        self.sigSetPressure.emit(pressure)

    @QtCore.Slot(float)
    def update_pressure_setpoint(self, pressure):
        """ Callback of a signal emitted from logic updating the pressure setpoint display.

        :param float pressure: current pressure value retrieved from hardware """
        self._mw.pressure_setpoint_DSpinBox.setValue(pressure)

    @QtCore.Slot()
    def measure_flow_clicked(self):
        """ Callback of start flow measurement toolbutton. Handles the toolbutton state and initiates the start / stop
        of flowrate and pressure measurements.
        """
        if self._flow_logic.measuring_flowrate:  # measurement already running
            self._mw.start_flow_measurement_Action.setText('Start flowrate measurement')
            self.sigStopFlowMeasure.emit()
        else:
            self._mw.start_flow_measurement_Action.setText('Stop flowrate measurement')
            self.t_data = []
            self.flowrate_data = []
            self.pressure_data = []
            self.sigStartFlowMeasure.emit()

    @QtCore.Slot(list, list)
    def update_flowrate_and_pressure(self, pressure, flowrate):
        """ Callback of a signal emitted from logic informing the GUI about the new pressure and flowrate values.

        :param float pressure: current pressure value retrieved from hardware
        :param float flowrate: current flowrate retrieved from hardware
        """
        self._mw.pressure_LineEdit.setText('{:.2f}'.format(pressure[0]))
        self._mw.flowrate_LineEdit.setText('{:.2f}'.format(flowrate[0]))
        self.update_pressure_and_flowrate_timetrace(pressure[0], flowrate[0])

    def update_pressure_and_flowrate_timetrace(self, pressure, flowrate):
        """ Add a new data point to the pressure and flowrate timetraces.

        :param float pressure: current pressure value retrieved from hardware
        :param float flowrate: current flowrate retrieved from hardware
        """
        if len(self.flowrate_data) < 100:
            self.t_data.append(len(self.t_data))
            self.flowrate_data.append(flowrate)
            self.pressure_data.append(pressure)

        else:
            self.t_data[:-1] = self.t_data[1:]
            self.t_data[-1] += 1
            self.flowrate_data[:-1] = self.flowrate_data[1:]  # shift data one position to the left
            self.flowrate_data[-1] = flowrate
            self.pressure_data[:-1] = self.pressure_data[1:]  # shift data one position to the left
            self.pressure_data[-1] = pressure

        self._flowrate_timetrace.setData(self.t_data, self.flowrate_data)  # t axis running with time
        self._pressure_timetrace.setData(self.t_data, self.pressure_data)

    @QtCore.Slot()
    def measure_volume_clicked(self):
        """ Callback of start / stop volume measurement toolbutton.
        Handles the toolbutton state and initiates the start / stop of volume measurement.
        """
        if self._flow_logic.measuring_volume:  # volume measurement already running
            self._mw.volume_measurement_Action.setText('Start volume measurement')
            self.sigStopVolumeMeasurement.emit()
        else:
            target_volume = 500000  # np.inf  --> caused problems because the value is sometimes large negative !
            sampling_interval = 1  # in seconds, fixed for measurement started from GUI
            self._mw.volume_measurement_Action.setText('Stop volume measurement')
            self.sigStartVolumeMeasurement.emit(target_volume, sampling_interval)

    @QtCore.Slot(int, int)
    def update_volume_and_time(self, total_volume, time):
        """ Callback of a signal emitted from logic informing the GUI about the new total volume
        and time since start of the measurement.

        :param: int total_volume: summed up volume already injected, rounded to integer format
        :param: int time: total time in seconds since start of the volume count
        """
        self._mw.volume_LineEdit.setText(str(total_volume))
        self._mw.time_since_start_LineEdit.setText(str(time))  # change formatting: maybe in min:sec when > 60 s ??

    @QtCore.Slot()
    def reset_volume_measurement_button(self):
        """ Callback of signal sigTargetVolumeReached from logic. Reset the action button to initial state
        when volume measurement is stopped because target volume was reached.
        """
        self._mw.volume_measurement_Action.setText('Start volume measurement')
        self._mw.volume_measurement_Action.setChecked(False)
    # this method might not be needed as we set the target volume to infinity when volume count is started by gui

    @QtCore.Slot()
    def start_rinsing_clicked(self):
        """ Callback of start / stop rinsing toolbutton.
        Handles the toolbutton state and initiates the start / stop of needle rinsing.
        Sets also the needle rinsing valve to the correct position before starting a rinsing step.
        The valve positioning is hardcoded. Attention if another experimental setup is configured differently.
        Then the rinsing valve and the rinsing position need to be added to a config.
        """
        if self._flow_logic.rinsing_enabled:
            self._mw.rinsing_Action.setText('Start rinsing')
            self._mw.rinsing_time_SpinBox.setDisabled(False)
            self.sigStopRinsing.emit()
        else:
            # make sure to set the RT rinsing valve to the correct position (pos 1)
            if self._valve_logic.get_valve_position('b') != 1:
                self._valve_logic.set_valve_position('b', 1)  # hardcoded version - needs modification in case another system is set up differently (i.e. if RT rinsing valve not as valve 'b', rinse needle not at pos 1)
                self._valve_logic.wait_for_idle()

            # handle the start of rinsing
            rinsing_time = self._mw.rinsing_time_SpinBox.value()
            self._mw.rinsing_time_SpinBox.setDisabled(True)  # do not allow to modify time when rinsing starts
            self._mw.rinsing_Action.setText('Stop rinsing')
            self.sigStartRinsing.emit(rinsing_time)

    @QtCore.Slot()
    def reset_rinsing_action_button(self):
        """ Callback of signal sigRinsingFinished from logic. Reset the action button to initial state
        when rinsing is finished because target duration has elapsed. """
        self._mw.rinsing_Action.setText('Start rinsing')
        self._mw.rinsing_Action.setChecked(False)
        self._mw.rinsing_time_SpinBox.setDisabled(False)

# Disable/Enable user interface actions --------------------------------------------------------------------------------
    @QtCore.Slot()
    def disable_flowcontrol_buttons(self):
        """ Disables set pressure toolbutton, start volume measurement toolbutton and start rinsing toolbutton,
        to be used for example during tasks. Pressure and flowrate measurement is still allowed because it can
        be useful during tasks and does not interfere. """
        self._mw.set_pressure_Action.setDisabled(True)
        self._mw.volume_measurement_Action.setDisabled(True)
        self._mw.rinsing_Action.setDisabled(True)

    @QtCore.Slot()
    def enable_flowcontrol_buttons(self):
        """ Enables flowcontrol toolbuttons. """
        self._mw.set_pressure_Action.setDisabled(False)
        self._mw.volume_measurement_Action.setDisabled(False)
        self._mw.rinsing_Action.setDisabled(False)

# ----------------------------------------------------------------------------------------------------------------------
# Slots related to the valve control dockwidget
# ----------------------------------------------------------------------------------------------------------------------

    @QtCore.Slot(int)
    def change_valve_position(self, valve_num):
        """ Callback of the valve comboboxes. Retrieves the target position and emits a signal containing the valve_id
        and the target position.

        :param: int valve_num: index of the element in the valve_ComboBoxes list. Element 0 corresponds to valve_id 'a', etc.
        """
        index = self.valve_ComboBoxes[valve_num].currentIndex()
        valve_pos = index + 1  # zero indexing
        valve_id = self._valve_logic.valve_IDs[valve_num]
        self.sigSetValvePosition.emit(valve_id, valve_pos)

    @QtCore.Slot(str, int)
    def update_combobox_index(self, valve_ID, valve_pos):
        """ Callback of the signal sent from the logic indicating that the position of a valve controller has been
        changed. Changes the GUI accordingly.

        :param str valve_ID: letter designating the valve_id in the daisychain (see hardware modules), 'a', 'b', 'c', ..
        :param int valve_pos: current position of the valve at valve_ID
        """
        if valve_ID == 'a':
            self.valve_ComboBoxes[0].setCurrentIndex(valve_pos-1)  # zero indexing
        elif valve_ID == 'b':
            self.valve_ComboBoxes[1].setCurrentIndex(valve_pos-1)
        elif valve_ID == 'c':
            self.valve_ComboBoxes[2].setCurrentIndex(valve_pos-1)
        elif valve_ID == 'd':
            self.valve_ComboBoxes[3].setCurrentIndex(valve_pos-1)
        elif valve_ID == 'e':
            self.valve_ComboBoxes[4].setCurrentIndex(valve_pos - 1)
        # extend if more valve positioners needed. Or define a mapping from letters to elements in valve_ComboBoxes list.
        else:
            pass

# Disable/Enable user interface actions --------------------------------------------------------------------------------
    @QtCore.Slot()
    def disable_valve_positioning(self):
        """ Disables the valve comboboxes, to be used for example during tasks. """
        for i in range(len(self.valve_ComboBoxes)):
            self.valve_ComboBoxes[i].setDisabled(True)

    @QtCore.Slot()
    def enable_valve_positioning(self):
        """ Enables the valve comboboxes. """
        for i in range(len(self.valve_ComboBoxes)):
            self.valve_ComboBoxes[i].setDisabled(False)

# ----------------------------------------------------------------------------------------------------------------------
# Close function: Stop all continuous actions.
# ----------------------------------------------------------------------------------------------------------------------

    def close_function(self):
        """ This method serves as a reimplementation of the close event. Continuous measurement modes are stopped
        when the main window is closed. """
        if self._flow_logic.measuring_flowrate:
            self.sigStopFlowMeasure.emit()
            self._mw.start_flow_measurement_Action.setText('Start flowrate measurement')
            self._mw.start_flow_measurement_Action.setChecked(False)
        if self._flow_logic.measuring_volume:
            self.sigStopVolumeMeasurement.emit()
            self._mw.volume_measurement_Action.setText('Start volume measurement')
            self._mw.volume_measurement_Action.setChecked(False)
        if self._flow_logic.rinsing_enabled:
            self.sigStopRinsing.emit()
            self._mw.rinsing_Action.setText('Start rinsing')
            self._mw.rinsing_Action.setChecked(False)
            self._mw.rinsing_time_SpinBox.setDisabled(False)
