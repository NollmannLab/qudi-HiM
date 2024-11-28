# -*- coding: utf-8 -*-
"""
Qudi-CBS

This file contains the hardware class representing an Andor iXon Ultra camera.

This module was first created by F.Barho for the Ixon-897 and then adapted for the 888-ultra.

@author: JB. Fiche (original code from F. Barho)
Created on Wed Nov 27 2024

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
from enum import Enum
from ctypes import *
from pyAndorSDK2 import atmcd
from pyAndorSDK2.atmcd_errors import Error_Codes
from pyAndorSDK2.atmcd_codes import Read_Mode, Trigger_Mode, Acquisition_Mode
from time import sleep
from core.module import Base
from core.configoption import ConfigOption
from interface.camera_interface import CameraInterface


# class ReadMode(Enum):
#     FVB = 0
#     MULTI_TRACK = 1
#     RANDOM_TRACK = 2
#     SINGLE_TRACK = 3
#     IMAGE = 4
#
#
# class AcquisitionMode(Enum):
#     SINGLE_SCAN = 1
#     ACCUMULATE = 2
#     KINETICS = 3
#     FAST_KINETICS = 4
#     RUN_TILL_ABORT = 5
#
#
# class TriggerMode(Enum):
#     INTERNAL = 0
#     EXTERNAL = 1
#     EXTERNAL_START = 6
#     EXTERNAL_EXPOSURE = 7
#     SOFTWARE_TRIGGER = 10
#     EXTERNAL_CHARGE_SHIFTING = 12

ERROR_DICT = {}


class IxonUltra(Base, CameraInterface):
    """ Hardware class for Andor Ixon Ultra 897. Example config for copy-paste:

    andor_ultra_camera:
        module.Class: 'camera.andor.iXon888_ultra.IxonUltra'
        sdk_location: 'C:\Program Files\Andor SDK\Python\pyAndorSDK2'
        default_exposure: 0.05  # en s
        default_read_mode: 'FULLIMAGE'
        default_temperature: -60
        default_cooler_on: True
        default_acquisition_mode: 'KINETIC'
        default_trigger_mode: 'INTERNAL'
    """
    # config options
    _sdk_location = ConfigOption('sdk_location', missing='error')
    _default_exposure = ConfigOption('default_exposure', 0.05)  # default exposure value 0.1 s
    _default_read_mode = ConfigOption('default_read_mode', 'IMAGE')
    _default_temperature = ConfigOption('default_temperature', -60)
    _default_cooler_on = ConfigOption('default_cooler_on', True)
    _default_acquisition_mode = ConfigOption('default_acquisition_mode', 'KINETICS')
    _default_trigger_mode = ConfigOption('default_trigger_mode', 'INTERNAL')

    # camera attributes
    _exposure = _default_exposure
    _temperature = _default_temperature
    _cooler_on = _default_cooler_on
    _read_mode = _default_read_mode
    _acquisition_mode = _default_acquisition_mode
    _trigger_mode = _default_trigger_mode

    _gain = 0
    _width = 0
    _height = 0
    _full_width = 0  # store this for default sensor size
    _full_height = 0  # for default sensor size
    # _last_acquisition_mode = None  # useful if config changes during acquisition
    _supported_read_modes = None
    _supported_acquisition_modes = None
    _supported_trigger_modes = None
    _max_cooling = -80
    _camera_name = 'iXon Ultra 897'
    _shutter = "closed"

    _live = False
    _acquiring = False
    _scans = 1
    _cur_image = None

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self.sdk = None
        self.dll = None

    def on_activate(self):
        """ Initialisation performed during activation of the module. Note that for the moment, only one camera is
        handled by the setup.
        """
        try:
            self.sdk = atmcd("")  # Load the atmcd library
            ret = self.sdk.Initialize(self._sdk_location)  # Initialize camera
            if Error_Codes.DRV_SUCCESS == ret:
                (ret, iSerialNumber) = self.sdk.GetCameraSerialNumber()
                print(f"Function GetCameraSerialNumber returned {ret} Serial No: {iSerialNumber}")
            else:
                print(f"Cannot continue, could not initialise camera - error code : {ret}")

            self._width, self._height = self._get_detector()
            self._full_width, self._full_height = self._width, self._height
            self._set_read_mode(self._read_mode)
            self._set_trigger_mode(self._trigger_mode)
            self._set_exposuretime(self._exposure)
            self._set_acquisition_mode(self._acquisition_mode)
            # start cooler if specified in config (otherwise it must be done via the console)
            self._set_cooler(self._cooler_on)
            self._set_temperature(self._default_temperature)
            # set the preamp gain (it is not accessible by the user interface)
            self._set_preamp_gain(2)  # pass in the index as argument to set the gain to a specific value.
        except Exception as e:
            self.log.error(f'Andor iXon Ultra 888 Camera: Connection failed: {e}.')

    def on_deactivate(self):
        """ Deinitialisation performed during deactivation of the module.
        """
        self.stop_acquisition()
        self._set_shutter(0, 0, 0.1, 0.1)
        self._set_cooler(False)
        self._shut_down()

# ======================================================================================================================
# Camera Interface functions
# ======================================================================================================================

# ----------------------------------------------------------------------------------------------------------------------
# Methods for handling error message
# ----------------------------------------------------------------------------------------------------------------------

    def check_error(self, ret, func):
        """
        Error handling function returning an error message if drv_success not working
        @return : return False if no error and True if an error was detected
        """
        if Error_Codes.DRV_SUCCESS != ret:
            self.log.error(f'The command issued by {func} returned the following error message : {Error_Codes(ret)}')
            return True
        else:
            return False

# ----------------------------------------------------------------------------------------------------------------------
# Getter and setter methods
# ----------------------------------------------------------------------------------------------------------------------

    def get_name(self):
        """
        Retrieve an identifier of the camera that the GUI can print.
        @return: (str) name for the camera
        """
        return self._camera_name

    def get_size(self):
        """
        Retrieve size of the image in pixel.
        @return: (tuple (int, int))  Size (width, height)
        """
        return self._width, self._height

    def set_exposure(self, exposure):
        """ Set the exposure time in seconds.

        :param: float exposure: desired new exposure time

        :return: bool: success ?
        """
        msg = self._set_exposuretime(exposure)
        if msg == "DRV_SUCCESS":
            self._exposure = exposure
            return True
        else:
            return False

    def get_exposure(self):
        """ Get the exposure time in seconds.

        :return: float exposure time
        """
        self._get_acquisition_timings()
        return self._exposure

    # new version in Qudi-CBS using the em gain
    def set_gain(self, gain):
        """ Set the electron multiplying gain.

        :param: int gain: desired new gain.

        :return bool: Success?
        """
        msg = self._set_emccd_gain(gain)
        if msg == "DRV_SUCCESS":
            self._gain = gain
            return True
        else:
            return False

    def get_gain(self):
        """ Get the electron multiplying gain

        :return int: em gain """
        self._gain = self._get_emccd_gain()
        return self._gain

    def get_ready_state(self):
        """ Is the camera ready for an acquisition ?

        :return: bool: ready ?
        """
        status = c_int()
        self._get_status(status)
        if ERROR_DICT[status.value] == 'DRV_IDLE':
            return True
        else:
            return False

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
        msg = self._set_image(hbin, vbin, hstart, hend, vstart, vend)
        if msg != 'DRV_SUCCESS':
            return -1
        return 0

    def get_progress(self):
        """ Retrieves the total number of acquired images during a movie acquisition.

        :return: int progress: total number of acquired images.
        """
        index = c_long()
        error_code = self.dll.GetTotalNumberImagesAcquired(byref(index))
        if ERROR_DICT[error_code] != 'DRV_SUCCESS':
            self.log.warning('Could not get number of images acquired: {}'.format(ERROR_DICT[error_code]))
            return
        return index.value

# ----------------------------------------------------------------------------------------------------------------------
# Methods to query the camera properties
# ----------------------------------------------------------------------------------------------------------------------

    def support_live_acquisition(self):
        """ Return whether or not the camera can take care of live acquisition.

        :return: bool: True if supported, False if not
        """
        return True

    def has_temp(self):
        """ Does the camera support setting of the temperature?

        :return: bool: has temperature ?
        """
        return True

    def has_shutter(self):
        """ Is the camera equipped with a mechanical shutter?

        If this function returns true, the attribute _shutter must also be defined in the hardware module

        :return: bool: has shutter ?
        """
        return True

# ----------------------------------------------------------------------------------------------------------------------
# Methods to handle camera acquisitions
# ----------------------------------------------------------------------------------------------------------------------

# Methods for displaying images on the GUI -----------------------------------------------------------------------------
    def start_single_acquisition(self):
        """ Start a single acquisition.

        :return: bool: Success ?
        """
        if self._shutter == 'closed':
            msg = self._set_shutter(0, 1, 0.1, 0.1)
            if msg == 'DRV_SUCCESS':
                self._shutter = 'open'
            else:
                self.log.error('shutter did not open.{0}'.format(msg))

        if self._live:
            return False
        else:
            self._acquiring = True  # do we need this here?
            self._set_acquisition_mode('SINGLE_SCAN')
            # self.log.info('set acquisition mode: single scan')
            msg = self._start_acquisition()
            if msg != "DRV_SUCCESS":
                return False
            self._acquiring = False
            return True

    def start_live_acquisition(self):
        """ Start a continuous acquisition.

        :return: bool: Success ?
        """
        # handle the variables indicating the status
        if self.support_live_acquisition():
            self._live = True
            self._acquiring = False

        # make sure shutter is opened
        if self._shutter == 'closed':
            msg = self._set_shutter(0, 1, 0.1, 0.1)
            if msg == 'DRV_SUCCESS':
                self._shutter = 'open'
            else:
                self.log.error('shutter did non open. {}'.format(msg))

        self._set_acquisition_mode('RUN_TILL_ABORT')
        msg = self._start_acquisition()
        if msg != "DRV_SUCCESS":
            return False

        return True

    def stop_acquisition(self):
        """ Stop/abort live or single acquisition

        :return: bool: Success ?
        """
        msg = self._abort_acquisition()
        self._set_acquisition_mode(self._default_acquisition_mode)  # reset to default (run till abort typically)
        if msg == "DRV_SUCCESS":
            self._live = False
            self._acquiring = False
            return True
        else:
            return False

# Methods for saving image data ----------------------------------------------------------------------------------------
    def start_movie_acquisition(self, n_frames):
        """ Set the conditions to save a movie and start the acquisition (typically kinetic / fixed length mode).

        :param: int n_frames: number of frames

        :return: bool: Success ?
        """
        # handle the variables indicating the status
        if self.support_live_acquisition():
            self._live = True
            self._acquiring = False

        # make sure shutter is opened
        if self._shutter == 'closed':
            msg = self._set_shutter(0, 1, 0.1, 0.1)
            if msg == 'DRV_SUCCESS':
                self._shutter = 'open'
            else:
                self.log.error('shutter did non open. {}'.format(msg))

        self._set_acquisition_mode('KINETICS')
        self.set_exposure(self._exposure)  # make sure this is taken into account, call it after acquisition mode setting
        self._set_number_kinetics(n_frames)
        self._scans = n_frames  # set this attribute to get the right dimension for get_acquired_data method
        msg = self._start_acquisition()
        if msg != "DRV_SUCCESS":
            return False

        return True

    def finish_movie_acquisition(self):
        """ Reset the conditions used to save a movie to default.

        :return: bool: Success ?
        """
        # no abort_acquisition needed because acquisition finishes when the number of frames is reached
        self._set_acquisition_mode(self._default_acquisition_mode)  # reset to default (run till abort typically)
        self._scans = 1  # reset to default number of scans. this is important so that the other acquisition modes run correctly
        self._live = False
        self._acquiring = False
        return True
        # or return True only if _set_aquisition_mode terminates without error ? to test which is the better option

    def wait_until_finished(self):
        """ Wait until an acquisition is finished. To be used with kinetic acquisition mode.

        :return: None
        """
        status = c_int()
        self._get_status(status)
        while ERROR_DICT[status.value] != 'DRV_IDLE':
            status = c_int()
            self._get_status(status)
        return

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
        self._abort_acquisition()  # as safety
        self._set_acquisition_mode('KINETICS')
        self._set_trigger_mode('EXTERNAL')
        # add here eventually other settings .. frame transfer etc.

        self.set_gain(gain)
        self.set_exposure(exposure)

        # set the number of frames
        self._set_number_kinetics(frames)

        # set spooling
        if file_format == 'fits':
            self._set_spool(1, 5, save_path, 10)
        else:  # use 'tiff' as default case # add other options if needed
            self._set_spool(1, 7, save_path, 10)

        # open the shutter
        if self._shutter == 'closed':
            msg = self._set_shutter(0, 1, 0.1, 0.1)
            if msg == 'DRV_SUCCESS':
                self._shutter = 'open'
            else:
                self.log.error('shutter did non open. {}'.format(msg))
        sleep(1.5)  # wait until shutter is opened

        # start the acquisition. Camera waits for trigger
        self._start_acquisition()

    def reset_camera_after_multichannel_imaging(self):
        """ Reset the camera to a default state after an experiment using synchronization between lightsources and
         the camera.

         :return: None
         """
        self._abort_acquisition()
        self._set_spool(0, 7, '', 10)
        self._set_acquisition_mode('RUN_TILL_ABORT')
        self._set_trigger_mode('INTERNAL')

# ----------------------------------------------------------------------------------------------------------------------
# Methods for image data retrieval
# ----------------------------------------------------------------------------------------------------------------------

    def get_most_recent_image(self):
        """ Return an array of last acquired image. Used mainly for live display on gui during video saving.

        :return: numpy array: image data in format [[row],[row]...]

        Each pixel might be a float, integer or sub pixels
        """
        width = self._width
        height = self._height
        dim = width * height

        dim = int(dim)
        image_array = np.zeros(dim)
        cimage_array = c_int * dim
        cimage = cimage_array()

        error_code = self.dll.GetMostRecentImage(byref(cimage), dim)
        if ERROR_DICT[error_code] != 'DRV_SUCCESS':
            self.log.warning('Couldn\'t retrieve an image. {0}'.format(ERROR_DICT[error_code]))
        else:
            for i in range(len(cimage)):
                image_array[i] = cimage[i]

        image_array = np.reshape(image_array, (self._height, self._width))

        return image_array

    def get_acquired_data(self):
        """ Return an array of the acquired data.
        Depending on the acquisition mode, this can be just one frame (single scan, run_till_abort)
        or the entire data as a 3D stack (kinetic series)

        :return: numpy ndarray: image data in format [[row],[row]...]

        Each pixel might be a float, integer or sub pixels
        """
        width = self._width
        height = self._height

        if self._read_mode == 'IMAGE':
            if self._acquisition_mode == 'SINGLE_SCAN':
                dim = width * height
            elif self._acquisition_mode == 'KINETICS':
                dim = width * height * self._scans
            elif self._acquisition_mode == 'RUN_TILL_ABORT':
                dim = width * height
            else:
                self.log.error('Your acquisition mode is not covered currently')
                return
        elif self._read_mode == 'SINGLE_TRACK' or self._read_mode == 'FVB':
            if self._acquisition_mode == 'SINGLE_SCAN':
                dim = width
            elif self._acquisition_mode == 'KINETICS':
                dim = width * self._scans
            else:
                self.log.error('Your acquisition mode is not covered currently')
                return
        else:
            self.log.error('Your acquisition mode is not covered currently')
            return

        dim = int(dim)
        image_array = np.zeros(dim)
        cimage_array = c_int * dim
        cimage = cimage_array()

        if self._acquisition_mode == 'RUN_TILL_ABORT':
            error_code = self.dll.GetMostRecentImage(pointer(cimage), dim)
        else:
            error_code = self.dll.GetAcquiredData(pointer(cimage), dim)
        if ERROR_DICT[error_code] != 'DRV_SUCCESS':
            self.log.warning('Couldn\'t retrieve an image. {0}'.format(ERROR_DICT[error_code]))
        else:
            # self.log.debug('image length {0}'.format(len(cimage)))  # commented for tests fb 20 jan
            for i in range(len(cimage)):
                # could be problematic for 'FVB' or 'SINGLE_TRACK' readmode
                image_array[i] = cimage[i]

        if self._scans > 1:  # distinguish between 3D and 2D case
            image_array = np.reshape(image_array,
                                     (self._scans, self._height, self._width))  # row major, so, height comes before width
        else:
            image_array = np.reshape(image_array, (self._height, self._width))

        self._cur_image = image_array
        return image_array

# ======================================================================================================================
# Non-Interface functions
# ======================================================================================================================

# pseudo-interface functions (called from camera logic when camera name is iXon Ultra or when has_temp returns true)----
    def get_kinetic_time(self):
        """ Get the kinetic time in seconds.

        :return: float kinetic time
        """
        self._get_acquisition_timings()
        return self._kinetic

    # def set_temperature(self, temp):
    #     """ Set the temperature setpoint for the camera cooler
    #     @param: temp (int): desired new temperature
    #     """
    #     ret = self._set_temperature(temp)
    #     if msg == "DRV_SUCCESS":
    #         return True
    #     else:
    #         return False

    def get_temperature(self):
        """ Get the current temperature.

        :return int: temperature
        """
        temp = c_int()
        error_code = self.dll.GetTemperature(byref(temp))
        pass_returns = ['DRV_TEMP_STABILIZED', 'DRV_TEMP_NOT_REACHED', 'DRV_TEMP_DRIFT', 'DRV_TEMP_NOT_STABILIZED']
        if ERROR_DICT[error_code] not in pass_returns:
            self.log.warning('Can not retrieve temperature: {}'.format(ERROR_DICT[error_code]))
        return temp.value

    def is_cooler_on(self):
        """ Checks the status of the cooler.

        :return: int: 0: cooler is off, 1: cooler is on
        """
        cooler_status = c_int()
        error_code = self.dll.IsCoolerOn(byref(cooler_status))
        if ERROR_DICT[error_code] != 'DRV_SUCCESS':
            self.log.warning('Can not retrieve cooler state: {}'.format(ERROR_DICT[error_code]))
        return cooler_status.value

# ----------------------------------------------------------------------------------------------------------------------
# Non-interface functions to handle acquisitions
# ----------------------------------------------------------------------------------------------------------------------

    def _start_acquisition(self):
        error_code = self.dll.StartAcquisition()
        if self._trigger_mode == 'INTERNAL':
            self.dll.WaitForAcquisition()
        return ERROR_DICT[error_code]

    def wait_for_acquisition(self):
        error_code = self.dll.WaitForAcquisition()
        if ERROR_DICT[error_code] != 'DRV_SUCCESS':
            self.log.info('non-acquisition event occured')
        return ERROR_DICT[error_code]

    def _abort_acquisition(self):
        error_code = self.dll.AbortAcquisition()
        return ERROR_DICT[error_code]

    def _shut_down(self):
        error_code = self.sdk.ShutDown()
        return ERROR_DICT[error_code]

# ----------------------------------------------------------------------------------------------------------------------
# Non-interface setter functions
# ----------------------------------------------------------------------------------------------------------------------

    def _set_shutter(self, typ, mode, closingtime, openingtime):
        """
        @param int typ:   0 Output TTL low signal to open shutter
                          1 Output TTL high signal to open shutter
        @param int mode:  0 Fully Auto
                          1 Permanently Open
                          2 Permanently Closed
                          4 Open for FVB series
                          5 Open for any series
        """
        typ, mode, closingtime, openingtime = c_int(typ), c_int(mode), c_float(closingtime), c_float(openingtime)
        error_code = self.dll.SetShutter(typ, mode, closingtime, openingtime)

        return ERROR_DICT[error_code]

    def _set_exposuretime(self, time):
        """
        @param time: (float) exposure duration in s
        """
        ret = self.sdk.SetExposureTime(time)
        self.check_error(ret, "_set_exposuretime")

    def _set_read_mode(self, mode):
        """ This function will set the read mode of the camera. Note that if the read mode is set to "Image", then the
        size of the output image is also set using the values width / height (not the default values, in case a ROI was
        defined before)

        @param mode : (string) string corresponding to certain ReadMode
        """
        if hasattr(Read_Mode, mode):
            n_mode = getattr(Read_Mode, mode).value
            ret = self.sdk.SetReadMode(n_mode)
            err = self.check_error(ret, "_set_read_mode")

            if mode == 'IMAGE':
                self._set_image(1, 1, 1, self._width, 1, self._height)

            if err:
                self.log.warning('Camera Readmode was not set!')
            else:
                self._read_mode = mode

        else:
            self.log.warning(f'{mode} readmode is not supported')

        # check_val = 0
        # if hasattr(ReadMode, mode):
        #     n_mode = getattr(ReadMode, mode).value
        #     n_mode = c_int(n_mode)
        #     error_code = self.dll.SetReadMode(n_mode)
        #     if mode == 'IMAGE':
        #         self.log.debug("width:{0}, height:{1}".format(self._width, self._height))
        #         msg = self._set_image(1, 1, 1, self._width, 1, self._height)
        #         if msg != 'DRV_SUCCESS':
        #             self.log.warning('{0}'.format(ERROR_DICT[error_code]))
        #     # put the condition on error_code here
        #     if ERROR_DICT[error_code] != 'DRV_SUCCESS':
        #         self.log.warning('Readmode was not set: {0}'.format(ERROR_DICT[error_code]))
        #         check_val = -1
        #     else:
        #         self._read_mode = mode
        # else:
        #     self.log.warning('{} readmode is not supported'.format(mode))
        #     check_val = -1
        #
        # return check_val

    def _set_trigger_mode(self, mode):
        """
        @param mode: (string) indicate the selected TriggerMode
        """
        if hasattr(Trigger_Mode, mode):
            n_mode = getattr(Trigger_Mode, mode).value
            ret = self.sdk.SetTriggerMode(n_mode)
            err = self.check_error(ret, "_set_trigger_mode")

            if err:
                self.log.warning('Camera trigger was not set')
            else:
                self._trigger_mode = mode
        else:
            self.log.warning(f'{mode} trigger mode is not supported')

    def _set_image(self, hbin, vbin, hstart, hend, vstart, vend):
        """
        This function allows to select a subimage on the sensor.

        @param int hbin: number of pixels to bin horizontally
        @param int vbin: number of pixels to bin vertically.
        @param int hstart: Start column (inclusive)
        @param int hend: End column (inclusive)
        @param int vstart: Start row (inclusive)
        @param int vend: End row (inclusive).
        """
        ret = self.sdk.SetImage(hbin, vbin, hstart, hend, vstart, vend)
        err = self.check_error(ret, "_set_image")
        if not err:
            self._hbin = hbin
            self._vbin = vbin
            self._hstart = hstart
            self._hend = hend
            self._vstart = vstart
            self._vend = vend
            self._width = int((self._hend - self._hstart + 1) / self._hbin)
            self._height = int((self._vend - self._vstart + 1) / self._vbin)

    def _set_output_amplifier(self, typ):
        """
        @param c_int typ: 0: EMCCD gain, 1: Conventional CCD register
        @return string: error code
        """
        error_code = self.dll.SetOutputAmplifier(typ)
        return ERROR_DICT[error_code]

    def _set_preamp_gain(self, index):
        """
        @param index (int): indicate the preamp gain value
        """
        ret = self.sdk.SetPreAmpGain(index)
        self.check_error(ret, "_set_preamp_gain")

    def _set_temperature(self, temp):
        """ Sets a new temperature setpoint for the camera cooler
        @param: temp (int): temperature setpoint
        """
        ret = self.sdk.SetTemperature(temp)
        self.check_error(ret, "_set_temperature")

    def _set_acquisition_mode(self, mode):
        """
        Function to set the acquisition mode
        @param mode: (str) acquisition mode
        @return: error code: ok = 0, error = -1
        """
        if hasattr(Acquisition_Mode, mode):
            n_mode = getattr(Acquisition_Mode, mode).value
            ret = self.sdk.SetAcquisitionMode(n_mode)
            err = self.check_error(ret, "_set_acquisition_mode")
            if not err:
                self._acquisition_mode = mode
        else:
            self.log.warning(f'{mode} acquisition mode is not supported')

    def _set_cooler(self, state):
        """ This method is called to switch the cooler on or off
        @param: state (bool): cooler on = True, cooler off = False
        @return: error message
        """
        if state:
            ret = self.sdk.CoolerON()
        else:
            ret = self.sdk.CoolerOFF()
        self.check_error(ret, "_set_cooler")

    # modified fb: frame transfer has no effect when acq mode is single scan or fast_kinetics. it has an effect for
    # kinetic mode however
    def _set_frame_transfer(self, transfer_mode):
        """ set the frame transfer mode

        @param: int tranfer_mode: 0: off, 1: on

        @returns: int error code 0 = ok, -1 = error"""
        acq_mode = self._acquisition_mode

        if (acq_mode == 'SINGLE_SCAN') | (acq_mode == 'FAST_KINETICS'):
            self.log.debug('Setting of frame transfer mode has no effect in acquisition '
                           'mode \'SINGLE_SCAN\' or \'FAST_KINETICs\'.')
            return -1
        else:
            rtrn_val = self.dll.SetFrameTransferMode(transfer_mode)

            if ERROR_DICT[rtrn_val] == 'DRV_SUCCESS':
                return 0
            else:
                self.log.warning('Could not set frame transfer mode:{0}'.format(ERROR_DICT[rtrn_val]))
                return -1

    def _set_em_gain_mode(self, mode):
        """ possible settings:
            mode = 0: the em gain is controlled by DAQ settings in the range 0-255. Default mode
            mode = 1: the em gain is controlled by DAQ settings in the range 0-4095.
            mode = 2: Linear mode.
            mode = 3: Real EM gain.
        """
        mode = c_int(mode)
        error_code = self.dll.SetEMGainMode(mode)
        return ERROR_DICT[error_code]

    def _set_emccd_gain(self, gain):
        """ allows to change the gain value. The allowed range depends on the gain mode currently used.

        @params: int gain: new gain value

        @returns: str errormessage"""
        gain = c_int(gain)
        error_code = self.dll.SetEMCCDGain(gain)
        return ERROR_DICT[error_code]

    def _set_spool(self, active, method, name, framebuffersize):
        """
        @params: int active: 0: disable spooling, 1: enable spooling
        @params: int method: indicates the format of the files written to disk.
                             0: sequence of 32-bit integers
                             1: 32-bit integer if data is being accumulated each scan, otherwise 16-bit integers
                             2: sequence of 16-bit integers
                             3: multiple directory structure with multiple images per file and multiple files per directory
                             4: spool to RAM disk
                             5: spool to 16-bit fits file
                             6: spool to andor sif format
                             7: spool to 16-bit tiff file
                             8: similar to method 3 but with data compression
                str name: filename stem (can include path) such as 'C:\\Users\\admin\\qudi-cbs-testdata\\images\\testimg'
                int framebuffersize: size of the internal circular buffer used as temporary storage (number of images).
                                     typical value = 10
        """
        active, method, framebuffersize = c_int(active), c_int(method), c_int(framebuffersize)
        name = c_char_p(name.encode('utf-8'))
        error_code = self.dll.SetSpool(active, method, name, framebuffersize)
        return ERROR_DICT[error_code]

    def _set_number_kinetics(self, number):
        """ set the number of scans for a kinetic series acquisition

        @params: int number: number of scans
        """
        number = c_int(number)
        error_code = self.dll.SetNumberKinetics(number)
        return ERROR_DICT[error_code]

# ----------------------------------------------------------------------------------------------------------------------
# Non-interface getter functions
# ----------------------------------------------------------------------------------------------------------------------

    def _get_status(self, status):
        """
        @params: c_int status: its value corresponds to the current camera status (idle, tempcycle, acquiring, ..)
        @returns:  error message: DRV_SUCCESS if ok, DRV_NOT_INITIALIZED if not ok"""
        error_code = self.dll.GetStatus(byref(status))
        return ERROR_DICT[error_code]

    def _get_detector(self):
        """ retrieves the size of the detector in pixels
        @params: c_int nx_px
        @params: c_int ny_px
        @returns: error message
                  nx_px, ny_px (int) : number of pixels along the width and height of the detector
        """
        error_code, nx_px, ny_px = self.sdk.GetDetector()
        self.check_error(error_code, "_get_detector")
        return nx_px, ny_px

    def _get_camera_serialnumber(self):
        # maybe reset also the old version here or add a variable to access the actual value not the errorcode
        """
        Gives serial number
        Parameters
        """
        number = c_int()
        error_code = self.dll.GetCameraSerialNumber(byref(number))
        return ERROR_DICT[error_code]

    def _get_acquisition_timings(self):
        """ Retrieves the current valid acquisition timing information.
        This method should be called after all the acquisition settings have been made (set exposuretime, set readmode, ..

        Updates the private attributes _exposure, _accumulate, _kinetic

        @returns: str error message
        """
        exposure = c_float()
        accumulate = c_float()
        kinetic = c_float()
        error_code = self.dll.GetAcquisitionTimings(byref(exposure), byref(accumulate), byref(kinetic))
        self._exposure = exposure.value
        self._accumulate = accumulate.value
        self._kinetic = kinetic.value
        return ERROR_DICT[error_code]

    def _get_oldest_image(self):
        """ Return an array of last acquired image.

        @return numpy array: image data in format [[row],[row]...]

        Each pixel might be a float, integer or sub pixels
        """

        width = self._width
        height = self._height

        if self._read_mode == 'IMAGE':
            if self._acquisition_mode == 'SINGLE_SCAN':
                dim = width * height / self._hbin / self._vbin
            elif self._acquisition_mode == 'KINETICS':
                dim = width * height / self._hbin / self._vbin * self._scans
        elif self._read_mode == 'SINGLE_TRACK' or self._read_mode == 'FVB':
            if self._acquisition_mode == 'SINGLE_SCAN':
                dim = width
            elif self._acquisition_mode == 'KINETICS':
                dim = width * self._scans

        dim = int(dim)
        image_array = np.zeros(dim)
        cimage_array = c_int * dim
        cimage = cimage_array()
        error_code = self.dll.GetOldestImage(pointer(cimage), dim)
        if ERROR_DICT[error_code] != 'DRV_SUCCESS':
            self.log.warning('Couldn\'t retrieve an image')
        else:
            self.log.debug('image length {0}'.format(len(cimage)))
            for i in range(len(cimage)):
                # could be problematic for 'FVB' or 'SINGLE_TRACK' readmode
                image_array[i] = cimage[i]

        image_array = np.reshape(image_array, (int(self._width / self._hbin), int(self._height / self._vbin)))
        return image_array

    def _get_number_amp(self):
        """
        @return int: Number of amplifiers available
        """
        n_amps = c_int()
        self.dll.GetNumberAmp(byref(n_amps))
        return n_amps.value

    def _get_number_preamp_gains(self):
        """
        Number of gain settings available for the pre amplifier

        @return int: Number of gains available
        """
        n_gains = c_int()
        self.dll.GetNumberPreAmpGains(byref(n_gains))
        return n_gains.value

    def _get_preamp_gain(self, index):
        """
        :param: int index: ranging from 0 to (number of preamp gains-1)
        Function returning
        @return tuple (int1, int2): First int describing the gain setting, second value the actual gain
        """
        index = c_int(index)
        gain = c_float()
        self.dll.GetPreAmpGain(index, byref(gain))
        return index.value, gain.value

    # def _get_temperature_f(self):
    #     """
    #     Status of the cooling process + current temperature
    #     @return: (float, str) containing current temperature and state of the cooling process
    #     """
    #     temp = c_float()
    #     error_code = self.dll.GetTemperatureF(byref(temp))
    #
    #     return temp.value, ERROR_DICT[error_code]

    def _get_size_of_circular_ring_buffer(self):
        index = c_long()
        error_code = self.dll.GetSizeOfCircularBuffer(byref(index))
        if ERROR_DICT[error_code] != 'DRV_SUCCESS':
            self.log.error('Can not retrieve size of circular ring '
                           'buffer: {0}'.format(ERROR_DICT[error_code]))
        return index.value

    def _get_number_new_images(self):
        first = c_long()
        last = c_long()
        error_code = self.dll.GetNumberNewImages(byref(first), byref(last))
        msg = ERROR_DICT[error_code]
        pass_returns = ['DRV_SUCCESS', 'DRV_NO_NEW_DATA']
        if msg not in pass_returns:
            self.log.error('Can not retrieve number of new images {0}'.format(ERROR_DICT[error_code]))

        return first.value, last.value

    def _get_em_gain_range(self):
        """ Retrieves the minimum and maximum values of the current selected electron multiplying gain mode

        @returns int: low: minimum value
                 int: high: maximum value
        """
        low = c_int()
        high = c_int()
        error_code = self.dll.GetEMGainRange(byref(low), byref(high))
        if ERROR_DICT[error_code] != 'DRV_SUCCESS':
            self.log.warning('Could not retrieve EM gain range. {}'.format(ERROR_DICT[error_code]))
            return
        return low.value, high.value

    def _get_emccd_gain(self):
        """ Returns the current gain setting"""
        gain = c_int()
        error_code = self.dll.GetEMCCDGain(byref(gain))
        if ERROR_DICT[error_code] != 'DRV_SUCCESS':
            self.log.warning('Could not retrieve EM gain. {}'.format(ERROR_DICT[error_code]))
            return
        return gain.value

    def _get_spool_progress(self):
        """ Retrieves information on the progress of the current spool operation.
        The corresponding dll function is deprecated.

        @returns: int: number of images that have been saved to disk during the current kinetic series
        """
        index = c_long()
        error_code = self.dll.GetSpoolProgress(byref(index))
        if ERROR_DICT[error_code] != 'DRV_SUCCESS':
            self.log.warning('Could not get spool progress: {}'.format(ERROR_DICT[error_code]))
            return
        return index.value

# ----------------------------------------------------------------------------------------------------------------------
# Unused methods from original version of Qudi. Keep for compatibility.
# ----------------------------------------------------------------------------------------------------------------------

    # not sure if the distinguishing between gain setting and gain value will be problematic for
    # this camera model. Just keeping it in mind for now.
    # Not really funcitonal right now.
    #    def set_gain(self, gain):
    #        """ Set the gain
    #
    #        @param float gain: desired new gain
    #
    #        @return float: new exposure gain
    #        """
    #        n_pre_amps = self._get_number_preamp_gains()
    #        msg = ''
    #        if (gain >= 0) & (gain < n_pre_amps):
    #            msg = self._set_preamp_gain(gain)
    #        else:
    #            self.log.warning('Choose gain value between 0 and {0}'.format(n_pre_amps-1))
    #        if msg == 'DRV_SUCCESS':
    #            self._gain = gain
    #        else:
    #            self.log.warning('The gain wasn\'t set. {0}'.format(msg))
    #        return self._gain
    #
    #    def get_gain(self):
    #        """ Get the gain
    #
    #        @return float: exposure gain
    #        """
    #        _, self._gain = self._get_preamp_gain()
    #        return self._gain

    # camera as photon counting device
    # soon to be interface functions for using
    # a camera as a part of a (slow) photon counter
    #     def set_up_counter(self):
    #         check_val = 0
    #         if self._shutter == 'closed':
    #             msg = self._set_shutter(0, 1, 0.1, 0.1)
    #             if msg == 'DRV_SUCCESS':
    #                 self._shutter = 'open'
    #             else:
    #                 self.log.error('Problems with the shutter.')
    #                 check_val = -1
    #         ret_val1 = self._set_trigger_mode('EXTERNAL')
    #         ret_val2 = self._set_acquisition_mode('RUN_TILL_ABORT')
    #         # let's test the FT mode
    #         # ret_val3 = self._set_frame_transfer(True)
    #         error_code = self.dll.PrepareAcquisition()
    #         error_msg = ERROR_DICT[error_code]
    #         if error_msg == 'DRV_SUCCESS':
    #             self.log.debug('prepared acquisition')
    #         else:
    #             self.log.debug('could not prepare acquisition: {0}'.format(error_msg))
    #         self._get_acquisition_timings()
    #         if check_val == 0:
    #             check_val = ret_val1 | ret_val2
    #
    #         if msg != 'DRV_SUCCESS':
    #             ret_val3 = -1
    #         else:
    #             ret_val3 = 0
    #
    #         check_val = ret_val3 | check_val
    #
    #         return check_val
    #
    #     def count_odmr(self, length):
    #         first, last = self._get_number_new_images()
    #         self.log.debug('number new images:{0}'.format((first, last)))
    #         if last - first + 1 < length:
    #             while last - first + 1 < length:
    #                 first, last = self._get_number_new_images()
    #         else:
    #             self.log.debug('acquired too many images:{0}'.format(last - first + 1))
    #
    #         images = []
    #         for i in range(first, last + 1):
    #             img = self._get_images(i, i, 1)
    #             images.append(img)
    #         self.log.debug('expected number of images:{0}'.format(length))
    #         self.log.debug('number of images acquired:{0}'.format(len(images)))
    #         return False, np.array(images).transpose()
    #
    #     def get_down_time(self):
    #         return self._exposure
    #
    #     def get_counter_channels(self):
    #         width, height = self.get_size()
    #         num_px = width * height
    #         return [i for i in map(lambda x: 'px {0}'.format(x), range(num_px))]

    # def _get_images(self, first_img, last_img, n_scans):
    #     """ Return an array of last acquired image.
    #
    #     @return numpy array: image data in format [[row],[row]...]
    #
    #     Each pixel might be a float, integer or sub pixels
    #     """
    #
    #     width = self._width
    #     height = self._height
    #
    #     # first_img, last_img = self._get_number_new_images()
    #     # n_scans = last_img - first_img
    #     dim = width * height * n_scans
    #
    #     dim = int(dim)
    #     image_array = np.zeros(dim)
    #     cimage_array = c_int * dim
    #     cimage = cimage_array()
    #
    #     first_img = c_long(first_img)
    #     last_img = c_long(last_img)
    #     size = c_ulong(width * height)
    #     val_first = c_long()
    #     val_last = c_long()
    #     error_code = self.dll.GetImages(first_img, last_img, pointer(cimage),
    #                                     size, byref(val_first), byref(val_last))
    #     if ERROR_DICT[error_code] != 'DRV_SUCCESS':
    #         self.log.warning('Couldn\'t retrieve an image. {0}'.format(ERROR_DICT[error_code]))
    #     else:
    #         for i in range(len(cimage)):
    #             # could be problematic for 'FVB' or 'SINGLE_TRACK' readmode
    #             image_array[i] = cimage[i]
    #
    #     self._cur_image = image_array
    #     return image_array
