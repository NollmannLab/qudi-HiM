# -*- coding: utf-8 -*-
"""
Qudi-CBS

This file contains the dummy implementation for a camera.

This module was available in Qudi original version and was extended.

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

import numpy as np
import time
from core.module import Base
from core.configoption import ConfigOption
from interface.camera_interface import CameraInterface


class CameraDummy(Base, CameraInterface):
    """ Dummy implementation of a microscope camera.

    Example config for copy-paste:

    camera_dummy:
        module.Class: 'camera.camera_dummy.CameraDummy'
        support_live: True
        camera_name: 'Dummy camera'
        resolution: (720, 1280)
        exposure: 0.1 
        gain: 1.0
    """
    # config options
    _support_live = ConfigOption('support_live', True)
    _camera_name = ConfigOption('camera_name', 'Dummy camera')  # 'Dummy camera' 'iXon Ultra 897'
    _resolution = ConfigOption('resolution', (720, 1280))  # (720, 1280) indicate (nb rows, nb cols) because row-major config is used in gui module
    _exposure = ConfigOption('exposure', .1)
    _gain = ConfigOption('gain', 1.)

    # camera attributes
    _live = False  # attribute indicating if the camera is currently in live mode
    _acquiring = False  # attribute indicating if the camera is currently acquiring  an image
    _has_temp = False
    _has_shutter = False

    image_size = _resolution
    n_frames = 1

    _full_width = 0
    _full_height = 0

    _progress = 0

    _frame_transfer = False

    # only needed for simulations with _has_temp = True
    temperature = 17
    _default_temperature = 12

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

    def on_activate(self):
        """ Initialisation performed during activation of the module.
        """
        self._full_width = self._resolution[1]
        self._full_height = self._resolution[0]

    def on_deactivate(self):
        """ Deinitialisation performed during deactivation of the module.
        """
        self.stop_acquisition()

# ======================================================================================================================
# Camera Interface functions
# ======================================================================================================================

# ----------------------------------------------------------------------------------------------------------------------
# Getter and setter methods
# ----------------------------------------------------------------------------------------------------------------------

    def get_name(self):
        """ Retrieve an identifier of the camera that the GUI can print.

        :return: string: name for the camera
        """
        return self._camera_name

    def get_size(self):
        """ Retrieve size of the image in pixel.

        :return: tuple (int, int): Size (width, height)
        """
        return self.image_size[1], self.image_size[0]

    def set_exposure(self, exposure):
        """ Set the exposure time in seconds.

        :param: float exposure: desired new exposure time

        :return: bool: Success ?
        """
        self._exposure = exposure
        return True

    def get_exposure(self):
        """ Get the exposure time in seconds.

        :return: float exposure time
        """
        return self._exposure

    def set_gain(self, gain):
        """ Set the gain.

        :param: int gain: desired new gain

        :return: bool: Success ?
        """
        self._gain = gain
        return True

    def get_gain(self):
        """ Get the gain.

        :return: int gain
        """
        return self._gain

    def get_ready_state(self):
        """ Is the camera ready for an acquisition ?

        :return: bool: ready ?
        """
        return not (self._live or self._acquiring)

    def set_image(self, hbin, vbin, hstart, hend, vstart, vend):
        """  Sets a ROI on the sensor surface.

        We don't use the binning parameters but they are needed in the
        function call to be conform with syntax of andor camera.
        :param: int hbin: number of pixels to bin horizontally
        :param: int vbin: number of pixels to bin vertically.
        :param: int hstart: Start column (inclusive)
        :param: int hend: End column (inclusive)
        :param: int vstart: Start row (inclusive)
        :param: int vend: End row (inclusive).

        :return: error code: ok = 0
        """
        self.image_size = (abs(vend-vstart)+1, abs(hend-hstart)+1, )  # rows, cols
        return 0

    def get_progress(self):
        """ Retrieves the total number of acquired images during a movie acquisition.

        :return: int progress: total number of acquired images.
        """
        n_frames = self.n_frames
        self._progress += 1
        progress = self._progress
        if progress == n_frames:
            self._live = False
            self._progress = 0
            return n_frames
        return progress

# ----------------------------------------------------------------------------------------------------------------------
# Methods to query the camera properties
# ----------------------------------------------------------------------------------------------------------------------

    def support_live_acquisition(self):
        """ Return whether or not the camera can take care of live acquisition.

        :return: bool: True if supported, False if not
        """
        return self._support_live

    def has_temp(self):
        """ Does the camera support setting of the temperature?

        :return: bool: has temperature ?
        """
        return self._has_temp

    def has_shutter(self):
        """ Is the camera equipped with a mechanical shutter?

        :return: bool: has shutter ?
        """
        return self._has_shutter

# ----------------------------------------------------------------------------------------------------------------------
# Methods to handle camera acquisitions
# ----------------------------------------------------------------------------------------------------------------------

# Methods for displaying images on the GUI -----------------------------------------------------------------------------
    def start_single_acquisition(self):
        """ Start a single acquisition

        :return: bool: Success ?
        """
        if self._live:
            return False
        else:
            self._acquiring = True
            time.sleep(float(self._exposure+10/1000))
            self._acquiring = False
            return True

    def start_live_acquisition(self):
        """ Start a continuous acquisition

        :return: bool: Success ?
        """
        if self._support_live:
            self._live = True
            self._acquiring = False
            return True
        else:
            return False

    def stop_acquisition(self):
        """ Stop/abort live or single acquisition

        :return: bool: Success ?
        """
        self._live = False
        self._acquiring = False
        return True

# Methods for saving image data ----------------------------------------------------------------------------------------
    def start_movie_acquisition(self, n_frames):
        """ Set the conditions to save a movie and start the acquisition (typically kinetic / fixed length mode).

        :param: int n_frames: number of frames

        :return: bool: Success ?
        """
        if not self._live and not self._acquiring:  # video can only be started if not yet in live or acquisition mode
            # handle the variables indicating the status
            if self.support_live_acquisition():
                self._live = True
                self._acquiring = False
            self.n_frames = n_frames
            self.log.info('started movie acquisition')
            return True
        else:
            return False

    def finish_movie_acquisition(self):
        """ Reset the conditions used to save a movie to default.

        :return: bool: Success ?
        """
        self._live = False
        self._acquiring = False
        self.n_frames = 1
        self.log.info('movie acquisition finished')
        return True

    def wait_until_finished(self):
        """ Wait until an acquisition is finished.

        :return: None
        """
        time.sleep(0.5)

# Methods for acquiring image data using synchronization between lightsource and camera---------------------------------
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

    def reset_camera_after_multichannel_imaging(self):
        """ Reset the camera to a default state after an experiment using synchronization between lightsources and
         the camera.

         :return: None
         """
        pass

# ----------------------------------------------------------------------------------------------------------------------
# Methods for image data retrieval
# ----------------------------------------------------------------------------------------------------------------------

    def get_most_recent_image(self):
        """ Return an array of last acquired image. Used for live display on gui during save procedures

        :return: numpy array: image data in format [[row],[row]...]

        Each pixel might be a float, integer or sub pixels
        """
        data = np.random.normal(size=self.image_size) * self._exposure * self._gain
        # data = data.astype(np.int16)  # type conversion
        return data

    def get_acquired_data(self):
        """ Return an array of last acquired image in case of a run till abort acquisition
        or of the complete data in case of a fixed length acquisition.

        :return: numpy array: image data in format [[row],[row]...]

        Each pixel might be a float, integer or sub pixels
        """
        if self.n_frames > 1:
            data = self._data_generator(size=(self.n_frames, self.image_size[0], self.image_size[1])) * self._exposure * self._gain
        else:
            data = self._data_generator(size=self.image_size) * self._exposure * self._gain
        return data

# ======================================================================================================================
# Non-Interface functions
# ======================================================================================================================

# ----------------------------------------------------------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def _data_generator(size):
        """ Allows to generate 2D or 3D data
        :param: int tuple size (width, height) or (depth, width, height)
        :return: np.array(float) data
        """
        data = np.random.normal(size=size)
        return data

# ----------------------------------------------------------------------------------------------------------------------
# Simulation of Andor camera
# ----------------------------------------------------------------------------------------------------------------------

    def _set_spool(self, active, mode, filenamestem, framebuffer):
        """ Simulates the spooling functionality of the andor camera.
         This function must be available if camera name is set to iXon Ultra 897
         """
        if active == 1:
            self.log.info('camera dummy: started spooling')
        elif active == 0:
            self.log.info('camera dummy: spooling finished')
        else:
            pass

    def get_kinetic_time(self):
        """ Simulates kinetic time method of andor camera.
        This function must be available if camera name is set to iXon Ultra 897.

        :return: float kinetic time """
        if self._frame_transfer:
            return self._exposure + 0.123
        else:
            return self._exposure + 0.7654321

    def _set_frame_transfer(self, transfer_mode):
        """ set the frame transfer mode

        :param: int tranfer_mode: 0: off, 1: on
        :returns: int error code 0 = ok, -1 = error
        """
        if transfer_mode == 1:
            self._frame_transfer = True
            self.log.info('Camera dummy: activated frame transfer mode, transfer_mode {}'.format(transfer_mode))
            err = 0
        elif transfer_mode == 0:
            self._frame_transfer = False
            self.log.info('Camera dummy: deactivated frame transfer mode, transfer_mode {}'.format(transfer_mode))
            err = 0
        else:
            self.log.info('Camera dummy: specify the transfer_mode to set frame transfer, transfer_mode {}'.format(transfer_mode))
            err = -1
        return err

    # temperature getter / setter functions
    def set_temperature(self, temp):
        """ Set the temperature setpoint.

        :param int temp: desired new temperature

        :return: bool: success ?
        """
        self.temperature = temp
        return True

    def get_temperature(self):
        """ Get the current temperature.

        :return int: temperature
        """
        return self.temperature

    def is_cooler_on(self):
        """ Checks the status of the cooler.

        :return: int: 0: cooler is off, 1: cooler is on
        """
        return 1

    def _set_cooler(self, state):
        """ This method is called to switch the cooler on or off

        :params: bool state: cooler on = True, cooler off = False

        :return: error message: ok = 0 """
        return 0
