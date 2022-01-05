# -*- coding: utf-8 -*-
"""
Qudi-CBS

This file contains a class for the NI-FPGA.

An extension to Qudi.

@author: F. Barho, JB. Fiche
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
from nifpga import Session
from time import sleep

from core.module import Base
from interface.lasercontrol_interface import LasercontrolInterface
from core.configoption import ConfigOption


class Nifpga(Base, LasercontrolInterface):
    """ National Instruments FPGA that controls the lasers via an OTF.

    Example config for copy-paste:

    nifpga:
        module.Class: 'fpga.ni_fpga.Nifpga'
        resource: 'RIO0'
        default_bitfile: 'C:\\Users\\sCMOS-1\\qudi-cbs\\hardware\\fpga\\FPGA\\FPGA Bitfiles\\FPGAv0_FPGATarget_QUDIQPDPIDlaserc_kWY0ujWrcbM.lvbitx' # Associated to QUDI_QPD_PID_laser_control.vi
        wavelengths:
            - '405 nm'
            - '488 nm'
            - '561 nm'
            - '640 nm'
        registers_laser:
            - '405'
            - '488'
            - '561'
            - '640'
            - 'Update lasers'
        registers_qpd:
            - 'X'
            - 'Y'
            - 'Sum'
            - 'counter'
            - 'duration_ms'
        registers_autofocus:
            - 'setpoint'
            - 'P'
            - 'I'
            - 'reset'
            - 'autofocus'
            - 'ref_axis'
            - 'output'
        registers_general:
            - 'stop'
            - 'integration_time_us'
            - 'reset_counter'

            # registers represent something like channels..
            # The link between registers and the physical channel is made in the labview file from which the bitfile is generated.
    """
    # config options
    resource = ConfigOption('resource', None, missing='error')
    default_bitfile = ConfigOption('default_bitfile', None, missing='error')
    _wavelengths = ConfigOption('wavelengths', None, missing='warn')
    _registers_laser = ConfigOption('registers_laser', None, missing='warn')
    _registers_qpd = ConfigOption('registers_qpd', None, missing='warn')
    _registers_autofocus = ConfigOption('registers_autofocus', None, missing='warn')
    _registers_general = ConfigOption('registers_general', None, missing='warn')

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self.session = None
        self.laser1_control = None
        self.laser2_control = None
        self.laser3_control = None
        self.laser4_control = None
        self.update = None
        self.qpd_x_read = None
        self.qpd_y_read = None
        self.qpd_i_read = None
        self.counter = None
        self.duration_ms = None
        self.stop = None
        self.integration_time_us = None
        self.reset_counter = None
        self.setpoint = None
        self.p_gain = None
        self.i_gain = None
        self.reset = None
        self.autofocus = None
        self.ref_axis = None
        self.output = None

    def on_activate(self):
        """ Required initialization steps when module is called.
        The bitfile registers are linked to class variables here. """
        self.session = Session(bitfile=self.default_bitfile, resource=self.resource)

        # make the bitfile registers accessible from python module
        if self._wavelengths is not None:

            self.laser1_control = self.session.registers[self._registers_laser[0]]
            self.laser2_control = self.session.registers[self._registers_laser[1]]
            self.laser3_control = self.session.registers[self._registers_laser[2]]
            self.laser4_control = self.session.registers[self._registers_laser[3]]
            self.update = self.session.registers[self._registers_laser[4]]
            self.session.reset()
            for i in range(len(self._registers_laser)-1):
                self.apply_voltage(0, self._registers_laser[i])  # set initial value to each channel

        if self._registers_qpd is not None:

            self.qpd_x_read = self.session.registers[self._registers_qpd[0]]
            self.qpd_y_read = self.session.registers[self._registers_qpd[1]]
            self.qpd_i_read = self.session.registers[self._registers_qpd[2]]
            self.counter = self.session.registers[self._registers_qpd[3]]
            self.duration_ms = self.session.registers[self._registers_qpd[4]]

            self.stop = self.session.registers[self._registers_general[0]]
            self.integration_time_us = self.session.registers[self._registers_general[1]]
            self.reset_counter = self.session.registers[self._registers_general[2]]

            self.setpoint = self.session.registers[self._registers_autofocus[0]]
            self.p_gain = self.session.registers[self._registers_autofocus[1]]
            self.i_gain = self.session.registers[self._registers_autofocus[2]]
            self.reset = self.session.registers[self._registers_autofocus[3]]
            self.autofocus = self.session.registers[self._registers_autofocus[4]]
            self.ref_axis = self.session.registers[self._registers_autofocus[5]]
            self.output = self.session.registers[self._registers_autofocus[6]]

            self.stop.write(False)
            self.integration_time_us.write(10)
        self.session.run()

    def on_deactivate(self):
        """ Required deactivation steps. Set the voltage for all laserlines to 0 and close the FPGA session. """
        for i in range(len(self._registers_laser)-1):
            self.apply_voltage(0, self._registers_laser[i])   # make sure to switch the lasers off before closing the session

        self.stop.write(True)
        self.session.close()

# ----------------------------------------------------------------------------------------------------------------------
# Functions for autofocus (QPD signal)
# ----------------------------------------------------------------------------------------------------------------------

    def read_qpd(self):
        """ read QPD signal and return a list containing the X,Y position of the spot, the SUM signal,
        the number of counts (iterations) since the session was launched and the duration of each iteration.

        :return list [x_value, y_value, i_value, count, duration]
        """
        # This modification was added to make sure the signal measured from the qpd is related to the actual position of
        # the stage (and not a previous one). The signal from the qpd is indeed average out, and it takes ~30ms between
        # each new measurement.
        count_t0 = self.counter.read()
        n_attempt = 0

        while self.counter.read() == count_t0 and n_attempt < 100:
            sleep(0.005)
            n_attempt += 1

        if n_attempt == 100:
            print('ni_fpga.py : FPGA counter is stuck or communication is lost')

        x_value = self.qpd_x_read.read()
        y_value = self.qpd_y_read.read()
        i_value = self.qpd_i_read.read()
        count = self.counter.read()
        duration = self.duration_ms.read()

        return [x_value, y_value, i_value, count, duration]

    def reset_qpd_counter(self):
        """ Reset the counter register of the default bitfile to 0.

        :return: None """
        self.reset_counter.write(True)

    def init_pid(self, p_gain, i_gain, setpoint, ref_axis):
        """ Initialize the PID settings for the autofocus.
        :param: float p_gain: proportional gain for the PID
        :param: float i_gain: integral gain for the PID
        :param: float setpoint: autofocus setpoint (position of the IR spot along the reference axis)
        :param: str ref_axis: identifier of the reference axis 'X' or 'Y'

        :return: None
        """
        self.reset_qpd_counter()
        self.setpoint.write(setpoint)
        self.p_gain.write(p_gain)
        self.i_gain.write(i_gain)
        if ref_axis == 'X':
            self.ref_axis.write(True)
        elif ref_axis == 'Y':
            self.ref_axis.write(False)
        self.reset.write(True)
        self.autofocus.write(True)
        sleep(0.1)
        self.reset.write(False)

    def update_pid_gains(self, p_gain, i_gain):
        """ Set new values as PID parameters.
        :param: float p_gain: proportional gain for the PID
        :param: float i_gain: integral gain for the PID

        :return: None
        """
        self.p_gain.write(p_gain)
        self.i_gain.write(i_gain)

    def read_pid(self):
        """ Read the output of the PID regulation.
        :return: float pid_output
        """
        pid_output = self.output.read()
        return pid_output

    def stop_pid(self):
        """ Stop the pid regulation.
        :return: None
        """
        self.autofocus.write(False)

# ----------------------------------------------------------------------------------------------------------------------
# Lasercontrol Interface functions
# ----------------------------------------------------------------------------------------------------------------------

    def apply_voltage(self, voltage, channel):
        """ Writes a voltage to the specified channel.

        :param: float voltage: percent of maximal voltage value to be applied.
                            If voltage < 0 or voltage > 100, the value will be rescaled to be in the allowed range.
        :param: str channel: register name corresponding to the physical channel (link made in labview bitfile),
                            example '405'

        :return: None
        """
        value = max(0, voltage)
        conv_value = self.convert_value(value)
        if channel == self._registers_laser[0]:  # '405'
            self.laser1_control.write(conv_value)
        elif channel == self._registers_laser[1]:  # '488'
            self.laser2_control.write(conv_value)
        elif channel == self._registers_laser[2]:  # '561'
            self.laser3_control.write(conv_value)
        elif channel == self._registers_laser[3]:  # '640'
            self.laser4_control.write(conv_value)
        else:
            pass
        self.update.write(True)

    def get_dict(self):
        """ Retrieves the channel name and the voltage range for each analog output for laser control from the
        configuration file and associates it to the laser wavelength which is controlled by this channel.

        :return: dict laser_dict
        """
        laser_dict = {}

        for i, item in enumerate(
                self._wavelengths):  # use any of the lists retrieved as config option, just to have an index variable
            label = 'laser{}'.format(i + 1)  # create a label for the i's element in the list starting from 'laser1'

            dic_entry = {'label': label,
                         'wavelength': self._wavelengths[i],
                         'channel': self._registers_laser[i]
                         }

            laser_dict[dic_entry['label']] = dic_entry

        return laser_dict

# ----------------------------------------------------------------------------------------------------------------------
# Helper functions for Lasercontrol Interface functions
# ----------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def convert_value(value):
        """ Helper function: fpga needs int16 (-32768 to + 32767) data format:
        do rescaling of value to apply in percent of max value.

        Apply min function to limit the allowed range.
        :param: float value: value in percent of maximum laser output to apply

        :return: int converted value in the range int16
        """
        return min(int(value/100*(2**15-1)), 32767)  # set to maximum in case value > 100

    def read_values(self):
        """ for tests - returns the (converted) values applied to the registers """
        return self.laser1_control.read(), self.laser2_control.read(), self.laser3_control.read(), self.laser4_control.read()

# ----------------------------------------------------------------------------------------------------------------------
# Functions to handle FPGA sessions associated to different bitfiles
# ----------------------------------------------------------------------------------------------------------------------

    def close_default_session(self):
        """ This method is called before another bitfile than the default one shall be loaded.
        :return: None
        """
        for i in range(len(self._registers_laser)):
            self.apply_voltage(0, self._registers_laser[i])  # make sure to switch the lasers off before closing the session
        self.session.close()

    def restart_default_session(self):
        """ This method allows to restart the default session.
        :return: None
        """
        self.on_activate()

    def start_task_session(self, bitfile):
        """ This method loads a bitfile used for a specific task.
        :param: str bitfile: complete path to the bitfile used for the new session
        :return: None
        """
        self.session = Session(bitfile=bitfile, resource=self.resource)

    def end_task_session(self):
        """ Close the current task session.
        :return: None
        """
        self.session.close()

# ----------------------------------------------------------------------------------------------------------------------
# Methods for specific tasks (such as experiments with synchronized piezo positioning, camera and lightsource)
# using a specific bitfile. It is needed to define all new register names that are used in the bitfile.
# ----------------------------------------------------------------------------------------------------------------------

    def run_test_task_session(self, data):
        """ Starts an exemplary session used during development. (Control of a single laser line)
        Serves as example when adding new run_.._session methods.
        Associated bitfile 'C:\\Users\\sCMOS-1\\qudi-cbs\\hardware\\fpga\\FPGA\\FPGA Bitfiles\\FPGAv0_FPGATarget_FPGAlasercontrol_pdDEc3yii+w.lvbitx'
        :param: list data: values to be applied to the output (in % of max intensity)
        :return: None
        """
        # using for a simple test the FPGA_laser_control_Qudi bitfile (control only for the 561 nm laser)
        n_lines = self.session.registers['N']
        laser_control = self.session.registers['561 Laser Power']
        self.session.reset()

        # print(n_lines.read())
        n_lines.write(5)
        # print(n_lines.read())

        conv_values = [self.convert_value(item) for item in data]
        # print(conv_values)
        laser_control.write(conv_values)
        self.session.run()

    def run_multicolor_imaging_task_session(self, z_planes, wavelength, values, num_laserlines, exposure_time_ms):
        """ Allows to access the parameters of the bitfile used in multicolor stack imaging experiments.
        Associated bitfile 'C:\\Users\\sCMOS-1\\qudi-cbs\\hardware\\fpga\\FPGA\\FPGA Bitfiles\\FPGAv0_FPGATarget_QudiHiMQPDPID_sHetN0yNJQ8.lvbitx'
        :param: int z_planes: number of z planes in a stack
        :param: int list wavelength: list of length 5 containing the identifier number of the laser line to be addressed:
                                        0: BF, 1: 405, 2: 488, 3: 561, 4: 640
                                        (elements in the list at index > num_laserlines are ignored)
        :param: float list values: list of length 5 containing the intensity in per cent to be applied to the line
                                    given at the same index in the wavelength list
                                    (elements in the list at index > num_laserlines are ignored)
        :param: int num_laserlines: number of channels from which images are to be taken
        :param: float exposure_time_ms: exposure time used during the experiment in ms

        :return: None
        """
        # make session registers accessible
        num_lines = self.session.registers['N laser lines']  # number of laser lines
        num_z_pos = self.session.registers['N Z positions']  # number of z positions
        num_images_acquired = self.session.registers['Images acquired']  # indicator register how many images have been acquired
        laser_lines = self.session.registers['Laser lines']  # list containing numbers of the laser lines which should be addressed
        laser_power = self.session.registers['Laser power']  # list containing the intensity in % to apply (to the element at the same index in laser_lines list
        stop = self.session.registers['stop']
        exposure = self.session.registers['exposure_time_ms']  # integer indicating the exposure time of the camera in ms

        # reuse the class attributes for QPD, general and autofocus related registers
        self.qpd_x_read = self.session.registers[self._registers_qpd[0]]
        self.qpd_y_read = self.session.registers[self._registers_qpd[1]]
        self.qpd_i_read = self.session.registers[self._registers_qpd[2]]
        self.counter = self.session.registers[self._registers_qpd[3]]
        self.duration_ms = self.session.registers[self._registers_qpd[4]]

        self.stop = self.session.registers[self._registers_general[0]]
        self.integration_time_us = self.session.registers[self._registers_general[1]]
        self.reset_counter = self.session.registers[self._registers_general[2]]

        self.setpoint = self.session.registers[self._registers_autofocus[0]]
        self.p_gain = self.session.registers[self._registers_autofocus[1]]
        self.i_gain = self.session.registers[self._registers_autofocus[2]]
        self.reset = self.session.registers[self._registers_autofocus[3]]
        self.autofocus = self.session.registers[self._registers_autofocus[4]]
        self.ref_axis = self.session.registers[self._registers_autofocus[5]]
        self.output = self.session.registers[self._registers_autofocus[6]]

        self.stop.write(False)
        self.integration_time_us.write(10)

        # reset session, apply new values and restart it
        self.session.reset()

        conv_values = [self.convert_value(item) for item in values]
        num_lines.write(num_laserlines)
        # print(num_laserlines)
        num_z_pos.write(z_planes)
        # print(z_planes)
        laser_lines.write(wavelength)
        # print(wavelength)
        laser_power.write(conv_values)
        # print(conv_values)
        stop.write(False)
        # print("exposure time = " + str(exposure_time_ms))
        exposure_time = int(exposure_time_ms * 1000 * 2)
        exposure.write(exposure_time)

        self.session.run()
