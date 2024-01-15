#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed June 23, 2021

@author: fbarho

A general module to control any DAQ functionality (analog input / output, digital input / output)
except the laser control which is handled by a dedicated module (lasercontrol_logic)

Used for the DAQ on Airyscan setup. This module may be reorganized later into individual parts for different functionality.
"""

from core.connector import Connector
from core.util.mutex import Mutex
from logic.generic_logic import GenericLogic
from qtpy import QtCore
from time import sleep


class WorkerSignals(QtCore.QObject):
    """ Defines the signals available from a running worker thread """

    sigFinished = QtCore.Signal()


class Worker(QtCore.QRunnable):
    """ Worker thread to monitor the pressure and the flowrate every x seconds when measuring mode is on

    The worker handles only the waiting time, and emits a signal that serves to trigger the update indicators """

    def __init__(self, duration, *args, **kwargs):
        super(Worker, self).__init__()
        self.signals = WorkerSignals()
        self.duration = duration

    @QtCore.Slot()
    def run(self):
        """ """
        sleep(self.duration)
        self.signals.sigFinished.emit()


class DAQaoLogic(GenericLogic):
    """ Controls the DAQ analog output and allows to set a digital output line for triggering
    """

    # declare connectors
    daq = Connector(interface='Base')

    # attributes
    _pressure = 0.0

    # signals
    sigRinsingDurationFinished = QtCore.Signal()

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        # activate if necessary
        # self.threadlock = Mutex()

        self.threadpool = QtCore.QThreadPool()

    def on_activate(self):
        """ Initialisation performed during activation of the module.
        """
        self._daq = self.daq()

    def on_deactivate(self):
        """ Perform required deactivation. """
        pass


# needle rinsing

    def write_to_pump_ao_channel(self, voltage):
        self._daq.write_to_pump_ao_channel(voltage)

    def start_rinsing(self, duration):
        self.write_to_pump_ao_channel(1.0)
        worker = Worker(duration)
        worker.signals.sigFinished.connect(self.stop_rinsing)
        self.threadpool.start(worker)

    def stop_rinsing(self):
        self.write_to_pump_ao_channel(0.0)
        self.sigRinsingDurationFinished.emit()

# handle pressure for fluidics system

    def write_to_fluidics_pump_ao_channel(self, voltage):
        self._daq.write_to_fluidics_pump_ao_channel(voltage)

    def set_pressure(self, pressure):
        voltage = pressure   # do we assume proportionality ??? or apply a transformation to convert pressure to a voltage
        self._pressure = pressure  # store the setting in a class attribute to use it for get pressure method
        self.write_to_fluidics_pump_ao_channel(voltage)

    def get_pressure(self):
        return self._pressure
