# -*- coding: utf-8 -*-
"""
Qudi-HiM

This file contains the hardware class representing a Kinetix teledyne/photometrics camera.
It is based on a Python wrapper for the dll functions of the PVCAM drivers. The wrapper can be found here :
https://github.com/Photometrics/PyVCAM

An extension to Qudi.

@author: JB Fiche
Created on Mon July 22, 2024
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
import ctypes
import numpy as np
from time import sleep
from core.module import Base
from core.configoption import ConfigOption
from interface.camera_interface import CameraInterface
from pyvcam import pvc, constants
from pyvcam.camera import Camera


# ======================================================================================================================
# Decorator (for debugging)
# ======================================================================================================================
def decorator_print_function(function):
    def new_function(*args, **kwargs):
        print(f'*** DEBUGGING *** Executing in hardware {function.__name__} from kinetix.py')
        return function(*args, **kwargs)
    return new_function


# ======================================================================================================================
# Class for controlling the Kinetix camera
# ======================================================================================================================
class KinetixCam(Base, CameraInterface):
    """ Hardware class for Kinetix teledyne-photometrics camera

    Example config for copy-paste:

    kinetix_camera:
        module.Class: 'camera.teledyne.kinetix.KinetixCam'
        default_exposure: 0.05
    """
    # config options
    _default_exposure = ConfigOption('default_exposure', 0.05)  # in seconds
    _default_acquisition_mode = ConfigOption('default_acquisition_mode', missing='error')
    camera_id = ConfigOption('camera_id', 0)
    _max_frames_number_video = ConfigOption('max_N_images_movie', missing='error')
    _default_trigger_mode = ConfigOption('default_trigger_mode', 'INTERNAL')
    _has_temp = ConfigOption('temperature_control', 'False')
    _has_shutter = ConfigOption('mechanical_shutter', 'False')
    _has_gain = ConfigOption('gain_control', 'False')
    _support_live_acquisition = ConfigOption('support_live_acquisition', 'False')
    _camera_name = ConfigOption('camera_name', missing='error')

    # camera attributes
    _width = 0  # current width
    _height = 0  # current height
    _full_width = 0  # maximum width of the sensor
    _full_height = 0  # maximum height of the sensor
    _exposure = _default_exposure
    _trigger_mode = _default_trigger_mode
    _acquisition_mode = _default_acquisition_mode
    _gain = 0
    n_frames = 1

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self.camera = None

    def on_activate(self):
        """ Initialisation performed during activation of the module.
        """
        pvc.init_pvcam()  # Initialize PVCAM
        n_cam = pvc.get_cam_total()
        if n_cam == 0:
            self.log.error('No camera detected - check the kinetix is switched ON and/or properly connected')
        elif n_cam > 1:
            self.log.error('More than one camera was detected - this program does not handle multiple camera')
        else:
            try:
                self.camera = next(Camera.detect_camera())  # Use generator to find first camera.
                self.camera.open()  # Open the camera.

                self.get_size()  # update the values _weight, _height
                self._full_width = self._width
                self._full_height = self._height

                # set some default parameters value - note the camera is already set to 'Dynamic Range' in order to get
                # the same intensity values for the displayed and saved data
                self.set_exposure(self._exposure)
                self._set_acquisition_mode(str(self._acquisition_mode))  # Set the camera in 'Dynamic Range' mode
                self._set_trigger_source(str(self._trigger_mode))  # Set the camera in 'Internal Trigger' mode

                # initialize the default acquisition parameters by launching a brief live acquisition - this step is
                # required to have access to the "check_frame_status" method without throwing an error
                self._start_acquisition(mode='Live')
                sleep(self._exposure * 2)
                self.camera.finish()

            except Exception as e:
                self.log.error(e)

    def on_deactivate(self):
        """ Camera will be deactivated and stopped during execution of this module.
        """
        self.camera.close()
        pvc.uninit_pvcam()

# ======================================================================================================================
# Camera Interface functions
# ======================================================================================================================

# ----------------------------------------------------------------------------------------------------------------------
# Getter and setter methods
# ----------------------------------------------------------------------------------------------------------------------

    def get_name(self):
        """
        Retrieve an identifier of the camera that the GUI can print.
        @return: string: name for the camera
        """
        self._camera_name = pvc.get_cam_name(0)
        return self._camera_name

    def get_size(self):
        """
        Retrieve size of the image in pixel.
        @return: tuple (int, int): Size (width, height)
        """
        sensor_size = self.camera.sensor_size
        self._width = sensor_size[0]
        self._height = sensor_size[1]

    def set_exposure(self, exposure):
        """
        Set the exposure time in ms.
        @param: exposure (float): desired new exposure time in s (but beware that default unit for Kinetix camera is ms)
        """
        self.camera.exp_time = exposure * 1000
        self._exposure = self.camera.exp_time / 1000

    def get_exposure(self):
        """
        Get the exposure time in seconds.
        @return: exposure time (float)
        """
        self._exposure = self.camera.exp_time / 1000
        return self._exposure

    @staticmethod
    def is_cooler_on():
        """
        Get the status of the camera cooler. For the Kinetix, it is always ON.
        @return: (int) 0 = cooler is OFF - 1 = cooler is ON
        """
        return 1

    def get_temperature(self):
        """
        Get the sensor temperature in degrees Celsius.
        @return: temp (float) sensor temperature
        """
        temp = pvc.get_param(self.camera.handle, constants.PARAM_TEMP, constants.ATTR_CURRENT)
        return temp

    def set_gain(self, gain):
        """
        Set the gain - gain is not available for the kinetix camera.
        @param: gain: (int) desired new gain
        @return: (bool)
        """
        return False

    def get_gain(self):
        """
        Get the gain
        @return: gain: (int)
        """
        return self._gain

    def get_ready_state(self):
        """
        Is the camera ready for an acquisition ?
        @return: ready ? (bool)
        """
        status = self.camera.check_frame_status()
        if (status == "EXPOSURE_IN_PROGRESS") or (status == "READOUT_IN_PROGRESS") or (status == "READOUT_FAILED"):
            return False
        else:
            return True

    def set_image(self, hbin, vbin, hstart, hend, vstart, vend):
        """
        Sets a ROI on the sensor surface.
        @param: hbin: (int) number of pixels to bin horizontally
        @param: vbin: (int) number of pixels to bin vertically.
        @param: hstart: (int) Start column
        @param: hend: (int) End column
        @param: vstart: (int) Start row
        @param: vend: (int) End row
        @return: (bool) return True if an error was detected
        """
        try:
            self._width = int(vend - vstart)
            self._height = int(hend - hstart)
            self.camera.set_roi(vstart, hstart, self._height, self._width)
            self.log.info(f'Set subarray: {self._height} x {self._width} pixels (rows x cols)')
            return False
        except Exception as e:
            self.log.error(f"The following error was encountered in set_image : {e}")
            return True

    def get_progress(self):
        """
        For the Kinetix, progress is handled in the "get_most_recent_image" method.
        """
        pass

    def get_max_frames(self):
        """ Return the maximum number of frames that can be handled by the camera for a single movie acquisition.
        Depending on the camera, multiple acquisition modes can be handled. A dictionary is used as output.
        @return:
            max_frames_dict (dict)
        """
        max_frames_dict = {'video': self._max_frames_number_video}
        return max_frames_dict

# ----------------------------------------------------------------------------------------------------------------------
# Methods to query the camera properties
# ----------------------------------------------------------------------------------------------------------------------

    def support_live_acquisition(self):
        """ Return whether the camera handle live acquisition.
        @return: (bool) True if supported, False if not
        """
        return self._support_live_acquisition

    def has_temp(self):
        """
        Does the camera support setting of the temperature?
        @return: (bool): has temperature ?
        """
        return self._has_temp

    def has_shutter(self):
        """
        Is the camera equipped with a mechanical shutter?
        If this function returns true, the attribute _shutter must also be defined in the hardware module
        @return: (bool): has shutter ?
        """
        return self._has_shutter

    def has_gain(self):
        """
        Is the camera enabling electronic gain control?
        If this function returns true, the attribute _gain must also be defined in the hardware module
        @return: (bool): has gain ?
        """
        return self._has_gain

# ----------------------------------------------------------------------------------------------------------------------
# Methods to handle camera acquisitions
# ----------------------------------------------------------------------------------------------------------------------

# Methods for displaying images on the GUI -----------------------------------------------------------------------------
    @decorator_print_function
    def start_single_acquisition(self):
        """
        Start acquisition for a single frame (snap mode) and return the acquired frame
        @return: frame (numpy array): acquired frame
        """
        frame = self._start_acquisition(mode='Single image')
        return frame

    @decorator_print_function
    def start_live_acquisition(self):
        """
        Start a continuous acquisition.
        @return: Success ? (bool)
        """
        try:
            self._start_acquisition(mode='Live')
            return True
        except Exception as e:
            self.log.error(f'The following error was encountered in start_live_acquisition : {e}')
            return False

    @decorator_print_function
    def stop_acquisition(self):
        """
        Stop/abort live or single acquisition
        @return: bool: Success ?
        """
        try:
            self.camera.finish()
            return True
        except Exception as e:
            self.log.error(f"The following error was encountered in stop_acquisition : {e}")
            return False

# Methods for saving image data ----------------------------------------------------------------------------------------
    @decorator_print_function
    def start_movie_acquisition(self, n_frames):
        """
        Set the conditions to save a movie and start the acquisition (fixed length mode).

        @param: (int) n_frames: number of frames
        @return: bool: Error ?
        """
        self.n_frames = n_frames  # needed to choose the correct case in get_acquired_data method
        try:
            self._start_acquisition(mode='Sequence')
            return False
        except Exception as e:
            if "PL_ERR_TOO_MANY_FRAMES" in str(e):
                self.log.error(f"{e} - The number of images is too large for the memory. Try using a smaller ROI")
            else:
                self.log.error(f"Error in start_movie_acquisition : {e}")
            return True

    @decorator_print_function
    def finish_movie_acquisition(self):
        """
        Reset the conditions used to save a movie to default.
        @return: bool: Success ?
        """
        try:
            self.camera.finish()
            self.n_frames = 1  # reset to default
            return True
        except Exception as e:
            self.log.error(e)
            return False

    def abort_movie_acquisition(self):
        """ Abort an acquisition.
        @return: (bool) Error ?
        """
        self._abort_acquisition()
        self._set_acquisition_mode(self._default_acquisition_mode)

    def wait_until_finished(self):
        """ Wait until an acquisition is finished.
        """
        pass

# Methods for acquiring image data using synchronization between lightsource and camera---------------------------------
    def prepare_camera_for_multichannel_imaging(self, frames, exposure, gain, save_path, file_format):
        """ Set the camera state for an experiment using synchronization between lightsources and the camera. Using
        typically an external trigger.

        @param: int frames: number of frames in a kinetic series / fixed length mode
        @param: float exposure: exposure time in seconds

        The following parameters are not needed for this camera. Only for compatibility with abstract function signature
        @param: int gain: gain setting
        @param: str save_path: complete path (without fileformat suffix) where the image data will be saved
        @param: str file_format: selected fileformat such as 'tiff', 'fits', ..
        """
        self.stop_acquisition()
        self.set_exposure(exposure)
        self.n_frames = frames
        self._set_trigger_source('EDGE')  # set the camera to "Edge Trigger" mode
        self._set_acquisition_mode('Dynamic Range')  # set the camera in Dynamic Range mode (to get 16-bit depth images)

    def reset_camera_after_multichannel_imaging(self):
        """
        Reset the camera to a default state after an experiment using synchronization between lightsources and the
        camera.
        """
        self.stop_acquisition()
        self._set_trigger_source('INTERNAL')
        self.n_frames = 1  # reset to default
        self._set_acquisition_mode('Dynamic Range')

# ----------------------------------------------------------------------------------------------------------------------
# Methods for image data retrieval
# ----------------------------------------------------------------------------------------------------------------------

    def get_most_recent_image(self, copy=True):
        """
        Return the last acquired image and the total number of acquired images. Used mainly for live display on gui
        during video saving. Note "copyData" is set to True when a copy of the data is required. When False, the image
        won't be accessible after stopping the acquisition.

        @param: (bool) copy : indicate whether the frame should be copied
        @return:
        frame (numpy array): latest acquired frame
        frame_count (int): number of acquired frames
        """
        try:
            frame, _, frame_count = self.camera.poll_frame(timeout_ms=1000, oldestFrame=False, copyData=copy)
            return frame['pixel_data'], frame_count
        except Exception as e:
            self.log.error(f"The following error was encountered in get_most_recent_image : {e}")
            return [], 0

    def get_acquired_data(self):
        """
        Return an array of the acquired data. This function is only used at the end of a sequence acquisition (not for
        live mode) and for the tasks. Therefore, it will return all the images acquired and available in the buffer.
        If the camera status is not compatible with data retrieval (for example if the number of frame is too high the
        acquisition is aborted), the function returns None.

        @return: (numpy ndarray) im_seq : data in format [n_frames, im_width, im_height]
        """
        status = self.camera.check_frame_status()

        if (status == "FRAME_AVAILABLE") or (status == "READOUT_COMPLETE"):
            self.log.info(f'Loading {self.n_frames} frames ...')
            im_seq = np.zeros((self.n_frames, self._width, self._height), dtype=np.uint16)
            for frame in range(self.n_frames):
                im, _, _ = self.camera.poll_frame(timeout_ms=1000, oldestFrame=True, copyData=False)
                im_seq[frame, :, :] = im['pixel_data']

        elif (status == "READOUT_IN_PROGRESS") or (status == "EXPOSURE_IN_PROGRESS"):
            self.log.error('Acquisition is still in process. Data are not accessible and cannot be saved.')
            im_seq = None

        else:
            im_seq = None

        return im_seq

# ======================================================================================================================
# Non-Interface functions
# ======================================================================================================================

# ----------------------------------------------------------------------------------------------------------------------
# Non-interface functions to handle acquisitions
# ----------------------------------------------------------------------------------------------------------------------
    def get_acquisition_mode(self):
        """
        Indicate the exposure mode currently used by the camera ('Sensitivity', 'Speed', 'Dynamic Range',
        'Sub-electron')
        @return: acq_mode (int): return a number according to the mode currently in use
        """
        acq_mode = self.camera.readout_port
        return acq_mode

    def _set_acquisition_mode(self, mode):
        """
        Set the acquisition readout mode (particularly important for the image format)
        @param mode (str): keyword for acquisition mode
        @return: (bool): indicate if the mode was correctly set
        """
        # translate mode codename into port-value
        if mode == 'Sensitivity':
            port_value = 0
        elif mode == 'Speed':
            port_value = 1
        elif mode == 'Dynamic Range':
            port_value = 2
        elif mode == 'Sub-Electron':
            port_value = 3
        else:
            self.log.warn('The readout mode selected does not exist - The camera is set to "Dynamic Range" as default')
            port_value = 2

        # set the mode
        try:
            self.camera.readout_port = port_value
        except Exception as e:
            self.log.error(e)
        else:
            sleep(0.1)
            check_mode = self.get_acquisition_mode()
            if check_mode == mode:
                return 0
            else:
                return -1

    @decorator_print_function
    def _start_acquisition(self, mode='Live'):
        """
        Launch an acquisition according to the indicated mode.
        @param mode: (str) indicate the mode to use for acquiring the image
        @return: frame (numpy array): latest acquired frame - only for the 'Single image' mode
        """
        if mode == 'Live':
            self.camera.start_live(exp_time=int(self._exposure * 1000))
        elif mode == 'Sequence':
            self.camera.start_seq(exp_time=int(self._exposure * 1000), num_frames=self.n_frames)
        elif mode == 'Single image':
            frame = self.camera.get_frame(exp_time=int(self._exposure * 1000))
            return frame
        else:
            self.log.warning("The mode requested does not exist - Acquisition will not start")

    def _abort_acquisition(self):
        """ Abort an acquisition prior completion.
        """
        try:
            self.camera.abort()
        except Exception as e:
            self.log.error(f"Error in _abort_acquisition : {e}")

# ----------------------------------------------------------------------------------------------------------------------
# Trigger
# ----------------------------------------------------------------------------------------------------------------------
    def _set_trigger_source(self, source):
        """
        Set the trigger source. For the kinetix the available trigger modes can be accessed using the "exp_modes"
        method.
        @param string source: string corresponding to certain TriggerMode 'INTERNAL', 'EDGE', 'SOFTWARE', ...
        @return int check_val: ok: 0, not ok: -1
        """
        # set the exposure mode for the camera
        if source == 'INTERNAL':
            exposure_mode = 1792
        elif source == 'EDGE':
            exposure_mode = 2304
        elif source == 'SOFTWARE':
            exposure_mode = 3072
        else:
            self.log.warning('Unknown trigger source')
            return -1

        self.camera.exp_mode = exposure_mode

        # wait 100ms and check the mode was properly changed
        sleep(0.1)
        check_trigger_mode = self._get_trigger_source()
        if check_trigger_mode == exposure_mode:
            return 0
        else:
            return -1

    def _get_trigger_source(self):
        """
        Return the trigger source currently used for the camera
        @return: trigger_source (str): indicates the type of trigger mode
        """
        trigger_source = self.camera.exp_mode
        return trigger_source