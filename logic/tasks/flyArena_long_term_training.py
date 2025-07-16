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
from time import sleep
import logging


class Task(InterruptableTask):
    """ Dummy task, does nothing. """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        print('Task {0} added!'.format(self.name))
        self.ctr = 0

    def startTask(self):
        """ Dummy start """

        # initialization of the training - make sure that odor circuit is closed, shutter off and display off
        self.ref['odor'].disable_odor_circuit_actions()
        self.ref['opto'].disable_optogenetic_actions()

        self.ref['odor'].stop_flow_measurement()
        self.ref['odor'].stop_air_flow()
        self.ref['odor'].close_odor_circuit()
        self.ref['opto'].open_shutter()
        self.ref['opto'].display_off()

    def runTaskStep(self):
        """ Dummy step """
        for n in range(10):
            print(n)
            sleep(1)

    def pauseTask(self):
        """ Dummy pause """
        sleep(1)
        print('paused task')

    def resumeTask(self):
        """ Dummy resume """
        sleep(1)
        print('resumed task')

    def cleanupTask(self):
        """ Dummy cleanup """
        self.ref['odor'].enable_odor_circuit_actions()
        self.ref['opto'].enable_optogenetic_actions()

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

