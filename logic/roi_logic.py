# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains the ROI selection logic.

It is in large parts inspired and adapted from the Qudi poimanager logic.
(+in this version:
deactivated tools concerning the camera image overlay but would be interesting to establish this in the future)

ROIs are regrouped into an ROI list (instead of using the terminology of POI in ROI
or, as in the labview measurement software ROIs per embryo.)
The chosen nomenclature is more flexible than regrouping by embryo and can be extended to other
types of samples.

An extension to Qudi.

@author: F. Barho

Created on Mon Nov 2020
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
import os
import numpy as np
from time import sleep
import json
from itertools import product
from math import ceil

from core.connector import Connector
from core.statusvariable import StatusVar
from datetime import datetime
from logic.generic_logic import GenericLogic
from qtpy import QtCore
from core.util.mutex import Mutex


# ======================================================================================================================
# Worker class for continuous stage position tracking mode
# ======================================================================================================================

class WorkerSignals(QtCore.QObject):
    """ Defines the signals available from a running worker thread """
    sigFinished = QtCore.Signal()


class Worker(QtCore.QRunnable):
    """ Worker thread to monitor the stage position every x seconds when tracking mode is on

    The worker handles only the waiting time, and emits a signal that serves to trigger the update stage position """

    def __init__(self, *args, **kwargs):
        super(Worker, self).__init__(*args, **kwargs)
        self.signals = WorkerSignals()

    @QtCore.Slot()
    def run(self):
        """ """
        sleep(1)  # 1 second as time constant
        self.signals.sigFinished.emit()


# ======================================================================================================================
# Classes representing the ROIlist and the ROI
# ======================================================================================================================


class RegionOfInterestList:
    """  
    Class containing the general information about a specific list of regions of interest,
    such as its name, the creation time, the rois as a dictionary of ROI instances,
    (N.B. Each individual ROI will be represented as a RegionOfInterest instance (see below).), 
    the camera image which may be overlayed on the map of ROI markers.
    
    example of a RegionOfInterestList instance in its dictionary representation
    {'name': 'roilist_20201113_1212_00_244657',
     'creation_time': '2020-11-13 12:12:00.244657',
     'cam_image': None,
     'cam_image_extent': None,
     'rois': [{'name': 'ROI_001', 'position': (0.0, 0.0, 0.0)},
              {'name': 'ROI_002', 'position': (10.0, 10.0, 0.0)},
              {'name': 'ROI_003', 'position': (20.0, 20.0, 0.0)},
              {'name': 'ROI_004', 'position': (30.0, 30.0, 0.0)}]}
    """

    def __init__(self, name=None, creation_time=None, cam_image=None,
                 cam_image_extent=None, rois=None):

        # Save the creation time for metadata
        self._creation_time = None
        # Optional camera image associated with this ROI
        self._cam_image = None
        # Optional initial camera image extent.
        self._cam_image_extent = None
        # Save name of the ROIlist. Create a generic, unambiguous one as default.
        self._name = None
        # dictionary of ROIs contained in this ROIlist with keys being the name
        self._rois = dict()

        self.creation_time = creation_time
        self.name = name
        # self.set_cam_image(cam_image, cam_image_extent)
        if rois is not None:
            for roi in rois:
                self.add_roi(roi)

    @property
    def name(self):
        """ Get the name of the roi list

        :return: str name
        """
        return str(self._name)

    @name.setter
    def name(self, new_name):
        """ Set a new name for the roi list instance.

        :param: str new_name
        :return: None
        """
        if isinstance(new_name, str) and new_name:
            self._name = str(new_name)
        elif new_name is None or new_name == '':
            self._name = self._creation_time.strftime('roilist_%Y%m%d_%H%M_%S_%f')  # modify the default roilist name ?
        else:
            raise TypeError('ROIlist name to set must be None or of type str.')

    @property
    def creation_time(self):
        """ Get the creation time of the ROI list.
        :return: datetime.datetime object creation time of the ROI list
        """
        return self._creation_time

    @property
    def creation_time_as_str(self):
        """ Get the creation time of the ROI list in str format.
        :return str: creation time on the ROI list """
        return datetime.strftime(self._creation_time, '%Y-%m-%d %H:%M:%S.%f')

    @creation_time.setter
    def creation_time(self, new_time):
        """ Set the creation time of the ROI list.
        :param: str or datetime.datetime object new time
        :return: None
        """
        if not new_time:
            new_time = datetime.now()
        elif isinstance(new_time, str):
            new_time = datetime.strptime(new_time, '%Y-%m-%d %H:%M:%S.%f')
        if isinstance(new_time, datetime):
            self._creation_time = new_time

    @property
    def origin(self):
        """ Get the origin of the ROI list. Not really useful here as we don't perform direct drift correction.
        Defaults always to (0,0,0)
        :return: np.ndarray[3] origin
        """
        return np.zeros(3)  # no drift correction so origin is set to 0 and does not move over time

    @property
    def cam_image(self):
        """ Get the camera image belonging to the ROI list.
        Not really useful here. In a future version, camera images could be included.
        But they should maybe be part of a RegionOfInterest object, not one image for RegionOfInterestList.
        Or this image should be composed of all the individual ROI images. """
        return self._cam_image

    # can be simplified when origin is kept as (0, 0, 0)
    @property
    def cam_image_extent(self):
        """ Get the camera image extent.
        Not really useful in the current version. We probably won't need a calculated extent as there is no drift
        correction. Maybe remove this class member. """
        if self._cam_image_extent is None:
            return None
        x, y, z = self.origin
        x_extent = (self._cam_image_extent[0][0] + x, self._cam_image_extent[0][1] + x)
        y_extent = (self._cam_image_extent[1][0] + y, self._cam_image_extent[1][1] + y)
        return x_extent, y_extent

    @property
    def roi_names(self):
        """ Get a list with all the ROI names (keys to all the RegionOfInterest Objects).
        :return: list of str: roi names """
        return list(self._rois)

    @property
    def roi_positions(self):
        """ Get a dictionary with roi names as keys and their positions as np.ndarray[3] as values.
        :return dict
        """
        origin = self.origin
        return {name: roi.position + origin for name, roi in self._rois.items()}

    def get_roi_position(self, name):
        """ Get the position of the ROI asked for by the function parameter name.
        :param: str name: valid ROI name
        :return: np.ndarray[3]: position of the ROI
        """
        if not isinstance(name, str):
            raise TypeError('ROI name must be of type str.')
        if name not in self._rois:
            raise KeyError('No ROI with name "{0}" found in ROI list.'.format(name))
        return self._rois[name].position + self.origin

    def set_roi_position(self, name, new_pos):
        """ Set the position of the addressed ROI to a different position.
        :param: str name: identifier of the addressed ROI
        :param: iterable of length 3: new position of the ROI
        :return: None
        """
        if name not in self._rois:
            raise KeyError('ROI with name "{0}" not found in ROIlist "{1}".\n'
                           'Unable to change ROI position.'.format(name, self.name))
        self._rois[name].position = np.array(new_pos, dtype=float) - self.origin

    # this method is made unavailable because only the generic name ROI_000 etc is allowed.
    #    def rename_roi(self, name, new_name=None):
    #        if new_name is not None and not isinstance(new_name, str):
    #            raise TypeError('ROI name to set must be of type str or None.')
    #        if name not in self._rois:
    #            raise KeyError('Name "{0}" not found in ROI list.'.format(name))
    #        if new_name in self._rois:
    #            raise NameError('New ROI name "{0}" already present in current ROI list.')
    #        self._rois[name].name = new_name
    #        self._rois[new_name] = self._rois.pop(name)
    #        return None

    # to be modified: remove kwarg name in calls to this function -> better solution: leave it as it for compatibility
    # and just make sure that a generic name always overwrites a name given by user

    def add_roi(self, position, first_digit=0, name=None):
        """ Add a new ROI to a list. A generic name is used (even when the name parameter is filled with a user defined
        value. name parameter was kept for compatibility with previous program structure.

        :param: iterable of length 3 position of the new ROi
        :param: str name: defaults to the generic numbering ROI_num even when the user specifies a custom name
        :return: None
        """
        if isinstance(position, RegionOfInterest):
            roi_inst = position
        else:
            position = position - self.origin

            # Create a generic name which cannot be accessed by the user
            # using the increment of the last roi in the list (deleted roi names do not get 'refilled')
            if len(self._rois) == 0:
                # last_number = 0
                last_number = int(first_digit) - 1
            else:
                last_index = len(self._rois) - 1  # self._rois is a dictionary
                keylist = [*self._rois.keys()]
                last = keylist[last_index]  # pick the roi with the highest number in the list containing all the keys
                last_number = int(last.strip('ROI_'))
            new_index = last_number + 1
            str_new_index = str(new_index).zfill(3)  # zero padding
            name = 'ROI_' + str_new_index

            roi_inst = RegionOfInterest(position=position, name=name)
        self._rois[roi_inst.name] = roi_inst

    def delete_roi(self, name):
        """ Deletes the ROI identified by name if it exists in the current list.

        :param: str name: valid identifier of a ROI in the current list
        :return: None
        """
        if not isinstance(name, str):
            raise TypeError('ROI name to delete must be of type str.')
        if name not in self._rois:
            raise KeyError('Name "{0}" not found in ROI list.'.format(name))
        del self._rois[name]

    # can be activated and modified if camera image is added
    #     def set_cam_image(self, image_arr=None, image_extent=None):
    #         """
    #
    #         @param scalar[][] image_arr:
    #         @param float[2][2] image_extent:
    #         """
    #         if image_arr is None:
    #             self._cam_image = None
    #             self._cam_image_extent = None
    #         else:
    #             roi_x_pos, roi_y_pos, roi_z_pos = self.origin
    #             x_extent = (image_extent[0][0] - roi_x_pos, image_extent[0][1] - roi_x_pos)
    #             y_extent = (image_extent[1][0] - roi_y_pos, image_extent[1][1] - roi_y_pos)
    #             self._cam_image = np.array(image_arr)
    #             self._cam_image_extent = (x_extent, y_extent)
    #         return

    def to_dict(self):
        """ Convert an instance of the ROI list object to a dictionary containing the relevant information.
        :return: dict
        """
        return {'name': self.name,
                'creation_time': self.creation_time_as_str,
                'cam_image': self.cam_image,
                'cam_image_extent': self.cam_image_extent,
                'rois': [roi.to_dict() for roi in self._rois.values()]}

    @classmethod
    def from_dict(cls, dict_repr):
        """ Creates a RegionOfInterestList object from its dictionary representation.
        :param: dict
        :return: roi_list object
        """
        if not isinstance(dict_repr, dict):
            raise TypeError('Parameter to generate RegionOfInterestList instance from must be of type '
                            'dict.')
        if 'rois' in dict_repr:
            rois = [RegionOfInterest.from_dict(roi) for roi in dict_repr.get('rois')]
        else:
            rois = None

        roi_list = cls(name=dict_repr.get('name'),
                       creation_time=dict_repr.get('creation_time'),
                       cam_image=dict_repr.get('cam_image'),
                       cam_image_extent=dict_repr.get('cam_image_extent'),
                       rois=rois,
                       )
        return roi_list


class RegionOfInterest:
    """
    The actual individual ROI is saved in this generic object.
    A RegionOfInterest object corresponds to a dictionary of the following format {'name': roi_name, 'position': roi_position}
    for example {'name': ROI_OO1, 'position': (10, 10, 0)}
    """

    def __init__(self, position, name=None):
        # Name of the ROI
        self._name = ''
        # Relative ROI position within the ROIlist (x,y,z) 
        self._position = np.zeros(3)
        # Initialize properties
        self.position = position
        self.name = name

    @property
    def name(self):
        """ Get the name of the ROI.
        :return: str name
        """
        return str(self._name)

    # redefined the name.setter so that it can be called from the RegionOfInterestList instance 
    # it will always be called with a new_name corresponding to the generic format. the 'if not new_name' part would produce the same name
    @name.setter
    def name(self, new_name):
        """ Set the name for the ROI. Only default name can be set (this is handled in RegionOfInterestList class
        or alternatively here if not new_name given.
        :param: str new_name or None
        :return: None
        """
        if new_name is not None and not isinstance(new_name, str):
            raise TypeError('Name to set must be either None or of type str.')
        if not new_name:
            # Create a generic name which cannot be accessed by the user
            # using the increment of the last roi in the list (deleted roi names do not get 'refilled')
            if len(self._rois) == 0:
                last_number = 0
            else:
                last_index = len(self._rois) - 1  # self._rois is a dictionary
                print(last_index)
                print(self._rois.keys())
                keylist = [*self._rois.keys()]
                last = keylist[last_index]  # pick the roi with the highest number in the list containing all the keys
                last_number = int(last.strip('ROI_'))
            new_index = last_number + 1
            str_new_index = str(new_index).zfill(3)  # zero padding
            new_name = 'ROI_' + str_new_index
        self._name = new_name

    @property
    def position(self):
        """ Get the position of the ROI object.
        :return: np.ndarray[3] """
        return self._position

    @position.setter
    def position(self, pos):
        """ Set the position of the ROI object.
        :param: iterable of length 3: new position"""
        if len(pos) != 3:
            raise ValueError('ROI position to set must be iterable of length 3 (X, Y, Z).')
        self._position = np.array(pos, dtype=float)

    def to_dict(self):
        """ Convert an instance of the RegionOfInterest object to its dictionary representation.
        :return: dict
        """
        return {'name': self.name, 'position': tuple(self.position)}

    @classmethod
    def from_dict(cls, dict_repr):
        """ Creates a RegionOfInterestList object from its dictionary representation.
        :param: dict
        :return: ROI object """
        return cls(**dict_repr)


# ======================================================================================================================
# Logic class
# ======================================================================================================================

class RoiLogic(GenericLogic):
    """
    This is the Logic class for selecting regions of interest.

    Example config for copy-paste:

    roi_logic:
        module.Class: 'roi_logic.RoiLogic'
        connect:
            stage: 'motor_dummy_roi'
    """
    # declare connectors
    stage = Connector(interface='MotorInterface')
    
    # status vars
    _roi_list = StatusVar(default=dict())  # Notice constructor and representer further below
    _active_roi = StatusVar(default=None)
    _roi_width = StatusVar(default=50)
    _roi_starting_digit = StatusVar(default=0)

    # Signals
    sigRoiUpdated = QtCore.Signal(str, str, np.ndarray)  # old_name, new_name, current_position
    sigActiveRoiUpdated = QtCore.Signal(str)
    sigRoiListUpdated = QtCore.Signal(dict)  # Dict containing ROI parameters to update
    sigWidthUpdated = QtCore.Signal(float)
    sigStageMoved = QtCore.Signal(np.ndarray)  # current_position
    sigUpdateStagePosition = QtCore.Signal(tuple)
    sigTrackingModeStopped = QtCore.Signal()  # important to emit this when tracking mode is programmatically stopped to reestablish correct GUI state
    sigDisableTracking = QtCore.Signal()
    sigEnableTracking = QtCore.Signal()
    sigDisableRoiActions = QtCore.Signal()
    sigEnableRoiActions = QtCore.Signal()

    # variables from mosaic settings dialog and default values
    _mosaic_x_start = 0
    _mosaic_y_start = 0
    _mosaic_roi_width = 0
    _mosaic_number_x = 0  # width
    _mosaic_number_y = 0  # height

    # class attributes
    tracking = False

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self.threadpool = QtCore.QThreadPool()
        self._stage = None

        # not needed in this version but remember to use it when starting to handle threads
        # self._threadlock = Mutex()

    def on_activate(self):
        """ Initialisation performed during activation of the module.
        """
        self._stage = self.stage()

        # Initialise the ROI camera image (xy image) if not present
        # if self._roi_list.cam_image is None:
        #     self.set_cam_image(False)

        self.sigRoiListUpdated.emit({'name': self.roi_list_name,
                                     'rois': self.roi_positions,
                                     'cam_image': self.roi_list_cam_image,
                                     'cam_image_extent': self.roi_list_cam_image_extent
                                     })
        self.sigActiveRoiUpdated.emit('' if self.active_roi is None else self.active_roi)

    def on_deactivate(self):
        """ Perform required deactivation steps. """
        pass

# ----------------------------------------------------------------------------------------------------------------------
# Getter and setter methods
# ----------------------------------------------------------------------------------------------------------------------

    @property
    def active_roi(self):
        """ Get the active ROI.
        :return str identifier of active ROI
        """
        return self._active_roi

    @active_roi.setter
    def active_roi(self, name):
        """ Set the active ROI.
        :param: str name: identifier of the ROI that shall be set as active one.
        :return: None
        """
        self.set_active_roi(name)

    @property
    def roi_names(self):
        """ Get the ROI names.
        :return: str list: list with identifiers of ROIs contained in the current ROI list.
        """
        return self._roi_list.roi_names

    @property
    def roi_positions(self):
        """ Get the ROI positions.
        :return: dict: with ROI name as key and its position as value (nd.array of dim(3,)
        """
        return self._roi_list.roi_positions

    @property
    def roi_list_name(self):
        """ Get the name of the roi list.
        :return: str: identifier of the current ROI list
        """
        return self._roi_list.name

    @roi_list_name.setter
    def roi_list_name(self, name):
        """ Set the name of the ROI list.
        :param: str name: new name for the ROI list
        :return: None
        """
        self.rename_roi_list(new_name=name)

    @property
    def roi_list_origin(self):
        """ Get the origin of the ROI list. (Not really needed, always defaults to (0,0,0)
        :return: nd.array origin
        """
        return self._roi_list.origin

    @property
    def roi_list_creation_time(self):
        """ Get the creation time of the ROI list.
        :return: datetime.datetime object: creation time
        """
        return self._roi_list.creation_time

    @property
    def roi_list_creation_time_as_str(self):
        """ Get the creation time of the ROI list in string format.
        :return: str: creation time as string
        """
        return self._roi_list.creation_time_as_str

    @property
    def roi_list_cam_image(self):
        """ Get the camera image associated to the ROI list.
        :return: (currently None) could be modified to return the camera image
        """
        return self._roi_list.cam_image

    @property
    def roi_list_cam_image_extent(self):
        """ Get the camera image extent associated to the ROI list.
        :return: (currently None) could be modified to return the camera image extent
        """
        return self._roi_list.cam_image_extent

    @property
    def roi_width(self):
        """ Get the width of the ROI marker.
        :return: float roi marker width (in um) """
        return float(self._roi_width)

    @roi_width.setter
    def roi_width(self, new_width):
        """ Set the width of the ROI marker.
        :param: float new_width
        """
        self.set_roi_width(new_width)

    @property
    def stage_position(self):
        """ Get the current stage position.
        :return tuple of floats: x y z coordinates of the stage (z is set to 0 in case of 2 axes stage)
        """
        pos = self._stage.get_pos()  # this returns a dictionary of the format {'x': pos_x, 'y': pos_y}
        if len(pos) == 2 and 'z' not in pos.keys():  # case for the 2 axes stage
            pos['z'] = 0  # add an artificial z component so that add_roi method can be called which expects a tuple (x, y, z)
        return tuple(pos.values())[:3]  # get only the dictionary values as a tuple.
        # [:3] as safety to get only the x y axis and (eventually empty) z value, in case more axis are configured (such as for the motor_dummy)

    def get_roi_position(self, name=None):
        """
        Returns the ROI position of the specified ROI or the active ROI if none is given.

        :param str name: Name of the ROI to return the position for.
                             If None (default) the active ROI position is returned.
        :return float[3]: Coordinates of the desired ROI (x,y,z)
        """
        if name is None:
            name = self.active_roi
        return self._roi_list.get_roi_position(name)

# ----------------------------------------------------------------------------------------------------------------------
# Methods for conversion between roi_lists and roi_dict
# ----------------------------------------------------------------------------------------------------------------------

    @_roi_list.constructor
    def dict_to_roi(self, roi_dict):
        """ This method creates a RegionOfInterestList instance, given a dictionary containing the necessary
        information.

        :param: dict roi_dict
        :return: RegionOfInterestList object
        """
        return RegionOfInterestList.from_dict(roi_dict)

    @_roi_list.representer
    def roi_list_to_dict(self, roi_list):
        """ This method converts a roi_list to a dictionary which is the form used for saving it to a file.

        :param: RegionOfInterestList object roi_list
        :return: dict: dictionary containing the information about the roi_list
        """
        return roi_list.to_dict()

# ----------------------------------------------------------------------------------------------------------------------
# Slots called from the GUI module for toolbar actions
# ----------------------------------------------------------------------------------------------------------------------

# ROI toolbar ----------------------------------------------------------------------------------------------------------
    @QtCore.Slot()
    @QtCore.Slot(np.ndarray)
    def add_roi(self, position=None, name=None, emit_change=True):
        """
        Creates a new ROI and adds it to the current ROI list.
        The ROI can be optionally initialized with position.

        Even if called with a name not None, a generic name is set.
        The specified one is not taken into account.
        This is handled in the add_roi method of RegionOfInterestList class.

        :param str name: Name for the ROI (must be unique within ROI list).
                         None (default) will create generic name.
        :param scalar[3] position: Iterable of length 3 representing the (x, y, z) position with
                                   respect to the ROI list origin. None (default) causes the current
                                   stage position to be used.
        :param bool emit_change: Flag indicating if the changed ROI set should be signaled.

        :return: None
        """
        # Get current stage position from motor interface if no position is provided.
        if position is None:
            position = self.stage_position

        current_roi_set = set(self.roi_names)

        # Add ROI to current ROI list
        self._roi_list.add_roi(position=position, first_digit=self._roi_starting_digit, name=name)

        # Get newly added ROI name from comparing ROI names before and after addition of new ROI
        roi_name = set(self.roi_names).difference(current_roi_set).pop()

        # Notify about a changed set of ROIs if necessary
        if emit_change:
            self.sigRoiUpdated.emit('', roi_name, self.get_roi_position(roi_name))

        # Set newly created ROI as active roi
        self.set_active_roi(roi_name)

    @QtCore.Slot()
    def go_to_roi(self, name=None):
        """
        Move translation stage to the given roi.

        :param str name: the name of the ROI, default is the active roi
        :return: None
        """
        if name is None:
            name = self.active_roi
        if not isinstance(name, str):
            self.log.error('ROI name to move to must be of type str.')
            return None
        self._move_stage(self.get_roi_position(name))

    def go_to_roi_xy(self, name=None):
        """
        Move translation stage to the xy position of the given roi.

        :param str name: the name of the ROI, default is the active roi
        :return: None
        """
        if name is None:
            name = self.active_roi
        if not isinstance(name, str):
            self.log.error('ROI name to move to must be of type str.')
            return None
        x_roi, y_roi, z_roi = self.get_roi_position(name)
        x_stage, y_stage, z_stage = self.stage_position
        target_pos = np.array((x_roi, y_roi, z_stage))  # conversion from tuple to np.ndarray for call of _move_stage
        self._move_stage(target_pos)

    @QtCore.Slot()
    def delete_roi(self, name=None):
        """
        Deletes the given roi from the roi list.
        This method can be called with a name present in the list (which will only be the generic names)

        :param str name: Name of the roi to delete. If None (default) delete active roi.
        """
        if len(self.roi_names) == 0:
            self.log.warning('Can not delete ROI. No ROI present in ROI list.')
            return None
        if name is None:
            if self.active_roi is None:
                self.log.error('No ROI name to delete and no active ROI set.')
                return None
            else:
                name = self.active_roi

        self._roi_list.delete_roi(name)  # see method defined in RegionOfInterestList class

        if self.active_roi == name:
            if len(self.roi_names) > 0:
                self.set_active_roi(self.roi_names[0])
            else:
                self.set_active_roi(None)

        # Notify about a changed set of ROIs if necessary
        self.sigRoiUpdated.emit(name, '', np.zeros(3))

    # with this overloading it is possible to call it from gui without specifying a roi_distance
    @QtCore.Slot()
    @QtCore.Slot(float)
    def add_interpolation(self, roi_distance=50):  # remember to correct the roi_distance parameter
        """ Fills the space between the already defined rois (at least 2) with more ROIs using a center to center
        distance roi_distance. The grid starts in the minimum x and y coordinates from the already defined ROIs and
        covers the maximum x and y coordinates

        :params: roi_distance

        ::return: None
        """
        if len(self.roi_positions) < 2:
            self.log.warning('Please specify at least 2 ROIs to perform an interpolation')
        else:
            try:
                # find the minimal and maximal x and y coordonates from the current roi_list
                xmin = min([self.roi_positions[key][0] for key in self.roi_positions])
                xmax = max([self.roi_positions[key][0] for key in self.roi_positions])
                ymin = min([self.roi_positions[key][1] for key in self.roi_positions])
                ymax = max([self.roi_positions[key][1] for key in self.roi_positions])
                # print(xmin, xmax, ymin, ymax)

                # calculate the number of tiles needed
                width = abs(xmax - xmin)
                height = abs(ymax - ymin)
                # print(width, height)
                num_x = ceil(width / roi_distance) + 1  # number of tiles in x direction
                num_y = ceil(height / roi_distance) + 1  # number of tiles in y direction
                # print(num_x, num_y)

                # create a grid of the central points
                grid = self.make_serpentine_grid(int(num_x), int(
                    num_y))  # type conversion necessary because xmin etc are numpy floats
                # type conversion from list to np array for making linear, elementwise operations
                grid_array = np.array(grid)
                # get the current z position of the stage to keep the same level for all rois defined in the interpolation
                # alternative: set it to 0. What should be done in case the different rois are not on the same z level ?
                z = self.stage_position[2]
                # stretch the grid and shift it so that the first center point is in (x_min, y_min)
                roi_centers = grid_array * roi_distance + [xmin, ymin, z]
                # print(roi_centers)

                # list is not reset before adding new rois. we might end up having some overlapping exactly the initial ones.
                for item in roi_centers:
                    self.add_roi(item)

            except Exception:
                self.log.error('Could not create interpolation')

# ROI list toolbar -----------------------------------------------------------------------------------------------------
    @QtCore.Slot()
    def reset_roi_list(self):
        """ Instantiate a new empty RegionOfInterestList.

        :return: None
        """
        self._roi_list = RegionOfInterestList()  # create an instance of the RegionOfInterestList class
        # self.set_cam_image()
        self.sigRoiListUpdated.emit({'name': self.roi_list_name,
                                     'rois': self.roi_positions,
                                     'cam_image': self.roi_list_cam_image,
                                     'cam_image_extent': self.roi_list_cam_image_extent
                                     })
        self.set_active_roi(None)

    def save_roi_list(self, path, filename):
        """
        Save the current roi_list to a file. A dictionary format is used.

        :param: str path: path to the folder where the ROI list will be saved
        :param: str filename: name of the file containing the dictionary with the ROI list information.
                                json format is used
        :return: None
        """
        # convert the roi_list to a dictionary
        roi_list_dict = self.roi_list_to_dict(self._roi_list)

        if not os.path.exists(path):
            try:
                os.makedirs(path)  # recursive creation of all directories on the path
            except Exception as e:
                self.log.error('Error {0}'.format(e))

        p = os.path.join(path, filename)

        try:
            with open(p + '.json', 'w') as file:
                json.dump(roi_list_dict, file)
            self.log.info('ROI list saved to file {}.json'.format(p))
        except Exception as e:
            self.log.warning('ROI list not saved: {}'.format(e))

    def load_roi_list(self, complete_path=None):
        """
        Load a selected roi_list from .json file.

        :param: str complete_path: path to the file containing the complete folder hierarchy
        :return: None
        """
        # if no path given do nothing
        if complete_path is None:
            self.log.warning('No path to ROI list given')
            return None

        try:
            print(f'The path is {complete_path}')
            with open(complete_path, 'r') as file:
                roi_list_dict = json.load(file)

            self._roi_list = self.dict_to_roi(roi_list_dict)

            self.sigRoiListUpdated.emit({'name': self.roi_list_name,
                                     'rois': self.roi_positions,
                                     'cam_image': self.roi_list_cam_image,
                                     'cam_image_extent': self.roi_list_cam_image_extent
                                     })
            self.set_active_roi(None if len(self.roi_names) == 0 else self.roi_names[0])
            self.log.info('Loaded ROI list from {}'.format(complete_path))
        except Exception as e:
            self.log.warning('ROI list not loaded: {}'.format(e))

    @QtCore.Slot()
    def delete_all_roi(self):
        """ Keep the current ROI list but discard all ROI names in the list.

        :return: None
        """
        self.active_roi = None
        for name in self.roi_names:
            self._roi_list.delete_roi(name)
            self.sigRoiUpdated.emit(name, '', np.zeros(3))

# ----------------------------------------------------------------------------------------------------------------------
# Slots for other actions (on GUI mainwindow elements for example)
# ----------------------------------------------------------------------------------------------------------------------

    @QtCore.Slot(str)
    def set_active_roi(self, name=None):
        """
        Set the name of the currently active ROI.
        :param: str name: should be present in current ROI list
        :return: None
        """
        if not isinstance(name, str) and name is not None:
            self.log.error('ROI name must be of type str or None.')
        elif name is None or name == '':
            self._active_roi = None
        elif name in self.roi_names:
            self._active_roi = str(name)
        else:
            self.log.error('No ROI with name "{0}" found in ROI list.'.format(name))
        self.sigActiveRoiUpdated.emit('' if self.active_roi is None else self.active_roi)

    @QtCore.Slot(str)
    def rename_roi_list(self, new_name):
        """
        Set a new name for the current ROI list.
        :param: str new name for the ROI list
        :return: None
        """
        if not isinstance(new_name, str) or new_name == '':
            self.log.error('ROI list name to set must be str of length > 0.')
            return None
        self._roi_list.name = new_name
        self.sigRoiListUpdated.emit({'name': self.roi_list_name})

    @QtCore.Slot(float)
    def set_roi_width(self, width):
        """
        Set a new width for the ROI marker.
        :param: float width: new width in um
        :return: None
        """
        self._roi_width = float(width)
        self.sigWidthUpdated.emit(width)

    @QtCore.Slot(float)
    def set_roi_first_digit(self, first_digit):
        """
        Set a new first digit for the ROI name.
        :param: float first_digit: new digit to use for naming the ROI
        :return: None
        """
        self._roi_starting_digit = float(first_digit)

    # @QtCore.Slot()
    # def set_cam_image(self, emit_change=True):
    #     """ Get the current xy scan data and set as scan_image of ROI. """
    #     self._roi_list.set_cam_image()
    #
    #     if emit_change:
    #         self.sigRoiListUpdated.emit({'cam_image': self.roi_list_cam_image,
    #                                  'cam_image_extent': self.roi_cam_image_extent})
    #     return None

# ----------------------------------------------------------------------------------------------------------------------
# Functions for mosaic tool
# ----------------------------------------------------------------------------------------------------------------------

    def add_mosaic(self, roi_width, width, height, x_center_pos=0, y_center_pos=0, z_pos=0, add=False):
        """
        Defines a new ROI list containing a serpentine scan.
        Parameters can be specified in the settings dialog on GUI option menu.

        :param float roi_width: (better distance between two ROI centers)
        :param int width: number of tiles in x direction
        :param int height: number of tiles in y direction
        :param float x_center_pos: origin of the mosaic, first coordinate
        :param float y_center_pos: origin of the mosaic, second coordinate
        :param z_pos: current z position of the stage if there is one; or 0 for two axes stage
        :param bool add: add the mosaic to the present list (True) or start a new one (False)

        :return: None
        """
        try:
            if not add:
                self.reset_roi_list()  # create a new list

            # create a grid of the central points
            grid = self.make_serpentine_grid(width, height)
            # type conversion from list to np array for making linear, elementwise operations
            grid_array = np.array(grid)
            # shift and stretch the grid to create the roi centers
            # mind the 3rd dimension so that it can be passed to the add_roi method
            # calculate start positions (lower left corner of the grid) given the central position
            x_start_pos = x_center_pos - roi_width * (width - 1) / 2
            y_start_pos = y_center_pos - roi_width * (height - 1) / 2
            roi_centers = grid_array * roi_width + [x_start_pos, y_start_pos, z_pos]

            for item in roi_centers:
                self.add_roi(item)
        except Exception:
            self.log.error('Could not create mosaic')

    def make_serpentine_grid(self, width, height):
        """ Creates the grid points for a serpentine scan, with ascending x values in even numbered rows and
        descending x values in odd values rows.
        Each element is appended with z = 0.

        :param: int width: number of columns (x direction)
        :param: int height: number of rows (y direction)

        :return: list gridpoints: list with points in serpentine scan order
        """
        list_even = [(x, y, 0) for y in range(height) for x in range(width) if y % 2 == 0]
        list_odd = [(x, y, 0) for y in range(height) for x in reversed(range(width)) if y % 2 != 0]
        list_all = list_even + list_odd
        gridpoints = sorted(list_all, key=self.sort_second)
        return gridpoints

    @staticmethod
    def sort_second(val):
        """ Helper function for sorting a list of tuples by the second element of each tuple,
        used for setting up the serpentine grid.

        :param: tuple (numeric type) val
        :return: the second element of value (in the context here, value is a 3dim tuple (x, y, z))
        """
        return val[1]

# ----------------------------------------------------------------------------------------------------------------------
# Methods for tracking mode of the stage position
# ----------------------------------------------------------------------------------------------------------------------

    def start_tracking(self):
        """ Start the tracking loop of the stage position. """
        self.tracking = True
        # monitor the current stage position, using a worker thread
        worker = Worker()
        worker.signals.sigFinished.connect(self.tracking_loop)
        self.threadpool.start(worker)

    def stop_tracking(self):
        """ Stop the tracking loop of the stage position. """
        self.tracking = False
        # get once again the latest position
        position = self.stage_position
        self.sigUpdateStagePosition.emit(position)
        self.sigTrackingModeStopped.emit()

    def tracking_loop(self):
        """ Perform a step in the tracking loop and start a new one if tracking mode is still on. """
        position = self.stage_position
        self.sigUpdateStagePosition.emit(position)
        if self.tracking:
            # enter in a loop until tracking mode is switched off
            worker = Worker()
            worker.signals.sigFinished.connect(self.tracking_loop)
            self.threadpool.start(worker)

# ----------------------------------------------------------------------------------------------------------------------
# Methods interacting with hardware
# ----------------------------------------------------------------------------------------------------------------------

    def set_stage_led_mode(self, mode):
        """
        Change the mode to control the bright field illumination (optional - depends on the ASI stage)

        :param: str mode : defined the mode "Internal" or "Triggered"
        :return: None
        """
        self._stage.led_mode(mode)

    def set_stage_led_intensity(self, intensity):
        """
        Change the intensity of the ASI LED for brightfield imaging

        :param: int intensity : value of intensity (between 0-100)
        :return: None
        """
        self._stage.led_control(intensity)

    def _move_stage(self, position):
        """
        Move the translation stage to position.

        :param: float tuple[3] position: target position for stage
        :return: None
        """
        if len(position) != 3:
            self.log.error('Stage position to set must be iterable of length 3.')
            return None
        axis_label = ('x', 'y', 'z')
        pos_dict = dict([*zip(axis_label, position)])
        self._stage.move_abs(pos_dict)
        self.sigStageMoved.emit(position)

    def set_stage_velocity(self, param_dict):
        """ Set the stage velocity. This method is needed for tasks to make the method in the hardware module
        accessible from logic layer.

        :param: dict param_dict: dictionary containing axes labels as keys and target velocity as values.
        :return: None
        """
        self._stage.set_velocity(param_dict)

    def stage_wait_for_idle(self):  # needed in tasks
        """ Wait until the stage status is idle. This method is needed for tasks to make the corresponding method
        in the hardware module accessible from the logic layer.

        @return timeout (bool) indicate whether the timeout limit was reach while waiting for the movement to stop
        """
        timeout = self._stage.wait_for_idle()
        return timeout

# ----------------------------------------------------------------------------------------------------------------------
# Methods to handle the user interface state
# ----------------------------------------------------------------------------------------------------------------------

    def disable_tracking_mode(self):
        """ This method provides a security that tracking mode is not callable from GUI, for example during Tasks. """
        if self.tracking:
            self.stop_tracking()
        self.sigDisableTracking.emit()
        sleep(0.5)

    def enable_tracking_mode(self):
        """ This method makes tracking mode again available from GUI, for example when a Task is finishing. """
        self.sigEnableTracking.emit()
        sleep(0.5)

    def disable_roi_actions(self):
        """ This method provides a security to avoid all stage related actions from GUI, for example during Tasks. """
        self.sigDisableRoiActions.emit()
        sleep(0.5)

    def enable_roi_actions(self):
        """ This method resets all ROI / stage related actions from GUI to callable state, for example after Tasks. """
        self.sigEnableRoiActions.emit()
        sleep(0.5)
