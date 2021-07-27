# -*- coding: utf-8 -*-
"""
Created on Friday March 26 2021

@author: fbarho

This file is an extension to Qudi software
obtained from <https://github.com/Ulm-IQO/qudi/>

Multicolor z-scan task simulation

Config example pour copy-paste:
    MulticolorScanTask:
        module: 'multicolor_scan_task_dummy'
        needsmodules:
            laser: 'lasercontrol_logic'
            cam: 'camera_logic'
            piezo: 'focus_logic'
"""

import numpy as np
from time import sleep, time
from logic.generic_task import InterruptableTask


class Task(InterruptableTask):  # do not change the name of the class. it is always called Task !
    """ This task does an acquisition of a series of planes in z direction using a sequence of lightsources for each plane
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        print('Task {0} added!'.format(self.name))

    def startTask(self):
        """ """
        self.log.info('started Task')

        # read all user parameters from config
        self.load_user_parameters()

        # prepare the camera
        self.num_frames = self.num_z_planes * len(self.wavelengths)
        print('Set camera exposure time')
        sleep(self.waiting_time)
        print('Set camera trigger mode: EXTERNAL')
        sleep(self.waiting_time)
        print('Set camera acquisition mode')
        sleep(self.waiting_time)
        print(f'Set number of frames to acquire: {self.num_frames}')
        sleep(self.waiting_time)
        print('Acquisition started')

        # initialize the counter (corresponding to the number of planes already acquired)
        self.step_counter = 0

    def runTaskStep(self):
        """ Implement one work step of your task here.
        @return bool: True if the task should continue running, False if it should finish.
        """
        self.step_counter += 1
        print(f'plane number {self.step_counter}')

        # position the piezo
        sleep(self.waiting_time)
        position = self.start_position + (self.step_counter - 1) * self.z_step
        print(f'Set piezo position: {position} um')

        # take a sequence of images from this plane
        for i in range(len(self.imaging_sequence)):
            print(f'Activated laser {self.imaging_sequence[i][0]}, intensity {self.imaging_sequence[i][1]}')
            sleep(0.1)

        print(f'Acquired {len(self.wavelengths)} images')
        sleep(self.waiting_time)

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

        # get acquired data from the camera and save it to file
        image_data = np.random.normal(size=(self.num_frames, 512, 512))
        print(f'acquired data structure of shape {image_data.shape}')
        sleep(self.waiting_time)

        if self.file_format == 'fits':
            metadata = {}  # to be added
            self.ref['cam']._save_to_fits(self.save_path, image_data, metadata)
        else:   # use tiff as default format
            self.ref['cam']._save_to_tiff(self.num_frames, self.save_path, image_data)
            # add metadata saving
        print('Saved image data')
        sleep(self.waiting_time)

        print('Set camera default settings')
        sleep(self.waiting_time)

    def load_user_parameters(self):
        self.exposure = 0.1
        self.num_z_planes = 10
        self.z_step = 0.25  # in um
        self.centered_focal_plane = True
        self.start_position = self.calculate_start_position(self.centered_focal_plane)
        self.save_path = '/home/barho/teststack.tif'  # to be defined how the default folder structure should be set up
        self.file_format = 'tif'
        self.waiting_time = 0.5

        lightsource_dict = {'BF': 0, '405 nm': 1, '488 nm': 2, '561 nm': 3, '640 nm': 4}
        self.imaging_sequence = [('488 nm', 5), ('561 nm', 5), ('640 nm', 10)]
        wavelengths = [self.imaging_sequence[i][0] for i, item in enumerate(self.imaging_sequence)]
        self.wavelengths = [lightsource_dict[key] for key in wavelengths]
        self.intensities = [self.imaging_sequence[i][1] for i, item in enumerate(self.imaging_sequence)]

    def calculate_start_position(self, centered_focal_plane):
        """
        @param bool centered_focal_plane: indicates if the scan is done below and above the focal plane (True) or if the focal plane is the bottommost plane in the scan (False)
        """
        current_pos = 10 # self.ref['piezo'].get_position()  # lets assume that we are at focus (user has set focus or run autofocus)

        if centered_focal_plane:  # the scan should start below the current position so that the focal plane will be the central plane or one of the central planes in case of an even number of planes
            # even number of planes:
            if self.num_z_planes % 2 == 0:
                start_pos = current_pos - self.num_z_planes / 2 * self.z_step  # focal plane is the first one of the upper half of the number of planes
            # odd number of planes:
            else:
                start_pos = current_pos - (self.num_z_planes - 1)/2 * self.z_step
            return start_pos
        else:
            return current_pos  # the scan starts at the current position and moves up
