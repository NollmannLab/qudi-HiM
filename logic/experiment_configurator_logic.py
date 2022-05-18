# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains the logic for the experiment configurator.

An extension to Qudi.

@author: F. Barho

Created on Wed Feb 17 2021
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
import yaml
from qtpy import QtCore
from logic.generic_logic import GenericLogic
from core.configoption import ConfigOption
from core.connector import Connector


# ======================================================================================================================
# Child class of QAbstractListModel for List View
# ======================================================================================================================

class ImagingSequenceModel(QtCore.QAbstractListModel):
    """ This class contains the model class for the listview with the imaging sequence
    consisting of entries of the form (lightsource, intensity)
    """
    def __init__(self, *args, items=None, **kwargs):
        super(ImagingSequenceModel, self).__init__(*args, **kwargs)
        self.items = items or []

    def data(self, index, role):
        if role == QtCore.Qt.DisplayRole:
            source, intens = self.items[index.row()]
            return f'{source}: {intens}'

    def rowCount(self, index):
        return len(self.items)


class ImagingSequenceModelTimelapseRAMM(QtCore.QAbstractListModel):
    """ This class contains the model class for the listview with the imaging sequence
    consisting of entries of the form ({'laserline': lightsource, 'intensity': intensity, 'num_z_planes': num_z_planes,
    'z_step': z_step)
    """
    def __init__(self, *args, items=None, **kwargs):
        super(ImagingSequenceModelTimelapseRAMM, self).__init__(*args, **kwargs)
        self.items = items or []

    def data(self, index, role):
        if role == QtCore.Qt.DisplayRole:
            source, intens, num_z_planes, z_step = self.items[index.row()].values()
            return f"laserline: {source}, intensity: {intens}, num_z_planes: {num_z_planes}, z_step: {z_step}"

    def rowCount(self, index):
        return len(self.items)


class ImagingSequenceModelTimelapsePALM(QtCore.QAbstractListModel):
    """ This class contains the model class for the listview with the imaging sequence
    consisting of entries of the form ({'laserline': lightsource, 'intensity': intensity, 'num_z_planes': num_z_planes,
    'z_step': z_step, 'filter': filterpos)
    """
    def __init__(self, *args, items=None, **kwargs):
        super(ImagingSequenceModelTimelapsePALM, self).__init__(*args, **kwargs)
        self.items = items or []

    def data(self, index, role):
        if role == QtCore.Qt.DisplayRole:
            source, intens, num_z_planes, z_step, filter_pos = self.items[index.row()].values()
            return f"laserline: {source}, intensity: {intens}, num_z_planes: {num_z_planes}, z_step: {z_step}," \
                   f"filter_pos: {filter_pos}"

    def rowCount(self, index):
        return len(self.items)


# ======================================================================================================================
# Logic class
# ======================================================================================================================

class ExpConfigLogic(GenericLogic):
    """
    Class containing the logic for the definition of a configuration file for an experiment

    Example config for copy-paste:

    exp_config_logic:
        module.Class: 'experiment_configurator_logic.ExpConfigLogic'
        experiments:
            - 'Multichannel imaging'
            - 'Multichannel scan PALM'
            - 'Dummy experiment'
        supported fileformats:
            - 'tif'
            - 'fits'
        default path: '/home/barho'
        connect:
            camera_logic: 'camera_logic'
            laser_logic: 'lasercontrol_logic'
            filterwheel_logic: 'filterwheel_logic'
    """
    # define connectors to logic modules
    camera_logic = Connector(interface='CameraLogic')
    laser_logic = Connector(interface='LaserControlLogic')
    filterwheel_logic = Connector(interface='FilterwheelLogic')

    # signals
    sigConfigDictUpdated = QtCore.Signal()
    sigImagingListChanged = QtCore.Signal()
    sigConfigLoaded = QtCore.Signal()
    sigUpdateListModel = QtCore.Signal(int)

    # config options
    experiments = ConfigOption('experiments')
    supported_fileformats = ConfigOption('supported fileformats')
    default_path_images = ConfigOption('default path imagedata')
    default_network_path = ConfigOption('default network path')

    config_dict = {}

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self._camera_logic = None
        self._laser_logic = None
        self._filterwheel_logic = None
        self.filters = None
        self.lasers = None
        self.img_sequence_model = None
        self.is_timelapse_ramm = False
        self.is_timelapse_palm = False

    def on_activate(self):
        """ Initialisation performed during activation of the module.
        """
        self._camera_logic = self.camera_logic()
        self._laser_logic = self.laser_logic()
        self._filterwheel_logic = self.filterwheel_logic()

        # prepare the items that will be displayed in the ComboBoxes on the GUI
        filter_dict = self._filterwheel_logic.get_filter_dict()
        self.filters = [filter_dict[key]['name'] for key in filter_dict]
        laser_dict = self._laser_logic.get_laser_dict()
        self.lasers = [laser_dict[key]['wavelength'] for key in laser_dict]

        self.img_sequence_model = ImagingSequenceModel()
        self.img_sequence_model_timelapse_ramm = ImagingSequenceModelTimelapseRAMM()
        self.img_sequence_model_timelapse_palm = ImagingSequenceModelTimelapsePALM()

        # add an additional entry to the experiment selector combobox with placeholder text
        self.experiments.insert(0, 'Select your experiment..')

        self.init_default_config_dict()

    def on_deactivate(self):
        """ Perform required deactivation. """
        pass

# ----------------------------------------------------------------------------------------------------------------------
# Methods to load / save experiment config files
# ----------------------------------------------------------------------------------------------------------------------

    def init_default_config_dict(self):
        """ Initialize the entries of the dictionary with some default values,
        to set entries to the form displayed on the GUI on startup.
        NB : since the following entries are defined by default, they will not be mandatory for saving the form.
        """
        # self.config_dict = {}
        self.config_dict['dapi'] = False
        self.config_dict['rna'] = False
        self.config_dict['transfer_data'] = False
        self.config_dict['exposure'] = 0.05
        self.config_dict['gain'] = 0
        self.config_dict['num_frames'] = 1
        self.config_dict['filter_pos'] = 1
        self.img_sequence_model.items = []
        self.img_sequence_model_timelapse_ramm.items = []
        self.img_sequence_model_timelapse_palm.items = []
        self.config_dict['save_path'] = self.default_path_images
        self.config_dict['save_network_path'] = self.default_network_path
        self.config_dict['file_format'] = 'tif'
        self.config_dict['num_z_planes'] = 1
        self.config_dict['centered_focal_plane'] = False
        self.config_dict['dapi_path'] = ''
        # self.config_dict['zen_ref_images_path'] = ''
        # self.config_dict['zen_saving_path'] = ''
        self.config_dict['num_iterations'] = 0
        self.config_dict['time_step'] = 0
        self.config_dict['axial_calibration_path'] = ''
        # add here further dictionary entries that need initialization
        self.sigConfigDictUpdated.emit()

    def save_to_exp_config_file(self, path, experiment, filename=None):
        """ Saves the current config_dict to a yml file.

        :param: str path: path to directory where the config file is saved
        :param: str experiment: name of the experiment that shall be saved.
                        For clarity, always append the name of the experimental setup for which the task is destinated.
        :param: str filename: name of the config file including the suffix .yml. Default is None.
                            filename must only be given when using save copy of config file under a non-default name.

        :return: None
        """
        if not os.path.exists(path):
            try:
                os.makedirs(path)  # recursive creation of all directories on the path
            except Exception as e:
                self.log.error(f'Error {e}.')

        config_dict = {}

        print(f'Experiment = {experiment}')

        try:
            if experiment == 'Multicolor imaging PALM':
                if not filename:
                    filename = 'multicolor_imaging_task_PALM.yml'
                keys_to_extract = ['sample_name', 'filter_pos', 'exposure', 'gain', 'num_frames', 'save_path',
                                   'imaging_sequence', 'file_format']
                config_dict = {key: self.config_dict[key] for key in keys_to_extract}

            elif experiment == 'Multicolor scan PALM':
                if not filename:
                    filename = 'multicolor_scan_task_PALM.yml'
                keys_to_extract = ['sample_name', 'filter_pos', 'exposure', 'gain', 'num_frames', 'save_path',
                                   'file_format', 'imaging_sequence', 'num_z_planes', 'z_step', 'centered_focal_plane']
                config_dict = {key: self.config_dict[key] for key in keys_to_extract}

            elif experiment == 'Multicolor scan RAMM':
                if not filename:
                    filename = 'multicolor_scan_task_RAMM.yml'
                keys_to_extract = ['sample_name', 'exposure', 'save_path', 'file_format', 'imaging_sequence',
                                   'num_z_planes', 'z_step', 'centered_focal_plane']
                config_dict = {key: self.config_dict[key] for key in keys_to_extract}

            elif experiment == 'Multicolor scan Airyscan':
                if not filename:
                    filename = 'multicolor_scan_task_AIRYSCAN.yml'
                keys_to_extract = ['imaging_sequence', 'num_z_planes']
                config_dict = {key: self.config_dict[key] for key in keys_to_extract}

            elif experiment == 'ROI multicolor scan PALM':
                if not filename:
                    filename = 'ROI_multicolor_scan_task_PALM.yml'
                keys_to_extract = ['sample_name', 'filter_pos', 'exposure', 'gain', 'num_frames', 'save_path',
                                   'file_format', 'imaging_sequence', 'num_z_planes', 'z_step', 'centered_focal_plane',
                                   'roi_list_path']
                config_dict = {key: self.config_dict[key] for key in keys_to_extract}

            elif experiment == 'ROI multicolor scan RAMM':
                if not filename:
                    filename = 'ROI_multicolor_scan_task_RAMM.yml'
                keys_to_extract = ['sample_name', 'dapi', 'rna', 'exposure', 'save_path', 'file_format',
                                   'imaging_sequence', 'num_z_planes', 'z_step', 'roi_list_path',
                                   'centered_focal_plane']
                config_dict = {key: self.config_dict[key] for key in keys_to_extract}

            elif experiment == 'ROI multicolor scan Airyscan':
                if not filename:
                    filename = 'ROI_multicolor_scan_task_AIRYSCAN.yml'
                keys_to_extract = ['sample_name', 'dapi', 'rna', 'save_path', 'imaging_sequence', 'num_z_planes',
                                   'roi_list_path']
                config_dict = {key: self.config_dict[key] for key in keys_to_extract}

            elif experiment == 'Fluidics RAMM':
                if not filename:
                    filename = 'fluidics_task_RAMM.yml'
                keys_to_extract = ['injections_path']
                config_dict = {key: self.config_dict[key] for key in keys_to_extract}

            elif experiment == 'Fluidics Airyscan':
                if not filename:
                    filename = 'fluidics_task_AIRYSCAN.yml'
                keys_to_extract = ['injections_path']
                config_dict = {key: self.config_dict[key] for key in keys_to_extract}

            elif experiment == 'Hi-M RAMM':
                if not filename:
                    filename = 'hi_m_task_RAMM.yml'
                keys_to_extract = ['sample_name', 'exposure', 'save_path', 'save_network_path', 'transfer_data',
                                   'file_format', 'imaging_sequence', 'num_z_planes', 'z_step', 'centered_focal_plane',
                                   'roi_list_path', 'injections_path', 'dapi_path']
                config_dict = {key: self.config_dict[key] for key in keys_to_extract}

            elif experiment == 'Hi-M Airyscan Lumencor':
                if not filename:
                    filename = 'hi_m_task_AIRYSCAN.yml'
                    keys_to_extract = ['sample_name', 'save_path', 'imaging_sequence', 'num_z_planes', 'roi_list_path',
                                       'injections_path', 'dapi_path']
                    config_dict = {key: self.config_dict[key] for key in keys_to_extract}

            elif experiment == 'Hi-M Airyscan Lumencor Tissue':
                if not filename:
                    filename = 'hi_m_task_AIRYSCAN_tissue.yml'
                    keys_to_extract = ['sample_name', 'save_path', 'imaging_sequence', 'num_z_planes', 'roi_list_path',
                                       'injections_path', 'dapi_path', 'zen_ref_images_path', 'zen_saving_path']
                    config_dict = {key: self.config_dict[key] for key in keys_to_extract}

            elif experiment == 'Hi-M Airyscan Confocal':
                if not filename:
                    filename = 'hi_m_task_AIRYSCAN_confocal.yml'
                    keys_to_extract = ['sample_name', 'save_path', 'roi_list_path', 'injections_path', 'dapi_path']
                    config_dict = {key: self.config_dict[key] for key in keys_to_extract}

            elif experiment == 'Photobleaching RAMM':
                if not filename:
                    filename = 'photobleaching_task_RAMM.yml'
                keys_to_extract = ['imaging_sequence', 'roi_list_path', 'illumination_time']
                config_dict = {key: self.config_dict[key] for key in keys_to_extract}

            elif experiment == 'Photobleaching Airyscan':
                if not filename:
                    filename = 'photobleaching_task_AIRYSCAN.yml'
                keys_to_extract = ['imaging_sequence', 'roi_list_path', 'illumination_time']
                config_dict = {key: self.config_dict[key] for key in keys_to_extract}

            elif experiment == 'Fast timelapse RAMM':
                if not filename:
                    filename = 'fast_timelapse_task_RAMM.yml'
                keys_to_extract = ['sample_name', 'exposure', 'save_path', 'file_format', 'imaging_sequence',
                                   'num_z_planes', 'z_step', 'centered_focal_plane', 'roi_list_path', 'num_iterations',
                                   'axial_calibration_path']
                config_dict = {key: self.config_dict[key] for key in keys_to_extract}

            elif experiment == 'Hubble RAMM':
                if not filename:
                    filename = 'hubble_task_RAMM.yml'
                keys_to_extract = ['sample_name', 'exposure', 'save_path', 'file_format', 'imaging_sequence',
                                   'num_z_planes', 'z_step', 'centered_focal_plane', 'roi_list_path',
                                   'axial_calibration_path']
                config_dict = {key: self.config_dict[key] for key in keys_to_extract}

            elif experiment == 'Timelapse RAMM':
                if not filename:
                    filename = 'timelapse_task_RAMM.yml'
                keys_to_extract = ['sample_name', 'exposure', 'save_path', 'file_format', 'imaging_sequence',
                                   'centered_focal_plane', 'roi_list_path', 'num_iterations', 'time_step']
                config_dict = {key: self.config_dict[key] for key in keys_to_extract}

            elif experiment == 'Timelapse PALM':
                if not filename:
                    filename = 'timelapse_task_PALM.yml'
                keys_to_extract = ['sample_name', 'exposure', 'gain', 'save_path', 'file_format', 'imaging_sequence',
                                   'centered_focal_plane', 'roi_list_path', 'num_iterations', 'time_step']
                config_dict = {key: self.config_dict[key] for key in keys_to_extract}

            # add here all additional experiments and select the relevant keys
            else:
                pass

        except KeyError as e:
            self.log.warning(f'Experiment configuration not saved. Missing information {e}.')
            return

        config_dict['experiment'] = experiment
        complete_path = os.path.join(path, filename)
        print(complete_path)
        with open(complete_path, 'w') as file:
            yaml.safe_dump(config_dict, file, default_flow_style=False)
        self.log.info('Saved experiment configuration to {}'.format(complete_path))

    def load_config_file(self, path):
        """ Loads a configuration file and sets the entries of the config_dict accordingly

        :param: str path: complete path to an experiment configuration file
        :return: None
        """
        with open(path, 'r') as stream:
            data_dict = yaml.safe_load(stream)

        self.config_dict = data_dict

        # safety check: is at least the key 'experiment' contained in the file ?
        if 'experiment' not in self.config_dict.keys():
            self.log.warning('The loaded files does not contain necessary parameters. Configuration not loaded.')
            return
        else:
            self.log.info(f'Configuration loaded from {path}')

        if 'imaging_sequence' in self.config_dict.keys():

            if self.config_dict['experiment'] == 'Timelapse RAMM':
                self.sigUpdateListModel.emit(1)
                self.is_timelapse_ramm = True
                self.is_timelapse_palm = False
                for item in self.config_dict['imaging_sequence']:
                    lightsource = item['lightsource']
                    intensity = item['intensity']
                    num_z_planes = item['num_z_planes']
                    z_step = item['z_step']
                    self.img_sequence_model_timelapse_ramm.items.append(
                        {'lightsource': lightsource, 'intensity': intensity, 'num_z_planes': num_z_planes,
                         'z_step': z_step})

            elif self.config_dict['experiment'] == 'Timelapse PALM':
                self.sigUpdateListModel.emit(2)
                self.is_timelapse_palm = True
                self.is_timelapse_ramm = False
                for item in self.config_dict['imaging_sequence']:
                    lightsource = item['lightsource']
                    intensity = item['intensity']
                    num_z_planes = item['num_z_planes']
                    z_step = item['z_step']
                    filter_pos = item['filter_pos']
                    self.img_sequence_model_timelapse_palm.items.append(
                        {'lightsource': lightsource, 'intensity': intensity, 'num_z_planes': num_z_planes,
                         'z_step': z_step, 'filter_pos': filter_pos})

            else:
                self.sigUpdateListModel.emit(0)
                self.is_timelapse_ramm = False
                self.is_timelapse_palm = False
                # synchronize the listviewmodel with the config_dict['imaging_sequence'] entry
                self.img_sequence_model.items = self.config_dict['imaging_sequence']

        self.sigConfigLoaded.emit()

# ----------------------------------------------------------------------------------------------------------------------
# Methods to update dictionary entries on change of associated GUI element
# ----------------------------------------------------------------------------------------------------------------------

    @QtCore.Slot(str)
    def update_sample_name(self, name):
        """ Updates the dictionary entry 'sample_name'
        :param: str name: sample name
        :return: None
        """
        self.config_dict['sample_name'] = name
        self.sigConfigDictUpdated.emit()

    @QtCore.Slot(int)
    def update_is_dapi(self, state):
        """ Updates the dictionary entry 'dapi' (needed for the roi multicolor scan task, if this is the imaging
        experiment after dapi injection, the generated filename should then contain the label DAPI.
        :param: int state: Qt.CheckState of the dapi checkbox
        :return: None
        """
        if state == 2:  # Enum Qt::CheckState Checked = 2
            self.config_dict['dapi'] = True
        elif state == 0:  # Unchecked = 0
            self.config_dict['dapi'] = False
        self.sigConfigDictUpdated.emit()

    @QtCore.Slot(int)
    def update_is_rna(self, state):
        """ Updates the dictionary entry 'rna' (needed for the roi multicolor scan task, if the generated filename
        should contain the label RNA.
        :param: int state: Qt.CheckState of the rna checkbox
        :return: None
        """
        if state == 2:  # Enum Qt::CheckState Checked = 2
            self.config_dict['rna'] = True
        elif state == 0:  # Unchecked = 0
            self.config_dict['rna'] = False
        self.sigConfigDictUpdated.emit()

    @QtCore.Slot(int)
    def update_data_transfer(self, state):
        """ Updates the dictionary entry 'data_transfer' indicating whether the automatic transfer of the data to the
        server should be activated.
        :param: int state: Qt.CheckState of the data transfer checkbox
        :return: None
        """
        if state == 2:  # Enum Qt::CheckState Checked = 2
            self.config_dict['transfer_data'] = True
        elif state == 0:  # Unchecked = 0
            self.config_dict['transfer_data'] = False
        self.sigConfigDictUpdated.emit()

    @QtCore.Slot(float)
    def update_exposure(self, value):
        """ Updates the dictionary entry 'exposure'
        :param float value: new exposure value
        :return None
        """
        self.config_dict['exposure'] = value
        # update the gui in case this method was called from the ipython console
        self.sigConfigDictUpdated.emit()

    @QtCore.Slot(int)
    def update_gain(self, value):
        """ Updates the dictionary entry 'gain'.
        :param: int value: new gain value
        :return: None
        """
        self.config_dict['gain'] = value
        self.sigConfigDictUpdated.emit()

    @QtCore.Slot(int)
    def update_frames(self, value):
        """ Updates the dictionary entry 'num_frames' (number of frames per channel).
        :param: int value: new number of frames per channel
        :return: None
        """
        self.config_dict['num_frames'] = value
        self.sigConfigDictUpdated.emit()

    @QtCore.Slot(int)
    def update_filterpos(self, index):
        """ Updates the dictionary entry 'filter_pos'
        :param: int index: index of the element in the combobox representing the selected filter
        :return: None
        """
        self.config_dict['filter_pos'] = index + 1  # zero indexing !
        self.sigConfigDictUpdated.emit()

    @QtCore.Slot(str)
    def update_save_path(self, path):
        """ Updates the dictionary entry 'save_path' (path where image data is saved to).
        :param: str path: complete path where image data shall be saved
        :return: None
        """
        self.config_dict['save_path'] = path
        self.sigConfigDictUpdated.emit()

    @QtCore.Slot(str)
    def update_save_network_path(self, path):
        """ Updates the dictionary entry 'network_save_path' (path where image data will be uploaded).
        :param: str path: complete path where image et logging data shall be saved on the network
        :return: None
        """
        self.config_dict['save_network_path'] = path
        self.sigConfigDictUpdated.emit()

    @QtCore.Slot(str)
    def update_fileformat(self, entry):
        """ Updates the dictionary entry 'fileformat'.
        :param: str entry: desired fileformat for image data, such as 'tif' or 'fits'.
        :return: None
        """
        self.config_dict['file_format'] = entry
        self.sigConfigDictUpdated.emit()

    @QtCore.Slot(int)
    def update_num_z_planes(self, value):
        """ Updates the dictionary entry 'num_z_planes' (number of planes in a z stack for scan experiments).
        :param: int value: number of planes in the z stack.
        :return: None
        """
        self.config_dict['num_z_planes'] = value
        self.sigConfigDictUpdated.emit()

    @QtCore.Slot(float)
    def update_z_step(self, value):
        """ Updates the dictionary entry 'z_step' (step between two planes in a z stack).
        :param: float value: step between two planes in a z stack in um
        :return: None
        """
        self.config_dict['z_step'] = value
        self.sigConfigDictUpdated.emit()

    @QtCore.Slot(int)
    def update_centered_focal_plane(self, state):
        """ Updates the dictionary entry 'centered_focal_plane'
        (z stack starting at bottom plane if False, or taking current plane as center plane if True).
        :param: int state: Qt.CheckState of the centered_focal_plane checkbox
        :return: None
        """
        if state == 2:  # Enum Qt::CheckState Checked = 2
            self.config_dict['centered_focal_plane'] = True
        elif state == 0:  # Unchecked = 0
            self.config_dict['centered_focal_plane'] = False
        self.sigConfigDictUpdated.emit()

    @QtCore.Slot(str)
    def update_roi_path(self, path):
        """ Updates the dictionary entry 'roi_list_path' (path to the roi list).
        :param: str path: complete path to the roi list
        :return: None
        """
        self.config_dict['roi_list_path'] = path
        self.sigConfigDictUpdated.emit()

    @QtCore.Slot(str)
    def update_injections_path(self, path):
        """ Updates the dictionary entry 'injections_path' (path to the injections list).
        :param: str path: complete path to the injections list
        :return: None"""
        self.config_dict['injections_path'] = path
        self.sigConfigDictUpdated.emit()

    @QtCore.Slot(str)
    def update_dapi_path(self, path):
        """ Updates the dictionary entry 'dapi_path' (path to the folder containing the associated dapi data for a
        Hi-M experiment).
        :param: str path: complete path to the folder containing the dapi data
        :return: None"""
        self.config_dict['dapi_path'] = path
        self.sigConfigDictUpdated.emit()

    @QtCore.Slot(str)
    def update_zen_ref_images_path(self, path):
        """ Updates the dictionary entry 'zen_ref_images_path' (path to the folder containing the reference images used
        to test the quality of the autofocus during a Hi-M experiment).
        :param: str path: complete path to the folder containing the reference images
        :return: None"""
        self.config_dict['zen_ref_images_path'] = path
        self.sigConfigDictUpdated.emit()

    @QtCore.Slot(str)
    def update_zen_saving_path(self, path):
        """ Updates the dictionary entry 'zen_saving_path' (path to the folder where the data will be saved during a
        Hi-M experiment).
        :param: str path: complete path to the folder where the data will be saved
        :return: None"""
        self.config_dict['zen_saving_path'] = path
        self.sigConfigDictUpdated.emit()

    @QtCore.Slot(str)
    def update_axial_calibration_path(self, path):
        """ Updates the dictionary entry 'axial_calibration_path' (path to the folder containing the associated axial
        calibration for the FTL experiment).
        :param: str path: complete path to the folder containing the axial calibration data
        :return: None"""
        self.config_dict['axial_calibration_path'] = path
        self.sigConfigDictUpdated.emit()

    @QtCore.Slot(float)
    def update_illumination_time(self, value):
        """ Updates the dictionary entry 'illumination_time' (laser-on time for photobleaching).
        :param: float value: illumination time for a photobleaching task in min (or fractions of min allowed)
        :return: None
        """
        self.config_dict['illumination_time'] = value
        self.sigConfigDictUpdated.emit()

    @QtCore.Slot(int)
    def update_num_iterations(self, value):
        """ Updates the dictionary entry 'num_iterations' (repetitions during a timelapse).
        :param: int value: number of iterations for a timelapse experiment
        :return: None
        """
        self.config_dict['num_iterations'] = value
        self.sigConfigDictUpdated.emit()

    @QtCore.Slot(int)
    def update_time_step(self, value):
        """ Updates the dictionary entry 'time_step' (delay before entering into the next iteration in a (slow) timelapse).
        :param: int value: time in seconds since start before entering into the next timelapse iteration
        :return: None
        """
        self.config_dict['time_step'] = value
        self.sigConfigDictUpdated.emit()

    @QtCore.Slot(str, float, int, float, int)
    def add_entry_to_imaging_list(self, lightsource, intensity, num_z_planes=None, z_step=None, filter_pos=None):
        """ Adds an entry to the imaging sequence.
        :param: str lightsource: name of the lightsource as displayed in the combobox on the GUI.
                    (May need conversion inside the experiment module to address the right lightsource)
        :param: float intensity: intensity in percent of max. intensity
        :return: None
        """
        if self.is_timelapse_ramm:
            self.img_sequence_model_timelapse_ramm.items.append(
                {'lightsource': lightsource, 'intensity': intensity, 'num_z_planes': num_z_planes, 'z_step': z_step})
            self.config_dict['imaging_sequence'] = self.img_sequence_model_timelapse_ramm.items

        elif self.is_timelapse_palm:
            self.img_sequence_model_timelapse_palm.items.append(
                {'lightsource': lightsource, 'intensity': intensity, 'num_z_planes': num_z_planes, 'z_step': z_step,
                 'filter_pos': filter_pos})
            self.config_dict['imaging_sequence'] = self.img_sequence_model_timelapse_palm.items

        else:
            # Access the list via the model.
            self.img_sequence_model.items.append((lightsource, intensity))
            # update the dictionary entry with the current content of the model
            self.config_dict['imaging_sequence'] = self.img_sequence_model.items

        # Trigger refresh of the listview on the GUI:
        # signal layoutChanged cannot be queued over different threads. use custom signal
        self.sigImagingListChanged.emit()

    @QtCore.Slot(QtCore.QModelIndex)
    def delete_entry_from_imaging_list(self, index):
        """ Deletes a selected entry from the imaging sequence.
        :param: QtCore.QModelIndex index: selected element in the imaging seqeunce model
        :return: None
        """
        if self.is_timelapse_ramm:
            del self.img_sequence_model_timelapse_ramm.items[index.row()]
            self.config_dict['imaging_sequence'] = self.img_sequence_model_timelapse_ramm.items

        elif self.is_timelapse_palm:
            del self.img_sequence_model_timelapse_palm.items[index.row()]
            self.config_dict['imaging_sequence'] = self.img_sequence_model_timelapse_palm.items

        else:
            # Remove the item and refresh.
            del self.img_sequence_model.items[index.row()]
            # update the dictionary entry with the current content of the model
            self.config_dict['imaging_sequence'] = self.img_sequence_model.items

        # Trigger refresh of the livtview on the GUI
        self.sigImagingListChanged.emit()

    @QtCore.Slot()
    def delete_imaging_list(self):
        """ Deletes the complete imaging sequence.
        :return: None
        """
        self.img_sequence_model.items = []
        self.img_sequence_model_timelapse_ramm.items = []
        self.img_sequence_model_timelapse_palm.items = []
        self.sigImagingListChanged.emit()

# ----------------------------------------------------------------------------------------------------------------------
# Methods to retrieve current values from devices
# ----------------------------------------------------------------------------------------------------------------------

    def get_exposure(self):
        """ Get the currently set exposure time from the camera logic and write it to the config dict.
        :return: None
        """
        exposure = self._camera_logic.get_exposure()
        self.config_dict['exposure'] = exposure
        self.sigConfigDictUpdated.emit()

    def get_gain(self):
        """ Get the current gain setting from the camera logic and write it to the config dict.
        :return: None
        """
        gain = self._camera_logic.get_gain()
        self.config_dict['gain'] = gain
        self.sigConfigDictUpdated.emit()

    def get_filterpos(self):
        """ Get the currently set filter position from the filterwheel logic and write it to the config dict.
        :return: None
        """
        filterpos = self._filterwheel_logic.get_position()
        self.config_dict['filter_pos'] = filterpos
        self.sigConfigDictUpdated.emit()
