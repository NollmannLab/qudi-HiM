# -*- coding: utf-8 -*-
"""
Qudi-CBS

An extension to Qudi.

This module contains all the steps to run a Hi-M experiment for the RAMM setup.

@todo: Save the injection data together with the log.
@todo: Wash IB if experiment is aborted during acquisition
@todo: In the parameter file - correct the imaging parameters (they are empty but an imaging sequence is indicated)
@todo: In the parameter file - add the autofocus parameters

@authors: JB.Fiche (based of F.Barho initial script)

Created on Thu Jan 18 2024
Last modification : Wed Feb 28 2024
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
import numpy as np
# import pandas as pd
import os
import shutil
import logging
import platform
import subprocess
import smtplib
from email.message import EmailMessage
from datetime import datetime
from tqdm import tqdm
from logic.generic_task import InterruptableTask
# from logic.task_helper_functions import save_z_positions_to_file, save_injection_data_to_csv, \
#     create_path_for_injection_data
# from logic.task_logging_functions import update_default_info, write_status_dict_to_file
# from logic.task_logging_functions import add_log_entry
from qtpy import QtCore
from glob import glob
from time import sleep, time

data_saved = True  # Global variable to follow data registration for each cycle (signal/slot communication is not


class UploadDataWorker(QtCore.QRunnable):
    """ Worker thread to parallelize data uploading to network during injections. Available with QRunnable - however,
    since qudi is using QThreadPool & QRunnable, I kept the same method for multi-threading (jb).

    :@param: str data_path = path to the local data
    :@param: str dest_folder = path where the data should be uploaded
    """

    def __init__(self, data_path, dest_folder):
        super(UploadDataWorker, self).__init__()
        self.data_local_path = data_path
        self.data_network_path = dest_folder

    @QtCore.Slot()
    def run(self):
        """ Copy the file to destination
        """
        global data_saved
        try:
            shutil.copy(self.data_local_path, self.data_network_path)
            data_saved = True
        except OSError as e:
            print(f"An error occurred during data transfer : {e}")


class Task(InterruptableTask):  # do not change the name of the class. it is always called Task !
    """ This task performs a Hi-M experiment on the RAMM setup.

    Config example pour copy-paste:

    HiMTask:
        module: 'HiM_task_RAMM'
        needsmodules:
            laser: 'lasercontrol_logic'
            bf: 'brightfield_logic'
            cam: 'camera_logic'
            daq: 'nidaq_logic'
            focus: 'focus_logic'
            roi: 'roi_logic'
            valves: 'valve_logic'
            pos: 'positioning_logic'
            flow: 'flowcontrol_logic'
        config:
            path_to_user_config: 'C:/Users/sCMOS-1/qudi_files/qudi_task_config_files/hi_m_task_RAMM.yml'
    """

    # ==================================================================================================================
    # Generic Task methods
    # ==================================================================================================================
    FPGA_max_laserlines = 10

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.threadpool = QtCore.QThreadPool()

        # specific task parameters
        self.probe_counter: int = 0
        self.start: float = 0
        self.timeout: float = 0
        self.IP_to_check: str = "192.168.6.30"  # IP address of GREY
        self.needle_rinsing_duration: int = 30  # time in seconds for rinsing the injection needle
        self.FPGA_bitfile: str = ('C:\\Users\\CBS\\qudi-HiM\\hardware\\fpga\\FPGA\\FPGA Bitfiles\\'
                                  'QudiROImulticolorscan_20240115.lvbitx')
        # self.FPGA_bitfile: str = ('C:\\Users\\CBS\\qudi-HiM\\hardware\\fpga\\FPGA\\FPGA Bitfiles\\'
        #                           'QudiROImulticolorscan_KINETIX_20240731.lvbitx')

        # parameter for handling experiment configuration
        self.user_config_path = self.config['path_to_user_config']
        self.user_param_dict: dict = {}

        # parameters for logging
        self.file_handler: object = None
        self.email: str = ''
        self.log_file: str = 'HiM_task.log'

        # # parameters for bokeh - DEPRECATED -
        # self.bokeh: bool = False
        # self.status_dict_path: str = ""
        # self.status_dict: dict = {}
        # self.log_path: str = ""
        # self.log_folder: str = ""
        # self.default_info_path: str = ""

        # parameters for data handling
        self.directory: str = ""
        self.network_directory: str = ""
        self.sample_name: str = ""
        self.save_path: str = ""
        self.save_network_path: str = ""
        self.transfer_data: bool = False
        self.file_format: str = ""
        self.prefix: str = ""
        self.path_to_upload: list = []

        # parameters for image acquisition
        self.default_exposure: float = 0.05
        self.num_frames: int = 0
        self.exposure: float = 0.05
        self.num_z_planes: int = 0
        self.z_step: float = 0
        self.centered_focal_plane: bool = False
        self.imaging_sequence: list = []
        self.num_laserlines: int = 0
        self.wavelengths: list = []
        self.intensities: list = []
        self.autofocus_failed: int = 0
        self.dz: list = []
        self.celesta_laser_dict: dict = {}
        self.FPGA_wavelength_channels: list = []
        self.celesta_intensity_dict: dict = {}

        # parameters for roi
        self.roi_list_path: list = []
        self.roi_names: list = []

        # parameters for injections
        self.injections_path: str = ""
        self.dapi_path: str = ""
        self.probe_dict: dict = {}
        self.hybridization_list: list = []
        self.photobleaching_list: list = []
        self.buffer_dict: dict = {}
        self.probe_list: list = []
        self.needle_valve_number: int = self.config['needle_valve_number']

    def startTask(self):
        """ """
        self.aborted = self.task_initialization()

        # read all user parameters from config and create a local directory in which all the data will be saved.
        self.load_user_parameters()
        self.directory = self.create_directory(self.save_path)

        # initialize the logger for the task
        self.init_logger()

        # save all the experiment parameters into a single file
        self.save_parameters()

        # retrieve the list of sources from the laser logic and format the imaging sequence (for Lumencor & FPGA)
        self.celesta_laser_dict = self.ref['laser']._laser_dict
        self.format_imaging_sequence()

        # log file paths
        # Previous version was set for bokeh and required access to a directory on a distant server. Log file is now
        # saved in the same folder that the data
        # self.init_bokeh()

        # prepare the camera - must be done before starting the FPGA. The camera sends sometimes 'false' trigger
        # signals that are detected by the FPGA and induce a shift in the way the images should be acquired. This
        # issue was only happening for the very first acquisition.
        self.num_frames = self.num_z_planes * self.num_laserlines
        self.timeout = self.num_laserlines * self.exposure + 0.1
        self.ref['cam'].prepare_camera_for_multichannel_imaging(self.num_frames, self.exposure, None, None, None)

        # prepare the Lumencor celesta laser source and pre-set the intensity of each laser line
        self.ref['laser'].lumencor_wakeup()
        self.ref['laser'].lumencor_set_ttl(True)
        self.ref['laser'].lumencor_set_laser_line_intensities(self.celesta_intensity_dict)

        # prepare the daq: set the digital output to 0 before starting the task
        self.ref['daq'].write_to_do_channel(self.ref['daq']._daq.start_acquisition_taskhandle, 1,
                                            np.array([0], dtype=np.uint8))

        # download the bitfile for the task on the FPGA and start the FPGA session
        self.log.info('FPGA bitfile loaded for HiM task')
        self.ref['laser'].start_task_session(self.FPGA_bitfile)
        self.ref['laser'].run_celesta_roi_multicolor_imaging_task_session(self.num_z_planes,
                                                                          self.FPGA_wavelength_channels,
                                                                          self.num_laserlines, self.exposure)

        # calculate the list of axial positions between successive rois (this is important for the stability of the
        # acquisition)
        self.dz = self.compute_axial_correction()

        # If the transfer option is selected, a network directory is also saved to transfer data on the server and allow
        # online analysis
        if (self.save_network_path is not None) and self.transfer_data:
            if self.check_local_network():
                self.network_directory = self.create_directory(self.save_network_path)
            else:
                logging.warning(f"Network connection is unavailable. The directory for transferring the data "
                                f"({self.save_network_path}) cannot be created. The experiment is aborted.")
                self.aborted = True

        # initialize a counter to iterate over the number of probes to inject
        self.probe_counter = 0

    def runTaskStep(self):
        """ Implement one work step of your task here.
        :return: bool: True if the task should continue running, False if it should finish.
        """

        if not self.aborted:
            self.probe_counter += 1
            self.log.info(f'Probe number {self.probe_counter}: {self.probe_list[self.probe_counter - 1][1]}')

            # list all the files that were already acquired and uploaded
            if self.transfer_data:
                self.path_to_upload = self.check_acquired_data()

        # --------------------------------------------------------------------------------------------------------------
        # Hybridization
        # --------------------------------------------------------------------------------------------------------------
        if not self.aborted:
            # if self.bokeh:
            #     self.status_dict['cycle_no'] = self.probe_counter
            #     self.status_dict['cycle_start_time'] = time()
            #     write_status_dict_to_file(self.status_dict_path, self.status_dict)
            #     add_log_entry(self.log_path, self.probe_counter, 0, f'Started cycle {self.probe_counter}', 'info')
            #     self.status_dict['process'] = 'Hybridization'
            #     write_status_dict_to_file(self.status_dict_path, self.status_dict)
            #     add_log_entry(self.log_path, self.probe_counter, 1, 'Started Hybridization', 'info')

            # position the needle in the tube associated to the selected probe
            self.ref['pos'].start_move_to_target(self.probe_list[self.probe_counter - 1][0])
            self.ref['pos'].disable_positioning_actions()  # to disable again the move stage button
            while self.ref['pos'].moving is True:
                sleep(0.1)

            # position the valves for hybridization sequence
            self.prepare_valves_for_injection()

            # iterate over the steps in the hybridization sequence
            needle_injection = 0
            needle_pos = self.probe_list[self.probe_counter - 1][0]
            for step in range(len(self.hybridization_list)):
                # if self.bokeh:
                #     add_log_entry(self.log_path, self.probe_counter, 1, f'Started injection {step + 1}')
                if self.aborted:
                    break

                product = self.hybridization_list[step]['product']
                flowrate = self.hybridization_list[step]['flowrate']
                volume = self.hybridization_list[step]['volume']
                incubation_time = self.hybridization_list[step]['time']

                if product is not None:  # an injection step
                    self.log.info(f'Hybridisation step {step + 1} - product: {product} - volume: {volume}µl '
                                  f'- flowrate: {flowrate}µl/min')
                    needle_pos, needle_injection = self.set_valves_and_needle(product, needle_injection, needle_pos)
                    self.perform_injection(flowrate, volume, transfer=self.transfer_data)

                else:  # an incubation step
                    self.log.info(f'Hybridisation step {step + 1} - incubation time : {incubation_time}s')
                    self.incubation(incubation_time, transfer=self.transfer_data)

                # if self.bokeh:
                #     add_log_entry(self.log_path, self.probe_counter, 1, f'Finished injection {step + 1}')

            # reset valves to default positions
            self.reset_valves_after_injection()

            # if self.bokeh:
            #     add_log_entry(self.log_path, self.probe_counter, 1, 'Finished Hybridization', 'info')

        # --------------------------------------------------------------------------------------------------------------
        # Imaging for all ROI
        # --------------------------------------------------------------------------------------------------------------
        if not self.aborted:
            # if self.bokeh:
            #     self.status_dict['process'] = 'Imaging'
            #     write_status_dict_to_file(self.status_dict_path, self.status_dict)
            #     add_log_entry(self.log_path, self.probe_counter, 2, 'Started Imaging', 'info')

            # make sure there is no data being transferred
            self.check_data_transfer()

            # launch the acquisition
            for n_roi, item in enumerate(self.roi_names):
                if self.aborted:
                    break

                # create the save path for each roi
                cur_save_path = self.get_complete_path(self.directory, item, self.probe_list[self.probe_counter - 1][1])

                # move to roi
                self.move_to_roi(item)

                # correct the axial position
                # the correction is not applied for the very first roi acquisition since we are starting in-focus.
                self.correct_axial_position(n_roi)

                # autofocus - if the autofocus is lost for two consecutive ROIs, the experiment is aborted -------------
                autofocus_lost = self.perform_autofocus()
                if autofocus_lost:
                    self.aborted = True
                    self.send_alert_email()
                    break

                # reset piezo position to default starting position if too close to the limits of travel range.
                self.correct_piezo()

                # imaging sequence -------------------------------------------------------------------------------------
                if self.aborted:
                    break

                # prepare the daq: set the digital output to 0 before starting the task
                self.ref['daq'].write_to_do_channel(self.ref['daq']._daq.start_acquisition_taskhandle, 1,
                                                    np.array([0], dtype=np.uint8))

                # start camera acquisition
                self.ref['cam'].start_acquisition()

                # compute the starting position of the stack
                reference_position = self.ref['focus'].get_position()  # save it to go back to this plane after imaging
                start_position = self.calculate_start_position(self.centered_focal_plane)

                # iterate over all planes in z
                self.acquire_z_stack(item, reference_position, start_position)

                # save data in the correct format
                self.save_stack(cur_save_path)

                # stop the camera (and allow the shutter security to be removed)
                self.ref['cam'].stop_acquisition()

                # # calculate and save projection for bokeh
                # if self.bokeh:
                #     self.calculate_save_projection(self.num_laserlines, image_data, cur_save_path)
                #     # save file with z positions (same procedure for either file format)
                #     file_path = os.path.join(os.path.split(cur_save_path)[0], 'z_positions.yaml')
                #     save_z_positions_to_file(z_target_positions, z_actual_positions, file_path)
                #     add_log_entry(self.log_path, self.probe_counter, 2, 'Image data saved', 'info')

            # go back to first ROI (to avoid a long displacement just before restarting imaging)
            self.ref['roi'].set_active_roi(name=self.roi_names[0])
            self.ref['roi'].go_to_roi_xy()

            # if self.bokeh:
            #     add_log_entry(self.log_path, self.probe_counter, 2, 'Finished Imaging', 'info')

        # --------------------------------------------------------------------------------------------------------------
        # Photobleaching
        # --------------------------------------------------------------------------------------------------------------
        if not self.aborted:
            # if self.bokeh:
            #     self.status_dict['process'] = 'Photobleaching'
            #     write_status_dict_to_file(self.status_dict_path, self.status_dict)
            #     add_log_entry(self.log_path, self.probe_counter, 3, 'Started Photobleaching', 'info')

            # list all the files that were already acquired and uploaded
            if self.transfer_data:
                self.path_to_upload = self.check_acquired_data()

            # position the injection valve
            self.ref['valves'].set_valve_position('c', 2)  # Syringe valve: towards pump
            self.ref['valves'].wait_for_idle()

            # iterate over the steps in the photobleaching sequence
            for step in range(len(self.photobleaching_list)):
                if self.aborted:
                    break

                # if self.bokeh:
                #     add_log_entry(self.log_path, self.probe_counter, 3, f'Started injection {step + 1}')

                product = self.photobleaching_list[step]['product']
                flowrate = self.photobleaching_list[step]['flowrate']
                volume = self.photobleaching_list[step]['volume']
                incubation_time = self.photobleaching_list[step]['time']

                if product is not None:  # an injection step
                    # set the 8 way valve to the position corresponding to the product
                    self.log.info(f'Photobleaching step {step + 1} - product: {product} - volume: {volume}µl '
                                  f'- flowrate: {flowrate}µl/min')
                    valve_pos = self.buffer_dict[product]
                    self.ref['valves'].set_valve_position('a', valve_pos)
                    self.ref['valves'].wait_for_idle()

                    # pressure regulation
                    self.perform_injection(flowrate, volume, transfer=self.transfer_data)

                else:  # an incubation step
                    self.log.info(f'Photobleaching step {step + 1} - incubation time : {incubation_time}s')
                    self.incubation(incubation_time, transfer=self.transfer_data)

                # if self.bokeh:
                #     add_log_entry(self.log_path, self.probe_counter, 3, f'Finished injection {step + 1}')

            # stop flux by closing valve towards pump
            self.ref['valves'].set_valve_position('c', 1)  # Syringe valve: towards syringe
            self.ref['valves'].wait_for_idle()

            # rinse needle
            if not self.aborted:
                self.rinse_needle()

            # set valves to default positions
            self.reset_valves_after_injection()

            # if self.bokeh:
            #     add_log_entry(self.log_path, self.probe_counter, 3, 'Finished Photobleaching', 'info')
            #     add_log_entry(self.log_path, self.probe_counter, 0, f'Finished cycle {self.probe_counter}', 'info')

        return (self.probe_counter < len(self.probe_list)) and (not self.aborted)

    def pauseTask(self):
        """ """
        self.log.info('pauseTask called')

    def resumeTask(self):
        """ """
        self.log.info('resumeTask called')

    def cleanupTask(self):
        """ """
        self.log.info('cleanupTask called')

        # if self.bokeh:
        #     try:
        #         self.status_dict = {}
        #         write_status_dict_to_file(self.status_dict_path, self.status_dict)
        #     except Exception:  # in case cleanup task was called before self.status_dict_path is defined
        #         pass

        if self.aborted:
            self.log.warning('HiM experiment was aborted.')
            # if self.bokeh:
            #     add_log_entry(self.log_path, self.probe_counter, 0, 'Task was aborted.', level='warning')
            # add extra actions to end up in a proper state: pressure 0, end regulation loop, set valves to default
            # position .. (maybe not necessary because all those elements will still be done above)
        else:
            # list all the files that were already acquired and uploaded
            if self.transfer_data:
                self.path_to_upload = self.check_acquired_data()

                while self.path_to_upload and (not self.aborted):
                    sleep(1)
                    self.launch_data_uploading()
                    if not self.check_local_network():
                        break

        # reset GUI and hardware
        self.task_ending()

        # reset the logging options and release the handle to the log file
        total = time() - self.start
        self.log.info(f'HiM experiment finished - total time : {total}')
        self.log.removeHandler(self.file_handler)
        self.ref['focus'].log.removeHandler(self.file_handler)

        # if the transfer option was selected, upload the log file
        if self.transfer_data:
            self.upload_log()

    # ==================================================================================================================
    # Helper functions
    # ==================================================================================================================

    # ------------------------------------------------------------------------------------------------------------------
    # initialization of the task and loading user parameters
    # ------------------------------------------------------------------------------------------------------------------
    def task_initialization(self):
        """ Perform all tests and action before properly launching the task.

        @return: abort: (bool) if the safety checks have not been met, the task is aborted.
        """
        abort = False
        self.start = time()

        # store the current exposure value to reset it at the end of task
        self.default_exposure = self.ref['cam'].get_exposure()

        # stop all interfering modes on GUIs and disable GUI actions
        self.ref['roi'].disable_tracking_mode()
        self.ref['roi'].disable_roi_actions()

        self.ref['cam'].stop_live_mode()
        self.ref['cam'].disable_camera_actions()
        self.ref['cam'].stop_acquisition()  # for safety

        self.ref['laser'].stop_laser_output()
        self.ref['bf'].led_off()
        self.ref['laser'].disable_laser_actions()  # includes also disabling of brightfield on / off button

        self.ref['focus'].stop_autofocus()
        self.ref['focus'].disable_focus_actions()
        self.ref['focus'].stop_live_display()

        self.ref['valves'].disable_valve_positioning()
        self.ref['flow'].disable_flowcontrol_actions()
        self.ref['pos'].disable_positioning_actions()

        # control if experiment can be started : origin defined in position logic & autofocus calibrated
        if not self.ref['pos'].origin:
            self.log.warning(
                'No position 1 defined for injections. Experiment can not be started. Please define position 1!')
            abort = True

        if (not self.ref['focus']._calibrated) or (not self.ref['focus']._setpoint_defined):
            self.log.warning('Autofocus is not calibrated. Experiment can not be started. Please calibrate autofocus!')
            abort = True

        # set stage velocity
        self.ref['roi'].set_stage_velocity({'x': 1, 'y': 1})

        # close previously opened FPGA session
        self.ref['laser'].end_task_session()

        return abort

    def task_ending(self):
        """ Perform all actions in order to properly end the task and make sure all hardware and GUI will remain
        available.
        """
        # reset the camera to default state
        self.ref['cam'].reset_camera_after_multichannel_imaging()
        self.ref['cam'].set_exposure(self.default_exposure)

        # close the fpga session
        self.ref['laser'].end_task_session()
        self.ref['laser'].restart_default_session()
        self.log.info('restarted default fpga session')

        # reset stage velocity to default
        self.ref['roi'].set_stage_velocity({'x': 3, 'y': 3})  # 5.74592

        # enable gui actions
        # roi gui
        self.ref['roi'].enable_tracking_mode()
        self.ref['roi'].enable_roi_actions()
        # basic imaging gui
        self.ref['cam'].enable_camera_actions()
        self.ref['laser'].enable_laser_actions()
        # focus tools gui
        self.ref['focus'].enable_focus_actions()
        # fluidics control gui
        self.ref['valves'].enable_valve_positioning()
        self.ref['flow'].enable_flowcontrol_actions()
        self.ref['pos'].enable_positioning_actions()

    def init_logger(self):
        """ Initialize a logger for the task. This logger is overriding the logger called in qudi-core, adding the
        possibility to directly write into a log file. The idea is that all errors and warnings sent by qudi will also
        be written in the log file, together with the task specific messages.
        """
        # define the handler for the log file
        self.file_handler = logging.FileHandler(filename=os.path.join(self.directory, self.log_file))
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        self.file_handler.setFormatter(formatter)

        # instantiate the logger
        self.log.addHandler(self.file_handler)
        self.log.info('started Task')

        # instantiate the logger for the focus
        self.ref['focus'].log.addHandler(self.file_handler)

    def load_user_parameters(self):
        """ This function is called from startTask() to load the parameters given by the user in a specific format.

        Specify the path to the user defined config for this task in the (global) config of the experimental setup.

        user must specify the following dictionary (here with example entries):
            sample_name: 'Mysample'
            exposure: 0.05  # in s
            num_z_planes: 50
            z_step: 0.25  # in um
            centered_focal_plane: False
            imaging_sequence: [('488 nm', 3), ('561 nm', 3), ('641 nm', 10)]
            save_path: 'E:/'
            file_format: 'tif'
            roi_list_path: 'pathstem/qudi_files/qudi_roi_lists/roilist_20210101_1128_23_123243.json'
            injections_path: 'pathstem/qudi_files/qudi_injection_parameters/injections_2021_01_01.yml'
            dapi_path: 'E:/imagedata/2021_01_01/001_HiM_MySample_dapi'
        """
        try:
            with open(self.user_config_path, 'r') as stream:
                self.user_param_dict = yaml.safe_load(stream)

                self.sample_name = self.user_param_dict['sample_name']
                self.exposure = self.user_param_dict['exposure']
                self.num_z_planes = self.user_param_dict['num_z_planes']
                self.z_step = self.user_param_dict['z_step']  # in um
                self.centered_focal_plane = self.user_param_dict['centered_focal_plane']
                self.imaging_sequence = self.user_param_dict['imaging_sequence']
                self.save_path = self.user_param_dict['save_path']
                self.save_network_path = self.user_param_dict['save_network_path']
                self.transfer_data = self.user_param_dict['transfer_data']
                self.file_format = self.user_param_dict['file_format']
                self.roi_list_path = self.user_param_dict['roi_list_path']
                self.injections_path = self.user_param_dict['injections_path']
                # self.dapi_path = self.user_param_dict['dapi_path']
                self.email = self.user_param_dict['email']

        except Exception as e:  # add the type of exception
            self.log.warning(f'Could not load user parameters for task {self.name}: {e}')

        # establish further user parameters derived from the given ones:

        # load rois from file and create a list ------------------------------------------------------------------------
        self.ref['roi'].load_roi_list(self.roi_list_path)
        self.roi_names = self.ref['roi'].roi_names

        # injections ---------------------------------------------------------------------------------------------------
        self.load_injection_parameters()
        self.log.info('user parameters loaded and processed')

    def load_injection_parameters(self):
        """ Load relevant information from the document containing the injection parameters in a specific format.
        This document is configured using the Qudi injections module to obtain the correct format.
        It is a dictionary with keys 'buffer', 'probes', 'hybridization list' and 'photobleaching list'.
        'buffer' and 'probes' contain themselves subdictionaries as value.
        """
        try:
            with open(self.injections_path, 'r') as stream:
                documents = yaml.safe_load(stream)  # yaml.full_load when yaml package updated
                buffer_dict = documents['buffer']
                self.probe_dict = documents['probes']
                self.hybridization_list = documents['hybridization list']
                self.photobleaching_list = documents['photobleaching list']

            # invert the buffer dict to address the valve by the product name as key
            self.buffer_dict = dict([(value, key) for key, value in buffer_dict.items()])
            # create a list out of probe_dict and order by ascending position
            # (for example: probes in pos 2, 5, 6, 9, 10 is ok but not 10, 2, 5, 6, 9)
            self.probe_list = sorted(self.probe_dict.items())  # list of tuples, such as [(1, 'RT1'), (2, 'RT2')]

        except Exception as e:
            self.log.warning(f'Could not load hybridization sequence for task {self.name}: {e}')

    def save_parameters(self):
        """ All the parameters are saved in the metadata folder as a yaml file.
        """
        param_filepath = os.path.join(self.directory, "HiM_parameters.yml")

        # shape the ROIs into a dictionary
        roi_pos = self.ref['roi'].roi_positions
        roi_dict = {}
        for roi in roi_pos.keys():
            X = roi_pos[roi][0]
            Y = roi_pos[roi][1]
            Z = roi_pos[roi][2]
            roi_dict[roi] = f"X={X} - Y={Y} - Z={Z}"

        # save all parameters into a yaml file
        param = {'1- global parameters': self.user_param_dict,
                 '2- fluidic parameters': {'probes': self.probe_dict,
                                           'hybridization list': self.hybridization_list,
                                           'photobleaching list': self.photobleaching_list},
                 '3- imaging parameters': {'number of laser lines': self.num_laserlines,
                                           'celesta intensity dict': self.celesta_intensity_dict,
                                           'FPGA sequence': self.FPGA_wavelength_channels},
                 '4- ROIs': roi_dict
                 }

        with open(param_filepath, 'w') as outfile:
            yaml.dump(param, outfile, default_flow_style=False)

    def upload_log(self):
        """ At the end of the experiment, upload the log file.
        """
        global data_saved
        data_saved = False

        log_path = os.path.join(self.directory, self.log_file)
        relative_dir = os.path.relpath(os.path.dirname(log_path), start=self.directory)
        network_dir = os.path.join(self.network_directory, relative_dir)

        worker = UploadDataWorker(log_path, network_dir)
        self.threadpool.start(worker)

    # ------------------------------------------------------------------------------------------------------------------
    # methods for mails
    # ------------------------------------------------------------------------------------------------------------------
    def send_alert_email(self):
        """ Email user warning him/her that the experiment was aborted.
        """
        if self.email:
            msg = EmailMessage()
            msg.set_content("Focus lost twice - experiment was aborted")

            msg['Subject'] = 'Focus lost - experiment aborted'
            msg['From'] = 'Qudi_HiM@cbs.cnrs.fr'
            msg['To'] = self.email

            with smtplib.SMTP('194.167.34.218') as s:
                try:
                    s.send_message(msg)
                    self.log.info(f'Email to {self.email} was sent.')
                except smtplib.SMTPRecipientsRefused as err:
                    self.log.err(f'Email to {self.email} could not be sent due to a refused recipient error : {err}.')
                except smtplib.SMTPResponseException as err:
                    self.log.err(f'Email to {self.email} could not be sent due to a reception error : {err}.')
                except Exception as err:
                    self.log.err(f'Email to {self.email} could not be sent due to the following error : {err}.')

    # ------------------------------------------------------------------------------------------------------------------
    # methods for initializing piezo & laser
    # ------------------------------------------------------------------------------------------------------------------

    def format_imaging_sequence(self):
        """ Format the imaging_sequence dictionary for the celesta laser source and the FPGA controlling the triggers.
        The lumencor celesta is controlled in TTL mode. Intensity for each laser line must be set before launching the
        acquisition sequence (using the celesta_intensity_dict). Then, the FPGA will activate each line (either laser or
        brightfield) based on the list of sources (FPGA_wavelength_channels).
        Since the intensity of each laser line must be set before the acquisition, it is not possibe to call the same
        laser line multiple times with different intensity values.
        """
    # reset parameters
        self.FPGA_wavelength_channels = []
        self.celesta_intensity_dict = {}

    # count the number of lightsources for each plane
        self.num_laserlines = len(self.imaging_sequence)

    # from _laser_dict, list all the available laser sources in a dictionary and associate a unique integer value for
    # the FPGA (starting at 1 since, for the FPGA, the brightfield is by default 0 and all the laser lines are organized
    # in increasing wavelength values).
    # In parallel, initialize the dictionary containing the intensity of each laser line of the Celesta.
        available_laser_dict = {}
        for laser in range(len(self.celesta_laser_dict)):
            key = self.celesta_laser_dict[f'laser{laser + 1}']['wavelength']
            available_laser_dict[key] = laser + 1
            self.celesta_intensity_dict[key] = 0

    # convert the imaging_sequence given by the user into format required by the bitfile (by default, 0 is the
    # brightfield and then all the laser lines sorted by increasing wavelength values. Note that a maximum number of
    # laser lines is allowed (self.FPGA_max_laserlines). It is constrained by the size of the laser/intensity arrays
    # defined in the labview script from which the bitfile is compiled.
        for line in range(self.num_laserlines):
            line_source = self.imaging_sequence[line][0]
            line_intensity = self.imaging_sequence[line][1]
            if line_source in available_laser_dict:
                self.FPGA_wavelength_channels.append(available_laser_dict[line_source])
                self.celesta_intensity_dict[line_source] = line_intensity
            else:
                self.FPGA_wavelength_channels.append(0)

    # For the FPGA, the wavelength list should have "FPGA_max_laserlines" entries. The list is padded with zero.
        for i in range(self.num_laserlines, self.FPGA_max_laserlines):
            self.FPGA_wavelength_channels.append(0)

    def calculate_start_position(self, centered_focal_plane):
        """
        This method calculates the piezo position at which the z stack will start. It can either start in the
        current plane or calculate an offset so that the current plane will be centered inside the stack.

        :param: bool centered_focal_plane: indicates if the scan is done below and above the focal plane (True)
                                            or if the focal plane is the bottommost plane in the scan (False)

        :return: float piezo start position
        """
        current_pos = self.ref['focus'].get_position()

        # the scan should start below the current position so that the focal plane will be the central plane or one of
        # the central planes in case of an even number of planes
        if centered_focal_plane:
            # even number of planes:
            if self.num_z_planes % 2 == 0:
                # focal plane is the first one of the upper half of the number of planes
                start_pos = current_pos - self.num_z_planes / 2 * self.z_step
            # odd number of planes:
            else:
                start_pos = current_pos - (self.num_z_planes - 1) / 2 * self.z_step
            return start_pos
        else:
            return current_pos  # the scan starts at the current position and moves up

    def compute_axial_correction(self):
        """ Compute the axial corrections based on the positions of the selected ROIs. This is useful for pre-setting
        the objective position before launching the autofocus when a sample is highly tilted or/and a very large area is
        explored during the HiM acquisition.

        @return: dz: (list) list of axial corrections
        """
        dz = np.zeros((len(self.roi_names),))
        for n in range(len(self.roi_names)):
            if n == 0:
                _, _, z_first = self.ref['roi'].get_roi_position(self.roi_names[0])
                _, _, z_last = self.ref['roi'].get_roi_position(self.roi_names[-1])
                dz[n] = z_first - z_last
            else:
                _, _, z = self.ref['roi'].get_roi_position(self.roi_names[n])
                _, _, z_previous = self.ref['roi'].get_roi_position(self.roi_names[n - 1])
                dz[n] = z - z_previous

        print(f'Differential axial positions : dz = {dz}')
        return dz

    # ------------------------------------------------------------------------------------------------------------------
    # file path handling
    # ------------------------------------------------------------------------------------------------------------------

    def create_directory(self, path_stem):
        """ Create the directory (based on path_stem given as user parameter),
        in which the folders for the ROI will be created
        Example: path_stem/YYYY_MM_DD/001_HiM_samplename

        :param: str pathstem
        :return: str path to directory
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

        foldername = f'{prefix}_HiM_{self.sample_name}'

        path = os.path.join(path_stem_with_date, foldername)

        # create the path  # no need to check if it already exists due to incremental prefix
        try:
            os.makedirs(path)  # recursive creation of all directories on the path
        except Exception as e:
            self.log.error('Error {0}'.format(e))

        return path

    def get_complete_path(self, directory, roi_number, probe_number):
        """ Create the complete path for a file containing image data,
        based on the directory for the experiment that was already created,
        the ROI number and the probe number,
        such as directory/ROI_007/RT2/scan_num_RT2_007_ROI.tif

        :param: str directory
        :param: str roi_number: identifier of the current ROI
        :param: str probe_number: identifier of the current RT

        :return: str complete path (as in the example above)
        """
        path = os.path.join(directory, roi_number, probe_number)

        if not os.path.exists(path):
            try:
                os.makedirs(path)  # recursive creation of all directories on the path
            except Exception as e:
                self.log.error('Error {0}'.format(e))

        roi_number_inv = roi_number.strip('ROI_') + '_ROI'  # for compatibility with analysis format

        file_name = f'scan_{self.prefix}_{probe_number}_{roi_number_inv}.{self.file_format}'

        complete_path = os.path.join(path, file_name)
        return complete_path

    # ------------------------------------------------------------------------------------------------------------------
    # metadata
    # ------------------------------------------------------------------------------------------------------------------

    def get_metadata(self):
        """ Get a dictionary containing the metadata in a plain text easy readable format.

        :return: dict metadata
        """
        metadata = {'Sample name': self.sample_name, 'Exposure time (s)': float(np.round(self.exposure, 3)),
                    'Scan step length (um)': self.z_step, 'Scan total length (um)': self.z_step * self.num_z_planes,
                    'Number laserlines': self.num_laserlines}
        for i in range(self.num_laserlines):
            metadata[f'Laser line {i + 1}'] = self.imaging_sequence[i][0]
            metadata[f'Laser intensity {i + 1} (%)'] = self.imaging_sequence[i][1]

        # add translation stage position
        metadata['x position'] = float(self.ref['roi'].stage_position[0])
        metadata['y position'] = float(self.ref['roi'].stage_position[1])

        # add autofocus information :
        metadata['Autofocus offset'] = float(self.ref['focus']._autofocus_logic._focus_offset)
        metadata['Autofocus calibration precision'] = float(np.round(self.ref['focus']._precision, 2))
        metadata['Autofocus calibration slope'] = float(np.round(self.ref['focus']._slope, 3))
        metadata['Autofocus setpoint'] = float(np.round(self.ref['focus']._autofocus_logic._setpoint, 3))

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
            metadata[f'LINE{i + 1}'] = (self.imaging_sequence[i][0], f'laser line {i + 1}')
            metadata[f'INTENS{i + 1}'] = (self.imaging_sequence[i][1], f'laser intensity {i + 1}')
        metadata['X_POS'] = (self.ref['roi'].stage_position[0], 'x position')
        metadata['Y_POS'] = (self.ref['roi'].stage_position[1], 'y position')

        # add autofocus information :
        metadata['AF_OFFST'] = self.ref['focus']._autofocus_logic._focus_offset
        metadata['AF_PREC'] = np.round(self.ref['focus']._precision, 2)
        metadata['AF_SLOPE'] = np.round(self.ref['focus']._slope, 3)
        metadata['AF_SETPT'] = np.round(self.ref['focus']._autofocus_logic._setpoint, 3)

        # pixel size
        return metadata

    def get_hdf5_metadata(self):
        """ Get a dictionary containing the metadata in a hdf5 header compatible format.
        @return: dict metadata
        """
        metadata = {'sample_name': self.sample_name,
                    'exposure_s': self.exposure,
                    'z_step_µm': self.z_step,
                    'z_total_length_µm': self.z_step * self.num_z_planes,
                    'n_channels': self.num_laserlines,
                    'roi_x_position': self.ref['roi'].stage_position[0],
                    'roi_y_position': self.ref['roi'].stage_position[1],
                    'autofocus_offset': self.ref['focus']._autofocus_logic._focus_offset,
                    'autofocus_calibration_precision': np.round(self.ref['focus']._precision, 2),
                    'autofocus_calibration_slope': np.round(self.ref['focus']._slope, 3),
                    'autofocus_setpoint': np.round(self.ref['focus']._autofocus_logic._setpoint, 3)
                    }
        for i in range(self.num_laserlines):
            metadata[f'laser_line_{i + 1}'] = self.imaging_sequence[i][0]
            metadata[f'laser_intensity_{i + 1}'] = self.imaging_sequence[i][1]
        return metadata

    def save_metadata_file(self, metadata, path):
        """ Save a txt file containing the metadata dictionary.

        :param dict metadata: dictionary containing the metadata
        :param str path: pathname
        """
        with open(path, 'w') as outfile:
            yaml.safe_dump(metadata, outfile, default_flow_style=False)
        self.log.info('Saved metadata to {}'.format(path))

    # ------------------------------------------------------------------------------------------------------------------
    # helper functions for the injections
    # ------------------------------------------------------------------------------------------------------------------
    def prepare_valves_for_injection(self):
        """ Make sure the injection valves are correctly oriented before starting injecting.
        """
        self.ref['valves'].set_valve_position('b', 2)  # RT rinsing valve: inject probe
        self.ref['valves'].wait_for_idle()
        self.ref['valves'].set_valve_position('c', 2)  # Syringe valve: towards pump
        self.ref['valves'].wait_for_idle()

    def reset_valves_after_injection(self):
        """ Make sure the injection valves are either closed or in their default positions.
        """
        self.ref['valves'].set_valve_position('c', 1)  # Syringe valve: towards syringe
        self.ref['valves'].wait_for_idle()
        self.ref['valves'].set_valve_position('a', 1)  # 8 way valve
        self.ref['valves'].wait_for_idle()
        self.ref['valves'].set_valve_position('b', 1)  # RT rinsing valve: Rinse needle
        self.ref['valves'].wait_for_idle()

    def set_valves_and_needle(self, product, needle_injection, needle_position):
        """ Set the positions of the valves and needle for a hybridization step.

        @param product: (str) indicate the product to be injected
        @param needle_injection: (int) indicate the number of injections already performed using the needle
        @param needle_position: (int) indicate the current position of the needle on the tray
        @return: needle_position: (int) return the current needle position
                 needle_injection: (int) return the current number of injections performed with the needle
        """
        # set the 8 way valve to the position corresponding to the product
        valve_pos = self.buffer_dict[product]
        self.ref['valves'].set_valve_position('a', valve_pos)
        self.ref['valves'].wait_for_idle()

        # for the RAMM, the needle is connected to the valve position indicated by "needle_valve_number" (in the config
        # file). If this valve is called more than once, the needle will be moved to the next position. The procedure
        # was added to make the DAPI injection easier.
        if needle_injection == 0 and valve_pos == self.needle_valve_number:
            needle_injection += 1
            needle_position += 1
        elif needle_injection > 0 and valve_pos == self.needle_valve_number:
            self.ref['valves'].set_valve_position('c', 1)  # Syringe valve: close
            self.ref['valves'].wait_for_idle()
            self.ref['pos'].start_move_to_target(needle_position)
            needle_injection += 1
            needle_position += 1
            while self.ref['pos'].moving is True:
                sleep(0.1)
            self.ref['valves'].set_valve_position('c', 2)  # Syringe valve: open
            self.ref['valves'].wait_for_idle()

        return needle_position, needle_injection

    def perform_injection(self, target_flowrate, target_volume, transfer=False):
        """ Perform the injection according to the values of target flowrate and volume.
        N.B All the commented lines were previoulsy used for bokeh

        @param target_flowrate: (float) indicate the average flow-rate that should be used for the injection
        @param target_volume: (int) indicate the target volume for the current injection
        @param transfer: (bool) indicate whether data transfer should be performed during the waiting time
        """
        # pressure regulation
        # create lists containing pressure and volume data and initialize first value to 0
        # pressure = [0]
        # volume = [0]
        # flowrate = [0]

        start_time = time()
        self.ref['flow'].set_pressure(0.0)  # as initial value
        self.ref['flow'].start_pressure_regulation_loop(target_flowrate)

        # start counting the volume of buffer or probe
        self.ref['flow'].start_volume_measurement(target_volume)
        ready = self.ref['flow'].target_volume_reached

        while not ready:
            if self.aborted:
                break

            sleep(1)
            ready = self.ref['flow'].target_volume_reached
            # if data are ready to be saved and the option was selected, launch a worker
            if transfer:
                self.launch_data_uploading()

            # # retrieve data for data saving at the end of interation
            # self.append_flow_data(pressure, volume, flowrate)

        self.ref['flow'].stop_pressure_regulation_loop()
        sleep(1)  # time to wait until last regulation step is finished, afterward reset pressure to 0
        # get the last data points for flow data
        # self.append_flow_data(pressure, volume, flowrate)
        self.ref['flow'].set_pressure(0.0)

        # indicate in the log how long was the injection and compare it to the expected time
        end_time = time()
        expected_time = np.round(target_volume / target_flowrate * 60)
        self.log.info(f'Injection time was {np.round(end_time - start_time)}s and the expected time was '
                      f'{expected_time}s')

        # # save pressure and volume data to file
        # complete_path = create_path_for_injection_data(self.network_directory,
        #                                                self.probe_list[self.probe_counter - 1][1],
        #                                                'hybridization', step)
        # save_injection_data_to_csv(pressure, volume, flowrate, complete_path)

    def incubation(self, t, transfer=False):
        """ Perform an incubation step.

        @param t: (int) indicate the duration of the incubation step in seconds
        @param transfer: (bool) indicate whether data transfer should be performed during the waiting time
        """
        # close the valves to make prevent any flow during the incubation
        self.ref['valves'].set_valve_position('c', 1)  # stop flux
        self.ref['valves'].wait_for_idle()

        # allow abort by splitting the waiting time into small intervals of 30 s
        num_steps = t // 30
        remainder = t % 30
        for i in range(num_steps):
            # if data are ready to be saved and the option is selected, launch a worker
            if transfer:
                self.launch_data_uploading()

            if not self.aborted:
                sleep(30)
                print(f"Elapsed time : {(i + 1) * 30}s")
        sleep(remainder)

        # open the valves for the next step
        self.ref['valves'].set_valve_position('c', 2)  # open flux again
        self.ref['valves'].wait_for_idle()
        self.log.info('Incubation time finished')

    def rinse_needle(self):
        self.log.info('Rinsing needle')
        self.ref['valves'].set_valve_position('b', 1)  # RT rinsing valve: rinse needle
        self.ref['valves'].wait_for_idle()
        self.ref['daq'].start_rinsing(self.needle_rinsing_duration)
        sleep(self.needle_rinsing_duration + 5)

    # ------------------------------------------------------------------------------------------------------------------
    # helper functions for data acquisition
    # ------------------------------------------------------------------------------------------------------------------
    def move_to_roi(self, roi_name):
        """ Move to the indicated ROI and add an entry in the log file.

        @param roi_name: (str) indicate the number of the roi
        """
        self.ref['roi'].active_roi = None
        self.ref['roi'].set_active_roi(name=roi_name)
        self.ref['roi'].go_to_roi_xy()
        timeout = self.ref['roi'].stage_wait_for_idle()
        if timeout:
            self.log.error(f'Timeout reach for ASI stage while moving to {roi_name}')
        else:
            self.log.info(f'Moved to {roi_name}')
        # if self.bokeh:
        #     add_log_entry(self.log_path, self.probe_counter, 2, f'Moved to {roi_name}')

    def correct_axial_position(self, n_roi):
        """ Perform objective axial re-positioning before launching the autofocus.

        @param n_roi: (int) indicate the number of the selected ROI within ROI_list
        """
        if (n_roi == 0) and (self.probe_counter == 1):
            pass
        else:
            dz = self.dz[n_roi]
            self.ref['focus'].stage_move_z_relative(dz)
            timeout = self.ref['focus'].stage_wait_for_idle()
            if timeout:
                self.log.error(f'Timeout reach for ASI stage while correcting objective axial position '
                               f'dz={np.around(dz, decimals=1)}µm')
            else:
                self.log.info(f'Correct objective axial position dz={np.around(dz, decimals=1)}µm')

    def perform_autofocus(self):
        """ Launch the search focus procedure.

        @return: abort_experiment: (bool) Indicate whether the experiment should be stopped
        """
        abort_experiment = False
        self.ref['focus'].start_search_focus()
        # wait for the search focus flag to turn True, indicating that the search procedure is launched. In case
        # the autofocus is lost from the start, the search focus routine is starting and stopped before the
        # while loop is initialized. The aborted flag is then used to avoid getting stuck in the loop.
        search_focus_start = self.ref['focus'].focus_search_running
        while not search_focus_start:
            sleep(0.1)
            search_focus_start = self.ref['focus'].focus_search_running
            if self.ref['focus'].focus_search_aborted:
                self.log.warning('The focus search was aborted')
                break

        # wait for the search focus flag to turn False, indicating that the search procedure stopped, whatever
        # the result
        search_focus_running = self.ref['focus'].focus_search_running
        while search_focus_running:
            sleep(0.5)
            search_focus_running = self.ref['focus'].focus_search_running

        # check if the focus was found
        ready = self.ref['focus']._stage_is_positioned
        if not ready and self.autofocus_failed == 0:
            self.log.warning('The autofocus was lost for the first time.')
            self.autofocus_failed += 1
        elif not ready and self.autofocus_failed > 0:
            self.log.warning('The autofocus was lost for the second time. The HiM experiment is aborted.')
            self.aborted = True
            abort_experiment = True
        else:
            self.autofocus_failed = 0

        # save the final position of the piezo in the log file
        z = self.ref['focus'].get_position()
        self.log.info(f'Final piezo position : {np.around(z, decimals=2)}µm')

        return abort_experiment

    def correct_piezo(self):
        """ Correct the piezo position when it gets too close to the limit positions.
        """
        self.ref['focus'].do_piezo_position_correction()
        busy = True
        while busy:
            sleep(0.5)
            busy = self.ref['focus'].piezo_correction_running

    def acquire_z_stack(self, roi_name, reference_position, start_position):
        """ Perform the stack acquisition.

        @param roi_name: (str) indicate the name of the current ROI
        @param reference_position: (float) axial position before moving the piezo to its initial position
        @param start_position: (float) axial position of the piezo for acquiring the first plane of the stack
        """
        self.log.info(f'performing z stack for {roi_name}.')
        for plane in tqdm(range(self.num_z_planes)):

            # position the piezo
            position = start_position + plane * self.z_step
            self.ref['focus'].go_to_position(position, direct=True)

            # send signal from daq to FPGA connector 0/DIO3 ('piezo ready')
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
                fpga_ready = \
                    self.ref['daq'].read_di_channel(self.ref['daq']._daq.acquisition_done_taskhandle, 1)[0]

                t1 = time() - t0
                if t1 > self.timeout:  # for safety: timeout if no signal received within the indicated time
                    self.log.warning('Timeout occurred during acquisition')
                    break

        # move the piezo back to its initial position
        self.ref['focus'].go_to_position(reference_position, direct=True)

    def save_stack(self, cur_save_path):
        """ Save the stack in the correct format.

        @param cur_save_path: (str) ROI path where to the save the stack.
        """
        image_data = self.ref['cam'].get_acquired_data()

        if self.file_format == 'fits':
            metadata = self.get_fits_metadata()
            self.ref['cam'].save_to_fits(cur_save_path, image_data, metadata)
        elif self.file_format == 'npy':
            self.ref['cam'].save_to_npy(cur_save_path, image_data)
            metadata = self.get_metadata()
            file_path = cur_save_path.replace('npy', 'yaml', 1)
            self.save_metadata_file(metadata, file_path)
            self.log.info(f'Data saved as {file_path}')
        elif self.file_format == 'hdf5':
            metadata = self.get_hdf5_metadata()
            self.ref['cam'].save_to_hdf5(cur_save_path, image_data, metadata)
        else:  # use tiff as default format
            self.ref['cam'].save_to_tiff(self.num_frames, cur_save_path, image_data)
            metadata = self.get_metadata()
            file_path = cur_save_path.replace('tif', 'yaml', 1)
            self.save_metadata_file(metadata, file_path)
            self.log.info(f'Data saved as {file_path}')

    # ------------------------------------------------------------------------------------------------------------------
    # helper functions for data online transferring
    # ------------------------------------------------------------------------------------------------------------------
    def check_local_network(self):
        """ Check if the connection to the local server is working. The IP address should be the typical data server one
         (for example GREY).

        @return: (bool) True if the network is working.
        """
        if platform.system() == 'Linux':
            result = subprocess.run(['ping', '-c', '1', self.IP_to_check],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        else:
            result = subprocess.run(['ping', '-n', '1', self.IP_to_check],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if (result.returncode == 0) and ("unreachable" not in str(result.stdout)):
            return True
        else:
            self.log.warning('Connection to the local server is lost')
            return False

    def check_data_transfer(self):
        """ Before launching an acquisition, check no data is being transferred. If an error occurred during a transfer,
         the global variable "data_saved" will remain False. A timeout of 5 minutes is used. If the timeout is reached,
         we proceed with the acquisition but the transfer is cancelled.
        """
        timeout_t0 = time()
        if self.transfer_data:
            global data_saved
            print('Checking there is no data being transferred ...')
            while not data_saved:
                sleep(1)
                dt = time() - timeout_t0
                if dt > 300:
                    self.log.error("Time out was reached for data transfer. Transfer is cancelled from now on.")
                    self.transfer_data = False
                    break

    def check_acquired_data(self):
        """ List all the acquired data in the directory and all the data already uploaded on the network. Compare the
        data in order to return a list containing only the paths to the files that were not transferred yet. In order to
        optimize the transfer, the npy and yaml files are processed first (allowing to use bokeh).

        @return: path_to_upload : list of all the .tif files in the local directory
        """
        # check the network is available
        if self.check_local_network():

            # look for all the tif/npy/yml files in the folder
            path_to_upload_npy = glob(self.directory + '/**/*.npy', recursive=True)
            # print(f'Number of npy files found : {len(path_to_upload_npy)}')
            path_to_upload_yml = glob(self.directory + '/**/*.yml', recursive=True)
            # print(f'Number of yaml files found : {len(path_to_upload_yml)}')
            path_to_upload_tif = glob(self.directory + '/**/*.tif', recursive=True)
            # print(f'Number of tif files found : {len(path_to_upload_tif)}')
            path_to_upload = path_to_upload_npy + path_to_upload_yml + path_to_upload_tif

            # look for all the tif/npy/yml files in the destination folder
            uploaded_path_npy = glob(self.network_directory + '/**/*.npy', recursive=True)
            uploaded_path_yml = glob(self.network_directory + '/**/*.yml', recursive=True)
            uploaded_path_tif = glob(self.network_directory + '/**/*.tif', recursive=True)
            uploaded_path = uploaded_path_npy + uploaded_path_yml + uploaded_path_tif
            uploaded_files = []
            for n, path in enumerate(uploaded_path):
                uploaded_files.append(os.path.basename(path))

            # remove from the list all the files that have already been transferred
            selected_path_to_upload = set(path_to_upload)
            for path in path_to_upload:
                file_name = os.path.basename(path)
                if file_name in uploaded_files:
                    selected_path_to_upload.remove(path)
            selected_path_to_upload = list(selected_path_to_upload)

            # sort the list based on the file format
            idx_tif = []
            idx_npy = []
            idx_yaml = []

            for n, path in enumerate(selected_path_to_upload):
                if path.__contains__('.npy'):
                    idx_npy.append(n)
                elif path.__contains__('.yaml'):
                    idx_yaml.append(n)
                else:
                    idx_tif.append(n)

            # build the final list of file to transfer
            path_to_upload_sorted = ([selected_path_to_upload[i] for i in idx_npy]
                                     + [selected_path_to_upload[i] for i in idx_yaml]
                                     + [selected_path_to_upload[i] for i in idx_tif])
        else:
            path_to_upload_sorted = []

        print(f'Number of files to upload : {len(path_to_upload_sorted)}')
        return list(path_to_upload_sorted)

    def launch_data_uploading(self):
        """ Look for the next .tif file to upload and start the worker on a specific thread to launch the transfer
        """
        if self.check_local_network():

            global data_saved
            if data_saved and self.path_to_upload:

                path = self.path_to_upload.pop(0)

                # rewrite the path to the server, following the same hierarchy
                relative_dir = os.path.relpath(os.path.dirname(path), start=self.directory)
                network_dir = os.path.join(self.network_directory, relative_dir)
                os.makedirs(network_dir, exist_ok=True)

                # launch the worker to start the transfer
                data_saved = False
                self.log.info(f"uploading {network_dir}")
                worker = UploadDataWorker(path, network_dir)
                self.threadpool.start(worker)

# ======================================================================================================================
#    DEPRECATED FUNCTIONS
# ======================================================================================================================

    # # ----------------------------------------------------------------------------------------------------------------
    # # Bokeh help function
    # # ----------------------------------------------------------------------------------------------------------------
    # def init_bokeh(self):
    #     """ This function was previously used for initializing the log for bokeh. This code was kept for history but
    #      is no longer used.
    #     """
    #     self.log_folder = os.path.join(self.network_directory, 'hi_m_log')
    #     os.makedirs(self.log_folder)  # recursive creation of all directories on the path
    #
    #     # default info file is used on start of bokeh app to configure its display elements. It is needed only once
    #     self.default_info_path = os.path.join(self.log_folder, 'default_info.yaml')
    #     # the status dict 'current_status.yaml' contains basic information and updates regularly
    #     self.status_dict_path = os.path.join(self.log_folder, 'current_status.yaml')
    #     # the log file contains more detailed information about individual steps and is a user readable format.
    #     # It is also useful after the experiment has finished.
    #     self.log_path = os.path.join(self.log_folder, 'log.csv')
    #
    #     if self.bokeh:
    #         # initialize the status dict yaml file
    #         self.status_dict = {'cycle_no': None, 'process': None, 'start_time': self.start, 'cycle_start_time': None}
    #         write_status_dict_to_file(self.status_dict_path, self.status_dict)
    #         # initialize the log file
    #         log = {'timestamp': [], 'cycle_no': [], 'process': [], 'event': [], 'level': []}
    #         df = pd.DataFrame(log, columns=['timestamp', 'cycle_no', 'process', 'event', 'level'])
    #         df.to_csv(self.log_path, index=False, header=True)
    #
    #     # update the default_info file that is necessary to run the bokeh app
    #     if self.bokeh:
    #         # hybr_list = [item for item in self.hybridization_list if item['time'] is None]
    #         # photobl_list = [item for item in self.photobleaching_list if item['time'] is None]
    #         last_roi_number = int(self.roi_names[-1].strip('ROI_'))
    #         update_default_info(self.default_info_path, self.user_param_dict, self.directory, self.file_format,
    #                             self.probe_dict, last_roi_number, self.hybridization_list, self.photobleaching_list)
    #
    # # ----------------------------------------------------------------------------------------------------------------
    # # data for injection tracking
    # # ----------------------------------------------------------------------------------------------------------------
    #
    # def append_flow_data(self, pressure_list, volume_list, flowrate_list):
    #     """ Retrieve most recent values of pressure, volume and flowrate from flowcontrol logic and
    #     append them to lists storing all values.
    #     :param: list pressure_list
    #     :param: list volume_list
    #     :param: list flowrate_list
    #     :return: None
    #     """
    #     new_pressure = self.ref['flow'].get_pressure()[0]  # get_pressure returns a list. just need the first element
    #     new_total_volume = self.ref['flow'].total_volume
    #     new_flowrate = self.ref['flow'].get_flowrate()[0]
    #     pressure_list.append(new_pressure)
    #     volume_list.append(new_total_volume)
    #     flowrate_list.append(new_flowrate)
    #
    # # ----------------------------------------------------------------------------------------------------------------
    # # data for acquisition tracking
    # # ----------------------------------------------------------------------------------------------------------------
    #
    # @staticmethod
    # def calculate_save_projection(num_channel, image_array, saving_path):
    #
    #     # According to the number of channels acquired, split the stack accordingly
    #     deinterleaved_array_list = [image_array[idx::num_channel] for idx in range(num_channel)]
    #
    #     # For each channel, the projection is calculated and saved as a npy file
    #     for n_channel in range(num_channel):
    #         image_array = deinterleaved_array_list[n_channel]
    #         projection = np.max(image_array, axis=0)
    #         path = saving_path.replace('.tif', f'_ch{n_channel}_2D', 1)
    #         np.save(path, projection)
            