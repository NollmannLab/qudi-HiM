# -*- coding: utf-8 -*-
"""
Task to perform stack imaging


Config example pour copy-paste:
    StackImagingTask:
        module: 'stack_imaging_task'
        needsmodules:
            roi: 'roi_logic'
            daq: 'daq_ao_logic'
            camera: 'camera_logic'
            filter: 'filterwheel_logic'
            focus: 'focus_logic'
        config:
            path_to_user_config: '/home/barho/qudi-cbs-user-configs/stack_imaging_task.json'
"""

from logic.generic_task import InterruptableTask
import time
import json
from datetime import datetime
import os


class Task(InterruptableTask):  # do not change the name of the class. it is always called Task !
    """ This task does an acquisition of a series of images at the current stage position varying the z position
    (moving into and out of focus)

    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        print('Task {0} added!'.format(self.name))
        self.laser_allowed = False
        self.user_config_path = self.config['path_to_user_config']
        self.log.info('Task {0} using the configuration at {1}'.format(self.name, self.user_config_path))

    def startTask(self):
        """ """
        self._load_user_parameters()

        # control the config : laser allowed for given filter ?
        self.laser_allowed = self._control_user_parameters()

        if not self.laser_allowed:
            self.log.warning('Task aborted. Please specify a valid filter / laser combination')
            return

        else:
            # set the filter to the specified position
            self.ref['filter'].set_position(self.filter_pos)

            # indicate the intensity values to be applied
            self.ref['daq'].update_intensity_dict(self.lightsource, self.intensity)

            # initialize the counter that will be used to iterate over the number of z planes
            self.counter = 0

            # calculate the start position given the current position set by the user
            self.start_position = self._calculate_start_position()

            # move to start position on the z axis
            self.ref['focus'].go_to_position(self.start_position)  # start position should be one step below the first plane to image


    def runTaskStep(self):
        """ Implement one work step of your task here.
        @return bool: True if the task should continue running, False if it should finish.
        """
        # move to the next plane
        self.ref['focus'].move_up(self.step)
        position = self.ref['focus'].get_position()
        self.log.info(f'Plane {self.counter + 1}: position {position}.')

        # switch the laser on
        self.ref['daq'].apply_voltage()

        if self.n_frames == 1:  # single image acquisition
            # take an image and save it -> it is needed to first call start_single_acquisition otherwise no data is available
            self.ref['camera'].start_single_acquistion()  # mind the typo !!
            self.ref['camera'].save_last_image(self.save_path, 'tif')
            # create the path for metadata file
            complete_path = self.ref['camera']._create_generic_filename(self.save_path, '_Image', 'parameters', 'txt',
                                                                        addfile=True)

        else:  # n_frames > 1: movie acquisition
            self.ref['camera'].save_video(self.save_path, 'tiff', self.n_frames, self.display, emit_signal=False)
            # create the path for metadata file
            complete_path = self.ref['camera']._create_generic_filename(self.save_path, '_Movie', 'parameters', 'txt',
                                                                        addfile=True)

        # switch laser off
        self.ref['daq'].voltage_off()
        # in a following version the laser on off switching should be triggered by the camera. but this actually goes into the daq_ao_logic module ..

        # # save the metadata
        metadata = self._create_metadata_dict()
        with open(complete_path, 'w') as file:
            file.write(str(metadata))
        self.log.info('Saved metadata to {}'.format(complete_path))

        self.counter += 1
        return self.counter < self.num_planes  # continue when there are still planes to be imaged

    def pauseTask(self):
        """ """
        self.log.info('pauseTask called')

    def resumeTask(self):
        """ """
        self.log.info('resumeTask called')

    def cleanupTask(self):
        """ """
        self.ref['focus'].go_to_position(self.start_position)  # for safety before making another movement move piezo back to lowest plane
        self.log.info(f'moved to position: {self.start_position}')
        self.ref['daq'].voltage_off()  # as security
        self.ref['daq'].reset_intensity_dict()
        self.log.info('cleanupTask called')

    def _load_user_parameters(self):
        """ this function is called from startTask() to load the parameters given in a specified format by the user

        specify only the path to the user defined config in the (global) config of the experimental setup

        user must specify the following dictionary (here with example entries):
            save_path: '/home/barho/myfolder'
            num_planes: 15
            step: 5  # in um
            lightsource: 'laser1'
            intensity: 10
            filter_pos: 2
            n_frames: 5
            activate_display: 1
        """
        try:
            with open(self.user_config_path, 'r') as file:
                self.user_param_dict = json.load(file)

            self.save_path = self.user_param_dict['save_path']
            self.num_planes = self.user_param_dict['num_planes']
            self.step = self.user_param_dict['step']
            self.lightsource = self.user_param_dict['lightsource']
            self.intensity = self.user_param_dict['intensity']
            self.filter_pos = self.user_param_dict['filter_pos']
            self.n_frames = self.user_param_dict['n_frames']
            self.display = bool(self.user_param_dict['activate_display'])

            self.log.info('loaded user parameters')
        except:
            self.log.warning('Could not load user parameters for task {}'.format(self.name))

    def _control_user_parameters(self):
        """ this function checks if the specified laser is allowed given the filter setting
        @return bool: valid ?"""
        filterpos = self.filter_pos
        key = 'filter{}'.format(filterpos)
        filterdict = self.ref['filter'].get_filter_dict()
        laserlist = filterdict[key]['lasers']  # returns a list of boolean elements, laser allowed ?
        # this part should be improved using a correct addressing of the element
        laser = self.lightsource
        laser_index = int(laser.strip('laser'))-1
        ##########
        return laserlist[laser_index]


    def _create_metadata_dict(self):
        """ create a dictionary containing the metadata

        this is a copy of the function available in basic_gui. the values are addressed slightly differently via the refs"""
        metadata = {}
        metadata['timestamp'] = datetime.now().strftime('%m-%d-%Y, %H:%M:%S')
        filterpos = self.ref['filter'].get_position()
        filterdict = self.ref['filter'].get_filter_dict()
        label = 'filter{}'.format(filterpos)
        metadata['filter'] = filterdict[label]['name']
        metadata['gain'] = self.ref['camera'].get_gain()
        metadata['exposuretime (s)'] = self.ref['camera'].get_exposure()
        intensity_dict = self.ref['daq']._intensity_dict
        keylist = [key for key in intensity_dict if intensity_dict[key] != 0]
        laser_dict = self.ref['daq'].get_laser_dict()
        metadata['laser'] = [laser_dict[key]['wavelength'] for key in keylist]
        metadata['intensity (%)'] = [intensity_dict[key] for key in keylist]
        if self.ref['camera'].has_temp:
            metadata['sensor temperature'] = self.ref['camera'].get_temperature()
        else:
            metadata['sensor temperature'] = 'Not available'

        return metadata

    def _calculate_start_position(self):
        # we assume that the user has correctly set the focus
        # this will be the reference plane and the stack will be taken around this plane
        # in a later version, autofocus can first be run to determine the focal plane
        current_pos = self.ref['focus'].get_position()
        # note that start position is set to be one 'step' below the first imaging plane because in the runTaskStep loop we first move one step up
        # user specified even number of planes: current position is the last plane in the lower half of planes
        if self.num_planes % 2 == 0:
            start_pos = current_pos - self.num_planes / 2 * self.step
        else:
        # user specified odd number of planes: the current position corresponds to the central plane
            start_pos = current_pos - (self.num_planes + 1)/2 * self.step
        return start_pos





