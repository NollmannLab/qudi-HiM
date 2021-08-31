# -*- coding: utf-8 -*-
"""
Qudi-CBS

A module to control any DAQ functionality (analog input / output, digital input / output)
except the laser control which is handled by a dedicated module (lasercontrol_logic)

An extension to Qudi.

@author: F. Barho

Created on Wed March 24, 2021
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
from core.configoption import ConfigOption
from logic.generic_logic import GenericLogic
from qtpy import QtCore
from time import sleep

# ======================================================================================================================
# Worker class for the needle rinsing continuous process
# ======================================================================================================================


class WorkerSignals(QtCore.QObject):
    """ Defines the signals available from a running worker thread """

    sigFinished = QtCore.Signal()


class Worker(QtCore.QRunnable):
    """ Worker thread to count the time during which the needle rinsing peristaltic pump should be activated.

    The worker handles only the waiting time, and emits a signal that serves to trigger following function
    that must be called to switch off the pump. """

    def __init__(self, duration, *args, **kwargs):
        super(Worker, self).__init__(*args, **kwargs)
        self.signals = WorkerSignals()
        self.duration = duration

    @QtCore.Slot()
    def run(self):
        """ """
        sleep(self.duration)
        self.signals.sigFinished.emit()


# ======================================================================================================================
# Logic class
# ======================================================================================================================


class DAQLogic(GenericLogic):
    """ Class containing the logic to control a DAQ.
    Its main reason is to make the DAQ hardware functions accessible from the logic level.
    Due to the specific usage, no common interface is required here.

    Example config for copy-paste:

    nidaq_logic:
        module.Class: 'daq_logic.DAQLogic'
        voltage_rinsing_pump: -3
        connect:
            daq: 'nidaq_6259'
    """
    # declare connectors
    daq = Connector(interface='Base')  # no specific DAQ interface required

    # config options
    _voltage_rinsing_pump = ConfigOption('voltage_rinsing_pump', 0)

    # signals
    sigRinsingDurationFinished = QtCore.Signal()

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self._daq = None
        self._pressure = 0
        self.threadpool = QtCore.QThreadPool()

    def on_activate(self):
        """ Initialisation performed during activation of the module.
        """
        self._daq = self.daq()

    def on_deactivate(self):
        """ Perform required deactivation. """
        pass

# ----------------------------------------------------------------------------------------------------------------------
# Low-level methods for digital input / output
# ----------------------------------------------------------------------------------------------------------------------
# For these low-level methods, it is needed to pass in a taskhandle (see hardware module) as argument
# (for connected NI-DAQ).
# This can for example be done in tasks (even though we access a private attribute from the NI-DAQ hardware class).
# Add here: how to use this for other daq types ?

    def write_to_do_channel(self, channel, num_samp, digital_write):
        """ Write a value to a digital output virtual channel.

        :param: DAQmx.Taskhandle object taskhandle: pointer to the virtual channel
        :param: int num_samp: number of values to write
        :param: np.ndarray digital_write: np array containing the values to write, using dtype=np.uint8

        :return: None
        """
        self._daq.write_to_do_channel(channel, num_samp, digital_write)

    def read_di_channel(self, channel, num_samp):
        """ Read a value from a digital input virtual channel.

        :param: DAQmx.Taskhandle object taskhandle: pointer to the virtual channel
        :param: int num_samp: number of values to read

        :return: float data: values read from the digital input channel
        """
        return self._daq.read_di_channel(channel, num_samp)

# ----------------------------------------------------------------------------------------------------------------------
# Low-level methods for analog input / output
# ----------------------------------------------------------------------------------------------------------------------

    def write_to_ao_channel(self, channel, voltage):
        """ Write a voltage to an analog output channel.

        :param: DAQmx.Taskhandle object channel: pointer to the virtual channel
        :param: float voltage: target voltage value to apply to the channel

        :return: None
        """
        self._daq.write_to_ao_channel(channel, voltage)

    def read_ai_channel(self, channel):
        """ Read a value from an analog input channel.

        :param: DAQmx.Taskhandle object channel: pointer to the virtual channel

        :return: float data: value read from the ai channel
        """
        return self._daq.read_ai_channel(channel)


# The following methods are defined in the hardware module to avoid having to deal with the corresponding taskhandle,
# which would be the case if using the low-level methods above.
# ----------------------------------------------------------------------------------------------------------------------
# Methods for analog in/out channels controlling a piezo
# ----------------------------------------------------------------------------------------------------------------------

    def read_piezo(self):
        """ Read the voltage applied to the channel controlling the piezo.

        :return: float value: voltage applied to the piezo.
        """
        return self._daq.read_piezo()

    def move_piezo(self, pos):
        """ Move the piezo to the indicated position.

        :param: float position: expected position of the piezo

        :return: None
        """
        self._daq.move_piezo(pos)

# ----------------------------------------------------------------------------------------------------------------------
# Methods for analog in/out channels controlling a peristaltic pump
# ----------------------------------------------------------------------------------------------------------------------

# needle rinsing pump used on RAMM and Airyscan setup ------------------------------------------------------------------
    def start_rinsing(self, duration):
        """ Start the needle rinsing pump by applying the target voltage.

        :param: int duration: rinsing time in seconds

        :return: None
        """
        self._daq.write_to_rinsing_pump_channel(self._voltage_rinsing_pump)
        worker = Worker(duration)
        worker.signals.sigFinished.connect(self.stop_rinsing)
        self.threadpool.start(worker)

    def stop_rinsing(self):
        """ Stop the needle rinsing pump.

        :return: None
        """
        self._daq.write_to_rinsing_pump_channel(0.0)
        self.sigRinsingDurationFinished.emit()

# flowcontrol peristaltic pump used only on Airyscan setup -------------------------------------------------------------
# The hardware function in not defined on the NI-DAQ, as there is no common DAQ interface

    def set_pressure(self, voltage):
        """ Start the peristaltic pump used for flowcontrol by applying a target voltage. Store the applied voltage
        in the class attribute _pressure (although it is a voltage!)

        :param: float voltage: target voltage to apply to the pump (for common user interface,
                                the method is nevertheless called set_pressure). """
        self._pressure = voltage  # store the setting in a class attribute to use it for get pressure method
        self._daq.write_to_fluidics_pump_channel(voltage)

    def get_pressure(self):
        """ Retrive the applied voltage of the peristaltic pump used for flowcontrol. It is stored under the name
        _pressure although it is a voltage (for common user interface with system where a real readout of the
        pressure is possible).

        :return: float tension applied to the peristaltic pump
        """
        return self._pressure
