# -*- coding: utf-8 -*-
"""
Qudi-CBS

This file contains the Qudi Interface for a camera.

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
from core.interface import abstract_interface_method
from core.meta import InterfaceMetaclass


class CameraInterface(metaclass=InterfaceMetaclass):
    """ This interface is used to control a camera.
    """
    # set the internal attributes _full_width, _full_height,
    # and, if has_temp returns true: _default_temperature
    # if has_shutter returns true: _shutter

# ----------------------------------------------------------------------------------------------------------------------
# Getter and setter methods
# ----------------------------------------------------------------------------------------------------------------------

    @abstract_interface_method
    def get_name(self):
        """ Retrieve an identifier of the camera that the GUI can print.

        :return: string name: name for the camera
        """
        pass

    @abstract_interface_method
    def get_size(self):
        """ Retrieve size of the image in pixel.

        :return: tuple (int, int): Size (width, height)
        """
        pass

    @abstract_interface_method
    def set_exposure(self, exposure):
        """ Set the exposure time in seconds.

        :param: float exposure: desired new exposure time

        :return: bool: Success ?
        """
        pass

    @abstract_interface_method
    def get_exposure(self):
        """ Get the exposure time in seconds.

        :return: float exposure time
        """
        pass

    @abstract_interface_method
    def set_gain(self, gain):
        """ Set the gain.

        :param: int gain: desired new gain

        :return: bool: Success ?
        """
        pass

    @abstract_interface_method
    def get_gain(self):
        """ Get the gain.

        :return: int gain
        """
        pass

    @abstract_interface_method
    def get_ready_state(self):
        """ Is the camera ready for an acquisition ?

        :return: bool: ready ?
        """
        pass

    @abstract_interface_method
    def set_image(self, hbin, vbin, hstart, hend, vstart, vend):
        """ Sets a ROI on the sensor surface.

        :param: int hbin: number of pixels to bin horizontally
        :param: int vbin: number of pixels to bin vertically.
        :param: int hstart: Start column (inclusive)
        :param: int hend: End column (inclusive)
        :param: int vstart: Start row (inclusive)
        :param: int vend: End row (inclusive).

        :return: error code: ok = 0
        """
        pass

    @abstract_interface_method
    def get_progress(self):
        """ Retrieves the total number of acquired images during a movie acquisition.

        :return: int progress: total number of acquired images. """
        pass

# ----------------------------------------------------------------------------------------------------------------------
# Methods to query the camera properties
# ----------------------------------------------------------------------------------------------------------------------

    @abstract_interface_method
    def support_live_acquisition(self):
        """ Return whether or not the camera can take care of live acquisition.

        :return: bool: True if supported, False if not
        """
        pass

    @abstract_interface_method
    def has_temp(self):
        """ Does the camera support setting of the temperature?

        If this function returns true, is is necessary that the methods get_temperature, set_temperature, is_cooler_on
        and _set_cooler (which are not interface functions) are implemented.
        The attribute _default_temperature must be also be set in the hardware module.
        
        :return: bool: has temperature ?
        """
        pass

    @abstract_interface_method
    def has_shutter(self):
        """ Is the camera equipped with a mechanical shutter?

        If this function returns true, the attribute _shutter must also be defined in the hardware module

        :return: bool: has shutter ?
        """
        pass

# ----------------------------------------------------------------------------------------------------------------------
# Methods to handle camera acquisitions
# ----------------------------------------------------------------------------------------------------------------------

# Methods for displaying images on the GUI -----------------------------------------------------------------------------
    @abstract_interface_method
    def start_single_acquisition(self):
        """ Start a single acquisition

        :return: bool: Success ?
        """
        pass

    @abstract_interface_method
    def start_live_acquisition(self):
        """ Start a continuous acquisition

        :return: bool: Success ?
        """
        pass

    @abstract_interface_method
    def stop_acquisition(self):
        """ Stop/abort live or single acquisition

        :return: bool: Success ?
        """
        pass

# Methods for saving image data ----------------------------------------------------------------------------------------
    @abstract_interface_method
    def start_movie_acquisition(self, n_frames):
        """ Set the conditions to save a movie and start the acquisition (typically kinetic / fixed length mode).

        :param: int n_frames: number of frames

        :return: bool: Success ?
        """
        pass

    @abstract_interface_method
    def finish_movie_acquisition(self):
        """ Reset the conditions used to save a movie to default.

        :return: bool: Success ?
        """
        pass

    @abstract_interface_method
    def wait_until_finished(self):
        """ Wait until an acquisition is finished.

        :return: None
        """
        pass

# Methods for acquiring image data using synchronization between lightsource and camera---------------------------------
    @abstract_interface_method
    def prepare_camera_for_multichannel_imaging(self, frames, exposure, gain, save_path, file_format):
        """ Set the camera state for an experiment using synchronization between lightsources and the camera.
        Using typically an external trigger.

        :param: int frames: number of frames in a kinetic series / fixed length mode
        :param: float exposure: exposure time in seconds
        :param: int gain: gain setting
        :param: str save_path: complete path (without fileformat suffix) where the image data will be saved
        :param: str file_format: selected fileformat such as 'tiff', 'fits', ..

        :return: None
        """
        pass

    @abstract_interface_method
    def reset_camera_after_multichannel_imaging(self):
        """ Reset the camera to a default state after an experiment using synchronization between lightsources and
         the camera.

         :return: None
         """
        pass

# ----------------------------------------------------------------------------------------------------------------------
# Methods for image data retrieval
# ----------------------------------------------------------------------------------------------------------------------

    @abstract_interface_method
    def get_most_recent_image(self):
        """ Return an array of last acquired image.

        :return: numpy array: image data in format [[row],[row]...]

        Each pixel might be a float, integer or sub pixels
        """
        pass

    @abstract_interface_method
    def get_acquired_data(self):
        """ Return an array of last acquired image in case of a run till abort acquisition
        or of the complete data in case of a fixed length acquisition.

        :return: numpy array: image data in format [[row],[row]...]

        Each pixel might be a float, integer or sub pixels
        """
        pass
