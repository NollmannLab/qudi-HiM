# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains a GUI that allows to create an experiment config file for a Task.

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
    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_exp_configurator.ui')

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
    # connector to logic module
    exp_logic = Connector(interface='ExpConfigLogic')

    # config options
    default_location = ConfigOption('default_location_qudi_files', missing='warn')
    # serves as a path stem to default locations where experimental configurations are saved, and where roi lists and injections lists are loaded

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

        self._mw = ExpConfiguratorWindow()
        self._mw.formWidget.hide()

        # initialize combobox
        self._mw.select_experiment_ComboBox.addItems(self._exp_logic.experiments)

        # disable the save configuration toolbuttons while no experiment selected yet
        self._mw.save_config_Action.setDisabled(True)
        self._mw.save_config_copy_Action.setDisabled(True)

        # initialize the entry form
        self.init_configuration_form()

        # initialize list view
        self._mw.imaging_sequence_ListView.setModel(self._exp_logic.img_sequence_model)

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
        self._mw.dapi_CheckBox.stateChanged.connect(self._exp_logic.update_is_dapi)
        self._mw.rna_CheckBox.stateChanged.connect(self._exp_logic.update_is_rna)
        self._mw.TransferData_checkBox.stateChanged.connect(self._exp_logic.update_data_transfer)
        self._mw.exposure_DSpinBox.valueChanged.connect(self._exp_logic.update_exposure)
        self._mw.gain_SpinBox.valueChanged.connect(self._exp_logic.update_gain)
        self._mw.num_frames_SpinBox.valueChanged.connect(self._exp_logic.update_frames)
        self._mw.filterpos_ComboBox.currentIndexChanged.connect(self._exp_logic.update_filterpos)
        self._mw.save_path_LineEdit.textChanged.connect(self._exp_logic.update_save_path)
        self._mw.save_network_path_LineEdit.textChanged.connect(self._exp_logic.update_save_network_path)
        self._mw.fileformat_ComboBox.currentTextChanged.connect(self._exp_logic.update_fileformat)
        self._mw.num_z_planes_SpinBox.valueChanged.connect(self._exp_logic.update_num_z_planes)
        self._mw.z_step_DSpinBox.valueChanged.connect(self._exp_logic.update_z_step)
        self._mw.centered_focal_plane_CheckBox.stateChanged.connect(self._exp_logic.update_centered_focal_plane)
        self._mw.roi_list_path_LineEdit.textChanged.connect(self._exp_logic.update_roi_path)
        self._mw.injections_list_LineEdit.textChanged.connect(self._exp_logic.update_injections_path)
        self._mw.dapi_data_LineEdit.textChanged.connect(self._exp_logic.update_dapi_path)
        self._mw.reference_images_lineEdit.textChanged.connect(self._exp_logic.update_zen_ref_images_path)
        self._mw.Zen_saving_folder_lineEdit.textChanged.connect(self._exp_logic.update_zen_saving_path)
        self._mw.illumination_time_DSpinBox.valueChanged.connect(self._exp_logic.update_illumination_time)
        self._mw.num_iterations_SpinBox.valueChanged.connect(self._exp_logic.update_num_iterations)
        self._mw.time_step_SpinBox.valueChanged.connect(self._exp_logic.update_time_step)
        self._mw.axial_calibration_path_lineEdit.textChanged.connect(self._exp_logic.update_axial_calibration_path)

        # pushbuttons
        # pushbuttons belonging to the listview
        self._mw.add_entry_PushButton.clicked.connect(self.add_entry_clicked)
        self._mw.delete_entry_PushButton.clicked.connect(self.delete_entry_clicked)
        self._mw.delete_all_PushButton.clicked.connect(self._exp_logic.delete_imaging_list)

        # get-current-value pushbutton signals
        self._mw.get_exposure_PushButton.clicked.connect(self._exp_logic.get_exposure)
        self._mw.get_gain_PushButton.clicked.connect(self._exp_logic.get_gain)
        self._mw.get_filterpos_PushButton.clicked.connect(self._exp_logic.get_filterpos)

        # load file pushbutton signals
        self._mw.load_roi_PushButton.clicked.connect(self.load_roi_list_clicked)
        self._mw.load_injections_PushButton.clicked.connect(self.load_injections_clicked)
        self._mw.load_dapi_PushButton.clicked.connect(self.load_dapi_path_clicked)
        self._mw.reference_images_pushButton.clicked.connect(self.load_ref_images_path_clicked)
        self._mw.Zen_saving_folder_pushButton.clicked.connect(self.load_zen_saving_path_clicked)
        self._mw.load_dz_calibration_pushButton.clicked.connect(self.load_axial_calibration_path_clicked)

        # signals to logic
        self.sigSaveConfig.connect(self._exp_logic.save_to_exp_config_file)
        self.sigLoadConfig.connect(self._exp_logic.load_config_file)
        self.sigAddEntry.connect(self._exp_logic.add_entry_to_imaging_list)
        self.sigDeleteEntry.connect(self._exp_logic.delete_entry_from_imaging_list)

        # signals from logic
        self._exp_logic.sigConfigDictUpdated.connect(self.update_entries)
        self._exp_logic.sigImagingListChanged.connect(self.update_listview)
        self._exp_logic.sigConfigLoaded.connect(self.display_loaded_config)
        self._exp_logic.sigUpdateListModel.connect(self.update_list_model)

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
        self._mw.filterpos_ComboBox.addItems(self._exp_logic.filters)
        self._mw.laser_ComboBox.addItems(self._exp_logic.lasers)
        self._mw.fileformat_ComboBox.addItems(self._exp_logic.supported_fileformats)

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
        self._mw.laser_ComboBox.clear()  # reset content of laser selection to default state because it could have been modified (see 'Photobleaching' experiment)
        self._mw.laser_ComboBox.addItems(self._exp_logic.lasers)

        if experiment == 'Select your experiment..':
            self._mw.formWidget.hide()
            self._mw.save_config_Action.setDisabled(True)
            self._mw.save_config_copy_Action.setDisabled(True)

        elif experiment == 'Multicolor imaging PALM':
            # chose the right the listview model
            self._mw.imaging_sequence_ListView.setModel(self._exp_logic.img_sequence_model)
            self._exp_logic.is_timelapse_ramm = False
            self._exp_logic.is_timelapse_palm = False

            self._mw.formWidget.setVisible(True)
            self.set_visibility_general_settings(True)
            self.set_visibility_camera_settings(True)
            self.set_visibility_filter_settings(True)
            self.set_visibility_imaging_settings(True)
            self.set_visibility_save_settings(True)
            self.set_visibility_scan_settings(False)
            self.set_visibility_documents_settings(False)
            self.set_visibility_prebleaching_settings(False)
            self.set_visibility_timelapse_settings(False)
            self.set_visibility_ZEN_security_settings(False)

            # additional visibility settings
            self._mw.save_remote_path_Label.setVisible(False)
            self._mw.save_network_path_LineEdit.setVisible(False)
            self._mw.TransferData_checkBox.setVisible(False)

        elif experiment == 'Multicolor scan PALM':
            # chose the right the listview model
            self._mw.imaging_sequence_ListView.setModel(self._exp_logic.img_sequence_model)
            self._exp_logic.is_timelapse_ramm = False
            self._exp_logic.is_timelapse_palm = False

            self._mw.formWidget.setVisible(True)
            self.set_visibility_general_settings(True)
            self.set_visibility_camera_settings(True)
            self.set_visibility_filter_settings(True)
            self.set_visibility_imaging_settings(True)
            self.set_visibility_save_settings(True)
            self.set_visibility_scan_settings(True)
            self.set_visibility_documents_settings(False)
            self.set_visibility_prebleaching_settings(False)
            self.set_visibility_timelapse_settings(False)
            self.set_visibility_ZEN_security_settings(False)

            # additional visibility settings
            self._mw.save_remote_path_Label.setVisible(False)
            self._mw.save_network_path_LineEdit.setVisible(False)
            self._mw.TransferData_checkBox.setVisible(False)

        elif experiment == 'Multicolor scan RAMM':
            # chose the right the listview model
            self._mw.imaging_sequence_ListView.setModel(self._exp_logic.img_sequence_model)
            self._exp_logic.is_timelapse_ramm = False
            self._exp_logic.is_timelapse_palm = False

            self._mw.formWidget.setVisible(True)
            self.set_visibility_general_settings(True)
            self.set_visibility_camera_settings(True)
            self.set_visibility_filter_settings(False)
            self.set_visibility_imaging_settings(True)
            self.set_visibility_save_settings(True)
            self.set_visibility_scan_settings(True)
            self.set_visibility_documents_settings(False)
            self.set_visibility_prebleaching_settings(False)
            self.set_visibility_timelapse_settings(False)
            self.set_visibility_ZEN_security_settings(False)

            # additional visibility settings
            self._mw.gain_Label.setVisible(False)
            self._mw.gain_SpinBox.setVisible(False)
            self._mw.get_gain_PushButton.setVisible(False)
            self._mw.num_frames_Label.setVisible(False)
            self._mw.num_frames_SpinBox.setVisible(False)
            self._mw.save_remote_path_Label.setVisible(False)
            self._mw.save_network_path_LineEdit.setVisible(False)
            self._mw.TransferData_checkBox.setVisible(False)

            # Modify the laser list in order to add the bright field control
            self._mw.laser_ComboBox.addItems(['Brightfield'])

        elif experiment == 'Multicolor scan Airyscan':
            # chose the right the listview model
            self._mw.imaging_sequence_ListView.setModel(self._exp_logic.img_sequence_model)
            self._exp_logic.is_timelapse_ramm = False
            self._exp_logic.is_timelapse_palm = False

            self._mw.formWidget.setVisible(True)
            self.set_visibility_general_settings(False)
            self.set_visibility_camera_settings(False)
            self.set_visibility_filter_settings(False)
            self.set_visibility_imaging_settings(True)
            self.set_visibility_save_settings(False)
            self.set_visibility_scan_settings(True)
            self.set_visibility_documents_settings(False)
            self.set_visibility_prebleaching_settings(False)
            self.set_visibility_timelapse_settings(False)
            self.set_visibility_ZEN_security_settings(False)

            # additional visibility settings
            self._mw.gain_Label.setVisible(False)
            self._mw.gain_SpinBox.setVisible(False)
            self._mw.get_gain_PushButton.setVisible(False)
            self._mw.num_frames_Label.setVisible(False)
            self._mw.num_frames_SpinBox.setVisible(False)
            self._mw.save_remote_path_Label.setVisible(False)
            self._mw.save_network_path_LineEdit.setVisible(False)
            self._mw.TransferData_checkBox.setVisible(False)

        elif experiment == 'ROI multicolor scan PALM':
            # chose the right the listview model
            self._mw.imaging_sequence_ListView.setModel(self._exp_logic.img_sequence_model)
            self._exp_logic.is_timelapse_ramm = False
            self._exp_logic.is_timelapse_palm = False

            self._mw.formWidget.setVisible(True)
            self.set_visibility_general_settings(True)
            self.set_visibility_camera_settings(True)
            self.set_visibility_filter_settings(True)
            self.set_visibility_imaging_settings(True)
            self.set_visibility_save_settings(True)
            self.set_visibility_scan_settings(True)
            self.set_visibility_documents_settings(True)
            self.set_visibility_prebleaching_settings(False)
            self.set_visibility_timelapse_settings(False)
            self.set_visibility_ZEN_security_settings(False)

            # additional visibility modifications
            self._mw.injections_list_Label.setVisible(False)
            self._mw.injections_list_LineEdit.setVisible(False)
            self._mw.load_injections_PushButton.setVisible(False)
            self._mw.dapi_path_Label.setVisible(False)
            self._mw.dapi_data_LineEdit.setVisible(False)
            self._mw.load_dapi_PushButton.setVisible(False)
            self._mw.save_remote_path_Label.setVisible(False)
            self._mw.save_network_path_LineEdit.setVisible(False)
            self._mw.TransferData_checkBox.setVisible(False)

        elif experiment == 'ROI multicolor scan RAMM':
            # chose the right the listview model
            self._mw.imaging_sequence_ListView.setModel(self._exp_logic.img_sequence_model)
            self._exp_logic.is_timelapse_ramm = False
            self._exp_logic.is_timelapse_palm = False

            self._mw.formWidget.setVisible(True)
            self.set_visibility_general_settings(True)
            self.set_visibility_camera_settings(True)
            self.set_visibility_filter_settings(False)
            self.set_visibility_imaging_settings(True)
            self.set_visibility_save_settings(True)
            self.set_visibility_scan_settings(True)
            self.set_visibility_documents_settings(True)
            self.set_visibility_prebleaching_settings(False)
            self.set_visibility_timelapse_settings(False)
            self.set_visibility_ZEN_security_settings(False)

            # additional visibility modifications
            self._mw.dapi_CheckBox.setVisible(True)
            self._mw.rna_CheckBox.setVisible(True)
            self._mw.gain_Label.setVisible(False)
            self._mw.gain_SpinBox.setVisible(False)
            self._mw.get_gain_PushButton.setVisible(False)
            self._mw.injections_list_Label.setVisible(False)
            self._mw.injections_list_LineEdit.setVisible(False)
            self._mw.load_injections_PushButton.setVisible(False)
            self._mw.dapi_path_Label.setVisible(False)
            self._mw.dapi_data_LineEdit.setVisible(False)
            self._mw.load_dapi_PushButton.setVisible(False)
            self._mw.num_frames_Label.setVisible(False)
            self._mw.num_frames_SpinBox.setVisible(False)
            self._mw.save_remote_path_Label.setVisible(False)
            self._mw.save_network_path_LineEdit.setVisible(False)
            self._mw.TransferData_checkBox.setVisible(False)

            # Modify the laser list in order to add the bright field control
            self._mw.laser_ComboBox.addItems(['Brightfield'])

        elif experiment == 'ROI multicolor scan Airyscan':
            # chose the right the listview model
            self._mw.imaging_sequence_ListView.setModel(self._exp_logic.img_sequence_model)
            self._exp_logic.is_timelapse_ramm = False
            self._exp_logic.is_timelapse_palm = False

            self._mw.formWidget.setVisible(True)
            self.set_visibility_general_settings(True)
            self.set_visibility_camera_settings(False)
            self.set_visibility_filter_settings(False)
            self.set_visibility_imaging_settings(True)
            self.set_visibility_save_settings(True)
            self.set_visibility_scan_settings(True)
            self.set_visibility_documents_settings(True)
            self.set_visibility_prebleaching_settings(False)
            self.set_visibility_timelapse_settings(False)
            self.set_visibility_ZEN_security_settings(False)

            # additional visibility modifications
            self._mw.dapi_CheckBox.setVisible(True)
            self._mw.rna_CheckBox.setVisible(True)
            self._mw.gain_Label.setVisible(False)
            self._mw.gain_SpinBox.setVisible(False)
            self._mw.get_gain_PushButton.setVisible(False)
            self._mw.injections_list_Label.setVisible(False)
            self._mw.injections_list_LineEdit.setVisible(False)
            self._mw.load_injections_PushButton.setVisible(False)
            self._mw.dapi_path_Label.setVisible(False)
            self._mw.dapi_data_LineEdit.setVisible(False)
            self._mw.load_dapi_PushButton.setVisible(False)
            self._mw.num_frames_Label.setVisible(False)
            self._mw.num_frames_SpinBox.setVisible(False)
            self._mw.save_remote_path_Label.setVisible(False)
            self._mw.save_network_path_LineEdit.setVisible(False)
            self._mw.TransferData_checkBox.setVisible(False)

        elif experiment == 'ROI multicolor scan Airyscan confocal':
            # chose the right the listview model
            # self._mw.imaging_sequence_ListView.setModel(self._exp_logic.img_sequence_model)
            self._exp_logic.is_timelapse_ramm = False
            self._exp_logic.is_timelapse_palm = False

            self._mw.formWidget.setVisible(True)
            self.set_visibility_general_settings(True)
            self.set_visibility_camera_settings(False)
            self.set_visibility_filter_settings(False)
            self.set_visibility_imaging_settings(False)
            self.set_visibility_save_settings(True)
            self.set_visibility_scan_settings(False)
            self.set_visibility_documents_settings(True)
            self.set_visibility_prebleaching_settings(False)
            self.set_visibility_timelapse_settings(False)
            self.set_visibility_ZEN_security_settings(False)

            # additional visibility modifications
            self._mw.dapi_CheckBox.setVisible(False)
            self._mw.rna_CheckBox.setVisible(False)
            self._mw.gain_Label.setVisible(False)
            self._mw.gain_SpinBox.setVisible(False)
            self._mw.get_gain_PushButton.setVisible(False)
            self._mw.injections_list_Label.setVisible(False)
            self._mw.injections_list_LineEdit.setVisible(False)
            self._mw.load_injections_PushButton.setVisible(False)
            self._mw.dapi_path_Label.setVisible(False)
            self._mw.dapi_data_LineEdit.setVisible(False)
            self._mw.load_dapi_PushButton.setVisible(False)
            self._mw.num_frames_Label.setVisible(False)
            self._mw.num_frames_SpinBox.setVisible(False)
            self._mw.save_remote_path_Label.setVisible(False)
            self._mw.save_network_path_LineEdit.setVisible(False)
            self._mw.TransferData_checkBox.setVisible(False)
            self._mw.fileformat_Label.setVisible(False)
            self._mw.fileformat_ComboBox.setVisible(False)

        elif experiment == 'Fluidics RAMM' or experiment == 'Fluidics Airyscan':
            # chose the right the listview model
            self._mw.imaging_sequence_ListView.setModel(self._exp_logic.img_sequence_model)
            self._exp_logic.is_timelapse_ramm = False
            self._exp_logic.is_timelapse_palm = False

            self._mw.formWidget.setVisible(True)
            self.set_visibility_general_settings(False)
            self.set_visibility_camera_settings(False)
            self.set_visibility_filter_settings(False)
            self.set_visibility_imaging_settings(False)
            self.set_visibility_save_settings(False)
            self.set_visibility_scan_settings(False)
            self.set_visibility_documents_settings(True)
            self.set_visibility_prebleaching_settings(False)
            self.set_visibility_timelapse_settings(False)
            self.set_visibility_ZEN_security_settings(False)

            # additional visibility modifications
            self._mw.roi_list_path_Label.setVisible(False)
            self._mw.roi_list_path_LineEdit.setVisible(False)
            self._mw.load_roi_PushButton.setVisible(False)
            self._mw.dapi_path_Label.setVisible(False)
            self._mw.dapi_data_LineEdit.setVisible(False)
            self._mw.load_dapi_PushButton.setVisible(False)

        elif experiment == 'Hi-M RAMM':
            # chose the right the listview model
            self._mw.imaging_sequence_ListView.setModel(self._exp_logic.img_sequence_model)
            self._exp_logic.is_timelapse_ramm = False
            self._exp_logic.is_timelapse_palm = False

            self._mw.formWidget.setVisible(True)
            self.set_visibility_general_settings(True)
            self.set_visibility_camera_settings(True)
            self.set_visibility_filter_settings(False)
            self.set_visibility_imaging_settings(True)
            self.set_visibility_save_settings(True)
            self.set_visibility_scan_settings(True)
            self.set_visibility_documents_settings(True)
            self.set_visibility_prebleaching_settings(False)
            self.set_visibility_timelapse_settings(False)
            self.set_visibility_ZEN_security_settings(False)

            # additional visibility settings
            self._mw.gain_Label.setVisible(False)
            self._mw.gain_SpinBox.setVisible(False)
            self._mw.get_gain_PushButton.setVisible(False)
            self._mw.num_frames_Label.setVisible(False)
            self._mw.num_frames_SpinBox.setVisible(False)

        elif experiment == 'Hi-M Airyscan Lumencor Tissue':
            # chose the right the listview model
            self._mw.imaging_sequence_ListView.setModel(self._exp_logic.img_sequence_model)
            self._exp_logic.is_timelapse_ramm = False
            self._exp_logic.is_timelapse_palm = False

            self._mw.formWidget.setVisible(True)
            self.set_visibility_general_settings(True)
            self.set_visibility_camera_settings(False)
            self.set_visibility_filter_settings(False)
            self.set_visibility_imaging_settings(True)
            self.set_visibility_save_settings(True)
            self.set_visibility_scan_settings(True)
            self.set_visibility_documents_settings(True)
            self.set_visibility_prebleaching_settings(False)
            self.set_visibility_timelapse_settings(False)
            self.set_visibility_ZEN_security_settings(True)

            # additional visibility settings
            self._mw.gain_Label.setVisible(False)
            self._mw.gain_SpinBox.setVisible(False)
            self._mw.get_gain_PushButton.setVisible(False)
            self._mw.num_frames_Label.setVisible(False)
            self._mw.num_frames_SpinBox.setVisible(False)
            self._mw.save_remote_path_Label.setVisible(False)
            self._mw.save_network_path_LineEdit.setVisible(False)
            self._mw.TransferData_checkBox.setVisible(False)
            self._mw.z_step_Label.setVisible(False)
            self._mw.z_step_DSpinBox.setVisible(False)
            self._mw.centered_focal_plane_CheckBox.setVisible(False)

        elif experiment == 'Hi-M Airyscan Lumencor':
            # chose the right the listview model
            self._mw.imaging_sequence_ListView.setModel(self._exp_logic.img_sequence_model)
            self._exp_logic.is_timelapse_ramm = False
            self._exp_logic.is_timelapse_palm = False

            self._mw.formWidget.setVisible(True)
            self.set_visibility_general_settings(True)
            self.set_visibility_camera_settings(False)
            self.set_visibility_filter_settings(False)
            self.set_visibility_imaging_settings(True)
            self.set_visibility_save_settings(True)
            self.set_visibility_scan_settings(True)
            self.set_visibility_documents_settings(True)
            self.set_visibility_prebleaching_settings(False)
            self.set_visibility_timelapse_settings(False)
            self.set_visibility_ZEN_security_settings(False)

            # additional visibility settings
            self._mw.gain_Label.setVisible(False)
            self._mw.gain_SpinBox.setVisible(False)
            self._mw.get_gain_PushButton.setVisible(False)
            self._mw.num_frames_Label.setVisible(False)
            self._mw.num_frames_SpinBox.setVisible(False)
            self._mw.save_remote_path_Label.setVisible(False)
            self._mw.save_network_path_LineEdit.setVisible(False)
            self._mw.TransferData_checkBox.setVisible(False)
            self._mw.z_step_Label.setVisible(False)
            self._mw.z_step_DSpinBox.setVisible(False)
            self._mw.centered_focal_plane_CheckBox.setVisible(False)

        elif experiment == 'Hi-M Airyscan Confocal':
            # chose the right the listview model
            self._mw.imaging_sequence_ListView.setModel(self._exp_logic.img_sequence_model)
            self._exp_logic.is_timelapse_ramm = False
            self._exp_logic.is_timelapse_palm = False

            self._mw.formWidget.setVisible(True)
            self.set_visibility_general_settings(True)
            self.set_visibility_camera_settings(False)
            self.set_visibility_filter_settings(False)
            self.set_visibility_imaging_settings(False)
            self.set_visibility_save_settings(True)
            self.set_visibility_scan_settings(False)
            self.set_visibility_documents_settings(True)
            self.set_visibility_prebleaching_settings(False)
            self.set_visibility_timelapse_settings(False)
            self.set_visibility_ZEN_security_settings(False)

            # additional visibility settings
            self._mw.gain_Label.setVisible(False)
            self._mw.gain_SpinBox.setVisible(False)
            self._mw.get_gain_PushButton.setVisible(False)
            self._mw.num_frames_Label.setVisible(False)
            self._mw.num_frames_SpinBox.setVisible(False)
            self._mw.save_remote_path_Label.setVisible(False)
            self._mw.save_network_path_LineEdit.setVisible(False)
            self._mw.TransferData_checkBox.setVisible(False)

        elif experiment == 'Photobleaching RAMM' or experiment == 'Photobleaching Airyscan':
            # chose the right the listview model
            self._mw.imaging_sequence_ListView.setModel(self._exp_logic.img_sequence_model)
            self._exp_logic.is_timelapse_ramm = False
            self._exp_logic.is_timelapse_palm = False

            self._mw.formWidget.setVisible(True)
            self.set_visibility_general_settings(False)
            self.set_visibility_camera_settings(False)
            self.set_visibility_filter_settings(False)
            self.set_visibility_imaging_settings(True)
            self.set_visibility_save_settings(False)
            self.set_visibility_scan_settings(False)
            self.set_visibility_documents_settings(True)
            self.set_visibility_prebleaching_settings(True)
            self.set_visibility_timelapse_settings(False)
            self.set_visibility_ZEN_security_settings(False)

            # additional visibility modifications
            self._mw.injections_list_Label.setVisible(False)
            self._mw.injections_list_LineEdit.setVisible(False)
            self._mw.load_injections_PushButton.setVisible(False)
            self._mw.dapi_path_Label.setVisible(False)
            self._mw.dapi_data_LineEdit.setVisible(False)
            self._mw.load_dapi_PushButton.setVisible(False)
            self._mw.laser_ComboBox.removeItem(0)  # do not allow the UV laser (405 nm typically)

        elif experiment == 'Fast timelapse RAMM' :
            # chose the right the listview model
            self._mw.imaging_sequence_ListView.setModel(self._exp_logic.img_sequence_model)
            self._exp_logic.is_timelapse_ramm = False  # only for 'usual' timelapse is this flag set to True
            self._exp_logic.is_timelapse_palm = False

            self._mw.formWidget.setVisible(True)
            self.set_visibility_general_settings(True)
            self.set_visibility_camera_settings(True)
            self.set_visibility_filter_settings(False)
            self.set_visibility_imaging_settings(True)
            self.set_visibility_save_settings(True)
            self.set_visibility_scan_settings(True)
            self.set_visibility_documents_settings(True)
            self.set_visibility_prebleaching_settings(False)
            self.set_visibility_timelapse_settings(True)
            self.set_visibility_ZEN_security_settings(False)

            # additional visibility modifications
            self._mw.gain_Label.setVisible(False)
            self._mw.gain_SpinBox.setVisible(False)
            self._mw.get_gain_PushButton.setVisible(False)
            self._mw.num_frames_Label.setVisible(False)
            self._mw.num_frames_SpinBox.setVisible(False)
            self._mw.injections_list_Label.setVisible(False)
            self._mw.injections_list_LineEdit.setVisible(False)
            self._mw.load_injections_PushButton.setVisible(False)
            self._mw.dapi_path_Label.setVisible(False)
            self._mw.dapi_data_LineEdit.setVisible(False)
            self._mw.load_dapi_PushButton.setVisible(False)
            self._mw.time_step_Label.setVisible(False)
            self._mw.time_step_SpinBox.setVisible(False)
            self._mw.save_remote_path_Label.setVisible(False)
            self._mw.save_network_path_LineEdit.setVisible(False)
            self._mw.TransferData_checkBox.setVisible(False)

            # Modify the laser list in order to add the bright field control
            self._mw.laser_ComboBox.addItems(['Brightfield'])

        elif experiment == 'Hubble RAMM':
            # chose the right the listview model
            self._mw.imaging_sequence_ListView.setModel(self._exp_logic.img_sequence_model)
            self._exp_logic.is_timelapse_ramm = False  # only for 'usual' timelapse is this flag set to True
            self._exp_logic.is_timelapse_palm = False

            self._mw.formWidget.setVisible(True)
            self.set_visibility_general_settings(True)
            self.set_visibility_camera_settings(True)
            self.set_visibility_filter_settings(False)
            self.set_visibility_imaging_settings(True)
            self.set_visibility_save_settings(True)
            self.set_visibility_scan_settings(True)
            self.set_visibility_documents_settings(True)
            self.set_visibility_prebleaching_settings(False)
            self.set_visibility_timelapse_settings(True)
            self.set_visibility_ZEN_security_settings(False)

            # additional visibility modifications
            self._mw.gain_Label.setVisible(False)
            self._mw.gain_SpinBox.setVisible(False)
            self._mw.get_gain_PushButton.setVisible(False)
            self._mw.num_frames_Label.setVisible(False)
            self._mw.num_frames_SpinBox.setVisible(False)
            self._mw.injections_list_Label.setVisible(False)
            self._mw.injections_list_LineEdit.setVisible(False)
            self._mw.load_injections_PushButton.setVisible(False)
            self._mw.dapi_path_Label.setVisible(False)
            self._mw.dapi_data_LineEdit.setVisible(False)
            self._mw.load_dapi_PushButton.setVisible(False)
            self._mw.time_step_Label.setVisible(False)
            self._mw.time_step_SpinBox.setVisible(False)
            self._mw.save_remote_path_Label.setVisible(False)
            self._mw.save_network_path_LineEdit.setVisible(False)
            self._mw.TransferData_checkBox.setVisible(False)
            self._mw.num_iterations_Label.setVisible(False)
            self._mw.num_iterations_SpinBox.setVisible(False)

            # Modify the laser list in order to add the bright field control
            self._mw.laser_ComboBox.addItems(['Brightfield'])

        elif experiment == 'Timelapse RAMM':
            # change the listview model
            self._mw.imaging_sequence_ListView.setModel(self._exp_logic.img_sequence_model_timelapse_ramm)
            self._exp_logic.is_timelapse_ramm = True
            self._exp_logic.is_timelapse_palm = False

            self._mw.formWidget.setVisible(True)
            self.set_visibility_general_settings(True)
            self.set_visibility_camera_settings(True)
            self.set_visibility_filter_settings(False)
            self.set_visibility_imaging_settings(True)
            self.set_visibility_save_settings(True)
            self.set_visibility_scan_settings(True)
            self.set_visibility_documents_settings(True)
            self.set_visibility_prebleaching_settings(False)
            self.set_visibility_timelapse_settings(True)
            self.set_visibility_ZEN_security_settings(False)

            # additional visibility modifications
            self._mw.gain_Label.setVisible(False)
            self._mw.gain_SpinBox.setVisible(False)
            self._mw.get_gain_PushButton.setVisible(False)
            self._mw.num_frames_Label.setVisible(False)
            self._mw.num_frames_SpinBox.setVisible(False)
            self._mw.injections_list_Label.setVisible(False)
            self._mw.injections_list_LineEdit.setVisible(False)
            self._mw.load_injections_PushButton.setVisible(False)
            self._mw.dapi_path_Label.setVisible(False)
            self._mw.dapi_data_LineEdit.setVisible(False)
            self._mw.load_dapi_PushButton.setVisible(False)
            self._mw.dz_calibration_label.setVisible(False)
            self._mw.axial_calibration_path_lineEdit.setVisible(False)
            self._mw.load_dz_calibration_pushButton.setVisible(False)
            self._mw.save_remote_path_Label.setVisible(False)
            self._mw.save_network_path_LineEdit.setVisible(False)
            self._mw.TransferData_checkBox.setVisible(False)

            # Modify the laser list in order to add the bright field control
            self._mw.laser_ComboBox.addItems(['Brightfield'])

        elif experiment == 'Timelapse PALM':
            # change the listview model
            self._mw.imaging_sequence_ListView.setModel(self._exp_logic.img_sequence_model_timelapse_palm)
            self._exp_logic.is_timelapse_ramm = False
            self._exp_logic.is_timelapse_palm = True

            self._mw.formWidget.setVisible(True)
            self.set_visibility_general_settings(True)
            self.set_visibility_camera_settings(True)
            self.set_visibility_filter_settings(True)
            self.set_visibility_imaging_settings(True)
            self.set_visibility_save_settings(True)
            self.set_visibility_scan_settings(True)
            self.set_visibility_documents_settings(True)
            self.set_visibility_prebleaching_settings(False)
            self.set_visibility_timelapse_settings(True)
            self.set_visibility_ZEN_security_settings(False)

            # additional visibility modifications
            self._mw.num_frames_Label.setVisible(False)
            self._mw.num_frames_SpinBox.setVisible(False)
            self._mw.injections_list_Label.setVisible(False)
            self._mw.injections_list_LineEdit.setVisible(False)
            self._mw.load_injections_PushButton.setVisible(False)
            self._mw.dapi_path_Label.setVisible(False)
            self._mw.dapi_data_LineEdit.setVisible(False)
            self._mw.load_dapi_PushButton.setVisible(False)
            self._mw.dz_calibration_label.setVisible(False)
            self._mw.axial_calibration_path_lineEdit.setVisible(False)
            self._mw.load_dz_calibration_pushButton.setVisible(False)
            self._mw.save_remote_path_Label.setVisible(False)
            self._mw.save_network_path_LineEdit.setVisible(False)
            self._mw.TransferData_checkBox.setVisible(False)

        # add here additional experiment types

        else:
            pass

    def set_visibility_general_settings(self, visible):
        """ Show or hide the block with the general settings widgets.
        :param bool visible: show widgets = True, hide widgets = False
        """
        self._mw.general_Label.setVisible(visible)
        self._mw.sample_name_Label.setVisible(visible)
        self._mw.sample_name_LineEdit.setVisible(visible)

        # the dapi and rna checkboxes are needed only for the ROI Multicolor scan RAMM. Set them invisible as default.
        self._mw.dapi_CheckBox.setVisible(False)
        self._mw.rna_CheckBox.setVisible(False)

    def set_visibility_camera_settings(self, visible):
        """ Show or hide the block with the camera settings widgets.
        :param bool visible: show widgets = True, hide widgets = False
        """
        self._mw.cam_settings_Label.setVisible(visible)
        self._mw.exposure_Label.setVisible(visible)
        self._mw.exposure_DSpinBox.setVisible(visible)
        self._mw.get_exposure_PushButton.setVisible(visible)
        self._mw.gain_Label.setVisible(visible)
        self._mw.gain_SpinBox.setVisible(visible)
        self._mw.get_gain_PushButton.setVisible(visible)
        self._mw.num_frames_Label.setVisible(visible)
        self._mw.num_frames_SpinBox.setVisible(visible)

    def set_visibility_filter_settings(self, visible):
        """ Show or hide the block with the filter settings widgets.
        :param bool visible: show widgets = True, hide widgets = False
        """
        self._mw.filter_settings_Label.setVisible(visible)
        self._mw.filterpos_Label.setVisible(visible)
        self._mw.filterpos_ComboBox.setVisible(visible)
        self._mw.get_filterpos_PushButton.setVisible(visible)

    def set_visibility_imaging_settings(self, visible):
        """ Show or hide the block with the imaging sequence widgets.
        :param bool visible: show widgets = True, hide widgets = False
        """
        self._mw.imaging_settings_Label.setVisible(visible)
        self._mw.imaging_sequence_Label.setVisible(visible)
        self._mw.imaging_sequence_ListView.setVisible(visible)
        self._mw.laser_ComboBox.setVisible(visible)
        self._mw.laser_intensity_DSpinBox.setVisible(visible)
        self._mw.delete_entry_PushButton.setVisible(visible)
        self._mw.add_entry_PushButton.setVisible(visible)
        self._mw.delete_all_PushButton.setVisible(visible)

    def set_visibility_save_settings(self, visible):
        """ Show or hide the block with the save settings widgets. (Information where to save image data, and fileformat)
        :param bool visible: show widgets = True, hide widgets = False
        """
        self._mw.save_settings_Label.setVisible(visible)
        self._mw.save_path_Label.setVisible(visible)
        self._mw.save_remote_path_Label.setVisible(visible)
        self._mw.save_path_LineEdit.setVisible(visible)
        self._mw.save_network_path_LineEdit.setVisible(visible)
        self._mw.fileformat_Label.setVisible(visible)
        self._mw.fileformat_ComboBox.setVisible(visible)
        self._mw.TransferData_checkBox.setVisible(visible)

    def set_visibility_scan_settings(self, visible):
        """ Show or hide the block with the scan settings widgets.
        :param bool visible: show widgets = True, hide widgets = False
        """
        self._mw.scan_settings_Label.setVisible(visible)
        self._mw.num_z_planes_Label.setVisible(visible)
        self._mw.num_z_planes_SpinBox.setVisible(visible)
        self._mw.z_step_Label.setVisible(visible)
        self._mw.z_step_DSpinBox.setVisible(visible)
        self._mw.centered_focal_plane_CheckBox.setVisible(visible)

    def set_visibility_documents_settings(self, visible):
        """ Show or hide the block with the additional documents settings widgets.
        :param bool visible: show widgets = True, hide widgets = False
        """
        self._mw.documents_Label.setVisible(visible)
        self._mw.roi_list_path_Label.setVisible(visible)
        self._mw.roi_list_path_LineEdit.setVisible(visible)
        self._mw.load_roi_PushButton.setVisible(visible)
        self._mw.injections_list_Label.setVisible(visible)
        self._mw.injections_list_LineEdit.setVisible(visible)
        self._mw.load_injections_PushButton.setVisible(visible)
        self._mw.dapi_path_Label.setVisible(visible)
        self._mw.dapi_data_LineEdit.setVisible(visible)
        self._mw.load_dapi_PushButton.setVisible(visible)

    def set_visibility_prebleaching_settings(self, visible):
        """ Show or hide the block with the prebleaching settings widgets
        :param bool visible: show widgets = True, hide widgets = False
        """
        self._mw.prebleach_settings_Label.setVisible(visible)
        self._mw.illumination_time_Label.setVisible(visible)
        self._mw.illumination_time_DSpinBox.setVisible(visible)

    def set_visibility_timelapse_settings(self, visible):
        """ Show or hide the block with the timelapse settings widgets.
        :param bool visible: show widgets = True, hide widgets = False """
        self._mw.timelapse_settings_Label.setVisible(visible)
        self._mw.num_iterations_Label.setVisible(visible)
        self._mw.num_iterations_SpinBox.setVisible(visible)
        self._mw.time_step_Label.setVisible(visible)
        self._mw.time_step_SpinBox.setVisible(visible)
        self._mw.dz_calibration_label.setVisible(visible)
        self._mw.axial_calibration_path_lineEdit.setVisible(visible)
        self._mw.load_dz_calibration_pushButton.setVisible(visible)

    def set_visibility_ZEN_security_settings(self, visible):
        """ Show or hide the block with the timelapse settings widgets.
        :param bool visible: show widgets = True, hide widgets = False """
        self._mw.Autofocus_security_Label.setVisible(visible)
        self._mw.reference_image_folder_Label.setVisible(visible)
        self._mw.Zen_saving_folder_Label.setVisible(visible)
        self._mw.reference_images_lineEdit.setVisible(visible)
        self._mw.Zen_saving_folder_lineEdit.setVisible(visible)
        self._mw.reference_images_pushButton.setVisible(visible)
        self._mw.Zen_saving_folder_pushButton.setVisible(visible)

# ----------------------------------------------------------------------------------------------------------------------
# Callbacks of the toolbuttons
# ----------------------------------------------------------------------------------------------------------------------

    def save_config_clicked(self):
        """ Callback of the save config toolbutton. Sends a signal to the logic indicating the complete path where
         the config file will be saved depending on the experimental setup, and the experiment.
        A default filename is used in the logic module which is linked to the taskrunner (experiments are run using the
        parameters in these default files.
        """
        path = os.path.join(self.default_location, 'qudi_task_config_files')
        experiment = self._mw.select_experiment_ComboBox.currentText()
        self.sigSaveConfig.emit(path, experiment, None)

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
        self._mw.laser_ComboBox.setCurrentIndex(0)
        self._mw.laser_intensity_DSpinBox.setValue(0.0)
        self._exp_logic.init_default_config_dict()

# ----------------------------------------------------------------------------------------------------------------------
# Callbacks of pushbuttons on the configuration form
# ----------------------------------------------------------------------------------------------------------------------

    def add_entry_clicked(self):
        """ Callback of add entry pushbutton inserting an item into the imaging sequence list. """
        lightsource = self._mw.laser_ComboBox.currentText()  # or replace by current index
        intensity = self._mw.laser_intensity_DSpinBox.value()

        if self._exp_logic.is_timelapse_ramm:
            num_z_planes = self._mw.num_z_planes_SpinBox.value()
            z_step = self._mw.z_step_DSpinBox.value()
            filter_pos = 0

        elif self._exp_logic.is_timelapse_palm:
            num_z_planes = self._mw.num_z_planes_SpinBox.value()
            z_step = self._mw.z_step_DSpinBox.value()
            filter_pos = self._mw.filterpos_ComboBox.currentIndex() + 1

        else:
            # dummy values
            num_z_planes = 0
            z_step = 0
            filter_pos = 0

        self.sigAddEntry.emit(lightsource, intensity, num_z_planes, z_step, filter_pos)

    def delete_entry_clicked(self):
        """ Callback of delete entry pushbutton. The selected item is deleted from the list model in the logic module.
        """
        indexes = self._mw.imaging_sequence_ListView.selectedIndexes()
        if indexes:
            # Indexes is a list of a single item in single-select mode.
            index = indexes[0]
            self.sigDeleteEntry.emit(index)

    def load_roi_list_clicked(self):
        """ Callback of load roi pushbutton. Opens a dialog to select the complete path to the roi list.
        """
        data_directory = os.path.join(self.default_location, 'qudi_roi_lists')
        this_file = QtWidgets.QFileDialog.getOpenFileName(self._mw,
                                                          'Open ROI list',
                                                          data_directory,
                                                          'json files (*.json)')[0]
        if this_file:
            self._mw.roi_list_path_LineEdit.setText(this_file)

    def load_injections_clicked(self):
        """ Callback of load injections pushbutton. Opens a dialog to select the complete path to the injections list.
        """
        data_directory = os.path.join(self.default_location, 'qudi_injection_parameters')
        this_file = QtWidgets.QFileDialog.getOpenFileName(self._mw,
                                                          'Open injections file',
                                                          data_directory,
                                                          'yml files (*.yml)')[0]
        # print(this_file)
        if this_file:
            self._mw.injections_list_LineEdit.setText(this_file)

    def load_dapi_path_clicked(self):
        """ Callback of load dapi path pushbutton. Opens a dialog to select the complete path to the folder with
        the associated dapi data, needed for data visualization and processing for experiment tracker app and / or
        simultaneous data analysis during a Hi-M experiment.
        """
        this_dir = QtWidgets.QFileDialog.getExistingDirectory(self._mw,
                                                          'Open DAPI directory',
                                                          '/home')  # to be changed using a correct path stem
        if this_dir:
            self._mw.dapi_data_LineEdit.setText(this_dir)

    def load_ref_images_path_clicked(self):
        """ Callback of reference_images pushbutton. Opens a dialog to select the complete path to the folder with
        the reference images, needed for the procedure checking the autofocus for the airyscan microscope.
        """
        this_dir = QtWidgets.QFileDialog.getExistingDirectory(self._mw,
                                                          'Open directory where reference images are saved',
                                                          r'W:')  # to be changed using a correct path stem
        if this_dir:
            self._mw.reference_images_lineEdit.setText(this_dir)

    def load_zen_saving_path_clicked(self):
        """ Callback of reference_images pushbutton. Opens a dialog to select the complete path to the folder where the
        data will be saved, needed for the procedure checking the autofocus for the airyscan microscope.
        """
        this_dir = QtWidgets.QFileDialog.getExistingDirectory(self._mw,
                                                          'Open directory where data are saved',
                                                          r"W:")  # to be changed using a correct path stem
        if this_dir:
            self._mw.Zen_saving_folder_lineEdit.setText(this_dir)

    def load_axial_calibration_path_clicked(self):
        """ Callback of load axial calibration path pushbutton. Opens a dialog to select the complete path to the folder
        with the associated calibration data. This file can be used for TFL experiment in order to skip the autofocus
        calibration.
        """
        # data_directory = os.path.join(self.default_location, 'qudi_roi_lists')
        this_file = QtWidgets.QFileDialog.getOpenFileName(self._mw,
                                                          'Open axial calibration file')[0]
        if this_file:
            self._mw.axial_calibration_path_lineEdit.setText(this_file)

# ----------------------------------------------------------------------------------------------------------------------
# Callbacks of signals sent from the logic
# ----------------------------------------------------------------------------------------------------------------------

    def update_entries(self):
        """ Callback of the signal sigConfigDictUpdated sent from the logic. Updates the values on the configuration
        form using the values stored in the config dict in the logic module. """
        self._mw.sample_name_LineEdit.setText(self._exp_logic.config_dict.get('sample_name', ''))
        self._mw.exposure_DSpinBox.setValue(self._exp_logic.config_dict.get('exposure', 0.0))
        self._mw.gain_SpinBox.setValue(self._exp_logic.config_dict.get('gain', 0))
        self._mw.num_frames_SpinBox.setValue(self._exp_logic.config_dict.get('num_frames', 1))
        self._mw.filterpos_ComboBox.setCurrentIndex(self._exp_logic.config_dict.get('filter_pos', 1) - 1)  # zero indexing
        self._exp_logic.img_sequence_model.layoutChanged.emit()
        self._exp_logic.img_sequence_model_timelapse_ramm.layoutChanged.emit()
        self._exp_logic.img_sequence_model_timelapse_palm.layoutChanged.emit()
        self._mw.save_path_LineEdit.setText(self._exp_logic.config_dict.get('save_path', ''))
        self._mw.save_network_path_LineEdit.setText(self._exp_logic.config_dict.get('save_network_path', ''))
        self._mw.fileformat_ComboBox.setCurrentText(self._exp_logic.config_dict.get('file_format', ''))
        self._mw.num_z_planes_SpinBox.setValue(self._exp_logic.config_dict.get('num_z_planes', 1))
        self._mw.z_step_DSpinBox.setValue(self._exp_logic.config_dict.get('z_step', 0.0))
        self._mw.centered_focal_plane_CheckBox.setChecked(self._exp_logic.config_dict.get('centered_focal_plane', False))
        self._mw.roi_list_path_LineEdit.setText(self._exp_logic.config_dict.get('roi_list_path', ''))
        self._mw.injections_list_LineEdit.setText(self._exp_logic.config_dict.get('injections_path', ''))
        self._mw.dapi_data_LineEdit.setText(self._exp_logic.config_dict.get('dapi_path', ''))
        self._mw.reference_images_lineEdit.setText(self._exp_logic.config_dict.get('zen_ref_images_path', ''))
        self._mw.Zen_saving_folder_lineEdit.setText(self._exp_logic.config_dict.get('zen_saving_path', ''))
        self._mw.illumination_time_DSpinBox.setValue(self._exp_logic.config_dict.get('illumination_time', 0.0))
        self._mw.num_iterations_SpinBox.setValue(self._exp_logic.config_dict.get('num_iterations', 0))
        self._mw.time_step_SpinBox.setValue(self._exp_logic.config_dict.get('time_step', 0))
        self._mw.axial_calibration_path_lineEdit.setText(self._exp_logic.config_dict.get('axial_calibration_path', ''))

    def update_listview(self):
        """ Callback of the signal sigImagingListChanged sent from the logic. Updates the items displayed in the
        imaging sequence listview. """
        self._exp_logic.img_sequence_model.layoutChanged.emit()
        self._exp_logic.img_sequence_model_timelapse_ramm.layoutChanged.emit()
        self._exp_logic.img_sequence_model_timelapse_palm.layoutChanged.emit()
        # for the delete entry case, if one row is selected then it will be deleted
        indexes = self._mw.imaging_sequence_ListView.selectedIndexes()
        if indexes:
            self._mw.imaging_sequence_ListView.clearSelection()

    def display_loaded_config(self):
        """ Callback of the signal sigConfigLoaded sent from the logic. Updates the displayed configuration form
        according to the experiment and shows the values defined in the loaded config file. """
        self._mw.select_experiment_ComboBox.setCurrentText(self._exp_logic.config_dict['experiment'])
        self.update_form()
        self.update_entries()

    def update_list_model(self, model):
        """ """
        if model == 1:  # timelapse ramm
            self._mw.imaging_sequence_ListView.setModel(self._exp_logic.img_sequence_model_timelapse_ramm)
        elif model == 2:  # timelapse palm
            self._mw.imaging_sequence_ListView.setModel(self._exp_logic.img_sequence_model_timelapse_palm)
        else:  # standard listview model (lightsource, intensity)
            self._mw.imaging_sequence_ListView.setModel(self._exp_logic.img_sequence_model)
