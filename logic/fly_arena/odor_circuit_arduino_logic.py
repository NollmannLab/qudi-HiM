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

    # attributes
    measuring_flowrate = False
    time_since_start = 0

    _valve_odor_1_in = ConfigOption('valve_odor_1_in', 3)
    _valve_odor_2_in = ConfigOption('valve_odor_2_in', 12)
    _valve_odor_3_in = ConfigOption('valve_odor_3_in', 11)
    _valve_odor_4_in = ConfigOption('valve_odor_4_in', 10)
    _valve_odor_1_out = ConfigOption('valve_odor_1_in', 7)
    _valve_odor_2_out = ConfigOption('valve_odor_2_in', 6)
    _valve_odor_3_out = ConfigOption('valve_odor_3_in', 5)
    _valve_odor_4_out = ConfigOption('valve_odor_4_in', 4)
    _mixing_valve = ConfigOption('mixing_valve', 9)
    _final_valve = ConfigOption('final_valve', 8)

    _MFC_1 = ConfigOption('MFC_1', 0)
    _MFC_2 = ConfigOption('MFC_2', 1)
    _MFC_3_purge = ConfigOption('MFC_purge', 2)
    _MFC_4 = ConfigOption('MFC_4', 3)

    _MFC_purge_flow = ConfigOption('MFC_purge_flow', 0.5)
    _MFC_1_flow = ConfigOption('MFC_1_flow', 0.25)
    _MFC_2_flow = ConfigOption('MFC_2_flow', 0.25)

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self.threadpool = QtCore.QThreadPool()
        self._MFC = None
        self._ard = None
        self.MFC_number: int = 0

    def on_activate(self):
        """
        Initialisation performed during activation of the module.
        """
        self._ard = self.arduino_uno()
        self._MFC = self.MFC()
        self.MFC_number = self._MFC.MFC_number

    def on_deactivate(self):
        """
        Perform required deactivation.
        """
        pass

# ----------------------------------------------------------------------------------------------------------------------
# Methods handling MFCs
# ----------------------------------------------------------------------------------------------------------------------
    def set_MFCs_flow(self, flow_setpoints):
        print(f'Flow setpoint : {flow_setpoints}')

        # check odor valves state
        is_odor = self._ard.check_odor_valves()
        print(f"odor detected : {is_odor}")

        # check mixing valve state
        is_mixing = self._ard.check_mixing_valve()
        print(f"mixing detected : {is_mixing}")

        # check if all the MFCs are turned off
        All_off = all(v == 0 for v in flow_setpoints)

        # if none of the valves are open, open the mixing valve by default (expect in the case all MFCs are turned off)
        if All_off:
            self._ard.control_mixing_valve(0)
        elif (not is_odor) and (not is_mixing) and (not All_off):
            self._ard.control_mixing_valve(1)

        # start the MFCs
        for mfc in range(self.MFC_number):
            if flow_setpoints[mfc] > 0:
                self._MFC.MFC_ON(mfc, flow_setpoints[mfc])
            else:
                self._MFC.MFC_OFF(mfc)

# ----------------------------------------------------------------------------------------------------------------------
# Methods handling Valves
# ----------------------------------------------------------------------------------------------------------------------
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

    def prepare_odor(self, odor_number):
        """
        Prepare the specified odor by activating the corresponding valves.
        @param odor_number: number of the odor you want to inject (not use yet)
        input example: 'odor_number'
        """
        if odor_number == 1:
            self.valve(self._valve_odor_1_in, 1)
            self.valve(self._valve_odor_1_out, 1)
        elif odor_number == 2:
            self.valve(self._valve_odor_2_in, 1)
            self.valve(self._valve_odor_2_out, 1)
        elif odor_number == 3:
            self.valve(self._valve_odor_3_in, 1)
            self.valve(self._valve_odor_3_out, 1)
        elif odor_number == 4:
            self.valve(self._valve_odor_4_in, 1)
            self.valve(self._valve_odor_4_out, 1)
        else:
            logger.warning('4 odor only')

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

    def close_air(self):
        """
        Close the MFCs
        """
        self._MFC.MFC_OFF(self._MFC_1)
        time.sleep(0.3)
        self._MFC.MFC_OFF(self._MFC_2)
        time.sleep(0.3)
        self._MFC.MFC_OFF(self._MFC_3_purge)
        time.sleep(0.3)
        self._MFC.MFC_OFF(self._MFC_4)

    def read_all_average_measure(self):
        """
        Read the flow passing through the MFCs
        @return flow: (list) contains the mean value of the flow measured separately for each MFC
        """
        flow = []
        for n in range(self.MFC_number):
            flow.append(self._MFC.average_measure(n, 20))

        return flow

    # -----------------------------------------------------------------------------------------------------------------
    # Methods for continuous processes (flowrate measurement loop)
    # -----------------------------------------------------------------------------------------------------------------

    # Flowrate measurement loop ---------------------------------------------------------------------------------------

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
        flow_rates = self.read_all_average_measure()
        self.sigUpdateFlowMeasurement.emit(flow_rates)
        if self.measuring_flowrate:
            # enter a loop until measuring mode is switched off
            worker = MeasurementWorker()
            worker.signals.sigFinished.connect(self.flow_measurement_loop)
            self.threadpool.start(worker)

    def stop_flow_measurement(self):
        """
        Stops the measurement of flowrate.
        Emits a signal to update the GUI with the most recent values.
        """
        self.measuring_flowrate = False

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
