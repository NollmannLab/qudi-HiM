# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains the hardware class representing a Thorlabs motorized filterwheel.

This module was available in Qudi original version and was modified.
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
import visa
from core.module import Base
from interface.filterwheel_interface import FilterwheelInterface
from core.configoption import ConfigOption


class ThorlabsMotorizedFilterWheel(Base, FilterwheelInterface):
    """ Hardware class representing the Thorlabs motorized filterwheel.

    Example config for copy-paste:

    thorlabs_wheel:
        module.Class: 'wheels.thorlabs_motorized_filter_wheel.ThorlabsMotorizedFilterWheel'
        interface: 'COM6'
        num_filters: 6
        filterpositions:
            - 1
            - 2
            - 3
            - 4
            - 5
            - 6
        filters:
            - '700 +/- 37 nm'
            - '600 +/- 25 nm'
            - '488 - 491 / 561 nm'
            - '525 +/- 22.5 nm'
            - '617 +/- 36 nm'
            - '460 +/- 25 nm'
        allowed_lasers:
            - [True, True, True, True]
            - [True, True, True, True]
            - [True, True, True, True]
            - [True, True, True, True]
            - [True, True, True, False]
            - [True, False, True, True]

            # please specify for all elements corresponding information in the same order
            # allowed lasers:
            # entries corresponding to [laser1_allowed, laser2_allowed, laser3_allowed, laser4_allowed, ..]
            # see also the config for the daq ao output to associate a laser number to a wavelength

    Description of the hardware provided by Thorlabs:
        These stepper-motor-driven filter wheels are designed for use in a host of automated applications including
        color CCD photography, fluorescence microscopy, and photometry. Each unit consists of a motorized housing
        and a preinstalled filter wheel with either 6 positions for Ø1" (Ø25 mm) optics or 12 positions
        for Ø1/2" (Ø12.5 mm) optics. Filter wheels of either type can also be purchased separately and installed
        by the user.
    """
    # config options
    interface = ConfigOption('interface', 'COM6', missing='error')
    
    _num_filters = ConfigOption('num_filters', 6)
    _filternames = ConfigOption('filters', missing='error')
    _positions = ConfigOption('filterpositions', missing='error')
    _allowed_lasers = ConfigOption('allowed_lasers', missing='error')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._rm = None
        self._inst = None

    def on_activate(self):
        """ Module activation method. """
        self._rm = visa.ResourceManager()
        try:
            self._inst = self._rm.open_resource(self.interface, baud_rate=115200, write_termination='\r',
                                                read_termination='\r')
            idn = self._query('*idn?')
            self.log.debug('Connected to : {}'.format(idn))
        except visa.VisaIOError as e:
            self.log.error(f'Thorlabs filter wheel: Connection failed: {e} Check if device is switched on.')

        if len(self._filternames) != self._num_filters or len(self._positions) != self._num_filters or len(self._allowed_lasers) != self._num_filters:
            self.log.warning('Please specify name, position, and allowed lasers for each filter')

    def on_deactivate(self):
        """ Disconnect from hardware on deactivation. """
        self._inst.close()
        self._rm.close()

# ----------------------------------------------------------------------------------------------------------------------
# Filterwheel interface functions
# ----------------------------------------------------------------------------------------------------------------------

    def get_position(self):
        """ Get the current position, from 1 to 6 (or 12).
         :return int position: number of the filterwheel position that is currently set """
        position = self._query('pos?')
        return int(position)

    def set_position(self, target_position):
        """ Set the position to a given value.
        The wheel will take the shorter path. If upward or downward are equivalent, the wheel take the upward path.

        :param: int target_position: position number
        :return: int error code: ok = 0
        """
        if target_position < self._num_filters + 1:
            res = self._write("pos={}".format(int(target_position)))
            err = 0
        else:
            self.log.error('Can not go to filter {0}. Filterwheel has only {1} positions'.format(target_position, self._num_filters))
            err = -1
        return err 

    def get_filter_dict(self):
        """ Retrieves a dictionary with the following entries:
                    {'filter1': {'label': 'filter1', 'name': str(name), 'position': 1, 'lasers': bool list},
                     'filter2': {'label': 'filter2', 'name': str(name), 'position': 2, 'lasers': bool list},
                    ...
                    }

                    # all positions of the filterwheel must be defined even when empty.
                    Match the dictionary key 'filter1' to the position 1 etc.

        :return: dict filter_dict
        """
        filter_dict = {}

        for i, item in enumerate(
                self._filternames):  # use any of the lists retrieved as config option, just to have an index variable
            label = 'filter{}'.format(i + 1)  # create a label for the i's element in the list starting from 'filter1'

            dic_entry = {'label': label,
                         'name': self._filternames[i],
                         'position': self._positions[i],
                         'lasers': self._allowed_lasers[i]}

            filter_dict[dic_entry['label']] = dic_entry

        return filter_dict

# ----------------------------------------------------------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------------------------------------------------------

    def _query(self, text):
        """ Send query, get and return answer
        :param: str text: query to be send
        :return: str answer: string read from hardware communication port """
        echo = self._write(text)
        answer = self._inst.read()
        return answer

    def _write(self, text):
        """ Write command, do not expect answer.
         :param: str text: string to be written to hardware communication port
         :return: str echo: string read from hardware communication port """
        self._inst.write(text)
        echo = self._inst.read()
        return echo
