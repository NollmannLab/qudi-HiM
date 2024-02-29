# -*- coding: utf-8 -*-
"""
Qudi-CBS

An extension to Qudi.

This module contains a task to perform laser induced bleaching at the defined ROIs, for the Airyscan setup.
(Illuminate each ROI with the defined laser lines. All lasers can be switched on simultaneously to speed up the process.
The 405 nm laser is excluded for this task (see form in experiment configurator) to avoid depositing a too high power
within the microscope objective.)

@author: JB.Fiche (originally from F. Barho)

Created on Tuesday March 1 2022 (copied from the task already designed for the RAMM microscope - a new task was created
in case further modifications are specifically required for the Airyscan).
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
from time import sleep
from logic.generic_task import InterruptableTask
from logic.task_helper_functions import get_entry_nested_dict


class Task(InterruptableTask):
    """ This task iterates over all roi given in a file and illuminates this position with the defined laser lines.

    Config example pour copy-paste:

    PhotobleachingTask:
        module: 'photobleaching_task_RAMM'
        needsmodules:
            laser: 'lasercontrol_logic'
            roi: 'roi_logic'
        config:
            path_to_user_config: 'C:/Users/sCMOS-1/qudi_files/qudi_task_config_files/photobleaching_task_RAMM.yml'
    """
    # ==================================================================================================================
    # Generic Task methods
    # ==================================================================================================================

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        print('Task {0} added!'.format(self.name))
        self.user_config_path: str = self.config['path_to_user_config']
        self.roi_counter: int = 0
        self.user_param_dict: dict = {}
        self.illumination_time: int = 0
        self.roi_list_path: list = []
        self.roi_names: list = []
        self.imaging_sequence: dict = {}
        self.intensity_dict: dict = {}

    def startTask(self):
        """ """
        self.log.info('started Task')

        # stop all interfering modes on GUIs and disable GUI actions
        self.ref['roi'].disable_tracking_mode()
        self.ref['roi'].disable_roi_actions()

        self.ref['laser'].stop_laser_output()
        self.ref['laser'].disable_laser_actions()  # includes also disabling of brightfield on / off button

        # warning to the user to make sure the microscope rear port is open
        self.log.warning("Make sure the microscope rear port in open (RL illumination ON)")

        # reset all lasers to zero if values still present on basic imaging GUI
        self.ref['laser'].reset_intensity_dict()

        # make sure the celesta laser source is ready and TTL mode is OFF
        self.ref['laser'].lumencor_wakeup()
        self.ref['laser'].lumencor_set_ttl(False)

        # set stage velocity
        self.ref['roi'].set_stage_velocity({'x': 1, 'y': 1})

        # read all user parameters from config
        self.load_user_parameters()

        # set the intensity of each laser line for the lumencor
        self.ref['laser'].lumencor_set_laser_line_intensities(self.intensity_dict)

        # update the laser intensity dictionary for the lasercontrol_logic
        for key in self.intensity_dict:
            intensity = self.intensity_dict[key]
            self.ref['laser'].update_intensity_dict(key, intensity)

        # initialize a counter to iterate over the ROIs
        self.roi_counter = 0

        # set the active_roi to none to avoid having two active rois displayed
        self.ref['roi'].active_roi = None

    def runTaskStep(self):
        """ Implement one work step of your task here.
        :return bool: True if the task should continue running, False if it should finish.
        """
        # --------------------------------------------------------------------------------------------------------------
        # move to ROI
        # --------------------------------------------------------------------------------------------------------------
        self.ref['roi'].set_active_roi(name=self.roi_names[self.roi_counter])
        self.ref['roi'].go_to_roi_xy()
        self.log.info('Moved to {}'.format(self.roi_names[self.roi_counter]))
        self.ref['roi'].stage_wait_for_idle()

        # --------------------------------------------------------------------------------------------------------------
        # activate lightsources
        # --------------------------------------------------------------------------------------------------------------

        self.ref['laser'].apply_voltage()
        sleep(self.illumination_time)
        self.ref['laser'].voltage_off()

        self.roi_counter += 1
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

        # reset stage velocity to default
        self.ref['roi'].set_stage_velocity({'x': 6, 'y': 6})  # 5.74592

        # for safety, make sure all lasers are off
        self.ref['laser'].voltage_off()

        # reset all lasers to zero to not mix up the state on Basic GUI
        self.ref['laser'].reset_intensity_dict()

        # enable gui actions
        # roi gui
        self.ref['roi'].enable_tracking_mode()
        self.ref['roi'].enable_roi_actions()
        # basic imaging gui
        self.ref['laser'].enable_laser_actions()

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
            illumination_time: 5  # in min
            imaging_sequence: [('488 nm', 30), ('561 nm', 30), ('641 nm', 100)]
            roi_list_path: 'pathstem/qudi_files/qudi_roi_lists/roilist_20210101_1128_23_123243.json'
        """
        try:
            with open(self.user_config_path, 'r') as stream:
                self.user_param_dict = yaml.safe_load(stream)

                self.illumination_time = self.user_param_dict['illumination_time'] * 60  # conversion from min to s
                self.imaging_sequence = self.user_param_dict['imaging_sequence']
                self.roi_list_path = self.user_param_dict['roi_list_path']

        except Exception as e:  # add the type of exception
            self.log.warning(f'Could not load user parameters for task {self.name}: {e}')

        # establish further user parameters derived from the given ones:
        self.ref['roi'].load_roi_list(self.roi_list_path)
        self.roi_names = self.ref['roi'].roi_names

        # Load the laser and intensity dictionary used in lasercontrol_logic
        laser_dict = self.ref['laser'].get_laser_dict()
        intensity_dict = self.ref['laser'].init_intensity_dict()
        imaging_sequence = [(*get_entry_nested_dict(laser_dict, self.imaging_sequence[i][0], 'label'),
                             self.imaging_sequence[i][1]) for i in range(len(self.imaging_sequence))]

        # Update the intensity dictionary
        for i in range(len(imaging_sequence)):
            key = imaging_sequence[i][0]
            intensity_dict[key] = imaging_sequence[i][1]

        self.intensity_dict = intensity_dict
