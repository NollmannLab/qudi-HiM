# -*- coding: utf-8 -*-
"""
Qudi-CBS

An extension to Qudi.

This module contains a task to perform a multicolor scan on RAMM setup.
(Take at a given position a stack of images using a sequence of different laserlines or intensities in each plane
of the stack.)

@author: JB. Fiche

Created on Wed November 30 2023
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
import os
from datetime import datetime
import numpy as np
import yaml
from time import sleep, time
from logic.generic_task import InterruptableTask
from logic.task_helper_functions import save_z_positions_to_file


class Task(InterruptableTask):  # do not change the name of the class. it is always called Task !
    """ This task acquires a stack of images using a sequence of lightsources for each plane.

    Config example pour copy-paste:

    MulticolorScanTask:
        module: 'multicolor_scan_task_RAMM'
        needsmodules:
            laser: 'lasercontrol_logic'
            bf: 'brightfield_logic'
            cam: 'camera_logic'
            daq: 'nidaq_logic'
            focus: 'focus_logic'
        config:
            path_to_user_config: 'C:/Users/sCMOS-1/qudi_files/qudi_task_config_files/multicolor_scan_task_RAMM.yml'
    """
    # ==================================================================================================================
    # Generic Task methods
    # ==================================================================================================================

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        print('Task {0} added!'.format(self.name))
        self.user_config_path = self.config['path_to_user_config']
        self.step_counter: int = 0
        self.user_param_dict = {}
        self.timeout: float = 0
        self.default_exposure: float = 0
        self.sample_name: str = ""
        self.exposure: float = 0
        self.num_frames_total: int = 0
        self.num_im_per_sequences: int = 400
        self.sequences: int = 0
        self.cycles: int = 0
        self.imaging_sequence: list = []
        self.save_path: str = ""
        self.file_format: str = ""
        self.complete_path: str = ""
        self.num_laserlines: int = 0
        self.wavelengths: list = []
        self.intensities: list = []
        self.lightsource_dict: dict = {'BF': 0, '405 nm': 1, '488 nm': 2, '561 nm': 3, '640 nm': 4}

    def startTask(self):
        """ """
        self.log.info('started Task')

        self.default_exposure = self.ref['cam'].get_exposure()  # store this value to reset it at the end of task

        # stop all interfering modes on GUIs and disable GUI actions
        self.ref['cam'].stop_live_mode()
        self.ref['cam'].disable_camera_actions()

        self.ref['laser'].stop_laser_output()
        self.ref['laser'].disable_laser_actions()  # includes also disabling of brightfield on / off button

        # read all user parameters from config
        self.load_user_parameters()

        # close default FPGA session
        self.ref['laser'].close_default_session()

        # prepare the camera - the maximum number of images per file is ~500. Therefore, the acquisition will be
        # organized as a sequence small acquisition, each composed of 400 images.
        self.sequences = int(np.ceil(self.num_frames_total / self.num_im_per_sequences))
        self.cycles = int(self.num_im_per_sequences / self.num_laserlines)
        print(f'The total number of sequences is {self.sequences} and each contains {self.cycles} cycles of '
              f'acquisition')

        # download the bitfile for the task on the FPGA
        # bitfile = 'C:\\Users\\sCMOS-1\\qudi-cbs\\hardware\\fpga\\FPGA\\FPGA Bitfiles\\FPGAv0_FPGATarget_QudiHiMQPDPID_sHetN0yNJQ8.lvbitx'  # associated to Qudi_HiM_QPD_PID.vi
        bitfile = 'C:\\Users\\sCMOS-1\\qudi-cbs\\hardware\\fpga\\FPGA\\FPGA Bitfiles\\50ms_FPGATarget_QudiFTLQPDPID_u+Bjp+80wxk.lvbitx'
        self.ref['laser'].start_task_session(bitfile)
        self.log.info('Task session started')

        # prepare the daq: set the digital output to 0 before starting the task
        self.ref['daq'].write_to_do_channel(self.ref['daq']._daq.start_acquisition_taskhandle, 1,
                                            np.array([0], dtype=np.uint8))

        # initialize the counter (corresponding to the number of planes already acquired)
        self.step_counter = 0

        # start the session on the fpga using the user parameters
        self.ref['laser'].run_multicolor_imaging_task_session(self.cycles, self.wavelengths, self.intensities,
                                                              self.num_laserlines, self.exposure)

        # defines the timeout value
        self.timeout = self.num_laserlines * self.exposure + 0.1

    def runTaskStep(self):
        """ Implement one work step of your task here.
        :return bool: True if the task should continue running, False if it should finish.
        """

        for sequence in range(self.sequences):
            print(f'imaging sequence #{sequence}')

            if self.aborted:
                break

            self.ref['cam'].prepare_camera_for_multichannel_imaging(self.num_im_per_sequences, self.exposure,
                                                                    None, None, None)
            self.ref['cam'].start_acquisition()

            for cycle in range(self.cycles):

                if self.aborted:
                    break

                # --------------------------------------------------------------------------------------------------
                # imaging sequence (handled by FPGA)
                # --------------------------------------------------------------------------------------------------
                # send signal from daq to FPGA connector 0/DIO3 ('piezo ready')
                sleep(0.05)
                self.ref['daq'].write_to_do_channel(self.ref['daq']._daq.start_acquisition_taskhandle, 1,
                                                    np.array([1], dtype=np.uint8))
                sleep(0.005)
                self.ref['daq'].write_to_do_channel(self.ref['daq']._daq.start_acquisition_taskhandle, 1,
                                                    np.array([0], dtype=np.uint8))

                # wait for signal from FPGA to DAQ ('acquisition ready')
                fpga_ready = self.ref['daq'].read_di_channel(self.ref['daq']._daq.acquisition_done_taskhandle, 1)[0]
                t0 = time()

                while not fpga_ready:
                    sleep(0.001)
                    fpga_ready = self.ref['daq'].read_di_channel(self.ref['daq']._daq.acquisition_done_taskhandle, 1)[0]

                    t1 = time() - t0
                    if t1 > self.timeout:  # for safety: timeout if no signal received within the calculated time (in s)
                        self.log.warning('Timeout occurred')
                        break

            # ------------------------------------------------------------------------------------------------------
            # save the images
            # ------------------------------------------------------------------------------------------------------
            image_data = self.ref['cam'].get_acquired_data()
            image_data = image_data[:, 255:1791, 255:1791]
            image_name = os.path.join(os.path.split(self.complete_path)[0], f'sequence_{sequence}.tif')
            print(image_name)

            self.ref['cam'].save_to_tiff(self.num_im_per_sequences, image_name, image_data)
            metadata = self.get_metadata()
            file_path = image_name.replace('tif', 'yaml', 1)
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

        # reset the camera to default state
        self.ref['cam'].reset_camera_after_multichannel_imaging()
        self.ref['cam'].set_exposure(self.default_exposure)

        # close the fpga session and restart the default session
        self.ref['laser'].end_task_session()
        self.ref['laser'].restart_default_session()
        self.log.info('restarted default fpga session')

        # enable gui actions
        self.ref['cam'].enable_camera_actions()
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
            sample_name: 'Mysample'
            exposure: 0.05  # in s
            save_path: 'E:\'
            imaging_sequence: [('488 nm', 3), ('561 nm', 3), ('641 nm', 10)]
        """
        try:
            with open(self.user_config_path, 'r') as stream:
                self.user_param_dict = yaml.safe_load(stream)

                self.sample_name = self.user_param_dict['sample_name']
                self.exposure = self.user_param_dict['exposure']
                self.num_frames_total = self.user_param_dict['num_z_planes']
                self.imaging_sequence = self.user_param_dict['imaging_sequence']
                self.save_path = self.user_param_dict['save_path']

        except Exception as e:  # add the type of exception
            self.log.warning(f'Could not load user parameters for task {self.name}: {e}')

        # establish further user parameters derived from the given ones
        self.complete_path = self.get_complete_path(self.save_path)

        # count the number of lightsources
        self.num_laserlines = len(self.imaging_sequence)

        # convert the imaging_sequence given by user into format required by the bitfile
        wavelengths = [self.imaging_sequence[i][0] for i in range(self.num_laserlines)]
        for n, key in enumerate(wavelengths):
            if key == 'Brightfield':
                wavelengths[n] = 0
            else:
                wavelengths[n] = self.lightsource_dict[key]

        for i in range(self.num_laserlines, 5):
            wavelengths.append(0)  # must always be a list of length 5: append zeros until necessary length reached
        self.wavelengths = wavelengths

        self.intensities = [self.imaging_sequence[i][1] for i, item in enumerate(self.imaging_sequence)]
        for i in range(self.num_laserlines, 5):
            self.intensities.append(0)

    # ------------------------------------------------------------------------------------------------------------------
    # file path handling
    # ------------------------------------------------------------------------------------------------------------------

    def get_complete_path(self, path_stem):
        """ Create the complete path based on path_stem given as user parameter,
        such as path_stem/YYYY_MM_DD/001_Scan_samplename/scan_001.tif
        or path_stem/YYYY_MM_DD/027_Scan_samplename/scan_027.fits

        :param: str path_stem such as E:/DATA
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
        foldername = f'{prefix}_Scan_{self.sample_name}'

        path = os.path.join(path_stem_with_date, foldername)

        # create the path  # no need to check if it already exists due to incremental prefix
        try:
            os.makedirs(path)  # recursive creation of all directories on the path
        except Exception as e:
            self.log.error('Error {0}'.format(e))

        file_name = f'scan_{prefix}.{self.file_format}'
        complete_path = os.path.join(path, file_name)
        return complete_path

    # ------------------------------------------------------------------------------------------------------------------
    # metadata
    # ------------------------------------------------------------------------------------------------------------------

    def get_metadata(self):
        """ Get a dictionary containing the metadata in a plain text easy readable format.

        :return: dict metadata
        """
        metadata = {'Sample name': self.sample_name, 'Exposure time (s)': self.exposure,
                    'Number of images per sequences': self.num_im_per_sequences,
                    'Number of sequences': self.sequences,
                    'Number laserlines': self.num_laserlines}
        for i in range(self.num_laserlines):
            metadata[f'Laser line {i+1}'] = self.imaging_sequence[i][0]
            metadata[f'Laser intensity {i+1} (%)'] = self.imaging_sequence[i][1]

        return metadata

    def get_fits_metadata(self):
        """ Get a dictionary containing the metadata in a fits header compatible format.

        :return: dict metadata
        """
        metadata = {'SAMPLE': (self.sample_name, 'sample name'), 'EXPOSURE': (self.exposure, 'exposure time (s)'),
                    'Z_STEP': (self.z_step, 'scan step length (um)'),
                    'Z_TOTAL': (self.z_step * self.num_z_planes, 'scan total length (um)'),
                    'CHANNELS': (self.num_laserlines, 'number laserlines')}
        for i in range(self.num_laserlines):
            metadata[f'LINE{i+1}'] = (self.imaging_sequence[i][0], f'laser line {i+1}')
            metadata[f'INTENS{i+1}'] = (self.imaging_sequence[i][1], f'laser intensity {i+1}')
        return metadata

    def save_metadata_file(self, metadata, path):
        """ Save a txt file containing the metadata dictionary.

        :param dict metadata: dictionary containing the metadata
        :param str path: pathname
        """
        with open(path, 'w') as outfile:
            yaml.safe_dump(metadata, outfile, default_flow_style=False)
        self.log.info('Saved metadata to {}'.format(path))
