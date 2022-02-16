# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains the logic to control the focus using manual settings or autofocus.
Connected hardware is a piezo stage controller.

An extension to Qudi.

@authors: F. Barho, JB. Fiche
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
# from core.util.mutex import Mutex
from logic.generic_logic import GenericLogic
from qtpy import QtCore
from time import sleep, time
import numpy as np
from numpy.polynomial import Polynomial as Poly
from functools import partial

# ======================================================================================================================
# Worker classes
# ======================================================================================================================


class WorkerSignals(QtCore.QObject):
    """ Defines the signals available from a running worker thread. """
    sigFinished = QtCore.Signal()


class AutofocusWorker(QtCore.QRunnable):
    """ Worker thread to monitor the autofocus signal (QPD or camera) and adjust the piezo position when autofocus in ON.
    The worker handles only the waiting time between signal readout. """
    def __init__(self, dt, *args, **kwargs):
        super(AutofocusWorker, self).__init__(*args, **kwargs)
        self.signals = WorkerSignals()
        self.frequency = dt

    @QtCore.Slot()
    def run(self):
        """ """
        sleep(self.frequency)
        self.signals.sigFinished.emit()


class Worker(QtCore.QRunnable):
    """ Worker thread for live camera display or piezo position timetrace.
    The worker handles only the waiting time between the sampling of an image / a position. """

    def __init__(self, time_constant):
        super(Worker, self).__init__()
        self.signals = WorkerSignals()
        self.time_constant = time_constant

    @QtCore.Slot()
    def run(self):
        """ """
        sleep(self.time_constant)
        self.signals.sigFinished.emit()


# ======================================================================================================================
# Logic class
# ======================================================================================================================


class FocusLogic(GenericLogic):
    """ Class to control the focus.

    Config entry for copy-paste:

    focus_logic:
        module.Class: 'focus_logic.FocusLogic'
        init_position: 10
        readout_device: 'qpd'  # 'camera', 'qpd'
        rescue_autofocus_possible: True
        connect:
            piezo: 'mcl'
            autofocus: 'autofocus_logic'
    """
    # declare connectors
    piezo = Connector(interface='MotorInterface')
    autofocus = Connector(interface='AutofocusLogic')

    # config options
    _init_position = ConfigOption('init_position', 10, missing='warn')
    _readout = ConfigOption('readout_device', missing='error')
    _rescue_autofocus_possible = ConfigOption('rescue_autofocus_possible', False, missing='warn')

    # signals
    sigStepChanged = QtCore.Signal(float)
    sigPositionChanged = QtCore.Signal(float)
    sigPiezoInitFinished = QtCore.Signal()
    sigUpdateTimetrace = QtCore.Signal(float)
    sigPlotCalibration = QtCore.Signal(object, object, object, float, float)
    sigOffsetCalibration = QtCore.Signal(float)
    sigSetpointDefined = QtCore.Signal(float)
    sigDisplayImageAndMask = QtCore.Signal(object, object, float, float)
    sigDisplayImage = QtCore.Signal(object)  # np.ndarray
    sigAutofocusError = QtCore.Signal()
    sigAutofocusStopped = QtCore.Signal()  # signal emitted when autofocus is programmatically stopped
    sigDoStageMovement = QtCore.Signal(float)
    sigFocusFound = QtCore.Signal()
    sigDisableFocusActions = QtCore.Signal()
    sigEnableFocusActions = QtCore.Signal()

    # piezo attributes
    _step = 0.01
    _max_step = 0
    _axis = None

    # display element state attributes
    timetrace_enabled = False
    timetrace_update_time = 0.1  # in s
    live_display_enabled = False  # camera image
    live_update_time = 0.2  # in s

    # autofocus attributes
    _calibration_range = 2  # Autofocus calibration range in µm
    _slope = None
    _precision = None
    _z0 = None
    _dt = None
    _calibrated = False
    _setpoint_defined = False
    _autofocus_lost = False
    _stage_is_positioned = False

    autofocus_enabled = False
    piezo_correction_running = False

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self.rescue = self._rescue_autofocus_possible
        self.threadpool = QtCore.QThreadPool()
        self._piezo = None
        self._autofocus_logic = None
        self._axis = None
        self._min_z = None
        self._max_z = None

        # uncomment if needed:
        # self.threadlock = Mutex()

    def on_activate(self):
        """ Initialisation performed during activation of the module.
        """
        # initialize the piezo
        self._piezo = self.piezo()
        self._axis = self._piezo._axis_label
        self._max_step = self._piezo.get_constraints()[self._axis]['max_step']
        self._min_z = self._piezo.get_constraints()[self._axis]['pos_min']
        self._max_z = self._piezo.get_constraints()[self._axis]['pos_max']
        self.init_piezo()

        # initialize the autofocus class
        self._autofocus_logic = self.autofocus()

        # signals to autofocus logic
        self.sigDoStageMovement.connect(self._autofocus_logic.do_position_correction)

        # signals from autofocus logic
        self._autofocus_logic.sigOffsetDefined.connect(self.define_autofocus_setpoint)
        self._autofocus_logic.sigStageMoved.connect(self.finish_piezo_position_correction)

    def on_deactivate(self):
        """ Perform required deactivation.
        Reset the piezo to the zero position.
        """
        self.go_to_position(0.5)

# ----------------------------------------------------------------------------------------------------------------------
# Methods for manual focus setting (manual focus dockwidget and toolbar)
# ----------------------------------------------------------------------------------------------------------------------

    def init_piezo(self):
        """ Move piezo to initial position defined in the configuration file.
        :return None
        """
        self.piezo_ramp(self._init_position)
        self.sigPiezoInitFinished.emit()

    def move_up(self, step):
        """ Make a relative movement in positive z direction.
        :param float step: target relative movement (positive value)
        :return None
        """
        self._piezo.move_rel({self._axis: step})
        sleep(0.03)  # stabilization time before reading the position
        position = self.get_position()
        self.sigPositionChanged.emit(position)

        # the stabilisation time of 30 ms should enable it to read an already stable position
        # but this could slow down continuous movements (button pressed down on GUI or key shortcuts)

    def move_down(self, step):
        """ Make a relative movement in negative z direction.
        :param float step: target relative movement (positive value, orientation is handled by this method)
        :return None
        """
        self._piezo.move_rel({self._axis: -step})
        sleep(0.03)
        position = self.get_position()
        self.sigPositionChanged.emit(position)

    def get_position(self):
        """ Read the current piezo position.
        :return current piezo position
        """
        return self._piezo.get_pos()[self._axis]

    def set_step(self, step):
        """ Set the step for a piezo movement. This updates the class attribute _step which is used by the GUI module.
        :param: float step: new value for the step
        :return: None """
        self._step = step
        # in case this function is called via console, update the GUI
        self.sigStepChanged.emit(step)

    def go_to_position_relative(self, dz):
        """ Perform a relative movement

        @param dz: indicate the axial displacement to perform
        """
        self._piezo.move_rel({self._axis: dz})

    def go_to_position(self, position, direct=False):
        """ Move piezo to the target position using a ramp to avoid moving in too big steps.
        :param: float position: target position for piezo
        :return: None
        """
        if direct:
            self._piezo.move_abs({self._axis: position})
            sleep(0.01)
        else:
            self.piezo_ramp(position)

    def piezo_ramp(self, target_pos):
        """ Helper function implementing a ramp to go to target_pos with max step as far as possible and then do
        a last_step <= max_step.
        :param float target_pos: target position for piezo
        :return: None
        """
        constraints = self._piezo.get_constraints()
        step = constraints[self._axis]['max_step']
        position = self.get_position()  # check the return format, and reformat it in case it is needed
        while position < abs(target_pos - step) or position > abs(
                target_pos + step):  # approach in an interval of step around the target position
            if position > target_pos:
                self.move_down(step)
            else:
                self.move_up(step)
            position = self.get_position()

        last_step = target_pos - position
        if last_step > 0:
            self.move_up(last_step)
        else:
            self.move_down(-last_step)

# ----------------------------------------------------------------------------------------------------------------------
# Methods for testing tne piezo stability
# ----------------------------------------------------------------------------------------------------------------------

    def test_reading_position_error(self, n_repeat, dt):
        """ Build-in functionality to test the reproducibility of the measured piezo position

        @param n_repeat: number of measurements to perform
        @param dt: lapse of time between two successive measurement (in s)
        """
        z = np.zeros((n_repeat,))
        for n in range(n_repeat):
            z[n] = self.get_position()
            sleep(dt)

        print(f'The average position is z={np.mean(z)} +/- {np.std(z)} nm')

    def test_execution(self, dz, direct=False):
        """ Test to measure the execution time of the go_to_position method, depending on the selected options.

        @param dz: amplitude of the axial displacement
        @param direct: indicate whether the movement is direct or using the ramp method.
        """
        z0 = self.get_position()
        t0 = time()
        self.go_to_position(z0 + dz, direct=direct)
        t1 = time()
        print(t1-t0)

    def test_position_reproducibility(self, dz, n_repeat, dt, direct=False):
        """ Build-in functionality to test the reproducibility of the piezo displacement.

        @param dz: relative displacement to perform (in µm)
        @param n_repeat: number of measurements to perform
        @param dt: lapse of time between movement and position measurement (in s)
        """
        z = np.zeros((n_repeat, 2))
        z0 = self.get_position()
        for n in range(n_repeat):
            self.go_to_position(z0 + dz, direct=direct)
            sleep(dt)
            z[n, 0] = self.get_position()
            self.go_to_position(z0-dz, direct=direct)
            sleep(dt)
            z[n, 1] = self.get_position()

        dz_up = z[:, 1] - z[:, 0]
        dz_down = z[1:-1, 0] - z[0:-2, 1]
        z_mean = np.mean(z, axis=0)
        z_std = np.std(z, axis=0)
        dz_up_mean = np.mean(dz_up, axis=0)
        dz_up_std = np.std(dz_up, axis=0)
        dz_down_mean = np.mean(dz_down, axis=0)
        dz_down_std = np.std(dz_down, axis=0)
        print(f'The average positions are z1 = {z_mean[0]} +/- {z_std[0]}nm and z2 = {z_mean[1]} +/- {z_std[1]}nm')
        print(f'The average dz_up = {dz_up_mean} +/- {dz_up_std}nm and dz_down = {dz_down_mean} +/- {dz_down_std}nm')

# ----------------------------------------------------------------------------------------------------------------------
# Methods for the timetrace of the piezo position (timetrace dockwidget)
# ----------------------------------------------------------------------------------------------------------------------

    def start_position_tracking(self):
        """ Start the timetrace of the piezo position. This method serves as slot called by gui signal sigTimetraceOn.
        """
        self.timetrace_enabled = True
        worker = Worker(self.timetrace_update_time)
        worker.signals.sigFinished.connect(self.position_tracking_loop)
        self.threadpool.start(worker)

    def stop_position_tracking(self):
        """ Stop the timetrace of the piezo position. This method serves as slot called by gui signal sigTimetraceOff.
        """
        self.timetrace_enabled = False

    def position_tracking_loop(self):
        """ Execute step in the data recording loop, get the current z position of the piezo.
        """
        position = self.get_position()
        self.sigUpdateTimetrace.emit(position)
        if self.timetrace_enabled:
            worker = Worker(self.timetrace_update_time)
            worker.signals.sigFinished.connect(self.position_tracking_loop)
            self.threadpool.start(worker)

# ----------------------------------------------------------------------------------------------------------------------
# Methods for live display of camera (image display dockwidget)
# ----------------------------------------------------------------------------------------------------------------------

    def start_live_display(self):
        """ Start the camera live display. """
        self.live_display_enabled = True
        self._autofocus_logic.start_camera_live()

        worker = Worker(self.live_update_time)
        worker.signals.sigFinished.connect(self.live_display_loop)
        self.threadpool.start(worker)

    def live_display_loop(self):
        """ Refresh the camera live image.
        """
        im = self._autofocus_logic.get_latest_image()

        if self._readout == "camera":
            mask = self._autofocus_logic.calculate_threshold_image(im)
            x, y = self._autofocus_logic.calculate_centroid(im, mask)
            self.sigDisplayImageAndMask.emit(im, mask, x, y)
        elif self._readout == "qpd":
            self.sigDisplayImage.emit(im)
        else:
            pass

        if self.live_display_enabled:
            worker = Worker(self.live_update_time)
            worker.signals.sigFinished.connect(self.live_display_loop)
            self.threadpool.start(worker)

    def stop_live_display(self):
        """ Stop the camera live image. """
        self._autofocus_logic.stop_camera_live()
        self.live_display_enabled = False

# ----------------------------------------------------------------------------------------------------------------------
# Methods for autofocus (autofocus dockwidget and toolbar)
# ----------------------------------------------------------------------------------------------------------------------

# Method specific for camera based readout -----------------------------------------------------------------------------
    def update_threshold(self, threshold):
        """ Set the user defined threshold used to calculate the threshold image of the raw data.
        :param: int threshold: value above which values are set to maximum of the scale.
        :return: None
        """
        self._autofocus_logic._threshold = threshold

# Signal readout -------------------------------------------------------------------------------------------------------
    def read_detector_signal(self):
        """ According to the method used for the autofocus, returns either the QPD signal or the centroid position
        of the IR reflection measured on the camera.
        :return: float detector signal
        """
        return self._autofocus_logic.read_detector_signal()

    def check_autofocus(self):
        """ Check if there is signal detected for the autofocus. Depending on the method it can be a non-zero signal
        detected by the QPD or the camera. This methods updates the class attribute _autofocus_lost.
        :return: None
        """
        self._autofocus_lost = not self._autofocus_logic.autofocus_check_signal()

# Calibration of the autofocus -----------------------------------------------------------------------------------------
    def calibrate_focus_stabilization(self):
        """ Calibrate the focus stabilization by performing a quick 2 µm ramp with the piezo and measuring the
        autofocus signal (either camera or QPD) for each position.
        :return: None
        """
        if self._readout == 'camera' and not self.live_display_enabled:
            self._autofocus_logic.start_camera_live()

        z0 = self.get_position()
        dz = self._calibration_range // 2
        z = np.arange(z0 - dz, z0 + dz, 0.1)
        n_positions = len(z)
        piezo_position = np.zeros((n_positions,))
        autofocus_signal = np.zeros((n_positions,))

        # Position the piezo (the first position is taking longer to stabilize)
        self.go_to_position(z[0])
        sleep(0.5)

        # Start the calibration
        for n in range(n_positions):
            current_z = z[n]
            self.go_to_position(current_z)
            # Timer necessary to make sure the piezo has reached the position and is stable
            sleep(0.05)
            piezo_position[n] = self.get_position()
            # Read the latest QPD signal
            autofocus_signal[n] = self.read_detector_signal()

        # Calculate the slope of the calibration curve
        p = Poly.fit(piezo_position, autofocus_signal, deg=1)
        self._slope = p(1) - p(0)
        self._calibrated = True

        self.go_to_position(z0)
        sleep(0.5)  # wait until position is stable

        # measure the precision of the autofocus
        iterations = 30
        self._precision = self.measure_precision(iterations)

        self.sigPlotCalibration.emit(piezo_position, autofocus_signal, p(piezo_position), self._slope, self._precision)

        if self._readout == 'camera' and not self.live_display_enabled:
            self._autofocus_logic.stop_camera_live()

    def measure_precision(self, num_iterations):
        """ Helper function during calibration: measure the position num_iterations-times and calculate the FWHM.
        :param: int num_iterations: number of measurements to perform
        :return: float precision
        """
        centroids = np.empty([num_iterations])
        for i in range(num_iterations):
            centroids[i] = self.read_detector_signal()
            sleep(0.1)  # which waiting time ?
        precision = np.std(centroids) * 2*np.sqrt(2*np.log(2))  # the FWHM
        return precision

    def define_autofocus_setpoint(self):
        """ From the present piezo position, read the detector signal and keep the value as reference for the pid.
        :return: None
        """
        setpoint = self._autofocus_logic.define_pid_setpoint()
        self._setpoint_defined = True
        self.sigSetpointDefined.emit(setpoint)

# Running the autofocus ------------------------------------------------------------------------------------------------
    def start_autofocus(self, stop_when_stable=False, search_focus=False):
        """ This method starts the autofocus. This can only be done if the piezo was calibrated and a setpoint defined.
        A check is also performed in order to make sure there is enough signal detected.

        :param bool stop_when_stable: if True, the autofocus stops automatically when the signal is stabilized.
                                        (little variation during 10 iterations).
                                        default is False: autofocus running continuously until stopped by user.
        :param bool search_focus: boolean variable indicating that an advanced autofocus method using the reflection
                                on the lower interface of the sample's glass slide called the start_autofocus routine.
                                If True, it ensures that the focus is moved back to the sample surface after stabilizing
                                the focus.
                                Only use search_focus = True in combination with stop_when_stable = True,
                                otherwise it has no effect.
        :return: None
        """
        # check if autofocus can be started
        if not self._calibrated:
            self.log.warning('Autofocus not calibrated.')
            self.sigAutofocusError.emit()
            return

        if not self._setpoint_defined:
            self.log.warning('Setpoint not defined.')
            self.sigAutofocusError.emit()
            return

        # autofocus can be started
        self.autofocus_enabled = True
        self.check_autofocus()  # this updates self._autofocus_lost

        if self._autofocus_lost:
            self.log.warning('Autofocus lost! (in start_autofocus')
            if self.rescue:
                success = self.rescue_autofocus()
                if success:
                    self.start_autofocus(stop_when_stable=stop_when_stable, search_focus=search_focus)
                    return
                else:
                    self.autofocus_enabled = False
                    self.log.warning('autofocus signal not found')
                    self.sigAutofocusError.emit()
                    return
            else:
                self.autofocus_enabled = False
                self.sigAutofocusError.emit()
                return

        # all prerequisites ok and signal found
        if self._readout == 'camera' and not self.live_display_enabled:
            self._autofocus_logic.start_camera_live()

        self._autofocus_logic.init_pid()
        self._z0 = self.get_position()
        self._dt = self._autofocus_logic._pid_frequency

        worker = AutofocusWorker(self._dt)
        worker.signals.sigFinished.connect(partial(self.run_autofocus, stop_when_stable=stop_when_stable, search_focus=search_focus))
        self.threadpool.start(worker)

    def run_autofocus(self, stop_when_stable=False, search_focus=False):
        """ Based on the pid output, the position of the piezo is corrected in real time. In order to avoid
        unnecessary movement of the piezo, the corrections are only applied when an absolute displacement >100nm is
        required.

        :param bool stop_when_stable: if True, the autofocus stops automatically when the signal is stabilized.
                                        (little variation during 10 iterations).
                                        default is False: autofocus running continuously until stopped by user.
        :param bool search_focus: boolean variable indicating that an advanced autofocus method using the reflection
                                on the lower interface of the sample's glass slide called the start_autofocus routine.
                                If True, it ensures that the focus is moved back to the sample surface after stabilizing
                                the focus.
                                Only use search_focus = True in combination with stop_when_stable = True,
                                otherwise it has no effect.
        :return: None
        """
        self.check_autofocus()  # updates self._autofocus_lost

        if self.autofocus_enabled:

            if self._autofocus_lost:
                self.log.warning('autofocus lost! in run_autofocus')
                if self.rescue:
                    # to verify: add here stop autofocus ?
                    success = self.rescue_autofocus()
                    if success:
                        self.start_autofocus(stop_when_stable=stop_when_stable, search_focus=search_focus)
                        return
                    else:
                        self.autofocus_enabled = False
                        self.log.warning('autofocus signal not found during rescue autofocus')
                        self.sigAutofocusError.emit()
                        return
                else:
                    self.autofocus_enabled = False
                    self.sigAutofocusError.emit()
                    return

            if stop_when_stable:
                pid, stable = self._autofocus_logic.read_pid_output(True)
                if stable:
                    self.log.info('focus is stable')
                    self.autofocus_enabled = False
                    self.sigAutofocusStopped.emit()
                    if search_focus:
                        self.search_focus_finished()
                    return
            else:
                pid = self._autofocus_logic.read_pid_output(False)

            # calculate the necessary movement of piezo dz
            z = self._z0 + pid / self._slope
            dz = np.absolute(self.get_position() - z)
            # print(f'z is {z}, dz is {dz}')

            if self._min_z + 1 < z < self._max_z - 1:
                if dz > 0.1:
                    self.go_to_position(z)
                else:
                    pass

            else:
                self.log.warning('piezo target position out of constraints')
                self.autofocus_enabled = False
                self.sigAutofocusError.emit()
                if search_focus:
                    self.search_focus_finished()
                return

            worker = AutofocusWorker(self._dt)
            worker.signals.sigFinished.connect(partial(self.run_autofocus, stop_when_stable=stop_when_stable,
                                                       search_focus=search_focus))
            self.threadpool.start(worker)

    def stop_autofocus(self):
        """ Stop the autofocus loop.
        """
        self.autofocus_enabled = False
        if self._readout == 'camera' and not self.live_display_enabled:
            self._autofocus_logic.stop_camera_live()
        self.sigAutofocusStopped.emit()

# ----------------------------------------------------------------------------------------------------------------------
# Advanced methods for autofocus available only with a 3 axes translation stage (here: autofocus_logic_fpga).
# autofocus_logic_camera contains only warning messages that these methods are not available
# ----------------------------------------------------------------------------------------------------------------------

    def calibrate_offset(self):
        """ Calibrate the offset between the sample position and a reference on the bottom of the coverslip. This method
        is inspired from the LSM-Zeiss microscope and is used when the sample (such as embryos) is interfering too much
        with the IR signal and makes the regular focus stabilization unstable.
        :return: None
        """
        offset = self._autofocus_logic.calibrate_offset()
        self.sigOffsetCalibration.emit(offset)

    def update_autofocus_offset_parameters(self, offset, setpoint):
        """ From the gui, it is possible to manually indicate which offset and setpoint should be used for the
        autofocus. This is particularly useful in case the program crashed and the user wants to reuse the same
        parameters.
        :param: float offset & float setpoint values previously saved by the user
        :return: None
        """
        # Define the offset value and display it on the main window
        self.sigOffsetCalibration.emit(offset)
        self._autofocus_logic._focus_offset = offset
        # Define the setpoint value and display it on the main window
        self._setpoint_defined = True
        self.sigSetpointDefined.emit(setpoint)
        self._autofocus_logic._setpoint = setpoint

    def rescue_autofocus(self):
        """ When the autofocus signal is lost, launch a rescuing procedure by using the 3-axes translation stage.
        The stage moves along the z axis until the signal is found.
        :return: bool success: True: rescue was successful, signal was found. False: Signal not found during rescue.
        """
        return self._autofocus_logic.rescue_autofocus()

    def do_piezo_position_correction(self):
        """ When the piezo position is too close to the limits (< 10 um, > 50 um), a slow movement of the translation
        stage is started while autofocus is on, so that piezo will follow back into the central range (to 25 um).
        This method is intended for a use in long automated tasks.
        The autofocus method with readout on a reference plane is used.
        :return: None
        """
        self.piezo_correction_running = True
        self.stop_autofocus()
        success = True

        piezo_pos = self.get_position()

        if (piezo_pos < 10) or (piezo_pos > 50):  # correction necessary
            print('doing piezo position correction.')
            # move to the reference plane
            offset = self._autofocus_logic._focus_offset
            self._autofocus_logic.stage_move_z(offset)
            self._autofocus_logic.stage_wait_for_idle()

            # check if there is enough signal to perform the piezo position correction
            if not self._autofocus_logic.autofocus_check_signal():
                success = self.rescue_autofocus()

            # signal ok, position correction can be done
            if success:
                self.start_autofocus()  # using default conditions for autofocus
                # calculate the relative movement necessary to move piezo to 25 um
                step = np.round(25 - piezo_pos, decimals=3)
                self.sigDoStageMovement.emit(step)
            else:  # no signal found
                self.log.warning('Position correction could not be done because autofocus signal not found!')
                self._autofocus_logic.stage_move_z(-offset)
                self._autofocus_logic.stage_wait_for_idle()
                self.piezo_correction_running = False

        else:  # position does not need to be corrected
            print('no piezo position correction needed..')
            self.piezo_correction_running = False

    def finish_piezo_position_correction(self):
        """ Slot called by the signal sigStageMoved from the autofocus_logic. Handles the stopping of the autofocus
        and resets the indicator variable. Moves also the stage back to the sample surface plane, as the piezo position
        correction method moved it to the reference interface.
        :return: None
        """
        self.stop_autofocus()
        # move stage back to surface plane
        offset = self._autofocus_logic._focus_offset
        self._autofocus_logic.stage_move_z(-offset)
        self._autofocus_logic.stage_wait_for_idle()
        self.piezo_correction_running = False

    def start_search_focus(self):
        """ Search the IR reflection signal on a reference plane at a distance 'offset' from the current position.
        Autofocus is programmatically stopped once the signal was found and is stable.
        This method can only be used when calibrations were correctly made.
        This method is callable from the user interface. A variation is made for systems with 2-axes stages:
        an offset of 0 is considered so that the focus is searched on the usual surface, not at a reference plane.
        This has the same effect as using the start_autofocus method with stop_when_stable=True.
        :return: None
        """
        if self._calibrated and self._setpoint_defined:
            self._stage_is_positioned = False  # set this flag as indicator that the search focus procedure is running
            offset = self._autofocus_logic._focus_offset
            if offset != 0:
                self._autofocus_logic.stage_move_z(offset)
                self._autofocus_logic.stage_wait_for_idle()
                sleep(1)
            self.start_autofocus(stop_when_stable=True, search_focus=True)
        else:
            self.log.warn('Search focus can not be used. Calibration or setpoint missing.')
            self.sigFocusFound.emit()  # signal is sent although focus not found, just to reset toolbutton state

    def search_focus_finished(self):
        """ Ensure the return of the 3-axes stage to the surface plane after finding focus based on the signal on
        a reference plane.
        :return: None
        """
        offset = self._autofocus_logic._focus_offset
        if offset != 0:
            self._autofocus_logic.stage_move_z(-offset)
            self._autofocus_logic.stage_wait_for_idle()
        self._stage_is_positioned = True
        self.sigFocusFound.emit()

# ----------------------------------------------------------------------------------------------------------------------
# Methods to handle the user interface state
# ----------------------------------------------------------------------------------------------------------------------

    def disable_focus_actions(self):
        """ This method provides a security to avoid all focus / autofocus related toolbar actions from GUI,
        for example during Tasks. """
        self.sigDisableFocusActions.emit()
        sleep(0.5)

    def enable_focus_actions(self):
        """ This method resets all focus related toolbar actions on GUI to callable state, for example after Tasks. """
        self.sigEnableFocusActions.emit()
        sleep(0.5)
