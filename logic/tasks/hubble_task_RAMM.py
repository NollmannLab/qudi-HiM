# -*- coding: utf-8 -*-
"""
Qudi-CBS

An extension to Qudi.

This module contains the timelapse experiment for the RAMM setup.

@authors: JB. Fiche

Created on Fri January 7, 2022
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
import matplotlib.pyplot as plt
import logging

from datetime import datetime
from logic.generic_task import InterruptableTask
from qtpy import QtCore
from tifffile import TiffWriter
from functools import wraps
from time import time, sleep


# Defines the decorator function for the log
def log(func):
    @wraps(func)
    def wrap(*args, **kwargs):
        t_init = args[0].hubble_init_time
        t0 = time()
        result = func(*args, **kwargs)
        t1 = time()
        task_logger = logging.getLogger('Task_logging')
        task_logger.info(f'function : {func.__name__} - time since start = {t0 - t_init}s - execution time = {t1 - t0}s')
        return result
    return wrap


class Task(InterruptableTask):  # do not change the name of the class. it is always called Task !
    """ This task iterates over all roi given in a file (typically a mosaic) and does an acquisition of a series of
    planes in z direction in multicolor. This is repeated num_iterations times.

    Config example pour copy-paste:

    FastTimelapseTask:
        module: 'fast_timelapse_task_RAMM'
        needsmodules:
            laser: 'lasercontrol_logic'
            bf: 'bright-field_logic'
            cam: 'camera_logic'
            daq: 'nidaq_logic'
            focus: 'focus_logic'
            roi: 'roi_logic'
        config:
            path_to_user_config: 'C:/Users/sCMOS-1/qudi_files/qudi_task_config_files/fast_timelapse_task_RAMM.yml'
    """
    # ==================================================================================================================
    # Generic Task methods
    # ==================================================================================================================

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.threadpool = QtCore.QThreadPool()

        self.directory: str = ""
        self.counter: int = 0
        self.user_param_dict: dict = {}
        self.lightsource_dict: dict = {'BF': 0, '405 nm': 1, '488 nm': 2, '561 nm': 3, '640 nm': 4}
        self.user_config_path: str = self.config['path_to_user_config']
        self.n_dz_calibration_cycles: int = 4
        self.sample_name: str = ""
        self.exposure: dict = {}
        self.centered_focal_plane: bool = False
        self.num_z_planes: int = 0
        self.z_step: int = 0
        self.save_path: str = ""
        self.file_format: str = ""
        self.roi_list_path: str = ""
        self.num_iterations: int = 0
        self.imaging_sequence: list = []
        self.autofocus_ok: bool = False
        self.num_frames: int = 0
        self.intensities: list = []
        self.default_exposure: float = 0.05
        self.roi_names: dict = {}
        self.num_roi: int = 0
        self.prefix: str = ""
        self.wavelengths: list = []
        self.num_laserlines: int = 0
        self.dz: list = []
        self.calibration_path: str = ""
        self.hubble_calibration_step: int = 4  # should it be in the config file?
        self.hubble_init_time: float = time()

        print('Task {0} added!'.format(self.name))

    def startTask(self):
        """ """
        # store this value to reset it at the end of task
        self.default_exposure = self.ref['cam'].get_exposure()

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

        # set the ASI stage in trigger mode and set the stage velocity
        self.ref['roi'].set_stage_led_mode('Triggered')
        self.ref['roi'].set_stage_velocity({'x': 3, 'y': 3, 'z': 3})

        # read all user parameters from config
        self.load_user_parameters()
        self.num_roi = len(self.roi_names)

        # control that autofocus has been calibrated and a setpoint is defined
        self.autofocus_ok = self.ref['focus']._calibrated and self.ref['focus']._setpoint_defined
        if self.autofocus_ok:

            # create a directory in which all the data will be saved
            self.directory = self.create_directory(self.save_path)

            # defines the log file
            log_path = os.path.join(self.directory, 'log_info.log')
            formatter = logging.Formatter('%(message)s')
            handler = logging.FileHandler(log_path)
            handler.setFormatter(formatter)
            logger = logging.getLogger('Task_logging')
            logger.setLevel(logging.INFO)
            logger.addHandler(handler)

            # close the default session and start the FTL session on the fpga using the user parameters
            self.ref['laser'].close_default_session()
            # bitfile = 'C:\\Users\\sCMOS-1\\qudi-cbs\\hardware\\fpga\\FPGA\\FPGA Bitfiles\\50ms_FPGATarget_QudiFTLQPDPID_u+Bjp+80wxk.lvbitx'
            bitfile = 'C:\\Users\\sCMOS-1\\qudi-cbs\\hardware\\fpga\\FPGA\\FPGA Bitfiles\\20ms_FPGATarget_QudiFTLQPDPID_u+Bjp+80wxk.lvbitx'
            self.ref['laser'].start_task_session(bitfile)
            print(
                f'z planes : {self.num_z_planes} - wavelengths : {self.wavelengths} - intensities : {self.intensities}')
            self.ref['laser'].run_multicolor_imaging_task_session(self.num_z_planes, self.wavelengths, self.intensities,
                                                                  self.num_laserlines, self.exposure)

            # prepare the camera
            self.num_frames = self.num_roi * self.num_z_planes * self.num_laserlines
            self.ref['cam'].prepare_camera_for_multichannel_imaging(self.num_frames, self.exposure, None, None, None)

            # set the active_roi to none to avoid having two active rois displayed
            # self.ref['roi'].active_roi = None
            self.move_to_roi(self.roi_names[0], True)

            # launch the calibration procedure to measure the tilt of the sample
            print(f'calibration file path: {self.calibration_path}')

            if not self.calibration_path:
                roi_x_positions = np.zeros((self.n_dz_calibration_cycles, self.num_roi//self.hubble_calibration_step+1))
                roi_y_positions = np.zeros((self.n_dz_calibration_cycles, self.num_roi//self.hubble_calibration_step+1))
                roi_z_positions = np.zeros((self.n_dz_calibration_cycles, self.num_roi//self.hubble_calibration_step+1))

                # for each roi, the autofocus positioning is performed. The process is repeated n_dz_calibration_cycles
                # times, in order to get a good average position.
                for n in range(self.n_dz_calibration_cycles):
                    roi_x, roi_y, roi_start_z = self.measure_sample_tilt()
                    roi_x_positions[n, :] = roi_x
                    roi_y_positions[n, :] = roi_y
                    roi_z_positions[n, :] = roi_start_z

                # calculate the average variation of axial displacement between two successive rois
                self.dz = self.fit_surface(roi_x_positions, roi_y_positions, roi_z_positions)

            else:
                with open(self.calibration_path, 'r') as file:
                    calibration = yaml.safe_load(file)
                self.dz = calibration['dz']

        else:
            self.aborted = True
            self.log.warning('Autofocus not calibrated')

    def runTaskStep(self):
        """ Implement one work step of your task here.
        :return: bool: True if the task should continue running, False if it should finish.
        """

        if self.aborted:
            return False

        # --------------------------------------------------------------------------------------------------------------
        # start time-lapse acquisition
        # --------------------------------------------------------------------------------------------------------------

        # start camera acquisition
        self.ref['cam'].stop_acquisition()  # for safety
        self.log.warning('Preparing camera for acquisition ...')
        self.ref['cam'].start_acquisition()

        # --------------------------------------------------------------------------------------------------------------
        # move to ROI and focus (using autofocus and stop when stable)
        # --------------------------------------------------------------------------------------------------------------

        for n, item in enumerate(self.roi_names):

            if self.aborted:
                break

            # go to roi
            # if n > 0:
            self.move_to_roi(item, True)

            # perform the autofocus routine only for the first ROI. For the other ones, simply move the objective
            # according to the axial shift measured during the calibration
            if n == 0:
                # start_position, end_position, z_absolute_position = self.perform_autofocus()
                self.perform_autofocus()
                # calculate the absolute positions of the piezo for each ROI
                z_absolute_position = self.calculate_absolute_z_positions()

            start_position, end_position = self.calculate_start_position(z_absolute_position[n],
                                                                         self.centered_focal_plane,
                                                                         self.num_z_planes, self.z_step)

            # ----------------------------------------------------------------------------------------------------------
            # imaging sequence
            # ----------------------------------------------------------------------------------------------------------
            self.acquire_single_stack(start_position, end_position)

        # go back to the first ROI and the initial piezo position
        self.move_to_roi(self.roi_names[0], False)
        self.ref['focus'].go_to_position(z_absolute_position[0], direct=True)

        # --------------------------------------------------------------------------------------------------------------
        # data saving
        # --------------------------------------------------------------------------------------------------------------

        # get acquired images from the camera
        self.log.warning('Processing data ...')
        image_data = self.ref['cam'].get_acquired_data()

        # launch the saving procedure, saving each movies according to channel and roi
        self.save_hubble_data(image_data)

        return

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

        # set the ASI stage in internal mode
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
            exposure: 0.05  # in s
            centered_focal_plane: False
            num_z_planes: 50
            z_step: 0.25  # in um
            save_path: 'E:/'
            file_format: 'tif'
            roi_list_path: 'pathstem/qudi_files/qudi_roi_lists/roilist_20210101_1128_23_123243.json'
            imaging_sequence: [('488 nm', 3), ('561 nm', 3), ('641 nm', 10)]

        """
        try:
            with open(self.user_config_path, 'r') as stream:
                self.user_param_dict = yaml.safe_load(stream)

                self.sample_name = self.user_param_dict['sample_name']
                self.exposure = self.user_param_dict['exposure']
                self.centered_focal_plane = self.user_param_dict['centered_focal_plane']
                self.num_z_planes = self.user_param_dict['num_z_planes']
                self.z_step = self.user_param_dict['z_step']  # in um
                self.save_path = self.user_param_dict['save_path']
                self.file_format = self.user_param_dict['file_format']
                self.roi_list_path = self.user_param_dict['roi_list_path']
                self.imaging_sequence = self.user_param_dict['imaging_sequence']
                self.calibration_path = self.user_param_dict['axial_calibration_path']

        except Exception as e:  # add the type of exception
            self.log.warning(f'Could not load user parameters for task {self.name}: {e}')

        # establish further user parameters derived from the given ones:

        # create a list of roi names
        self.ref['roi'].load_roi_list(self.roi_list_path)
        # get the list of the roi names
        self.roi_names = self.ref['roi'].roi_names

        # count the number of lightsources
        self.num_laserlines = len(self.imaging_sequence)

        # convert the imaging_sequence given by user into format required by the bitfile
        wavelengths = [self.imaging_sequence[i][0] for i in range(self.num_laserlines)]
        print(f'wavelength first : {wavelengths}')
        for n, key in enumerate(wavelengths):
            if key == 'Brightfield':
                wavelengths[n] = 0
            else:
                wavelengths[n] = self.lightsource_dict[key]
        # wavelengths = [self.lightsource_dict[key] for key in wavelengths]
        print(f'wavelength second : {wavelengths}')
        for i in range(self.num_laserlines, 5):
            wavelengths.append(0)  # must always be a list of length 5: append zeros until necessary length reached
        self.wavelengths = wavelengths

        self.intensities = [self.imaging_sequence[i][1] for i in range(self.num_laserlines)]
        for i in range(self.num_laserlines, 5):
            self.intensities.append(0)

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
        foldername = f'{prefix}_Hubble_{self.sample_name}'
        path = os.path.join(path_stem_with_date, foldername)

        # create the path # no need to check if it already exists due to incremental prefix
        try:
            os.makedirs(path)  # recursive creation of all directories on the path
        except Exception as e:
            self.log.error('Error {0}'.format(e))

        return path

    @staticmethod
    def get_complete_path(directory, roi, channel, file_format):
        """ Compile the complete saving path for each stack of images, according to the roi and acquisition channel.

    :param: int roi = indicate the number of the roi
    :param: int channel = number associated to the selected channel
    :param: str directory = path to the folder where the data will be saved
    :param: int counter = indicate how many time-lapse cycles have been performed

    :return: str complete_path = complete path indicating the folder and the name of the file
        """

        file_name = f'hubble_{str(roi).zfill(3)}_ch_{str(channel).zfill(3)}.{file_format}'
        directory_path = os.path.join(directory, 'channel_'+str(channel), str(roi))

        # check if folder exists, if not: create it
        if not os.path.exists(directory_path):
            try:
                os.makedirs(directory_path)  # recursive creation of all directories on the path
            except Exception as e:
                print(f'Error : {e}')

        complete_path = os.path.join(directory_path, file_name)
        return complete_path

    # ------------------------------------------------------------------------------------------------------------------
    # saving method
    # ------------------------------------------------------------------------------------------------------------------

    @log
    def save_hubble_data(self, image_data):
        """ save all the images separately, according to imaging channel and roi.

        @param image_data: data acquired by the camera during acquisition
        """
        start_frame = 0
        for roi in self.roi_names:
            end_frame = start_frame + self.num_z_planes * self.num_laserlines
            roi_data = image_data[start_frame:end_frame]
            for channel in range(self.num_laserlines):
                data = roi_data[channel:len(roi_data):self.num_laserlines]
                cur_save_path = self.get_complete_path(self.directory, roi, channel, self.file_format)
                self.log.info(f'saving file : {os.path.basename(cur_save_path)}')

                if self.file_format == 'tif':
                    self.save_to_tiff(cur_save_path, data)
                    start_frame = end_frame
                else:
                    self.save_to_npy(cur_save_path, data)
                    start_frame = end_frame

    @staticmethod
    def save_to_tiff(path, data):
        """ Save the image data to a tiff file.

        :param: int n_frames: number of frames (needed to distinguish between 2D and 3D data)
        :param: str path: complete path where the object is saved to (including the suffix .tif)
        :param: data: np.array

        :return: None
        """
        try:
            with TiffWriter(path) as tif:
                tif.save(data.astype(np.uint16))
        except Exception as e:
            print(f'Error while saving file : {e}')

    @staticmethod
    def save_to_npy(path, data):
        """ Save the image data to a npy file. The images are re-formated to uint16, in order to optimize the saving
        time.

        :param: str path: complete path where the object is saved to (including the suffix .tif)
        :param: data: np.array
        :return: None
        """
        try:
            np.save(path, data.astype(np.uint16))
        except Exception as e:
            print(f'Error while saving file : {e}')

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
            metadata[f'Laser line {i+1}'] = self.imaging_sequence[i]['lightsource']
            metadata[f'Laser intensity {i+1} (%)'] = self.imaging_sequence[i]['intensity']
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
            metadata[f'LINE{i+1}'] = (self.imaging_sequence[i]['lightsource'], f'laser line {i+1}')
            metadata[f'INTENS{i+1}'] = (self.imaging_sequence[i]['intensity'], f'laser intensity {i+1}')
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
    # task methods for hubble calibration
    # ------------------------------------------------------------------------------------------------------------------
    @log
    def measure_sample_tilt(self):
        """ Calculate the axial tilt between successive ROI. This tilt is induced by the sample and the stage and is
        reproducible over time. This calibration is used to save time between successive timelapse acquisition. For the
        hubble experiment, since the area explored is quite large (>100 ROIs), the calibration must be faster and the
        focus is performed every "hubble_calibration_step".

        @return array roi_start_z: axial focus position associated to each ROI
                      roi_x, roi_y : 2D positions of the stage for each selected ROI
        """

        roi_start_z = np.zeros((self.num_roi // self.hubble_calibration_step + 1,))
        roi_x = np.zeros((self.num_roi // self.hubble_calibration_step + 1,))
        roi_y = np.zeros((self.num_roi // self.hubble_calibration_step + 1,))

        for n, item in enumerate(self.roi_names):

            if self.aborted:
                break

            if n % self.hubble_calibration_step == 0:

                # go to roi
                print(item)
                self.move_to_roi(item, True)

                # autofocus
                self.ref['focus'].start_autofocus(stop_when_stable=True, search_focus=False)

                # measure the stage position
                pos = self.ref['roi'].stage_position
                x = pos[0]
                y = pos[1]

                # ensure that focus is stable here (autofocus_enabled is True when autofocus is started and once it is
                # stable is set to false)
                busy = self.ref['focus'].autofocus_enabled
                counter = 0
                while busy:
                    counter += 1
                    sleep(0.05)
                    busy = self.ref['focus'].autofocus_enabled
                    if counter > 500:
                        break

                # Save the z position after the focus
                current_z = self.ref['focus'].get_position()
                roi_x[n//self.hubble_calibration_step] = x
                roi_y[n//self.hubble_calibration_step] = y
                roi_start_z[n//self.hubble_calibration_step] = current_z

        # go back to first ROI
        self.move_to_roi(self.roi_names[0], True)

        # move the piezo to its first measured position
        self.ref['focus'].go_to_position(roi_start_z[0])

        return roi_x, roi_y, roi_start_z

    def fit_surface(self, roi_x_positions, roi_y_positions, roi_z_positions):
        """ Compile the axial positions data to calculate the average value and save the graph.

        @param ndarray roi_x_positions: array containing all the x position of each selected ROI, for each repetition
        @param ndarray roi_y_positions: array containing all the y position of each selected ROI, for each repetition
        @param ndarray roi_z_positions: array containing all the axial focus position of each ROI, for each repetition
        @return ndarray dz: array containing the average axial displacement between successive ROIs
        """
        # compute the sample surface
        x_calibration = np.median(roi_x_positions, axis=0)
        y_calibration = np.median(roi_y_positions, axis=0)
        z_calibration = np.median(roi_z_positions, axis=0)
        z_std = np.std(roi_z_positions, axis=0)

        # fit the surface with a paraboloid
        A = np.array([x_calibration*0+1, x_calibration, y_calibration, x_calibration**2, y_calibration**2,
                      x_calibration*y_calibration]).T
        B = z_calibration
        coeff, r, _, s = np.linalg.lstsq(A, B, rcond=None)

        # compare the fit with the calibration
        z_fit = coeff[0]*(x_calibration*0+1) + coeff[1]*x_calibration + coeff[2]*y_calibration +\
            coeff[3]*x_calibration**2 + coeff[4]*y_calibration**2 + coeff[5]*x_calibration*y_calibration
        z_compare = z_calibration - z_fit

        # plot the results to inspect if the values were reproducible
        roi = np.linspace(1, len(x_calibration), len(x_calibration))
        plt.errorbar(roi, z_calibration, yerr=z_std)
        plt.plot(roi, z_fit)
        plt.xlabel('ROI number')
        plt.ylabel('z (in µm)')
        plt.legend({'fit', 'calibration'})
        figure_path = os.path.join(self.directory, f'tilt_surface_calibration.png')
        plt.savefig(figure_path)

        # calculate the dz values based on the fit
        x_roi = np.zeros((self.num_roi,))
        y_roi = np.zeros((self.num_roi,))
        dz = np.zeros((self.num_roi,))
        for n, roi in enumerate(self.roi_names):
            x_roi[n], y_roi[n], _ = self.ref['roi'].get_roi_position(roi)

        z_roi = coeff[0]*(x_roi*0+1) + coeff[1]*x_roi + coeff[2]*y_roi + coeff[3]*x_roi**2 + coeff[4]*y_roi**2 \
            + coeff[5]*x_roi*y_roi
        for n in range(self.num_roi):
            if n > 0:
                dz[n] = z_roi[n] - z_roi[n-1]
            else:
                dz[n] = 0

        # save the x,y,z values and the fit results in a specific file
        data_dict = {'x': x_calibration.tolist(), 'y': y_calibration.tolist(), 'z': z_calibration.tolist(),
                     'dz': dz.tolist(), 'z_std': z_std.tolist(), 'coeff_fit': coeff.tolist(), 'r_fit': r.tolist(),
                     's_fit': s.tolist(), 'z_compare': z_compare.tolist()}
        tilt_path = os.path.join(self.directory, f'tilt_surface_calibration.yml')
        with open(tilt_path, 'w') as outfile:
            yaml.safe_dump(data_dict, outfile, default_flow_style=False)

        return dz

    # ------------------------------------------------------------------------------------------------------------------
    # task methods for hubble acquisition
    # ------------------------------------------------------------------------------------------------------------------

    def move_to_roi(self, item, wait_for_idle):
        """ Move to roi.

        :param str item: name of the roi selected
        :param bool wait_for_idle: indicate if the wait_for_idle routine is required
        """
        self.ref['roi'].set_active_roi(name=item)
        self.ref['roi'].go_to_roi_xy()
        if wait_for_idle:
            self.ref['roi'].stage_wait_for_idle()

    @log
    def perform_autofocus(self):
        """ Perform the focus stabilization for the first ROI.
        """
        # autofocus
        self.ref['focus'].start_autofocus(stop_when_stable=True, search_focus=False)

        # ensure that focus is stable here (autofocus_enabled is True when autofocus is started and once it is
        # stable is set to false)
        busy = self.ref['focus'].autofocus_enabled
        counter = 0
        while busy:
            counter += 1
            sleep(0.05)
            busy = self.ref['focus'].autofocus_enabled
            if counter > 500:  # maybe increase the counter ?
                break

    @staticmethod
    def calculate_start_position(current_pos, centered_focal_plane, num_z_planes, z_step):
        """ This method calculates the piezo position at which the z stack will start. It can either start in the
        current plane or calculate an offset so that the current plane will be centered inside the stack.

        @param current_pos: indicates the current position of the piezo stage
        @param centered_focal_plane: indicates if the scan is done below and above the focal plane (True)
        or if the focal plane is the bottommost plane in the scan (False)
        @param num_z_planes: indicates the number of planes for the stack
        @param z_step: indicates the distance between two successive planes
        @return: two positions, the axial positions of the first plane. And the position where the piezo stage should go
        back at the end of the process.
        """
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

    def calculate_absolute_z_positions(self):
        """ Using the current piezo position, calculate the expected positions for each ROI using the calibration.

        @return: z_positions, the absolute z positions for the next cycle.
        """
        z_positions = np.zeros((self.num_roi,))
        z_positions[0] = self.ref['focus'].get_position()
        for n_roi in range(self.num_roi - 1):
            z_positions[n_roi+1] = z_positions[n_roi] + self.dz[n_roi]

        return z_positions

    @log
    def acquire_single_stack(self, start_position, end_position):
        """ Launch acquisition of a single stack of images.

        @param start_position: starting position of the stack
        @param end_position: position where the piezo should go back after the stack
        """
        # prepare the daq: set the digital output to 0 before starting the task

        self.ref['daq'].write_to_do_channel(self.ref['daq']._daq.start_acquisition_taskhandle, 1,
                                            np.array([0], dtype=np.uint8))

        for plane in range(self.num_z_planes):

            # position the piezo
            position = start_position + plane * self.z_step
            self.ref['focus'].go_to_position(position, direct=True)

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
                if t1 > 1:  # for safety: timeout if no signal received within 1 s
                    self.log.warning('Timeout occurred')
                    break

        self.ref['focus'].go_to_position(end_position, direct=True)
