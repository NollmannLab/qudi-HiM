# -*- coding: utf-8 -*-
"""
Dummy task for taskrunner.

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
"""
from logic.generic_task import InterruptableTask
import os
import time
import logging

class Task(InterruptableTask):
    """ Dummy task, does nothing. """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        print('Task {0} added!'.format(self.name))
        self.ctr = 0

    def startTask(self):
        """ Dummy start """
        print('Start')
        self.ctr = 0
        self._result = '{0} lines printed!'.format(self.ctr)
        self.file_handler = logging.FileHandler(filename=os.path.join('/home/jb/Desktop', 'HiM_task.log'))
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        self.file_handler.setFormatter(formatter)

        self.task_logger = logging.getLogger()
        self.task_logger.setLevel(logging.INFO)
        self.task_logger.addHandler(self.file_handler)
        self.task_logger.info('started Task')

    def runTaskStep(self):
        """ Dummy step """

        if not self.aborted:
            time.sleep(0.5)
            self.task_logger.info(f'step :{self.ctr}')
        if not self.aborted:
            time.sleep(0.5)
        if not self.aborted:
            print('still in the task step', self.ctr)
            time.sleep(0.1)
            self.ctr += 1
        self._result = '{0} lines printed!'.format(self.ctr)
        return self.ctr < 5

    def pauseTask(self):
        """ Dummy pause """
        time.sleep(1)
        print('paused task')

    def resumeTask(self):
        """ Dummy resume """
        time.sleep(1)
        print('resumed task')

    def cleanupTask(self):
        """ Dummy cleanup """
        print(self._result)
        self.task_logger.info('task cleaned up')
        self.task_logger.removeHandler(self.file_handler)
        self.task_logger.info('task cleaned up')

    def checkExtraStartPrerequisites(self):
        """ Check extra start prerequisites, there are none """
        print('things needed for task to start')
        return True

    def checkExtraPausePrerequisites(self):
        """ Check extra pause prerequisites, there are none """
        print('things needed for task to pause')
        return True

