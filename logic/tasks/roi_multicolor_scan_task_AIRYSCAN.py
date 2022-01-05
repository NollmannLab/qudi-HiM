# -*- coding: utf-8 -*-
"""
Qudi-CBS

An extension to Qudi.

This module contains a task to perform a multicolor scan on RAMM setup iterating over a list of ROIs.
(Take for each region of interest (ROI) a stack of images using a sequence of different laserlines or intensities
in each plane of the stack.)

@author: F. Barho, JB. Fiche

Created on Wed March 30 2021
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
from time import sleep
from datetime import datetime
from logic.generic_task import InterruptableTask
from logic.task_helper_functions import get_entry_nested_dict
from logic.task_logging_functions import write_dict_to_file


class Task(InterruptableTask):  # do not change the name of the class. it is always called Task !
    """ This task iterates over all roi given in a file and acquires a series of planes in z direction
    using a sequence of lightsources for each plane, for each roi.

    Config example pour copy-paste:

        ROIMulticolorScanTask:
            module: 'roi_multicolor_scan_task_AIRYSCAN'
            needsmodules:
                laser: 'lasercontrol_logic'
                daq: 'daq_logic'
                roi: 'roi_logic'
            config:
                path_to_user_config: 'C:/Users/MFM/qudi_files/qudi_task_config_files/ROI_multicolor_scan_task_AIRYSCAN.yml'
                IN7_ZEN : 0
                OUT7_ZEN : 1
                OUT8_ZEN : 3
                camera_global_exposure : 2
    """
    # ==================================================================================================================
    # Generic Task methods
    # ==================================================================================================================

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        print('Task {0} added!'.format(self.name))
        self.user_config_path = self.config['path_to_user_config']
        print("Path to user config file : {}".format(self.user_config_path))
        self.roi_counter = None
        self.directory = None
        self.user_param_dict = {}
        self.sample_name = None
        self.is_dapi = False
        self.is_rna = False
        self.num_z_planes = None
        self.imaging_sequence = []
        self.save_path = None
        self.roi_list_path = None
        self.roi_names = []
        self.num_laserlines = None
        self.intensity_dict = {}
        self.ao_channel_sequence = []
        self.lumencor_channel_sequence = []
        self.IN7_ZEN = self.config['IN7_ZEN']
        self.OUT7_ZEN = self.config['OUT7_ZEN']
        self.OUT8_ZEN = self.config['OUT8_ZEN']
        self.camera_global_exposure = self.config['camera_global_exposure']
        self.prefix = None

    def startTask(self):
        """ """
        self.log.info('started Task')

        # stop all interfering modes on GUIs and disable GUI actions
        self.ref['roi'].disable_tracking_mode()
        self.ref['roi'].disable_roi_actions()

        self.ref['laser'].stop_laser_output()
        self.ref['laser'].disable_laser_actions()  # includes also disabling of brightfield on / off button

        # set stage velocity
        self.ref['roi'].set_stage_velocity({'x': 1, 'y': 1})

        # read all user parameters from config
        self.load_user_parameters()

        # create the daq channels
        self.ref['daq'].initialize_digital_channel(self.OUT7_ZEN, 'input')
        self.ref['daq'].initialize_digital_channel(self.OUT8_ZEN, 'input')
        self.ref['daq'].initialize_digital_channel(self.camera_global_exposure, 'input')
        self.ref['daq'].initialize_digital_channel(self.IN7_ZEN, 'output')

        # define the laser intensities as well as the sequence for the daq external trigger.
        # Set : - all laser lines to OFF and wake the source up
        #       - all the ao_channels to +5V
        #       - the celesta laser source in external TTL mode
        #       - the intensity of each laser line according to the task parameters
        self.format_imaging_sequence()
        self.ref['laser'].lumencor_wakeup()
        self.ref['laser'].stop_laser_output()
        self.ref['laser'].disable_laser_actions()  # includes also disabling of brightfield on / off button
        self.ref['daq'].initialize_ao_channels()
        self.ref['laser'].lumencor_set_ttl(True)
        self.ref['laser'].lumencor_set_laser_line_intensities(self.intensity_dict)

        # indicate to the user the parameters he should use for zen configuration
        self.log.warning('############ ZEN PARAMETERS ############')
        self.log.warning('This task is compatible with experiment ZEN/HiM_celesta')
        self.log.warning('Number of acquisition loops in ZEN experiment designer : {}'.format(len(self.roi_names)/2))
        self.log.warning('For each acquisition block C={} and Z={}'.format(self.num_laserlines, self.num_z_planes))
        self.log.warning('The number of ticked channels should be equal to {}'.format(self.num_laserlines))
        self.log.warning('Select the autofocus block and hit "Start Experiment"')
        self.log.warning('########################################')

        # wait for the trigger from ZEN indicating that the experiment is starting
        trigger = self.ref['daq'].read_di_channel(self.OUT7_ZEN, 1)
        while trigger == 0 and not self.aborted:
            sleep(.1)
            trigger = self.ref['daq'].read_di_channel(self.OUT7_ZEN, 1)

        # create a directory in which all the data will be saved
        self.directory = self.create_directory(self.save_path)

        # if dapi data is acquired, save a dapi channel info file in order to make the link to the bokeh app
        if self.is_dapi:
            imag_dict = {'imaging_sequence': self.imaging_sequence}
            dapi_channel_info_path = os.path.join(self.directory, 'DAPI_channel_info.yml')
            write_dict_to_file(dapi_channel_info_path, imag_dict)

        # save the acquisition parameters
        metadata = self.get_metadata()
        self.save_metadata_file(metadata, os.path.join(self.directory, "parameters.yml"))

        # initialize a counter to iterate over the ROIs
        self.roi_counter = 0
        # set the active_roi to none to avoid having two active rois displayed
        self.ref['roi'].active_roi = None

    def runTaskStep(self):
        """ Implement one work step of your task here.
        :return bool: True if the task should continue running, False if it should finish.
        """

        # --------------------------------------------------------------------------------------------------------------
        # move to the first ROI
        # --------------------------------------------------------------------------------------------------------------

        # define the name of the file according to the roi number and cycle
        scan_name = self.file_name(self.roi_names[self.roi_counter])

        # go to roi
        self.ref['roi'].set_active_roi(name=self.roi_names[self.roi_counter])
        self.ref['roi'].go_to_roi_xy()
        self.log.info('Moved to {} xy position'.format(self.roi_names[self.roi_counter]))
        self.ref['roi'].stage_wait_for_idle()
        self.roi_counter += 1

        # --------------------------------------------------------------------------------------------------------------
        # autofocus (ZEN)
        # --------------------------------------------------------------------------------------------------------------

        # send trigger to ZEN to start the autofocus search
        sleep(5)
        self.ref['daq'].write_to_do_channel(self.IN7_ZEN, 1, 1)
        sleep(0.1)
        self.ref['daq'].write_to_do_channel(self.IN7_ZEN, 1, 0)

        # wait for ZEN trigger indicating the task is completed
        trigger = self.ref['daq'].read_di_channel(self.OUT8_ZEN, 1)
        while trigger == 0 and not self.aborted:
            sleep(.1)
            trigger = self.ref['daq'].read_di_channel(self.OUT8_ZEN, 1)

        # --------------------------------------------------------------------------------------------------------------
        # first imaging sequence
        # --------------------------------------------------------------------------------------------------------------

        # make sure the celesta laser source is ready
        self.ref['laser'].lumencor_wakeup()

        # launch the acquisition task
        sleep(5)
        self.ref['daq'].write_to_do_channel(self.IN7_ZEN, 1, 1)
        sleep(0.1)
        self.ref['daq'].write_to_do_channel(self.IN7_ZEN, 1, 0)

        for plane in range(self.num_z_planes):
            for i in range(len(self.imaging_sequence)):

                # daq waiting for global_exposure trigger from the camera ----------------------------------------------
                error = self.wait_for_camera_trigger(1)
                if error is True:
                    return False

                # switch the selected laser line ON --------------------------------------------------------------------
                # self.ref['laser'].lumencor_set_laser_line_emission(self.lumencor_channel_sequence[i])
                self.ref['daq'].write_to_ao_channel(5, self.ao_channel_sequence[i])

                # daq waiting for global_exposure trigger from the camera to end ---------------------------------------
                error = self.wait_for_camera_trigger(0)
                if error is True:
                    return False

                # switch the selected laser line OFF -------------------------------------------------------------------
                self.ref['daq'].write_to_ao_channel(0, self.ao_channel_sequence[i])

        # save the file name
        self.save_file_name(os.path.join(self.directory, 'movie_name.txt'), scan_name)

        # --------------------------------------------------------------------------------------------------------------
        # move to the second ROI
        # --------------------------------------------------------------------------------------------------------------

        # define the name of the file according to the roi number and cycle
        scan_name = self.file_name(self.roi_names[self.roi_counter])

        # go to roi
        self.ref['roi'].set_active_roi(name=self.roi_names[self.roi_counter])
        self.ref['roi'].go_to_roi_xy()
        self.log.info('Moved to {} xy position'.format(self.roi_names[self.roi_counter]))
        self.ref['roi'].stage_wait_for_idle()
        self.roi_counter += 1

        # --------------------------------------------------------------------------------------------------------------
        # second imaging sequence
        # --------------------------------------------------------------------------------------------------------------

        # launch the acquisition task
        sleep(5)
        self.ref['daq'].write_to_do_channel(self.IN7_ZEN, 1, 1)
        sleep(0.1)
        self.ref['daq'].write_to_do_channel(self.IN7_ZEN, 1, 0)

        for plane in range(self.num_z_planes):
            for i in range(len(self.imaging_sequence)):

                # daq waiting for global_exposure trigger from the camera ----------------------------------------------
                error = self.wait_for_camera_trigger(1)
                if error is True:
                    return False

                # switch the selected laser line ON --------------------------------------------------------------------
                # self.ref['laser'].lumencor_set_laser_line_emission(self.lumencor_channel_sequence[i])
                self.ref['daq'].write_to_ao_channel(5, self.ao_channel_sequence[i])

                # daq waiting for global_exposure trigger from the camera to end ---------------------------------------
                error = self.wait_for_camera_trigger(0)
                if error is True:
                    return False

                # switch the selected laser line OFF -------------------------------------------------------------------
                self.ref['daq'].write_to_ao_channel(0, self.ao_channel_sequence[i])

        # save the file name
        self.save_file_name(os.path.join(self.directory, 'movie_name.txt'), scan_name)

        return self.roi_counter < len(self.roi_names)

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

        # reset the lumencor state
        self.ref['laser'].lumencor_set_ttl(False)
        self.ref['laser'].voltage_off()

        # reset stage velocity to default
        self.ref['roi'].set_stage_velocity({'x': 6, 'y': 6})  # 5.74592

        # enable gui actions
        # roi gui
        self.ref['roi'].enable_tracking_mode()
        self.ref['roi'].enable_roi_actions()

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
                self.num_z_planes = self.user_param_dict['num_z_planes']
                self.imaging_sequence = self.user_param_dict['imaging_sequence']
                self.save_path = self.user_param_dict['save_path']
                self.roi_list_path = self.user_param_dict['roi_list_path']

        except Exception as e:  # add the type of exception
            self.log.warning(f'Could not load user parameters for task {self.name}: {e}')

        # establish further user parameters derived from the given ones:
        # create a list of roi names
        self.ref['roi'].load_roi_list(self.roi_list_path)
        # get the list of the roi names
        self.roi_names = self.ref['roi'].roi_names
        # get the number of laser lines
        self.num_laserlines = len(self.imaging_sequence)

    # ------------------------------------------------------------------------------------------------------------------
    # communication with ZEN
    # ------------------------------------------------------------------------------------------------------------------

    def wait_for_camera_trigger(self, value):
        """ This method contains a loop to wait for the camera exposure starts or stops.

        :return: bool ready: True: trigger was received, False: experiment cannot be started because ZEN is not ready
        """
        bit_value = self.ref['daq'].read_di_channel(self.camera_global_exposure, 1)
        counter = 0
        error = False

        while bit_value != value and error is False and not self.aborted:
            counter += 1
            bit_value = self.ref['daq'].read_di_channel(self.camera_global_exposure, 1)
            if counter > 10000:
                self.log.warning(
                    'No trigger was detected during the past 60s... experiment is aborted')
                error = True

        return error

    # ------------------------------------------------------------------------------------------------------------------
    # data for imaging cycle with Lumencor
    # ------------------------------------------------------------------------------------------------------------------

    def format_imaging_sequence(self):
        """ Format the imaging_sequence dictionary for the celesta laser source and the daq ttl/ao sequence for the
        triggers. For controlling the laser source, two solutions are tested :
        - directly by communicating with the Lumencor, in that case the intensity dictionary is used to predefine the
        intensity of each laser line, and the list emission_state contains the succession of emission state for the
        acquisition
        - by using the Lumencor is external trigger mode. In that case, the intensity dictionary is used the same way
        but the DAQ is controlling the succession of emission state
        """

    # Load the laser and intensity dictionary used in lasercontrol_logic -----------------------------------------------
        laser_dict = self.ref['laser'].get_laser_dict()
        intensity_dict = self.ref['laser'].init_intensity_dict()
        # From [('488 nm', 3), ('561 nm', 3)] to [('laser2', 3), ('laser3', 3), (10,)]
        imaging_sequence = [(*get_entry_nested_dict(laser_dict, self.imaging_sequence[i][0], 'label'),
                             self.imaging_sequence[i][1]) for i in range(len(self.imaging_sequence))]

    # Load the daq dictionary for ttl ----------------------------------------------------------------------------------
        daq_dict = self.ref['daq']._daq.get_dict()
        ao_channel_sequence = []
        lumencor_channel_sequence = []

    # Update the intensity dictionary and defines the sequence of ao channels for the daq ------------------------------
        for i in range(len(imaging_sequence)):
            key = imaging_sequence[i][0]
            intensity_dict[key] = imaging_sequence[i][1]
            if daq_dict[key]['channel']:
                ao_channel_sequence.append(daq_dict[key]['channel'])
            else:
                self.log.warning('The wavelength {} is not configured for external trigger mode with DAQ'.format(
                    laser_dict[key]['wavelength']))

            emission_state = np.zeros((len(laser_dict),), dtype=int)
            emission_state[laser_dict[key]['channel']] = 1
            lumencor_channel_sequence.append(emission_state.tolist())

        self.intensity_dict = intensity_dict
        self.ao_channel_sequence = ao_channel_sequence
        self.lumencor_channel_sequence = lumencor_channel_sequence

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

    def file_name(self, roi_number):
        """ Define the complete name of the image data file.

        :param: str roi_number: string identifier of the current ROI for which a complete path shall be created
        :return: str complete_path: such as directory/ROI_001/scan_001_004_ROI.tif (experiment nb. 001, ROI nb. 004)
        """

        roi_number_inv = roi_number.strip('ROI_')+'_ROI'  # for compatibility with analysis format

        if self.is_dapi:
            file_name = f'scan_{self.prefix}_DAPI_{roi_number_inv}'
        elif self.is_rna:
            file_name = f'scan_{self.prefix}_RNA_{roi_number_inv}'
        else:
            file_name = f'scan_{self.prefix}_{roi_number_inv}'

        return file_name

    @staticmethod
    def save_file_name(file, movie_name):
        with open(file, 'a+') as outfile:
            outfile.write(movie_name)
            outfile.write("\n")

    # ------------------------------------------------------------------------------------------------------------------
    # metadata
    # ------------------------------------------------------------------------------------------------------------------

    def get_metadata(self):
        """ Get a dictionary containing the metadata in a plain text easy readable format.

        :return: dict metadata
        """
        metadata = {'Sample name': self.sample_name, 'Scan number of planes (um)': self.num_z_planes,
                    'Number laserlines': self.num_laserlines}
        for i in range(self.num_laserlines):
            metadata[f'Laser line {i + 1}'] = self.imaging_sequence[i][0]
            metadata[f'Laser intensity {i + 1} (%)'] = self.imaging_sequence[i][1]

        for roi in self.roi_names:
            pos = self.ref['roi'].get_roi_position(roi)
            metadata[roi] = f'X = {pos[0]} - Y = {pos[1]}'

        return metadata

    def save_metadata_file(self, metadata, path):
        """ Save a txt file containing the metadata dictionary.

        :param dict metadata: dictionary containing the metadata
        :param str path: pathname
        """
        with open(path, 'w') as outfile:
            yaml.safe_dump(metadata, outfile, default_flow_style=False)
        self.log.info('Saved metadata to {}'.format(path))
