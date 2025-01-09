# -*- coding: utf-8 -*-
"""
Qudi-CBS

An extension to Qudi.

This module contains a task to perform a multicolor scan on PALM setup.
(Take at a given position a sequence of images in a stack of planes with different laserlines or intensities.)

@author: F. Barho - JB Fiche for later modifications

Created on Wed Mar 17 2021 - modified Thur Jan 09 2025
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
# import yaml
import os
from time import sleep
from logic.generic_task import InterruptableTask
from logic.task_helper_functions import get_entry_nested_dict
from ruamel.yaml import YAML
from datetime import datetime


# ======================================================================================================================
# YAML file editor function for editing metadata
# ======================================================================================================================
def update_metadata(metadata, key_path, value, action="set"):
    """
    Generalized function to update nested metadata fields, including lists.
    @param: metadata: The metadata structure (OrderedDict or dict).
    @param: key_path: A list representing the nested path to the key.
    @param: value: The value to set, append, or remove.
    @param: action: The action to perform: "set", "append", or "remove".
            - "set" (default): Replaces the value.
            - "append": Adds to the list if it doesn't already exist.
    @return: The updated metadata structure.
    """
    current = metadata
    # Navigate to the parent of the target key
    for key in key_path[:-1]:
        if isinstance(current, list):
            # Look for the key in a list of dictionaries or OrderedDicts
            for item in current:
                if key in item:
                    current = item[key]
                    break
        else:
            current = current[key]

    # Perform the specified action on the target key
    target_key = key_path[-1]
    if isinstance(current, list):
        # Handle lists of dictionaries
        for item in current:
            if target_key in item:
                if action == "set":
                    item[target_key] = value
                elif action == "append":
                    if isinstance(item[target_key], list):
                        item[target_key].append(value)
                break
        else:
            # If key not found in list, create it (for append action)
            if action == "append":
                current.append({target_key: [value]})
    else:
        # Handle direct dictionary updates
        if action == "set":
            current[target_key] = value
        elif action == "append":
            if target_key not in current:
                current[target_key] = [value]
            elif isinstance(current[target_key], list):
                current[target_key].append(value)

    return metadata


# ======================================================================================================================
# TASK definition
# ======================================================================================================================
class Task(InterruptableTask):  # do not change the name of the class. it is always called Task !
    """ This task does an acquisition of a stack of images from different channels or using different intensities.

    Config example pour copy-paste:

    MulticolorScanTask:
        module: 'multicolor_scan_task_PALM'
        needsmodules:
            camera: 'camera_logic'
            daq: 'lasercontrol_logic'
            filter: 'filterwheel_logic'
            focus: 'focus_logic'
        config:
            path_to_user_config: 'C:/Users/admin/qudi_files/qudi_task_config_files/multicolor_scan_task_PALM.yml'
    """
    # ==================================================================================================================
    # Generic Task methods
    # ==================================================================================================================

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        print('Task {0} added!'.format(self.name))
        self.user_config_path = self.config['path_to_user_config']
        self.metadata_template_path = self.config['path_to_metadata_template']
        self.err_count = None
        self.laser_allowed = False
        self.user_param_dict = {}
        self.yaml = YAML()
        self.metadata_template: dict = {}
        self.metadata: dict = {}
        self.step_counter: int = 0
        self.sample_name: str = ""
        self.filter_pos: dict = {}
        self.exposure: float = 0
        self.gain: int = 0
        self.num_frames: int = 0
        self.num_z_planes: int = 0
        self.z_step: int = 0
        self.centered_focal_plane: bool = False
        self.save_path: str = ""
        self.imaging_sequence_raw: dict = {}
        self.file_format: dict = {}
        self.imaging_sequence: list = []
        self.num_laserlines: int = 0
        self.complete_path: str = ""
        self.start_position: float = 0
        self.focal_plane_position: float = 0

    def startTask(self):
        """ """
        self.log.info('started Task')
        self.err_count = 0  # initialize the error counter (counts number of missed triggers for debug)

        # stop all interfering modes on GUIs and disable GUI actions. Make sure the camera is not in Frame Transfer mode
        self.ref['camera'].stop_live_mode()
        self.ref['camera'].disable_camera_actions()
        if self.ref['camera'].frame_transfer:
            self.log.warning('Frame Transfer mode is now switched OFF.')
            self.ref['camera'].disable_frame_transfer()

        self.ref['daq'].stop_laser_output()
        self.ref['daq'].disable_laser_actions()

        self.ref['filter'].disable_filter_actions()

        self.ref['focus'].stop_autofocus()
        self.ref['focus'].disable_focus_actions()

        # read all user parameters from config
        self.load_user_parameters()

        # control the config : laser allowed for given filter ?
        self.laser_allowed = self.control_user_parameters()
        if not self.laser_allowed:
            self.log.warning('Task aborted. Please specify a valid filter / laser combination')
            return

        # preparation steps
        # set the filter to the specified position (changing filter not allowed during task because this is too slow)
        self.ref['filter'].set_position(self.filter_pos)
        # wait until filter position set
        pos = self.ref['filter'].get_position()
        while not pos == self.filter_pos:
            sleep(1)
            pos = self.ref['filter'].get_position()

        # prepare the camera
        frames = len(self.imaging_sequence) * self.num_frames * self.num_z_planes
        self.ref['camera'].prepare_camera_for_multichannel_imaging(frames, self.exposure, self.gain,
                                                                   self.complete_path.rsplit('.', 1)[0],
                                                                   self.file_format)

        # load the metadata template and update it according to the parameters
        with open(self.metadata_template_path, "r", encoding='utf-8') as file:
            self.metadata_template = self.yaml.load(file)
        self.metadata_template = dict(self.metadata_template)
        self.metadata = self._create_metadata_dict(frames)

        # initialize the counter (corresponding to the number of planes already acquired)
        self.step_counter = 0

    def runTaskStep(self):
        """ Implement one work step of your task here.
        @return (bool): True if the task should continue running, False if it should finish.
        """
        if not self.laser_allowed:
            return False  # skip runTaskStep and directly go to cleanupTask

        # --------------------------------------------------------------------------------------------------------------
        # position the piezo
        # --------------------------------------------------------------------------------------------------------------
        self.step_counter += 1
        print(f'plane number {self.step_counter}')

        position = self.start_position + (self.step_counter - 1) * self.z_step
        self.ref['focus'].go_to_position(position)
        sleep(0.03)  # stabilization time

        # --------------------------------------------------------------------------------------------------------------
        # imaging sequence (image data is spooled to disk)
        # --------------------------------------------------------------------------------------------------------------
        # outer loop over the number of frames per color
        for j in range(self.num_frames):  # per default only one frame per plane per color but keep it as an option 

            # use a while loop to catch the exception when a trigger is missed and just repeat the last (missed) image
            i = 0
            while i < len(self.imaging_sequence):
                # reset the intensity dict to zero
                self.ref['daq'].reset_intensity_dict()
                # prepare the output value for the specified channel
                self.ref['daq'].update_intensity_dict(self.imaging_sequence[i][0], self.imaging_sequence[i][1])
                # waiting time for stability of the synchronization
                sleep(0.05)
            
                # switch the laser on and send the trigger to the camera
                self.ref['daq'].apply_voltage()
                err = self.ref['daq'].send_trigger_and_control_ai()  
            
                # read fire signal of camera and switch off when the signal is low
                ai_read = self.ref['daq'].read_trigger_ai_channel()
                count = 0
                while not ai_read <= 2.5:  # analog input varies between 0 and 5 V. use max/2 to check if signal is low
                    sleep(0.001)  # read every ms
                    ai_read = self.ref['daq'].read_trigger_ai_channel()
                    count += 1  # can be used for control and debug
                self.ref['daq'].voltage_off()
                # self.log.debug(f'iterations of read analog in - while loop: {count}')
            
                # waiting time for stability
                sleep(0.05)

                # repeat the last step if the trigger was missed
                if err < 0:
                    self.err_count += 1  # control value to check how often a trigger was missed
                    i = i  # then the last iteration will be repeated
                else:
                    i += 1  # increment to continue with the next image

        return self.step_counter < self.num_z_planes

    def pauseTask(self):
        """ """
        self.log.info('pauseTask called')

    def resumeTask(self):
        """ """
        self.log.info('resumeTask called')

    def cleanupTask(self):
        """ """
        self.log.info('cleanupTask called')

        # reset piezo position to the initial one
        self.ref['focus'].go_to_position(self.focal_plane_position)

        # reset the camera to default state
        self.ref['camera'].reset_camera_after_multichannel_imaging()
        # self.ref['camera'].set_exposure(self.default_exposure)

        self.ref['daq'].voltage_off()  # as security
        self.ref['daq'].reset_intensity_dict()

        # save metadata if task has not been aborted during acquisition
        if self.step_counter == self.num_z_planes:
            if self.file_format == 'fits':
                metadata = self.get_fits_metadata()
                self.ref['camera'].add_fits_header(self.complete_path, metadata)
            else:  # save metadata in a txt file
                # metadata = self.get_metadata()
                file_path = self.complete_path.replace('tif', 'txt', 1)
                # self.save_metadata_file(metadata, file_path)
                self.save_metadata_txt_file(self.metadata, file_path)

        # enable gui actions
        self.ref['camera'].enable_camera_actions()
        self.ref['daq'].enable_laser_actions()
        self.ref['filter'].enable_filter_actions()
        self.ref['focus'].enable_focus_actions()

        self.log.debug(f'number of missed triggers: {self.err_count}')
        self.log.info('cleanupTask finished')

    # ==================================================================================================================
    # Helper functions
    # ==================================================================================================================

    # ------------------------------------------------------------------------------------------------------------------
    # user parameters
    # ------------------------------------------------------------------------------------------------------------------

    def load_user_parameters(self):
        """ This function is called from startTask() to load the parameters given by the user in a specific format.

        Specify the path to the user defined config for this task in the (global) config of the experimental setup.

        user must specify the following dictionary (here with example entries):
            sample_name: 'Mysample'
            filter_pos: 1
            exposure: 0.05  # in s
            gain: 0
            num_frames: 1  # number of frames per color
            num_z_planes: 50
            z_step: 0.25  # in um
            centered_focal_plane: False
            save_path: 'E:\'
            file_format: 'tif'
            imaging_sequence = [('488 nm', 3), ('561 nm', 3), ('641 nm', 10)]
        """
        try:
            with open(self.user_config_path, 'r') as stream:
                self.user_param_dict = self.yaml.load(stream)

                self.sample_name = self.user_param_dict['sample_name']
                self.filter_pos = self.user_param_dict['filter_pos']
                self.exposure = self.user_param_dict['exposure']
                self.gain = self.user_param_dict['gain']
                self.num_frames = self.user_param_dict['num_frames']
                self.num_z_planes = self.user_param_dict['num_z_planes']
                self.z_step = self.user_param_dict['z_step']  # in um
                self.centered_focal_plane = self.user_param_dict['centered_focal_plane']
                self.save_path = self.user_param_dict['save_path']
                self.imaging_sequence_raw = self.user_param_dict['imaging_sequence']
                self.file_format = self.user_param_dict['file_format']

        except Exception as e:  # add the type of exception
            self.log.warning(f'Could not load user parameters for task {self.name}: {e}')
            return

        # establish further user parameters derived from the given ones:
        # for the imaging sequence, we need to access the corresponding labels
        laser_dict = self.ref['daq'].get_laser_dict()
        imaging_sequence = [(*get_entry_nested_dict(laser_dict, self.imaging_sequence_raw[i][0], 'label'),
                             self.imaging_sequence_raw[i][1]) for i in range(len(self.imaging_sequence_raw))]
        self.log.info(imaging_sequence)
        self.imaging_sequence = imaging_sequence
        # new format: self.imaging_sequence = [('laser2', 10), ('laser2', 20), ('laser3', 10)]

        self.num_laserlines = len(self.imaging_sequence)

        self.complete_path = self.get_complete_path(self.save_path)

        self.start_position = self.calculate_start_position(self.centered_focal_plane)

    def control_user_parameters(self):
        """ This method checks if the laser lines that will be used are compatible with the chosen filter.
        :return bool: lasers_allowed
        """
        # use the filter position to create the key # simpler than using get_entry_netsted_dict method
        key = 'filter{}'.format(self.filter_pos)
        bool_laserlist = self.ref['filter'].get_filter_dict()[key]['lasers']
        forbidden_lasers = []
        for i, item in enumerate(bool_laserlist):
            if not item:  # if the element in the list is False:
                label = 'laser'+str(i+1)
                forbidden_lasers.append(label)      
        lasers_allowed = True  # as initialization
        for item in forbidden_lasers:
            if item in [self.imaging_sequence[i][0] for i in range(len(self.imaging_sequence))]:
                lasers_allowed = False
                break  # stop if at least one forbidden laser is found
        return lasers_allowed       
        
    def calculate_start_position(self, centered_focal_plane):
        """
        This method calculates the piezo position at which the z stack will start. It can either start in the
        current plane or calculate an offset so that the current plane will be centered inside the stack.

        :param: bool centered_focal_plane: indicates if the scan is done below and above the focal plane (True)
                                            or if the focal plane is the bottommost plane in the scan (False)

        :return: float piezo start position
        """
        current_pos = self.ref['focus'].get_position()
        self.focal_plane_position = current_pos  # save it to come back to this plane at the end of the task

        # the scan should start below the current position so that the focal plane will be the central plane or one of
        # the central planes in case of an even number of planes
        if centered_focal_plane:
            # even number of planes:
            if self.num_z_planes % 2 == 0:
                start_pos = current_pos - self.num_z_planes / 2 * self.z_step
            # odd number of planes:
            else:
                start_pos = current_pos - (self.num_z_planes - 1)/2 * self.z_step
            return start_pos
        else:
            return current_pos  # the scan starts at the current position and moves up

    # ------------------------------------------------------------------------------------------------------------------
    # file path handling
    # ------------------------------------------------------------------------------------------------------------------

    def get_complete_path(self, path_stem):
        """ Create the complete path based on path_stem given as user parameter,
        such as path_stem/YYYY_MM_DD/001_Scan_samplename/scan_001.tif
        or path_stem/YYYY_MM_DD/027_Scan_samplename/scan_027.fits

        :param: str path_stem such as E:/
        :return: str complete path (see examples above)
        """
        cur_date = datetime.today().strftime('%Y_%m_%d')

        path_stem_with_date = os.path.join(path_stem, cur_date)

        # check if folder path_stem/cur_date exists, if not: create it
        if not os.path.exists(path_stem_with_date):
            try:
                os.makedirs(path_stem_with_date)  # recursive creation of all directories on the path
            except Exception as e:
                self.log.error('Error {0}'.format(e))

        # count the subdirectories in the directory path (non recursive !) to generate an incremental prefix
        dir_list = [folder for folder in os.listdir(path_stem_with_date) if
                    os.path.isdir(os.path.join(path_stem_with_date, folder))]
        number_dirs = len(dir_list)

        prefix = str(number_dirs + 1).zfill(3)
        foldername = f'{prefix}_Scan_{self.sample_name}'

        path = os.path.join(path_stem_with_date, foldername)

        # create the path  # no need to check if it already exists due to incremental prefix
        try:
            os.makedirs(path)  # recursive creation of all directories on the path
        except Exception as e:
            self.log.error('Error {0}'.format(e))

        file_name = f'scan_{prefix}.{self.file_format}'
        complete_path = os.path.join(path, file_name)
        return complete_path

    # ------------------------------------------------------------------------------------------------------------------
    # metadata
    # ------------------------------------------------------------------------------------------------------------------

    # def get_metadata(self):
    #     """ Get a dictionary containing the metadata in a plain text easy readable format.
    #
    #     :return: dict metadata
    #     """
    #     metadata = {}
    #     metadata['Time'] = datetime.now().strftime(
    #         '%m-%d-%Y, %H:%M:%S')  # or take the starting time of the acquisition instead ???
    #     metadata['Sample name'] = self.sample_name
    #     metadata['Exposure time (s)'] = self.exposure
    #     metadata['Kinetic time (s)'] = self.ref['camera'].get_kinetic_time()
    #     metadata['Gain'] = self.gain
    #     metadata['Sensor temperature (deg C)'] = self.ref['camera'].get_temperature()
    #     filterpos = self.ref['filter'].get_position()
    #     filterdict = self.ref['filter'].get_filter_dict()
    #     label = 'filter{}'.format(filterpos)
    #     metadata['Filter'] = filterdict[label]['name']
    #     metadata['Number laserlines'] = self.num_laserlines
    #     imaging_sequence = self.imaging_sequence_raw
    #     for i in range(self.num_laserlines):
    #         metadata[f'Laser line {i + 1}'] = imaging_sequence[i][0]
    #         metadata[f'Laser intensity {i + 1} (%)'] = imaging_sequence[i][1]
    #     metadata['Scan step length (um)'] = self.z_step
    #     metadata['Scan total length (um)'] = self.z_step * self.num_z_planes
    #     # pixel size ???
    #     return metadata

    def _create_metadata_dict(self, n_frames):
        """ create a dictionary containing the metadata.
        @param: (int) number of frames required for the acquisition
        @return: (dict) metadata
        """
        metadata = self.metadata_template
        # ----general----------------------------------------------------------------------------
        metadata['Time'] = datetime.now().strftime('%m-%d-%Y, %H:%M:%S')

        # ----camera-----------------------------------------------------------------------------
        metadata = update_metadata(metadata, ['Acquisition', 'number_frames'], n_frames)
        metadata = update_metadata(metadata, ['Acquisition', 'sample_name'], self.sample_name)
        metadata = update_metadata(metadata, ['Acquisition', 'exposure_time_(s)'], self.exposure)
        metadata = update_metadata(metadata, ['Acquisition', 'kinetic_time_(s)'], self.ref['camera'].get_kinetic_time())
        metadata = update_metadata(metadata, ['Acquisition', 'number_z_planes'], self.num_z_planes)
        metadata = update_metadata(metadata, ['Acquisition', 'distance_z_planes_(µm)'], self.z_step)
        metadata = update_metadata(metadata, ['Acquisition', 'number_frames_per_z_plane'], len(self.imaging_sequence) *
                                   self.num_frames)

        parameters = self.ref['camera'].get_non_interfaced_parameters()
        for key, value in parameters.items():
            metadata = update_metadata(metadata, ['Camera', 'specific_parameters', key], value)
        metadata = update_metadata(metadata, ['Acquisition', 'gain'], self.gain)
        if self.ref['camera'].has_temp:
            metadata = update_metadata(metadata, ['Acquisition', 'sensor_temperature_setpoint_(°C)'],
                                       self.ref['camera'].get_temperature())
        else:
            metadata = update_metadata(metadata, ['Acquisition', 'sensor_temperature_setpoint_(°C)'],
                                       "Not available")

        # ----filter------------------------------------------------------------------------------
        filterpos = self.ref['filter'].get_position()
        filterdict = self.ref['filter'].get_filter_dict()
        label = 'filter{}'.format(filterpos)
        metadata = update_metadata(metadata, ['Acquisition', 'filter'], filterdict[label]['name'])

        # ----laser-------------------------------------------------------------------------------
        for laser_lines in range(self.num_laserlines):
            metadata = update_metadata(metadata, ['Acquisition', 'laser_lines'],
                                       self.imaging_sequence_raw[laser_lines][0],
                                       action="append")
            metadata = update_metadata(metadata, ['Acquisition', 'laser_power_(%)'],
                                       self.imaging_sequence_raw[laser_lines][1],
                                       action="append")
        return metadata

    def get_fits_metadata(self):
        """ Get a dictionary containing the metadata in a fits header compatible format.

        :return: dict metadata
        """
        metadata = {'TIME': datetime.now().strftime('%m-%d-%Y, %H:%M:%S'), 'SAMPLE': (self.sample_name, 'sample name'),
                    'EXPOSURE': (self.exposure, 'exposure time (s)'),
                    'KINETIC': (self.ref['camera'].get_kinetic_time(), 'kinetic time (s)'), 'GAIN': (self.gain, 'gain'),
                    'TEMP': (self.ref['camera'].get_temperature(), 'sensor temperature (deg C)')}
        filterpos = self.ref['filter'].get_position()
        filterdict = self.ref['filter'].get_filter_dict()
        label = 'filter{}'.format(filterpos)
        metadata['FILTER'] = (filterdict[label]['name'], 'filter')
        metadata['CHANNELS'] = (self.num_laserlines, 'number laserlines')
        for i in range(self.num_laserlines):
            metadata[f'LINE{i + 1}'] = (self.imaging_sequence_raw[i][0], f'laser line {i + 1}')
            metadata[f'INTENS{i + 1}'] = (self.imaging_sequence_raw[i][1], f'laser intensity {i + 1}')
        metadata['Z_STEP'] = (self.z_step, 'scan step length (um)')
        metadata['Z_TOTAL'] = (self.z_step * self.num_z_planes, 'scan total length (um)')
        # pixel size
        return metadata

    # def save_metadata_file(self, metadata, path):
    #     """ Save a txt file containing the metadata dictionary
    #
    #     :param dict metadata: dictionary containing the metadata
    #     :param str path: pathname
    #     """
    #     with open(path, 'w') as outfile:
    #         self.yaml.safe_dump(metadata, outfile, default_flow_style=False)
    #     self.log.info('Saved metadata to {}'.format(path))

    def save_metadata_txt_file(self, metadata, path):
        """ Save a txt file containing the metadata.
        @param: (str) path : complete path for the metadata file
        @param: (dict) metadata: dictionary containing the annotations
        """
        with open(path, 'w') as file:
            self.yaml.dump(metadata, file)
        self.log.info('Saved metadata to {}'.format(path))
