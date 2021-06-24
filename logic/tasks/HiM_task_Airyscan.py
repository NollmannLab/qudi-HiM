# -*- coding: utf-8 -*-
"""
Created on Wed March 30 2021

@author: fbarho

This file is an extension to Qudi software
obtained from <https://github.com/Ulm-IQO/qudi/>

Hi-M Experiment for the RAMM setup

Config example pour copy-paste:
    HiMTask:
        module: 'HiM_task_Airyscan'
        needsmodules:
            roi: 'roi_logic'
            valves: 'valve_logic'
            pos: 'positioning_logic'
            flow: 'flowcontrol_logic'
        config:
            path_to_user_config: 'C:/Users/MFM/qudi_data/qudi_task_config_files/hi_m_task_AIRYSCAN.yaml'
"""
import yaml
import numpy as np
import pandas as pd
import os
import time
from datetime import datetime
from tqdm import tqdm
from logic.generic_task import InterruptableTask


class Task(InterruptableTask):  # do not change the name of the class. it is always called Task !
    """ This task iterates over all roi given in a file and does an acquisition of a series of planes in z direction
    using a sequence of lightsources for each plane, for each roi.
    """
    # ==================================================================================================================
    # Generic Task methods
    # ==================================================================================================================

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        print('Task {0} added!'.format(self.name))
        self.user_config_path = self.config['path_to_user_config']
        # for logging:
        # self.status_dict_path = 'Z:/DATA/JB/hi_m_log/current_status.yaml'    # maybe read from config
        # self.log_path = 'Z:/DATA/JB/hi_m_log/log_hi_m.csv'   # maybe read from config
        self.logging = False

    def startTask(self):
        """ """
        self.start = time.time()
        if self.logging:
            # initialize the status dict yaml file
            self.status_dict = {'cycle_no': None, 'process': None, 'start_time': self.start, 'cycle_start_time': None}
            write_status_dict_to_file(self.status_dict_path, self.status_dict)
            # initialize the log file
            log = {'timestamp': [], 'cycle_no': [], 'process': [], 'event': [], 'level': []}
            df = pd.DataFrame(log, columns=['timestamp', 'cycle_no', 'process', 'event', 'level'])
            df.to_csv(self.log_path, index=False, header=True)

        self.log.info('started Task')
        # stop all interfering modes on GUIs and disable GUI actions
        self.ref['roi'].disable_tracking_mode()
        self.ref['roi'].disable_roi_actions()

        self.ref['valves'].disable_valve_positioning()
        self.ref['flow'].disable_flowcontrol_actions()
        self.ref['pos'].disable_positioning_actions()

        # control if experiment can be started : origin defined in position logic ?
        if not self.ref['pos'].origin:
            self.log.warning('No position 1 defined for injections. Experiment can not be started. Please define position 1!')
            return

        # set stage velocity
        self.ref['roi'].set_stage_velocity({'x': 1, 'y': 1})

        # read all user parameters from config
        self.load_user_parameters()

        # create a directory in which all the data will be saved
        self.directory = self.create_directory(self.save_path)

        # initialize a counter to iterate over the number of probes to inject
        self.probe_counter = 0

    def runTaskStep(self):
        """ Implement one work step of your task here.
        @return bool: True if the task should continue running, False if it should finish.
        """
        # go directly to cleanupTask if position 1 is not defined
        if not self.ref['pos'].origin:
            return False

        if not self.aborted:
            now = time.time()
            # info message
            self.probe_counter += 1
            self.log.info(f'Probe number {self.probe_counter}: {self.probe_list[self.probe_counter - 1][1]}')
            if self.logging:
                self.status_dict['cycle_no'] = self.probe_counter
                self.status_dict['cycle_start_time'] = now
                write_status_dict_to_file(self.status_dict_path, self.status_dict)
                add_log_entry(self.log_path, self.probe_counter, 0, f'Started cycle {self.probe_counter}', 'info')

            # position the needle in the probe
            self.ref['pos'].start_move_to_target(self.probe_list[self.probe_counter-1][0])
            self.ref['pos'].disable_positioning_actions()  # to disable again the move stage button

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

                    # pressure regulation
                    self.ref['flow'].set_pressure(0.0)  # as initial value
                    self.ref['flow'].start_pressure_regulation_loop(self.hybridization_list[step]['flowrate'])
                    # start counting the volume of buffer or probe
                    sampling_interval = 1  # in seconds
                    self.ref['flow'].start_volume_measurement(self.hybridization_list[step]['volume'],
                                                              sampling_interval)

                    ready = self.ref['flow'].target_volume_reached
                    while not ready:
                        time.sleep(2)
                        ready = self.ref['flow'].target_volume_reached
                        if self.aborted:
                            ready = True
                    self.ref['flow'].stop_pressure_regulation_loop()
                    time.sleep(2)  # waiting time to wait until last regulation step is finished, afterwards reset pressure to 0
                    self.ref['flow'].set_pressure(0.0)

                else:  # an incubation step
                    t = self.hybridization_list[step]['time']
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
                    add_log_entry(self.log_path, self.probe_counter, 1, f'Finished injection {step + 1}')

            # set valves to default positions
            self.ref['valves'].set_valve_position('a', 1)  # 8 way valve
            self.ref['valves'].wait_for_idle()
            self.ref['valves'].set_valve_position('b', 1)  # RT rinsing valve: Rinse needle
            self.ref['valves'].wait_for_idle()

            if self.logging:
                add_log_entry(self.log_path, self.probe_counter, 1, 'Finished Hybridization', 'info')
        # Hybridization finished ---------------------------------------------------------------------------------------

        # --------------------------------------------------------------------------------------------------------------
        # Imaging for all ROI
        # --------------------------------------------------------------------------------------------------------------
        if not self.aborted:
            if self.logging:
                self.status_dict['process'] = 'Imaging'
                write_status_dict_to_file(self.status_dict_path, self.status_dict)
                add_log_entry(self.log_path, self.probe_counter, 2, 'Started Imaging', 'info')

            for item in self.roi_names:
                if self.aborted:
                    break

                # create the save path for each roi --------------------------------------------------------------------
                cur_save_path = self.get_complete_path(self.directory, item, self.probe_list[self.probe_counter - 1][1])

                # move to roi ------------------------------------------------------------------------------------------
                self.ref['roi'].active_roi = None
                self.ref['roi'].set_active_roi(name=item)
                self.ref['roi'].go_to_roi_xy()
                self.log.info('Moved to {}'.format(item))
                self.ref['roi'].stage_wait_for_idle()

                if self.logging:
                    add_log_entry(self.log_path, self.probe_counter, 2, f'Moved to {item}')

                # imaging sequence -------------------------------------------------------------------------------------
                print(f'{item}: performing z stack..')
                time.sleep(1)
                # add here whatever is needed for imaging

            # go back to first ROI (to avoid a long displacement just before restarting imaging)
            self.ref['roi'].set_active_roi(name=self.roi_names[0])
            self.ref['roi'].go_to_roi_xy()

            if self.logging:
                add_log_entry(self.log_path, self.probe_counter, 2, 'Finished Imaging', 'info')
        # Imaging (for all ROIs) finished ------------------------------------------------------------------------------

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
                    self.ref['flow'].set_pressure(0.0)  # as initial value
                    self.ref['flow'].start_pressure_regulation_loop(self.photobleaching_list[step]['flowrate'])
                    # start counting the volume of buffer or probe
                    sampling_interval = 1 # in seconds
                    self.ref['flow'].start_volume_measurement(self.photobleaching_list[step]['volume'],
                                                              sampling_interval)

                    ready = self.ref['flow'].target_volume_reached
                    while not ready:
                        time.sleep(2)
                        ready = self.ref['flow'].target_volume_reached
                        if self.aborted:
                            ready = True
                    self.ref['flow'].stop_pressure_regulation_loop()
                    time.sleep(2)  # waiting time to wait until last regulation step is finished, afterwards reset pressure to 0
                    self.ref['flow'].set_pressure(0.0)
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
            time.sleep(60)   # block the program flow until rinsing is finished

            # set valves to default positions
            self.ref['valves'].set_valve_position('a', 1)  # 8 way valve
            self.ref['valves'].wait_for_idle()
            self.ref['valves'].set_valve_position('b', 1)  # RT rinsing valve: Rinse needle
            self.ref['valves'].wait_for_idle()

            if self.logging:
                add_log_entry(self.log_path, self.probe_counter, 3, 'Finished Photobleaching', 'info')
        # Photobleaching finished --------------------------------------------------------------------------------------

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
            self.status_dict = {}
            write_status_dict_to_file(self.status_dict_path, self.status_dict)

        if self.aborted:
            if self.logging:
                add_log_entry(self.log_path, self.probe_counter, 0, 'Task was aborted.', level='warning')
            # add extra actions to end up in a proper state: pressure 0, end regulation loop, set valves to default position .. (maybe not necessary because all those elements will still be done above)

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
        try:
            with open(self.user_config_path, 'r') as stream:
                self.user_param_dict = yaml.safe_load(stream)

                self.sample_name = self.user_param_dict['sample_name']
                self.save_path = self.user_param_dict['save_path']
                self.file_format = self.user_param_dict['file_format']
                self.roi_list_path = self.user_param_dict['roi_list_path']
                self.injections_path = self.user_param_dict['injections_path']

        except Exception as e:  # add the type of exception
            self.log.warning(f'Could not load user parameters for task {self.name}: {e}')

        # establish further user parameters derived from the given ones:
        # load rois from file and create a list ------------------------------------------------------------------------
        self.ref['roi'].load_roi_list(self.roi_list_path)
        self.roi_names = self.ref['roi'].roi_names

        # injections ---------------------------------------------------------------------------------------------------
        self.load_injection_parameters()

    def load_injection_parameters(self):
        """ """
        try:
            with open(self.injections_path, 'r') as stream:
                documents = yaml.safe_load(stream)  # yaml.full_load when yaml package updated
                buffer_dict = documents['buffer']
                probe_dict = documents['probes']
                self.hybridization_list = documents['hybridization list']
                self.photobleaching_list = documents['photobleaching list']

            # invert the buffer dict to address the valve by the product name as key
            self.buffer_dict = dict([(value, key) for key, value in buffer_dict.items()])
            # create a list out of probe_dict and order by ascending position (for example: probes in pos 2, 5, 6, 9, 10 is ok but not 10, 2, 5, 6, 9)
            self.probe_list = sorted(probe_dict.items())  # list of tuples, such as [(1, 'RT1'), (2, 'RT2')]

        except Exception as e:
            self.log.warning(f'Could not load hybridization sequence for task {self.name}: {e}')

    # ------------------------------------------------------------------------------------------------------------------
    # file path handling
    # ------------------------------------------------------------------------------------------------------------------
    def create_directory(self, path_stem):
        """ Create the directory (based on path_stem given as user parameter),
        in which the folders for the ROI will be created
        Example: path_stem/YYYY_MM_DD/001_HiM_samplename
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
        dir_list = [folder for folder in os.listdir(path_stem_with_date) if os.path.isdir(os.path.join(path_stem_with_date, folder))]
        number_dirs = len(dir_list)

        prefix=str(number_dirs+1).zfill(3)
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
        path = os.path.join(directory, roi_number, probe_number)

        if not os.path.exists(path):
            try:
                os.makedirs(path)  # recursive creation of all directories on the path
            except Exception as e:
                self.log.error('Error {0}'.format(e))

        file_name = f'scan_{self.prefix}_{probe_number}_{roi_number}.{self.file_format}'

        complete_path = os.path.join(path, file_name)
        return complete_path


# ----------------------------------------------------------------------------------------------------------------------
# helper functions for bokeh app display  (put this in a separate file later and import)
# ----------------------------------------------------------------------------------------------------------------------


def write_status_dict_to_file(path, status_dict):
    """ Write the current status dictionary to a yaml file.
    :param: dict status_dict: dictionary containing a summary describing the current state of the experiment.
    """
    with open(path, 'w') as outfile:
        yaml.safe_dump(status_dict, outfile, default_flow_style=False)


def add_log_entry(path, cycle, process, event, level='info'):
    """ Append a log entry to the log.csv file.
    :param: str path: complete path to the log file
    :param: int cycle: number of the current cycle, or 0 if not in a cycle
    :param int process: number of the process, encoded using Hybridization: 1, Imaging: 2, Photobleaching: 3
    :param str event: message describing the logged event
    :param: str level: 'info', 'warning', 'error'
    """
    timestamp = datetime.now()
    entry = {'timestamp': [timestamp], 'cycle_no': [cycle], 'process': [process], 'event': [event], 'level': [level]}
    df_line = pd.DataFrame(entry, columns=['timestamp', 'cycle_no', 'process', 'event', 'level'])
    with open(path, 'a') as file:
        df_line.to_csv(file, index=False, header=False)