# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains a GUI for the odor circuit on the Fly Arena.

An extension to Qudi.

@author: D. Guerin, JB. Fiche

Created on Wen july 16, 2024
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
from PyQt5.QtCore import Qt
from qtpy import QtCore
from core.connector import Connector
from logic.generic_logic import GenericLogic
from core.configoption import ConfigOption
from glob import glob
from os import path
from time import sleep


class WorkerSignals(QtCore.QObject):
    """ Defines the signals available from a running worker thread """
    sigOptoStepFinished = QtCore.Signal(int, int)


class OptoWorker(QtCore.QRunnable):
    """ Worker thread to wait during an opto pulse. The worker handles only the waiting time.
    """
    def __init__(self, t, n_steps_on, n_steps_off):
        super(OptoWorker, self).__init__()
        self.signals = WorkerSignals()
        self.t = t
        self.n_steps_on = n_steps_on
        self.n_steps_off = n_steps_off

    @QtCore.Slot()
    def run(self):
        """ """
        sleep(self.t)
        self.signals.sigOptoStepFinished.emit(self.n_steps_on, self.n_steps_off)


class OptogeneticLogic(GenericLogic):
    # motor_FlyArena = Connector(interface='Base')  # no specific MFC interface required
    arduino_uno = Connector(interface='Base')  # no specific arduino interface required
    _patterns_folder_path = ConfigOption('patterns_path', missing='error')
    _bkg_pattern = ConfigOption('background_pattern', missing='error')

    # signals
    sigInitComboBox = QtCore.Signal(list, str)
    sigDisplayBlackBkg = QtCore.Signal()
    sigUpdatePattern = QtCore.Signal(str)
    sigDisplayPattern = QtCore.Signal()
    sigStimulation = QtCore.Signal(bool)
    sigTaskInitialization = QtCore.Signal(bool)
    sigTaskUpdateOptoGui = QtCore.Signal(int, float, float, int)

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self.threadpool = QtCore.QThreadPool()
        self._shutter_ard = None
        self.shutter_state: bool = False
        self.emitting: bool = False
        self.patterns_path: list = []
        self.patterns_list: list = []
        self.bkg_pattern_file: str = ""
        self.selected_pattern: str = ""
        self.tON: float = 0.0
        self.tOFF: float = 0.0
        self.stimulation_duration: int = 0.0
        self.stimulation_launched: bool = False

    def on_activate(self):
        self._shutter_ard = self.arduino_uno()
        self.initialize_patterns_list()

    def on_deactivate(self):
        """
        Perform required deactivation.
        """
        pass

    # ------------------------------------------------------------------------------------------------------------------
    # Methods handling GUI value change
    # ------------------------------------------------------------------------------------------------------------------
    @QtCore.Slot(str)
    def update_pattern(self, filename):
        """
        Update the pattern for the GUI (but do not display it)
        @param filename: (str) indicate the filename associated to the selected pattern
        """
        self.selected_pattern = path.join(self._patterns_folder_path, filename)
        self.sigUpdatePattern.emit(self.selected_pattern)
        if self.shutter_state and self.emitting:
            self.sigDisplayPattern.emit()

    @QtCore.Slot(float)
    def update_tON(self, t):
        """
        Update t_on, the time of a stimulation pulse (in s)
        @param t: (float) duration of a single duration pulse
        """
        self.tON = t

    @QtCore.Slot(float)
    def update_tOFF(self, t):
        """
        Update t_off, the time between two successive stimulation pulses (in s)
        @param t: (float) duration of a pause between two successive simulations
        """
        self.tOFF = t

    @QtCore.Slot(float)
    def update_stimulation_length(self, t):
        """
        update stimulation_duration, the total time of the stimulation sequence (in s)
        @param t: (int) total duration
        """
        self.stimulation_duration = t

    # ------------------------------------------------------------------------------------------------------------------
    # Methods handling image display
    # ------------------------------------------------------------------------------------------------------------------

    def initialize_patterns_list(self):
        """
        Initialize the list of patterns available for the projector & optogenetics simulations
        @return: list of patterns available as a list of paths to all the PNG files found in the folder.
        """
        patterns = glob(path.join(self._patterns_folder_path, '*.PNG'))
        self.patterns_path = sorted(patterns)
        for file in patterns:
            filename = path.basename(file)
            if filename == self._bkg_pattern:
                self.bkg_pattern_file = file
            else:
                self.patterns_list.append(filename)

    def display_off(self):
        """
        Display the 'black' image
        """
        self.sigDisplayBlackBkg.emit()
        self.close_shutter()
        self.emitting = False

    def display_on(self):
        """
        Display the current pattern (not the background)
        """
        self.open_shutter()
        self.sigDisplayPattern.emit()
        self.emitting = True

    def launch_stimulation(self):
        """
        Launch a stimulation cycle
        """
        self.sigDisplayBlackBkg.emit()
        self.open_shutter()
        self.stimulation(0, 0)
        self.stimulation_launched = True

    def stimulation(self, n_step_ON, n_step_OFF):
        dt = self.tON * n_step_ON + self.tOFF * n_step_OFF
        if dt < self.stimulation_duration:
            if n_step_ON == n_step_OFF:
                n_step_ON += 1
                self.sigStimulation.emit(True)
                worker = OptoWorker(self.tON, n_step_ON, n_step_OFF)
            else:
                n_step_OFF += 1
                self.sigStimulation.emit(False)
                worker = OptoWorker(self.tOFF, n_step_ON, n_step_OFF)

            worker.signals.sigOptoStepFinished.connect(self.stimulation)
            self.threadpool.start(worker)
        else:
            self.stop_stimulation()

    def stop_stimulation(self):
        """
        stop the stimulation sequence
        """
        self.close_shutter()
        self.sigDisplayBlackBkg.emit()
        self.stimulation_launched = False

    # ----------------------------------------------------------------------------------------------------------------------
    # Methods handling the shutter
    # ----------------------------------------------------------------------------------------------------------------------
    def send_trigger_to_shutter(self):
        """
        Send trigger to the shutter to open or close it (send pattern to the arena)
        """
        self._shutter_ard.shutter()
        self.shutter_state = not self.shutter_state
        return self.shutter_state

    def open_shutter(self):
        """ Open the shutter
        """
        if not self.shutter_state:
            self.send_trigger_to_shutter()

    def close_shutter(self):
        """ Close the shutter
        """
        if self.shutter_state:
            self.send_trigger_to_shutter()

    # ------------------------------------------------------------------------------------------------------------------
    # Helper methods for the tasks
    # ------------------------------------------------------------------------------------------------------------------

    def disable_optogenetic_actions(self):
        """
        Safety when launching a task - to avoid conflict between task and actions handled by the GUI
        """
        self.sigTaskInitialization.emit(True)

    def enable_optogenetic_actions(self):
        """
        Safety when launching a task - to avoid conflict between task and actions handled by the GUI
        """
        self.sigTaskInitialization.emit(False)

    def update_opto_gui(self, stimulation_duration, t_on, t_off, pattern):
        """
        Update GUI displays
        @param stimulation_duration: (int) indicate the duration of a stimulation sequence (in s)
        @param t_on: (float) indicate the duration of a stimulation flash (in s)
        @param t_off: (float) indicate the duration separating two consecutive stimulation flashes (in s)
        @param pattern: (str) indicate the name of the selected stimulation pattern
        """
        pattern_idx = self.patterns_list.index(pattern)
        self.tON = t_on
        self.tOFF = t_off
        self.stimulation_duration = stimulation_duration
        self.sigTaskUpdateOptoGui.emit(stimulation_duration, t_on, t_off, pattern_idx)

