# -*- coding: utf-8 -*-
"""
Qudi-CBS

An extension to Qudi.

This module contains the timelapse experiment for the RAMM setup.

@authors: F. Barho, JB. Fiche

Created on Thu June 17 2021
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
import time
from datetime import datetime
from logic.generic_task import InterruptableTask
from logic.task_helper_functions import save_roi_start_times_to_file


class Task(InterruptableTask):  # do not change the name of the class. it is always called Task !
    """ This task iterates over all roi given in a file (typically a mosaic) and does an acquisition of a series of
    planes in z direction color by color. This is repeated num_iterations times, after a defined waiting time per
    iteration. The stack at an ROI for each color can have a different number of planes and distances in z direction.

    Config example pour copy-paste:

    TimelapseTask:
        module: 'timelapse_task_RAMM'
        needsmodules:
            laser: 'lasercontrol_logic'
            bf: 'brightfield_logic'
            cam: 'camera_logic'
            daq: 'nidaq_logic'
            focus: 'focus_logic'
            roi: 'roi_logic'
        config:
            path_to_user_config: 'C:/Users/sCMOS-1/qudi_files/qudi_task_config_files/timelapse_task_RAMM.yml'
    """
    # ==================================================================================================================
    # Generic Task methods
    # ==================================================================================================================

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.directory: str = ""
        self.counter: int = 0
        self.user_param_dict: dict = {}
        self.lightsource_dict: dict = {'BF': 0, '405 nm': 1, '488 nm': 2, '561 nm': 3, '640 nm': 4}
        self.user_config_path: str = self.config['path_to_user_config']
        self.autofocus_ok: bool = False
        self.default_exposure: float = 0.05
        self.num_frames: int = 0
        self.sample_name: str = ""
        self.exposure: float = 0.05
        self.centered_focal_plane: bool = False
        self.save_path: str = ""
        self.file_format: str = ""
        self.roi_list_path: list = []
        self.num_iterations: int = 0
        self.time_step: float = 0
        self.imaging_sequence: list = []
        self.roi_names: list = []
        self.num_laserlines: int = 0
        self.prefix: str = ""

    def startTask(self):
        """ """
        self.log.info('Starting task')
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

        # control that autofocus has been calibrated and a setpoint is defined
        self.autofocus_ok = self.ref['focus']._calibrated and self.ref['focus']._setpoint_defined

        if not self.autofocus_ok:
            self.log.warning('Task aborted. Please initialize the autofocus before starting this task.')
            return

        # read all user parameters from config
        self.load_user_parameters()

        # calculate the total number of images to acquire for each cycle. If the number is above 300, the program is
        # issuing a warning indicating that the number of images is high (since all the images are acquired in one
        # single acquisition cycle)
        num_z_planes_total = sum(self.imaging_sequence[i]['num_z_planes'] for i in range(len(self.imaging_sequence)))
        self.num_frames = len(self.roi_names) * num_z_planes_total
        if self.num_frames > 300:
            self.log.warning('More than 300 images are saved for each cycle.')

        # create a directory in which all the data will be saved
        self.directory = self.create_directory(self.save_path)

        # prepare the camera
        self.ref['cam'].prepare_camera_for_multichannel_imaging(self.num_frames, self.exposure, None, None, None)
        self.ref['cam'].stop_acquisition()  # for safety
        self.ref['cam'].start_acquisition()
        time.sleep(1)
        self.ref['cam'].stop_acquisition()

        # close the default FPGA session and start the time-lapse session on the fpga using the user parameters
        self.ref['laser'].close_default_session()
        # bitfile = 'C:\\Users\\sCMOS-1\\qudi-cbs\\hardware\\fpga\\FPGA\\FPGA Bitfiles\\50ms_FPGATarget_QudiFTLQPDPID_u+Bjp+80wxk.lvbitx'
        bitfile = 'C:\\Users\\CBS\\qudi-HiM\\hardware\\fpga\\FPGA\\FPGA Bitfiles\\20ms_FPGATarget_QudiFTLQPDPID_u+Bjp+80wxk.lvbitx'
        self.ref['laser'].start_task_session(bitfile)

        # in order to have a session running for access to autofocus
        self.ref['laser'].run_multicolor_imaging_task_session(1, [0, 0, 0, 0, 0], [0, 0, 0, 0, 0], 1, self.exposure)

        # set the active_roi to none to avoid having two active rois displayed
        self.ref['roi'].active_roi = None

        # save the acquisition parameters
        metadata = self.get_metadata()
        file_path = os.path.join(self.directory, 'TL_parameters.yml')
        self.save_metadata_file(metadata, file_path)

        # initialize a counter to iterate over the number of cycles to do
        self.counter = 0

    def runTaskStep(self):
        """ Implement one work step of your task here.
        :return: bool: True if the task should continue running, False if it should finish.
        """
        if not self.autofocus_ok or self.aborted:
            return False

        start_time = time.time()

        # create a save path for the current iteration
        # cur_save_path = self.get_complete_path(self.directory, self.counter+1)

        # start camera acquisition
        self.ref['cam'].start_acquisition()

        # --------------------------------------------------------------------------------------------------------------
        # move to ROI and focus (using autofocus and stop when stable)
        # --------------------------------------------------------------------------------------------------------------

        roi_start_times = []
        # roi_start_z = []

        for item in self.roi_names:

            if self.aborted:
                break

            # measure the start time for the ROI
            roi_start_time = time.time()
            roi_start_times.append(roi_start_time)

            # go to roi
            self.ref['roi'].set_active_roi(name=item)
            self.ref['roi'].go_to_roi_xy()
            self.log.info(f'Moved to {item} xy position')
            self.ref['roi'].stage_wait_for_idle()

            # autofocus
            self.ref['focus'].start_autofocus(stop_when_stable=True, search_focus=False)
            # ensure that focus is stable here
            # autofocus_enabled is True when autofocus is started and once it is stable is set to false
            busy = self.ref['focus'].autofocus_enabled
            counter = 0
            while busy:
                counter += 1
                time.sleep(0.1)
                busy = self.ref['focus'].autofocus_enabled
                if counter > 100:
                    break

            # Save the z position after the focus (for later optimization, in order to check that the tilt of the sample
            # is reproducible)
            current_z = self.ref['focus'].get_position()
            # roi_start_z.append(current_z)

            # ----------------------------------------------------------------------------------------------------------
            # imaging sequence
            # ----------------------------------------------------------------------------------------------------------
            # acquire a stack for each laserline at the current ROI
            for i in range(self.num_laserlines):

                if self.aborted:
                    break

                num_z_planes = self.imaging_sequence[i]['num_z_planes']
                z_step = self.imaging_sequence[i]['z_step']
                start_position, end_position = self.calculate_start_position(self.centered_focal_plane, num_z_planes,
                                                                             z_step)

                # autofocus could be moved here if setpoint for each laserline defined

                # define the parameters of the fpga session for the laserline:
                wavelength = self.imaging_sequence[i]['lightsource']
                if wavelength == 'Brightfield':
                    wavelengths = [0, 0, 0, 0, 0]
                    intensities = [0, 0, 0, 0, 0]
                    intensity = self.imaging_sequence[i]['intensity']
                    self.ref['roi'].set_stage_led_intensity(intensity)
                else:
                    wavelengths = [0, 0, 0, 0]
                    intensities = [0, 0, 0, 0]
                    wavelength = self.lightsource_dict[wavelength]
                    # generate a list of length 5 having only a first entry different from zero
                    wavelengths.insert(0, wavelength)
                    intensity = self.imaging_sequence[i]['intensity']
                    intensities.insert(0, intensity)

                self.ref['laser'].run_multicolor_imaging_task_session(num_z_planes, wavelengths, intensities, 1,
                                                                      self.exposure)
                # parameters: num_z_planes, wavelengths: array of length 5 with only 1 entry != 0, intensities: array of
                # length 5 with only 1 entry != 0, num_laserlines, exposure_time

                # prepare the daq: set the digital output to 0 before starting the task
                self.ref['daq'].write_to_do_channel(self.ref['daq']._daq.start_acquisition_taskhandle, 1,
                                                    np.array([0], dtype=np.uint8))

                # print(f'{item}: Laserline {i}: performing z stack..')

                for plane in range(num_z_planes):
                    # position the piezo
                    position = start_position + plane * z_step
                    self.ref['focus'].go_to_position(position, direct=True)
                    # print(f'target position: {position} um')
                    time.sleep(0.03)
                    # cur_pos = self.ref['focus'].get_position()
                    # print(f'current position: {cur_pos} um')

                    # send signal from daq to FPGA connector 0/DIO3 ('piezo ready')
                    self.ref['daq'].write_to_do_channel(self.ref['daq']._daq.start_acquisition_taskhandle, 1,
                                                        np.array([1], dtype=np.uint8))
                    time.sleep(0.005)
                    self.ref['daq'].write_to_do_channel(self.ref['daq']._daq.start_acquisition_taskhandle, 1,
                                                        np.array([0], dtype=np.uint8))

                    # wait for signal from FPGA to DAQ ('acquisition ready')
                    fpga_ready = self.ref['daq'].read_di_channel(self.ref['daq']._daq.acquisition_done_taskhandle, 1)[0]
                    t0 = time.time()

                    while not fpga_ready:
                        time.sleep(0.001)
                        fpga_ready = self.ref['daq'].read_di_channel(self.ref['daq']._daq.acquisition_done_taskhandle, 1)[0]
                        t1 = time.time() - t0
                        if t1 > 1:  # for safety: timeout if no signal received within 1 s
                            self.log.warning('Timeout occurred')
                            break

                self.ref['focus'].go_to_position(end_position, direct=True)
                if wavelength == 'Brightfield':
                    self.ref['roi'].set_stage_led_intensity(0)

        # go back to first ROI
        self.ref['roi'].set_active_roi(name=self.roi_names[0])
        self.ref['roi'].go_to_roi_xy()
        self.ref['roi'].stage_wait_for_idle()

        # --------------------------------------------------------------------------------------------------------------
        # data saving
        # --------------------------------------------------------------------------------------------------------------
        image_data = self.ref['cam'].get_acquired_data()

        # for the sake of simplicity, a single file is saved for each ROI & channel.
        start_frame = 0
        for roi in self.roi_names:
            for channel in range(self.num_laserlines):
                num_z_planes = self.imaging_sequence[channel]['num_z_planes']
                end_frame = start_frame + num_z_planes
                data = image_data[start_frame:end_frame]
                cur_save_path = self.get_complete_path(self.directory, self.counter + 1, roi, channel)

                print(f'file format : {self.file_format}')

                if self.file_format == 'fits':
                    metadata = self.get_fits_metadata()
                    self.ref['cam'].save_to_fits(cur_save_path, data, metadata)
                if self.file_format == 'npy':
                    self.ref['cam'].save_to_npy(cur_save_path, data)
                else:  # use tiff as default format
                    self.ref['cam'].save_to_tiff(num_z_planes, cur_save_path, data)

                start_frame = end_frame

        # save roi start times to file
        roi_start_times = [item - start_time for item in roi_start_times]
        num = str(self.counter+1).zfill(2)
        file_path = os.path.join(os.path.split(cur_save_path)[0], f'roi_start_times_step_{num}.yml')
        save_roi_start_times_to_file(roi_start_times, file_path)

        # save the roi z start position
        # file_path = os.path.join(os.path.split(cur_save_path)[0], f'z_start_position_step_{num}.yml')
        # save_roi_start_times_to_file(roi_start_z, file_path)

        # increment the counter
        self.counter += 1

        # waiting time before going to next step
        finish_time = time.time()
        duration = finish_time - start_time
        wait = self.time_step - duration
        print(f'Finished step in {duration} s. Waiting {wait} s.')
        if wait > 0:
            time.sleep(wait)

        return self.counter < self.num_iterations

    def pauseTask(self):
        """ """
        self.log.info('pauseTask called')

    def resumeTask(self):
        """ """
        self.log.info('resumeTask called')

    def cleanupTask(self):
        """ """
        self.log.info('cleanupTask called')

        # reset the camera to default state
        self.ref['cam'].reset_camera_after_multichannel_imaging()
        self.ref['cam'].set_exposure(self.default_exposure)

        # close the fpga session
        self.ref['laser'].end_task_session()
        self.ref['laser'].restart_default_session()
        self.log.info('restarted default session')

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
            exposure: 0.05  # in s
            centered_focal_plane: False
            save_path: 'E:/'
            file_format: 'tif'
            roi_list_path: 'pathstem/qudi_files/qudi_roi_lists/roilist_20210101_1128_23_123243.json'
            num_iterations: 5
            time_step: 120  # in seconds
            imaging_sequence: [{'lightsource': '488 nm', 'intensity': 5}, 'num_z_planes': 10, 'z_step': 0.1},
                               {'lightsource': '561 nm', 'intensity': 5}, 'num_z_planes': 12, 'z_step': 0.1}]
        """
        try:
            with open(self.user_config_path, 'r') as stream:
                self.user_param_dict = yaml.safe_load(stream)

                self.sample_name = self.user_param_dict['sample_name']
                self.exposure = self.user_param_dict['exposure']
                self.centered_focal_plane = self.user_param_dict['centered_focal_plane']
                self.save_path = self.user_param_dict['save_path']
                self.file_format = self.user_param_dict['file_format']
                self.roi_list_path = self.user_param_dict['roi_list_path']
                self.num_iterations = self.user_param_dict['num_iterations']
                self.time_step = self.user_param_dict['time_step']
                self.imaging_sequence = self.user_param_dict['imaging_sequence']

        except Exception as e:  # add the type of exception
            self.log.warning(f'Could not load user parameters for task {self.name}: {e}')

        # establish further user parameters derived from the given ones:
        # create a list of roi names
        self.ref['roi'].load_roi_list(self.roi_list_path)
        # get the list of the roi names
        self.roi_names = self.ref['roi'].roi_names

        # count the number of lightsources
        self.num_laserlines = len(self.imaging_sequence)

    def calculate_start_position(self, centered_focal_plane, num_z_planes, z_step):
        """
        This method calculates the piezo position at which the z stack will start. It can either start in the
        current plane or calculate an offset so that the current plane will be centered inside the stack.

        :param: bool centered_focal_plane: indicates if the scan is done below and above the focal plane (True)
                                            or if the focal plane is the bottommost plane in the scan (False)
        :param: int num_z_planes: number of planes in the current stack
        :param: float z_step: spacing between two planes in the current stack

        :return: float piezo start position
        """
        current_pos = self.ref['focus'].get_position()

        if centered_focal_plane:  # the scan should start below the current position so that the focal plane will be the
            # central plane or one of the central planes in case of an even number of planes
            # even number of planes:
            if num_z_planes % 2 == 0:
                # focal plane is the first one of the upper half of the number of planes
                start_pos = current_pos - num_z_planes / 2 * z_step
            # odd number of planes:
            else:
                start_pos = current_pos - (num_z_planes - 1)/2 * z_step

            return start_pos, current_pos
        else:
            return current_pos, current_pos  # the scan starts at the current position and moves up

    # ------------------------------------------------------------------------------------------------------------------
    # file path handling
    # ------------------------------------------------------------------------------------------------------------------

    def create_directory(self, path_stem):
        """ Create the directory (based on path_stem given as user parameter),
        in which the data is saved.
        Example: path_stem/YYYY_MM_DD/001_Timelapse_samplename

        :param: str path_stem: name of the (default) directory for data saving
        :return: str path to the directory where data is saved (see example above)
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

        prefix = str(number_dirs + 1).zfill(3)
        # make prefix accessible to include it in the filename generated in the method get_complete_path
        self.prefix = prefix

        foldername = f'{prefix}_Timelapse_{self.sample_name}'

        path = os.path.join(path_stem_with_date, foldername)

        # create the path  # no need to check if it already exists due to incremental prefix
        try:
            os.makedirs(path)  # recursive creation of all directories on the path
        except Exception as e:
            self.log.error('Error {0}'.format(e))

        return path

    def get_complete_path(self, directory, counter, roi, channel):
        """ Get the complete path to the data file, for the current iteration.

        :param: str directory: path to the data directory
        :param: int counter: number of the current iteration

        :return: str complete_path
        """
        file_name = f'TL_{self.prefix}_roi_{str(roi).zfill(3)}_ch_{str(channel).zfill(3)}_step_{str(counter).zfill(3)}.{self.file_format}'
        complete_path = os.path.join(directory, file_name)
        return complete_path

    # ------------------------------------------------------------------------------------------------------------------
    # metadata
    # ------------------------------------------------------------------------------------------------------------------

    def get_metadata(self):
        """ Get a dictionary containing the metadata in a plain text easy readable format.

        :return: dict metadata
        """
        metadata = {'Sample name': self.sample_name, 'Exposure time (s)': self.exposure,
                    'Number laserlines': self.num_laserlines}
        for i in range(self.num_laserlines):
            metadata[f'Laser line {i+1}'] = self.imaging_sequence[i]['lightsource']
            metadata[f'Laser intensity {i+1} (%)'] = self.imaging_sequence[i]['intensity']
            metadata[f'Scan step length {i+1} (um)'] = self.imaging_sequence[i]['z_step']
            metadata[f'Scan total length {i+1} (um)'] = self.imaging_sequence[i]['num_z_planes'] * self.imaging_sequence[i]['z_step']
        return metadata

    def get_fits_metadata(self):
        """ Get a dictionary containing the metadata in a fits header compatible format.

        :return: dict metadata
        """
        metadata = {'SAMPLE': (self.sample_name, 'sample name'), 'EXPOSURE': (self.exposure, 'exposure time (s)'),
                    'CHANNELS': (self.num_laserlines, 'number laserlines')}
        for i in range(self.num_laserlines):
            metadata[f'LINE{i+1}'] = (self.imaging_sequence[i]['lightsource'], f'laser line {i+1}')
            metadata[f'INTENS{i+1}'] = (self.imaging_sequence[i]['intensity'], f'laser intensity {i+1}')
            metadata[f'Z_STEP{i+1}'] = (self.imaging_sequence[i]['z_step'], f'scan step length (um) {i+1}')
            metadata[f'Z_TOTAL{i+1}'] = (self.imaging_sequence[i]['num_z_planes'] * self.imaging_sequence[i]['z_step'], f'scan total length (um) {i+1}')
        return metadata

    def save_metadata_file(self, metadata, path):
        """ Save a txt file containing the metadata dictionary.

        :param dict metadata: dictionary containing the metadata
        :param str path: pathname
        """
        with open(path, 'w') as outfile:
            yaml.safe_dump(metadata, outfile, default_flow_style=False)
        self.log.info('Saved metadata to {}'.format(path))
