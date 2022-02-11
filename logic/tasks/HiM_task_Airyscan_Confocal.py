# -*- coding: utf-8 -*-
"""
Qudi-CBS

An extension to Qudi.

This module contains the Hi-M Experiment for the Airyscan experimental setup using confocal configuration.

@author: F. Barho, JB. Fiche

Created on Thu Aug 26 2021
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
import time
from time import sleep
from datetime import datetime
from logic.generic_task import InterruptableTask
from logic.task_helper_functions import save_injection_data_to_csv, create_path_for_injection_data
from logic.task_helper_functions import get_entry_nested_dict
from logic.task_logging_functions import update_default_info, write_status_dict_to_file, add_log_entry


class Task(InterruptableTask):  # do not change the name of the class. it is always called Task !
    """ This task performs a Hi-M experiment on the Airyscan setup in epifluorescence configuration using the
     lumencor celesta lightsource.

    Config example pour copy-paste:
    HiMTask_confocal:
        module: 'HiM_task_Airyscan_Confocal'
        needsmodules:
            daq : 'daq_logic'
            roi: 'roi_logic'
            valves: 'valve_logic'
            pos: 'positioning_logic'
            flow: 'flowcontrol_logic'
        config:
            path_to_user_config: 'C:/Users/MFM/qudi_files/qudi_task_config_files/hi_m_task_AIRYSCAN_confocal.yml'
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
        print('Task {0} added!'.format(self.name))
        self.user_config_path = self.config['path_to_user_config']
        self.directory = None
        self.user_param_dict = {}
        self.sample_name = None
        self.probe_counter = None
        self.user_param_dict = {}
        self.logging = True
        self.save_path = None
        self.roi_list_path = None
        self.roi_names = []
        self.IN7_ZEN = self.config['IN7_ZEN']
        self.OUT7_ZEN = self.config['OUT7_ZEN']
        self.OUT8_ZEN = self.config['OUT8_ZEN']
        self.log_folder = None
        self.default_info_path = None
        self.status_dict_path = None
        self.log_path = None
        self.status_dict = {}
        self.start = None
        self.injections_path = None
        self.hybridization_list = []
        self.photobleaching_list = []
        self.buffer_dict = {}
        self.probe_list = []
        self.prefix = None
        self.probe_dict = {}

    def startTask(self):
        """ """
        self.start = time.time()

        # stop all interfering modes on GUIs and disable GUI actions
        self.ref['roi'].disable_tracking_mode()
        self.ref['roi'].disable_roi_actions()

        self.ref['valves'].disable_valve_positioning()
        self.ref['flow'].disable_flowcontrol_actions()
        self.ref['pos'].disable_positioning_actions()

        # control if experiment can be started : origin defined in position logic ?
        if not self.ref['pos'].origin:
            self.log.warning(
                'No position 1 defined for injections. Experiment can not be started. Please define position 1!')
            return

        # Send message that initialization is complete and the experiment is starting
        self.log.info('HiM experiment is starting ...')

        # set stage velocity
        self.ref['roi'].set_stage_velocity({'x': 1, 'y': 1})

        # read all user parameters from config
        self.load_user_parameters()

        # create the daq channels
        self.ref['daq'].initialize_digital_channel(self.OUT7_ZEN, 'input')
        self.ref['daq'].initialize_digital_channel(self.OUT8_ZEN, 'input')
        self.ref['daq'].initialize_digital_channel(self.IN7_ZEN, 'output')

        # indicate to the user the parameters he should use for zen configuration
        self.log.warning('############ ZEN PARAMETERS ############')
        self.log.warning('This task is compatible with experiment ZEN/HiM_confocal')
        self.log.warning('Number of acquisition loops in ZEN experiment designer : {}'.format(
            len(self.probe_list) * len(self.roi_names)))
        self.log.warning('Select the acquisition block and hit "Start Experiment"')
        self.log.warning('########################################')

        # wait for the trigger from ZEN indicating that the experiment is starting
        trigger = self.ref['daq'].read_di_channel(self.OUT7_ZEN, 1)
        while trigger == 0 and not self.aborted:
            sleep(.1)
            trigger = self.ref['daq'].read_di_channel(self.OUT7_ZEN, 1)

        # create a directory in which all the data will be saved
        self.directory = self.create_directory(self.save_path)

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
            self.ref['pos'].start_move_to_target(self.probe_list[self.probe_counter-1][0])
            while self.ref['pos'].moving is True:
                sleep(0.1)

            # disable again the move stage button
            self.ref['pos'].disable_positioning_actions()

        # keep in memory the position of the needle
        needle_pos = self.probe_list[self.probe_counter - 1][0]
        rt_injection = 0

        # --------------------------------------------------------------------------------------------------------------
        # Hybridization
        # --------------------------------------------------------------------------------------------------------------
        if not self.aborted:

            if self.logging:
                self.status_dict['process'] = 'Hybridization'
                write_status_dict_to_file(self.status_dict_path, self.status_dict)
                add_log_entry(self.log_path, self.probe_counter, 1, 'Started Hybridization', 'info')

            # position the valves for hybridization sequence
            self.ref['valves'].set_valve_position('b', 1)  # RT rinsing valve: inject probe
            self.ref['valves'].wait_for_idle()

            # iterate over the steps in the hybridization sequence
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

                    # for the Airyscan, the needle is connected to valve position 3. If this valve is called more than
                    # once, the needle will move to the next position. The procedure was added to make the DAPI
                    # injection easier.
                    print('Valve position : {}'.format(valve_pos))
                    if rt_injection == 0 and valve_pos == 3:
                        rt_injection += 1
                        needle_pos += 1
                    elif rt_injection > 0 and valve_pos == 3:
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

            # initialize roi counter and start the while loop over all the roi
            for roi in self.roi_names:

                if self.aborted:
                    break

                # define the name of the file according to the roi number and cycle
                scan_name = self.file_name(roi, probe_name)

                # move to roi ------------------------------------------------------------------------------------------
                self.ref['roi'].active_roi = None
                self.ref['roi'].set_active_roi(name=roi)
                self.ref['roi'].go_to_roi_xy()
                self.log.info('Moved to {}'.format(roi))
                self.ref['roi'].stage_wait_for_idle()

                if self.logging:
                    add_log_entry(self.log_path, self.probe_counter, 2, f'Moved to {roi}')

                # --------------------------------------------------------------------------------------------------------------
                # acquisition block (ZEN)
                # --------------------------------------------------------------------------------------------------------------

                # send trigger to ZEN to start the autofocus search and the acquisition
                sleep(5)
                self.ref['daq'].write_to_do_channel(self.IN7_ZEN, 1, 1)
                sleep(0.1)
                self.ref['daq'].write_to_do_channel(self.IN7_ZEN, 1, 0)

                # wait for ZEN trigger indicating the task is completed
                trigger = self.ref['daq'].read_di_channel(self.OUT8_ZEN, 1)
                while trigger == 0 and not self.aborted:
                    sleep(.1)
                    trigger = self.ref['daq'].read_di_channel(self.OUT8_ZEN, 1)

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
                        if not self.aborted:
                            time.sleep(30)
                    time.sleep(remainder)

                    self.log.info('Incubation time finished')

                if self.logging:
                    add_log_entry(self.log_path, self.probe_counter, 3, f'Finished injection {step + 1}')

            # rinse needle after photobleaching
            self.ref['valves'].set_valve_position('a', 3)  # Towards probe
            self.ref['valves'].wait_for_idle()
            self.ref['valves'].set_valve_position('b', 2)  # RT rinsing valve: rinse needle
            self.ref['valves'].wait_for_idle()
            self.ref['flow'].start_rinsing(60)
            time.sleep(61)   # block the program flow until rinsing is finished

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

        return self.probe_counter < len(self.probe_list)

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

        if self.aborted:

            if self.logging:
                add_log_entry(self.log_path, self.probe_counter, 0, 'Task was aborted.', level='warning')
            # add extra actions to end up in a proper state: pressure 0, end regulation loop, set valves to default
            # position .. (maybe not necessary because all those elements will still be done above)

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
            roi_list_path: 'pathstem/qudi_files/qudi_roi_lists/roilist_20210101_1128_23_123243.json'
            injections_path: 'pathstem/qudi_files/qudi_injection_parameters/injections_2021_01_01.yml'
            dapi_path: 'E:/imagedata/2021_01_01/001_HiM_MySample_dapi'
        """
        try:
            with open(self.user_config_path, 'r') as stream:
                self.user_param_dict = yaml.safe_load(stream)

                self.sample_name = self.user_param_dict['sample_name']
                self.save_path = self.user_param_dict['save_path']
                self.injections_path = self.user_param_dict['injections_path']

        except Exception as e:  # add the type of exception
            self.log.warning(f'Could not load user parameters for task {self.name}: {e}')

        # establish further user parameters derived from the given ones:
        # load rois from file and create a list
        self.ref['roi'].load_roi_list(self.roi_list_path)
        self.roi_names = self.ref['roi'].roi_names
        # injections
        self.load_injection_parameters()

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
        :param: str probe_name: string identifier of the current probe
        :return: str complete_path: such as directory/ROI_001/scan_001_004_ROI.tif (experiment nb. 001, ROI nb. 004)
        """

        roi_number_inv = roi_number.strip('ROI_') + '_ROI'  # for compatibility with analysis format
        file_name = f'scan_{self.prefix}_{probe_name}_{roi_number_inv}'
        return file_name

    @staticmethod
    def save_file_name(file, movie_name):
        """ Save the name of the movie by appending the file for each new acquisition.

        :param: str file: string identifier of the file where the data are saved
        :param: str movie_name: string identifier of the movie name (indicating the ROI and the probe)
        """
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
        metadata = {'Sample name': self.sample_name}

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

