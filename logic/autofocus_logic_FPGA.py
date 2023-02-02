# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains the logic for the autofocus with quadrant photo diode (QPD)
based readout.

An extension to Qudi.

@authors: JB. Fiche, F. Barho
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
from core.util.mutex import Mutex
from logic.generic_logic import GenericLogic
from qtpy import QtCore

import numpy as np
from numpy.polynomial import Polynomial as Poly
from time import sleep


class AutofocusLogic(GenericLogic):
    """ Logic class to control the autofocus using QPD-based readout. Connected hardware is an FPGA that
    handles the signal readout of the QPD, and a 3 axes translation stage. Moreover, a Thorlabs camera is connected
    for visual support, without processing its image.

    An autofocus logic class is needed as connector to the focus logic.

    autofocus_logic:
        module.Class: 'autofocus_logic_FPGA.AutofocusLogic'
        autofocus_ref_axis : 'X' # 'Y'
        proportional_gain : 0.1 # in %%
        integration_gain : 1 # in %%
        exposure = 0.001
        connect:
            camera : 'thorlabs_camera'
            fpga: 'nifpga'
            stage: 'ms2000'
    """
    # declare connectors
    fpga = Connector(interface='Base')
    stage = Connector(interface='MotorInterface')
    camera = Connector(interface='CameraInterface')

    # camera attributes
    _exposure: float = ConfigOption('exposure', 0.001, missing='warn')
    _camera_acquiring: bool = False
    _threshold: float = 0  # for compatibility with focus logic, not used

    # autofocus attributes
    _default_focus_offset: float = ConfigOption('focus_offset', 0, missing='warn')
    _ref_axis: str = ConfigOption('autofocus_ref_axis', 'X', missing='warn')
    _autofocus_stable: bool = False
    _autofocus_iterations: int = 0
    _focus_offset: float = 0 # Set to zero until the calibration is performed

    # autofocus parameters for stabilization
    _num_points_fit = ConfigOption('num_points_fit', 10, missing='warn')
    _stable_threshold = ConfigOption('stabilization_threshold', 1, missing='warn')
    _target_tolerance = ConfigOption('target_tolerance', 10, missing='warn')

    # pid attributes
    _pid_frequency: float = 0  # in s, frequency of autofocus PID (to make sure there is a new measure for the FPGA)
    _P_gain: float = ConfigOption('proportional_gain', 0, missing='warn')
    _I_gain: float = ConfigOption('integration_gain', 0, missing='warn')
    _setpoint: float = 0

    # signals
    sigOffsetDefined = QtCore.Signal()
    sigStageMoved = QtCore.Signal()

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self._fpga = None
        self._stage = None
        self._camera = None
        self._last_pid_output_values: list = []
        self.X_stabilization: list = []

    def on_activate(self):
        """ Initialisation performed during activation of the module.
        """
        # hardware connections
        self._fpga = self.fpga()
        self._stage = self.stage()
        self._camera = self.camera()

        # initialize the camera
        self._camera.set_exposure(self._exposure)

        # initialize the pid array for stabilization
        self._last_pid_output_values = np.zeros((self._num_points_fit,))
        self.X_stabilization = np.linspace(0, self._num_points_fit - 1, num=self._num_points_fit)

    def on_deactivate(self):
        """ Required deactivation.
        """
        self.stop_camera_live()

# ======================================================================================================================
# Public methods for the autofocus, used by all the techniques (camera or FPGA/QPD based readout)
# ======================================================================================================================
        
    def read_detector_signal(self):
        """ This method reads the reference signal for the autofocus correction. In the case of the
        method using a FPGA, it returns the QPD signal measured along the reference axis.
        :return: float: coordinate of the QPD signal on the reference axis  # verify type: float or int ?
        """
        return self.qpd_read_position()

    # fpga only
    def read_detector_intensity(self):
        """ Function used for the focus search. The intensity of the reflection is measured (instead of its x or y
        position which is read in read_detector_signal.
        :return: int: intensity of the QPD signal
        """
        return self.qpd_read_sum()

    def autofocus_check_signal(self):
        """ Check that the intensity detected by the QPD is above a specific threshold (300) If the signal is too low,
        the function returns False to indicate that the autofocus signal is lost.
        :return bool: True: signal ok, False: signal too low
        """
        qpd_sum = self.qpd_read_sum()
        if qpd_sum < 300:
            print("Autofocus check signal is too low : SUM = {}".format(qpd_sum))
            return False
        else:
            return True

    def init_pid(self):
        """ Initialize the pid for the autofocus, and reset the number of autofocus iterations.
        @return: None
        """
        # self.qpd_reset()
        self._fpga.init_pid(self._P_gain, self._I_gain, self._setpoint, self._ref_axis)
        self.set_worker_frequency()

        self._autofocus_stable = False
        self._autofocus_iterations = 0

    def define_pid_setpoint(self):
        """ Initialize the pid setpoint and save it as a class attribute.
        @return float: setpoint
        """
        self.qpd_reset()
        self._setpoint = self.read_detector_signal()
        return self._setpoint

    def read_pid_output(self, do_stabilization_check, stop_at_target):
        """ Read the pid output signal in order to adjust the position of the objective.
        @param: bool do_stabilization_check: if True, the last 10 pid output values are stored and fitted.
        @return tuple (float, bool): pid_output, stop autofocus?
        """
        pid_output = self._fpga.read_pid()

        if do_stabilization_check:
            self._autofocus_iterations += 1
            self._last_pid_output_values = np.concatenate(
                (self._last_pid_output_values[1:self._num_points_fit], [pid_output]))
            # self._last_pid_output_values = np.concatenate((self._last_pid_output_values[1:10], [pid_output]))
            return pid_output, self.check_stabilization()
        elif stop_at_target:
            return pid_output, np.abs(self._setpoint - self.read_detector_signal()) < self._target_tolerance
        else:
            return pid_output, False

    def check_stabilization(self):
        """ Check for the stabilization of the focus. If at least 10 values of pid readout are present, a linear fit
        is performed. If the slope is sufficiently low, the autofocus is considered as stable. The class attribute
        self._autofocus_stable is updated by this function.
        @return: bool: is the autofocus stable ?
        """
        if self._autofocus_iterations > self._num_points_fit:
            # p = Poly.fit(np.linspace(0, 4, num=5), self._last_pid_output_values, deg=1)
            # slope = (p(4) - p(0))/10
            p = Poly.fit(self.X_stabilization, self._last_pid_output_values, deg=1)
            slope = p(self._num_points_fit - 1) - p(0)
            if np.absolute(slope) < self._stable_threshold:
                self._autofocus_stable = True
            else:
                self._autofocus_stable = False

        return self._autofocus_stable

    def start_camera_live(self):
        """ Launch live acquisition of the camera.
        :return: None
        """
        self._camera.start_live_acquisition()
        self._camera_acquiring = True

    def stop_camera_live(self):
        """ Stop live acquisition of the camera.
        :return: None
        """
        self._camera.stop_acquisition()
        self._camera_acquiring = False

    def get_latest_image(self):
        """ Get the latest acquired image from the camera.
        :return: np.ndarray im: most recent image from the camera
        """
        im = self._camera.get_acquired_data()
        return im

# ======================================================================================================================
# Advanced methods for autofocus available only with a 3 axes translation stage (here: autofocus_logic_fpga)
# ======================================================================================================================

    def calibrate_offset(self):
        """ Calibrate the offset between the sample position and a reference on the bottom of the coverslip. This method
        is inspired from the LSM-Zeiss microscope and is used when the sample (such as embryos) is interfering too much
        with the IR signal and makes the regular focus stabilization unstable.
        :return: float offset: distance to the sample plane where a maximum signal was found
        """
        self.stage_wait_for_idle()
        # Read the stage position
        z_up = self._stage.get_pos()['z']
        offset = self._default_focus_offset

        # Move the stage by the default offset value along the z-axis
        self.stage_move_z(offset)
        self.stage_wait_for_idle()

        # rescue autofocus when no signal detected
        if not self.autofocus_check_signal():
             self.rescue_autofocus()

        # Look for the position with the maximum intensity - for the QPD the SUM signal is used.
        max_sum = 0
        z_range = 50  # in µm
        z_step = 1  # in µm

        self.stage_move_z(-z_range/2)
        self.stage_wait_for_idle()
        # max_qpd_pos = self.read_detector_signal()
        n_step = int(z_range/z_step)

        for n in range(n_step):

            self.stage_move_z(z_step)
            self.stage_wait_for_idle()
            # sleep(0.1)

            # qpd_sum[n] = self.read_detector_intensity()
            # qpd_pos[n] = self.read_detector_signal()
            # print("SUM={} - POS={}".format(qpd_sum, qpd_pos))
            # if np.abs(qpd_pos) < max_qpd_pos :
            #     max_qpd_pos = np.abs(qpd_pos)
            # elif np.abs(qpd_pos) > max_qpd_pos and qpd_sum>400:
            #     break

            qpd_sum = self.read_detector_intensity()
            print("SUM={}".format(qpd_sum))
            if qpd_sum > max_sum:
                max_sum = qpd_sum
            elif qpd_sum < max_sum and max_sum > 400:
                break

        # Calculate the offset for the stage
        offset = self._stage.get_pos()['z'] - z_up
        offset = np.round(offset, decimals=1)

        # Send signal to focus logic that will be linked to define_autofocus_setpoint. The autofocus setpoint is defined
        # on the bottom of the coverslip, at the oil/glass interface
        self.sigOffsetDefined.emit()

        # avoid moving stage while QPD signal is read
        sleep(0.5)

        # move the stage back to its original position
        self.stage_move_z(-offset)
        self.stage_wait_for_idle()

        # save the offset
        self._focus_offset = offset
        return offset

    def rescue_autofocus(self):
        """ When the autofocus signal is lost, launch a rescuing procedure by using the 3-axes translation stage.
        The stage moves along the z axis until the signal is found.
        :return: bool success: True: rescue was successful, signal was found. False: Signal not found during rescue.
        """
        success = False
        z_range = 40  # in µm - starting range for the search
        z_step = 1  # in µm

        while not self.autofocus_check_signal() and z_range <= 80:

            print(f"Search range is dz={z_range}µm")
            self.stage_move_z(z_range/2)  # positive value =  the objective is going down
            self.stage_wait_for_idle()

            for z in range(z_range):
                self.stage_move_z(-z_step)
                self.stage_wait_for_idle()

                if self.autofocus_check_signal():
                    success = True
                    print("autofocus signal found!")
                    return success

            if not self.autofocus_check_signal():
                self.stage_move_z(z_range/2)
                self.stage_wait_for_idle()
                z_range += 20

        # This final check is necessary if the autofocus if the signal is detected between to iteration of the while
        # loop
        if self.autofocus_check_signal():
            print("autofocus signal found!")
            success = True
        else:
            print('rescue finished without finding the focus position')

        return success

    def stage_move_z(self, step):
        """ Do a relative movement of the translation stage.
        :param: float step: target relative movement
        :return: None
        """
        self._stage.move_rel({'z': step})

    def stage_wait_for_idle(self):
        """ This method waits that the connected translation stage is in idle state.
        :return: None
        """
        self._stage.wait_for_idle()
        # pos = self._stage.get_pos()
        # print("stage position : {}".format(pos))

    def do_position_correction(self, step):
        """ This method handles the stage movement which is needed to perform the piezo position correction routine.
        The autofocus has been switched on in the focus_logic. The stage moves with a low velocity, to ensure
        that the piezo can follow. After the relative movement, the stage velocity is reset to its default value
        and a signal is emitted to inform the focus logic that the stage reached its target position.
        :param: float step: target relative movement
        :return: None
        """
        self._stage.set_velocity({'z': 0.0025})
        self.stage_wait_for_idle()
        self.stage_move_z(step)
        self.stage_wait_for_idle()
        self._stage.set_velocity({'z': 1.9})
        self.sigStageMoved.emit()

# ======================================================================================================================
# private methods for QPD-based autofocus
# ======================================================================================================================

    def qpd_read_position(self):
        """ Read the QPD signal from the FPGA. The signal is read from X/Y positions. In order to make sure we are
        always reading from the latest piezo position, the method is waiting for a new count.
        :return: float: QPD signal position projected along the x or y axis according to reference axis set in the
                        configuration    # check return type: int or float ?
        """
        qpd = self._fpga.read_qpd()
        last_count = qpd[3]
        while last_count == qpd[3]:
            qpd = self._fpga.read_qpd()
            sleep(0.01)

        if self._ref_axis == 'X':
            return qpd[0]
        elif self._ref_axis == 'Y':
            return qpd[1]

    def qpd_read_sum(self):
        """ Read the sum signal from the QPD.
        :return: float: intensity of the QPD signal   # check return type: int or float ?
        """
        qpd = self._fpga.read_qpd()
        return qpd[2]

    def set_worker_frequency(self):
        """ Update the worker frequency according to the iteration time of the fpga, and store it as a class attribute
        self._pid_frequency
        @return: None
        """
        qpd = self._fpga.read_qpd()
        self._pid_frequency = qpd[4] / 1000 + 0.01

    def qpd_reset(self):
        """ Reset the QPD counter>
        :return: None
        """
        self._fpga.reset_qpd_counter()
