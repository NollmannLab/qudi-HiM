# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains the logic for the experiment configurator for the Fly Arena.

An extension to Qudi.

@author: JB Fiche (from original by F. Barho)

Created on Mon Jul 14 2025
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
import yaml
from qtpy import QtCore
from logic.generic_logic import GenericLogic
from core.configoption import ConfigOption
from core.connector import Connector


# ======================================================================================================================
# Logic class
# ======================================================================================================================

class ExpConfigLogic(GenericLogic):
    """
    Class containing the logic for the definition of a configuration file for an experiment

    Example config for copy-paste:

    exp_config_logic:
        module.Class: 'experiment_configurator_logic.ExpConfigLogic'
        experiments:
            - 'Multichannel imaging'
            - 'Multichannel scan PALM'
            - 'Dummy experiment'
        supported fileformats:
            - 'tif'
            - 'fits'
        default path: '/home/barho'
        connect:
            camera_logic: 'camera_logic'
            laser_logic: 'lasercontrol_logic'
            filterwheel_logic: 'filterwheel_logic'
    """
    # define connectors to logic modules
    odor_logic = Connector(interface='OdorCircuitArduinoLogic')
    opto_logic = Connector(interface='OptogeneticLogic')

    # signals
    sigConfigDictUpdated = QtCore.Signal()
    sigImagingListChanged = QtCore.Signal()
    sigConfigLoaded = QtCore.Signal()
    sigUpdateListModel = QtCore.Signal(int)

    # config options
    experiments = ConfigOption('experiments')
    config_dict = {}

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self._odor_logic = None
        self._opto_logic = None
        self.odor: list = []
        self.patterns: list = []

    def on_activate(self):
        """
        Initialisation performed during activation of the module.
        """
        self._odor_logic = self.odor_logic()
        self._opto_logic = self.opto_logic()

        # prepare the items that will be displayed in the ComboBoxes on the GUI
        self.odor = self._odor_logic.odor_list
        self.patterns = self._opto_logic.patterns_list

        # add an additional entry to the experiment selector combobox with placeholder text
        self.experiments.insert(0, 'Select your experiment..')

        self.init_default_config_dict()

    def on_deactivate(self):
        """
        Perform required deactivation.
        """
        pass

# ----------------------------------------------------------------------------------------------------------------------
# Methods to load / save experiment config files
# ----------------------------------------------------------------------------------------------------------------------

    def init_default_config_dict(self):
        """ Initialize the entries of the dictionary with some default values,
        to set entries to the form displayed on the GUI on startup.
        NB : since the following entries are defined by default, they will not be mandatory for saving the form.
        """

        self.config_dict['training_cycles'] = 10
        self.config_dict['resting_time'] = 15
        self.config_dict['training_duration'] = 60
        self.config_dict['odor'] = ""
        self.config_dict['air_flow'] = 0.1
        self.config_dict['prep_time'] = 10
        self.config_dict['patterns'] = ""
        self.config_dict['t_on'] = 0.2
        self.config_dict['t_off'] = 0.2
        self.config_dict['saving_path'] = r"E:\DATA"

        # add here further dictionary entries that need initialization
        self.sigConfigDictUpdated.emit()

    def save_to_exp_config_file(self, path, experiment, filename=None):
        """ Saves the current config_dict to a yml file.

        @param: str path: path to directory where the config file is saved
        @param: str experiment: name of the experiment that shall be saved.
                        For clarity, always append the name of the experimental setup for which the task is destinated.
        @param: str filename: name of the config file including the suffix .yml. Default is None.
                            filename must only be given when using save copy of config file under a non-default name.

        @return: None
        """
        if not os.path.exists(path):
            try:
                os.makedirs(path)  # recursive creation of all directories on the path
            except Exception as e:
                self.log.error(f'Error {e}.')

        config_dict = {}
        print(f'Experiment = {experiment}')

        try:
            if experiment == 'Long-term training':
                if not filename:
                    filename = 'long_term_training_FlyArena.yml'
                keys_to_extract = ['sample_name', 'training_cycles', 'resting_time', 'training_duration', 'odor',
                                   'air_flow', 'prep_time', 'patterns', 't_on', 't_off', 'saving_path']
                config_dict = {key: self.config_dict[key] for key in keys_to_extract}

            # add here all additional experiments and select the relevant keys
            else:
                pass

        except KeyError as e:
            self.log.warning(f'Experiment configuration not saved. Missing information {e}.')
            return

        config_dict['experiment'] = experiment
        complete_path = os.path.join(path, filename)
        print(complete_path)
        with open(complete_path, 'w') as file:
            yaml.safe_dump(config_dict, file, default_flow_style=False)
        self.log.info('Saved experiment configuration to {}'.format(complete_path))

    def load_config_file(self, path):
        """ Loads a configuration file and sets the entries of the config_dict accordingly

        :param: str path: complete path to an experiment configuration file
        :return: None
        """
        with open(path, 'r') as stream:
            data_dict = yaml.safe_load(stream)

        self.config_dict = data_dict

        # safety check: is at least the key 'experiment' contained in the file ?
        if 'experiment' not in self.config_dict.keys():
            self.log.warning('The loaded files does not contain necessary parameters. Configuration not loaded.')
            return
        else:
            self.log.info(f'Configuration loaded from {path}')

        self.sigConfigLoaded.emit()

# ----------------------------------------------------------------------------------------------------------------------
# Methods to update dictionary entries on change of associated GUI element
# ----------------------------------------------------------------------------------------------------------------------

    @QtCore.Slot(str)
    def update_sample_name(self, name):
        """ Updates the dictionary entry 'sample_name'
        @param: (str) name: sample name
        """
        self.config_dict['sample_name'] = name
        self.sigConfigDictUpdated.emit()

    @QtCore.Slot(int)
    def update_training_cycles(self, n_cycles):
        """ Updates the dictionary entry 'training_cycles'
        @param: (int) n_cycles: number of training cycles
        """
        self.config_dict['training_cycles'] = n_cycles
        self.sigConfigDictUpdated.emit()

    @QtCore.Slot(int)
    def update_resting_time(self, time):
        """ Updates the dictionary entry 'resting_time' indicating the duration between two stimulations.
        @param: (int) time: indicate the duration time (min) between two stimulations
        """
        self.config_dict['resting_time'] = time
        self.sigConfigDictUpdated.emit()

    @QtCore.Slot(int)
    def update_training_duration(self, time):
        """ Updates the dictionary entry 'training_duration' indicating the duration of a stimulation (in s).
        @param: (int) time: indicate the stimulation time (s)
        """
        self.config_dict['training_duration'] = time
        self.sigConfigDictUpdated.emit()

    @QtCore.Slot(str)
    def update_odor(self, odor):
        """ Updates the dictionary entry 'odor'.
        @param: (str) odor: indicate which odor will be injected
        """
        self.config_dict['odor'] = odor
        self.sigConfigDictUpdated.emit()

    @QtCore.Slot(float)
    def update_air_flow(self, flow):
        """ Updates the dictionary entry 'air_flow'.
        @param: (float) flow: indicate the air-flow in sL/min in each quadrant
        """
        self.config_dict['air_flow'] = flow
        self.sigConfigDictUpdated.emit()

    @QtCore.Slot(int)
    def update_prep_time(self, time):
        """ Updates the dictionary entry 'prep_time' indicating how long the preparation of odor will last before
        injection in the chamber.
        @param: (int) time: indicate the preparation time (s)
        """
        self.config_dict['prep_time'] = time
        self.sigConfigDictUpdated.emit()

    @QtCore.Slot(str)
    def update_pattern(self, pattern):
        """ Updates the dictionary entry 'patterns' indicating which pattern will be used for the optogenetics
        stimulation
        @param: (str) pattern: indicate which pattern is selected
        """
        self.config_dict['patterns'] = pattern
        self.sigConfigDictUpdated.emit()

    @QtCore.Slot(float)
    def update_ton(self, time):
        """ Updates the dictionary entry 't_on' indicating the duration of an opto flash / stimulus
        @param: (int) time: indicate the duration in s of an opto flash
        """
        self.config_dict['t_on'] = time
        self.sigConfigDictUpdated.emit()

    @QtCore.Slot(float)
    def update_toff(self, time):
        """ Updates the dictionary entry 't_off' indicating the duration of an opto flash / stimulus
        @param: (int) time: indicate the duration in s between two consecutive opto stimulations
        """
        self.config_dict['t_off'] = time
        self.sigConfigDictUpdated.emit()

    @QtCore.Slot(str)
    def update_saving_path(self, path):
        """ Updates the dictionary entry 'saving_path' indicating where to save the logs
        @param: (str) path: indicate the path to the folder where to save the logs
        """
        self.config_dict['saving_path'] = path
        self.sigConfigDictUpdated.emit()
