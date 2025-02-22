# -*- coding: utf-8 -*-
"""
Qudi-CBS

An extension to Qudi.

This module contains the Hi-M Experiment for the Airyscan experimental setup using epifluorescence configuration.
(For confocal configuration, use HiM_task_Airyscan_confocal.) It is a modification of the HiM task created for the
Airyscan microscope and used for epi-fluorescence

@author: JB. Fiche

Created on Mon May 16 2021
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
import pandas as pd
import os
import re
import time
import tkinter as tk
import shutil
from time import sleep
from datetime import datetime
from scipy.signal import correlate
from czifile import imread
from tifffile import TiffWriter
from glob import glob
from logic.generic_task import InterruptableTask
from logic.task_helper_functions import save_injection_data_to_csv, create_path_for_injection_data
from logic.task_helper_functions import get_entry_nested_dict
from logic.task_logging_functions import update_default_info, write_status_dict_to_file, add_log_entry
from tkinter import messagebox
from qtpy import QtCore


data_saved = True  # Global variable to follow data registration for each cycle (signal/slot communication is not


class UploadDataWorker(QtCore.QRunnable):
    """ Worker thread to parallelize data uploading to network during injections. This worker is opening the czi file
    acquired by ZEN and saving it on the network as a tif.

    :param: str data_path = path to the local data
    :param: str dest_folder = path where the data should be uploaded
    """

    def __init__(self, data_path, dest_folder):
        super(UploadDataWorker, self).__init__()
        self.data_local_path = data_path
        self.data_network_path = dest_folder

    @QtCore.Slot()
    def run(self):
        """ Copy the file to destination
        """
        _, file_extension = os.path.splitext(self.data_local_path)
        if file_extension != '.czi':
            shutil.copy(self.data_local_path, self.data_network_path)
        else:
            self.save_czi_to_tif()

        global data_saved
        data_saved = True

    def save_czi_to_tif(self):
        """ Convert the czi file and save it on the network as a tif
        """
        movie = imread(self.data_local_path)
        print(f'movie shape is {movie.shape}')
        n_channel = movie.shape[1]
        n_z = movie.shape[2]

        with TiffWriter(self.data_network_path) as tf:
            for z in range(n_z):
                for c in range(n_channel):
                    im = movie[0, c, z, :, :, 0]
                    im = np.array(im)
                    tf.save(im.astype(np.uint16))


class Task(InterruptableTask):
    """ This task performs a Hi-M experiment on the Airyscan setup in epifluorescence configuration using the
     lumencor celesta lightsource.

    Config example pour copy-paste:
            HiMTask:
                module: 'HiM_task_Airyscan'
                needsmodules:
                    daq : 'daq_logic'
                    laser : 'lasercontrol_logic'
                    roi: 'roi_logic'
                    valves: 'valve_logic'
                    pos: 'positioning_logic'
                    flow: 'flowcontrol_logic'
                config:
                    path_to_user_config: 'C:/Users/MFM/qudi_files/qudi_task_config_files/hi_m_task_AIRYSCAN.yml'
                    IN7_ZEN : 0
                    OUT7_ZEN : 1
                    OUT8_ZEN : 3
                    camera_global_exposure : 2
    """
    # ==================================================================================================================
    # Generic Task methods
    # ==================================================================================================================

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.threadpool = QtCore.QThreadPool()

        self.user_config_path: str = self.config['path_to_user_config']
        self.directory: str = ""
        self.zen_directory: str = ""
        self.user_param_dict: dict = {}
        self.sample_name: str = ""
        self.probe_counter: int = 0
        self.user_param_dict: dict = {}
        self.logging: bool = True
        self.num_z_planes: int = 0
        self.imaging_sequence: list = []
        self.save_path: str = ""
        self.roi_list_path: str = ""
        self.roi_names: list = []
        self.num_laserlines: int = 0
        self.intensity_dict: dict = {}
        self.ao_channel_sequence: list = []
        self.lumencor_channel_sequence: list = []
        self.IN7_ZEN: int = self.config['IN7_ZEN']
        self.OUT7_ZEN: int = self.config['OUT7_ZEN']
        self.OUT8_ZEN: int = self.config['OUT8_ZEN']
        self.camera_global_exposure: float = self.config['camera_global_exposure']
        self.log_folder: str = ""
        self.default_info_path: str = ""
        self.status_dict_path: str = ""
        self.log_path: str = ""
        self.status_dict: dict = {}
        self.start: float = 0
        self.injections_path: str = ""
        self.hybridization_list: list = []
        self.photobleaching_list: list = []
        self.buffer_dict: dict = {}
        self.probe_list: list = []
        self.prefix: str = ""
        self.probe_dict: dict = {}
        self.probe_valve_number: int = self.config['probe_valve_number']
        self.zen_ref_images_path: str = ""
        self.zen_saving_path: str = ""
        self.ref_images: list = []
        self.correlation_score: list = []
        self.save_path_content_before: list = []
        self.root = None
        self.save_network_path: str = ""
        self.transfer_data: bool = False
        self.uploaded_files: list = []
        self.network_directory: str = ""

    def startTask(self):
        """ """
        self.start = time.time()

        # stop all interfering modes on GUIs and disable GUI actions
        self.ref['roi'].disable_tracking_mode()
        self.ref['roi'].disable_roi_actions()

        self.ref['valves'].disable_valve_positioning()
        self.ref['flow'].disable_flowcontrol_actions()
        self.ref['pos'].disable_positioning_actions()

        # create the tkinter root window and hide it
        self.root = tk.Tk()
        self.root.withdraw()

        # send an error message to make sure the filter on the backport of the microscope is set to position 2
        messagebox.showinfo("Check microscope configuration", "Make sure the back-port filter is set on position 2")

        # control if experiment can be started : origin defined in position logic ?
        if not self.ref['pos'].origin:
            self.log.warning(
                'No position 1 defined for injections. Experiment can not be started. Please define position 1!')
            return

        # Send message that initialization is complete and the experiment is starting
        self.log.info('HiM experiment is starting ...')

        # set stage velocity
        self.ref['roi'].set_stage_velocity({'x': .5, 'y': .5})

        # read all user parameters from config
        self.load_user_parameters()

        # create the daq channels
        self.ref['daq'].initialize_digital_channel(self.OUT7_ZEN, 'input')
        self.ref['daq'].initialize_digital_channel(self.OUT8_ZEN, 'input')
        self.ref['daq'].initialize_digital_channel(self.camera_global_exposure, 'input')
        self.ref['daq'].initialize_digital_channel(self.IN7_ZEN, 'output')

        # define the laser intensities as well as the sequence for the daq external trigger.
        # Set : - all laser lines to OFF and wake the source up
        #       - all the ao_channels to +5V
        #       - the celesta laser source in external TTL mode
        #       - the intensity of each laser line according to the task parameters
        self.format_imaging_sequence()
        self.ref['laser'].stop_laser_output()
        self.ref['laser'].disable_laser_actions()  # includes also disabling of brightfield on / off button
        self.ref['daq'].initialize_ao_channels()
        self.ref['laser'].lumencor_set_ttl(True)
        self.ref['laser'].lumencor_set_laser_line_intensities(self.intensity_dict)

        # check the reference image for the autofocus - sort them in the right acquisition order and store them in a
        # list
        ref_im_name_list = self.sort_czi_path_list(self.zen_ref_images_path)
        for im_name in ref_im_name_list:
            ref_image = imread(im_name)
            ref_image = ref_image[0, 0, :, :, 0]
            self.ref_images.append(ref_image)

        # define the correlation list where the data will be saved
        self.correlation_score = np.zeros((len(self.probe_list), len(self.roi_names)))

        # # check the images in the save folder
        # self.save_path_content_before = glob(os.path.join(self.zen_saving_path, '**', '*_AcquisitionBlock1_pt*.czi'),
        #                                      recursive=True)
        # return the list of immediate subdirectories in self.zen_saving_path
        zen_folder_list_before = glob(os.path.join(self.zen_saving_path, '*'))

        # indicate to the user the parameters he should use for zen configuration
        self.log.warning('############ ZEN PARAMETERS ############')
        self.log.warning('This task is ONLY compatible with experiment ZEN/HiM_celesta_autofocus_intensity')
        self.log.warning('Number of acquisition loops in ZEN experiment designer : {}'.format(
            len(self.probe_list) * len(self.roi_names)))
        self.log.warning('For each acquisition block C={} and Z={}'.format(self.num_laserlines, self.num_z_planes))
        self.log.warning('The number of ticked channels should be equal to {}'.format(self.num_laserlines))
        self.log.warning('Select the autofocus block and hit "Start Experiment"')
        self.log.warning('########################################')

        # wait for the trigger from ZEN indicating that the experiment is starting
        trigger = self.ref['daq'].read_di_channel(self.OUT7_ZEN, 1)
        while trigger == 0 and not self.aborted:
            sleep(.1)
            trigger = self.ref['daq'].read_di_channel(self.OUT7_ZEN, 1)

        # return the list of immediate subdirectories in self.zen_saving_path and compare it to the previous list. When
        # ZEN starts the experiment, it automatically creates a new data folder. The two lists are compared and the
        # folder where the czi data will be saved is defined.
        attempt = 0
        while attempt < 10:

            attempt = attempt + 1
            zen_folder_list_after = glob(os.path.join(self.zen_saving_path, '*'))
            self.zen_directory = list(set(zen_folder_list_after) - set(zen_folder_list_before))

            if len(self.zen_directory) == 1:
                self.zen_directory = self.zen_directory[0]
                print(f'ZEN will save the data in the following folder : {self.zen_directory}')
            elif len(self.zen_directory) == 0:
                sleep(1)
            else:
                print('More than one folder were found. The acquisition is aborted')
                self.aborted = True

        # check the autofocus images in the save folder
        self.save_path_content_before = glob(os.path.join(self.zen_directory, '**', '*_AcquisitionBlock1_pt*.czi'),
                                             recursive=True)

        # create a directory in which all the metadata will be saved (for zen the acquisition parameters and file name
        # are saved on a separate computer) and create the network directory as well
        self.directory = self.create_directory(self.save_path)
        if self.transfer_data:
            self.network_directory = self.create_directory(self.save_network_path)

        # # save the acquisition parameters
        # metadata = self.get_metadata()
        # self.save_metadata_file(metadata, os.path.join(self.directory, "parameters.yml"))

        # log file paths -----------------------------------------------------------------------------------------------
        self.log_folder = os.path.join(self.directory, 'hi_m_log')
        os.makedirs(self.log_folder)  # recursive creation of all directories on the path

        # default info file is used on start of the bokeh app to configure its display elements. It is needed only once
        self.default_info_path = os.path.join(self.log_folder, 'default_info.yaml')
        # the status dict 'current_status.yaml' contains basic information and updates regularly
        self.status_dict_path = os.path.join(self.log_folder, 'current_status.yaml')
        # the log file contains more detailed information about individual steps and is a user readable format.
        # It is also useful after the experiment has finished.
        self.log_path = os.path.join(self.log_folder, 'log.csv')

        if self.logging:
            # initialize the status dict yaml file
            self.status_dict = {'cycle_no': None, 'process': None, 'start_time': self.start, 'cycle_start_time': None}
            write_status_dict_to_file(self.status_dict_path, self.status_dict)
            # initialize the log file
            log = {'timestamp': [], 'cycle_no': [], 'process': [], 'event': [], 'level': []}
            df = pd.DataFrame(log, columns=['timestamp', 'cycle_no', 'process', 'event', 'level'])
            df.to_csv(self.log_path, index=False, header=True)

        # update the default_info file that is necessary to run the bokeh app
        if self.logging:
            # hybr_list = [item for item in self.hybridization_list if item['time'] is None]
            # photobl_list = [item for item in self.photobleaching_list if item['time'] is None]
            last_roi_number = int(self.roi_names[-1].strip('ROI_'))
            update_default_info(self.default_info_path, self.user_param_dict, self.directory, 'czi',
                                self.probe_dict, last_roi_number, self.hybridization_list, self.photobleaching_list)
        # logging prepared ---------------------------------------------------------------------------------------------

        # initialize a counter to iterate over the number of probes to inject
        self.probe_counter = 0

    def runTaskStep(self):
        """ Implement one work step of your task here.
        :return: bool: True if the task should continue running, False if it should finish.
        """
        # go directly to cleanupTask if position 1 is not defined or ZEN ready trigger not received
        if not self.ref['pos'].origin:
            return False

        if not self.aborted:
            now = time.time()
            # info message indicating the probe
            self.probe_counter += 1
            probe_name = self.probe_list[self.probe_counter - 1][1]
            self.log.info(f'Probe number {self.probe_counter}: {probe_name}')

            if self.logging:
                self.status_dict['cycle_no'] = self.probe_counter
                self.status_dict['cycle_start_time'] = now
                write_status_dict_to_file(self.status_dict_path, self.status_dict)
                add_log_entry(self.log_path, self.probe_counter, 0, f'Started cycle {self.probe_counter}', 'info')

            # position the needle in the probe
            needle_pos = self.probe_list[self.probe_counter - 1][0]
            self.ref['pos'].start_move_to_target(needle_pos)
            while self.ref['pos'].moving is True:
                sleep(0.1)

            # disable again the move stage button
            self.ref['pos'].disable_positioning_actions()

        # --------------------------------------------------------------------------------------------------------------
        # Hybridization
        # --------------------------------------------------------------------------------------------------------------
        if not self.aborted:

            if self.logging:
                self.status_dict['process'] = 'Hybridization'
                write_status_dict_to_file(self.status_dict_path, self.status_dict)
                add_log_entry(self.log_path, self.probe_counter, 1, 'Started Hybridization', 'info')

            # list all the files that were already acquired and uploaded
            if self.transfer_data:
                path_to_upload = self.check_acquired_data()
            else:
                path_to_upload = []

            # position the valves for hybridization sequence
            self.ref['valves'].set_valve_position('b', 1)  # RT rinsing valve: inject probe
            self.ref['valves'].wait_for_idle()

            # iterate over the steps in the hybridization sequence
            rt_injection = 0

            for step in range(len(self.hybridization_list)):
                if self.aborted:
                    break

                self.log.info(f'Hybridisation step {step+1}')
                if self.logging:
                    add_log_entry(self.log_path, self.probe_counter, 1, f'Started injection {step + 1}')

                if self.hybridization_list[step]['product'] is not None:  # an injection step
                    # set the 8 way valve to the position corresponding to the product
                    product = self.hybridization_list[step]['product']
                    valve_pos = self.buffer_dict[product]
                    self.ref['valves'].set_valve_position('a', valve_pos)
                    self.ref['valves'].wait_for_idle()

                    # for the Airyscan, the needle is connected to the valve position defined in the config file by
                    # self.probe_valve_number. If this valve is called more than once, the needle will move to the next
                    # position. The procedure was added to make the DAPI injection easier.
                    print('Valve position : {}'.format(valve_pos))
                    if rt_injection == 0 and valve_pos == self.probe_valve_number:
                        rt_injection += 1
                        needle_pos += 1
                    elif rt_injection > 0 and valve_pos == self.probe_valve_number:
                        self.ref['pos'].start_move_to_target(needle_pos)
                        while self.ref['pos'].moving is True:
                            sleep(0.1)
                        rt_injection += 1
                        needle_pos += 1
                        self.ref['pos'].disable_positioning_actions()

                    # pressure regulation
                    # create lists containing pressure and volume data and initialize first value to 0
                    pressure = [0]
                    volume = [0]
                    flowrate = self.ref['flow'].get_flowrate()

                    self.ref['flow'].set_pressure(0.0)  # as initial value
                    self.ref['flow'].start_pressure_regulation_loop(self.hybridization_list[step]['flowrate'])

                    # start counting the volume of buffer or probe
                    self.ref['flow'].start_volume_measurement(self.hybridization_list[step]['volume'])

                    ready = self.ref['flow'].target_volume_reached
                    while not ready:
                        time.sleep(1)
                        ready = self.ref['flow'].target_volume_reached
                        # retrieve data for data saving at the end of interation
                        self.append_flow_data(pressure, volume, flowrate)
                        # if data are ready to be saved, launch a worker
                        path_to_upload = self.launch_data_uploading(path_to_upload)

                        if self.aborted:
                            ready = True

                    self.ref['flow'].stop_pressure_regulation_loop()
                    time.sleep(1)  # time to wait until last regulation step is finished, afterwards reset pressure to 0
                    # get the last data points for flow data
                    self.append_flow_data(pressure, volume, flowrate)
                    time.sleep(1)
                    self.ref['flow'].set_pressure(0.0)

                    # save pressure and volume data to file
                    complete_path = create_path_for_injection_data(self.directory,
                                                                   probe_name,
                                                                   'hybridization', step)
                    save_injection_data_to_csv(pressure, volume, flowrate, complete_path)

                else:  # an incubation step
                    t = self.hybridization_list[step]['time']
                    self.log.info(f'Incubation time.. {t} s')

                    # allow abort by splitting the waiting time into small intervals of 30 s
                    num_steps = t // 30
                    remainder = t % 30
                    for i in range(num_steps):

                        # if data are ready to be saved, launch a worker
                        path_to_upload = self.launch_data_uploading(path_to_upload)

                        if not self.aborted:
                            time.sleep(30)
                    if not self.aborted:
                        time.sleep(remainder)

                    self.log.info('Incubation time finished')

                if self.logging:
                    add_log_entry(self.log_path, self.probe_counter, 1, f'Finished injection {step + 1}')

            # set valves to default positions
            self.ref['valves'].set_valve_position('a', 1)  # 8 way valve
            self.ref['valves'].wait_for_idle()
            self.ref['valves'].set_valve_position('b', 1)  # RT rinsing valve: Inject probe
            self.ref['valves'].wait_for_idle()

            if self.logging:
                add_log_entry(self.log_path, self.probe_counter, 1, 'Finished Hybridization', 'info')

        # --------------------------------------------------------------------------------------------------------------
        # Imaging for all ROI
        # --------------------------------------------------------------------------------------------------------------
        if not self.aborted:

            if self.logging:
                self.status_dict['process'] = 'Imaging'
                write_status_dict_to_file(self.status_dict_path, self.status_dict)
                add_log_entry(self.log_path, self.probe_counter, 2, 'Started Imaging', 'info')

            # make sure there is no data being transferred
            global data_saved
            print('Checking there is no data being transferred ...')
            while not data_saved:
                time.sleep(1)

            # ref_folder = r'W:\jb\2022-05-11\RT-7.czi\RT-7_AcquisitionBlock1.czi'
            # im_list = glob(os.path.join(ref_folder, '*.czi'))
            # im_list = sorted(im_list)
            # print(im_list)

            # start the acquisition loop over all the roi
            for n_roi, roi in enumerate(self.roi_names):
                if self.aborted:
                    break

                # make sure the celesta laser source is ready
                self.ref['laser'].lumencor_wakeup()

                # define the name of the file according to the roi number and cycle
                # roi = self.roi_names[roi_counter]
                scan_name = self.file_name(roi, probe_name)

                # move to roi ------------------------------------------------------------------------------------------
                self.ref['roi'].active_roi = None
                self.ref['roi'].set_active_roi(name=roi)
                self.ref['roi'].go_to_roi_xy()
                self.log.info('Moved to {}'.format(roi))
                self.ref['roi'].stage_wait_for_idle()
                # roi_counter += 1

                if self.logging:
                    add_log_entry(self.log_path, self.probe_counter, 2, f'Moved to {roi}')

                # --------------------------------------------------------------------------------------------------------------
                # autofocus (ZEN)
                # --------------------------------------------------------------------------------------------------------------

                # send trigger to ZEN to start the autofocus search
                sleep(5)
                self.ref['daq'].write_to_do_channel(self.IN7_ZEN, 1, 1)
                sleep(0.1)
                self.ref['daq'].write_to_do_channel(self.IN7_ZEN, 1, 0)

                # wait for ZEN trigger indicating the task is completed
                trigger = self.ref['daq'].read_di_channel(self.OUT8_ZEN, 1)
                while trigger == 0 and not self.aborted:
                    sleep(.1)
                    trigger = self.ref['daq'].read_di_channel(self.OUT8_ZEN, 1)

                # check the autofocus image is in focus. This is performed in a few steps :
                #   1- wait for a new autofocus output image to be saved by ZEN
                #   2- calculate the correlation score is then calculated and saved
                #   3- if the correlation score is too low, the experiment is put in hold
                new_autofocus_image_path = self.check_for_new_autofocus_images()

                ref_image = self.ref_images[n_roi]
                new_image = imread(new_autofocus_image_path[0])
                correlation_score = self.calculate_correlation_score(ref_image, new_image[0, 0, :, :, 0])
                self.correlation_score[self.probe_counter-1, n_roi] = correlation_score

                if correlation_score < 0.9:
                    answer = messagebox.askokcancel("Autofocus is lost!", "Proceed?")
                    if not answer:
                        self.aborted = True
                        break
                    else:
                        messagebox.showinfo("Proceed with experiment", "The experiment will move to the next ROI...")

                print(f'correlation for image #{n_roi} : {correlation_score}')

                # ------------------------------------------------------------------------------------------------------
                # imaging sequence
                # ------------------------------------------------------------------------------------------------------

                # launch the acquisition task
                sleep(5)
                self.ref['daq'].write_to_do_channel(self.IN7_ZEN, 1, 1)
                sleep(0.1)
                self.ref['daq'].write_to_do_channel(self.IN7_ZEN, 1, 0)

                for plane in range(self.num_z_planes):
                    for i in range(len(self.imaging_sequence)):

                        # daq waiting for global_exposure trigger from the camera --------------------------------------
                        error = self.wait_for_camera_trigger(1)
                        if error is True:
                            return False

                        # switch the selected laser line ON ------------------------------------------------------------
                        # self.ref['laser'].lumencor_set_laser_line_emission(self.lumencor_channel_sequence[i])
                        self.ref['daq'].write_to_ao_channel(5, self.ao_channel_sequence[i])

                        # daq waiting for global_exposure trigger from the camera to end -------------------------------
                        error = self.wait_for_camera_trigger(0)
                        if error is True:
                            return False

                        # switch the selected laser line OFF -----------------------------------------------------------
                        self.ref['daq'].write_to_ao_channel(0, self.ao_channel_sequence[i])

                # save the file name
                self.save_file_name(os.path.join(self.directory, 'movie_name.txt'), scan_name)

            # go back to first ROI (to avoid a long displacement just before restarting imaging)
            self.ref['roi'].set_active_roi(name=self.roi_names[0])
            self.ref['roi'].go_to_roi_xy()

            if self.logging:
                add_log_entry(self.log_path, self.probe_counter, 2, 'Finished Imaging', 'info')

        # --------------------------------------------------------------------------------------------------------------
        # Photobleaching
        # --------------------------------------------------------------------------------------------------------------
        if not self.aborted:

            if self.logging:
                self.status_dict['process'] = 'Photobleaching'
                write_status_dict_to_file(self.status_dict_path, self.status_dict)
                add_log_entry(self.log_path, self.probe_counter, 3, 'Started Photobleaching', 'info')

            # rinse needle after photobleaching
            self.ref['valves'].set_valve_position('a', self.probe_valve_number)  # Towards probe
            self.ref['valves'].wait_for_idle()
            self.ref['valves'].set_valve_position('b', 2)  # RT rinsing valve: rinse needle
            self.ref['valves'].wait_for_idle()
            start_rinsing_time = time.time()

            # list all the files that were already acquired and uploaded
            if self.transfer_data:
                path_to_upload = self.check_acquired_data()
            else:
                path_to_upload = []

            # iterate over the steps in the photobleaching sequence
            for step in range(len(self.photobleaching_list)):
                if self.aborted:
                    break

                self.log.info(f'Photobleaching step {step+1}')
                if self.logging:
                    add_log_entry(self.log_path, self.probe_counter, 3, f'Started injection {step + 1}')

                if self.photobleaching_list[step]['product'] is not None:  # an injection step
                    # set the 8 way valve to the position corresponding to the product
                    product = self.photobleaching_list[step]['product']
                    valve_pos = self.buffer_dict[product]
                    self.ref['valves'].set_valve_position('a', valve_pos)
                    self.ref['valves'].wait_for_idle()

                    # pressure regulation
                    # create lists containing pressure, volume and flowrate data and initialize first value to 0
                    pressure = [0]
                    volume = [0]
                    flowrate = self.ref['flow'].get_flowrate()

                    self.ref['flow'].set_pressure(0.0)  # as initial value
                    self.ref['flow'].start_pressure_regulation_loop(self.photobleaching_list[step]['flowrate'])
                    # start counting the volume of buffer or probe
                    self.ref['flow'].start_volume_measurement(self.photobleaching_list[step]['volume'])

                    ready = self.ref['flow'].target_volume_reached
                    while not ready:
                        time.sleep(1)
                        ready = self.ref['flow'].target_volume_reached
                        # retrieve data for data saving at the end of interation
                        self.append_flow_data(pressure, volume, flowrate)
                        # if data are ready to be saved, launch a worker
                        path_to_upload = self.launch_data_uploading(path_to_upload)

                        if self.aborted:
                            ready = True

                    self.ref['flow'].stop_pressure_regulation_loop()
                    time.sleep(1)  # time to wait until last regulation step is finished, afterwards reset pressure to 0
                    # get the last data points
                    self.append_flow_data(pressure, volume, flowrate)
                    time.sleep(1)

                    self.ref['flow'].set_pressure(0.0)

                    # save pressure and volume data to file
                    complete_path = create_path_for_injection_data(self.directory,
                                                                   probe_name,
                                                                   'photobleaching', step)
                    save_injection_data_to_csv(pressure, volume, flowrate, complete_path)

                else:  # an incubation step
                    t = self.photobleaching_list[step]['time']
                    self.log.info(f'Incubation time.. {t} s')

                    # allow abort by splitting the waiting time into small intervals of 30 s
                    num_steps = t // 30
                    remainder = t % 30
                    for i in range(num_steps):
                        # if data are ready to be saved, launch a worker
                        path_to_upload = self.launch_data_uploading(path_to_upload)
                        if not self.aborted:
                            time.sleep(30)
                    time.sleep(remainder)

                    self.log.info('Incubation time finished')

                if self.logging:
                    add_log_entry(self.log_path, self.probe_counter, 3, f'Finished injection {step + 1}')

            # verify if rinsing finished in the meantime
            current_time = time.time()
            diff = current_time - start_rinsing_time
            if diff < 60:
                time.sleep(60 - diff + 1)

            # set valves to default positions
            self.ref['valves'].set_valve_position('a', 1)  # 8 way valve
            self.ref['valves'].wait_for_idle()
            self.ref['valves'].set_valve_position('b', 1)  # RT rinsing valve: Rinse needle
            self.ref['valves'].wait_for_idle()

            if self.logging:
                add_log_entry(self.log_path, self.probe_counter, 3, 'Finished Photobleaching', 'info')

        if not self.aborted:
            if self.logging:
                add_log_entry(self.log_path, self.probe_counter, 0, f'Finished cycle {self.probe_counter}', 'info')

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

        if self.logging:
            try:
                self.status_dict = {}
                write_status_dict_to_file(self.status_dict_path, self.status_dict)
            except Exception:  # in case cleanup task was called before self.status_dict_path is defined
                pass

        # save correlation score
        np.save(os.path.join(self.directory, 'correlation.npy'), self.correlation_score)

        # if the task was not aborted, make sure all the files were properly transferred (if the online transfer option
        # was selected by the user)
        if self.aborted:
            if self.logging:
                add_log_entry(self.log_path, self.probe_counter, 0, 'Task was aborted.', level='warning')
            # add extra actions to end up in a proper state: pressure 0, end regulation loop, set valves to default
            # position, etc. (maybe not necessary because all those elements will still be done above)
        else:
            # list all the files that were already acquired and uploaded
            if self.transfer_data:
                path_to_upload = self.check_acquired_data()
            else:
                path_to_upload = []
            while path_to_upload and not self.aborted:
                time.sleep(1)
                path_to_upload = self.launch_data_uploading(path_to_upload)

        # destroy the tkinter window
        self.root.destroy()

        # reset stage velocity to default
        self.ref['roi'].set_stage_velocity({'x': 6, 'y': 6})  # 5.74592

        # enable gui actions
        # roi gui
        self.ref['roi'].enable_tracking_mode()
        self.ref['roi'].enable_roi_actions()

        # fluidics control gui
        self.ref['valves'].enable_valve_positioning()
        self.ref['flow'].enable_flowcontrol_actions()
        self.ref['pos'].enable_positioning_actions()

        # reset the lumencor state
        self.ref['laser'].lumencor_set_ttl(False)
        self.ref['laser'].voltage_off()

        total = time.time() - self.start
        print(f'total time with logging = {self.logging}: {total} s')

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
            num_z_planes: 50
            imaging_sequence: [('488 nm', 3), ('561 nm', 3), ('641 nm', 10)]
            roi_list_path: 'pathstem/qudi_files/qudi_roi_lists/roilist_20210101_1128_23_123243.json'
            injections_path: 'pathstem/qudi_files/qudi_injection_parameters/injections_2021_01_01.yml'
            dapi_path: 'E:/imagedata/2021_01_01/001_HiM_MySample_dapi'
        """
        try:
            with open(self.user_config_path, 'r') as stream:
                self.user_param_dict = yaml.safe_load(stream)

                self.sample_name = self.user_param_dict['sample_name']
                self.num_z_planes = self.user_param_dict['num_z_planes']
                self.imaging_sequence = self.user_param_dict['imaging_sequence']
                self.save_path = self.user_param_dict['save_path']
                self.injections_path = self.user_param_dict['injections_path']
                self.roi_list_path = self.user_param_dict['roi_list_path']
                self.zen_ref_images_path = self.user_param_dict['zen_ref_images_path']
                self.zen_saving_path = self.user_param_dict['zen_saving_path']
                self.transfer_data = self.user_param_dict['transfer_data']
                self.save_network_path = self.user_param_dict['save_network_path']

        except Exception as e:  # add the type of exception
            self.log.warning(f'Could not load user parameters for task {self.name}: {e}')

        # establish further user parameters derived from the given ones:
        # load rois from file and create a list
        self.ref['roi'].load_roi_list(self.roi_list_path)
        self.roi_names = self.ref['roi'].roi_names
        # injections
        self.load_injection_parameters()
        # get the number of laser lines
        self.num_laserlines = len(self.imaging_sequence)

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

    # ------------------------------------------------------------------------------------------------------------------
    # communication with ZEN
    # ------------------------------------------------------------------------------------------------------------------

    def wait_for_camera_trigger(self, value):
        """ This method contains a loop to wait for the camera exposure starts or stops.

        :return: bool ready: True: trigger was received, False: experiment cannot be started because ZEN is not ready
        """
        bit_value = self.ref['daq'].read_di_channel(self.camera_global_exposure, 1)
        counter = 0
        error = False

        while bit_value != value and error is False and not self.aborted:
            counter += 1
            bit_value = self.ref['daq'].read_di_channel(self.camera_global_exposure, 1)
            if counter > 10000:
                self.log.warning(
                    'No trigger was detected during the past 60s... experiment is aborted')
                error = True

        return error

    # ------------------------------------------------------------------------------------------------------------------
    # data for imaging cycle with Lumencor
    # ------------------------------------------------------------------------------------------------------------------

    def format_imaging_sequence(self):
        """ Format the imaging_sequence dictionary for the celesta laser source and the daq ttl/ao sequence for the
        triggers. For controlling the laser source, two solutions are tested :
        - directly by communicating with the Lumencor, in that case the intensity dictionary is used to predefine the
        intensity of each laser line, and the list emission_state contains the succession of emission state for the
        acquisition
        - by using the Lumencor is external trigger mode. In that case, the intensity dictionary is used the same way
        but the DAQ is controlling the succession of emission state
        """

    # Load the laser and intensity dictionary used in lasercontrol_logic -----------------------------------------------
        laser_dict = self.ref['laser'].get_laser_dict()
        intensity_dict = self.ref['laser'].init_intensity_dict()
        imaging_sequence = [(*get_entry_nested_dict(laser_dict, self.imaging_sequence[i][0], 'label'),
                             self.imaging_sequence[i][1]) for i in range(len(self.imaging_sequence))]

    # Load the daq dictionary for ttl ----------------------------------------------------------------------------------
        daq_dict = self.ref['daq']._daq.get_dict()
        ao_channel_sequence = []
        lumencor_channel_sequence = []

    # Update the intensity dictionary and defines the sequence of ao channels for the daq ------------------------------
        for i in range(len(imaging_sequence)):
            key = imaging_sequence[i][0]
            intensity_dict[key] = imaging_sequence[i][1]
            if daq_dict[key]['channel']:
                ao_channel_sequence.append(daq_dict[key]['channel'])
            else:
                self.log.warning('The wavelength {} is not configured for external trigger mode with DAQ'.format(
                    laser_dict[key]['wavelength']))

            emission_state = np.zeros((len(laser_dict), ), dtype=int)
            emission_state[laser_dict[key]['channel']] = 1
            lumencor_channel_sequence.append(emission_state.tolist())

        self.intensity_dict = intensity_dict
        self.ao_channel_sequence = ao_channel_sequence
        self.lumencor_channel_sequence = lumencor_channel_sequence

    # ------------------------------------------------------------------------------------------------------------------
    # data for injection tracking
    # ------------------------------------------------------------------------------------------------------------------

    def append_flow_data(self, pressure_list, volume_list, flowrate_list):
        """ Retrieve most recent values of pressure, volume and flowrate from flowcontrol logic and
        append them to lists storing all values.
        :param: list pressure_list
        :param: list volume_list
        :param: list flowrate_list

        :return: None
        """
        new_pressure = self.ref['flow'].get_pressure()[0]  # get_pressure returns a list, we just need the first element
        new_total_volume = self.ref['flow'].total_volume
        new_flowrate = self.ref['flow'].get_flowrate()[0]
        pressure_list.append(round(new_pressure, 1))
        volume_list.append(round(new_total_volume, 1))
        flowrate_list.append(round(new_flowrate, 1))

    # ------------------------------------------------------------------------------------------------------------------
    # file path handling
    # ------------------------------------------------------------------------------------------------------------------

    def create_directory(self, path_stem):
        """ Create the directory (based on path_stem given as user parameter),
        in which the folders for the ROI will be created
        Example: path_stem/YYYY_MM_DD/001_Scan_samplename (default)
        or path_stem/YYYY_MM_DD/001_Scan_samplename_dapi (option dapi)
        or path_stem/YYYY_MM_DD/001_Scan_samplename_rna (option rna)

        :param: str path_stem: base name of the path that will be created

        :return: str path (see example above)
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

        foldername = f'{prefix}_Scan_{self.sample_name}'
        path = os.path.join(path_stem_with_date, foldername)

        # create the path  # no need to check if it already exists due to incremental prefix
        try:
            os.makedirs(path)  # recursive creation of all directories on the path
        except Exception as e:
            self.log.error('Error {0}'.format(e))

        return path

    def file_name(self, roi_number, probe_name):
        """ Define the complete name of the image data file.

        :param: str roi_number: string identifier of the current ROI for which a complete path shall be created
        :return: str complete_path: such as directory/ROI_001/scan_001_004_ROI.tif (experiment nb. 001, ROI nb. 004)
        """

        roi_number_inv = roi_number.strip('ROI_') + '_ROI'  # for compatibility with analysis format
        file_name = f'scan_{self.prefix}_{probe_name}_{roi_number_inv}'
        return file_name

    @staticmethod
    def save_file_name(file, movie_name):
        with open(file, 'a+') as outfile:
            outfile.write(movie_name)
            outfile.write("\n")

    # ------------------------------------------------------------------------------------------------------------------
    # metadata
    # ------------------------------------------------------------------------------------------------------------------

    def get_metadata(self):
        """ Get a dictionary containing the metadata in a plain text easy readable format.

        :return: dict metadata
        """
        metadata = {'Sample name': self.sample_name, 'Scan number of planes (um)': self.num_z_planes,
                    'Number laserlines': self.num_laserlines}
        for i in range(self.num_laserlines):
            metadata[f'Laser line {i + 1}'] = self.imaging_sequence[i][0]
            metadata[f'Laser intensity {i + 1} (%)'] = self.imaging_sequence[i][1]

        for roi in self.roi_names:
            pos = self.ref['roi'].get_roi_position(roi)
            metadata[roi] = f'X = {pos[0]} - Y = {pos[1]}'

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
    # autofocus check helper functions
    # ------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def sort_czi_path_list(folder):
        """ Specific function sorting the name of the czi file in "human" order, that is in the order of acquisition.

        @param folder: folder where to look for the czi files
        @return: list the content of the folder in the acquisition order
        """
        path_list = glob(os.path.join(folder, '*.czi'))
        file_list = [os.path.basename(path) for path in path_list]

        pt_list = np.zeros((len(file_list),))
        sorted_path_list = [None] * len(file_list)

        for n, file in enumerate(file_list):
            digit = re.findall('\d+', file)
            pt_list[n] = int(digit[-1])

        for n, idx in enumerate(np.argsort(pt_list)):
            sorted_path_list[n] = path_list[idx]

        return sorted_path_list

    def check_for_new_autofocus_images(self):
        """ Check whether a new autofocus image was saved by ZEN by comparing the content of the folder before and after
        launching the autofocus procedure. When the autofocus procedure is performed, two new files are added : a
        temporary file and an empty image. When the procedure is completed, the temporary file is destroyed.

        @return: the path pointing toward the newly acquired autofocus images
        """
        # analyze the content of the folder until a new autofocus image is detected
        new_image_found = False
        while not new_image_found:
            save_path_content_after = glob(os.path.join(self.zen_directory, '**', '*_AcquisitionBlock1_pt*.czi'),
                                           recursive=True)
            print(save_path_content_after)
            new_autofocus_image_path = list(set(save_path_content_after) - set(self.save_path_content_before))
            if len(new_autofocus_image_path) > 1:
                sleep(0.5)
                print('temporary file')
            elif len(new_autofocus_image_path) == 0:
                sleep(0.5)
                print('no file')
            else:
                new_image_found = True

        # update the content of the folder for the next acquisition
        self.save_path_content_before = save_path_content_after

        return new_autofocus_image_path

    @staticmethod
    def calculate_correlation_score(ref_image, new_image):
        """ Compute a correlation score (1 = perfectly correlated - 0 = no correlation) between two images

        @param ref_image: reference image (specific of the roi)
        @param new_image: newly acquired autofocus image
        @return: correlation score
        """
        # bin the two images from 2048x2048 to 512x512
        shape = (512, 4, 512, 4)
        ref_image_bin = ref_image.reshape(shape).mean(-1).mean(1)
        new_image_bin = new_image.reshape(shape).mean(-1).mean(1)

        # select the central portion of the reference image. The idea is to use a smaller image to compute the
        # correlation faster but also to be less sensitive to any translational variations between the two images.
        ref_image_bin_roi = ref_image_bin[128:384, 128:384]

        # calculate the correlation between the two images and compute a score (with respect to the reference)
        correlation_ref = correlate(ref_image_bin_roi, ref_image_bin, mode='valid')
        correlation_new = correlate(ref_image_bin_roi, new_image_bin, mode='valid')
        correlation_score = np.max(correlation_new) / np.max(correlation_ref)

        return correlation_score

    # ------------------------------------------------------------------------------------------------------------------
    # data for acquisition tracking
    # ------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def calculate_save_projection(num_channel, image_array, saving_path):

        # According to the number of channels acquired, split the stack accordingly
        deinterleaved_array_list = [image_array[idx::num_channel] for idx in range(num_channel)]

        # For each channel, the projection is calculated and saved as a npy file
        for n_channel in range(num_channel):
            image_array = deinterleaved_array_list[n_channel]
            projection = np.max(image_array, axis=0)
            path = saving_path.replace('.tif', f'_ch{n_channel}_2D', 1)
            np.save(path, projection)

    def check_acquired_data(self):
        """ List all the acquired data in the directory and all the data already uploaded on the network. Compare the
        data in order to return a list containing only the paths to the files that were not transferred yet. In order to
        optimize the transfer, the npy and yaml files are processed first (allowing to use bokeh).

        @return: path_to_upload : list of all the files in the local directory
        """
        # look for all the czi/txt/npy/yml files in the folder
        path_to_upload_npy = glob(self.directory + '/*.npy', recursive=True)
        print(f'Number of npy files found : {len(path_to_upload_npy)}')
        path_to_upload_txt = glob(self.directory + '/*.txt', recursive=True)
        print(f'Number of txt files found : {len(path_to_upload_txt)}')
        path_to_upload_czi = glob(self.zen_directory + '/**/*_AcquisitionBlock2_pt*.czi', recursive=True)
        print(f'Number of czi files found : {len(path_to_upload_czi)}')
        path_to_upload = path_to_upload_npy + path_to_upload_txt + path_to_upload_czi

        # # look for all the tif/npy/yml files in the destination folder
        # uploaded_path_npy = glob(self.network_directory + '/**/*.npy', recursive=True)
        # uploaded_path_yml = glob(self.network_directory + '/**/*.yaml', recursive=True)
        # uploaded_path_czi = glob(self.network_directory + '/**/*.czi', recursive=True)
        # uploaded_path = uploaded_path_npy + uploaded_path_yml + uploaded_path_czi
        # uploaded_files = []
        # for n, path in enumerate(uploaded_path):
        #     uploaded_files.append(os.path.basename(path))

        # remove from the list all the files that have already been transferred
        selected_path_to_upload = set(path_to_upload)
        for path in path_to_upload:
            # file_name = os.path.basename(path)
            if path in self.uploaded_files:
                selected_path_to_upload.remove(path)
        selected_path_to_upload = list(selected_path_to_upload)

        # sort the list based on the file format
        idx_czi = []
        idx_npy = []
        idx_txt = []

        for n, path in enumerate(selected_path_to_upload):
            if path.__contains__('.npy'):
                idx_npy.append(n)
            elif path.__contains__('.txt'):
                idx_txt.append(n)
            else:
                idx_czi.append(n)

        # build the final list of file to transfer
        path_to_upload_sorted = [selected_path_to_upload[i] for i in idx_npy] \
                                + [selected_path_to_upload[i] for i in idx_txt] \
                                + [selected_path_to_upload[i] for i in idx_czi]

        print(f'Number of files to upload : {len(path_to_upload_sorted)}')
        return list(path_to_upload_sorted)

    def launch_data_uploading(self, path_to_upload):
        """ Look for the next file to upload and start the worker on a specific thread to launch the transfer

        @param path_to_upload: list of all the files in the local directory
        """
        global data_saved

        if data_saved and path_to_upload:

            path = path_to_upload.pop(0)

            # rewrite the path to the server, following the same hierarchy. Note that npy and yml files can be saved as
            # they are. However, the czi files needs to be converted, renamed and saved as tif. The following part is
            # handling the renaming of the czi files.
            _, file_extension = os.path.splitext(path)
            if file_extension != '.czi':
                relative_dir = os.path.relpath(os.path.dirname(path), start=self.directory)
                network_dir = os.path.join(self.network_directory, relative_dir)
                os.makedirs(network_dir, exist_ok=True)
            else:
                czi_renamed = self.rename_czi(path)
                network_dir = os.path.join(self.network_directory, czi_renamed)

            # launch the worker to start the transfer
            data_saved = False
            print(f"uploading {path}")
            worker = UploadDataWorker(path, network_dir)
            self.threadpool.start(worker)

            # update the uploaded_files list
            self.uploaded_files.append(path)

        return path_to_upload

    def rename_czi(self, movie_path):
        """ According to the experiment's parameters defined on Qudi, each czi file is associated to a unique file name.

        @param movie_path: path to the czi file selected for uploading
        @return: name of the associated tif file indicating the ROI, RT and scan number for the selected file
        """
        # list all the czi files and sort them according to the acquisition order
        czi_path = glob(self.zen_directory + '/**/*_AcquisitionBlock2_pt*.czi', recursive=True)

        data_number = []
        for file in czi_path:
            n = re.findall(r'_pt\d+', file)
            data_number.append(n[0][3:])

        data_number = np.array(data_number)
        data_number = data_number.astype(np.int16)
        idx = np.argsort(data_number)

        sorted_czi_path = []
        for n in idx:
            sorted_czi_path.append(czi_path[n])

        # list all the names of the movie from the txt file updated during acquisition
        with open(os.path.join(self.directory, 'movie_name.txt')) as f:
            data_name = f.readlines()
            data_name = [x.strip() for x in data_name]

        # find the position of the selected file to upload in sorted_czi_path and return the associated name from
        # data_name
        idx = sorted_czi_path.index(movie_path)
        return data_name[idx] + '.tif'



