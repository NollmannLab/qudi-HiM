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
from qtpy import QtCore
from core.configoption import ConfigOption
from core.connector import Connector
from logic.generic_logic import GenericLogic

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
    sigChangeValveState = QtCore.Signal(dict)

    # attributes
    measuring_flowrate = False
    time_since_start = 0

    # _valve_odor_1_in = ConfigOption('valve_odor_1_in', 3)
    # _valve_odor_2_in = ConfigOption('valve_odor_2_in', 12)
    # _valve_odor_3_in = ConfigOption('valve_odor_3_in', 11)
    # _valve_odor_4_in = ConfigOption('valve_odor_4_in', 10)
    # _valve_odor_1_out = ConfigOption('valve_odor_1_in', 7)
    # _valve_odor_2_out = ConfigOption('valve_odor_2_in', 6)
    # _valve_odor_3_out = ConfigOption('valve_odor_3_in', 5)
    # _valve_odor_4_out = ConfigOption('valve_odor_4_in', 4)
    # _mixing_valve = ConfigOption('mixing_valve', 9)
    # _final_valve = ConfigOption('final_valve', 8)
    #
    # _MFC_1 = ConfigOption('MFC_1', 0)
    # _MFC_2 = ConfigOption('MFC_2', 1)
    # _MFC_3_purge = ConfigOption('MFC_purge', 2)
    # _MFC_4 = ConfigOption('MFC_4', 3)
    #
    # _MFC_purge_flow = ConfigOption('MFC_purge_flow', 0.5)
    # _MFC_1_flow = ConfigOption('MFC_1_flow', 0.25)
    # _MFC_2_flow = ConfigOption('MFC_2_flow', 0.25)

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self.threadpool = QtCore.QThreadPool()
        self._MFC = None
        self._ard = None
        self.MFC_number: int = 0
        self.n_odors_available: int = 0
        self.valves_status: dict = {}

    def on_activate(self):
        """
        Initialisation performed during activation of the module.
        """
        # connect logic to arduino (valve control) & MFC (air flow control)
        self._ard = self.arduino_uno()
        self._MFC = self.MFC()

        # initialize variables
        self.n_odors_available = self._ard.n_odor_available
        self.MFC_number = self._MFC.MFC_number
        self.valves_status = {'odor_1': 0,
                              'odor_2': 0,
                              'odor_3': 0,
                              'odor_4': 0,
                              'mixing': 0,
                              'switch_purge_arena': 0}

        # initialize connection to GUI

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
        """ Stop all air flow in the arena and close the odor circuit
        """
        self.turn_all_MFC_off()
        self.close_odor_circuit()

    def start_air_flow(self, flow_set_points):
        """ Set the flow rate for all MFCs - this function is called from the GUI when selecting a configuration from
        the comboBox.
        @param: flow_set_points (list): indicate the flow set_points for all MFCs
        @return:
        """
        # check odor valves state - return True if at least one couple of inlet / outlet valves for the odors is OPEN
        is_odor = self.check_odor_valves()

        # check mixing valve state - return True if the mixing valve is OPEN
        is_mixing = self._ard.check_valve_state("mixing")

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
        flow_rates = self.read_average_flow()
        self.sigUpdateFlowMeasurement.emit(flow_rates)
        if self.measuring_flowrate:
            # enter a loop until measuring mode is switched off
            worker = MeasurementWorker()
            worker.signals.sigFinished.connect(self.flow_measurement_loop)
            self.threadpool.start(worker)

    def stop_flow_measurement(self):
        """
        Stops the measurement of flowrate.
        """
        self.measuring_flowrate = False

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

# ----------------------------------------------------------------------------------------------------------------------
# Helper methods handling MFCs
# ----------------------------------------------------------------------------------------------------------------------
    def turn_all_MFC_off(self):
        """ Turn all MFCs OFF
        """
        for mfc in range(self.MFC_number):
            self._MFC.MFC_OFF(mfc)
            time.sleep(0.3)

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
        @param state: (bool) indicate True to open the valve, False to close it
        """
        err = self._ard.change_valve_state(code, state)
        if not err:
            self.valves_status[code] = state
            self.sigChangeValveState.emit(self.valves_status)














    def valve(self, pin, state):
        """
        Open only 1 valve
        @param pin: Number of the pin to activate (2 to 12)
        @param state: (bool) ON / OFF state of the valve (1 : odor circuit on ; 0 : odor circuit off)
        input example: ' 'state' '
        """
        if state == 1:
            self._ard.pin_on(pin)
        elif state == 0:
            self._ard.pin_off(pin)

    # def prepare_odor(self, odor_number):
    #     """
    #     Prepare the specified odor by activating the corresponding valves.
    #     @param odor_number: number of the odor you want to inject (not use yet)
    #     input example: 'odor_number'
    #     """
    #     if odor_number == 1:
    #         self.valve(self._valve_odor_1_in, 1)
    #         self.valve(self._valve_odor_1_out, 1)
    #     elif odor_number == 2:
    #         self.valve(self._valve_odor_2_in, 1)
    #         self.valve(self._valve_odor_2_out, 1)
    #     elif odor_number == 3:
    #         self.valve(self._valve_odor_3_in, 1)
    #         self.valve(self._valve_odor_3_out, 1)
    #     elif odor_number == 4:
    #         self.valve(self._valve_odor_4_in, 1)
    #         self.valve(self._valve_odor_4_out, 1)
    #     else:
    #         logger.warning('4 odor only')

    def flush_odor(self):
        """
        Close all the valves that need to be closed
        """
        self.valve(self._mixing_valve, 1)
        self.valve(self._final_valve, 0)
        self.valve(self._valve_odor_1_in, 0)
        self.valve(self._valve_odor_1_out, 0)
        self.valve(self._valve_odor_2_in, 0)
        self.valve(self._valve_odor_2_out, 0)
        self.valve(self._valve_odor_3_in, 0)
        self.valve(self._valve_odor_3_out, 0)
        self.valve(self._valve_odor_4_in, 0)

        print('Odor circuit off')

    def turn_MFC_on(self, flow_setpoints):
        """
        Open the MFCs
        @param flow_setpoints : list of the setpoints for each MFC
        """
        for n_MFC, flow in enumerate(flow_setpoints):
            self._MFC.MFC_ON(n_MFC, flow)

    # def close_air(self):
    #     """
    #     Close the MFCs
    #     """
    #     self._MFC.MFC_OFF(self._MFC_1)
    #     time.sleep(0.3)
    #     self._MFC.MFC_OFF(self._MFC_2)
    #     time.sleep(0.3)
    #     self._MFC.MFC_OFF(self._MFC_3_purge)
    #     time.sleep(0.3)
    #     self._MFC.MFC_OFF(self._MFC_4)




    # ----------------------------------------------------------------------------------------------------------------------
    # Methods to handle the user interface state
    # ----------------------------------------------------------------------------------------------------------------------
    def disable_flowcontrol_actions(self):
        """
        This method provides a security to avoid using the set pressure, start volume measurement and start rinsing
        button on GUI, for example during Tasks. By security, all thread actions (measuring flow-rate and volume are
        stopped as well).
        """
        self.sigDisableFlowActions.emit()
        self.stop_flow_measurement()

    def enable_flowcontrol_actions(self):
        """
        This method resets flowcontrol action buttons on GUI to callable state, for example after Tasks.
        """
        self.sigEnableFlowActions.emit()
