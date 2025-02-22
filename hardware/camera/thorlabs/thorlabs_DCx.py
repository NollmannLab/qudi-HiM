# -*- coding: utf-8 -*-
"""
Qudi-CBS

This file contains the hardware class representing an Thorlabs DCx camera.

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
import platform
import ctypes
from ctypes import *

import numpy as np

from core.module import Base
from core.configoption import ConfigOption
from interface.camera_interface import CameraInterface
from .uc480_h import *


class CameraThorlabs(Base, CameraInterface):
    """ Hardware class for Thorlabs Camera.

    Example config for copy-paste:

    thorlabs_camera:
        module.Class: 'camera.thorlabs.thorlabs_DCx.CameraThorlabs'
        default_exposure: 0.1
        default_gain: 1.0
        id_camera: 0 # if more tha one camera is present
    """
    # config options
    _default_exposure = ConfigOption('default_exposure', 0.1)
    _default_gain = ConfigOption('default_gain', 1.0)
    _id_camera = ConfigOption('id_camera', 0)  # if more than one camera is present

    # camera attributes
    _dll = None
    _camera_handle = None
    _exposure = _default_exposure
    _gain = _default_gain
    _width = 0
    _height = 0
    _pos_x = 0
    _pos_y = 0
    _bit_depth = 0
    _cam = None
    _sensor_info = None
    _image_memory = None
    _image_pid = None

    _acquiring = False
    _live = False

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

    def on_activate(self):
        """ Initialisation performed during activation of the module.
         """
        try:
            # Load the dll if present
            self._load_dll()
            self._connect_camera()
            self._init_camera()
        except Exception as e:
            self.log.error(f'Thorlabs DCx Camera: Connection failed: {e}.')

    def on_deactivate(self):
        """
        Deinitialisation performed during deactivation of the module.
        """
        self._dll.is_ExitCamera(self._camera_handle)
        self._acquiring = False
        self._live = False

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
        return self._sensor_info.strSensorName

    def get_size(self):
        """ Retrieve size of the image in pixel.

        :return: tuple (int, int): Size (width, height)
        """
        return self._width, self._height

    def set_exposure(self, time):
        """ Set the exposure time in seconds.

        :param: float time: desired new exposure time

        :return: bool: Success ?
        """
        exp = c_double(time * 1e3)  # in ms
        new_exp = c_double(0)
        code = self._dll.is_SetExposureTime(self._camera_handle, exp, byref(new_exp))
        err = self._check_error(code, "Could not set exposure")
        self._exposure = float(new_exp.value)/1000  # in ms
        return err

    def get_exposure(self):
        """ Get the exposure time in seconds.

        :return: float exposure time
        """
        return self._exposure

    def set_gain(self, gain):
        """ Set the gain. Not available for Thorlabs camera.

        :param: int gain: desired new gain

        :return: bool: Success ?
        """
        return False

    def get_gain(self):
        """ Get the gain.

        :return: int gain
        """
        return self._gain

    def get_ready_state(self):
        """ Is the camera ready for an acquisition ?

        :return: bool: ready ?
        """
        if self.module_state() != 'idle':
            return False
        return not self._acquiring

    # does not work yet ..
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
        #        hbin = 1  # overwrite in case a value was given # no binning made available to the user
        #        vbin = 1
        #        width = hend - hstart
        #
        #        height = vend - vstart
        #        self.log.info(f'{width}, {height}')
        #        try:
        #            self.log.info(f'image start position {hstart}, {vstart}')
        #            self.set_image_position(hstart, vstart)
        #            #self.set_image_size(width, height)
        #            return 0
        #        except:
        #            return -1
        pass

    def get_progress(self):
        """ Retrieves the total number of acquired images during a movie acquisition.
        This function is not needed for Thorlabs camera.

        :return: int progress: total number of acquired images.
        """
        return 0

# ----------------------------------------------------------------------------------------------------------------------
# Methods to query the camera properties
# ----------------------------------------------------------------------------------------------------------------------

    def support_live_acquisition(self):
        """
        Return whether or not this camera support live acquisition
        """
        return True

    def has_temp(self):
        """ Does the camera support setting of the temperature?

        :return: bool: has temperature ?
        """
        return False

    def has_shutter(self):
        """ Is the camera equipped with a mechanical shutter?

        :return: bool: has shutter ?
        """
        return False

# ----------------------------------------------------------------------------------------------------------------------
# Methods to handle camera acquisitions
# ----------------------------------------------------------------------------------------------------------------------

# Methods for displaying images on the GUI -----------------------------------------------------------------------------
    def start_single_acquisition(self):
        """ Start a single acquisition

        :return: bool: Success ?
        """
        if self.get_ready_state():
            self._acquiring = True
            code = self._dll.is_FreezeVideo(self._camera_handle, c_int(IS_WAIT))
            self._acquiring = False
            return self._check_error(code, "Could not start single acquisition")
        else:
            return False

    def start_live_acquisition(self):
        """ Start a continuous acquisition

        :return: bool: Success ?
        """
        status = self.get_ready_state()
        if status:
            self._acquiring = True
            self._live = True
            # code = self._dll.is_CaptureVideo(self._camera_handle, c_int(IS_DONT_WAIT))
            code = self._dll.is_CaptureVideo(self._camera_handle, c_int(IS_WAIT))
            # Parameter was changed to IS_WAIT to make sure that at least one image was acquired before making a request
            # for an image

            # # Allocate memory for image:
            # img_size = self._width * self._height
            # c_array = ctypes.c_char * img_size
            # self.c_img = c_array()

            no_error = self._check_error(code, "Could not start live acquisition")
            if not no_error:
                self._acquiring = False
                self._live = False
                return False
            return True
        else:
            print("The camera is not ready for an acquisition. Status : {}".format(status))
            return False

    def stop_acquisition(self):
        """ Stop/abort live or single acquisition

        :return: bool: Success ?
        """
        no_error = True
        if self._acquiring:
            code = self._dll.is_StopLiveVideo(self._camera_handle, c_int(IS_FORCE_VIDEO_STOP))
            no_error = self._check_error(code, "Could not stop acquisition")
        self._acquiring = False
        self._live = False
        return no_error

# Methods for saving image data ----------------------------------------------------------------------------------------
    # not needed for thorlabs camera
    def start_movie_acquisition(self, n_frames):
        """ Set the conditions to save a movie and start the acquisition (typically kinetic / fixed length mode).

        :param: int n_frames: number of frames

        :return: bool: Success ?
        """
        self.log.info('This method is not supported by Thorlabs camera')

    def finish_movie_acquisition(self):
        """ Reset the conditions used to save a movie to default.

        :return: bool: Success ?
        """
        self.log.info('This method is not supported by Thorlabs camera')

    def wait_until_finished(self):
        """ Wait until an acquisition is finished.

        :return: None
        """
        self.log.info('This method is not supported by Thorlabs camera')

# Methods for acquiring image data using synchronization between lightsource and camera---------------------------------
    # not needed for thorlabs camera at the moment
    def prepare_camera_for_multichannel_imaging(self, frames, file_format, exposure, gain, save_path):
        """ Set the camera state for an experiment using synchronization between lightsources and the camera.
        Using typically an external trigger.

        :param: int frames: number of frames in a kinetic series / fixed length mode
        :param: float exposure: exposure time in seconds
        :param: int gain: gain setting
        :param: str save_path: complete path (without fileformat suffix) where the image data will be saved
        :param: str file_format: selected fileformat such as 'tiff', 'fits', ..

        :return: None
        """
        self.log.info('This method is not supported by Thorlabs camera')

    def reset_camera_after_multichannel_imaging(self):
        """ Reset the camera to a default state after an experiment using synchronization between lightsources and
         the camera.

         :return: None
         """
        self.log.info('This method is not supported by Thorlabs camera')

# ----------------------------------------------------------------------------------------------------------------------
# Methods for image data retrieval
# ----------------------------------------------------------------------------------------------------------------------

    def get_most_recent_image(self):
        """ Return an array of last acquired image. Used for live display on gui during save procedures.

        :return: numpy array: image data in format [[row],[row]...]

        Each pixel might be a float, integer or sub pixels
        """
        self.log.info('This method is not supported by Thorlabs camera')

    def get_acquired_data(self):
        """ Return an array of last acquired image in case of a run till abort acquisition
        or of the complete data in case of a fixed length acquisition.

        :return: numpy array: image data in format [[row],[row]...]

        Each pixel might be a float, integer or sub pixels
        """
        # Allocate memory for image:
        img_size = self._width * self._height
        c_array = ctypes.c_char * img_size
        c_img = c_array()

        # copy camera memory to accessible memory

        code = self._dll.is_CopyImageMem(self._camera_handle, self._image_memory, self._image_pid, c_img)
        self._check_error(code, "Could copy image to memory")
        # Convert to numpy 2d array of float from 0 to 1
        img_array = np.frombuffer(c_img, dtype=ctypes.c_ubyte)
        img_array = img_array.astype(c_uint8)  # Replaced "float" by "c_uint8" since tne image depth is 8bit by default
        img_array.shape = np.array((self._height, self._width))

        return img_array

# ======================================================================================================================
# Non-Interface functions
# ======================================================================================================================

    def get_bit_depth(self):
        """
        Return the bit depth of the image.
        """
        return self._bit_depth

# ----------------------------------------------------------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------------------------------------------------------

    def _check_error(self, code, message):
        """
        Check that the code means OK and log message as error if not. Return True if OK, False otherwise.
        """
        if code != IS_SUCCESS:
            # self.log.error(message)
            return False
        else:
            return True

    def _check_int_range(self, value, mini, maxi, message):
        """
        Check that value is in the range [mini, maxi] and log message as error if not. Return True if OK.
        """
        if value < mini or value > maxi:
            self.log.error('{} - Value {} must be between {} and {}'.format(message, value, mini, maxi))
            return False
        else:
            return True

    def _load_dll(self):
        """
        Load the dll for the camera.
        """
        try:
            if platform.system() == "Windows":
                if platform.architecture()[0] == "64bit":
                    self._dll = ctypes.cdll.uc480_64
                else:
                    self._dll = ctypes.cdll.uc480
            # for Linux
            elif platform.system() == "Linux":
                self._dll = ctypes.cdll.LoadLibrary('libueye_api.so')
            else:
                self.log.error("Can not detect operating system to load Thorlabs DLL.")
        except OSError:
            self.log.error("Can not log Thorlabs DLL.")

    def _connect_camera(self):
        """
        Connect to the camera and get basic info on it.
        """
        number_of_cameras = ctypes.c_int(0)
        self._dll.is_GetNumberOfCameras(byref(number_of_cameras))
        if number_of_cameras.value < 1:
            self.log.error("No Thorlabs camera detected.")
        elif number_of_cameras.value - 1 < self._id_camera:
            self.log.error("A Thorlabs camera has been detected but the id specified above the number of camera(s)")
        else:
            self._camera_handle = ctypes.c_int(0)
            ret = self._dll.is_InitCamera(ctypes.pointer(self._camera_handle))
            self._check_error(ret, "Could not initialize camera")
            self._sensor_info = SENSORINFO()
            self._dll.is_GetSensorInfo(self._camera_handle, byref(self._sensor_info))
            self.log.debug('Connected to camera : {}'.format(str(self._sensor_info.strSensorName)))

    def _init_camera(self):
        """
        Set the parameters of the camera for our usage.
        """
        # Color mode
        code = self._dll.is_SetColorMode(self._camera_handle, ctypes.c_int(IS_SET_CM_Y8))
        self._check_error(code, "Could set color mode IS_SET_CM_Y8")
        self._bit_depth = 8
        # Image size
        self.set_image_size(self._sensor_info.nMaxWidth, self._sensor_info.nMaxHeight)
        # Image position
        self.set_image_position(0, 0)
        # Binning
        code = self._dll.is_SetBinning(self._camera_handle, ctypes.c_int(0))  # Disable binning
        self._check_error(code, "Could set binning disabled")
        # Sub sampling
        code = self._dll.is_SetSubSampling(self._camera_handle, ctypes.c_int(0))  # Disable sub sampling
        self._check_error(code, "Could set sub sampling disabled")
        # Allocate image memory
        self._image_pid = ctypes.c_int()
        self._image_memory = ctypes.c_char_p()
        code = self._dll.is_AllocImageMem(
            self._camera_handle, self._width, self._height,
            self._bit_depth, byref(self._image_memory), byref(self._image_pid))
        self._check_error(code, "Could not allocate image memory")
        # Set image memory
        code = self._dll.is_SetImageMem(self._camera_handle, self._image_memory, self._image_pid)
        self._check_error(code, "Could not set image memory")
        # Set auto exit
        code = self._dll.is_EnableAutoExit(self._camera_handle, 1)  # Enable auto-exit
        self._check_error(code, "Could not set auto exit")

        self.set_exposure(self._exposure)
        self.set_gain(self._gain)

    def set_image_size(self, width=None, height=None):
        """
        Set the size of the image, here the camera will acquire only part of the image from a given position.
        """
        if width is not None:
            width = int(width)
            self._check_int_range(width, 1, self._sensor_info.nMaxWidth, 'Can not set image width')
            self._width = width
        if height is not None:
            height = int(height)
            self._check_int_range(height, 1, self._sensor_info.nMaxHeight, 'Can not set image height')
            self._height = height

        code = self._dll.is_SetImageSize(self._camera_handle, ctypes.c_int(self._width), ctypes.c_int(self._height))
        return self._check_error(code, "Could not set image size")

    def set_image_position(self, pos_x, pos_y):
        """
        Set image position reference coordinate
        """
        if pos_x is not None:
            pos_x = int(pos_x)
            self._check_int_range(pos_x, 0, self._sensor_info.nMaxWidth-1, 'Can not set image position x')
            self._pos_x = pos_x
        if pos_y is not None:
            pos_y = int(pos_y)
            self._check_int_range(pos_y, 0, self._sensor_info.nMaxHeight-1, 'Can not set image position y')
            self._pos_y = pos_y

        code = self._dll.is_SetImagePos(self._camera_handle, ctypes.c_int(self._pos_x), ctypes.c_int(self._pos_y))
        return self._check_error(code, "Could not set image position")
