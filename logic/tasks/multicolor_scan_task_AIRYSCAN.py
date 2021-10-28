# -*- coding: utf-8 -*-
"""
Qudi-CBS

An extension to Qudi.

This module contains a task to perform a multicolor scan on PALM setup.
(Take at a given position a sequence of images in a stack of planes with different laserlines or intensities.)

@author: F. Barho, JB. Fiche

Created on Wed Mar 17 2021
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
import yaml
# from datetime import datetime
# import os
# from time import sleep
import numpy as np

from logic.generic_task import InterruptableTask
from logic.task_helper_functions import get_entry_nested_dict


class Task(InterruptableTask):  # do not change the name of the class. it is always called Task !
    """ This task does an acquisition of a stack of images from different channels or using different intensities.

    Config example:

        MulticolorScanTask:
            module: 'multicolor_scan_task_AIRYSCAN'
            needsmodules:
                daq : 'daq_logic'
                laser : 'lasercontrol_logic'
            config:
                path_to_user_config: 'C:/Users/MFM/qudi_files/qudi_task_config_files/multicolor_scan_task_AIRYSCAN.yml'
    """
    # ==================================================================================================================
    # Generic Task methods
    # ==================================================================================================================

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        print('Task {0} added!'.format(self.name))
        self.user_config_path = self.config['path_to_user_config']
        self.err_count = None
        self.laser_allowed = False
        self.user_param_dict = {}
        self.intensity_dict = {}
        self.ao_channel_sequence = []
        self.lumencor_channel_sequence = []
        self.sample_name = None
        self.num_z_planes = None
        self.imaging_sequence = []
        self.step_counter = None
        self.num_laserlines = None
        self.IN7_ZEN = self.config['IN7_ZEN']
        self.OUT7_ZEN = self.config['OUT7_ZEN']
        self.OUT8_ZEN = self.config['OUT8_ZEN']
        self.camera_global_exposure = self.config['camera_global_exposure']

    def startTask(self):
        """ """
        self.log.info('started Task')
        self.err_count = 0  # initialize the error counter (counts number of missed triggers for debug)

        # read all user parameters from config
        self.load_user_parameters()

        # create the daq channels
        self.ref['daq'].initialize_digital_channel(self.OUT7_ZEN, 'input')
        self.ref['daq'].initialize_digital_channel(self.OUT8_ZEN, 'input')
        self.ref['daq'].initialize_digital_channel(self.camera_global_exposure, 'input')
        self.ref['daq'].initialize_digital_channel(self.IN7_ZEN, 'output')

        # define the laser intensities as well as the sequence for the daq external trigger.
        # Set : - all laser lines to OFF
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
        self.log.warning('This task is compatible with experiment ZEN/HiM_single_scan_celesta')
        self.log.warning('The number of planes for Z-Stack is {}'.format(self.num_z_planes))
        self.log.warning('The number of ticked channels should be equal to {}'.format(self.num_laserlines))
        self.log.warning('Hit "Start Experiment"')
        self.log.warning('########################################')

        # initialize the counter (corresponding to the number of planes already acquired)
        self.step_counter = 0

    def runTaskStep(self):
        """ Implement one work step of your task here.
        :return bool: True if the task should continue running, False if it should finish.
        """
        # if not self.laser_allowed:
        #     return False  # skip runTaskStep and directly go to cleanupTask

        # --------------------------------------------------------------------------------------------------------------
        # imaging sequence
        # --------------------------------------------------------------------------------------------------------------

        # use a while loop to catch the exception when a trigger is missed and just repeat the last (missed) image
        for i in range(len(self.imaging_sequence)):

            # daq waiting for global_exposure trigger from the camera --------------------------------------------------
            error = self.wait_for_camera_trigger(1)
            if error is True:
                return False

            # switch the selected laser line ON ------------------------------------------------------------------------
            # self.ref['laser'].lumencor_set_laser_line_emission(self.lumencor_channel_sequence[i])
            self.ref['daq'].write_to_ao_channel(5, self.ao_channel_sequence[i])

            # daq waiting for global_exposure trigger from the camera to end -------------------------------------------
            error = self.wait_for_camera_trigger(0)
            if error is True:
                return False

            # switch the selected laser line OFF -----------------------------------------------------------------------
            self.ref['daq'].write_to_ao_channel(0, self.ao_channel_sequence[i])

        self.step_counter += 1
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
        self.ref['laser'].lumencor_set_ttl(False)
        self.ref['laser'].voltage_off()
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
                self.user_param_dict = yaml.safe_load(stream)

                self.num_z_planes = self.user_param_dict['num_z_planes']
                self.imaging_sequence = self.user_param_dict['imaging_sequence']

        except Exception as e:  # add the type of exception
            self.log.warning(f'Could not load user parameters for task {self.name}: {e}')
            return

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

        while bit_value != value and error is False:
            counter += 1
            bit_value = self.ref['daq'].read_di_channel(self.camera_global_exposure, 1
                                                        )
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
