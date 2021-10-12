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
import numpy as np
from core.module import Base
from core.configoption import ConfigOption


class LumencorCelesta(Base):
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
            - "750"
        allowed_wavelengths :
            - True
            - False
            - True
            - False
            - True
            - True
            - True

    """

    # config options
    _ip = ConfigOption('ip', missing='error')
    _wavelengths = ConfigOption('wavelengths', missing='error')
    _allowed_wavelengths = ConfigOption('allowed_wavelengths', missing='error')

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self.laser_check = {}
        self.laser_lines = {}

    def on_activate(self):
        """ Initialization: test whether the celesta is connected
        """
        self.laser_check = dict(zip(self._wavelengths, self._allowed_wavelengths))
        self.laser_lines = dict(zip(self._wavelengths, np.linspace(0, 6, num=7, dtype=int)))
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

    def wakeup(self):
        """ Wake up the celesta source when it is in standby mode
        """
        self.lumencor_httpcommand(self._ip, 'WAKEUP')

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

    def set_laserline_intensity(self, wavelength, intensity):
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

        command = 'SET MULCHINT {}'.format(' '.join(map(str, laser_lines_intensity)))
        self.lumencor_httpcommand(self._ip, command)

    def set_laserline_on_off(self, wavelength, state):
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

        command = 'SET MULCH {}'.format(' '.join(map(str, laser_lines_state)))
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
        # print('Commande envoyee au Celesta : {}'.format(command_full))
        with urllib.request.urlopen(command_full) as response:
            message = eval(response.read())  # the default is conveniently JSON so eval creates dictionary
            if message['message'][0] == 'E':
                self.log.warning('An error occurred - the command was not recognized')

        return message
