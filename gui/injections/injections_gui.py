# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains a GUI that allows to create an injection sequence.

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

from gui.guibase import GUIBase
from core.connector import Connector
from core.configoption import ConfigOption


class InjectionsWindow(QtWidgets.QMainWindow):
    """ Class defined for the main window (not the module)
    """
    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_merfish.ui')

        # Load it
        super().__init__()
        uic.loadUi(ui_file, self)

        self.show()


class InjectionsGUI(GUIBase):
    """ Main window that allows to create an injection sequence, save it to a file, or load it from file.

    Example config for copy-paste:

    Injections Configurator:
        module.Class: 'injections.injections_gui.InjectionsGUI'
        default_path: 'C:\\Users\\sCMOS-1\\qudi_files\\qudi_injection_parameters'
        connect:
            injections_logic: 'injections_logic'
    """
    # connector to logic module
    injections_logic = Connector(interface='InjectionsLogic')

    # config options
    default_path = ConfigOption('default_path')

    # Signals
    sigAddBuffer = QtCore.Signal(str, int)
    sigDeleteBuffer = QtCore.Signal(QtCore.QModelIndex)
    sigAddProbe = QtCore.Signal(str, int)
    sigDeleteProbe = QtCore.Signal(QtCore.QModelIndex)
    sigAddInjectionStep = QtCore.Signal(str, str, int, int)
    sigAddIncubationTime = QtCore.Signal(str, int)
    sigDeleteHybrStep = QtCore.Signal(QtCore.QModelIndex)
    sigDeletePhotoblStep = QtCore.Signal(QtCore.QModelIndex)

    sigLoadInjections = QtCore.Signal(str)
    sigSaveInjections = QtCore.Signal(str)

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self._injections_logic = None
        self._mw = None

    def on_activate(self):
        """ Required initialization steps.
        """
        self._injections_logic = self.injections_logic()

        self._mw = InjectionsWindow()
        self._mw.centralwidget.hide()  # everything is in dockwidgets

        # initialize list views
        self._mw.buffer_ListView.setModel(self._injections_logic.buffer_list_model)
        self._mw.probe_ListView.setModel(self._injections_logic.probe_position_model)
        self._mw.hybridization_ListView.setModel(self._injections_logic.hybridization_injection_sequence_model)
        self._mw.photobleaching_ListView.setModel(self._injections_logic.photobleaching_injection_sequence_model)
        self._mw.product_ComboBox.setModel(self._injections_logic.buffer_list_model)

        # initialize comboboxes
        self._mw.valve_position_ComboBox.addItems([str(i) for i in range(1, self._injections_logic.num_valve_positions + 1)])
        self._mw.probe_position_ComboBox.addItems([str(i) for i in range(1, self._injections_logic.num_probes + 1)])
        self._mw.procedure_ComboBox.addItems(self._injections_logic.procedures)

        # signals
        # internal signals
        # menubar
        self._mw.close_Action.triggered.connect(self._mw.close)

        # toolbar
        self._mw.load_Action.triggered.connect(self.load_injections_clicked)
        self._mw.save_Action.triggered.connect(self.save_injections_clicked)

        # pushbuttons
        self._mw.add_buffer_PushButton.clicked.connect(self.add_buffer_clicked)
        self._mw.delete_buffer_PushButton.clicked.connect(self.delete_buffer_clicked)

        self._mw.add_probe_PushButton.clicked.connect(self.add_probe_clicked)
        self._mw.delete_probe_PushButton.clicked.connect(self.delete_probe_clicked)

        self._mw.add_injection_PushButton.clicked.connect(self.add_injection_step_clicked)
        self._mw.add_time_PushButton.clicked.connect(self.add_incubation_time_clicked)

        self._mw.delete_hybridization_PushButton.clicked.connect(self.delete_hybr_step_clicked)
        self._mw.delete_photobleaching_PushButton.clicked.connect(self.delete_photobl_step_clicked)

        # signals to logic
        self.sigAddBuffer.connect(self._injections_logic.add_buffer)
        self.sigDeleteBuffer.connect(self._injections_logic.delete_buffer)
        self._mw.delete_all_buffer_PushButton.clicked.connect(self._injections_logic.delete_all_buffer)
        self.sigAddProbe.connect(self._injections_logic.add_probe)
        self.sigDeleteProbe.connect(self._injections_logic.delete_probe)
        self._mw.delete_all_probes_PushButton.clicked.connect(self._injections_logic.delete_all_probes)
        self.sigAddInjectionStep.connect(self._injections_logic.add_injection_step)
        self.sigAddIncubationTime.connect(self._injections_logic.add_incubation_step)
        self.sigDeleteHybrStep.connect(self._injections_logic.delete_hybr_step)
        self._mw.delete_all_hybr_PushButton.clicked.connect(self._injections_logic.delete_hybr_all)
        self.sigDeletePhotoblStep.connect(self._injections_logic.delete_photobl_step)
        self._mw.delete_all_photobl_PushButton.clicked.connect(self._injections_logic.delete_photobl_all)
        self.sigSaveInjections.connect(self._injections_logic.save_injections)
        self.sigLoadInjections.connect(self._injections_logic.load_injections)

        # signals from logic
        self._injections_logic.sigBufferListChanged.connect(self.update_buffer_listview)
        self._injections_logic.sigProbeListChanged.connect(self.update_probe_listview)
        self._injections_logic.sigHybridizationListChanged.connect(self.update_hybridization_listview)
        self._injections_logic.sigPhotobleachingListChanged.connect(self.update_photobleaching_listview)
        self._injections_logic.sigIncompleteLoad.connect(self.show_incomplete_load_warning)

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

# ======================================================================================================================
# Callbacks of pushbuttons on dockwidgets
# ======================================================================================================================

    def add_buffer_clicked(self):
        """ Callback of add buffer pushbutton, inserting an entry into the buffer list """
        buffername = self._mw.buffername_LineEdit.text()
        valve_number = self._mw.valve_position_ComboBox.currentIndex() + 1  # or could use a spinbox instead to work
        # in integer format directly
        if not buffername:
            text = 'Please specify a valid buffer name!'
            QtWidgets.QMessageBox.information(self._mw, 'No buffer name', text, QtWidgets.QMessageBox.Ok)
        else:
            self.sigAddBuffer.emit(buffername, valve_number)
            # move to the next entry in the combobox
            index = self._mw.valve_position_ComboBox.currentIndex()
            self._mw.valve_position_ComboBox.setCurrentIndex(index + 1)
            self._mw.buffername_LineEdit.setText('')

    def delete_buffer_clicked(self):
        """ Callback of delete buffer pushbutton, deleting the currently selected item in the listview.
        (Single select mode) """
        indexes = self._mw.buffer_ListView.selectedIndexes()
        if indexes:
            index = indexes[0]  # single select mode
            self.sigDeleteBuffer.emit(index)

    def add_probe_clicked(self):
        """ Callback of add probe pushbutton, inserting an entry into the buffer list """
        probename = self._mw.probename_LineEdit.text()
        probe_position = self._mw.probe_position_ComboBox.currentIndex() + 1  # or could use a spinbox instead to
        # work in integer format directly
        if not probename:
            text = 'Please specify a valid probe name!'
            QtWidgets.QMessageBox.information(self._mw, 'No probe name', text, QtWidgets.QMessageBox.Ok)
        else:
            self.sigAddProbe.emit(probename, probe_position)
            # move to the next entry in the combobox
            index = self._mw.probe_position_ComboBox.currentIndex()
            self._mw.probe_position_ComboBox.setCurrentIndex(index + 1)
            self._mw.probename_LineEdit.setText('')

    def delete_probe_clicked(self):
        """ Callback of delete probe pushbutton, deleting the currently selected item in the listview.
        (Single select mode) """
        indexes = self._mw.probe_ListView.selectedIndexes()
        if indexes:
            index = indexes[0]  # single select mode
            self.sigDeleteProbe.emit(index)

    def add_injection_step_clicked(self):
        """ Callback of pushbutton inserting an entry into hybridization or photobleaching sequence """
        procedure = self._mw.procedure_ComboBox.currentText()  # 'Hybridization' or 'Photobleaching'
        product = self._mw.product_ComboBox.currentText()
        volume = self._mw.volume_SpinBox.value()
        flowrate = self._mw.flowrate_SpinBox.value()
        self.sigAddInjectionStep.emit(procedure, product, volume, flowrate)

    def add_incubation_time_clicked(self):
        """ Callback of pushbutton inserting an incubation time into hybridization or photobleaching sequence """
        procedure = self._mw.procedure_ComboBox.currentText()  # 'Hybridization' or 'Photobleaching'
        time = self._mw.incubation_time_SpinBox.value()
        self.sigAddIncubationTime.emit(procedure, time)

    def delete_hybr_step_clicked(self):
        """ Callback of pushbutton deleting an entry (single select mode) from the hybridization manager listview """
        indexes = self._mw.hybridization_ListView.selectedIndexes()
        if indexes:
            index = indexes[0]  # single select mode
            self.sigDeleteHybrStep.emit(index)

    def delete_photobl_step_clicked(self):
        """ Callback of pushbutton deleting an entry (single select mode) from the photobleaching manager listview """
        indexes = self._mw.photobleaching_ListView.selectedIndexes()
        if indexes:
            index = indexes[0]  # single select mode
            self.sigDeletePhotoblStep.emit(index)

# ======================================================================================================================
# Callbacks of signals sent from logic to update the listview contents
# ======================================================================================================================

    def update_buffer_listview(self):
        """ Callback of a signal sent from logic (sigBufferListChanged) notifying that the listview model has
        changed and the listview can now be updated.

        Note that it is not possible to send the layoutChanged (built-in) signal over threads. This is why the custom
        signal establishes the communication over threads and the signal layoutChanged is emitted here.
        """
        self._injections_logic.buffer_list_model.layoutAboutToBeChanged.emit()
        self._injections_logic.buffer_list_model.layoutChanged.emit()
        # for the delete entry case, if one row is selected then it will be unselected and deleted
        indexes = self._mw.buffer_ListView.selectedIndexes()
        if indexes:
            self._mw.buffer_ListView.clearSelection()

    def update_probe_listview(self):
        """ Callback of a signal sent from logic (sigProbeListChanged) notifying that the listview model has
        changed and the listview can now be updated.

        Note that it is not possible to send the layoutChanged (built-in) signal over threads. This is why the custom
        signal establishes the communication over threads and the layoutChanged is emitted here.
        """
        self._injections_logic.probe_position_model.layoutChanged.emit()
        # for the delete entry case, if one row is selected then it will be unselected and deleted
        indexes = self._mw.probe_ListView.selectedIndexes()
        if indexes:
            self._mw.probe_ListView.clearSelection()

    def update_hybridization_listview(self):
        """ Callback of a signal sent from logic (sigHybridizationListChanged) notifying that the listview
        model has changed and the listview can now be updated.

        Note that it is not possible to send the layoutChanged (built-in) signal over threads. This is why the custom
        signal establishes the communication over threads and the layoutChanged is emitted here.
        """
        self._injections_logic.hybridization_injection_sequence_model.layoutChanged.emit()
        # for the delete entry case, if one row is selected then it will be unselected and deleted
        indexes = self._mw.hybridization_ListView.selectedIndexes()
        if indexes:
            self._mw.hybridization_ListView.clearSelection()

    def update_photobleaching_listview(self):
        """ Callback of a signal sent from logic (sigPhotobleachingListChanged) notifying that the listview
        model has changed and the listview can now be updated.

        Note that it is not possible to send the layoutChanged (built-in) signal over threads. This is why the custom
        signal establishes the communication over threads and the layoutChanged is emitted here.
        """
        self._injections_logic.photobleaching_injection_sequence_model.layoutChanged.emit()
        # # for the delete entry case, if one row is selected then it will be unselected and deleted
        indexes = self._mw.photobleaching_ListView.selectedIndexes()
        if indexes:
            self._mw.photobleaching_ListView.clearSelection()

# ======================================================================================================================
# Callbacks of toolbar actions
# ======================================================================================================================

    def load_injections_clicked(self):
        """ Callback of the toolbutton load injections. Opens a dialog to select a file and hands the path
        over to the logic where the data is loaded.
        """
        data_directory = self.default_path  # default location to look for the file
        this_file = QtWidgets.QFileDialog.getOpenFileName(self._mw, 'Load injections', data_directory, 'yml files ('
                                                                                                       '*.yml)')[0]
        if this_file:
            self.sigLoadInjections.emit(this_file)

    def save_injections_clicked(self):
        """ Callback of the toolbutton save injections. Opens a dialog to select a file or a path where
        the data should be saved. The path is handed over to the logic module where data saving is managed. """
        data_directory = self.default_path
        this_file = QtWidgets.QFileDialog.getSaveFileName(self._mw,
                                                          'Save injection sequence',
                                                          data_directory,
                                                          'yml files (*.yml)')[0]
        if this_file:
            self.sigSaveInjections.emit(this_file)

    def show_incomplete_load_warning(self):
        """ Callback of the sigIncompleteLoad signal from logic.
         Shows a warning dialog box if selected document could not be loaded.
         """
        QtWidgets.QMessageBox.warning(self._mw, 'Load injections', 'Injections not loaded. Document is incomplete.', QtWidgets.QMessageBox.Ok)
