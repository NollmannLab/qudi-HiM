# -*- coding: utf-8 -*-
"""
Qudi-HiM

This file contains the hardware class representing a Hamamatsu Flash camera.
It is based on a Python wrapper for the dll functions of the Hamamatsu Flash camera
found here:
https://github.com/ZhuangLab/storm-control/blob/master/storm_control/sc_hardware/hamamatsu/hamamatsu_camera.py

An extension to Qudi.

@author: F. Barho
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
from .hamamatsu_python_driver import HamamatsuCamera


class HCam(Base, CameraInterface):
    """ Hardware class for Hamamatsu Orca Flash Camera

    Example config for copy-paste:

    hamamatsu_camera:
        module.Class: 'camera.hamamatsu.hamamatsu.HCam'
        camera_id: 0
        default_exposure: 0.01
        default_acquisition_mode: 'run_till_abort'

    """
    # config options
    _default_exposure = ConfigOption('default_exposure', 0.01)  # in seconds
    _default_acquisition_mode = ConfigOption('default_acquisition_mode', 'run_till_abort')
    camera_id = ConfigOption('camera_id', 0)

    # camera attributes
    _width = 0  # current width
    _height = 0  # current height
    _full_width = 0  # maximum width of the sensor
    _full_height = 0  # maximum height of the sensor
    _exposure = _default_exposure
    _gain = 0
    n_frames = 1

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self.camera = None

    def on_activate(self):
        """ Initialisation performed during activation of the module.
        """
        try:
            self.camera = HamamatsuCamera(
                self.camera_id)  # the idea is to use the class HamamatsuCamera like a python wrapper for the dcamapi

            self.get_size()  # update the values _weight, _height
            self._full_width = self._width
            self._full_height = self._height

            # # set some default values
            # self.camera.setACQMode(self._default_acquisition_mode)
            self.set_exposure(self._exposure)
        except Exception:
            self.log.error(f'Hamamatsu camera not connected. Check if device is switched on.')

    def on_deactivate(self):
        """ Deinitialisation performed during deactivation of the module.
        """
        self.camera.stopAcquisition()
        # close the camera
        self.camera.shutdown()
        # maybe add also the deinitialization of the dcamapi

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
        camera_name = self.camera.getModelInfo(self.camera_id)
        return camera_name

    def get_size(self):
        """ Retrieve size of the image in pixel.

        :return: tuple (int, int): Size (width, height)
        """
        self._width = self.camera.getPropertyValue('image_width')[0]
        self._height = self.camera.getPropertyValue('image_height')[0]
        return self._width, self._height

    def set_exposure(self, exposure):
        """ Set the exposure time in seconds.

        :param: float exposure: desired new exposure time

        :return: bool: success ?
        """
        new_exp = self.camera.setPropertyValue('exposure_time',
                                               exposure)  # return value new_exp: float if new exposure set (eventually corrected to be inside the allowed range); False if error
        # update the attribute
        if isinstance(new_exp, float):
            self._exposure = self.camera.getPropertyValue('exposure_time')[0]
            return True
        else:
            return False
        # is this error check sufficient ?

    def get_exposure(self):
        """ Get the exposure time in seconds.

        :return: float exposure time
        """
        self._exposure = self.camera.getPropertyValue('exposure_time')[0]
        return self._exposure

    def set_gain(self, gain):
        """ Set the gain - gain is not available for the hamamatsu camera.

        :param: int gain: desired new gain

        :return: bool: Success ?
        """
        return False

    def get_gain(self):
        """ Get the gain

        :return: int: gain """
        return self._gain

    def get_ready_state(self):
        """ Is the camera ready for an acquisition ?

        :return: bool: ready ?
        """
        return self.camera.get_ready_state()

    def set_image(self, hbin, vbin, hstart, hend, vstart, vend):
        """ Sets a ROI on the sensor surface.

        :param: int hbin: number of pixels to bin horizontally
        :param: int vbin: number of pixels to bin vertically.
        :param: int hstart: Start column
        :param: int hend: End column
        :param: int vstart: Start row
        :param: int vend: End row

        :return: int error code: ok = 0
        """
        try:
            # only multiples of 4 are allowed for hstart, hend, vsize, hsize. Use the lower nearest multiple of 4
            hstart = int(hstart / 4) * 4
            vstart = int(vstart / 4) * 4
            vend = int(vend / 4) * 4
            hend = int(hend / 4) * 4
            vsize = vend - vstart
            hsize = hend - hstart
            self.camera.setPropertyValue('subarray_hpos', hstart)
            self.camera.setPropertyValue('subarray_vpos', vstart)
            self.camera.setPropertyValue('subarray_hsize', hsize)
            self.camera.setPropertyValue('subarray_vsize', vsize)
            self.camera.setSubArrayMode()
            self.log.info(f'Set subarray: {vsize} x {hsize} pixels (rows x cols)')  # for tests
            return 0
        except Exception:
            return -1

    def get_progress(self):
        """ Retrieves the total number of acquired images during a movie acquisition.

        :return: int progress: total number of acquired images.
        """
        return self.camera.check_frame_number()

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
        return False

    def has_shutter(self):
        """ Is the camera equipped with a mechanical shutter?

        If this function returns true, the attribute _shutter must also be defined in the hardware module

        :return: bool: has shutter ?
        """
        return False

# ----------------------------------------------------------------------------------------------------------------------
# Methods to handle camera acquisitions
# ----------------------------------------------------------------------------------------------------------------------

# Methods for displaying images on the GUI -----------------------------------------------------------------------------
    def start_single_acquisition(self):
        """ Start a single acquisition.

        :return: bool: Success ?
        """
        try:
            self.camera.setACQMode('fixed_length', 1)
            self.camera.startAcquisition()
            return True
        except Exception:
            return False

    def start_live_acquisition(self):
        """ Start a continuous acquisition.

        :return: bool: Success ?
        """
        try:
            self.camera.setACQMode('run_till_abort')
            self.camera.startAcquisition()
            return True
        except Exception:
            return False

    def stop_acquisition(self):
        """ Stop/abort live or single acquisition

        :return: bool: Success ?
        """
        try:
            self.camera.stopAcquisition()
            return True
        except Exception:
            return False

# Methods for saving image data ----------------------------------------------------------------------------------------
    def start_movie_acquisition(self, n_frames):
        """ Set the conditions to save a movie and start the acquisition (fixed length mode).

        :param: int n_frames: number of frames

        :return: bool: Success ?
        """
        self.n_frames = n_frames  # needed to choose the correct case in get_acquired_data method
        try:
            self.camera.setACQMode('fixed_length', n_frames)
            self.camera.startAcquisition()
            return True
        except Exception:
            return False

    def finish_movie_acquisition(self):
        """ Reset the conditions used to save a movie to default.

        :return: bool: Success ?
        """
        try:
            self.camera.stopAcquisition()
            self.n_frames = 1  # reset to default
            return True
        except Exception:
            return False

    def wait_until_finished(self):
        """ Wait until an acquisition is finished.

        :return: None
        """
        pass

# Methods for acquiring image data using synchronization between lightsource and camera---------------------------------
    def prepare_camera_for_multichannel_imaging(self, frames, exposure, gain, save_path, file_format):
        """ Set the camera state for an experiment using synchronization between lightsources and the camera.
        Using typically an external trigger.

        :param: int frames: number of frames in a kinetic series / fixed length mode
        :param: float exposure: exposure time in seconds

        The following parameters are not needed for this camera. Only for compatibility with abstract function signature
        :param: int gain: gain setting
        :param: str save_path: complete path (without fileformat suffix) where the image data will be saved
        :param: str file_format: selected fileformat such as 'tiff', 'fits', ..

        :return: None
        """
        self.stop_acquisition()
        self.set_exposure(exposure)
        self._set_acquisition_mode('fixed_length', frames)
        self.n_frames = frames  # this ensures that the data retrieval format is correct
        # external trigger mode, positive polarity
        self._set_trigger_source('EXTERNAL')
        self._set_trigger_polarity('POSITIVE')
        # output trigger: trigger ready and global exposure
        self._configure_output_trigger(1, 'TRIGGER READY', 'NEGATIVE')
        self._configure_output_trigger(2, 'EXPOSURE', 'NEGATIVE')
        # self._start_acquisition()

    def reset_camera_after_multichannel_imaging(self):
        """ Reset the camera to a default state after an experiment using synchronization between lightsources and
         the camera.

         :return: None
         """
        self.stop_acquisition()
        self._set_trigger_source('INTERNAL')
        self.n_frames = 1  # reset to default
        self._set_acquisition_mode('run_till_abort')

# ----------------------------------------------------------------------------------------------------------------------
# Methods for image data retrieval
# ----------------------------------------------------------------------------------------------------------------------

    def get_most_recent_image(self):
        """ Return an array of last acquired image. Used mainly for live display on gui during video saving.

        :return: numpy array: image data in format [[row],[row]...]

        Each pixel might be a float, integer or sub pixels
        """
        [frame, dim] = self.camera.getMostRecentFrame()  # frame is HCamData object, dim is a list [image_width, image_height]
        image_array = np.zeros(dim[0] * dim[1])
        data = frame.getData()
        image_array = np.reshape(data, (dim[1], dim[0]))
        return image_array

    def get_acquired_data(self):
        """ Return an array of the acquired data.
        Depending on the acquisition mode, this can be just one frame (single scan, run_till_abort)
        or the entire data as a 3D stack (fixed length)

        :return: numpy ndarray: image data in format [[row],[row]...]

        Each pixel might be a float, integer or sub pixels
        """
        # bug fixes are used here to wait until data is available. A more elegant solution would be to modify the hamamatsu_python_driver file
        # so that getFrames method blocks waiting until at least one frame is available. (which is supposed to be the case according to comments therein).
        # for fixed length and n = 1, the counter may go up to its maximum if the exposure time is long (such as 1 s)
        # if even longer exposure times are needed, the counter or the waiting time must be increased.
        acq_mode = self.get_acquisition_mode()

        image_array = []  # or should this be initialized as an np array ??
        [frames,
         dim] = self.camera.getFrames()  # frames is a list of HCamData objects, dim is a list [image_width, image_height]

        if acq_mode == 'run_till_abort':
            # bug fix trial
            if not frames:  # check if list is empty
                print('no frames available')
                image_array = np.zeros((dim[1], dim[0]))
            else:
                data = frames[-1].getData()  # for run_till_abort acquisition: get the last (= most recent) frame
                image_array = np.reshape(data, (dim[1], dim[
                    0]))  # reshape in row major shape (height, width) # to check if image is reconstituted correctly
        elif acq_mode == 'fixed_length' and self.n_frames == 1:  # equivalent to single_scan
            # bug fix for snap functionality: data retrieval is sometimes invoked too fast and data is not yet ready
            counter = 0
            while not frames and counter < 10:  # check if frames list is empty; 10 tries to get the data
                [frames, dim] = self.camera.getFrames()  # try again to get the data
                counter += 1
                sleep(0.005)
            if not frames:  # as last option
                data = np.zeros((dim[1], dim[0]))
                print('no data available from camera')
            else:  # else continue normally
                data = frames[-1].getData()
            print(counter)  # for debugging, comment out later
            image_array = np.reshape(data, (dim[1], dim[0]))
            # this case is covered separately to guarantee the correct display for snap
            # code could be combined with case 1 above (conditions listed with 'or')
        elif acq_mode == 'fixed_length' and self.n_frames > 1:
            frames_list = [np.reshape(frames[i].getData(), (dim[1], dim[0])) for i in range(len(frames))]  # retrieve the data, reshape it and create a list of the frames
            image_array = np.stack(frames_list)
        else:
            self.log.info('Your aquisition mode is not covered yet.')
        return image_array

# ======================================================================================================================
# Non-Interface functions
# ======================================================================================================================

# ----------------------------------------------------------------------------------------------------------------------
# Non-interface functions to handle acquisitions
# ----------------------------------------------------------------------------------------------------------------------

    def get_acquisition_mode(self):
        acq_mode = self.camera.acquisition_mode
        return acq_mode

    def _set_acquisition_mode(self, mode, n_frames=None):
        self.camera.setACQMode(mode, n_frames)
        # add error handling etc.

    def _start_acquisition(self):
        self.camera.startAcquisition()

# ----------------------------------------------------------------------------------------------------------------------
# Trigger
# ----------------------------------------------------------------------------------------------------------------------

    def _set_trigger_source(self, source):
        """
        Set the trigger source.
        @param string source: string corresponding to certain TriggerMode 'INTERNAL', 'EXTERNAL', 'SOFTWARE', 'MASTER PULSE'
        @return int check_val: ok: 0, not ok: -1
        """
        # the supported trigger sources can be found as follows:
        # self.camera.getPropertyText('trigger_source') returns {'INTERNAL': 1, 'EXTERNAL': 2, 'SOFTWARE': 3, 'MASTER PULSE': 4}
        check_val = self.camera.setPropertyValue('trigger_source', source)
        if isinstance(check_val, float):
            return 0
        else:
            return -1

    def _get_trigger_source(self):
        trigger_source = self.camera.getPropertyValue('trigger_source')  # returns a list [value, type] such as [1, 'MODE']
        return trigger_source[0]  # would be a good idea to map the number to the description

    def _set_trigger_polarity(self, polarity):
        """ Set the trigger polarity (default is negative)
        @param: str polarity: 'NEGATIVE', 'POSITIVE'
        @return int check_val: ok: 0, not ok: -1
        """
        check_val = self.camera.setPropertyValue('trigger_polarity', polarity)  # returns a float corresponding to the polarity (1.0: negative, 2.0: positive) or bool False if not set
        if isinstance(check_val, float):
            return 0
        else:
            return -1

    def _get_trigger_polarity(self):
        trigger_polarity = self.camera_getPropertyValue('trigger_polarity')
        return trigger_polarity[0]

    def _configure_output_trigger(self, channel, output_trigger_kind, output_trigger_polarity):
        """
        Configure the output trigger for the specified output channel
        @param: int channel: index ranging up to the number of output trigger connectors - 1
        @param: str output_trigger_kind: supported values 'LOW', 'EXPOSURE', 'PROGRAMABLE', 'TRIGGER READY', 'HIGH'
        @param: str output_trigger_polarity: supported values 'NEGATIVE', 'POSITIVE'
        """
        trigger_kind = self.camera.setPropertyValue(f'output_trigger_kind[{channel}]', output_trigger_kind)
        print(trigger_kind)
        trigger_polarity = self.camera.setPropertyValue(f'output_trigger_polarity[{channel}]', output_trigger_polarity)
        print(trigger_polarity)
