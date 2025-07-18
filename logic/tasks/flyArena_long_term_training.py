# -*- coding: utf-8 -*-
"""
Qudi-CBS

An extension to Qudi.

This module contains the Hi-M Experiment for the Airyscan experimental setup using confocal configuration.

@author: JB. Fiche
Created on Tue July 16 2025

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
from logic.generic_task import InterruptableTask
import os
from time import sleep, time
from ruamel.yaml import YAML
import logging


class Task(InterruptableTask):
    """ Dummy task, does nothing. """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # experiment parameters
        self.user_config_path = self.config['path_to_user_config']
        self.yaml = YAML()
        self.user_param_dict: dict = {}
        self.sample_name: str = ""
        self.training_cycles: int = 0
        self.resting_time: int = 0
        self.training_duration: int = 0
        self.odor: str = ""
        self.air_flow: float = 0.
        self.prep_time: int = 0
        self.pattern: str = ""
        self.t_on: float = 0.
        self.t_off: float = 0.

        # general parameters
        self.abort: bool = False
        self.stimulation_counter: int = 0
        self.odor_number: int = 0

    def startTask(self):
        """ Initialize the task """

        # initialization of the training - make sure that all GUI actions are disabled
        self.ref['odor'].disable_odor_circuit_actions()
        self.ref['opto'].disable_optogenetic_actions()

        # load the parameters
        self.load_parameters()

        # initialize odor circuit & opto GUIs based on the parameters
        self.initialize_task()

        # initialize stimulation counter
        self.stimulation_counter = 0

    def runTaskStep(self):
        """ Each step corresponds to a single stimulation sequence """
        if not self.aborted:
            self.stimulation_counter += 1

        # prepare odor
        self.ref['odor'].launch_odor_preparation()
        self.counter(self.prep_time, task='prep')

        # inject odor
        self.ref['odor'].launch_odor_injection()
        self.counter(self.prep_time, task='inject')

        # launch stimulation sequence
        if not self.aborted:
            self.ref['opto'].launch_stimulation()
            while self.ref['opto'].stimulation_launched:
                sleep(0.5)

        return (self.stimulation_counter < self.training_cycles) and (not self.aborted)

    def pauseTask(self):
        """ Dummy pause """
        sleep(1)
        print('paused task')

    def resumeTask(self):
        """ Dummy resume """
        sleep(1)
        print('resumed task')

    def cleanupTask(self):
        """ Set all GUIs to their initial state  """
        self.ref['odor'].enable_odor_circuit_actions()
        self.ref['opto'].enable_optogenetic_actions()
        self.finish_task()

        # self.task_logger.info('task cleaned up')
        # self.task_logger.removeHandler(self.file_handler)
        # self.task_logger.info('task cleaned up')

    def checkExtraStartPrerequisites(self):
        """ Check extra start prerequisites, there are none """
        print('things needed for task to start')
        return True

    def checkExtraPausePrerequisites(self):
        """ Check extra pause prerequisites, there are none """
        print('things needed for task to pause')
        return True

    def load_parameters(self):
        """
        Load task parameters
        """
        try:
            with open(self.user_config_path, 'r') as stream:
                self.user_param_dict = self.yaml.load(stream)

                self.sample_name = self.user_param_dict['sample_name']
                self.training_cycles = self.user_param_dict['training_cycles']
                self.resting_time = self.user_param_dict['resting_time']
                self.training_duration = self.user_param_dict['training_duration']
                self.odor = self.user_param_dict['odor']
                self.air_flow = self.user_param_dict['air_flow']
                self.prep_time = self.user_param_dict['prep_time']
                self.pattern = self.user_param_dict['patterns']
                self.t_on = self.user_param_dict['t_on']
                self.t_off = self.user_param_dict['t_off']

        except Exception as e:  # add the type of exception
            self.log.warning(f'Could not load user parameters for task {self.name}: {e}')

    def initialize_task(self):
        """
        Initialize the GUIs based on the loaded parameters
        """
        # close all valves & MFCs and make sure opto stimulation is off
        self.ref['odor'].stop_flow_measurement()
        self.ref['odor'].stop_air_flow()
        self.ref['opto'].close_shutter()
        self.ref['opto'].display_off()

        # initialize the odor_circuit
        sleep(2)
        self.ref['odor'].start_air_flow(self.air_flow, config=1)
        self.odor_number = self.ref['odor'].update_odor_circuit_gui(True, self.odor, self.air_flow)

        # initialize the optogenetics actions
        self.ref['opto'].update_opto_gui(self.training_duration, self.t_on, self.t_off, self.pattern)

    def finish_task(self):
        """
        Finish the task by closing the odor circuit, all MFCs and making sure the opto is off.
        """
        self.ref['odor'].update_odor_circuit_gui(False, self.odor, self.air_flow)

        # close all valves & MFCs and make sure opto stimulation is off
        self.ref['odor'].stop_flow_measurement()
        self.ref['odor'].stop_air_flow()
        self.ref['odor'].close_odor_circuit()
        self.ref['opto'].close_shutter()
        self.ref['opto'].display_off()

    def counter(self, dt, task='prep'):
        """
        Define a counter for odor preparation or injection.
        @param dt: (int) time to wait before stopping the counter
        @param task: (str) indicate to which task the counter should be associated (either for odor preparation of
        injection)
        """
        t0 = time()
        n = 0
        while time() - t0 < dt:
            sleep(1)
            n += 1

            # depending on the task, update different timer on the GUI
            if task == "prep":
                self.ref['odor'].update_odor_preparation_timer(n)
            elif task == "inject":
                self.ref['odor'].update_odor_injection_timer(n)



