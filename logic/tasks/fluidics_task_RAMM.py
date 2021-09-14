# -*- coding: utf-8 -*-
"""
Qudi-CBS

An extension to Qudi.

This module contains the fluidics task for the RAMM setup.
Inject a sequence of buffers and / or a probe in the sample.

@author: F. Barho

Created on March 16, 2021
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
from time import sleep
import yaml


class Task(InterruptableTask):
    """ Fluidic injection task for the taskrunner.

    Config example pour copy-paste:

    FluidicsTask:
        module: 'fluidics_task_RAMM'
        needsmodules:
            valves: 'valve_logic'
            pos: 'positioning_logic'
            flow: 'flowcontrol_logic'
        config:
            path_to_user_config: 'C:/Users/sCMOS-1/qudi_files/qudi_task_config_files/fluidics_task_RAMM.yml'
    """
    # ==================================================================================================================
    # Generic Task methods
    # ==================================================================================================================

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        print('Task {0} added!'.format(self.name))
        self.user_config_path = self.config['path_to_user_config']
        self.step_counter = None
        self.user_param_dict = {}
        self.needle_pos = 0
        self.rt_injection = 0

    def startTask(self):
        """ """
        self.log.info('started Task')

        # disable actions on Fluidics GUI (except from flowrate and pressure measurement mode)
        self.ref['valves'].disable_valve_positioning()
        self.ref['flow'].disable_flowcontrol_actions()
        self.ref['pos'].disable_positioning_actions()

        # load user parameters
        self.load_user_parameters()

        # initialize a counter to iterate over the injections in the procedure
        self.step_counter = 0

        # position the needle in the probe in case a probe is injected
        if self.probe_list:
            # control if experiment can be started : origin defined in position logic ?
            if not self.ref['pos'].origin:
                self.log.warning(
                    'No position 1 defined for injections. Experiment can not be started. Please define position 1')
                return
            # position the needle in the probe
            self.ref['pos'].start_move_to_target(self.probe_list[0][0])

            # keep in memory the position of the needle
            self.needle_pos = self.probe_list[self.probe_counter-1][0]

        # set the valve default positions for injection
        self.ref['valves'].set_valve_position('b', 2)  # inject probe
        self.ref['valves'].wait_for_idle()
        self.ref['valves'].set_valve_position('c', 2)  # towards pump
        self.ref['valves'].wait_for_idle()

    def runTaskStep(self):
        """ Implement one work step of your task here. The task step iterates over then number of injection steps to
        be done.
        :return bool: True if the task should continue running, False if it should finish.
        """
        if self.probe_list:
            # go directly to cleanupTask if position 1 is not defined
            if not self.ref['pos'].origin:
                return False

        print(f'step: {self.step_counter+1}')

        if self.hybridization_list[self.step_counter]['product'] is not None:  # an injection step
            # set the 8 way valve to the position corresponding to the product
            product = self.hybridization_list[self.step_counter]['product']
            valve_pos = self.buffer_dict[product]
            self.ref['valves'].set_valve_position('a', valve_pos)
            self.ref['valves'].wait_for_idle()

            # for the RAMM, the needle is connected to valve position 7. If this valve is called more than once,
            # the needle will be moved to the next position. The procedure was added to make the DAPI injection
            # easier.
            if self.rt_injection == 0 and valve_pos == 7:
                self.rt_injection += 1
                self.needle_pos += 1
            elif self.rt_injection > 0 and valve_pos == 7:
                self.ref['pos'].start_move_to_target(self.needle_pos)
                self.rt_injection += 1
                self.needle_pos += 1
                sleep(15)

            # pressure regulation
            self.ref['flow'].set_pressure(0.0)  # as initial value
            self.ref['flow'].start_pressure_regulation_loop(self.hybridization_list[self.step_counter]['flowrate'])
            # start counting the volume of buffer or probe
            sampling_interval = 1  # in seconds
            self.ref['flow'].start_volume_measurement(self.hybridization_list[self.step_counter]['volume'], sampling_interval)

            ready = self.ref['flow'].target_volume_reached
            while not ready:
                sleep(2)
                ready = self.ref['flow'].target_volume_reached
                if self.aborted:
                    ready = True
            self.ref['flow'].stop_pressure_regulation_loop()
            sleep(2)  # waiting time to wait until last regulation step is finished, afterwards reset pressure to 0
            self.ref['flow'].set_pressure(0.0)
        else:  # an incubation step
            incubation_time = self.hybridization_list[self.step_counter]['time']
            print(f'Incubation time.. {incubation_time} s')
            self.ref['valves'].set_valve_position('c', 1)  # towards syringe
            self.ref['valves'].wait_for_idle()

            # allow abort by splitting the waiting time into small intervals of 30 s
            num_steps = incubation_time // 30
            remainder = incubation_time % 30
            for i in range(num_steps):
                if not self.aborted:
                    sleep(30)

            if not self.aborted:
                sleep(remainder)

            self.ref['valves'].set_valve_position('c', 2)  # towards pump
            self.ref['valves'].wait_for_idle()
            print('Incubation time finished')

        self.step_counter += 1

        if self.aborted:
            return True  # avoid error when aborting during last iteration of runTaskStep

        return self.step_counter < len(self.hybridization_list)

    def pauseTask(self):
        """ Pause """
        self.log.info('pauseTask called')

    def resumeTask(self):
        """ Resume """
        self.log.info('resumeTask called')

    def cleanupTask(self):
        """ Cleanup """
        self.log.info('cleanupTask called')

        self.ref['flow'].set_pressure(0.0)

        # set valve default positions
        self.ref['valves'].set_valve_position('c', 1)
        self.ref['valves'].wait_for_idle()
        self.ref['valves'].set_valve_position('b', 1)
        self.ref['valves'].wait_for_idle()
        self.ref['valves'].set_valve_position('a', 1)
        self.ref['valves'].wait_for_idle()

        # # verify that flux is closed
        # is_closed_position = self.ref['valves'].get_valve_position('c')
        # if is_closed_position != 1:
        #     self.ref['valves'].set_valve_position('c', 1)
        #     self.ref['valves'].wait_for_idle()

        # enable actions on Fluidics GUI
        self.ref['valves'].enable_valve_positioning()
        self.ref['flow'].enable_flowcontrol_actions()
        self.ref['pos'].enable_positioning_actions()

        self.log.info('Cleanup task finished')

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
            injections_path: 'pathstem/qudi_files/qudi_injection_parameters/injections.yml'
        """
        try:
            with open(self.user_config_path, 'r') as stream:
                self.user_param_dict = yaml.safe_load(stream)  # yaml.full_load when yaml package updated

                self.injections_path = self.user_param_dict['injections_path']

            self.load_injection_parameters()

        except Exception as e:  # add the type of exception
            self.log.warning(f'Could not load user parameters for task {self.name}: {e}')

    def load_injection_parameters(self):
        """ This function reads from a document containing the injection information in a specific format the
        following elements: the dictionary with the valve positions as keys and the associated buffers,
        the dictionary with probe position numbers as keys and probe identifiers as values (this can be an empty
        dictionary if no probes are injected or should contain only one probe number for this kind of task, other
        than the Hi-M task), and the hybridization list with the different steps to perform.

        :return: None
        """
        try:
            with open(self.injections_path, 'r') as stream:
                documents = yaml.safe_load(stream)  # yaml.full_load when yaml package updated
                buffer_dict = documents['buffer']  # example {3: 'Buffer3', 7: 'Probe', 8: 'Buffer8'}
                probe_dict = documents['probes']  # example {1: 'DAPI'}, probe_dict can be empty or should contain at maximum one entry for the fluidics task (only 1 positioning step of the needle is performed)
                self.hybridization_list = documents['hybridization list']

            # invert the buffer dict to address the valve by the product name as key
            self.buffer_dict = dict([(value, key) for key, value in buffer_dict.items()])
            self.probe_list = sorted(probe_dict.items())

        except Exception as e:
            self.log.warning(f'Could not load hybridization sequence for task {self.name}: {e}')
