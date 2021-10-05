# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains the logic to control the microfluidics pump and flowrate sensor.

An extension to Qudi.

@author: F. Barho

Created on Thu Mars 4 2021
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
import numpy as np
from time import sleep
import math
from simple_pid import PID

from qtpy import QtCore
from logic.generic_logic import GenericLogic
from core.configoption import ConfigOption
from core.connector import Connector


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
    sigIntegrationIntervalFinished = QtCore.Signal()


class MeasurementWorker(QtCore.QRunnable):
    """ Worker thread to monitor the pressure and the flow-rate every x seconds when measuring mode is on.

    The worker handles only the waiting time, and emits a signal that serves to trigger the update of indicators on GUI.
    """

    def __init__(self, *args, **kwargs):
        super(MeasurementWorker, self).__init__(*args, **kwargs)
        self.signals = WorkerSignals()

    @QtCore.Slot()
    def run(self):
        """ """
        sleep(1)  # 1 second as time constant
        self.signals.sigFinished.emit()


class RegulationWorker(QtCore.QRunnable):
    """ Worker thread to regulate the pressure every 1 second when regulation loop is on.

    The worker handles only the waiting time, and emits a signal that serves to trigger the next regulation step.
    The signal transmits the target flowrate value to the next loop iteration.
    """

    def __init__(self, target_flowrate):
        super(RegulationWorker, self).__init__()
        self.signals = WorkerSignals()
        self.target_flowrate = target_flowrate

    @QtCore.Slot()
    def run(self):
        """ """
        sleep(1)  # 1 second as time constant
        self.signals.sigRegulationWaitFinished.emit(self.target_flowrate)


class VolumeCountWorker(QtCore.QRunnable):
    """ Worker thread to measure the injected volume of buffer or probe

    The worker handles only the waiting time, and emits a signal that serves to trigger a new sampling.
    The signal transmits the target volume and the sampling interval to the next loop iteration. """

    # def __init__(self, target_volume, sampling_interval):
    def __init__(self):
        super(VolumeCountWorker, self).__init__()
        self.signals = WorkerSignals()
        # self.target_volume = target_volume
        # self.sampling_interval = sampling_interval

    @QtCore.Slot()
    def run(self):
        """ """
        # sleep(self.sampling_interval)
        sleep(1)
        # self.signals.sigIntegrationIntervalFinished.emit(self.target_volume, self.sampling_interval)
        self.signals.sigIntegrationIntervalFinished.emit()


# ======================================================================================================================
# Logic class
# ======================================================================================================================


class FlowcontrolLogic(GenericLogic):
    """
    Class containing the logic to control the microfluidics pump and flowrate sensor.
    The microfluidics pump can either be handled by a flowboard (if it is part of the Fluigent system) or by a DAQ.
    The pump for needle rinsing is handled by a DAQ.

    Example config for copy-paste:

    flowcontrol_logic:
        module.Class: 'flowcontrol_logic.FlowcontrolLogic'
        p_gain: 0.005
        i_gain: 0.01
        d_gain: 0.0
        pid_sample_time: 0.1  # in s
        pid_output_min: 0
        pid_output_max: 15
        connect:
            flowboard: 'flowboard_dummy'
            daq_logic: 'daq_logic'
    """
    # declare connectors
    flowboard = Connector(interface='MicrofluidicsInterface')
    daq_logic = Connector(interface='DAQLogic')

    # signals
    sigUpdateFlowMeasurement = QtCore.Signal(list, list)
    sigUpdatePressureSetpoint = QtCore.Signal(float)
    sigUpdateVolumeMeasurement = QtCore.Signal(int, int, int, int)
    sigTargetVolumeReached = QtCore.Signal()
    sigRinsingFinished = QtCore.Signal()
    sigDisableFlowActions = QtCore.Signal()
    sigEnableFlowActions = QtCore.Signal()

    # attributes
    measuring_flowrate = False
    regulating = False
    measuring_volume = False
    target_volume = 0
    sampling_interval = 1 # If this value is changed, change also the sleep time in VolumeCountWorker
    total_volume = 0
    time_since_start = 0
    target_volume_reached = True
    rinsing_enabled = False

    # attributes for pid
    p_gain = ConfigOption('p_gain', 0.005, missing='warn')   # 0.005
    i_gain = ConfigOption('i_gain', 0.01, missing='warn')  # 0.001 for Airyscan   # 0.01 for RAMM
    d_gain = ConfigOption('d_gain', 0.0, missing='warn')  # 0.0
    pid_sample_time = ConfigOption('pid_sample_time', 0.1, missing='warn')  # 0.1 (for RAMM)  # in s, frequency for the PID update in simple_pid package
    pid_output_min = ConfigOption('pid_output_min', 0, missing='warn')
    pid_output_max = ConfigOption('pid_output_max', 15, missing='warn')

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self.threadpool = QtCore.QThreadPool()
        self._flowboard = None
        self._daq_logic = None
        self.pid = None

    def on_activate(self):
        """ Initialisation performed during activation of the module.
        """
        # connector
        self._flowboard = self.flowboard()
        self._daq_logic = self.daq_logic()
        self.set_pressure(0.0)

        # signals from connected logic
        self._daq_logic.sigRinsingDurationFinished.connect(self.rinsing_finished)

    def on_deactivate(self):
        """ Perform required deactivation. """
        self.set_pressure(0.0)

# ----------------------------------------------------------------------------------------------------------------------
# Low level methods for pressure settings
# ----------------------------------------------------------------------------------------------------------------------

    def get_pressure(self, channels=None):
        """ Get the current pressure value of the corresponding list of channel or all channels.

        :param: list channels: optional, list of channels of which pressure value will be measured
        :return: list of floats: pressure value of the single queried channel or all channels
        """
        if len(self._flowboard.pressure_channel_IDs) > 0:  # pump is controlled by flowboard
            pressure = self._flowboard.get_pressure(channels)  # returns a dictionary: {0: pressure_channel_0}
            pressure = [*pressure.values()]  # retrieve only the values from the dictionary and convert into list
            return pressure
        else:
            return [self._daq_logic.get_pressure()]

    def set_pressure(self, pressures, log_entry=True, channels=None):
        """ Set the pressure to the specified channels or all channels. If channels argument is omitted, only a
        single value for pressure can be given.
        :param: float or float list pressures: pressure to be set to a given channel
        :param: bool log_entry: make log entry optional, for example to avoid overloading logger while running a pressure regulation loop
        :param: int list channels: optional, needed in case more than one pressure channel is available
        :return: None
        """
        if len(self._flowboard.pressure_channel_IDs) > 0:  # pump is controlled by flowboard
            if not channels:
                if not isinstance(pressures, int) and not isinstance(pressures, float):  # a list is given
                    self.log.warning('Channels must be specified if more than one pressure value shall be set.')
                else:
                    # case for a single channel
                    param_dict = {}
                    param_dict[0] = pressures  # maybe modify in case another pump has a different way of addressing its channel (adapt by config; default_channel_ID ?)
                    unit = self.get_pressure_unit()[0]
                    self._flowboard.set_pressure(param_dict)
                    if log_entry:
                        self.log.info(f'Pressure set to {pressures} {unit}')
                    self.sigUpdatePressureSetpoint.emit(pressures)
            else:
                param_dict = dict(zip(channels, pressures))
                self._flowboard.set_pressure(param_dict)
        else:
            if type(pressures) == list:  # handle the list case, just take the first entry
                pressure = pressures[0]
            else:
                pressure = pressures
            self._daq_logic.set_pressure(pressure)

    def get_pressure_range(self, channels=None):
        """ Get the pressure range of the corresponding channel or all channels.

        :param list channels: list of channels from which pressure range value will be retrieved.
                                If None, all channels are queried.
        :return list pressure_range: pressure ranges for all channels
        """
        if len(self._flowboard.pressure_channel_IDs) > 0:  # pump is controlled by flowboard
            pressure_range = self._flowboard.get_pressure_range(channels)  # returns a dictionary: {0: pressure_range_channel_0}
            pressure_range = [*pressure_range.values()]  # retrieve only the values from the dictionary and convert into list
            return pressure_range
        else:
            return [(0, 10)]  # arbitrary value for the moment

    def get_pressure_unit(self, channels=None):
        """ Get the pressure unit of the corresponding channel or all channels.

        :param list channels: list of channels from which pressure unit will be retrieved.
                                If None, all channels are queried.
        :return list pressure_unit: pressure unit for all channels
        """
        if len(self._flowboard.pressure_channel_IDs) > 0:  # pump is controlled by flowboard
            pressure_unit = self._flowboard.get_pressure_unit(channels)  # returns a dictionary: {0: pressure_unit_channel_0}
            pressure_unit = [*pressure_unit.values()]  # retrieve only the values from the dictionary and convert into list
            return pressure_unit
        else:
            return ['Volt']  # add here the corresponding unit if pump is controlled by a daq

# ----------------------------------------------------------------------------------------------------------------------
# Low level methods for flowrate measurement
# ----------------------------------------------------------------------------------------------------------------------

    def get_flowrate(self, channels=None):
        """ Get the current flowrate of the corresponding sensor channel(s) or all sensor channels.

        :param list channels: optional, flowrate of a specific channel or a list of channels.
                                If None, all channels are queried.
        :return list of floats flowrate: flowrate of a single queried channel
                                                  or a list of flowrates of all channels
                                                  or a list of the channels specified as parameter.
        """
        flowrate = self._flowboard.get_flowrate(channels)  # returns a dictionary: {0: flowrate_channel_0}
        flowrate = [*flowrate.values()]  # retrieve only the values from the dictionary and convert into list
        return flowrate

    def get_flowrate_range(self, channels=None):
        """ Get the flowrate range of the corresponding sensor channel(s) or all sensor channels.

        :param list channels: optional, flowrate range of a specific channel or a list of channels.
                                If None, all channels are queried.
        :return list of float tuples flowrate_range: flowrate  range of a single queried channel
                                                        or a list of flowrate ranges of all channels
                                                        or a list of the channels specified as parameter.
        """
        flowrate_range = self._flowboard.get_sensor_range(channels)  # returns a dictionary: {0: sensor_range_channel_0}
        flowrate_range = [*flowrate_range.values()]  # retrieve only the values from the dictionary and convert into list
        return flowrate_range

    def get_flowrate_unit(self, channels=None):
        """ Get the flowrate unit of the corresponding sensor channel(s) or all sensor channels.

        :param list channels: optional, flowrate unit of a specific channel or a list of channels.
                                If None, all channels are queried.
        :return list of floats flowrate_unit: flowrate unit of a single queried channel
                                                        or a list of flowrate units of all channels
                                                        or a list of the channels specified as parameter.
        """
        flowrate_unit = self._flowboard.get_sensor_unit(channels)  # returns a dictionary: {0: sensor_unit_channel_0}
        flowrate_unit = [*flowrate_unit.values()]  # retrieve only the values from the dictionary and convert into list
        return flowrate_unit

# ----------------------------------------------------------------------------------------------------------------------
# Methods for continuous processes (flowrate measurement loop, pressure regulation loop, volume count, needle rinsing)
# ----------------------------------------------------------------------------------------------------------------------

# Flowrate measument loop ----------------------------------------------------------------------------------------------

    def start_flow_measurement(self):
        """ Start a continuous measurement of the flowrate and the pressure.
        :param: None
        :return: None
        """
        self.measuring_flowrate = True
        # monitor the pressure and flowrate, using a worker thread
        worker = MeasurementWorker()
        worker.signals.sigFinished.connect(self.flow_measurement_loop)
        self.threadpool.start(worker)

    def flow_measurement_loop(self):
        """ Continous measuring of the flowrate and the pressure at a defined sampling rate using a worker thread.
        :param: None
        :return: None
        """
        pressure = self.get_pressure()
        flowrate = self.get_flowrate()
        self.sigUpdateFlowMeasurement.emit(pressure, flowrate)
        if self.measuring_flowrate:
            # enter in a loop until measuring mode is switched off
            worker = MeasurementWorker()
            worker.signals.sigFinished.connect(self.flow_measurement_loop)
            self.threadpool.start(worker)

    def stop_flow_measurement(self):
        """ Stops the measurement of flowrate and pressure.
        Emits a signal to update the GUI with the most recent values.
        :param: None
        :return: None
        """
        self.measuring_flowrate = False
        # get once again the latest values
        pressure = self.get_pressure()
        flowrate = self.get_flowrate()
        self.sigUpdateFlowMeasurement.emit(pressure, flowrate)

# Pressure regulation loop ----------------------------------------------------------------------------------------------
    def init_pid(self, setpoint):
        """ Initialize the PID object from simple PID package.

        :param: float setpoint: regulation target value

        :return: PID object
        """
        pid = PID(self.p_gain, self.i_gain, self.d_gain, setpoint=setpoint)
        pid.output_limits = (self.pid_output_min, self.pid_output_max)
        pid.sample_time = self.pid_sample_time
        return pid

    def regulate_pressure_pid(self):  # maybe add channel as argument later
        """ Helper function to calculate the new pressure value given the flowrate.
        This new pressure value is set.
        This method is used in the pressure regulation loop.

        :return: None
        """
        flowrate = self.get_flowrate()
        new_pressure = float(self.pid(flowrate[0]))
        self.set_pressure(new_pressure, log_entry=False)

# first tests with a simple version where the channels are not specified (we would need signal overloading in the worker thread... to be explored later)
    def start_pressure_regulation_loop(self, target_flowrate):
        """ Start a continuous mode to regulate the pressure to achieve the target_flowrate.
        :param: int target_flowrate
        :return: None
        """
        self.regulating = True
        self.pid = self.init_pid(setpoint=target_flowrate)

        # regulate the pressure, using a worker thread
        worker = RegulationWorker(target_flowrate)
        worker.signals.sigRegulationWaitFinished.connect(self.pressure_regulation_loop)
        self.threadpool.start(worker)

    def stop_pressure_regulation_loop(self):
        """ Stop the continuous pressure regulation mode. Set the flag to False to avoid entering in a new loop.
        :return: None
        """
        self.regulating = False

    def pressure_regulation_loop(self, target_flowrate):
        """ Perform a step of pressure regulation towards reaching the target flowrate.
        :param: int target_flowrate
                (could eventually be removed because it was used in the initialization of the simple PID and is no longer needed.
                 Then the RegulationWorker must also be modified)
        :return: None
        """
        self.regulate_pressure_pid()
        if self.regulating:
            # enter in a loop until the regulating mode is stopped
            worker = RegulationWorker(target_flowrate)
            worker.signals.sigRegulationWaitFinished.connect(self.pressure_regulation_loop)
            self.threadpool.start(worker)

# Volume count ---------------------------------------------------------------------------------------------------------

    # in case multiplexing shall be implemented, the signal sigUpdateVolumeMeasurement could be overloaded,
    # such as sigVolumeMeasurement = QtCore.Signal(list, int), self.total_volume would be a list in this case
    # and the calculation of self.total_volume in volume_measurement_loop would need to be modified.
    def start_volume_measurement(self, target_volume): #, sampling_interval):
        """ Start a continuous measurement of the injected volume.
        :param: int target_volume: target volume to be injected.
                                Volume measurement will be stopped when target volume is reached (necessary for tasks).
        :param: float: sampling interval: time in seconds as sampling period.
        :return: None
        """
        self.measuring_volume = True
        self.total_volume = 0.0
        self.time_since_start = 0
        self.target_volume = target_volume
        # self.sampling_interval = sampling_interval
        # if self.total_volume < target_volume:
        if self.total_volume < self.target_volume:
            self.target_volume_reached = False
        # start summing up the total volume, using a worker thread
        # worker = VolumeCountWorker(target_volume, sampling_interval)
        worker = VolumeCountWorker()
        worker.signals.sigIntegrationIntervalFinished.connect(self.volume_measurement_loop)
        self.threadpool.start(worker)

    # def volume_measurement_loop(self, target_volume, sampling_interval):
    def volume_measurement_loop(self):
        """ Perform a step in the volume count loop.
        :param: int target_volume: target volume to be injected.
                                Volume measurement will be stopped when target volume is reached (necessary for tasks).
        :param: float: sampling interval: time in seconds as sampling period.
        :return: None
        """
        flowrate = self.get_flowrate()[0]
        pressure = self.get_pressure()[0]
        self.total_volume += flowrate * self.sampling_interval / 60
        self.total_volume = np.round(self.total_volume, decimals=3)  # as safety to avoid entering into the else part when target volume is not yet reached due to data overflow
        self.time_since_start += self.sampling_interval

        #  print("The target volume is {}, the total volume is {}, the duration of injection is {}".format(self.target_volume, self.total_volume, self.time_since_start))

        self.sigUpdateVolumeMeasurement.emit(int(self.total_volume), self.time_since_start, flowrate, pressure)

        # The second conditions was added to avoid target volume error. Sometimes, the target volume is never reached
        # and the pump keeps injecting without stopping.
        if self.total_volume < self.target_volume and self.measuring_volume:
            self.target_volume_reached = False
        else:
            self.target_volume_reached = True
            self.measuring_volume = False
            self.sigTargetVolumeReached.emit()

        # second condition is necessary to stop measurement via GUI button
        if not self.target_volume_reached and self.measuring_volume:
            # enter in a loop until the target_volume is reached
            worker = VolumeCountWorker()
            worker.signals.sigIntegrationIntervalFinished.connect(self.volume_measurement_loop)
            self.threadpool.start(worker)

        # when using np.inf as target_volume, the comparison ended sometimes up in the wrong branch (else) because np.inf was sometimes a large negative number

    def stop_volume_measurement(self):
        """ Stops the volume count. This method is used to stop the volume count using the GUI buttons,
        when no real target volume is provided.
        :param: None
        :return: None
        """
        self.measuring_volume = False
        self.target_volume_reached = True

# Rinse needle ---------- ----------------------------------------------------------------------------------------------
    def start_rinsing(self, duration):
        """ This method starts a needle rinsing process (informs the hardware to output a value on the DAQ) for
        a given duration.

        :param: int duration: rinsing duration in seconds
        :return: None
        """
        self.rinsing_enabled = True
        self._daq_logic.start_rinsing(duration)

    def stop_rinsing(self):
        """ This method is used to manually stop rinsing before specified duration (in start_rinsing) has elapsed. """
        self.rinsing_enabled = False
        self._daq_logic.stop_rinsing()

    def rinsing_finished(self):
        """ Callback of signal sigRinsingDurationFinished from connected daq logic.
        Inform the GUI that the rinsing time has elapsed. """
        self.rinsing_enabled = False
        self.sigRinsingFinished.emit()

# ----------------------------------------------------------------------------------------------------------------------
# Methods to handle the user interface state
# ----------------------------------------------------------------------------------------------------------------------

    def disable_flowcontrol_actions(self):
        """ This method provides a security to avoid using the set pressure, start volume measurement and start rinsing
        button on GUI, for example during Tasks. """
        self.sigDisableFlowActions.emit()

    def enable_flowcontrol_actions(self):
        """ This method resets flowcontrol action buttons on GUI to callable state, for example after Tasks. """
        self.sigEnableFlowActions.emit()
