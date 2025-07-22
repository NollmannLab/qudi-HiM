# -*- coding: utf-8 -*-
"""
Qudi-CBS

A module to control The Fly Arena odor system from Arduino uno.

An extension to Qudi.

@author: D. Guerin, JB. Fiche

Created on Tue May 28, 2024
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
import logging
import time
import numpy as np
from qtpy import QtCore
from core.configoption import ConfigOption
from core.connector import Connector
from logic.generic_logic import GenericLogic
from matplotlib import pyplot as plt
from scipy.stats import norm
from os import path

logging.basicConfig(filename='Fly Arena/logfile.log', filemode='w', level=logging.DEBUG)
logger = logging.getLogger(__name__)


# ======================================================================================================================
# Worker classes
# ======================================================================================================================

class WorkerSignals(QtCore.QObject):
    """ Defines the signals available from a running worker thread.

    For simplicity, contains all the signals for the different child classes of QRunnable
    (although each child class uses only one of these signals). """

    sigFinished = QtCore.Signal()
    sigRegulationWaitFinished = QtCore.Signal(float)  # parameter: target_flowrate
    # sigIntegrationIntervalFinished = QtCore.Signal(float, float)  # parameters: target_volume, integration_interval
    sigIntegrationIntervalFinished = QtCore.Signal(float)  # parameters : sampling_interval


class MeasurementWorker(QtCore.QRunnable):
    """ Worker thread to monitor the flow-rate every x seconds when measuring mode is on.

    The worker handles only the waiting time, and emits a signal that serves to trigger the update of indicators on GUI.
    """

    def __init__(self, *args, **kwargs):
        super(MeasurementWorker, self).__init__(*args, **kwargs)
        self.signals = WorkerSignals()

    @QtCore.Slot()
    def run(self):
        """ """
        time.sleep(1)  # 1 second as time constant
        self.signals.sigFinished.emit()


# ======================================================================================================================
# Logic class
# ======================================================================================================================
class OdorCircuitArduinoLogic(GenericLogic):

    arduino_uno = Connector(interface='Base')  # no specific arduino interface required
    MFC = Connector(interface='Base')  # no specific MFC interface required

    # declare signals for GUI
    sigUpdateFlowMeasurement = QtCore.Signal(list)
    sigDisableFlowActions = QtCore.Signal()
    sigEnableFlowActions = QtCore.Signal()
    sigUpdateValveState = QtCore.Signal(dict)
    sigTaskStartStop = QtCore.Signal(bool)
    sigTaskUpdateOdorGui = QtCore.Signal(bool, int, float)
    sigStartPrepOdor = QtCore.Signal()
    sigUpdatePrepTimer = QtCore.Signal(int)
    sigStartInjectOdor = QtCore.Signal()
    sigUpdateInjectTimer = QtCore.Signal(int)
    sigStopInjectOdor = QtCore.Signal()
    sigUpdateFlowRateDisplay = QtCore.Signal(list)

    # attributes
    measuring_flowrate = False
    time_since_start = 0
    calibrating_flowrate = False

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self.threadpool = QtCore.QThreadPool()
        self._MFC = None
        self._ard = None
        self.MFC_number: int = 0
        self.n_odors_available: int = 0
        self.odor_list: list = []
        self.valves_status: dict = {}
        self.calibration_saving_filename: str = ""
        self.calibration: dict = {}

    def on_activate(self):
        """
        Initialisation performed during activation of the module.
        """
        # connect logic to arduino (valve control) & MFC (air flow control)
        self._ard = self.arduino_uno()
        self._MFC = self.MFC()

        # initialize variables
        self.n_odors_available = self._ard.n_odor_available
        self.odor_list = self._ard.odor_list
        self.MFC_number = self._MFC.MFC_number
        self.valves_status = {'odor_1': 0,
                              'odor_2': 0,
                              'odor_3': 0,
                              'odor_4': 0,
                              'mixing': 0,
                              'switch_purge_arena': 0,
                              "3_way": 0,
                              "switch_quadrants": 0}

    def on_deactivate(self):
        """
        Perform required deactivation.
        """
        self.stop_air_flow()

# ----------------------------------------------------------------------------------------------------------------------
# Methods from GUI
# ----------------------------------------------------------------------------------------------------------------------

# Handling of the flow configuration  ----------------------------------------------------------------------------------
    def stop_air_flow(self):
        """ Stop all air flow in the arena and close the odor circuit - set all flow to zero
        @return (list) mfc_flow - list of the set-flow for each MFC
        """
        self.turn_all_MFC_off()
        self.close_odor_circuit()
        mfc_flow = [0, 0, 0, 0]
        return mfc_flow

    def start_air_flow(self, flow_set_point, config=1):
        """ Set the flow rate for all MFCs - this function is called from the GUI when selecting a configuration from
        the comboBox.
        @param: flow_set_point (float): indicate the flow expected in each quadrant of the arena
        @param: config (int) : indicate the arena configuration: 1 = 2 quadrants (1/3 and 2/4 are handled separately) -
        2 = 4 quadrants (all quadrants are identical)
        @return: flow_set_points (list) computed set-point values for each MFC
        """
        # check odor valves state - return True if at least one couple of inlet / outlet valves for the odors is OPEN
        is_odor = self.check_odor_valves()

        # check mixing valve state - return True if the mixing valve is OPEN
        is_mixing = self._ard.check_valve_state("mixing")

        # depending on the selected config, change the state of the 3way-valve
        if config == 1:
            self.change_valve_state("3_way", 0)
            flow_set_points = [flow_set_point, flow_set_point, 2 * flow_set_point, 2 * flow_set_point]
        elif config == 2:
            self.change_valve_state("3_way", 1)
            flow_set_points = [2 * flow_set_point, 2 * flow_set_point, 4 * flow_set_point, 0]
        else:
            flow_set_points = [0, 0, 0, 0]
            self.log.error("The indicated config does not exist (in logic - function start_air_flow")

        # if no odor are being prepared or injected, make sure the mixing valve is open (else, an error will occur for
        # the MFCs since it will be impossible to reach the set-point)
        if (not is_odor) and (not is_mixing):
            self.change_valve_state("mixing", 1)

        # start the MFCs
        for mfc in range(self.MFC_number):
            if flow_set_points[mfc] > 0:
                self._MFC.MFC_ON(mfc, flow_set_points[mfc])
            else:
                self._MFC.MFC_OFF(mfc)

        return flow_set_points

# Flowrate measurement loop --------------------------------------------------------------------------------------------
    def start_flow_measurement(self):
        """
        Start a continuous measurement of the flowrate.
        """
        self.measuring_flowrate = True
        # monitor the flowrate, using a worker thread
        worker = MeasurementWorker()
        worker.signals.sigFinished.connect(self.flow_measurement_loop)
        self.threadpool.start(worker)

    def flow_measurement_loop(self):
        """
        Continuous measuring of the flowrate at a defined sampling rate using a worker thread.
        """
        # launch signal to the GUI to update the flowchart
        flow_rates = self.read_average_flow()
        self.sigUpdateFlowMeasurement.emit(flow_rates)

        # if calibrating, save the datapoints
        if self.calibrating_flowrate:
            for n, key in enumerate(self.calibration.keys()):
                self.calibration[key].append(flow_rates[n])

        # if the conditions are checked, launch a new worker for the next measurement
        if self.measuring_flowrate or self.calibrating_flowrate:
            # enter a loop until measuring mode is switched off
            worker = MeasurementWorker()
            worker.signals.sigFinished.connect(self.flow_measurement_loop)
            self.threadpool.start(worker)

    def stop_flow_measurement(self):
        """
        Stops the measurement of flowrate.
        """
        self.measuring_flowrate = False
        self.calibrating_flowrate = False

# MFC calibration ------------------------------------------------------------------------------------------------------
    def start_flow_calibration(self, filename):
        """
        Start a calibration measurement of each MFC flowrate.
        """
        self.calibrating_flowrate = True
        self.calibration = {"MFC1": [], "MFC2": [], "MFC3": [], "MFC4": []}
        self.calibration_saving_filename = filename
        worker = MeasurementWorker()
        worker.signals.sigFinished.connect(self.flow_measurement_loop)
        self.threadpool.start(worker)

    def stop_flow_calibration(self):
        """
        Stop the calibration
        """
        # stop the flow rate loop
        self.measuring_flowrate = False
        self.calibrating_flowrate = False

        # plot
        fig, axes = plt.subplots(2, 2, figsize=(10, 18))
        colors = ['b', 'g', 'r', 'k']
        for n, key in enumerate(self.calibration.keys()):
            x, y = divmod(n, 2)
            self.plot_histogram_with_density(self.calibration[key], f'MFC_{n + 1}', colors[n], axes[x, y])

        fig.suptitle('Histograms and Density Curves for the MFCs')
        plt.savefig(self.calibration_saving_filename, dpi=150)

        # set MFCs to OFF
        self.stop_air_flow()

    @staticmethod
    def plot_histogram_with_density(data, label, color, ax):
        """
        Plot a histogram
        @param label : Name of the MFC
        @param color : color of the plot
        @param data : the mfc values
        @param ax : the place of the graph on the print
        """
        mean_value = np.mean(data)
        std_deviation = np.std(data)

        count, bins, ignored = ax.hist(data, bins='auto', alpha=0.5, rwidth=0.85, color=color,
                                       edgecolor='black', density=True, label=f'{label} histogram')

        bin_centers = 0.5 * (bins[1:] + bins[:-1])
        pdf = norm.pdf(bin_centers, mean_value, std_deviation)

        ax.plot(bin_centers, pdf, linestyle='dashed', linewidth=2, color=color, label=f'{label} density')

        ax.axvline(mean_value, color=color, linestyle='dashed', linewidth=1)
        ax.text(mean_value + 0.1 * (np.max(data) - np.min(data)), ax.get_ylim()[1] * 0.9,
                f'{label} Mean: {mean_value:.6f}', color=color)
        ax.text(mean_value + 0.1 * (np.max(data) - np.min(data)), ax.get_ylim()[1] * 0.85,
                f'{label} Std Dev: {std_deviation:.6f}', color=color)
        ax.set_xlabel('Flow (sL/min)')
        ax.set_ylabel('Density')
        ax.legend()

# Odor handling --------------------------------------------------------------------------------------------------------
    def prepare_odor(self, odor_number):
        """
        Prepare the specified odor by activating the corresponding valves. Note that when preparing an odor the
        following steps need to be checked:
        - open the valves associated to the selected odor
        - close the mixing valve
        - make sure the odor is sent to the purge (final valve in False state)
        @param odor_number: number of the odor you want to inject (not use yet)
        """
        self.change_valve_state("mixing", 0)
        self.change_valve_state(f"odor_{odor_number}", 1)
        self.change_valve_state("switch_purge_arena", 0)

    def inject_odor(self):
        """
        Inject the specified odor by activating the corresponding valves. Note that when injecting an odor, it is
        assumed that preparation was already running. Therefore, only the state of the "final" valve is changed
        (switching between purge & arena)
        """
        self.change_valve_state("switch_purge_arena", 1)

    def stop_odor(self, odor_number):
        """ Stop odor preparation or injection.
        @param odor_number: number of the odor you want to inject (not use yet)
        """
        self.change_valve_state("mixing", 1)
        self.change_valve_state(f"odor_{odor_number}", 0)
        self.change_valve_state("switch_purge_arena", 0)

    def switch_quadrants(self, state):
        """ Control the valve allowing switching between quadrants
        @param state: (int) indicate the state of the switch valve
        """
        self.change_valve_state("switch_quadrants", state)

# ----------------------------------------------------------------------------------------------------------------------
# Helper methods handling MFCs
# ----------------------------------------------------------------------------------------------------------------------
    def turn_all_MFC_off(self):
        """ Turn all MFCs OFF
        """
        for mfc in range(self.MFC_number):
            self._MFC.MFC_OFF(mfc)
            time.sleep(0.1)

    def read_average_flow(self):
        """ Read the average flow-rate for each MFC - note that the measurements are performed according to the order of
        the MFCs id/address indicated in the parameters file
        @return flow: (list) contains the mean value of the flow measured separately for each MFC
        """
        flow = []
        for n in range(self.MFC_number):
            flow.append(self._MFC.average_measure(n, 10))
        return flow

# ----------------------------------------------------------------------------------------------------------------------
# Helper methods handling Valves
# ----------------------------------------------------------------------------------------------------------------------
    def close_odor_circuit(self):
        """ Close all the valve in the odor circuit (odor, mixing and final valves).
        """
        self.change_valve_state("mixing", 0)
        for odor in range(self.n_odors_available):
            self.change_valve_state(f"odor_{odor + 1}", 0)

        self.change_valve_state("switch_purge_arena", 0)
        self.change_valve_state("3_way", 0)

    def check_odor_valves(self):
        """ Check if at least one pair of odor valves is OPEN
        @return: (bool) return True if a pair of valves is open. Else False.
        """
        for odor in range(self.n_odors_available):
            is_odor = self._ard.check_valve_state(f"odor_{odor + 1}")
            if is_odor:
                return True
        return False

    def change_valve_state(self, code, state):
        """ Send signal to GUI to update valve state
        @param code: (str) indicate the name of the selected valve in the dictionary
        @param state: (bool or int) indicate the state of the valve
        """
        err = self._ard.change_valve_state(code, int(state))
        if not err:
            self.valves_status[code] = int(state)
            self.sigUpdateValveState.emit(self.valves_status)

# ----------------------------------------------------------------------------------------------------------------------
# Helper methods for the tasks
# ----------------------------------------------------------------------------------------------------------------------

    def disable_odor_circuit_actions(self):
        """
        Safety when launching a task - to avoid conflict between task and actions handled by the GUI
        """
        self.sigTaskStartStop.emit(True)

    def update_odor_circuit_gui(self, init, odor, flow):
        """
        Launch signal to update the displays on the GUI based on task parameters
        @param init: (bool) indicate whether the task is at the initialization or closing step
        @param odor: (str) indicate the name of the odor selected for the training
        @param flow: (float) indicate the default MFC flow in each quadrant
        @return (int) indicate the index of the selected odor within the list of available odor
        """
        odor_idx = self.odor_list.index(odor) + 1
        self.sigTaskUpdateOdorGui.emit(init, odor_idx, flow)
        return odor_idx

    def enable_odor_circuit_actions(self):
        """
        Reset GUI to default state at the end of a task
        """
        self.sigTaskStartStop.emit(False)

    def launch_odor_preparation(self):
        """
        Launch odor preparation from logic
        """
        self.sigStartPrepOdor.emit()

    def update_odor_preparation_timer(self, dt):
        """
        Update the SpinBox associated to odor preparation
        @param dt: (int) elapsed time in s
        """
        self.sigUpdatePrepTimer.emit(dt)

    def launch_odor_injection(self):
        """
        Launch odor preparation from logic
        """
        self.sigStartInjectOdor.emit()

    def update_odor_injection_timer(self, dt):
        """
        Update the SpinBox associated to odor injection
        @param dt: (int) elapsed time in s
        """
        self.sigUpdateInjectTimer.emit(dt)

    def stop_odor_injection(self):
        """
        Stop odor preparation or injection from logic
        """
        self.sigStopInjectOdor.emit()

    def measure_MFC_flowrate(self):
        """
        Measure flow-rate from MFC
        """
        flow_rates = self.read_average_flow()
        self.sigUpdateFlowRateDisplay.emit(flow_rates)
