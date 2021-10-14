# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains a class representing a Lumencor celesta laser source.

An extension to Qudi.

@author: JB.Fiche

Created on Thur June 24 2021
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
import urllib.request
from core.module import Base
from core.configoption import ConfigOption
from interface.lasercontrol_interface import LasercontrolInterface
from time import sleep


class LumencorCelesta(Base, LasercontrolInterface):
    """ Class representing the Lumencor celesta laser source.

    Example config for copy-paste:

    celesta:
        module.Class: 'laser.lumencor_celesta.LumencorCelesta'
        ip: '192.168.201.200'
        wavelengths :
            - "405"
            - "446"
            - "477"
            - "520"
            - "546"
            - "638"
            - "749"
    """

    # config options
    _ip = ConfigOption('ip', missing='error')
    _wavelengths = ConfigOption('wavelengths', missing='error')

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self.laser_lines = {}

    def on_activate(self):
        """ Initialization: test whether the celesta is connected
        """
        try:
            message = self.lumencor_httpcommand(self._ip, 'GET VER')
            print('Lumencor source version {} was found'.format(message['message']))
        except Exception:
            self.log.warning('Lumencor celesta laser source was not found - HTTP connection was not possible')

    def on_deactivate(self):
        """ Close serial port when deactivating the module.
        """
        self.zero_all()
        self.set_ttl(False)

# ----------------------------------------------------------------------------------------------------------------------
# Celesta status functions
# ----------------------------------------------------------------------------------------------------------------------

    def status(self):
        """ Ask for the laser source status (0:OK - 6:Standby - 7:Warming up - 1/2/3/4/5:Errors)
        """
        message = self.lumencor_httpcommand(self._ip, 'GET STAT')
        status = message['message']

        if status.find('A STAT') == -1:
            self.log.warning('Communication with the Celesta is currently impossible')
        elif status == 'A STAT 1' or status == 'A STAT 2' or status == 'A STAT 3':
            self.log.warning('There is an issue with the celesta source : overheating')
        return status

    def wakeup(self):
        """ Wake up the celesta source when it is in standby mode and wait for the warmup procedure to be done
        """
        self.lumencor_httpcommand(self._ip, 'WAKEUP')
        self.log.warning('Celesta is in stand-by mode. Launching warming-up procedure ... wait a few seconds')
        status = self.status()
        while status == 'A STAT 7':
            sleep(0.5)
            status = self.status()
        self.log.info('Celesta laser source is ready!')

# ----------------------------------------------------------------------------------------------------------------------
# Lasercontrol Interface functions
# ----------------------------------------------------------------------------------------------------------------------

    def apply_voltage(self, intensity, laser_on):
        """ Writes a voltage to the specified channel. Historical name since the intensity of laser is usually
        controlled through an AOTF. However in this case, the laser selection and intensity control is allowed by
        directly communicating with the laser source.

        :param: float voltage: voltage value to be applied
        :param: str channel: analog output line such as /Dev1/AO0

        :return: None
        """

        # check whether the laser source is in stand-by mode
        status = self.status()
        if status == "A STAT 6":
            self.wakeup()

        # define the intensity for each line
        self.set_intensity_all_laser_lines(intensity)

        # switch ON only the lines with an intensity > 0
        self.set_state_all_laser_lines(laser_on)

    def get_dict(self):
        """ Retrieves the channel name and the voltage range for each analog output for laser control from the
        configuration file and associates it to the laser wavelength which is controlled by this channel.

        Make sure that the config contains all the necessary elements.

        :return: dict laser_dict
        """
        laser_dict = {}

        for i, item in enumerate(
                self._wavelengths):  # use any of the lists retrieved as config option, just to have an index variable
            label = 'laser{}'.format(i + 1)  # create a label for the i's element in the list starting from 'laser1'

            dic_entry = {'label': label,
                         'wavelength': self._wavelengths[i],
                         'channel': i}

            laser_dict[dic_entry['label']] = dic_entry

        return laser_dict

# ----------------------------------------------------------------------------------------------------------------------
# Getter and setter functions
# ----------------------------------------------------------------------------------------------------------------------

    def get_laserline_intensity(self):
        """ Return the intensity of all laser lines

            intensity : array of int - indicate the intensity of each laser line
        """
        message = self.lumencor_httpcommand(self._ip, 'GET MULCHINT')
        intensity = [int(s) for s in message['message'].split() if s.isdigit()]

        return intensity

    def get_laserline_state(self):
        """ Return the status of all laser lines

            status : array of int - indicate the status of each laser line (1=ON, 0=OFF)
        """
        message = self.lumencor_httpcommand(self._ip, 'GET MULCH')
        status = [int(s) for s in message['message'].split() if s.isdigit()]

        return status

    def stop_all(self):
        """ Set all laser lines to zero.
        """
        self.lumencor_httpcommand(self._ip, 'SET MULCH 0 0 0 0 0 0 0')

    def set_ttl(self, ttl_state):
        """ Define whether the celesta source can be controlled through ttl control.

            ttl_state : boolean - indicate whether to allow external trigger control of the source
        """
        if ttl_state:
            self.lumencor_httpcommand(self._ip, 'SET TTLENABLE 1')
        else:
            self.lumencor_httpcommand(self._ip, 'SET TTLENABLE 0')

    def set_intensity_selected_laser_lines(self, wavelength, intensity):
        """ Set laser line intensity to a given value

            wavelength : array of string - indicate the selected laser line
            intensity : array of int - indicate the laser power (in per thousand)
        """
        laser_lines_intensity = self.get_laserline_intensity()

        for n in range(len(wavelength)):
            channel_wavelength = wavelength[n]
            channel_intensity = intensity[n]
            if self.laser_check[channel_wavelength]:
                line = self.laser_lines[channel_wavelength]
                laser_lines_intensity[line] = channel_intensity

        self.set_intensity_all_laser_lines(laser_lines_intensity)

    def set_intensity_all_laser_lines(self, intensity):
        """ Set the intensity of all laser lines at oonce

            intensity : array of int - indicate the laser power (in per thousand)
        """
        command = 'SET MULCHINT {}'.format(' '.join(map(str, intensity)))
        self.lumencor_httpcommand(self._ip, command)

    def set_selected_laser_line_on_off(self, wavelength, state):
        """ Switch specified laser line to ON or OFF

            wavelength : array of string - indicate the selected laser line
            state : array of int - indicate 0 to switch OFF the specified line, or 1 to switch it ON.
        """
        laser_lines_state = self.get_laserline_state()

        for n in range(len(wavelength)):
            channel_wavelength = wavelength[n]
            channel_state = state[n]
            if self.laser_check[channel_wavelength]:
                line = self.laser_lines[channel_wavelength]
                laser_lines_state[line] = channel_state

        self.set_state_all_laser_lines(laser_lines_state)

    def set_state_all_laser_lines(self, state):
        """ Switch all laser lines to the specified state ON or OFF

            state : array of int - indicate 0 to switch OFF the specified line, or 1 to switch it ON.
        """
        command = 'SET MULCH {}'.format(' '.join(map(str, state)))
        self.lumencor_httpcommand(self._ip, command)

# ----------------------------------------------------------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------------------------------------------------------

    def lumencor_httpcommand(self, ip, command):
        """
        Sends commands to the lumencor system via http.
        Please find commands here:
        http://lumencor.com/wp-content/uploads/sites/11/2019/01/57-10018.pdf
        """
        command_full = r'http://' + ip + '/service/?command=' + command.replace(' ', '%20')
        with urllib.request.urlopen(command_full) as response:
            message = eval(response.read())  # the default is conveniently JSON so eval creates dictionary
            if message['message'][0] == 'E':
                self.log.warning('An error occurred - the command was not recognized')

        return message
