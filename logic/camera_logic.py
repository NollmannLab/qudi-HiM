# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains the logic to control a microscope camera.

An extension to Qudi.

@author: F.Barho & JB.Fiche for later modifications
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
import time
import h5py
import numpy as np
import os
# import yaml

from time import sleep
from tifffile import TiffWriter
from astropy.io import fits
from core.connector import Connector
from core.configoption import ConfigOption
from logic.generic_logic import GenericLogic
from qtpy import QtCore
from ome_types.model import OME, Image, Pixels, Channel, Plane
from ruamel.yaml import YAML

verbose = True


# ======================================================================================================================
# Decorator (for debugging)
# ======================================================================================================================
def decorator_print_function(function):
    global verbose

    def new_function(*args, **kwargs):
        if verbose:
            print(f'*** DEBUGGING *** Executing {function.__name__}')
        return function(*args, **kwargs)
    return new_function

# ======================================================================================================================
# Worker class for camera live display
# ======================================================================================================================


class WorkerSignals(QtCore.QObject):
    """ Defines the signals available from a running worker thread """
    sigFinished = QtCore.Signal()
    sigStepFinished = QtCore.Signal(str, str, str, int, bool, dict, bool, bool)
    sigSpoolingStepFinished = QtCore.Signal(str, str, str, bool, dict)


class LiveImageWorker(QtCore.QRunnable):
    """ Worker thread to update the live image at the desired frame rate

    The worker handles only the waiting time, and emits a signal that serves to trigger the update indicators
    """
    def __init__(self, time_constant):
        super(LiveImageWorker, self).__init__()
        self.signals = WorkerSignals()
        self.time_constant = time_constant

    @QtCore.Slot()
    def run(self):
        """ """
        sleep(self.time_constant)
        self.signals.sigFinished.emit()


class SaveProgressWorker(QtCore.QRunnable):
    """ Worker thread to update the progress during video saving and eventually handle the image display.

    The worker handles only the waiting time, and emits a signal that serves to trigger the update indicators """
    def __init__(self, time_constant, filenamestem, filename, fileformat, n_frames, is_display, metadata, addfile,
                 emit_signal):
        super(SaveProgressWorker, self).__init__()
        self.signals = WorkerSignals()
        self.time_constant = time_constant
        # the following attributes need to be transmitted by the worker to the finish_save_video method
        self.filenamestem = filenamestem
        self.filename = filename
        self.fileformat = fileformat
        self.n_frames = n_frames
        self.is_display = is_display
        self.metadata = metadata
        self.addfile = addfile
        self.emit_signal = emit_signal

    @QtCore.Slot()
    def run(self):
        """ """
        sleep(self.time_constant)
        self.signals.sigStepFinished.emit(self.filenamestem, self.filename, self.fileformat, self.n_frames,
                                          self.is_display, self.metadata, self.addfile, self.emit_signal)


class SpoolProgressWorker(QtCore.QRunnable):
    """ Worker thread to update the progress during spooling and eventually handle the image display.

    The worker handles only the waiting time, and emits a signal that serves to trigger the update indicators. """

    def __init__(self, time_constant, filenamestem, path, fileformat, is_display, metadata):
        super(SpoolProgressWorker, self).__init__()
        self.signals = WorkerSignals()
        self.time_constant = time_constant
        # the following attributes need to be transmitted by the worker to the finish_spooling method
        self.filenamestem = filenamestem
        self.path = path
        self.fileformat = fileformat
        self.is_display = is_display
        self.metadata = metadata

    @QtCore.Slot()
    def run(self):
        """ """
        sleep(self.time_constant)
        self.signals.sigSpoolingStepFinished.emit(self.filenamestem, self.path, self.fileformat, self.is_display,
                                                  self.metadata)


# ======================================================================================================================
# Logic class
# ======================================================================================================================
class CameraLogic(GenericLogic):
    """
    Class containing the logic to control a microscope camera.

    Example config for copy-paste:

    camera_logic:
        module.Class: 'camera_logic2.CameraLogic'
        default_exposure: 20
        connect:
            hardware: 'andor_ultra_camera'
    """
    # declare connectors
    hardware = Connector(interface='CameraInterface')
    shutter = Connector(interface='ShutterInterface', optional=True)

    # declare available file formats
    fileformat_list = ConfigOption('fileformat_list', missing='error')

    # config options
    _max_fps = ConfigOption('default_exposure', 20)

    # signals
    sigUpdateDisplay = QtCore.Signal()
    sigAcquisitionFinished = QtCore.Signal()
    sigVideoFinished = QtCore.Signal()
    sigVideoSavingFinished = QtCore.Signal()
    sigSpoolingFinished = QtCore.Signal()
    sigExposureChanged = QtCore.Signal(float)
    sigGainChanged = QtCore.Signal(float)
    sigTemperatureChanged = QtCore.Signal(float)
    sigProgress = QtCore.Signal(int)  # sends the number of already acquired images
    sigSaving = QtCore.Signal()
    sigCleanStatusbar = QtCore.Signal()
    sigUpdateCamStatus = QtCore.Signal(str, str, str, str)
    sigLiveStarted = QtCore.Signal()  # informs the GUI that live mode was started programmatically
    sigLiveStopped = QtCore.Signal()  # informs the GUI that live mode was stopped programmatically
    sigDisableCameraActions = QtCore.Signal()
    sigEnableCameraActions = QtCore.Signal()
    sigDisableFrameTransfer = QtCore.Signal()

    # attributes
    cam_type = None  # indicated the type of camera used
    live_enabled = False  # indicates if the camera is currently in live mode
    saving = False  # indicates if the camera is currently saving a movie
    restart_live = False
    frame_transfer = False  # indicates whether the frame transfer mode is activated
    acquisition_aborted = False

    has_temp = False
    has_shutter = False
    _fps = 20
    _exposure = 1.
    _gain = 1.
    _temperature = 0  # use any value. It will be overwritten during on_activate if sensor temperature is available
    temperature_setpoint = _temperature
    _last_image = None
    _kinetic_time = None
    _max_frames_movie = None
    _max_frames_spool = None

    _hardware = None
    _security_shutter = None

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self.threadpool = QtCore.QThreadPool()

    def on_activate(self):
        """ Initialisation performed during activation of the module.
        """
        self._hardware = self.hardware()
        self._security_shutter = self.shutter()

        # indicate the type of camera used
        self.cam_type = self._hardware.__class__.__name__

        self.live_enabled = False
        self.saving = False
        self.restart_live = False
        self.has_temp = self._hardware.has_temp()
        if self.has_temp and (self.cam_type != "KinetixCam"):
            self.temperature_setpoint = self._hardware._default_temperature
        self.has_shutter = self._hardware.has_shutter()

        # update the private variables _exposure, _gain, _temperature
        self.get_exposure()
        self.get_gain()
        self.get_temperature()

        # inquire the maximum number of images to acquire for movies acquisition
        self._max_frames_movie, self._max_frames_spool = self._hardware.get_max_frames()

    def on_deactivate(self):
        """ Perform required deactivation. """
        pass

# ----------------------------------------------------------------------------------------------------------------------
# (Low-level) methods making the camera interface functions accessible from the GUI.
# Getter and setter methods for camera attributes.
# ----------------------------------------------------------------------------------------------------------------------

    def get_name(self):
        """ Retrieve an identifier of the camera that the GUI can print.
        @return: (string) name for the camera
        """
        return self._hardware.get_name()

    def get_size(self):
        """ Retrieve size of the image in pixel.

        :return: tuple (int, int): Size (width, height)
        """
        return self._hardware.get_size()

    def get_max_size(self):
        """ Retrieve maximum size of the sensor in pixel.

        :return tuple (int, int): Size (width, height)
        """
        return self._hardware._full_width, self._hardware._full_height

    def set_exposure(self, time):
        """ Set the exposure time of the camera. Inform the GUI that a new value was set.

        @param: time (float): desired new exposure time in seconds
        @return: None
        """
        self._hardware.set_exposure(time)
        exp = self.get_exposure()  # updates also the attribute self._exposure and self._fps
        self.sigExposureChanged.emit(exp)

    def get_exposure(self):
        """ Get the exposure time of the camera and update the class attributes _exposure and _fps.
        @return: (float) exposure time (in seconds)
        """
        self._exposure = self._hardware.get_exposure()
        self._fps = min(1 / self._exposure, self._max_fps)
        return self._exposure

    # this function is specific to andor camera
    def get_kinetic_time(self):
        """ Andor camera only: Get the kinetic time of the camera and update the class attribute _kinetic_time.
        @return: (float) kinetic time (in seconds)
        """
        if (self.get_name() == 'iXon Ultra 897') or (self.get_name() == 'iXon Ultra 888'):
            self._kinetic_time = self._hardware.get_kinetic_time()
            return self._kinetic_time
        else:
            return

    def set_gain(self, gain):
        """ Set the gain of the camera. Inform the GUI that a new gain value was set.
        @param: (int) gain: desired new gain.
        """
        self._hardware.set_gain(gain)
        gain_value = self.get_gain()  # called to update the attribute self._gain
        self.sigGainChanged.emit(gain_value)

    def get_gain(self):
        """ Get the gain setting of the camera and update the class attribute _gain.
        @return: (int) gain: current gain setting.
        """
        gain = self._hardware.get_gain()
        self._gain = gain
        return gain

    def get_gain_range(self):
        """ Get the limits for the gain.
        @return: (int) low and high limits
        """
        low, high = self._hardware.get_gain_limits()
        return low, high

    def get_progress(self):
        """ Retrieves the total number of acquired images by the camera (during a movie acquisition).
        @return: (int) progress: total number of acquired images.
        """
        return self._hardware.get_progress()

    def set_temperature(self, temperature):
        """
        Set temperature of the camera, if accessible.
        @param: int temperature: desired new temperature setpoint
        """
        if (not self.has_temp) or (self.cam_type != "IxonUltra"):
            pass
        else:
            # make sure the cooler is on
            if self._hardware.is_cooler_on() == 0:
                self._hardware._set_cooler(True)

            self.temperature_setpoint = temperature  # store the new setpoint to compare against actual temperature
            self._hardware._set_temperature(temperature)

    def get_temperature(self):
        """
        Get temperature of the camera, if accessible, and update the class attribute _temperature.
        @return: int temperature: current sensor temperature
        """
        if not self.has_temp:
            self.log.warn('Sensor temperature control not available')
        else:
            if self.live_enabled:  # live mode on
                self.interrupt_live()
                
            temp = self._hardware.get_temperature()
            self._temperature = temp
            
            if self.live_enabled:  # restart live mode
                self.resume_live()
            return temp

    def get_max_frames(self):
        """ Return the maximum number of frames that can be handled by the camera for a single movie acquisition. Two
        values are returned, depending on which methods is used for the acquisition (video or spooling if it exists)
        @return:
            max frames video mode (int)
            max frames spool mode (int)
        """
        return self._max_frames_movie, self._max_frames_spool

    def get_non_interfaced_parameters(self):
        """ Return the values of all the non-interfaced parameters of the camera
        """
        return self._hardware.get_non_interfaced_parameters()

# ----------------------------------------------------------------------------------------------------------------------
# Methods to access camera state
# ----------------------------------------------------------------------------------------------------------------------

    def get_ready_state(self):
        """ Is the camera ready for an acquisition ?

        @return: ready ? (str) 'True', 'False'
        """
        return str(self._hardware.get_ready_state())

    def get_shutter_state(self):
        """ Retrieves the status of the shutter if there is one.

        :returns str: shutter status: 'open', 'closed' """
        if not self.has_shutter:
            return
        else:
            return self._hardware._shutter

    def get_cooler_state(self):
        """
        Retrieves the status of the cooler if there is one (only if "has_temp" is True).
        @returns str: cooler on, cooler off """
        if not self.has_temp:
            return
        else:
            cooler_status = self._hardware.is_cooler_on()
            idle = self._hardware.get_ready_state()
            # first check if camera is recording
            if not idle:
                return 'NA'
            else:   # _hardware.is_cooler_on only returns an adapted value when camera is idle
                if cooler_status == 0:
                    return 'Off'
                if cooler_status == 1:
                    return 'On'

    def update_camera_status(self):
        """ Retrieves an ensemble of camera status values:
        ready: if camera is idle, shutter: open / closed if available, cooler: on / off if available, temperature value.
        Emits a signal containing the 4 retrieved status informations as str.

        :return: None
        """
        ready_state = self.get_ready_state()
        shutter_state = self.get_shutter_state()
        cooler_state = self.get_cooler_state()
        temperature = str(self.get_temperature())
        self.sigUpdateCamStatus.emit(ready_state, shutter_state, cooler_state, temperature)

# ----------------------------------------------------------------------------------------------------------------------
# Methods to set advanced configurations of the camera
# ----------------------------------------------------------------------------------------------------------------------

    def set_sensor_region(self, hbin, vbin, hstart, hend, vstart, vend):
        """ Defines a limited region on the sensor surface, hence accelerating the acquisition.

        @param int hbin: number of pixels to bin horizontally
        @param int vbin: number of pixels to bin vertically.
        @param int hstart: Start column (inclusive)
        @param int hend: End column (inclusive)
        @param int vstart: Start row (inclusive)
        @param int vend: End row (inclusive)
        """
        if self.live_enabled:  # live mode is on
            self.interrupt_live()  # interrupt live to allow access to camera settings

        err = self._hardware.set_image(hbin, vbin, hstart, hend, vstart, vend)
        if err < 0:
            self.log.warn('Sensor region not set')
        else:
            self.log.info('Sensor region set to {} x {}'.format(vend - vstart + 1, hend - hstart + 1))

        if self.live_enabled:
            self.resume_live()  # restart live in case it was activated

    def reset_sensor_region(self):
        """ Reset to full sensor size. """

        if self.live_enabled:  # live mode is on
            self.interrupt_live()

        width = self._hardware._full_width
        height = self._hardware._full_height

        err = self._hardware.set_image(1, 1, 1, width, 1, height)
        if err < 0:
            self.log.warn('Sensor region not reset to default')
        else:
            self.log.info('Sensor region reset to default: {} x {}'.format(height, width))

        if self.live_enabled:
            self.resume_live()

    @QtCore.Slot(bool)
    def set_frametransfer(self, activate):
        """ Activate frametransfer mode for ixon ultra camera: the boolean activate is stored in a variable in the
        camera module. When an acquisition is started, frame transfer is set accordingly.

        :params: bool activate ?

        :return: None
        """
        if self.get_name() == 'iXon Ultra 897':
            if self.live_enabled:  # if live mode is on, interrupt to be able to access frame transfer setting
                self.interrupt_live()
            self._hardware._set_frame_transfer(int(activate))
            if self.live_enabled:  # if live mode was interrupted, restart it
                self.resume_live()
            self.log.info(f'Frametransfer mode activated: {activate}')
            self.frame_transfer = bool(activate)
            # we also need to update the indicator on the gui
            exp = self.get_exposure()  # we just need to send the signal sigExposureChanged, but it must carry a float
            # so we send exp as argument
            self.sigExposureChanged.emit(exp)
        # do nothing in case of cameras that do not support frame transfer
        else:
            pass

    def disable_frame_transfer(self):
        """ For specific tasks, the frame transfer mode should be disabled."""
        self.sigDisableFrameTransfer.emit()

# ----------------------------------------------------------------------------------------------------------------------
# Methods to handle camera acquisition and snap / live display
# ----------------------------------------------------------------------------------------------------------------------

# Method invoked by snap button on GUI ---------------------------------------------------------------------------------
    def start_single_acquisition(self):
        """ Take a single camera image.
        """
        # For the RAMM microscope, a shutter is used to block the IR laser
        if self._security_shutter is not None:
            self._security_shutter.camera_security(acquiring=True)

        # Depending on the type of camera, image retrieval will be different
        if self.cam_type == "KinetixCam":
            self._last_image = self._hardware.start_single_acquisition()
        else:
            self._hardware.start_single_acquisition()
            self._last_image = self._hardware.get_acquired_data()

        # Send signal to GUi for image display
        self.sigUpdateDisplay.emit()
        self._hardware.stop_acquisition()  # this in needed to reset the acquisition mode to default
        self.sigAcquisitionFinished.emit()

# Methods invoked by live button on GUI --------------------------------------------------------------------------------
    def start_loop(self):
        """ Start the live display mode.
        """
        self.live_enabled = True
        if self._security_shutter is not None:
            self._security_shutter.camera_security(acquiring=True)

        worker = LiveImageWorker(1 / self._fps)
        worker.signals.sigFinished.connect(self.loop)
        self.threadpool.start(worker)

        if self._hardware.support_live_acquisition():
            self._hardware.start_live_acquisition()
        else:
            self._hardware.start_single_acquisition()

    def loop(self):
        """ Execute one step in the live display loop.
        """
        if self.live_enabled:
            if self.cam_type == "KinetixCam":
                self._last_image, _ = self._hardware.get_most_recent_image(copy=False)
            else:
                self._last_image = self._hardware.get_acquired_data()
            self.sigUpdateDisplay.emit()

            worker = LiveImageWorker(1 / self._fps)
            worker.signals.sigFinished.connect(self.loop)
            self.threadpool.start(worker)

            # In case live mode does not exist, launch a new snap acquisition
            if not self._hardware.support_live_acquisition():
                self._hardware.start_single_acquisition()  # the hardware has to check it's not busy

    def stop_loop(self):
        """ Stop the live display loop.
        """
        self.live_enabled = False

        # in the case of the Kinetix camera, no copy of the images is performed during live acquisition (to avoid
        # lagging). However, a copy is performed before stopping the camera and removing all the images from the buffer.
        # This copy is required for the GUI's display.
        if self.cam_type == "KinetixCam":
            self._last_image, _ = self._hardware.get_most_recent_image(copy=True)

        # stop acquisition
        self._hardware.stop_acquisition()
        if self._security_shutter is not None:
            self._security_shutter.camera_security(acquiring=False)

        # self.sigVideoFinished.emit()

# Helper methods to interrupt/restart the camera live mode to give access to camera settings etc. ----------------------

    def interrupt_live(self):
        """ Interrupt the live display loop, for example to update camera settings. """
        self._hardware.stop_acquisition()
        # note that enabled attribute is not modified, to resume the state of the live display

    def resume_live(self):
        """ Restart the live display loop """
        self._hardware.start_live_acquisition()

# Method invoked by save last image button on GUI ----------------------------------------------------------------------
    def save_last_image(self, path, metadata, fileformat='.tif'):
        """
        saves a single image to disk
        @param: str path: path stem, such as '/home/barho/images/2020-12-16/samplename'
        @param: dict metadata: dictionary containing the metadata
        @param: str fileformat: default '.tif' but can be modified if needed.
        """
        if self._last_image is None:
            self.log.warning('No image available to save')
        else:
            image_data = self._last_image

            complete_path = self.create_generic_filename(path, '_Image', 'image', fileformat, addfile=False)
            self.save_to_tiff(1, complete_path, image_data)
            self.save_metadata_txt_file(path, '_Image', metadata)

# Methods invoked by start video button on GUI--------------------------------------------------------------------------
    def start_save_video(self, filenamestem, filename, fileformat, n_frames, is_display, metadata, addfile=False,
                         emit_signal=True):
        """ Starts saving n_frames to disk as a stack (tiff of fits formats supported)

        @param: (str) filenamestem, such as /home/barho/images/2020-12-16/samplename
        @param: (str) filename, such as movie_00
        @param: (str) fileformat (including the dot, such as '.tif', '.fits')
        @param: (int) n_frames: number of frames to be saved
        @param: (bool) is_display: show images on live display on gui
        @param: (dict) metadata: meta information to be saved with the image data (in a separate txt file if tiff
                                fileformat, or in the header if fits format)
        @param: (bool) addfile: indicate if the images are saved in a new folder or appended to the last created
        @param: (bool) emit_signal: can be set to False in order to avoid sending the signal for gui interaction,
                for example when function is called from ipython console or in a task
                #leave the default value True when function is called from gui
        """
        # handle live mode variables
        if self.live_enabled:  # live mode is on
            self.restart_live = True  # store the state of live mode in a helper variable in order to restart it after
            # self.live_enabled = False  # live mode will stop then
            self.stop_live_mode()
            status = self._hardware.get_ready_state()
            while not status:
                status = self._hardware.get_ready_state()
                sleep(0.5)
        self.saving = True

        # handle IR laser shutter security
        if self._security_shutter is not None:
            self._security_shutter.camera_security(acquiring=True)

        # start movie acquisition
        err = self._hardware.start_movie_acquisition(n_frames)
        if err:
            self.log.warning('Video acquisition did not start')
            self.finish_save_video(filenamestem, filename, fileformat, n_frames, metadata, addfile, emit_signal=True)
            return

        # wait at least a full exposure time to make sure at least one image was acquired.
        time.sleep(self._exposure * 2)

        # start a worker thread that will monitor the status of the saving
        worker = SaveProgressWorker(1 / self._fps, filenamestem, filename, fileformat, n_frames, is_display, metadata,
                                    addfile, emit_signal)
        worker.signals.sigStepFinished.connect(self.save_video_loop)
        self.threadpool.start(worker)

    def save_video_loop(self, filenamestem, filename, fileformat, n_frames, is_display, metadata, addfile, emit_signal):
        """ This method performs one step in saving procedure until the last image is saved.
        Handles also the update of the live display if activated.

        @param: (str) filenamestem, such as /home/barho/images/2020-12-16/samplename
        @param: (str) filename, such as movie_00
        @param: (str) fileformat (including the dot, such as '.tif', '.fits')
        @param: (int) n_frames: number of frames to be saved
        @param: (bool) is_display: show images on live display on gui
        @param: (dict) metadata: meta information to be saved with the image data (in a separate txt file if tiff
                                fileformat, or in the header if fits format)
        @param: (bool) addfile: indicate if the images are saved in a new folder or appended to the last created
        @param: (bool) emit_signal: can be set to False in order to avoid sending the signal for gui interaction,
                for example when function is called from ipython console or in a task
                #leave the default value True when function is called from gui
        """
        # Check if the camera is still acquiring
        ready = self._hardware.get_ready_state()

        # Handle progress and display - note that for the Kinetix camera, progress & display are handled in the same
        # function.
        if (not ready) and (not self.acquisition_aborted):
            if self.cam_type == "KinetixCam":
                self._last_image, progress = self._hardware.get_most_recent_image()
                self.sigProgress.emit(progress)
                if is_display:
                    self.sigUpdateDisplay.emit()
            else:
                progress = self._hardware.get_progress()
                self.sigProgress.emit(progress)
                if is_display:
                    self._last_image = self._hardware.get_most_recent_image()
                    self.sigUpdateDisplay.emit()

            # restart a worker if acquisition still ongoing
            worker = SaveProgressWorker(1 / self._fps, filenamestem, filename, fileformat, n_frames, is_display,
                                        metadata, addfile, emit_signal)
            worker.signals.sigStepFinished.connect(self.save_video_loop)
            self.threadpool.start(worker)

        elif self.acquisition_aborted:
            self.abort_save_video()

        # finish the save procedure when hardware is ready
        else:
            self.finish_save_video(filenamestem, filename, fileformat, n_frames, metadata, addfile, emit_signal)

    def abort_save_video(self, emit_signal=True):
        """ This method is used when an acquisition is aborted

        @param: (bool) emit_signal: can be set to False in order to avoid sending the signal for gui interaction,
        for example when function is called from ipython console or in a task
        #leave the default value True when function is called from gui
        """
        self._hardware.abort_movie_acquisition()
        self.acquisition_aborted = False
        self.saving = False

        # if there is a shutter, release the shutter
        if self._security_shutter is not None:
            self._security_shutter.camera_security(acquiring=False)

        # restart live in case it was activated
        if self.restart_live:
            self.restart_live = False  # reset to default value
            self.start_live_mode()
            # self.start_loop()

        if emit_signal:
            self.sigVideoSavingFinished.emit()
        else:  # needed to clean up the info on statusbar when gui is opened without calling video_saving_finished
            self.sigCleanStatusbar.emit()

    def finish_save_video(self, filenamestem, filename, fileformat, n_frames, metadata, addfile, emit_signal=True):
        """ This method finishes the saving procedure. Live mode of the camera is eventually restarted.

        @param: (str) filenamestem, such as /home/barho/images/2020-12-16/samplename
        @param: (str) filename, such as movie_00
        @param: (str) fileformat (including the dot, such as '.tif', '.fits')
        @param: (int) n_frames: number of frames to be saved
        @param: (dict) metadata: meta information to be saved with the image data (in a separate txt file if tiff
                                fileformat, or in the header if fits format)
        @param: (bool) addfile: indicate if the images are saved in a new folder or appended to the last created
        @param: (bool) emit_signal: can be set to False in order to avoid sending the signal for gui interaction,
                for example when function is called from ipython console or in a task
                #leave the default value True when function is called from gui
        """
        self._hardware.wait_until_finished()  # this is important especially if display is disabled
        self.sigSaving.emit()  # for info message on statusbar of GUI

        # get the acquired data before resetting the acquisition mode of the camera
        image_data = self._hardware.get_acquired_data()

        # reset the attributes and the default acquisition mode
        self._hardware.finish_movie_acquisition()
        if self._security_shutter is not None:
            self._security_shutter.camera_security(acquiring=False)
        self.saving = False

        # restart live in case it was activated
        if self.restart_live:
            self.restart_live = False  # reset to default value
            self.start_live_mode()
            # self.start_loop()

        # data handling
        if image_data is not None:
            complete_path = self.create_generic_filename(filenamestem, '_Movie', filename, fileformat, addfile=addfile)
            if fileformat == '.tif':
                self.save_to_tiff(n_frames, complete_path, image_data)
                self.save_metadata_txt_file(filenamestem, '_Movie', metadata)
            elif fileformat == '.fits':
                fits_metadata = self.convert_to_fits_metadata(metadata)
                self.save_to_fits(complete_path, image_data, fits_metadata)
            elif fileformat == '.npy':
                self.save_to_npy(complete_path, image_data)
                self.save_metadata_txt_file(filenamestem, '_Movie', metadata)
            elif fileformat == '.hdf5':
                hdf5_metadata = {'exposure': self._exposure, 'n_channels': 1}
                self.save_to_hdf5(complete_path, image_data, hdf5_metadata)
            elif fileformat == '.ome-tif':
                self.save_to_ome_tif(complete_path, image_data, metadata)
            else:
                self.log.error(f'Your fileformat {fileformat} is currently not covered')

        if emit_signal:
            self.sigVideoSavingFinished.emit()
        else:  # needed to clean up the info on statusbar when gui is opened without calling video_saving_finished
            self.sigCleanStatusbar.emit()

    # methods specific for andor ixon ultra camera for video saving ----------------------------------------------------
    def start_spooling(self, filenamestem, filename, fileformat, n_frames, is_display, metadata, addfile=False):
        """ Starts saving n_frames to disk as a tiff stack without need of data handling within this function.
        Available for andor camera. Useful for large data sets which would be overwritten in the buffer.
        @param: (str) filenamestem, such as '/home/barho/images/2020-12-16/samplename'
        @param: (str) fileformat: including the dot, such as '.tif', '.fits'
        @param: (int) n_frames: number of frames to be saved
        @param: (bool) is_display: show images on live display on gui
        @param: (dict) metadata: meta information to be saved with the image data (in a separate txt file if tiff
                fileformat, or in the header if fits format)
        @param: (bool) addfile: indicate if the images are saved in a new folder or appended to the last created
        """
        if self.live_enabled:  # live mode is on
            # store the state of live mode in a helper variable
            self.restart_live = True
            self.live_enabled = False  # live mode will stop then
            self._hardware.stop_acquisition()

        self.saving = True
        if self._security_shutter is not None:
            self._security_shutter.camera_security(acquiring=True)
        path = self.create_generic_filename(filenamestem, '_Movie', filename, '', addfile=addfile)
        # Depending on the selected format, set the correct spool method
        if fileformat == '.tif':
            method = 7
        elif fileformat == '.fits':
            method = 5
        else:
            self.log.info(f'Your fileformat {fileformat} is currently not covered for spool conditions')
            return
        err_spool = self._hardware.set_spool(1, method, path, 10)

        # Start acquisition
        err_acq = self._hardware.start_movie_acquisition(n_frames)  # setting kinetics acquisition mode, make sure
        if err_spool or err_acq:
            self.log.warning('Spooling did not start')

        # start a worker thread that will monitor the status of the saving
        worker = SpoolProgressWorker(1 / self._fps, filenamestem, path, fileformat, is_display, metadata)
        worker.signals.sigSpoolingStepFinished.connect(self.spooling_loop)
        self.threadpool.start(worker)

    def spooling_loop(self, filenamestem, path, fileformat, is_display, metadata):
        """ This method performs one step in spooling procedure.
        Handles also the update of the live display if activated.
        NB : most of the parameters are only needed to hand them over to finish_spooling method.
        @param: (str) filenamestem, such as '/home/barho/images/2020-12-16/samplename'
        @param: (str) path: generic filepath created in start_spooling using the filenamestem
        @param: (str) fileformat: including the dot, such as '.tif', '.fits'
        @param: (bool) is_display: show images on live display on gui - True, False
        @param: (dict) metadata: meta information to be saved with the image data (in a separate txt file if tiff
                fileformat, or in the header if fits format)
        """
        ready = self._hardware.get_ready_state()

        if (not ready) and (not self.acquisition_aborted):
            spoolprogress = self._hardware.get_progress()
            self.sigProgress.emit(spoolprogress)

            if is_display:
                self._last_image = self._hardware.get_most_recent_image()
                self.sigUpdateDisplay.emit()

            # restart a worker if acquisition still ongoing
            worker = SpoolProgressWorker(1 / self._fps, filenamestem, path, fileformat, is_display, metadata)
            worker.signals.sigSpoolingStepFinished.connect(self.spooling_loop)
            self.threadpool.start(worker)

        elif self.acquisition_aborted:
            self.abort_save_video()

        # finish the save procedure when hardware is ready
        else:
            self.finish_spooling(filenamestem, path, fileformat, metadata)

    def finish_spooling(self, filenamestem, path, fileformat, metadata):
        """ This method finishes the spooling procedure.
        @param: (str) filenamestem, such as '/home/barho/images/2020-12-16/samplename'
        @param: (str) path: generic filepath created in start_spooling using the filenamestem
        @param: (str) fileformat: including the dot, such as '.tif', '.fits'
        @param: (bool) is_display: show images on live display on gui - True, False
        @param: (dict) metadata: meta information to be saved with the image data (in a separate txt file if tiff
                fileformat, or in the header if fits format)
        """
        if fileformat == '.tif':
            method = 7
        elif fileformat == '.fits':
            method = 5
        else:
            pass

        self._hardware.wait_until_finished()
        self._hardware.finish_movie_acquisition()
        self._hardware.set_spool(0, method, path, 10)  # deactivate spooling
        self.log.info(f'Saved data to file {path}{fileformat}')

        # metadata saving
        if fileformat == '.tif':
            self.save_metadata_txt_file(filenamestem, '_Movie', metadata)
        elif fileformat == '.fits':
            try:
                complete_path = path + '.fits'
                fits_metadata = self.convert_to_fits_metadata(metadata)
                self.add_fits_header(complete_path, fits_metadata)
            except Exception as e:
                self.log.warn(f'Metadata not saved: {e}.')
        else:
            pass

        self.saving = False
        if self._security_shutter is not None:
            self._security_shutter.camera_security(acquiring=False)

        # restart live in case it was activated
        if self.restart_live:
            self.restart_live = False  # reset to default value
            self.start_loop()

        # send signal to the GUI to either stop the acquisition or start the following block
        self.sigSpoolingFinished.emit()

# ----------------------------------------------------------------------------------------------------------------------
# Methods for Qudi tasks / experiments requiring synchronization between camera and lightsources
# ----------------------------------------------------------------------------------------------------------------------
    def prepare_camera_for_multichannel_imaging(self, frames, exposure, gain, save_path, file_format):
        """ Method used for camera in external trigger mode, used for tasks with synchonization between
        lightsources and camera. Prepares the camera setting the required parameters. Camera waits for trigger.

        @param: int frames:
        @param: float exposure:
        @param: int gain:
        @param: str save_path:
        @param: str file_format:
        """
        self._hardware.prepare_camera_for_multichannel_imaging(frames, exposure, gain, save_path, file_format)

    def reset_camera_after_multichannel_imaging(self):
        """
        Reset the camera default state at the end of a synchronized acquisition mode.
        """
        self._hardware.reset_camera_after_multichannel_imaging()

    def get_acquired_data(self):   # used in Hi-M Task RAMM
        return self._hardware.get_acquired_data()

    def start_acquisition(self):
        """
        This method is only used for the task, to launch an acquisition without connections to the GUI (no display and
        no possible interactions with the user).
        """
        # close the shutter for IR laser (only for the RAMM setup)
        if self._security_shutter is not None:
            self._security_shutter.camera_security(acquiring=True)

        # launch acquisition
        if self.cam_type == "KinetixCam":
            self._hardware._start_acquisition(mode='Sequence')
        else:
            self._hardware._start_acquisition()

    def stop_acquisition(self):  # used in Hi-M Task RAMM
        self._hardware.stop_acquisition()
        if self._security_shutter is not None:
            self._security_shutter.camera_security(acquiring=False)
        
    def abort_acquisition(self):  # used in multicolor imaging PALM  -> can this be combined with stop_acquisition ?
        self._hardware._abort_acquisition()  # not on camera interface

# ----------------------------------------------------------------------------------------------------------------------
# Filename and data handling
# ----------------------------------------------------------------------------------------------------------------------

    def get_last_image(self):  # is this method needed ??
        """ Return last acquired image.

        :return: np.ndarray self._last_image """
        return self._last_image

    def create_generic_filename(self, filenamestem, folder, file, fileformat, addfile):
        """ This method creates a generic filename using the following format:
        filenamestem/001_folder/file.tif example: /home/barho/images/2020-12-16/samplename/000_Movie/movie.tif

        filenamestem is typically generated by the save settings dialog in basic gui but can also entered manually if
        function is called in the console

        @param: (str) filenamestem  (example /home/barho/images/2020-12-16/samplename)
        @param: (str) folder: specify the type of experiment (ex. Movie, Snap)
        @param: (str) file: filename (ex movie, image). do not specify the fileformat.
        @param: (str) fileformat: specify the type of file (.tif, .txt, ..) including the dot !
        @param: (bool) addfile: if True, the last created folder will again be accessed (needed for metadata saving)
        @return: (str) complete path
        """
        # Check if folder filenamestem exists, if not create it
        if not os.path.exists(filenamestem):
            try:
                os.makedirs(filenamestem)  # recursive creation of all directories on the path
            except Exception as e:
                self.log.error('Error {0}'.format(e))

        # Count the subdirectories in the directory filenamestem (non recursive !) to generate an incremental prefix
        dir_list = [name for name in os.listdir(filenamestem) if os.path.isdir(os.path.join(filenamestem, name))]
        number_dirs = len(dir_list)
        if addfile:
            number_dirs -= 1
        prefix = str(number_dirs).zfill(3)
        folder_name = prefix + folder
        path = os.path.join(filenamestem, folder_name)

        # Create this folder (since addfile is possible, need to check first whether the folder already exists)
        if not os.path.exists(path):
            try:
                os.makedirs(path)
            except Exception as e:
                self.log.error('Error creating the target folder: {}'.format(e))

        # Count the number of files in the folder
        filename = f"{file}{fileformat}"
        complete_path = os.path.join(path, filename)
        return complete_path

    def save_to_tiff(self, n_frames, path, data):
        """ Save the image data to a tiff file.

        @param: (int) n_frames: number of frames (needed to distinguish between 2D and 3D data)
        @param: (str) path: complete path where the object is saved to (including the suffix .tif)
        @param: data: (np.array) image stack
        """
        try:
            with TiffWriter(path) as tif:
                tif.write(data.astype(np.uint16))
            self.log.info('Saved data to file {}'.format(path))
        except Exception as e:
            self.log.warning(f'Data not saved: {e}')

    def save_to_tiff_separate(self, n_channels, path, data):
        """ For each separate channel (laser line), save the image data to a tiff file.

        @param: int n_channels: number of acquisition channels
        @param: str path: complete path where the object is saved to (including the suffix .tif)
        @param: data: (np.array) image stack
        """
        try:
            for channel in range(n_channels):
                new_path, filename = os.path.split(path)
                filename, _ = os.path.splitext(filename)
                new_path = os.path.join(new_path, f'{filename}_ch{str(channel).zfill(2)}.tif')

                with TiffWriter(new_path) as tif:
                    tif.write(data[channel::n_channels].astype(np.uint16))
                self.log.info('Saved data to file {}'.format(new_path))
        except Exception as e:
            self.log.warning(f'Data not saved: {e}')

    def save_metadata_txt_file(self, filenamestem, datatype, metadata):
        """"Save a txt file containing the metadata.
        @param: (str) filenamestem (example /home/barho/images/2020-12-16/samplename)
        @param: (str) datatype: string identifier of the data shape: _Movie or _Image
        @param: (dict) metadata: dictionary containing the annotations
        """
        complete_path = self.create_generic_filename(filenamestem, datatype, 'parameters', '.txt', addfile=True)
        with open(complete_path, 'w') as file:
            # file.write(str(metadata))  # for standard txt file
            # yaml file. can use suffix .txt. change if .yaml preferred.
            yaml = YAML()
            yaml.dump(metadata, file)
        self.log.info('Saved metadata to {}'.format(complete_path))

    def save_to_fits(self, path, data, metadata):
        """ Save the image data to a fits file, including the metadata in the header
        See also https://docs.astropy.org/en/latest/io/fits/index.html#creating-a-new-image-file

        Works for 2D data and stacks

        :param: str path: complete path where the object is saved to, including the suffix .fits
        :param: data: np.array (2D or 3D)
        :param: dict metadata: dictionary containing the metadata that shall be saved with the image data
        """

        data = data.astype(np.int16)  # data conversion because 16 bit image shall be saved
        hdu = fits.PrimaryHDU(data)  # PrimaryHDU object encapsulates the data
        hdul = fits.HDUList([hdu])
        # add the header
        hdr = hdul[0].header
        for key in metadata:
            hdr[key] = metadata[key]
        # write to file
        try:
            hdul.writeto(path)
            self.log.info('Saved data to file {}'.format(path))
        except Exception as e:
            self.log.warning(f'Data not saved: {e}')
        #
        # t1 = time()
        # print(f'Saving time : {t1-t0}s')

    def save_to_hdf5(self, path, data, metadata):
        """ Save the data in h5 format. This function was specifically created for the Kinetix camera. Considering the
        size of the images, a gzip compression is applied (this method is a lossless method - the decompressed images
        should be identical to the original). Note the metadata are also saved in the same file and the images are
        separated according to acquisition channels.

        @param path: (str) complete path where to save the data
        @param data: (numpy array) array containing the images to be saved
        @param metadata: (dict) contains all the metadata regarding the acquisition parameters
        """
        n_channels = int(metadata['n_channels'])
        with h5py.File(path, 'w') as hf:
            for channel in range(n_channels):
                self.log.info(f"Saving images for channel {channel}")
                dataset = hf.create_dataset(f'image_ch{channel}', data=data[channel::n_channels],
                                            compression='gzip', compression_opts=1)
                # dataset = hf.create_dataset(f'image_ch{channel}', data=data[channel::n_channels],
                #                             compression='lzf')
                # dataset = hf.create_dataset(f'image_ch{channel}', data=data[channel::n_channels],
                #                             **hdf5plugin.Blosc())

            self.log.info(f"Saving metadata.")
            for key, value in metadata.items():
                dataset.attrs[key] = value

    @staticmethod
    def add_fits_header(path, dictionary):
        """ After spooling to fits format, this method accesses the file and adds the metadata in the header.
        This method is to be used only in combination with spooling.
        :params str path: complete path where the object is saved to, including the suffix .fits
        :params dict dictionary: containing metadata with fits compatible keys and values
        """
        with fits.open(path, mode='update') as hdul:
            hdr = hdul[0].header
            for key in dictionary:
                hdr[key] = dictionary[key]

    @staticmethod
    def convert_to_fits_metadata(metadata):
        """ Convert a dictionary in arbitrary format to fits compatible format, using keys with max. 8 letters,
        capitals and no spaces. If several values are stored under one key, each list item gets its proper key
        using a numerotation.
        :param: dict metadata: dictionary to convert to fits compatible format

        :return: dict fits_metadata: dictionary converted to fits compatible format """
        fits_metadata = {}
        for key, value in metadata.items():
            key = key.replace(' ', '_')
            if isinstance(value, list):
                for i in range(len(value)):
                    fits_key = key[:7].upper()+str(i+1)
                    fits_value = (value[i], key+str(i+1))
                    fits_metadata[fits_key] = fits_value
            else:
                fits_key = key[:8].upper()
                fits_value = (value, key)
                fits_metadata[fits_key] = fits_value

        return fits_metadata

    def save_to_npy(self, path, data):
        """ Save the image data to a npy file. The images are reformated to uint16, in order to optimize the saving
        time.
        @param: str path: complete path where the object is saved to (including the suffix .tif)
        @param: data: np.array
        """
        try:
            np.save(path, data.astype(np.uint16))
            self.log.info('Saved data to file {}'.format(path))
        except Exception as e:
            self.log.warning(f'Data not saved: {e}')

    def save_to_ome_tif(self, path, data, metadata):
        """Save a NumPy array as an OME-TIFF file.
        @param: path (str): indicate the complete file path were to save the data
        @param: data (numpy array): acquired data
        @param: metadata (dict): contains all the metadata associated to the acquisition
        """
        # Read the parameters from the metadata
        acquisition = metadata.get('Acquisition', [])
        exposure = None
        kinetic = None
        excitation_wavelength = []

        for item in acquisition:
            if 'exposure_time_(s)' in item:
                exposure = item['exposure_time_(s)']
            if 'laser_lines' in item:
                excitation_wavelength = item['laser_lines']
                if len(excitation_wavelength) > 0:
                    excitation_wavelength = int(excitation_wavelength[0].split()[0])
                else:
                    excitation_wavelength = None
            if 'kinetic_time_(s)' in item:
                kinetic = item['kinetic_time_(s)']

        # Create the metadata
        Nframes, Lx, Ly = data.shape
        planes = [Plane(delta_t=kinetic * i, delta_t_unit="s",
                        exposure_time=exposure, exposure_time_unit="s",
                        the_z=0, the_c=0, the_t=i)
                  for i in range(Nframes)]

        channel = Channel(
            id='Channel:0:0',
            name='CH1',
            illumination_type='Epifluorescence'
        )
        if excitation_wavelength is not None:
            channel.excitation_wavelength = excitation_wavelength

        pixels = Pixels(
            id='Pixels:0',
            dimension_order='XYZCT',
            size_c=1,
            size_t=Nframes,
            size_x=Ly,
            size_y=Lx,
            size_z=1,
            type='uint16',
            channels=[channel],
            planes=planes,
        )
        ome = OME(images=[Image(id="Image:0", pixels=pixels)])

        # Save the data as TIFF
        with TiffWriter(path) as tif:
            tif.write(data.astype(np.uint16), metadata={"axes": "TXY", "OME": ome.to_xml()})

# ----------------------------------------------------------------------------------------------------------------------
# Methods to handle the user interface state
# ----------------------------------------------------------------------------------------------------------------------

    def start_live_mode(self):
        """ Allows to start the live mode programmatically.
        """
        if not self.live_enabled:
            self.sigLiveStarted.emit()  # to inform the GUI that live mode has been started programmatically

    def stop_live_mode(self):
        """ Allows to stop the live mode programmatically, for example in the preparation steps of a task
        where live mode would interfere with the new camera settings. """
        if self.live_enabled:
            self.stop_loop()
            self.sigLiveStopped.emit()  # to inform the GUI that live mode has been stopped programmatically

    def disable_camera_actions(self):
        """ This method provides a security to avoid all camera related actions from GUI, for example during Tasks. """
        self.sigDisableCameraActions.emit()

    def enable_camera_actions(self):
        """ This method resets all camera related actions from GUI to callable state, for example after Tasks. """
        self.sigEnableCameraActions.emit()
