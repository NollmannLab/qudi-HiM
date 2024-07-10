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
from core.connector import Connector
from logic.generic_logic import GenericLogic
from qtpy import QtCore
import time
import numpy as np
from core.configoption import ConfigOption


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
    #connectors
    arduino_uno = Connector(interface='Base')  # no specific arduino interface required
    MFC = Connector(interface='Base')  # no specific MFC interface required

    sigUpdateFlowMeasurement = QtCore.Signal(list, list, list)
    sigDisableFlowActions = QtCore.Signal()
    sigEnableFlowActions = QtCore.Signal()

    # attributes
    measuring_flowrate = False
    time_since_start = 0
    # declare connectors

    _MFC_purge = ConfigOption('MFC_purge', 2)
    _MFC_1 = ConfigOption('MFC_1', 0)
    _MFC_2 = ConfigOption('MFC_2', 1)
    _MFC_purge_flow = ConfigOption('MFC_purge_flow', 0.4)
    _MFC_1_flow = ConfigOption('MFC_1_flow', 0.04)
    _MFC_2_flow = ConfigOption('MFC_2_flow', 0.36)

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self.threadpool = QtCore.QThreadPool()
        self._MFC = None
        self._ard = None

    def on_activate(self):
        """
        Initialisation performed during activation of the module.
        """
        self._ard = self.arduino_uno()
        self._MFC = self.MFC()
        self._ard.pin_on(3)
    def on_deactivate(self):
        """ Perform required deactivation. """

    def valve(self, NbValve, state):
        """ Open only 1 valve 
        @param state: (bool) ON / OFF state of the valve (1 : odor circuit on ; 0 : odor circuit off)
        input example: ' 'state' '
        @param NbValve : The ^pin number link to the valve
        """
        if state == 1:
            self._ard.pin_on(NbValve)
        elif state == 0:
            self._ard.pin_off(NbValve)

    def prepare_odor(self, odor_number):
        """
        @param odor_number: number of the odor you want to inject (not use yet)
        input example: ' 'odor_number' '
        """

        if odor_number == 1:

            self._ard.pin_on(1)
            self._ard.pin_on(2)
            self._ard.pin_off(3)
        elif odor_number == 2:
            self._ard.pin_on(6)
            self._ard.pin_on(7)
            self._ard.pin_off(3)
        elif odor_number == 3:
            self._ard.pin_on(8)
            self._ard.pin_on(9)
            self._ard.pin_off(3)
        elif odor_number == 4:
            self._ard.pin_on(10)
            self._ard.pin_on(11)
            self._ard.pin_off(3)
        #elif odor_number == 5:
        #self._ard.pin_on('12')
        #self._ard.pin_on('13')
        #self._ard.pin_on('3')
        else:
            print('4 odor only')

    def flush_odor(self):
        """ Close all the valves that need to be closed
        """
        self._ard.pin_off(1)
        self._ard.pin_off(2)
        self._ard.pin_on(3)
        self._ard.pin_off(4)
        self._ard.pin_off(5)
        self._ard.pin_off(6)
        self._ard.pin_off(7)
        self._ard.pin_off(8)
        self._ard.pin_off(9)
        self._ard.pin_off(10)
        self._ard.pin_off(11)
        self._ard.pin_off(12)
        self._ard.pin_off(13)
        print('Odor circuit off')

    def open_air(self, flow1, flow2, flow3):
        """
            Open the MFCs
        """
        self._MFC.MFC_ON(self._MFC_1, flow1)
        time.sleep(0.3)
        self._MFC.MFC_ON(self._MFC_2, flow2)
        time.sleep(0.3)
        self._MFC.MFC_ON(self._MFC_purge, flow3)

    def close_air(self):
        """
            Close the MFCs
        """
        self._MFC.MFC_OFF(self._MFC_1)
        time.sleep(0.3)
        self._MFC.MFC_OFF(self._MFC_2)
        time.sleep(0.3)
        self._MFC.MFC_OFF(self._MFC_purge)

    @property
    def read_all_average_measure(self):
        """
        Read the flow passing through the MFCs
        """

        A1 = self._MFC.average_measure(self._MFC_purge, 20)
        A2 = self._MFC.average_measure(self._MFC_1, 20)
        A3 = self._MFC.average_measure(self._MFC_2, 20)

        return A1, A2, A3
    def get_flowrate(self):
        """
        """
        M1, M2, M3 = self.read_all_average_measure
        M1, M2, M3 = [M1], [M2], [M3]
        return M1, M2, M3

    # ----------------------------------------------------------------------------------------------------------------------
    # Methods for continuous processes (flowrate measurement loop)
    # ----------------------------------------------------------------------------------------------------------------------

    # Flowrate measument loop ----------------------------------------------------------------------------------------------

    def start_flow_measurement(self):
        """ Start a continuous measurement of the flowrate.
        :param: None
        :return: None
        """
        self.measuring_flowrate = True
        # monitor the flowrate, using a worker thread
        worker = MeasurementWorker()
        worker.signals.sigFinished.connect(self.flow_measurement_loop)
        self.threadpool.start(worker)

    def flow_measurement_loop(self):
        """ Continous measuring of the flowrate at a defined sampling rate using a worker thread.
        :param: None
        :return: None
        """
        flowrate1, flowrate2, flowrate3 = self.get_flowrate()
        self.sigUpdateFlowMeasurement.emit(flowrate1, flowrate2, flowrate3)
        if self.measuring_flowrate:
            # enter in a loop until measuring mode is switched off
            worker = MeasurementWorker()
            worker.signals.sigFinished.connect(self.flow_measurement_loop)
            self.threadpool.start(worker)

    def stop_flow_measurement(self):
        """ Stops the measurement of flowrate.
        Emits a signal to update the GUI with the most recent values.
        :param: None
        :return: None
        """
        self.measuring_flowrate = False
        # get once again the latest values
        flowrate1, flowrate2, flowrate3 = self.get_flowrate()
        self.sigUpdateFlowMeasurement.emit(flowrate1, flowrate2, flowrate3)

    # ----------------------------------------------------------------------------------------------------------------------
    # Methods to handle the user interface state
    # ----------------------------------------------------------------------------------------------------------------------
    def disable_flowcontrol_actions(self):
        """ This method provides a security to avoid using the set pressure, start volume measurement and start rinsing
        button on GUI, for example during Tasks. By security, all thread actions (measuring flow-rate and volume are
         stopped as well)."""
        self.sigDisableFlowActions.emit()
        self.stop_flow_measurement()

    def enable_flowcontrol_actions(self):
        """ This method resets flowcontrol action buttons on GUI to callable state, for example after Tasks. """
        self.sigEnableFlowActions.emit()
