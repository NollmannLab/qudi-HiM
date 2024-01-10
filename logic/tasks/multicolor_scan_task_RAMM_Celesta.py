# -*- coding: utf-8 -*-
"""
Qudi-CBS

An extension to Qudi.

This module contains a task to perform a multicolor scan on the RAMM setup equiped with a Celesta Lumencor laser source.
(Take at a given position a stack of images using a sequence of different laserlines or intensities in each plane of the
 stack.)

@author: JB. Fiche (from F. Barho original code)

Created on Tue January 9, 2024
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
from datetime import datetime
import numpy as np
import yaml
from time import sleep, time
from logic.generic_task import InterruptableTask
from logic.task_helper_functions import save_z_positions_to_file
from logic.task_helper_functions import get_entry_nested_dict


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

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        print('Task {0} added!'.format(self.name))
        self.FPGA_max_laserlines = 10
        self.user_config_path = self.config['path_to_user_config']
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
        self.start_position: float = 0
        self.num_laserlines: int = 0
        self.wavelengths: list = []
        self.intensities: list = []
        self.focal_plane_position: float = 0
        self.lightsource_dict: dict = {'Brightfield': 0, '405 nm': 1, '477 nm': 2, '546 nm': 3, '638 nm': 4,
                                       '750 nm': 5}

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

        # set the ASI stage in trigger mode to allow brightfield control
        self.ref['roi'].set_stage_led_mode('Triggered')

        # close default FPGA session
        self.ref['laser'].end_task_session()

        # read all user parameters from config
        self.load_user_parameters()

        # compute the starting position of the z-stack (for the piezo)
        self.start_position = self.calculate_start_position(self.centered_focal_plane)

        # format the imaging sequence (for Lumencor & FPGA)
        self.format_imaging_sequence()

        # prepare the camera
        self.num_frames = self.num_z_planes * self.num_laserlines
        self.ref['cam'].prepare_camera_for_multichannel_imaging(self.num_frames, self.exposure, None, None, None)
        self.ref['cam'].start_acquisition()

        # define the laser intensities for the Lumencor
        # Set : - all laser lines to OFF
        #       - the celesta laser source in external TTL mode
        #       - the intensity of each laser line according to the task parameters
        self.ref['laser'].lumencor_wakeup()
        self.ref['laser'].lumencor_set_ttl(True)
        self.ref['laser'].lumencor_set_laser_line_intensities(self.intensity_dict)

        # download the bitfile for the task on the FPGA
        # bitfile = 'C:\\Users\\sCMOS-1\\qudi-cbs\\hardware\\fpga\\FPGA\\FPGA Bitfiles\\50ms_FPGATarget_QudiFTLQPDPID_u+Bjp+80wxk.lvbitx'
        bitfile = 'C:\\Users\\sCMOS-1\\qudi-cbs\\hardware\\fpga\\FPGA\\FPGA Bitfiles\\FPGAv0_FPGATarget_Qudimulticolours_mq4E6EoFF7s.lvbitx'
        self.ref['laser'].start_task_session(bitfile)
        self.log.info('FPGA bitfile loaded for Multicolour task')

        # prepare the daq: set the digital output to 0 before starting the task
        self.ref['daq'].write_to_do_channel(self.ref['daq']._daq.start_acquisition_taskhandle, 1,
                                            np.array([0], dtype=np.uint8))

        # initialize the counter (corresponding to the number of planes already acquired)
        self.step_counter = 0

        # start the session on the fpga using the user parameters
        #self.ref['laser'].run_multicolor_imaging_task_session(self.num_z_planes, self.wavelengths, self.intensities,
        #                                                      self.num_laserlines, self.exposure)
        print(self.wavelengths, self.num_laserlines)
        self.ref['laser'].run_celesta_multicolor_imaging_task_session(self.num_z_planes, self.wavelengths,
                                                                      self.num_laserlines, self.exposure)

        # defines the timeout value
        self.timeout = self.num_laserlines * self.exposure + 0.1

    def runTaskStep(self):
        """ Implement one work step of your task here.
        :return bool: True if the task should continue running, False if it should finish.
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

        # get acquired data from the camera and save it to file in case the task has not been stopped during acquisition
        if self.step_counter == self.num_z_planes:
            image_data = self.ref['cam'].get_acquired_data()

            if self.file_format == 'fits':
                metadata = self.get_fits_metadata()
                self.ref['cam'].save_to_fits(self.complete_path, image_data, metadata)
            elif self.file_format == 'npy':
                self.ref['cam'].save_to_npy(self.complete_path, image_data)
                metadata = self.get_metadata()
                file_path = self.complete_path.replace('npy', 'yaml', 1)
                self.save_metadata_file(metadata, file_path)
            else:   # use tiff as default format
                self.ref['cam'].save_to_tiff(self.num_frames, self.complete_path, image_data)
                metadata = self.get_metadata()
                file_path = self.complete_path.replace('tif', 'yaml', 1)
                self.save_metadata_file(metadata, file_path)

            # save file with z positions (same procedure for either file format)
            file_path = os.path.join(os.path.split(self.complete_path)[0], 'z_positions.yaml')
            save_z_positions_to_file(self.z_target_positions, self.z_actual_positions, file_path)

        # reset the camera to default state
        self.ref['cam'].reset_camera_after_multichannel_imaging()
        self.ref['cam'].set_exposure(self.default_exposure)

        # close the fpga session and restart the default session
        self.ref['laser'].end_task_session()
        self.ref['laser'].restart_default_session()
        self.log.info('restarted default fpga session')

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
        """ This function is called from startTask() to load the parameters given by the user in a specific format.

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
                self.user_param_dict = yaml.safe_load(stream)

                self.sample_name = self.user_param_dict['sample_name']
                self.exposure = self.user_param_dict['exposure']
                self.num_z_planes = self.user_param_dict['num_z_planes']
                self.z_step = self.user_param_dict['z_step']  # in um
                self.centered_focal_plane = self.user_param_dict['centered_focal_plane']
                self.imaging_sequence = self.user_param_dict['imaging_sequence']
                self.save_path = self.user_param_dict['save_path']
                self.file_format = self.user_param_dict['file_format']

        except Exception as e:  # add the type of exception
            self.log.warning(f'Could not load user parameters for task {self.name}: {e}')

        # define the path where the data will be saved
        self.complete_path = self.get_complete_path(self.save_path)

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
    # file path handling
    # ------------------------------------------------------------------------------------------------------------------

    def get_complete_path(self, path_stem):
        """ Create the complete path based on path_stem given as user parameter,
        such as path_stem/YYYY_MM_DD/001_Scan_samplename/scan_001.tif
        or path_stem/YYYY_MM_DD/027_Scan_samplename/scan_027.fits

        :param: str path_stem such as E:/DATA
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
    # Format the imaging cycle for the Lumencor laser source and FPGA
    # ------------------------------------------------------------------------------------------------------------------

    def format_imaging_sequence(self):
        """ Format the imaging_sequence dictionary for the celesta laser source and the FPGA controlling the triggers.
        The lumencor celesta is controlled in TTL mode. Intensity for each channel must be set before launching the
        acquisition sequence. It is not possible to call the same line with different power during the acquisition.
        """

    # count the number of lightsources
        self.num_laserlines = len(self.imaging_sequence)

    # convert the imaging_sequence given by user into format required by the bitfile. Note that a maximum number of
    # laser lines is allowed (self.FPGA_max_laserlines). It is constrained by the size of the laser/intensity arrays
    # defined in the labview script from which the bitfile is compiled.
        self.wavelengths = [self.imaging_sequence[i][0] for i in range(self.num_laserlines)]

        print(self.wavelengths)

        self.wavelengths = [self.lightsource_dict[key] for key in self.wavelengths]

        print(self.wavelengths)

        for i in range(self.num_laserlines, self.FPGA_max_laserlines):
            self.wavelengths.append(0)  # must always be a list of length 5: append 0 until necessary length reached

        self.intensities = [self.imaging_sequence[i][1] for i, item in enumerate(self.imaging_sequence)]
        for i in range(self.num_laserlines, self.FPGA_max_laserlines):
            self.intensities.append(0)

        print(self.intensities)

    # Load the laser and intensity dictionary used in lasercontrol_logic and update it according to the imaging sequence
        laser_dict = self.ref['laser'].get_laser_dict()
        intensity_dict = self.ref['laser'].init_intensity_dict()
        imaging_sequence = [(*get_entry_nested_dict(laser_dict, self.imaging_sequence[i][0], 'label'),
                             self.imaging_sequence[i][1]) for i in range(len(self.imaging_sequence))]

        print(laser_dict)
        print(intensity_dict)
        print(imaging_sequence)

        for i in range(len(imaging_sequence)):
            key = imaging_sequence[i][0]
            intensity_dict[key] = imaging_sequence[i][1]

        self.intensity_dict = intensity_dict

    # ------------------------------------------------------------------------------------------------------------------
    # metadata
    # ------------------------------------------------------------------------------------------------------------------

    def get_metadata(self):
        """ Get a dictionary containing the metadata in a plain text easy readable format.

        :return: dict metadata
        """
        metadata = {'Sample name': self.sample_name, 'Exposure time (s)': self.exposure,
                    'Scan step length (um)': self.z_step, 'Scan total length (um)': self.z_step * self.num_z_planes,
                    'Number laserlines': self.num_laserlines}
        for i in range(self.num_laserlines):
            metadata[f'Laser line {i+1}'] = self.imaging_sequence[i][0]
            metadata[f'Laser intensity {i+1} (%)'] = self.imaging_sequence[i][1]
        # pixel size ???
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
        return metadata

    def save_metadata_file(self, metadata, path):
        """ Save a txt file containing the metadata dictionary.

        :param dict metadata: dictionary containing the metadata
        :param str path: pathname
        """
        with open(path, 'w') as outfile:
            yaml.safe_dump(metadata, outfile, default_flow_style=False)
        self.log.info('Saved metadata to {}'.format(path))
