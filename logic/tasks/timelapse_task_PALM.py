# -*- coding: utf-8 -*-
"""
Created on Tue June 1 2021

@author: fbarho

This file is an extension to Qudi software
obtained from <https://github.com/Ulm-IQO/qudi/>

Timelapse task for the PALM setup

Config example pour copy-paste:
    TimelapseTask:
        module: 'timelapse_task_PALM'
        needsmodules:
            camera: 'camera_logic'
            daq: 'lasercontrol_logic'
            filter: 'filterwheel_logic'
            focus: 'focus_logic'
            roi: 'roi_logic'
        config:
            path_to_user_config: 'C:/Users/admin/qudi_files/qudi_task_config_files/timelapse_task_PALM.yaml'

"""
import numpy as np
import yaml
from datetime import datetime
import os
import time
from tqdm import tqdm
from logic.generic_task import InterruptableTask


class Task(InterruptableTask):  # do not change the name of the class. it is always called Task !
    """ This task does an acquisition of a series of images from different channels or using different intensities
    """

    # ==================================================================================================================
    # Generic Task methods
    # ==================================================================================================================

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        print('Task {0} added!'.format(self.name))
        self.user_config_path = self.config['path_to_user_config']
        self.err_count = None
        self.autofocus_ok = False
        self.user_param_dict = {}

    def startTask(self):
        """ """
        self.log.info('started Task')
        self.err_count = 0  # initialize the error counter (counts number of missed triggers for debug)

        # stop all interfering modes on GUIs and disable GUI actions
        self.ref['roi'].disable_tracking_mode()
        self.ref['roi'].disable_roi_actions()

        self.ref['camera'].stop_live_mode()
        self.ref['camera'].disable_camera_actions()

        self.ref['daq'].stop_laser_output()
        self.ref['daq'].disable_laser_actions()

        self.ref['filter'].disable_filter_actions()

        self.ref['focus'].stop_autofocus()
        self.ref['focus'].disable_focus_actions()

        # control that autofocus has been calibrated and a setpoint is defined
        self.autofocus_ok = self.ref['focus']._calibrated and self.ref['focus']._setpoint_defined

        if not self.autofocus_ok:
            self.log.warning('Task aborted. Please initialize the autofocus before starting this task.')
            return

        # open camera shutter ??

        # set stage velocity
        self.ref['roi'].set_stage_velocity({'x': 1, 'y': 1})

        # read all user parameters from config
        self.load_user_parameters()

        # initialize the digital output channel for trigger
        self.ref['daq'].set_up_do_channel()

        # initialize the analog input channel that reads the fire
        self.ref['daq'].set_up_ai_channel()

        # create a directory in which all the data will be saved
        self.directory = self.create_directory(self.save_path)

        # initialize a counter to iterate over the number of cycles to do
        self.counter = 0

    def runTaskStep(self):
        """ Implement one work step of your task here.
        @return bool: True if the task should continue running, False if it should finish.
        """
        #
        start_time = time.time()

        # create a save path for the current iteration
        cur_save_path = self.get_complete_path(self.directory, self.counter+1)  # replace roi by relevant quantity for timelapse
        print(cur_save_path)

        # prepare the camera
        num_z_planes_total = sum(self.imaging_sequence[i]['num_z_planes'] for i in range(len(self.imaging_sequence)))  # get the total number of planes
        frames = len(self.roi_names) * num_z_planes_total
        self.ref['camera'].prepare_camera_for_multichannel_imaging(frames, self.exposure, self.gain,
                                                                   cur_save_path.rsplit('.', 1)[0],
                                                                   self.file_format)

        # set the active_roi to none to avoid having two active rois displayed
        self.ref['roi'].active_roi = None

        for item in self.roi_names:

            # go to roi
            self.ref['roi'].set_active_roi(name=item)
            self.ref['roi'].go_to_roi_xy()
            self.log.info(f'Moved to {item} xy position')
            # time.sleep(1)  # replace maybe by wait for idle
            self.ref['roi'].stage_wait_for_idle()

            for i in range(len(self.imaging_sequence)):  # loop over all laser lines specified in the user config

                # set the filter to the specified position
                filter_pos = self.imaging_sequence[i]['filter_pos']
                self.ref['filter'].set_position(filter_pos)

                # wait until filter position set
                pos = self.ref['filter'].get_position()
                while not pos == filter_pos:
                    time.sleep(1)
                    pos = self.ref['filter'].get_position()

                # autofocus
                # eventually using a setpoint defined per laser line
                num_z_planes = self.imaging_sequence[i]['num_z_planes']
                z_step = self.imaging_sequence[i]['z_step']

                self.ref['focus'].start_search_focus()
                # need to ensure that focus is stable here:
                ready = self.ref['focus']._stage_is_positioned  # maybe use (not self.ref['focus'].autofocus_enabled) instead
                counter = 0
                while not ready:
                    counter += 1
                    time.sleep(0.1)
                    ready = self.ref['focus']._stage_is_positioned
                    if counter > 50:
                        break

                initial_position = self.ref['focus'].get_position()
                print(f'initial position: {initial_position}')
                start_position = self.calculate_start_position(self.centered_focal_plane, num_z_planes, z_step)
                print(f'start position: {start_position}')

                # prepare the light source output
                laserline = self.imaging_sequence[i]['laserline']
                intensity = self.imaging_sequence[i]['intensity']
                # reset the intensity dict to zero
                self.ref['daq'].reset_intensity_dict()
                # prepare the output value for the specified channel
                self.ref['daq'].update_intensity_dict(laserline, intensity)
                # waiting time for stability of the synchronization
                # time.sleep(0.05)  # might not be needed here - to test

                for plane in tqdm(range(num_z_planes)):

                    # print(f'plane number {plane + 1}')

                    # position the piezo
                    position = np.round(start_position + plane * z_step, decimals=3)
                    self.ref['focus'].go_to_position(position)
                    # print(f'target position: {position} um')
                    time.sleep(0.03)
                    cur_pos = self.ref['focus'].get_position()
                    # print(f'current position: {cur_pos} um')

                    # use a while loop to catch the exception when a trigger is missed and repeat the missed image
                    j = 0
                    while j < 1:  # take one image of the plane
                        # switch the laser on and send the trigger to the camera
                        self.ref['daq'].apply_voltage()
                        err = self.ref['daq'].send_trigger_and_control_ai()

                        # read fire signal of camera and switch off when the signal is low
                        ai_read = self.ref['daq'].read_ai_channel()

                        count = 0
                        while not ai_read <= 2.5:  # analog input varies between 0 and 5 V. use max/2 to check if signal is low
                            time.sleep(0.001)  # read every ms
                            ai_read = self.ref['daq'].read_ai_channel()
                            count += 1  # can be used for control and debug
                        self.ref['daq'].voltage_off()
                        # self.log.debug(f'iterations of read analog in - while loop: {count}')

                        # waiting time for stability
                        time.sleep(0.05)

                        # repeat the last step if the trigger was missed
                        if err < 0:
                            self.err_count += 1  # control value to check how often a trigger was missed
                            j = 0  # then the last iteration will be repeated
                        else:
                            j = 1  # increment to continue with the next plane

                # go back to the initial plane position
                self.ref['focus'].go_to_position(initial_position)
                print(f'initial_position: {initial_position}')
                time.sleep(0.5)
                position = self.ref['focus'].get_position()
                print(f'piezo position reset to {position}')

        # --------------------------------------------------------------------------------------------------------------
        # metadata saving
        # --------------------------------------------------------------------------------------------------------------
        self.ref['camera'].abort_acquisition()  # after this, temperature can be retrieved for metadata
        if self.file_format == 'fits':
            metadata = self.get_fits_metadata()
            self.ref['camera']._add_fits_header(cur_save_path, metadata)
        else:  # save metadata in a txt file
            metadata = self.get_metadata()
            file_path = cur_save_path.replace('tif', 'txt', 1)
            self.save_metadata_file(metadata, file_path)

        # go back to first ROI
        self.ref['roi'].set_active_roi(name=self.roi_names[0])
        self.ref['roi'].go_to_roi_xy()
        self.ref['roi'].stage_wait_for_idle()

        self.counter += 1

        # waiting time before going to next step
        finish_time = time.time()
        duration = finish_time - start_time
        wait = self.time_step - duration
        print(f'Finished step in {duration} s. Waiting {wait} s.')
        if wait > 0:
            time.sleep(wait)

        return self.counter < self.num_iterations

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
        self.ref['camera'].reset_camera_after_multichannel_imaging()

        self.ref['daq'].voltage_off()  # as security
        self.ref['daq'].reset_intensity_dict()
        self.ref['daq'].close_do_task()
        self.ref['daq'].close_ai_task()

        # reset stage velocity to default
        self.ref['roi'].set_stage_velocity({'x': 6, 'y': 6})  # 5.74592

        # enable gui actions
        # roi gui
        self.ref['roi'].enable_tracking_mode()
        self.ref['roi'].enable_roi_actions()
        # basic imaging gui
        self.ref['camera'].enable_camera_actions()
        self.ref['daq'].enable_laser_actions()
        self.ref['filter'].enable_filter_actions()
        # focus tools gui
        self.ref['focus'].enable_focus_actions()

        self.log.debug(f'number of missed triggers: {self.err_count}')
        self.log.info('cleanupTask finished')

    # ==================================================================================================================
    # Helper functions
    # ==================================================================================================================

    # ------------------------------------------------------------------------------------------------------------------
    # user parameters
    # ------------------------------------------------------------------------------------------------------------------

    def load_user_parameters(self):
        """ this function is called from startTask() to load the parameters given in a specified format by the user

        specify only the path to the user defined config in the (global) config of the experimental setup

        user must specify the following dictionary (here with example entries):
            sample_name: 'Mysample'
            exposure: 0.05  # in s
            gain: 0
            centered_focal_plane: False
            save_path: 'E:\'
            file_format: 'tif'
            imaging_sequence = [('488 nm', 3, ), ('561 nm', 3), ('641 nm', 10)]
            roi_list_path:
        """
        try:
            with open(self.user_config_path, 'r') as stream:
                self.user_param_dict = yaml.safe_load(stream)

                self.sample_name = self.user_param_dict['sample_name']
                self.exposure = self.user_param_dict['exposure']  # or should this be defined for each laser line ?
                self.gain = self.user_param_dict['gain']
                self.centered_focal_plane = self.user_param_dict['centered_focal_plane']
                self.save_path = self.user_param_dict['save_path']
                self.imaging_sequence = [{'laserline': '561 nm', 'intensity': 5, 'num_z_planes': 10, 'z_step': 0.25, 'filter_pos': 2},
                                         {'laserline': '641 nm', 'intensity': 5, 'num_z_planes': 5, 'z_step': 0.25, 'filter_pos': 1}]
                self.file_format = self.user_param_dict['file_format']
                self.roi_list_path = self.user_param_dict['roi_list_path']
                self.num_iterations = self.user_param_dict['num_iterations']
                self.time_step = self.user_param_dict['time_step']

        except Exception as e:  # add the type of exception
            self.log.warning(f'Could not load user parameters for task {self.name}: {e}')
            return

        # establish further user parameters derived from the given ones:
        # create a list of roi names
        self.ref['roi'].load_roi_list(self.roi_list_path)
        # get the list of the roi names
        self.roi_names = self.ref['roi'].roi_names

        # translate the laser lines indicated in user config to required format
        lightsource_dict = {'405 nm': 'laser1', '488 nm': 'laser2', '561 nm': 'laser3', '641 nm': 'laser4'}
        for i in range(len(self.imaging_sequence)):
            self.imaging_sequence[i]['laserline'] = lightsource_dict[self.imaging_sequence[i]['laserline']]

    def calculate_start_position(self, centered_focal_plane, num_z_planes, z_step):
        """
        @param bool centered_focal_plane: indicates if the scan is done below and above the focal plane (True) or if the focal plane is the bottommost plane in the scan (False)
        """
        current_pos = self.ref['focus'].get_position()

        if centered_focal_plane:  # the scan should start below the current position so that the focal plane will be the central plane or one of the central planes in case of an even number of planes
            # even number of planes:
            if num_z_planes % 2 == 0:
                start_pos = current_pos - num_z_planes / 2 * z_step  # focal plane is the first one of the upper half of the number of planes
            # odd number of planes:
            else:
                start_pos = current_pos - (num_z_planes - 1) / 2 * z_step
            return start_pos
        else:
            return current_pos  # the scan starts at the current position and moves up

    # ------------------------------------------------------------------------------------------------------------------
    # file path handling
    # ------------------------------------------------------------------------------------------------------------------

    def create_directory(self, path_stem):
        """ Create the directory (based on path_stem given as user parameter),
        in which the folders for the ROIs will be created
        Example: path_stem/YYYY_MM_DD/001_Timelapse_samplename
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

        foldername = f'{prefix}_Timelapse_{self.sample_name}'

        path = os.path.join(path_stem_with_date, foldername)

        # create the path  # no need to check if it already exists due to incremental prefix
        try:
            os.makedirs(path)  # recursive creation of all directories on the path
        except Exception as e:
            self.log.error('Error {0}'.format(e))

        return path

    def get_complete_path(self, directory, counter):

        path = os.path.join(directory, str(counter).zfill(2))

        if not os.path.exists(path):
            try:
                os.makedirs(path)  # recursive creation of all directories on the path
            except Exception as e:
                self.log.error('Error {0}'.format(e))

        file_name = f'timelapse_{self.prefix}_step_{str(counter).zfill(2)}.{self.file_format}'

        complete_path = os.path.join(path, file_name)
        return complete_path

    # ------------------------------------------------------------------------------------------------------------------
    # metadata
    # ------------------------------------------------------------------------------------------------------------------

    def get_metadata(self):
        """ Get a dictionary containing the metadata in a plain text compatible format. """
        metadata = {}
        # metadata['Time'] = datetime.now().strftime(
        #     '%m-%d-%Y, %H:%M:%S')  # or take the starting time of the acquisition instead ??? # then add a variable to startTask
        metadata['Sample name'] = self.sample_name
        metadata['Exposure time (s)'] = self.exposure
        metadata['Kinetic time (s)'] = self.ref['camera'].get_kinetic_time()
        metadata['Gain'] = self.gain
        metadata['Sensor temperature (deg C)'] = self.ref['camera'].get_temperature()
        # filterpos = self.ref['filter'].get_position()
        # filterdict = self.ref['filter'].get_filter_dict()
        # label = 'filter{}'.format(filterpos)
        # metadata['Filter'] = filterdict[label]['name']
        # metadata['Number laserlines'] = self.num_laserlines
        # imaging_sequence = self.imaging_sequence_raw
        # for i in range(self.num_laserlines):
        #     metadata[f'Laser line {i + 1}'] = imaging_sequence[i][0]
        #     metadata[f'Laser intensity {i + 1} (%)'] = imaging_sequence[i][1]
        # metadata['Scan step length (um)'] = self.z_step
        # metadata['Scan total length (um)'] = self.z_step * self.num_z_planes
        # metadata['x position'] = self.ref['roi'].stage_position[0]
        # metadata['y position'] = self.ref['roi'].stage_position[1]
        # pixel size ???
        return metadata

    def get_fits_metadata(self):
        """ Get a dictionary containing the metadata in a fits header compatible format. """
        metadata = {}
        # metadata['TIME'] = datetime.now().strftime('%m-%d-%Y, %H:%M:%S')
        metadata['SAMPLE'] = (self.sample_name, 'sample name')
        metadata['EXPOSURE'] = (self.exposure, 'exposure time (s)')
        metadata['KINETIC'] = (self.ref['camera'].get_kinetic_time(), 'kinetic time (s)')
        metadata['GAIN'] = (self.gain, 'gain')
        metadata['TEMP'] = (self.ref['camera'].get_temperature(), 'sensor temperature (deg C)')
        # filterpos = self.ref['filter'].get_position()
        # filterdict = self.ref['filter'].get_filter_dict()
        # label = 'filter{}'.format(filterpos)
        # metadata['FILTER'] = (filterdict[label]['name'], 'filter')
        # metadata['CHANNELS'] = (self.num_laserlines, 'number laserlines')
        # for i in range(self.num_laserlines):
        #     metadata[f'LINE{i + 1}'] = (self.imaging_sequence_raw[i][0], f'laser line {i + 1}')
        #     metadata[f'INTENS{i + 1}'] = (self.imaging_sequence_raw[i][1], f'laser intensity {i + 1}')
        # metadata['Z_STEP'] = (self.z_step, 'scan step length (um)')
        # metadata['Z_TOTAL'] = (self.z_step * self.num_z_planes, 'scan total length (um)')
        # metadata['X_POS'] = (self.ref['roi'].stage_position[0], 'x position')
        # metadata['Y_POS'] = (self.ref['roi'].stage_position[1], 'y position')
        # # pixel size
        return metadata

    def save_metadata_file(self, metadata, path):
        """" Save a txt file containing the metadata dictionary

        :param dict metadata: dictionary containing the metadata
        :param str path: pathname
        """
        with open(path, 'w') as outfile:
            yaml.safe_dump(metadata, outfile, default_flow_style=False)
        self.log.info('Saved metadata to {}'.format(path))
