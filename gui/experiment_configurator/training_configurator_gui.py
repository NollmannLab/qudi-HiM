# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains a GUI that allows to create an experiment config file for a Task for the FlyArena.

An extension to Qudi.

@author: F. Barho - later modifications JB Fiche
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


class ExpConfiguratorWindow(QtWidgets.QMainWindow):
    """ Class defined for the main window (not the module).

    """
    def __init__(self, ui_filename):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, ui_filename)

        # Load it
        super().__init__()
        uic.loadUi(ui_file, self)

        self.show()


class ExpConfiguratorGUI(GUIBase):
    """ GUI module that helps the user to define the configuration file for the different types of experiments (=tasks).

    Example config for copy-paste:

    Experiment Configurator:
        module.Class: 'experiment_configurator.exp_configurator_gui.ExpConfiguratorGUI'
        default_location_qudi_files: '/home/barho/qudi_files'
        connect:
            exp_config_logic: 'exp_config_logic'
    """
    # define the default language option as English (to make sure all float have a point as a separator)
    QtCore.QLocale.setDefault(QtCore.QLocale("English"))

    # connector to logic module
    exp_logic = Connector(interface='ExpConfigLogic')

    # config options
    default_location = ConfigOption('default_location_qudi_files', missing='warn')
    # serves as a path stem to default locations where experimental configurations are saved, and where roi lists and
    # injections lists are loaded
    _ui_window_filename = ConfigOption('_ui_window_filename', default='ui_exp_configurator.ui')

    # Signals
    sigSaveConfig = QtCore.Signal(str, str, str)
    sigLoadConfig = QtCore.Signal(str)
    sigAddEntry = QtCore.Signal(str, float, int, float, int)
    sigDeleteEntry = QtCore.Signal(QtCore.QModelIndex)

    def __init__(self, config, **kwargs):
        # load connection
        super().__init__(config=config, **kwargs)
        self._exp_logic = None
        self._mw = None

    def on_activate(self):
        """ Required initialization steps.
        """
        self._exp_logic = self.exp_logic()

        self._mw = ExpConfiguratorWindow(self._ui_window_filename)
        self._mw.formWidget.hide()

        # initialize combobox
        self._mw.select_experiment_ComboBox.addItems(self._exp_logic.experiments)

        # disable the save configuration toolbuttons while no experiment selected yet
        self._mw.save_config_Action.setDisabled(True)
        self._mw.save_config_copy_Action.setDisabled(True)

        # initialize the entry form
        self.init_configuration_form()

        # signals
        # internal signals
        # toolbar
        self._mw.save_config_Action.triggered.connect(self.save_config_clicked)
        self._mw.save_config_copy_Action.triggered.connect(self.save_config_copy_clicked)
        self._mw.load_config_Action.triggered.connect(self.load_config_clicked)
        self._mw.clear_all_Action.triggered.connect(self.clear_all_clicked)

        # widgets on the configuration form
        # self._mw.select_experiment_ComboBox.activated[str].connect(self.update_form)
        self._mw.select_experiment_ComboBox.activated[str].connect(self.start_new_experiment_config)

        self._mw.sample_name_LineEdit.textChanged.connect(self._exp_logic.update_sample_name)
        self._mw.n_cycles_spinBox.valueChanged.connect(self._exp_logic.update_training_cycles)
        self._mw.rest_time_spinBox.valueChanged.connect(self._exp_logic.update_resting_time)
        self._mw.training_duration_spinBox.valueChanged.connect(self._exp_logic.update_training_duration)
        self._mw.odor_ComboBox.currentTextChanged.connect(self._exp_logic.update_odor)
        self._mw.flow_doubleSpinBox.valueChanged.connect(self._exp_logic.update_air_flow)
        self._mw.prep_SpinBox.valueChanged.connect(self._exp_logic.update_prep_time)
        self._mw.opto_ComboBox.currentTextChanged.connect(self._exp_logic.update_pattern)
        self._mw.tON_doubleSpinBox.valueChanged.connect(self._exp_logic.update_ton)
        self._mw.tOFF_doubleSpinBox.valueChanged.connect(self._exp_logic.update_toff)

        # signals to logic
        self.sigSaveConfig.connect(self._exp_logic.save_to_exp_config_file)
        self.sigLoadConfig.connect(self._exp_logic.load_config_file)

        # signals from logic
        self._exp_logic.sigConfigDictUpdated.connect(self.update_entries)
        self._exp_logic.sigConfigLoaded.connect(self.display_loaded_config)

        # update the entries on the form
        self._exp_logic.init_default_config_dict()

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

    def init_configuration_form(self):
        """ Enter items into the combo-boxes according to available elements on the setup. """
        self._mw.odor_ComboBox.addItems(["Select odor"])
        self._mw.odor_ComboBox.addItems(self._exp_logic.odor)
        self._mw.opto_ComboBox.addItems(["Select opto pattern"])
        self._mw.opto_ComboBox.addItems(self._exp_logic.patterns)

# ----------------------------------------------------------------------------------------------------------------------
# Methods to adapt the configuration form depending on the current experiment
# ----------------------------------------------------------------------------------------------------------------------

    def start_new_experiment_config(self):
        """
        """
        self._exp_logic.init_default_config_dict()
        self.update_form()

    def update_form(self):
        """ Update the configuration form according to the selected experiment type.
        Sets the visibility of the GUI widgets depending on whether an information is required for the selected
        experiment type or not.

        When implementing new experiments, an additional case must be defined here.
        """
        experiment = self._mw.select_experiment_ComboBox.currentText()
        self._mw.save_config_Action.setDisabled(False)
        self._mw.save_config_copy_Action.setDisabled(False)

        if experiment == 'Select your experiment..':
            self._mw.formWidget.hide()
            self._mw.save_config_Action.setDisabled(True)
            self._mw.save_config_copy_Action.setDisabled(True)

        elif experiment == 'Long-term training':
            self._mw.formWidget.setVisible(True)
            self.set_visibility_general_settings(True)
            self.set_visibility_odor_settings(True)
            self.set_visibility_opto_settings(True)

        # add here additional experiment types

        else:
            pass

    def set_visibility_general_settings(self, visible):
        """ Show or hide the block with the general settings widgets.
        @param bool visible: show widgets = True, hide widgets = False
        """
        self._mw.general_Label.setVisible(visible)
        self._mw.sample_name_Label.setVisible(visible)
        self._mw.sample_name_LineEdit.setVisible(visible)
        self._mw.n_cycles_Label.setVisible(visible)
        self._mw.n_cycles_spinBox.setVisible(visible)
        self._mw.rest_time_label.setVisible(visible)
        self._mw.rest_time_spinBox.setVisible(visible)
        self._mw.training_duration_spinBox.setVisible(visible)
        self._mw.training_duration_label.setVisible(visible)

    def set_visibility_odor_settings(self, visible):
        """ Show or hide the block with the odor settings widgets.
        @param bool visible: show widgets = True, hide widgets = False
        """
        self._mw.odor_settings_Label.setVisible(visible)
        self._mw.odor_selection_Label.setVisible(visible)
        self._mw.odor_ComboBox.setVisible(visible)
        self._mw.air_flow_label.setVisible(visible)
        self._mw.flow_doubleSpinBox.setVisible(visible)
        self._mw.odor_prep_duration_Label.setVisible(visible)
        self._mw.prep_SpinBox.setVisible(visible)

    def set_visibility_opto_settings(self, visible):
        """ Show or hide the block with the opto settings widgets.
        @param bool visible: show widgets = True, hide widgets = False
        """
        self._mw.opto_settings_Label.setVisible(visible)
        self._mw.patterns_Label.setVisible(visible)
        self._mw.opto_ComboBox.setVisible(visible)
        self._mw.ton_label.setVisible(visible)
        self._mw.tON_doubleSpinBox.setVisible(visible)
        self._mw.toff_label.setVisible(visible)
        self._mw.tOFF_doubleSpinBox.setVisible(visible)

# ----------------------------------------------------------------------------------------------------------------------
# Callbacks of the toolbuttons
# ----------------------------------------------------------------------------------------------------------------------

    def save_config_clicked(self):
        """ Callback of the save config toolbutton. Sends a signal to the logic indicating the complete path where
         the config file will be saved depending on the experimental setup, and the experiment.
        A default filename is used in the logic module which is linked to the taskrunner (experiments are run using the
        parameters in these default files.
        """
        if (self._mw.odor_ComboBox.currentIndex() != 0) and (self._mw.opto_ComboBox.currentIndex() != 0):
            path = os.path.join(self.default_location, 'qudi_task_config_files')
            experiment = self._mw.select_experiment_ComboBox.currentText()
            self.sigSaveConfig.emit(path, experiment, None)
        else:
            self.log.error('Missing values for odor and/or optogenetics pattern')

    def save_config_copy_clicked(self):
        """ Callback of the save config copy toolbutton. Sends a signal to the logic indicating the complete path where
         the config file will be saved depending on the experimental setup, the experiment, and a custom filename.
         The experiment will not be run based on the parameters in the custom file, this just serves as a backup for
         the user.
        """
        path = os.path.join(self.default_location, 'qudi_task_config_files')
        experiment = self._mw.select_experiment_ComboBox.currentText()
        this_file = QtWidgets.QFileDialog.getSaveFileName(self._mw, 'Save copy of experimental configuration',
                                                          path, 'yml files (*.yml)')[0]
        path, filename = os.path.split(this_file)
        if this_file:
            self.sigSaveConfig.emit(path, experiment, filename)

    def load_config_clicked(self):
        """ Callback of the load config toolbutton. Opens a dialog to select an already defined config file. """
        data_directory = os.path.join(self.default_location, 'qudi_task_config_files')
        this_file = QtWidgets.QFileDialog.getOpenFileName(self._mw,
                                                          'Open experiment configuration',
                                                          data_directory,
                                                          'yml files (*.yml)')[0]
        if this_file:
            self.sigLoadConfig.emit(this_file)

    def clear_all_clicked(self):
        """ Callback of clear all toolbutton. Resets default values to all fields on the GUI. """
        self._mw.odor_ComboBox.setCurrentIndex(0)
        self._mw.opto_ComboBox.setCurrentIndex(0)
        self._exp_logic.init_default_config_dict()

# ----------------------------------------------------------------------------------------------------------------------
# Callbacks of signals sent from the logic
# ----------------------------------------------------------------------------------------------------------------------

    def update_entries(self):
        """ Callback of the signal sigConfigDictUpdated sent from the logic. Updates the values on the configuration
        form using the values stored in the config dict in the logic module. """
        self._mw.sample_name_LineEdit.setText(self._exp_logic.config_dict.get('sample_name', ''))
        self._mw.n_cycles_spinBox.setValue(self._exp_logic.config_dict.get('training_cycles', 0))
        self._mw.rest_time_spinBox.setValue(self._exp_logic.config_dict.get('resting_time', 0))
        self._mw.training_duration_spinBox.setValue(self._exp_logic.config_dict.get('training_duration', 0))
        self._mw.odor_ComboBox.setCurrentText(self._exp_logic.config_dict.get('odor', ''))
        self._mw.flow_doubleSpinBox.setValue(self._exp_logic.config_dict.get('air_flow', 0.0))
        self._mw.prep_SpinBox.setValue(self._exp_logic.config_dict.get('prep_time', 0))
        self._mw.opto_ComboBox.setCurrentText(self._exp_logic.config_dict.get('patterns', ''))
        self._mw.tON_doubleSpinBox.setValue(self._exp_logic.config_dict.get('t_on', 0.0))
        self._mw.tOFF_doubleSpinBox.setValue(self._exp_logic.config_dict.get('t_off', 0.0))

    def display_loaded_config(self):
        """ Callback of the signal sigConfigLoaded sent from the logic. Updates the displayed configuration form
        according to the experiment and shows the values defined in the loaded config file. """
        self._mw.select_experiment_ComboBox.setCurrentText(self._exp_logic.config_dict['experiment'])
        self.update_form()
        self.update_entries()

