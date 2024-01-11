# -*- coding: utf-8 -*-
"""
Qudi-CBS

An extension to Qudi.

This module contains a task to perform a multicolor scan on RAMM setup iterating over a list of ROIs.
(Take for each region of interest (ROI) a stack of images using a sequence of different laserlines or intensities
in each plane of the stack.)

@author: JB Fiche (original code F. Barho)

Created on Thu Jan 11 2024
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
import numpy as np
import os
import yaml
from time import sleep, time
from datetime import datetime
from tqdm import tqdm
from logic.generic_task import InterruptableTask
from logic.task_helper_functions import save_z_positions_to_file
from logic.task_logging_functions import write_dict_to_file


class Task(InterruptableTask):  # do not change the name of the class. it is always called Task !
    """ This task iterates over all roi given in a file and acquires a series of planes in z direction
    using a sequence of lightsources for each plane, for each roi.

    Config example pour copy-paste:

    ROIMulticolorScanTask:
        module: 'roi_multicolor_scan_task_RAMM'
        needsmodules:
            laser: 'lasercontrol_logic'
            bf: 'brightfield_logic'
            cam: 'camera_logic'
            daq: 'nidaq_logic'
            focus: 'focus_logic'
            roi: 'roi_logic'
        config:
            path_to_user_config: 'C:/Users/sCMOS-1/qudi_files/qudi_task_config_files/ROI_multicolor_scan_task_RAMM.yml'
    """
    # ==================================================================================================================
    # Generic Task methods
    # ==================================================================================================================

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        print('Task {0} added!'.format(self.name))
        self.user_config_path = self.config['path_to_user_config']
        self.FPGA_max_laserlines = 10
        self.user_config_path: str = self.config['path_to_user_config']
        self.celesta_laser_dict: dict = self.ref['laser']._laser_dict
        self.FPGA_wavelength_channels: list = []
        self.celesta_intensity_dict: dict = {}
        self.num_laserlines: int = 0

        self.roi_counter: int = 0
        self.directory: str = "None"
        self.user_param_dict: dict = {}
        self.timeout: float = 0
        self.default_exposure: float = 0
        self.num_frames: int = 0
        self.sample_name: str = ""
        self.is_dapi: bool = False
        self.is_rna: bool = False
        self.exposure: float = 0
        self.num_z_planes: int = 0
        self.z_step: int = 0
        self.centered_focal_plane: bool = False
        self.imaging_sequence: list = []
        self.save_path: str = ""
        self.file_format: str = ""
        self.roi_list_path: str = ""
        self.roi_names: list = []
        self.prefix: str = ""
        self.autofocus_failed: int = 0

    def startTask(self):
        """ """
        self.log.info('started Task')

        self.default_exposure = self.ref['cam'].get_exposure()  # store this value to reset it at the end of task

        # stop all interfering modes on GUIs and disable GUI actions
        self.ref['roi'].disable_tracking_mode()
        self.ref['roi'].disable_roi_actions()

        self.ref['cam'].stop_live_mode()
        self.ref['cam'].disable_camera_actions()

        self.ref['laser'].stop_laser_output()
        self.ref['bf'].led_off()
        self.ref['laser'].disable_laser_actions()  # includes also disabling of brightfield on / off button

        self.ref['focus'].stop_autofocus()
        self.ref['focus'].disable_focus_actions()

        # set stage velocity and trigger mode (for brightfield control)
        self.ref['roi'].set_stage_velocity({'x': 1, 'y': 1})
        self.ref['roi'].set_stage_led_mode('Triggered')

        # close previously opened FPGA session
        self.ref['laser'].end_task_session()

        # read all user parameters from config
        self.load_user_parameters()

        # format the imaging sequence (for Lumencor & FPGA)
        self.format_imaging_sequence()

        # create a directory in which all the data will be saved
        self.directory = self.create_directory(self.save_path)

        # if dapi data is acquired, save a dapi channel info file in order to make the link to the bokeh app
        if self.is_dapi:
            imag_dict = {'imaging_sequence': self.imaging_sequence}
            dapi_channel_info_path = os.path.join(self.directory, 'DAPI_channel_info.yml')
            write_dict_to_file(dapi_channel_info_path, imag_dict)

        # prepare the camera
        self.num_frames = self.num_z_planes * self.num_laserlines
        self.ref['cam'].prepare_camera_for_multichannel_imaging(self.num_frames, self.exposure, None, None, None)

        # start the session on the fpga using the user parameters
        bitfile = 'C:\\Users\\sCMOS-1\\qudi-cbs\\hardware\\fpga\\FPGA\\FPGA Bitfiles\\QudiROImulticolorscan_20240111.lvbitx'
        self.ref['laser'].start_task_session(bitfile)
        self.ref['laser'].run_celesta_roi_multicolor_imaging_task_session(self.num_z_planes,
                                                                          self.FPGA_wavelength_channels,
                                                                          self.num_laserlines, self.exposure)

        # defines the timeout value
        self.timeout = self.num_laserlines * self.exposure + 0.1

        # Check the autofocus is calibrated
        if (not self.ref['focus']._calibrated) or (not self.ref['focus']._setpoint_defined):
            self.log.warning('Autofocus is not calibrated. Experiment can not be started. Please calibrate autofocus!')
            self.aborted = True

        # initialize a counter to iterate over the ROIs
        self.roi_counter = 0

        # set the active_roi to none to avoid having two active rois displayed
        self.ref['roi'].active_roi = None

    def runTaskStep(self):
        """ Implement one work step of your task here.
        :return bool: True if the task should continue running, False if it should finish.
        """
        # --------------------------------------------------------------------------------------------------------------
        # move to ROI and focus
        # --------------------------------------------------------------------------------------------------------------
        # create the path for each roi
        cur_save_path = self.get_complete_path(self.directory, self.roi_names[self.roi_counter])

        # go to roi
        self.ref['roi'].set_active_roi(name=self.roi_names[self.roi_counter])
        self.ref['roi'].go_to_roi_xy()
        self.log.info('Moved to {} xy position'.format(self.roi_names[self.roi_counter]))
        self.ref['roi'].stage_wait_for_idle()

        # autofocus
        self.ref['focus'].start_search_focus()
        # wait for the search focus flag to turn True, indicating that the search procedure is launched. In case
        # the autofocus is lost from the start, the search focus routine is starting and stopped before the
        # while loop is initialized. The aborted flag is then used to avoid getting stuck in the loop.
        search_focus_start = self.ref['focus'].focus_search_running
        while not search_focus_start:
            sleep(0.1)
            search_focus_start = self.ref['focus'].focus_search_running
            if self.ref['focus'].focus_search_aborted:
                print('focus search was aborted')
                break

        # wait for the search focus flag to turn False, indicating that the search procedure stopped, whatever
        # the result
        search_focus_running = self.ref['focus'].focus_search_running
        while search_focus_running:
            sleep(0.5)
            search_focus_running = self.ref['focus'].focus_search_running

        # check if the focus was found
        ready = self.ref['focus']._stage_is_positioned
        if not ready and self.autofocus_failed == 0:
            print('The autofocus was lost for the first time.')
            self.autofocus_failed += 1
        elif not ready and self.autofocus_failed > 0:
            print('The autofocus was lost for the second time. The HiM experiment is aborted.')
            self.aborted = True
        else:
            self.autofocus_failed = 0

        # reset piezo position to 25 um if too close to the limit of travel range (< 10 or > 50)
        self.ref['focus'].do_piezo_position_correction()
        busy = True
        while busy:
            sleep(0.5)
            busy = self.ref['focus'].piezo_correction_running

        start_position = self.calculate_start_position(self.centered_focal_plane)

        # --------------------------------------------------------------------------------------------------------------
        # imaging sequence
        # --------------------------------------------------------------------------------------------------------------
        # prepare the daq: set the digital output to 0 before starting the task
        self.ref['daq'].write_to_do_channel(self.ref['daq']._daq.start_acquisition_taskhandle, 1,
                                            np.array([0], dtype=np.uint8))

        # start camera acquisition
        self.ref['cam'].stop_acquisition()  # for safety
        self.ref['cam'].start_acquisition()

        # initialize arrays to save the target and current z positions
        z_target_positions = []
        z_actual_positions = []
        print(f'{self.roi_names[self.roi_counter]}: performing z stack..')

        for plane in tqdm(range(self.num_z_planes)):

            # position the piezo
            position = start_position + plane * self.z_step
            self.ref['focus'].go_to_position(position)
            # print(f'target position: {position} um')
            sleep(0.03)
            cur_pos = self.ref['focus'].get_position()
            # print(f'current position: {cur_pos} um')
            z_target_positions.append(position)
            z_actual_positions.append(cur_pos)

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
                if t1 > self.timeout:  # for safety: timeout if no signal received within indicated time
                    self.log.warning('Timeout occurred')
                    break

        self.ref['focus'].go_to_position(start_position)

        # --------------------------------------------------------------------------------------------------------------
        # data saving
        # --------------------------------------------------------------------------------------------------------------
        image_data = self.ref['cam'].get_acquired_data()

        if self.file_format == 'fits':
            metadata = self.get_fits_metadata()
            self.ref['cam'].save_to_fits(cur_save_path, image_data, metadata)
        elif self.file_format == 'npy':
            self.ref['cam'].save_to_npy(self.complete_path, image_data)
            metadata = self.get_metadata()
            file_path = self.complete_path.replace('npy', 'yaml', 1)
            self.save_metadata_file(metadata, file_path)
        else:  # use tiff as default format
            self.ref['cam'].save_to_tiff(self.num_frames, cur_save_path, image_data)
            metadata = self.get_metadata()
            file_path = cur_save_path.replace('tif', 'yaml', 1)
            self.save_metadata_file(metadata, file_path)

        # save the projection of the acquired stack if DAPI was checked (for experiment tracking option)
        if self.is_dapi:
            self.calculate_save_projection(self.num_laserlines, image_data, cur_save_path)

        # save file with z positions (same procedure for either file format)
        file_path = os.path.join(os.path.split(cur_save_path)[0], 'z_positions.yaml')
        save_z_positions_to_file(z_target_positions, z_actual_positions, file_path)

        self.roi_counter += 1
        return (self.roi_counter < len(self.roi_names)) and (not self.aborted)

    def pauseTask(self):
        """ """
        self.log.info('pauseTask called')

    def resumeTask(self):
        """ """
        self.log.info('resumeTask called')

    def cleanupTask(self):
        """ """
        self.log.info('cleanupTask called')

        # go back to first ROI
        self.ref['roi'].set_active_roi(name=self.roi_names[0])
        self.ref['roi'].go_to_roi_xy()

        # reset the camera to default state
        self.ref['cam'].reset_camera_after_multichannel_imaging()
        self.ref['cam'].set_exposure(self.default_exposure)

        # close the fpga session
        self.ref['laser'].end_task_session()
        self.ref['laser'].restart_default_session()
        self.log.info('restarted default session')

        # reset stage velocity and trigger mode to default
        self.ref['roi'].set_stage_velocity({'x': 6, 'y': 6})  # 5.74592e
        self.ref['roi'].set_stage_led_mode('Internal')

        # enable gui actions
        # roi gui
        self.ref['roi'].enable_tracking_mode()
        self.ref['roi'].enable_roi_actions()
        # basic imaging gui
        self.ref['cam'].enable_camera_actions()
        self.ref['laser'].enable_laser_actions()
        # focus tools gui
        self.ref['focus'].enable_focus_actions()

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
            dapi: False
            rna: False
            exposure: 0.05  # in s
            num_z_planes: 50
            z_step: 0.25  # in um
            centered_focal_plane: False
            save_path: 'E:\'
            file_format: 'tif'
            imaging_sequence: [('488 nm', 3), ('561 nm', 3), ('641 nm', 10)]
            roi_list_path: 'pathstem/qudi_files/qudi_roi_lists/roilist_20210101_1128_23_123243.json'
        """
        try:
            with open(self.user_config_path, 'r') as stream:
                self.user_param_dict = yaml.safe_load(stream)

                self.sample_name = self.user_param_dict['sample_name']
                self.is_dapi = self.user_param_dict['dapi']
                self.is_rna = self.user_param_dict['rna']
                self.exposure = self.user_param_dict['exposure']
                self.num_z_planes = self.user_param_dict['num_z_planes']
                self.z_step = self.user_param_dict['z_step']  # in um
                self.centered_focal_plane = self.user_param_dict['centered_focal_plane']
                self.imaging_sequence = self.user_param_dict['imaging_sequence']
                self.save_path = self.user_param_dict['save_path']
                self.file_format = self.user_param_dict['file_format']
                self.roi_list_path = self.user_param_dict['roi_list_path']

        except Exception as e:  # add the type of exception
            self.log.warning(f'Could not load user parameters for task {self.name}: {e}')

        # establish further user parameters derived from the given ones:
        # create a list of roi names
        self.ref['roi'].load_roi_list(self.roi_list_path)
        # get the list of the roi names
        self.roi_names = self.ref['roi'].roi_names

    def format_imaging_sequence(self):
        """ Format the imaging_sequence dictionary for the celesta laser source and the FPGA controlling the triggers.
        The lumencor celesta is controlled in TTL mode. Intensity for each laser line must be set before launching the
        acquisition sequence (using the celesta_intensity_dict). Then, the FPGA will activate each line (either laser or
        brightfiel) based on the list of sources (FPGA_wavelength_channels).
        Since the intensity of each laser line must be set before the acquisition, it is not possibe to call the same
        laser line multiple times with different intensity values.
        """

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

        :param: bool centered_focal_plane: indicates if the scan is done below and above the focal plane (True)
                                            or if the focal plane is the bottommost plane in the scan (False)

        :return: float piezo start position
        """
        current_pos = self.ref['focus'].get_position()

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

    def create_directory(self, path_stem):
        """ Create the directory (based on path_stem given as user parameter),
        in which the folders for the ROI will be created
        Example: path_stem/YYYY_MM_DD/001_Scan_samplename (default)
        or path_stem/YYYY_MM_DD/001_Scan_samplename_dapi (option dapi)
        or path_stem/YYYY_MM_DD/001_Scan_samplename_rna (option rna)

        :param: str path_stem: base name of the path that will be created

        :return: str path (see example above)
        """
        cur_date = datetime.today().strftime('%Y_%m_%d')

        path_stem_with_date = os.path.join(path_stem, cur_date)

        # check if folder path_stem_with_date exists, if not: create it
        if not os.path.exists(path_stem_with_date):
            try:
                os.makedirs(path_stem_with_date)  # recursive creation of all directories on the path
            except Exception as e:
                self.log.error('Error {0}'.format(e))

        # count the subdirectories in the directory path (non recursive !) to generate an incremental prefix
        dir_list = [folder for folder in os.listdir(path_stem_with_date) if
                    os.path.isdir(os.path.join(path_stem_with_date, folder))]
        number_dirs = len(dir_list)

        prefix = str(number_dirs+1).zfill(3)
        # make prefix accessible to include it in the filename generated in the method get_complete_path
        self.prefix = prefix

        # special format if option dapi or rna checked in experiment configurator
        if self.is_dapi:
            foldername = f'{prefix}_HiM_{self.sample_name}_DAPI'
        elif self.is_rna:
            foldername = f'{prefix}_HiM_{self.sample_name}_RNA'
        else:
            foldername = f'{prefix}_Scan_{self.sample_name}'

        path = os.path.join(path_stem_with_date, foldername)

        # create the path  # no need to check if it already exists due to incremental prefix
        try:
            os.makedirs(path)  # recursive creation of all directories on the path
        except Exception as e:
            self.log.error('Error {0}'.format(e))

        return path

    def get_complete_path(self, directory, roi_number):
        """ Create the complete path name to the image data file.

        :param: str directory: directory where the data shall be saved
        :param: str roi_number: string identifier of the current ROI for which a complete path shall be created

        :return: str complete_path: such as directory/ROI_001/scan_001_004_ROI.tif (experiment nb. 001, ROI nb. 004)
        """
        if self.is_dapi:
            path = os.path.join(directory, roi_number, 'DAPI')
        elif self.is_rna:
            path = os.path.join(directory, roi_number, 'RNA')
        else:
            path = os.path.join(directory, roi_number)

        if not os.path.exists(path):
            try:
                os.makedirs(path)  # recursive creation of all directories on the path
            except Exception as e:
                self.log.error('Error {0}'.format(e))

        roi_number_inv = roi_number.strip('ROI_')+'_ROI'  # for compatibility with analysis format

        if self.is_dapi:
            file_name = f'scan_{self.prefix}_DAPI_{roi_number_inv}.{self.file_format}'
        elif self.is_rna:
            file_name = f'scan_{self.prefix}_RNA_{roi_number_inv}.{self.file_format}'
        else:
            file_name = f'scan_{self.prefix}_{roi_number_inv}.{self.file_format}'

        complete_path = os.path.join(path, file_name)
        return complete_path

    # ------------------------------------------------------------------------------------------------------------------
    # metadata
    # ------------------------------------------------------------------------------------------------------------------

    def get_metadata(self):
        """ Get a dictionary containing the metadata in a plain text easy readable format.

        :return: dict metadata
        """
        metadata = {'Sample name': self.sample_name, 'Exposure time (s)': float(np.round(self.exposure, 3)),
                    'Scan step length (um)': self.z_step, 'Scan total length (um)': self.z_step * self.num_z_planes,
                    'Number laserlines': self.num_laserlines}
        for i in range(self.num_laserlines):
            metadata[f'Laser line {i + 1}'] = self.imaging_sequence[i][0]
            metadata[f'Laser intensity {i + 1} (%)'] = self.imaging_sequence[i][1]

        # add translation stage position
        metadata['x position'] = float(self.ref['roi'].stage_position[0])
        metadata['y position'] = float(self.ref['roi'].stage_position[1])

        # add autofocus information :
        metadata['Autofocus offset'] = float(self.ref['focus']._autofocus_logic._focus_offset)
        metadata['Autofocus calibration precision'] = float(np.round(self.ref['focus']._precision, 2))
        metadata['Autofocus calibration slope'] = float(np.round(self.ref['focus']._slope, 3))
        metadata['Autofocus setpoint'] = float(np.round(self.ref['focus']._autofocus_logic._setpoint, 3))

        return metadata

    def get_fits_metadata(self):
        """ Get a dictionary containing the metadata in a fits header compatible format.

        :return: dict metadata
        """
        metadata = {'SAMPLE': (self.sample_name, 'sample name'), 'EXPOSURE': (self.exposure, 'exposure time (s)'),
                    'Z_STEP': (self.z_step, 'scan step length (um)'),
                    'Z_TOTAL': (self.z_step * self.num_z_planes, 'scan total length (um)'),
                    'CHANNELS': (self.num_laserlines, 'number laserlines')}
        for i in range(self.num_laserlines):
            metadata[f'LINE{i+1}'] = (self.imaging_sequence[i][0], f'laser line {i+1}')
            metadata[f'INTENS{i+1}'] = (self.imaging_sequence[i][1], f'laser intensity {i+1}')
        metadata['X_POS'] = (self.ref['roi'].stage_position[0], 'x position')
        metadata['Y_POS'] = (self.ref['roi'].stage_position[1], 'y position')
        # metadata['ROI001'] = (self.ref['roi'].get_roi_position('ROI001'), 'ROI 001 position')
        # pixel size

        # add autofocus information :
        metadata['AF_OFFST'] = self.ref['focus']._autofocus_logic._focus_offset
        metadata['AF_PREC'] = np.round(self.ref['focus']._precision, 2)
        metadata['AF_SLOPE'] = np.round(self.ref['focus']._slope, 3)
        metadata['AF_SETPT'] = np.round(self.ref['focus']._autofocus_logic._setpoint, 3)

        return metadata

    def save_metadata_file(self, metadata, path):
        """ Save a txt file containing the metadata dictionary.

        :param dict metadata: dictionary containing the metadata
        :param str path: pathname
        """
        with open(path, 'w') as outfile:
            yaml.safe_dump(metadata, outfile, default_flow_style=False)
        self.log.info('Saved metadata to {}'.format(path))

    # ------------------------------------------------------------------------------------------------------------------
    # data for acquisition tracking
    # ------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def calculate_save_projection(num_channel, image_array, saving_path):

        # According to the number of channels acquired, split the stack accordingly
        deinterleaved_array_list = [image_array[idx::num_channel] for idx in range(num_channel)]

        # For each channel, the projection is calculated and saved as a npy file
        for n_channel in range(num_channel):
            image_array = deinterleaved_array_list[n_channel]
            projection = np.max(image_array, axis=0)
            path = saving_path.replace('.tif', f'_ch{n_channel}_2D', 1)
            np.save(path, projection)
