# -*- coding: utf-8 -*-
"""
Qudi-CBS

An extension to Qudi.

This module contains a task to perform a multicolor scan on the RAMM setup equiped with a Celesta Lumencor laser source.
(Take at a given position a stack of images using a sequence of different laserlines or intensities in each plane of the
 stack.)

@author: JB. Fiche (from F. Barho original code)

Created on Tue January 9, 2024 - last update Fri Jan 17, 2025
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
# import yaml
import numpy as np
from datetime import datetime
from time import sleep, time
from logic.generic_task import InterruptableTask
from logic.task_helper_functions import save_z_positions_to_file
from ruamel.yaml import YAML


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
    """ This task acquires a stack of images using a sequence of lightsources for each plane.

    Config example pour copy-paste:

    MulticolorScanTask:
        module: 'multicolor_scan_task_RAMM'
        needsmodules:
            laser: 'lasercontrol_logic'
            bf: 'brightfield_logic'
            cam: 'camera_logic'
            daq: 'nidaq_logic'
            focus: 'focus_logic'
        config:
            path_to_user_config: 'C:/Users/sCMOS-1/qudi_files/qudi_task_config_files/multicolor_scan_task_RAMM.yml'
    """
    # ==================================================================================================================
    # Generic Task methods
    # ==================================================================================================================

    FPGA_max_laserlines = 10

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        print('Task {0} added!'.format(self.name))
        self.user_config_path: str = self.config['path_to_user_config']
        self.metadata_template_path = self.config['path_to_metadata_template']
        self.yaml = YAML()
        self.celesta_laser_dict: dict = {}
        self.celesta_intensity_dict: dict = {}
        self.FPGA_wavelength_channels: list = []
        self.num_laserlines: int = 0
        self.step_counter: int = 0
        self.user_param_dict = {}
        self.timeout: float = 0
        self.z_target_positions: list = []
        self.z_actual_positions: list = []
        self.num_frames: int = 0
        self.default_exposure: float = 0
        self.sample_name: str = ""
        self.exposure: float = 0
        self.num_z_planes: int = 0
        self.z_step: int = 0
        self.centered_focal_plane: bool = False
        self.imaging_sequence: list = []
        self.save_path: str = ""
        self.file_format: str = ""
        self.complete_path: str = ""
        self.metadata_path: str = ""
        self.start_position: float = 0
        self.focal_plane_position: float = 0
        self.metadata: dict = {}

    def startTask(self):
        """ """
        self.log.info('started Task')
        self.default_exposure = self.ref['cam'].get_exposure()  # store this value to reset it at the end of task

        # stop all interfering modes on GUIs and disable GUI actions
        self.ref['cam'].stop_live_mode()
        self.ref['cam'].disable_camera_actions()

        self.ref['laser'].stop_laser_output()
        self.ref['bf'].led_off()
        self.ref['laser'].disable_laser_actions()  # includes also disabling of brightfield on / off button

        self.ref['focus'].stop_autofocus()
        self.ref['focus'].disable_focus_actions()
        self.ref['focus'].stop_live_display()

        # set the ASI stage in trigger mode to allow brightfield control
        self.ref['roi'].set_stage_led_mode('Triggered')

        # close previously opened FPGA session
        self.ref['laser'].end_task_session()

        # read all user parameters from config and define the path where the data will be saved
        self.load_user_parameters()
        self.complete_path, self.metadata_path = self.get_complete_path(self.save_path)

        # compute the starting position of the z-stack (for the piezo)
        self.start_position = self.calculate_start_position(self.centered_focal_plane)

        # retrieve the list of sources from the laser logic and format the imaging sequence (for Lumencor & FPGA)
        self.celesta_laser_dict = self.ref['laser']._laser_dict
        self.format_imaging_sequence()

        # prepare the camera and defines the timeout value (maximum time between two successive frames if not signal
        # from the DAQ or FPGA was detected)
        self.num_frames = self.num_z_planes * self.num_laserlines
        self.timeout = self.num_laserlines * self.exposure + 0.1
        max_frames, _ = self.ref['cam'].get_max_frames()
        if self.num_frames <= max_frames:
            self.ref['cam'].prepare_camera_for_multichannel_imaging(self.num_frames, self.exposure, None, None, None)
            self.ref['cam'].start_acquisition()
        else:
            self.log.error(f'The number of frames requested is higher than the maximum handled by the camera: '
                           f'{max_frames} - the task is aborted!')
            self.aborted = True

        # prepare the Lumencor celesta laser source and pre-set the intensity of each laser line
        self.ref['laser'].lumencor_wakeup()
        self.ref['laser'].lumencor_set_ttl(True)
        self.ref['laser'].lumencor_set_laser_line_intensities(self.celesta_intensity_dict)

        # prepare the daq: set the digital output to 0 before starting the task
        self.ref['daq'].write_to_do_channel(self.ref['daq']._daq.start_acquisition_taskhandle, 1,
                                            np.array([0], dtype=np.uint8))

        # download the bitfile for the task on the FPGA and start the FPGA session
        # bitfile = 'C:\\Users\\CBS\\qudi-HiM\\hardware\\fpga\\FPGA\\FPGA Bitfiles\\Qudimulticolourscan_20240112.lvbitx'
        bitfile = ('C:\\Users\\CBS\\qudi-HiM\\hardware\\fpga\\FPGA\\FPGA Bitfiles\\'
                   'Qudimulticolourscan_KINETIX_20240731.lvbitx')
        self.ref['laser'].start_task_session(bitfile)
        self.log.info('FPGA bitfile loaded for Multicolour task')
        self.ref['laser'].run_celesta_multicolor_imaging_task_session(self.num_z_planes, self.FPGA_wavelength_channels,
                                                                      self.num_laserlines, self.exposure)

        # load the metadata template and update it according to the parameters
        with open(self.metadata_template_path, "r", encoding='utf-8') as file:
            self.metadata = self.yaml.load(file)
        self.metadata = dict(self.metadata)
        self._update_metadata_dict(self.num_frames)

        # initialize the counter (corresponding to the number of planes already acquired)
        self.step_counter = 0

    def runTaskStep(self):
        """ Implement one work step of your task here.
        @return (bool): True if the task should continue running, False if it should finish.
        """
        self.step_counter += 1

        # --------------------------------------------------------------------------------------------------------------
        # position the piezo
        # --------------------------------------------------------------------------------------------------------------
        position = self.start_position + (self.step_counter - 1) * self.z_step
        self.ref['focus'].go_to_position(position)
        sleep(0.03)
        cur_pos = self.ref['focus'].get_position()
        self.z_target_positions.append(position)
        self.z_actual_positions.append(cur_pos)

        # --------------------------------------------------------------------------------------------------------------
        # imaging sequence (handled by FPGA)
        # --------------------------------------------------------------------------------------------------------------
        # send signal from daq to FPGA connector 0/DIO3 ('piezo ready')
        self.ref['daq'].write_to_do_channel(self.ref['daq']._daq.start_acquisition_taskhandle, 1,
                                            np.array([1], dtype=np.uint8))
        sleep(0.005)
        self.ref['daq'].write_to_do_channel(self.ref['daq']._daq.start_acquisition_taskhandle, 1,
                                            np.array([0], dtype=np.uint8))

        # wait for signal from FPGA to DAQ ('acquisition ready')
        fpga_ready = self.ref['daq'].read_di_channel(self.ref['daq']._daq.acquisition_done_taskhandle, 1)[0]
        t0 = time()

        while not fpga_ready:
            sleep(0.001)
            fpga_ready = self.ref['daq'].read_di_channel(self.ref['daq']._daq.acquisition_done_taskhandle, 1)[0]

            t1 = time() - t0
            if t1 > self.timeout:  # for safety: timeout if no signal received within the calculated time (in s)
                self.log.warning('Timeout occurred')
                break

        return (self.step_counter < self.num_z_planes) and (not self.aborted)

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

        # set the ASI stage in internal mode
        self.ref['roi'].set_stage_led_mode('Internal')

        # close the fpga session and restart the default session (to make sure the laser power are set to zero)
        self.ref['laser'].end_task_session()
        self.ref['laser'].restart_default_session()
        self.log.info('restarted default fpga session')

        # get acquired data from the camera and save it to file in case the task has not been stopped during acquisition
        if self.step_counter == self.num_z_planes:
            image_data = self.ref['cam'].get_acquired_data()

            if self.file_format == 'fits':
                metadata = self.get_fits_metadata()
                self.ref['cam'].save_to_fits(self.complete_path, image_data, metadata)
            elif self.file_format == 'npy':
                self.ref['cam'].save_to_npy(self.complete_path, image_data)
                self.save_metadata_txt_file()
            elif self.file_format == 'hdf5':
                metadata = self.get_hdf5_metadata()
                self.ref['cam'].save_to_hdf5(self.complete_path, image_data, metadata)
            else:
                self.ref['cam'].save_to_tiff_separate(self.num_laserlines, self.complete_path, image_data)
                self.save_metadata_txt_file()

            # save file with z positions (same procedure for either file format)
            file_path = os.path.join(os.path.split(self.complete_path)[0], 'z_positions.yaml')
            save_z_positions_to_file(self.z_target_positions, self.z_actual_positions, file_path)

        # reset the camera to default state
        self.ref['cam'].reset_camera_after_multichannel_imaging()
        self.ref['cam'].set_exposure(self.default_exposure)

        # enable gui actions
        self.ref['cam'].enable_camera_actions()
        self.ref['laser'].enable_laser_actions()
        self.ref['focus'].enable_focus_actions()

        self.log.info('cleanupTask finished')

    # ==================================================================================================================
    # Helper functions
    # ==================================================================================================================

    # ------------------------------------------------------------------------------------------------------------------
    # user parameters
    # ------------------------------------------------------------------------------------------------------------------
    def load_user_parameters(self):
        """ This function is called from startTask() to load the parameters given by the user in a specific format and
        initialize all the variables.

        Specify the path to the user defined config for this task in the (global) config of the experimental setup.
        User must specify the following dictionary (here with example entries):
            sample_name: 'Mysample'
            exposure: 0.05  # in s
            num_z_planes: 50
            z_step: 0.25  # in um
            centered_focal_plane: False
            save_path: 'E:\'
            file_format: 'tif'
            imaging_sequence: [('488 nm', 3), ('561 nm', 3), ('641 nm', 10)]
        """
        try:
            with open(self.user_config_path, 'r') as stream:
                user_param_dict = self.yaml.load(stream)

                self.sample_name = user_param_dict['sample_name']
                self.exposure = user_param_dict['exposure']
                self.num_z_planes = user_param_dict['num_z_planes']
                self.z_step = user_param_dict['z_step']  # in um
                self.centered_focal_plane = user_param_dict['centered_focal_plane']
                self.imaging_sequence = user_param_dict['imaging_sequence']
                self.save_path = user_param_dict['save_path']
                self.file_format = user_param_dict['file_format']

        except Exception as e:  # add the type of exception
            self.log.warning(f'Could not load user parameters for task {self.name}: {e}')

    # ------------------------------------------------------------------------------------------------------------------
    # file path handling
    # ------------------------------------------------------------------------------------------------------------------
    def get_complete_path(self, path_stem):
        """ Create the complete path based on path_stem given as user parameter, such as
        path_stem/YYYY_MM_DD/001_Scan_samplename/scan_001.tif or path_stem/YYYY_MM_DD/027_Scan_samplename/scan_027.fits
        @param: (str) path_stem such as E:/DATA
        @return: (str) complete path (see examples above)
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
        metadata_file_name = f'scan_{prefix}_metadata.yaml'
        complete_path = os.path.join(path, file_name)
        metadata_path = os.path.join(path, metadata_file_name)
        return complete_path, metadata_path

    # ------------------------------------------------------------------------------------------------------------------
    # methods for initializing piezo & laser
    # ------------------------------------------------------------------------------------------------------------------
    def format_imaging_sequence(self):
        """ Format the imaging_sequence dictionary for the celesta laser source and the FPGA controlling the triggers.
        The lumencor celesta is controlled in TTL mode. Intensity for each laser line must be set before launching the
        acquisition sequence (using the celesta_intensity_dict). Then, the FPGA will activate each line (either laser or
        brightfiel) based on the list of sources (FPGA_wavelength_channels).
        Since the intensity of each laser line must be set before the acquisition, it is not possibe to call the same
        laser line multiple times with different intensity values.
        """

    # reset parameters
        self.celesta_intensity_dict = {}
        self.FPGA_wavelength_channels = []

    # count the number of lightsources for each plane
        self.num_laserlines = len(self.imaging_sequence)

    # from _laser_dict, list all the available laser sources in a dictionary and associate a unique integer value for
    # the FPGA (starting at 1 since, for the FPGA, the brightfield is by default 0 and all the laser lines are organized
    # in increasing wavelength values).
    # In parallel, initialize the dictionary containing the intensity of each laser line of the Celesta.
        available_laser_dict = {}
        for laser in range(len(self.celesta_laser_dict)):
            key = self.celesta_laser_dict[f'laser{laser + 1}']['wavelength']
            available_laser_dict[key] = laser + 1
            self.celesta_intensity_dict[key] = 0

    # convert the imaging_sequence given by the user into format required by the bitfile (by default, 0 is the
    # brightfield and then all the laser lines sorted by increasing wavelength values. Note that a maximum number of
    # laser lines is allowed (self.FPGA_max_laserlines). It is constrained by the size of the laser/intensity arrays
    # defined in the labview script from which the bitfile is compiled.
        for line in range(self.num_laserlines):
            line_source = self.imaging_sequence[line][0]
            line_intensity = self.imaging_sequence[line][1]
            if line_source in available_laser_dict:
                self.FPGA_wavelength_channels.append(available_laser_dict[line_source])
                self.celesta_intensity_dict[line_source] = line_intensity
            else:
                self.FPGA_wavelength_channels.append(0)

    # For the FPGA, the wavelength list should have "FPGA_max_laserlines" entries. The list is padded with zero.
        for i in range(self.num_laserlines, self.FPGA_max_laserlines):
            self.FPGA_wavelength_channels.append(0)

    def calculate_start_position(self, centered_focal_plane):
        """
        This method calculates the piezo position at which the z stack will start. It can either start in the
        current plane or calculate an offset so that the current plane will be centered inside the stack.
        Note : the scan should start below the current position so that the focal plane will be the central plane or one
        of the central planes in case of an even number of planes.

        :param: bool centered_focal_plane: indicates if the scan is done below and above the focal plane (True)
                                            or if the focal plane is the bottommost plane in the scan (False)

        :return: float piezo start position
        """
        current_pos = self.ref['focus'].get_position()  # user has set focus
        self.focal_plane_position = current_pos  # save it to come back to this plane at the end of the task

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
    # metadata
    # ------------------------------------------------------------------------------------------------------------------
    # def get_metadata(self):
    #     """ Get a dictionary containing the metadata in a plain text easy readable format.
    #
    #     :return: dict metadata
    #     """
    #     metadata = {'Sample name': self.sample_name, 'Exposure time (s)': self.exposure,
    #                 'Scan step length (um)': self.z_step, 'Scan total length (um)': self.z_step * self.num_z_planes,
    #                 'Number laserlines': self.num_laserlines}
    #     for i in range(self.num_laserlines):
    #         metadata[f'Laser line {i+1}'] = self.imaging_sequence[i][0]
    #         metadata[f'Laser intensity {i+1} (%)'] = self.imaging_sequence[i][1]
    #     return metadata

    def _update_metadata_dict(self, n_frames):
        """ create a dictionary containing the metadata.
        @param: (int) number of frames required for the acquisition
        @return: (dict) metadata
        """
        # ----general----------------------------------------------------------------------------
        self.metadata['Time'] = datetime.now().strftime('%m-%d-%Y, %H:%M:%S')

        # ----camera-----------------------------------------------------------------------------
        self.metadata = update_metadata(self.metadata, ['Acquisition', 'number_frames'], n_frames)
        self.metadata = update_metadata(self.metadata, ['Acquisition', 'sample_name'], self.sample_name)
        self.metadata = update_metadata(self.metadata, ['Acquisition', 'exposure_time_(s)'], self.exposure)
        self.metadata = update_metadata(self.metadata, ['Acquisition', 'kinetic_time_(s)'], "NA")
        self.metadata = update_metadata(self.metadata, ['Acquisition', 'frame_transfer'], "NA")
        self.metadata = update_metadata(self.metadata, ['Acquisition', 'gain'], 1)
        self.metadata = update_metadata(self.metadata, ['Acquisition', 'sensor_temperature_setpoint_(°C)'], "NA")
        self.metadata = update_metadata(self.metadata, ['Acquisition', 'number_z_planes'], self.num_z_planes)
        self.metadata = update_metadata(self.metadata, ['Acquisition', 'distance_z_planes_(µm)'], self.z_step)
        self.metadata = update_metadata(self.metadata, ['Acquisition', 'number_frames_per_z_plane'],
                                        len(self.imaging_sequence))

        # ----filter------------------------------------------------------------------------------
        filterpos = self.ref['filter'].get_position()
        filterdict = self.ref['filter'].get_filter_dict()
        label = 'filter{}'.format(filterpos)
        self.metadata = update_metadata(self.metadata, ['Acquisition', 'filter'], filterdict[label]['name'])

        # ----laser-------------------------------------------------------------------------------
        for laser_lines in range(self.num_laserlines):
            self.metadata = update_metadata(self.metadata, ['Acquisition', 'laser_lines'],
                                            self.imaging_sequence[laser_lines][0], action="append")
            self.metadata = update_metadata(self.metadata, ['Acquisition', 'laser_power_(%)'],
                                            self.imaging_sequence[laser_lines][1], action="append")

    def get_fits_metadata(self):
        """ Get a dictionary containing the metadata in a fits header compatible format. Note this format is also
        compatible for the h5 format.
        @return: dict metadata
        """
        metadata = {'SAMPLE': (self.sample_name, 'sample name'), 'EXPOSURE': (self.exposure, 'exposure time (s)'),
                    'Z_STEP': (self.z_step, 'scan step length (um)'),
                    'Z_TOTAL': (self.z_step * self.num_z_planes, 'scan total length (um)'),
                    'CHANNELS': (self.num_laserlines, 'number laserlines')}
        for i in range(self.num_laserlines):
            metadata[f'LINE{i+1}'] = (self.imaging_sequence[i][0], f'laser line {i+1}')
            metadata[f'INTENS{i+1}'] = (self.imaging_sequence[i][1], f'laser intensity {i+1}')
        return metadata

    def get_hdf5_metadata(self):
        """ Get a dictionary containing the metadata in a hdf5 header compatible format.
        @return: dict metadata
        """
        metadata = {'sample_name': self.sample_name,
                    'exposure_s': self.exposure,
                    'z_step_µm': self.z_step,
                    'z_total_length_µm': self.z_step * self.num_z_planes,
                    'n_channels': self.num_laserlines}

        for i in range(self.num_laserlines):
            metadata[f'laser_line_{i+1}'] = self.imaging_sequence[i][0]
            metadata[f'laser_intensity_{i+1}'] = self.imaging_sequence[i][1]
        return metadata

    def save_metadata_txt_file(self):
        """ Save a txt file containing the metadata.
        """
        with open(self.metadata_path, 'w') as file:
            self.yaml.dump(self.metadata, file)
        self.log.info(f'Saved metadata to {self.metadata_path}')
