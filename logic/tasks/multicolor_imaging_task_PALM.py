# -*- coding: utf-8 -*-
"""
Qudi-CBS

An extension to Qudi.

This module contains a task to perform multicolor imaging on PALM setup.
(Take at a given position a sequence of images with different laserlines or intensities).

@author: F. Barho

Created on Tue Feb 2 2021
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
from datetime import datetime
import os
from time import sleep
from logic.generic_task import InterruptableTask
from logic.task_helper_functions import get_entry_nested_dict


class Task(InterruptableTask):  # do not change the name of the class. it is always called Task !
    """ This task does an acquisition of a series of images from different channels or using different intensities.

    Config example pour copy-paste:

    MulticolorImagingTask:
        module: 'multicolor_imaging_task_PALM'
        needsmodules:
            camera: 'camera_logic'
            daq: 'lasercontrol_logic'
            filter: 'filterwheel_logic'
        config:
            path_to_user_config: 'C:/Users/admin/qudi_files/qudi_task_config_files/multicolor_imaging_task_PALM.yml'
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

    def startTask(self):
        """ """
        self.log.info('started Task')
        self.err_count = 0  # initialize the error counter (counts number of missed triggers for debug)

        # stop all interfering modes on GUIs and disable GUI actions
        self.ref['camera'].stop_live_mode()
        self.ref['camera'].disable_camera_actions()

        self.ref['daq'].stop_laser_output()
        self.ref['daq'].disable_laser_actions()

        self.ref['filter'].disable_filter_actions()

        # read all user parameters from config
        self.load_user_parameters()

        # control the config : laser allowed for given filter ?
        self.laser_allowed = self.control_user_parameters()
        
        if not self.laser_allowed:
            self.log.warning('Task aborted. Please specify a valid filter / laser combination')
            return

        # preparation steps
        # set the filter to the specified position (changing filter not allowed during task because this is too slow)
        self.ref['filter'].set_position(self.filter_pos)
        # wait until filter position set
        pos = self.ref['filter'].get_position()
        while not pos == self.filter_pos:
            sleep(1)
            pos = self.ref['filter'].get_position()

        # prepare the camera
        frames = len(self.imaging_sequence) * self.num_frames 
        self.ref['camera'].prepare_camera_for_multichannel_imaging(frames, self.exposure, self.gain, self.complete_path.rsplit('.', 1)[0], self.file_format)

    def runTaskStep(self):
        """ Implement one work step of your task here.
        :return bool: True if the task should continue running, False if it should finish.
        """
        if not self.laser_allowed:
            return False  # skip runTaskStep and directly go to cleanupTask

        # --------------------------------------------------------------------------------------------------------------
        # imaging sequence (image data is spooled to disk)
        # --------------------------------------------------------------------------------------------------------------
        # this task has only one step until a data set is prepared and saved
        # but loops over the number of frames per channel and the channels

        # outer loop over the number of frames per color
        for j in range(self.num_frames):

            # use a while loop to catch the exception when a trigger is missed and just repeat the missed image
            # (in case one trigger was missed)
            i = 0
            while i < len(self.imaging_sequence):
                # reset the intensity dict to zero
                self.ref['daq'].reset_intensity_dict()
                # prepare the output value for the specified channel
                self.ref['daq'].update_intensity_dict(self.imaging_sequence[i][0], self.imaging_sequence[i][1])
                # waiting time for stability of the code
                sleep(0.05)
            
                # switch the laser on and send the trigger to the camera
                self.ref['daq'].apply_voltage()
                err = self.ref['daq'].send_trigger_and_control_ai()  
            
                # read fire signal of camera and switch off when the signal is low
                ai_read = self.ref['daq'].read_trigger_ai_channel()
                count = 0
                while not ai_read <= 2.5:  # analog input varies between 0 and 5 V. use max/2 to check if signal is low
                    sleep(0.001)  # read every ms
                    ai_read = self.ref['daq'].read_trigger_ai_channel()
                    count += 1  # can be used for control and debug
                self.ref['daq'].voltage_off()
                # self.log.debug(f'iterations of read analog in - while loop: {count}')
            
                # waiting time for stability
                sleep(0.05)

                # repeat the last step if the trigger was missed
                if err < 0:
                    self.err_count += 1  # control value to check how often a trigger was missed
                    i = i  # then the last iteration will be repeated
                else:
                    i += 1  # increment to continue with the next image

        # --------------------------------------------------------------------------------------------------------------
        # metadata saving
        # --------------------------------------------------------------------------------------------------------------
        self.ref['camera'].abort_acquisition()  # after this, temperature can be retrieved for metadata
        if self.file_format == 'fits':
            metadata = self.get_fits_metadata()
            self.ref['camera'].add_fits_header(self.complete_path, metadata)
        else:  # save metadata in a txt file
            metadata = self.get_metadata()
            file_path = self.complete_path.replace('tif', 'txt', 1)
            self.save_metadata_file(metadata, file_path)

        return False

    def pauseTask(self):
        """ """
        self.log.info('pauseTask called')

    def resumeTask(self):
        """ """
        self.log.info('resumeTask called')

    def cleanupTask(self):
        """ """
        self.log.info('cleanupTask called')

        self.ref['camera'].reset_camera_after_multichannel_imaging()

        self.ref['daq'].voltage_off()  # as security
        self.ref['daq'].reset_intensity_dict()

        # enable gui actions
        self.ref['camera'].enable_camera_actions()
        self.ref['daq'].enable_laser_actions()
        self.ref['filter'].enable_filter_actions()

        self.log.debug(f'number of missed triggers: {self.err_count}')
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

        The config file contains the following dictionary (here with example entries):
            sample_name: 'MySample'
            filter_pos: 1
            exposure: 0.05  # in s
            gain: 0
            num_frames: 1  # number of frames per color
            save_path: 'E:\\'
            file_format: 'tif'
            imaging_sequence = [('488 nm', 3), ('561 nm', 3), ('641 nm', 10)]
        """
        try:
            with open(self.user_config_path, 'r') as stream:
                self.user_param_dict = yaml.safe_load(stream)

                self.sample_name = self.user_param_dict['sample_name']
                self.filter_pos = self.user_param_dict['filter_pos']
                self.exposure = self.user_param_dict['exposure']
                self.gain = self.user_param_dict['gain']
                self.num_frames = self.user_param_dict['num_frames']
                self.save_path = self.user_param_dict['save_path']
                self.imaging_sequence_raw = self.user_param_dict['imaging_sequence']
                self.file_format = self.user_param_dict['file_format']
                # self.log.debug(self.imaging_sequence_raw)

        except Exception as e:  # add the type of exception
            self.log.warning(f'Could not load user parameters for task {self.name}: {e}')
            return

        # establish further user parameters derived from the given ones:
        # for the imaging sequence, we need to access the corresponding labels
        laser_dict = self.ref['daq'].get_laser_dict()
        imaging_sequence = [(*get_entry_nested_dict(laser_dict, self.imaging_sequence_raw[i][0], 'label'),
                             self.imaging_sequence_raw[i][1]) for i in range(len(self.imaging_sequence_raw))]
        self.log.info(imaging_sequence)
        self.imaging_sequence = imaging_sequence
        # new format: self.imaging_sequence = [('laser2', 10), ('laser2', 20), ('laser3', 10)]

        self.complete_path = self.get_complete_path(self.save_path)

        self.num_laserlines = len(self.imaging_sequence)

    def control_user_parameters(self):
        """ This method checks if the laser lines that will be used are compatible with the chosen filter.
        :return bool: lasers_allowed
        """
        # use the filter position to create the key # simpler than using get_entry_nested_dict method
        key = 'filter{}'.format(self.filter_pos)
        bool_laserlist = self.ref['filter'].get_filter_dict()[key]['lasers']  # list of booleans, laser allowed ? such as [True True False True], corresponding to [laser1, laser2, laser3, laser4]
        forbidden_lasers = []
        for i, item in enumerate(bool_laserlist):
            if not item:  # if the element in the list is False:
                label = 'laser'+str(i+1)
                forbidden_lasers.append(label)      
        lasers_allowed = True  # as initialization
        for item in forbidden_lasers:
            if item in [self.imaging_sequence[i][0] for i in range(len(self.imaging_sequence))]:
                lasers_allowed = False
                break  # stop if at least one forbidden laser is found
        return lasers_allowed

    # ------------------------------------------------------------------------------------------------------------------
    # file path handling
    # ------------------------------------------------------------------------------------------------------------------

    def get_complete_path(self, path_stem):
        """ Create the complete path based on path_stem given as user parameter,
        such as path_stem/YYYY_MM_DD/001_MulticolorImaging_samplename/movie_001.tif
        or path_stem/YYYY_MM_DD/027_MulticolorImaging_samplename/movie_027.fits

        :param: str path_stem such as E:/
        :return: str complete path (see examples above)
        """
        cur_date = datetime.today().strftime('%Y_%m_%d')

        path_stem_with_date = os.path.join(path_stem, cur_date)

        # check if folder path_stem/cur_date exists, if not: create it
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
        foldername = f'{prefix}_MulticolorImaging_{self.sample_name}'

        path = os.path.join(path_stem_with_date, foldername)

        # create the path  # no need to check if it already exists due to incremental prefix
        try:
            os.makedirs(path)  # recursive creation of all directories on the path
        except Exception as e:
            self.log.error('Error {0}'.format(e))

        file_name = f'movie_{prefix}.{self.file_format}'
        complete_path = os.path.join(path, file_name)
        return complete_path

    # ------------------------------------------------------------------------------------------------------------------
    # metadata
    # ------------------------------------------------------------------------------------------------------------------

    def get_metadata(self):
        """ Get a dictionary containing the metadata in a plain text easy readable format.

        :return: dict metadata
        """
        metadata = {}
        metadata['Time'] = datetime.now().strftime('%m-%d-%Y, %H:%M:%S')  # or take the starting time of the acquisition instead ??? # then add a variable to startTask
        metadata['Sample name'] = self.sample_name
        metadata['Exposure time (s)'] = self.exposure
        metadata['Kinetic time (s)'] = self.ref['camera'].get_kinetic_time()
        metadata['Gain'] = self.gain
        metadata['Sensor temperature (deg C)'] = self.ref['camera'].get_temperature()
        filterpos = self.ref['filter'].get_position()
        filterdict = self.ref['filter'].get_filter_dict()
        label = 'filter{}'.format(filterpos)
        metadata['Filter'] = filterdict[label]['name']
        metadata['Number laserlines'] = self.num_laserlines
        imaging_sequence = self.imaging_sequence_raw
        for i in range(self.num_laserlines):
            metadata[f'Laser line {i+1}'] = imaging_sequence[i][0]
            metadata[f'Laser intensity {i+1} (%)'] = imaging_sequence[i][1]
        # pixel size ???
        return metadata

    def get_fits_metadata(self):
        """ Get a dictionary containing the metadata in a fits header compatible format.

        :return: dict metadata
        """
        metadata = {}
        metadata['TIME'] = datetime.now().strftime('%m-%d-%Y, %H:%M:%S')
        metadata['SAMPLE'] = (self.sample_name, 'sample name')
        metadata['EXPOSURE'] = (self.exposure, 'exposure time (s)')
        metadata['KINETIC'] = (self.ref['camera'].get_kinetic_time(), 'kinetic time (s)')
        metadata['GAIN'] = (self.gain, 'gain')
        metadata['TEMP'] = (self.ref['camera'].get_temperature(), 'sensor temperature (deg C)')
        filterpos = self.ref['filter'].get_position()
        filterdict = self.ref['filter'].get_filter_dict()
        label = 'filter{}'.format(filterpos)
        metadata['FILTER'] = (filterdict[label]['name'], 'filter')
        metadata['CHANNELS'] = (self.num_laserlines, 'number laserlines')
        for i in range(self.num_laserlines):
            metadata[f'LINE{i+1}'] = (self.imaging_sequence_raw[i][0], f'laser line {i+1}')
            metadata[f'INTENS{i+1}'] = (self.imaging_sequence_raw[i][1], f'laser intensity {i+1}')
        # pixel size
        return metadata

    def save_metadata_file(self, metadata, path):
        """" Save a txt file containing the metadata dictionary.

        :param dict metadata: dictionary containing the metadata
        :param str path: pathname
        """
        with open(path, 'w') as outfile:
            yaml.safe_dump(metadata, outfile, default_flow_style=False)
        self.log.info('Saved metadata to {}'.format(path))
