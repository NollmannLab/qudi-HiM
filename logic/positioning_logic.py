# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains the logic to control the positioning system for the probes.

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
from time import sleep
from qtpy import QtCore
from logic.generic_logic import GenericLogic
from core.configoption import ConfigOption
from core.connector import Connector


# ======================================================================================================================
# Worker classes
# ======================================================================================================================

class WorkerSignals(QtCore.QObject):
    """ Defines the signals available from a running worker thread. """
    sigxyStepFinished = QtCore.Signal(dict, dict)
    sigzStepFinished = QtCore.Signal(dict)


class xyMoveWorker(QtCore.QRunnable):
    """ Worker thread to wait for the end of a translation stage movement but which preserves the possibility to
    abort the movement.

    The worker handles only the waiting time, and emits a signal that serves to trigger the update indicators. """

    def __init__(self, pos_dict_xy, pos_dict_z):
        super(xyMoveWorker, self).__init__()
        self.signals = WorkerSignals()
        self.pos_dict_xy = pos_dict_xy
        self.pos_dict_z = pos_dict_z

    @QtCore.Slot()
    def run(self):
        """ """
        sleep(0.5)  # 0.5 second as time constant
        self.signals.sigxyStepFinished.emit(self.pos_dict_xy, self.pos_dict_z)


class zMoveWorker(QtCore.QRunnable):
    """ Worker thread to wait for the end of a translation stage movement but which preserves the possibility to
    abort the movement.

    The worker handles only the waiting time, and emits a signal that serves to trigger the update indicators. """

    def __init__(self, pos_dict_z):
        super(zMoveWorker, self).__init__()
        self.signals = WorkerSignals()
        self.pos_dict_z = pos_dict_z

    @QtCore.Slot()
    def run(self):
        """ """
        sleep(0.5)  # 0.5 second as time constant
        self.signals.sigzStepFinished.emit(self.pos_dict_z)


# ======================================================================================================================
# Logic class
# ======================================================================================================================

class PositioningLogic(GenericLogic):
    """
    Class containing the logic to control the 3 axis positioning system for the probes

    Example config for copy-paste:

    positioning_logic:
        module.Class: 'positioning_logic.PositioningLogic'
        z_safety_position: 0
        first_axis: 'X axis'
        second_axis: 'Y axis'
        third_axis: 'Z axis'
        grid: 'cartesian'
        connect:
            stage: 'motor_dummy'
    """
    # declare connectors
    stage = Connector(interface='MotorInterface')

    # config options
    z_safety_pos = ConfigOption('z_safety_position', 0, missing='warn')
    first_axis_label = ConfigOption('first_axis', 'X axis')
    second_axis_label = ConfigOption('second_axis', 'Y axis')
    third_axis_label = ConfigOption('third_axis', 'Z axis')
    grid = ConfigOption('grid', missing='warn')  # either 'cartesian' or 'polar'

    # signals
    sigUpdatePosition = QtCore.Signal(tuple)  # send during movement to update coordinates on the GUI
    sigStageMoved = QtCore.Signal(tuple)  # this signal is sent if movement was started using coordinates of stage. tuple contains the new stage position (x, y, z)
    sigStageMovedToTarget = QtCore.Signal(tuple, int)  # this signal is sent if movement was started using target position (number of probe). tuple contains the new stage position (x, y, z), int is the target position
    sigOriginDefined = QtCore.Signal()
    sigStageStopped = QtCore.Signal(tuple)  # tuple contains the current stage position (x, y, z)
    sigDisablePositioningActions = QtCore.Signal()
    sigEnablePositioningActions = QtCore.Signal()

    # attributes
    move_stage = False  # flag
    go_to_target = False  # flag
    target_position = 0  # will be overwritten when movement is started using the start_move_to_target method  # target is the probe number
    origin = None
    moving = False

    delta_x = 14.9  # in mm # to be defined by config later
    delta_y = 14.9  # in mm # to be defined by config later
    delta_r = -20  # in mm # to be defined by config later
    delta_phi = -10  # in degree # to be defined by config later

    _probe_grid_dict = {}  # contains the mapping of probe numbers to their coordinates on the grid  {1: (0, 0), ...}
    _probe_xy_position_dict = {}  # contains the mapping the physical x-y or r-phi positions of the probes to their probe number  {(12.0, 10.0): 1, ..} # _probe_xy_position_dict is empty until the origin is set

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self.threadpool = QtCore.QThreadPool()
        self._stage = None
        self.num_probes = 0

    def on_activate(self):
        """ Initialisation performed during activation of the module.
        """
        # connector
        self._stage = self.stage()

        # calculate the probe grid coordinates  # the grid is independent of the origin that is not yet set
        self._probe_grid_dict = self.map_probe_number_to_grid_coordinates()

    def on_deactivate(self):
        """ Perform required deactivation. """
        pass

    def get_hardware_constraints(self):
        """ Retrieve constraints from the connected stage. This is used to update the indicators on the GUI
        according to the connected stage.
        :return: dict constraints
        """
        return self._stage.get_constraints()

# ----------------------------------------------------------------------------------------------------------------------
# Methods defining the origin, the grid and the x-y or r-phi coordinates
# ----------------------------------------------------------------------------------------------------------------------

    def set_origin(self, origin):
        """ Defines the origin = the metric coordinates of the position1 of the grid with the probes.
        Sends a signal to indicate that the origin was set.
        """
        self.origin = origin
        # create a dictionary that allows to access the position number of the probe by its metric coordinates
        self._probe_xy_position_dict = self.map_xy_position_to_probe_number()
        self.sigOriginDefined.emit()

    def map_probe_number_to_grid_coordinates(self):
        """ For a cartesian grid, this method generates a mapping of probe positions to coordinates on a
        serpentine grid (just grid points, no metric coordinates):
        1: (0, 0), 2: (0, 1), 3: (0, 2), etc.. values in (x, y) order, y being the index that varies rapidly.

        For a polar grid, this method generates a mapping of probe positions to coordinates on on a grid using
        using polar coordinates
        1: (0, 0), 2: (1, 0), 3: (2, 0), 4: (0, 1), 5: (1, 1), .. etc. Values in (r, phi) order, r varying rapidly.

        :return dict coord_dict: dictionary mapping the probe position to the corresponding grid position
        """
        if self.grid == 'cartesian':  # for RAMM setup
            num_x = 10  # number of positions in x direction
            num_y = 10  # number of positions in y direction
            self.num_probes = num_x * num_y
            # create the coordinate grid
            list_even = [(x, y) for x in range(num_x) for y in range(num_y) if x % 2 == 0]
            list_odd = [(x, y) for x in range(num_x) for y in reversed(range(num_y)) if x % 2 != 0]
            list_all = list_even + list_odd
            coords_list = sorted(list_all, key=self.sort_first)

            # associate a grid point to each probe position
            coord_dict = {}
            for key in range(self.num_probes):
                coord_dict[key+1] = coords_list[key]

        elif self.grid == 'polar':  # for Airyscan setup
            num_r = 3
            num_phi = 36
            self.num_probes = num_r * num_phi

            # coords_list = [(x, y) for y in range(0, -360, -10) for x in [40, 20, 0]]  # this would directly define the metric coordinates
            coords_list = [(x, y) for y in range(num_phi) for x in range(num_r)]

            coord_dict = {}
            for key in range(self.num_probes):
                coord_dict[key+1] = coords_list[key]

        else:
            coord_dict = {}
            self.log.warning('Your grid type is currently not covered.')

        return coord_dict

    @staticmethod
    def sort_first(val):
        """ Helper function for sorting a list of tuples by the first element of each tuple,
        used for setting up the serpentine grid

        :return: the first element of value (in the context here, value is a 2dim tuple (x, y))
        """
        return val[0]

    def map_xy_position_to_probe_number(self):
        """ This method calculates the in-plane coordinates given the metrics of the respective setup
        (spacing of probe positions in x, y directions or r, phi directions) and stores them in a dictionary.

        :return dict inv_dict: dictionary containing a tuple of in-plane coordinates as key and associated probe number as value.

        This dictionary serves as look-up-table in the fluidics gui module to check if the stage is currently at a probe position.
        """
        probe_xy_position_dict = {}
        if self.grid == 'cartesian':
            for key in self._probe_grid_dict:
                x_pos = self._probe_grid_dict[key][0] * self.delta_x + self.origin[0] + self._probe_grid_dict[key][1] * -0.11
                y_pos = self._probe_grid_dict[key][1] * self.delta_y + self.origin[1] + self._probe_grid_dict[key][0] * -0.055
                position = (x_pos, y_pos)
                probe_xy_position_dict[key] = position

        elif self.grid == 'polar':
            for key in self._probe_grid_dict:
                r_pos = self._probe_grid_dict[key][0] * self.delta_r + self.origin[0]
                phi_pos = self._probe_grid_dict[key][1] * self.delta_phi + self.origin[1]
                position = (r_pos, phi_pos)
                probe_xy_position_dict[key] = position

        else:
            self.log.warning('Your grid type is currently not covered.')

        # invert the keys and values in the dictionary because we want to access the target position by the key
        inv_dict = dict((v, k) for k, v in probe_xy_position_dict.items())

        return inv_dict

    def get_coordinates(self, target):
        """ This method returns the (x, y) grid coordinates associated to the target position

        :param: int target: target position of the probe
        :return: int tuple (x, y)
        """
        return self._probe_grid_dict[target]

# ----------------------------------------------------------------------------------------------------------------------
# Methods to perform movements either given the target stage coordinates or the target position of the probe
# ----------------------------------------------------------------------------------------------------------------------

    def start_move_stage(self, position):
        """ This method allows to perform a movement of the 3 axis stage to the specified stage position.
        A movement to the z safety position is performed first, before doing the xy positioning.
        xy positioning is started from this method, then a loop is entered to make a call to the abort movement method
        possible.
        Finally, the z movement is done using again a loop.

        :param: float tuple position: (x, y, z) position
        """
        if len(position) != 3:
            self.log.warn('Stage position to set must be iterable of length 3. No movement done.')

        else:
            self.move_stage = True  # flag indicating later on that the translation stage movement was initiated by start_move_stage method
            self.moving = True

            # do not allow descending z below safety position when operating by move stage (x y z coordinates given instead of target position)
            if position[2] > self.z_safety_pos:
                self.log.warning('z movement will not be made. z out of allowed range.')
                # redefine position using the z safety position instead of the user defined z position
                x = position[0]
                y = position[1]
                z = self.z_safety_pos
                position = (x, y, z)

            # if self.grid == 'polar':
            #     axis_label = ('r', 'phi', 'z')
            # else:
            axis_label = ('x', 'y', 'z')  # 'cartesian' as default case

            pos_dict = dict([*zip(axis_label, position)])
            # separate movement into xy and z movements for safety
            # if self.grid == 'polar':
            #     pos_dict_xy = {key: pos_dict[key] for key in ['r', 'phi']}
            # else:
            pos_dict_xy = {key: pos_dict[key] for key in ['x', 'y']}
            pos_dict_z = {key: pos_dict[key] for key in ['z']}
            self._stage.move_abs({'z': self.z_safety_pos})  # move to z safety position before making the xy movement
            ready = self._stage.get_status('z')['z']
            while not ready:
                sleep(0.5)
                ready = self._stage.get_status('z')['z']

            # start the xy movement of the translation stage
            self._stage.move_abs(pos_dict_xy)

            # start a worker thread to monitor the xy movement
            worker = xyMoveWorker(pos_dict_xy, pos_dict_z)
            worker.signals.sigxyStepFinished.connect(self.move_xy_stage_loop)
            self.threadpool.start(worker)

    def start_move_to_target(self, target_position):
        """ This method allows to perform a movement of the 3 axis stage to the specified position given by the
        target probe number.
        A movement to the z safety position is performed first, before doing the xy positioning.
        Then, z is moved to its specified value.
        Emits a signal when finished and sends the new position and the reached target number.

        :param: int target_position: number of the target probe
        """
        if not self.origin:
            self.log.warn('Move to target is not possible. Please define the origin')
            return

        self.go_to_target = True  # flag indicating later on that the translation stage movement was initiated by start_move_to_target method
        self.target_position = target_position  # keep this variable accessible until movement is finished
        self.moving = True

        # invert the probe_xy_position_dict
        inv_probe_xy_position_dict = dict((v, k) for k, v in self._probe_xy_position_dict.items())
        x_pos = inv_probe_xy_position_dict[target_position][0]
        y_pos = inv_probe_xy_position_dict[target_position][1]
        z_pos = self.origin[2]
        position = (x_pos, y_pos, z_pos)
        # if self.grid == 'polar':
        #     axis_label = ('r', 'phi', 'z')
        # else:
        axis_label = ('x', 'y', 'z')
        pos_dict = dict([*zip(axis_label, position)])
        # separate into in-plane and z movements
        # if self.grid == 'polar':
        #     pos_dict_xy = {key: pos_dict[key] for key in ['r', 'phi']}
        # else:
        pos_dict_xy = {key: pos_dict[key] for key in ['x', 'y']}
        pos_dict_z = {key: pos_dict[key] for key in ['z']}

        # do the z safety movement
        self._stage.move_abs({'z': self.z_safety_pos})
        ready = self._stage.get_status('z')['z']
        while not ready:
            sleep(0.5)
            ready = self._stage.get_status('z')['z']
            # or use wait for idle (waitontarget) as non interface method .. or add it to the interface

        # start the xy movement of the translation stage
        self._stage.move_abs(pos_dict_xy)

        # start a worker thread to monitor the xy movement
        worker = xyMoveWorker(pos_dict_xy, pos_dict_z)
        worker.signals.sigxyStepFinished.connect(self.move_xy_stage_loop)
        self.threadpool.start(worker)

    def move_xy_stage_loop(self, pos_dict_xy, pos_dict_z):
        """ This method queries the current position and sends a signal to the GUI to update the current position.
        It calls itself using a worker thread until the in-plane target position is reached. Then it starts the move
        to the z coordinate.

        :param: dict pos_dict_xy: dictionary containing the labels 'x' and 'y' as keys and the target values along
                                    these axes as values. 'x' and 'y' can be an alias for any other type of axes,
                                    such as 'r' and 'phi'. For coding clarity, first and second axes are always called
                                    'x' and 'y', respectively.
        :param: dict pos_dict_z: dictionary containing the label 'z' as key and the target value along the z axis as
                                    value.
        :return: None
        """
        # compare the current position with the target position
        new_position = self.get_position()
        x_pos = new_position[0]
        y_pos = new_position[1]
        self.sigUpdatePosition.emit(new_position)

        if self.moving:  # make sure that movement has not been aborted
            if (abs(x_pos - pos_dict_xy['x']) > 0.005) or (abs(y_pos - pos_dict_xy['y']) > 0.005):
                # enter in a loop until xy position reached
                worker = xyMoveWorker(pos_dict_xy, pos_dict_z)
                worker.signals.sigxyStepFinished.connect(self.move_xy_stage_loop)
                self.threadpool.start(worker)
            else:
                # xy position reached, start now the z movement
                self.start_move_z_stage(pos_dict_z)

    def start_move_z_stage(self, pos_dict_z):
        """ This method starts the movement in z direction and starts a worker thread that will invoke
        the move_z_stage_loop after a waiting time.

        :param: dict pos_dict_z: dictionary containing the label 'z' as key and the target value along the z axis as
                                    value.
        :return: None
        """
        # start the z movement of the translation stage
        self._stage.move_abs(pos_dict_z)

        # start a worker thread to monitor the xy movement
        worker = zMoveWorker(pos_dict_z)
        worker.signals.sigzStepFinished.connect(self.move_z_stage_loop)
        self.threadpool.start(worker)

    def move_z_stage_loop(self, pos_dict_z):
        """ This method queries the current z position and sends a signal to the GUI to update the current position.
        It calls itself using a worker thread until the target z position is reached. It then sends a signal to the
        GUI to indicate that the movement is finished and to reset the toolbuttons.

        :param: dict pos_dict_z: dictionary containing the label 'z' as key and the target value along the z axis as
                                    value.
        :return: None
        """
        # compare the current position with the target position
        new_position = self.get_position()
        z_pos = new_position[2]
        self.sigUpdatePosition.emit(new_position)

        if self.moving:  # make sure that movement has not been aborted
            # if z_pos != pos_dict_z['z']:
            if abs(z_pos - pos_dict_z['z'] > 0.002):
                # enter in a loop until z position reached
                worker = zMoveWorker(pos_dict_z)
                worker.signals.sigzStepFinished.connect(self.move_z_stage_loop)
                self.threadpool.start(worker)

            else:
                self.moving = False
                self._stage.wait_for_idle()
                new_pos = self.get_position()
                # self.log.info(new_pos)

                # send the signal to the GUI depending on which button triggered the stage movement
                if self.move_stage:
                    self.sigStageMoved.emit(new_pos)
                    self.move_stage = False
                elif self.go_to_target:
                    self.sigStageMovedToTarget.emit(new_pos, self.target_position)
                    self.go_to_target = False
                else:
                    pass

    def abort_movement(self):
        """ This method is called to abort a stage movement (either initiated by move_stage or move_to_target)
        Sends a signal to indicate that the stage was stopped and the current reached position.
        """
        self.moving = False
        self._stage.abort()
        # reset all flags
        self.move_stage = False
        self.go_to_target = False
        # self.target_position = 1

        self.log.info('Movement aborted!')
        pos = self.get_position()
        self.sigStageStopped.emit(pos)

    def get_position(self):
        """ This method retrieves the current stage position from the hardware and does formatting of the return value.

        :return: float tuple: position (x, y, z) or (r, phi, z)
        """
        position = self._stage.get_pos()  # returns a dictionary {'x': x_pos, 'y': y_pos, 'z': z_pos}
        position = tuple([*position.values()])  # convert into tuple
        return position

# ----------------------------------------------------------------------------------------------------------------------
# Methods to handle the user interface state
# ----------------------------------------------------------------------------------------------------------------------

    def disable_positioning_actions(self):
        """ This method provides a security to avoid using the positioning action buttons on GUI,
        for example during Tasks. """
        self.sigDisablePositioningActions.emit()

    def enable_positioning_actions(self):
        """ This method resets positioning action button on GUI to callable state,
        for example after Tasks. """
        self.sigEnablePositioningActions.emit()
