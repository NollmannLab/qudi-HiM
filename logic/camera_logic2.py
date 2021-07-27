# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains the logic to control a microscope camera.

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
import numpy as np
from time import sleep
import os
from PIL import Image
from astropy.io import fits
import yaml

from core.connector import Connector
from core.configoption import ConfigOption
from core.util.mutex import Mutex
from logic.generic_logic import GenericLogic
from qtpy import QtCore

# ======================================================================================================================
# Worker class for camera live display
# ======================================================================================================================


class WorkerSignals(QtCore.QObject):
    """ Defines the signals available from a running worker thread """

    sigFinished = QtCore.Signal()


class LiveImageWorker(QtCore.QRunnable):
    """ Worker thread to update the live image at the desired frame rate

    The worker handles only the waiting time, and emits a signal that serves to trigger the update indicators """

    def __init__(self, time_constant):
        super(LiveImageWorker, self).__init__()
        self.signals = WorkerSignals()
        self.time_constant = time_constant

    @QtCore.Slot()
    def run(self):
        """ """
        sleep(self.time_constant)
        self.signals.sigFinished.emit()

# ======================================================================================================================
# Logic class
# ======================================================================================================================


class CameraLogic(GenericLogic):
    """
    Class containing the logic to control a microscope camera.

    Example config for copy-paste:

    camera_logic:
    module.Class: 'camera_logic2.CameraLogic'
    connect:
        hardware: 'andor_ultra_camera'

    """
    # declare connectors
    hardware = Connector(interface='CameraInterface')

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
    sigLiveStopped = QtCore.Signal()  # informs the GUI that live mode was stopped programatically
    sigDisableCameraActions = QtCore.Signal()
    sigEnableCameraActions = QtCore.Signal()

    # attributes
    enabled = False  # indicates if the camera is currently acquiring data
    saving = False  # indicates if the camera is currently saving a movie

    has_temp = False
    has_shutter = False
    _fps = 20
    _exposure = 1.
    _gain = 1.
    _temperature = 0  # use any value. It will be overwritten during on_activate if sensor temperature is available
    temperature_setpoint = _temperature
    _last_image = None
    _kinetic_time = None

    _hardware = None

    fileformat_list = ['tif', 'fits']

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self.threadpool = QtCore.QThreadPool()

    def on_activate(self):
        """ Initialisation performed during activation of the module.
        """
        self._hardware = self.hardware()

        self.enabled = False
        self.saving = False
        self.has_temp = self._hardware.has_temp()
        if self.has_temp:
            self.temperature_setpoint = self._hardware._default_temperature
        self.has_shutter = self._hardware.has_shutter()

        # update the private variables _exposure, _gain, _temperature
        self.get_exposure()
        self.get_gain()
        self.get_temperature()

    def on_deactivate(self):
        """ Perform required deactivation. """
        pass

# ----------------------------------------------------------------------------------------------------------------------
# (Low-level) methods making the camera interface functions accessible from the GUI.
# Getter and setter methods for camera attributes.
# ----------------------------------------------------------------------------------------------------------------------

    def get_name(self):
        """ Retrieve an identifier of the camera that the GUI can print.

        :return: string: name for the camera
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

        :param: float time: desired new exposure time in seconds

        :return: None
        """
        self._hardware.set_exposure(time)
        exp = self.get_exposure()  # updates also the attribute self._exposure and self._fps
        self.sigExposureChanged.emit(exp)

    def get_exposure(self):
        """ Get the exposure time of the camera and update the class attributes _exposure and _fps.

        :return: float exposure time (in seconds)
        """
        self._exposure = self._hardware.get_exposure()
        self._fps = min(1 / self._exposure, self._max_fps)
        return self._exposure

    # this function is specific to andor camera
    def get_kinetic_time(self):
        """ Andor camera only: Get the kinetic time of the camera and update the class attribute _kinetic_time.

        :return: float kinetic time (in seconds)
        """
        if self.get_name() == 'iXon Ultra 897':
            self._kinetic_time = self._hardware.get_kinetic_time()
            return self._kinetic_time
        else:
            return

    def set_gain(self, gain):
        """ Set the gain of the camera. Inform the GUI that a new gain value was set.

        :param: int gain: desired new gain.

        :return: None
        """
        self._hardware.set_gain(gain)
        gain_value = self.get_gain()  # called to update the attribute self._gain
        self.sigGainChanged.emit(gain_value)

    def get_gain(self):
        """ Get the gain setting of the camera and update the class attribute _gain.

        :return: int gain: current gain setting.
        """
        gain = self._hardware.get_gain()
        self._gain = gain
        return gain

    def get_progress(self):
        """ Retrieves the total number of acquired images by the camera (during a movie acquisition).

        :return: int progress: total number of acquired images.
        """
        return self._hardware.get_progress()

    def set_temperature(self, temperature):
        """ Set temperature of the camera, if accessible.

         :param: int temperature: desired new temperature setpoint
         :return: None
         """
        if not self.has_temp:
            pass
        else:
            # make sure the cooler is on
            if self._hardware.is_cooler_on() == 0:
                self._hardware._set_cooler(True)

            self.temperature_setpoint = temperature  # store the new setpoint to compare against actual temperature
            self._hardware.set_temperature(temperature)

    def get_temperature(self):
        """ Get temperature of the camera, if accessible, and update the class attribute _temperature.

        :return: int temperature: current sensor temperature
        """
        if not self.has_temp:
            self.log.warn('Sensor temperature control not available')
        else:
            if self.enabled:  # live mode on
                self.interrupt_live()
                
            temp = self._hardware.get_temperature()
            self._temperature = temp
            
            if self.enabled:  # restart live mode
                self.resume_live()
            return temp

# ----------------------------------------------------------------------------------------------------------------------
# Methods to access camera state
# ----------------------------------------------------------------------------------------------------------------------

    def get_ready_state(self):
        """ Is the camera ready for an acquisition ?

        :return: str: ready ? 'True', 'False'
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
        """ Retrieves the status of the cooler if there is one (only if has_temp is True).

        :returns str: cooler on, cooler off """
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

        :param int hbin: number of pixels to bin horizontally
        :param int vbin: number of pixels to bin vertically.
        :param int hstart: Start column (inclusive)
        :param int hend: End column (inclusive)
        :param int vstart: Start row (inclusive)
        :param int vend: End row (inclusive).
        """
        if self.enabled:  # live mode is on
            self.interrupt_live()  # interrupt live to allow access to camera settings

        err = self._hardware.set_image(hbin, vbin, hstart, hend, vstart, vend)
        if err < 0:
            self.log.warn('Sensor region not set')
        else:
            self.log.info('Sensor region set to {} x {}'.format(vend - vstart + 1, hend - hstart + 1))

        if self.enabled:
            self.resume_live()  # restart live in case it was activated

    def reset_sensor_region(self):
        """ Reset to full sensor size. """
        if self.enabled:  # live mode is on
            self.interrupt_live()

        width = self._hardware._full_width  # store the full_width in the hardware module because _width is
        # overwritten when image is set
        height = self._hardware._full_height  # same goes for height

        err = self._hardware.set_image(1, 1, 1, width, 1, height)
        if err < 0:
            self.log.warn('Sensor region not reset to default')
        else:
            self.log.info('Sensor region reset to default: {} x {}'.format(height, width))

        if self.enabled:
            self.resume_live()

    @QtCore.Slot(bool)
    def set_frametransfer(self, activate):
        """ Activate frametransfer mode for ixon ultra camera: the boolean activate is stored in a variable in the
        camera module. When an acquisition is started, frame transfer is set accordingly.

        :params: bool activate ?
        """
        if self.get_name() == 'iXon Ultra 897':
            if self.enabled:  # if live mode is on, interrupt to be able to access frame transfer setting
                self.interrupt_live()
            self._hardware._set_frame_transfer(int(activate))
            if self.enabled:  # if live mode was interrupted, restart it
                self.resume_live()
            self.log.info(f'Frametransfer mode activated: {activate}')
            # we also need to update the indicator on the gui
            exp = self.get_exposure()  # we just need to send the signal sigExposureChanged but it must carry a float
            # so we send exp as argument
            self.sigExposureChanged.emit(exp)
        # do nothing in case of cameras that do not support frame transfer
        else:
            pass

# ----------------------------------------------------------------------------------------------------------------------
# Methods to handle camera acquisition and snap / live display
# ----------------------------------------------------------------------------------------------------------------------

# Method invoked by snap button on GUI ---------------------------------------------------------------------------------
    def start_single_acquistion(self):  # watch out for the typo !!
        """ Take a single camera image
        """
        self._hardware.start_single_acquisition()
        self._last_image = self._hardware.get_acquired_data()
        self.sigUpdateDisplay.emit()
        self._hardware.stop_acquisition()  # this in needed to reset the acquisition mode to default
        self.sigAcquisitionFinished.emit()

# Methods invoked by live button on GUI --------------------------------------------------------------------------------
    def start_loop(self):
        """ Start the live display loop.
        """
        self.enabled = True
        # self.timer.start(1000*1/self._fps)
        worker = LiveImageWorker(1 / self._fps)
        worker.signals.sigFinished.connect(self.loop)
        self.threadpool.start(worker)

        if self._hardware.support_live_acquisition():
            self._hardware.start_live_acquisition()
        else:
            self._hardware.start_single_acquisition()

    def loop(self):
        """ Execute step in the live display loop: save one of each control and process values
        """
        self._last_image = self._hardware.get_acquired_data()
        self.sigUpdateDisplay.emit()
        if self.enabled:
            worker = LiveImageWorker(1 / self._fps)
            worker.signals.sigFinished.connect(self.loop)
            self.threadpool.start(worker)

            if not self._hardware.support_live_acquisition():
                self._hardware.start_single_acquisition()  # the hardware has to check it's not busy

    def stop_loop(self):
        """ Stop the live display loop.
        """
        self.enabled = False
        self._hardware.stop_acquisition()
        self.sigVideoFinished.emit()

# Helper methods to interrupt/restart the camera live mode to give access to camera settings etc. ----------------------

    # maybe there is some more things to do here, to avoid that the worker thread continues running
    # or try to explore if this could help for the live display during the video saving ..
    def interrupt_live(self):
        """ Interrupt the live display loop, for example to update camera settings """
        self._hardware.stop_acquisition()
        # note that enabled attribute is not modified, to resume the state of the live display

    def resume_live(self):
        """ Restart the live display loop """
        self._hardware.start_live_acquisition()

# Method invoked by save last image button on GUI ----------------------------------------------------------------------
    def save_last_image(self, path, metadata, fileformat='.tif'):
        """ saves a single image to disk

        @param: str path: path stem, such as /home/barho/images/2020-12-16/samplename
        @param: dict metadata: dictionary containing the metadata
        @param: str fileformat: default '.tif' but can be modified if needed.

        @return: None
        """
        if self._last_image is None:
            self.log.warning('No image available to save')
        else:
            image_data = self._last_image

            complete_path = self._create_generic_filename(path, '_Image', 'image', fileformat, addfile=False)
            self._save_to_tiff(1, complete_path, image_data)
            self._save_metadata_txt_file(path, '_Image', metadata)

# Methods invoked by start video button on GUI--------------------------------------------------------------------------
    def save_video(self, filenamestem, fileformat, n_frames, display, metadata, emit_signal=True):
        """ Saves n_frames to disk as a tiff stack

        :param: str filenamestem, such as /home/barho/images/2020-12-16/samplename
        :param: str fileformat (including the dot, such as '.tif', '.fits')
        :param: int n_frames: number of frames to be saved
        :param: bool display: show images on live display on gui
        :param: dict metadata: meta information to be saved with the image data (in a separate txt file if tiff fileformat, or in the header if fits format)
        :param: bool emit_signal: can be set to false to avoid sending the signal for gui interaction,
                for example when function is called from ipython console or in a task
                #leave the default value True when function is called from gui
        """
        if self.enabled:  # live mode is on
            self.interrupt_live()  # do not call stop_loop. self.enabled must be left in its state.

        self.saving = True
        # n_proxy helps to limit the number of displayed images during the video saving
        n_proxy = int(250 / (self._exposure * 1000))  # the factor 250 is chosen arbitrarily to give a reasonable number
        # of displayed images (every 5th for an exposure time of 50 ms for example)
        n_proxy = max(1, n_proxy)  # if n_proxy is less than 1 (long exposure time), display every image
        err = self._hardware.start_movie_acquisition(n_frames)
        if not err:
            self.log.warning('Video acquisition did not start')

        ready = self._hardware.get_ready_state()
        while not ready:
            progress = self._hardware.get_progress()
            self.sigProgress.emit(progress)
            ready = self._hardware.get_ready_state()
            if display:
                if progress % n_proxy == 0:  # to limit the number of displayed images
                    self._last_image = self._hardware.get_most_recent_image()
                    self.sigUpdateDisplay.emit()
                    # sleep(0.0001)  # this is used to force enough time for a signal to be transmitted. maybe there
                    # is a better way to do this ? not needed in case the modulo operation is used to take only every
                    # n'th image

        self._hardware.wait_until_finished()  # this is important especially if display is disabled
        self.sigSaving.emit()  # for info message on statusbar of GUI

        image_data = self._hardware.get_acquired_data()  # first get the data before resetting the acquisition mode
        # of the camera
        self._hardware.finish_movie_acquisition()  # reset the attributes and the default acquisition mode
        self.saving = False

        # restart live in case it was activated
        if self.enabled:
            self.resume_live()

        # data handling
        complete_path = self._create_generic_filename(filenamestem, '_Movie', 'movie', fileformat, addfile=False)
        # create the PIL.Image object and save it to tiff
        if fileformat == '.tif':
            self._save_to_tiff(n_frames, complete_path, image_data)
            self._save_metadata_txt_file(filenamestem, '_Movie', metadata)

        elif fileformat == '.fits':
            fits_metadata = self.convert_to_fits_metadata(metadata)
            self._save_to_fits(complete_path, image_data, fits_metadata)
        else:
            self.log.info(f'Your fileformat {fileformat} is currently not covered')
        if emit_signal:
            self.sigVideoSavingFinished.emit()
        else:  # needed to clean up the info on statusbar when gui is opened without calling video_saving_finished
            self.sigCleanStatusbar.emit()

    # this function is specific for andor ixon ultra camera
    def do_spooling(self, filenamestem, fileformat, n_frames, display, metadata):
        """ Saves n_frames to disk as a tiff stack without need of data handling within this function.
        Available for andor camera. Useful for large data sets which would be overwritten in the buffer

        :param: str filenamestem, such as /home/barho/images/2020-12-16/samplename
        :param: int n_frames: number of frames to be saved
        :param: bool display: show images on live display on gui
        :param: dict metadata: meta information to be saved with the image data (in a separate txt file if tiff fileformat, or in the header if fits format)
        """
        if self.enabled:  # live mode is on
            self.interrupt_live()

        self.saving = True
        # n_proxy helps to limit the number of displayed images during the video saving
        n_proxy = int(250 / (self._exposure * 1000))  # the factor 250 is chosen arbitrarily to give a reasonable number
        # of displayed images (every 5th for an exposure time of 50 ms for example)
        n_proxy = max(1, n_proxy)  # if n_proxy is less than 1 (long exposure time), display every image
        path = self._create_generic_filename(filenamestem, '_Movie', 'movie', '', addfile=False)  # use an empty
        # string for fileformat. this will be handled by the camera itself
        if fileformat == '.tif':
            method = 7
        elif fileformat == '.fits':
            method = 5
        else:
            self.log.info(f'Your fileformat {fileformat} is currently not covered')
            return

        self._hardware._set_spool(1, method, path, 10)  # parameters: active (1 = yes), method (7 save as tiff,
        # 5 save as fits), filenamestem, framebuffersize
        err = self._hardware.start_movie_acquisition(n_frames)  # setting kinetics acquisition mode, make sure
        # everything is ready for an acquisition
        if not err:
            self.log.warning('Spooling did not start')

        ready = self._hardware.get_ready_state()
        while not ready:
            spoolprogress = self._hardware.get_progress()
            self.sigProgress.emit(spoolprogress)
            ready = self._hardware.get_ready_state()
            if display:
                if spoolprogress % n_proxy == 0:  # to limit the number of displayed images
                    self._last_image = self._hardware.get_most_recent_image()
                    self.sigUpdateDisplay.emit()
                    # sleep(0.0001)  # this is used to force enough time for a signal to be transmitted. maybe there
                    # is a better way to do this ?

        self._hardware.wait_until_finished()
        self._hardware.finish_movie_acquisition()
        self._hardware._set_spool(0, method, path, 10)  # deactivate spooling
        self.log.info('Saved data to file {}{}'.format(path, fileformat))
        # metadata saving
        if fileformat == '.tif':
            self._save_metadata_txt_file(filenamestem, '_Movie', metadata)
        elif fileformat == '.fits':
            try:
                complete_path = path + '.fits'
                fits_metadata = self.convert_to_fits_metadata(metadata)
                self._add_fits_header(complete_path, fits_metadata)
            except Exception as e:
                self.log.warn(f'Metadata not saved: {e}.')
        else:
            pass  # this case will never be accessed because the same if-elif-else structure was already applied above

        self.saving = False

        # restart live in case it was activated
        if self.enabled:
            self.resume_live()

        self.sigSpoolingFinished.emit()

# ----------------------------------------------------------------------------------------------------------------------
# Methods for Qudi tasks / experiments requiring synchronization between camera and lightsources
# ----------------------------------------------------------------------------------------------------------------------

    def prepare_camera_for_multichannel_imaging(self, frames, exposure, gain, save_path, file_format):
        self._hardware.prepare_camera_for_multichannel_imaging(frames, exposure, gain, save_path, file_format)

    def reset_camera_after_multichannel_imaging(self):
        self._hardware.reset_camera_after_multichannel_imaging()

    def get_acquired_data(self):   # used in Hi-M Task RAMM
        return self._hardware.get_acquired_data()

    def start_acquisition(self):  # used in Hi-M Task RAMM
        self._hardware._start_acquisition()  # not on camera interface

    def stop_acquisition(self):  # used in Hi-M Task RAMM
        self._hardware.stop_acquisition()
        
    def abort_acquisition(self):  # used in multicolor imaging PALM  -> can this be combined with stop_acquisition ?
        self._hardware._abort_acquisition()  # not on camera interface

# ----------------------------------------------------------------------------------------------------------------------
# Filename and data handling
# ----------------------------------------------------------------------------------------------------------------------

    def get_last_image(self):  # is this method needed ??
        """ Return last acquired image """
        return self._last_image

    def _create_generic_filename(self, filenamestem, folder, file, fileformat, addfile):
        """ helper function that creates a generic filename using the following format:

        filenamestem/001_folder/file.tif example: /home/barho/images/2020-12-16/samplename/000_Movie/movie.tif

        filenamestem is typically generated by the save settings dialog in basic gui but can also entered manually if
        function is called in console

        :params: str filenamestem  (example /home/barho/images/2020-12-16/samplename)
        :params: str folder: specify the type of experiment (ex. Movie, Snap)
        :params: str file: filename (ex movie, image). do not specify the fileformat.
        :params: str fileformat: specify the type of file (.tif, .txt, ..) including the dot !
        :params: bool addfile: if True, the last created folder will again be accessed (needed for metadata saving)

        :returns str complete path
        """
        # check if folder filenamestem exists, if not create it
        if not os.path.exists(filenamestem):
            try:
                os.makedirs(filenamestem)  # recursive creation of all directories on the path
            except Exception as e:
                self.log.error('Error {0}'.format(e))

        # count the subdirectories in the directory filenamestem (non recursive !) to generate an incremental prefix
        dir_list = [name for name in os.listdir(filenamestem) if os.path.isdir(os.path.join(filenamestem, name))]
        number_dirs = len(dir_list)
        if addfile:
            number_dirs -= 1
        prefix = str(number_dirs+1).zfill(3)
        folder_name = prefix + folder
        path = os.path.join(filenamestem, folder_name)
        # now create this folder
        if not os.path.exists(path):  # we need this condition because metadata will be written in the same folder so
            # the folder may already exist
            try:
                os.makedirs(path)
            except Exception as e:
                self.log.error('Error creating the target folder: {}'.format(e))
        filename = '{0}{1}'.format(file, fileformat)
        complete_path = os.path.join(path, filename)
        return complete_path

    def _save_to_tiff(self, n_frames, path, data):
        """ helper function to save the image data to a tiff file

        creates the PIL.Image object and saves it to tiff

        :params int n_frames: number of frames (needed to distinguish between 2D and 3D data)
        :params str path: complete path where the object is saved to (including the suffix .tif)
        :params data: np.array

        :returns None
        """
        # type conversion to int16
        data = data.astype('int16')
        # self.log.info('type conversion called')
        # 2D data case (no stack)
        if n_frames == 1:
            try:
                self.save_u16_to_tiff(data, (data.shape[1], data.shape[0]), path)
                self.log.info('Saved data to file {}'.format(path))
            except:
                self.log.warning('Data not saved')
            return None

        # 3D data (note: z stack is the first dimension)
        else:
            try:
                size = (data.shape[2], data.shape[1])
                self.save_u16_to_tiff_stack(n_frames, data, size, path)
                self.log.info('Saved data to file {}'.format(path))
            except:
                self.log.warning('Data not saved')
            return None

    def save_u16_to_tiff(self, u16int, size, tiff_filename):
        """
        function found at https://blog.itsayellow.com/technical/saving-16-bit-tiff-images-with-pillow-in-python/#
        Since Pillow has poor support for 16-bit TIFF, we make our own save function to properly save a 16-bit TIFF.

        modified version for numpy array only

        @param u16int: np.array with dtype int16 to be saved as tiff. make sure that the data is in int16 format !
        otherwise the conversion to bytes will not give the right result
        @param size: size of the data
        @param str tiff_filename: including the suffix '.tif'
        """
        # write 16-bit TIFF image
        # PIL interprets mode 'I;16' as "uint16, little-endian"
        img_out = Image.new('I;16', size)
        outpil = u16int.astype(u16int.dtype.newbyteorder("<")).tobytes()
        img_out.frombytes(outpil)
        img_out.save(tiff_filename)

    def save_u16_to_tiff_stack(self, n_frames, u16int, size, tiff_filename):
        """ handles saving of 3D image data to 16 bit tiff stacks
        @param int n_frames: number of frames to be saved (1st dimension of the image data)
        @param u16int: 3D np.array with dtype int16 to be saved as tiff
        @param int tuple size: size of an individual image in the stack (x pixel, y pixel)
        @param str tiff_filename: complete path to the file, including the suffix .tif """

        imlist = []  # this will be a list of pillow Image objects
        for i in range(n_frames):
            img_out = Image.new('I;16', size)  # initialize a new pillow object of the right size
            outpil = u16int[i].astype(
                u16int.dtype.newbyteorder("<")).tobytes()  # convert the i-th frame to bytes object
            img_out.frombytes(outpil)  # create pillow object from bytes
            imlist.append(img_out)  # create the list of pillow image objects
        imlist[0].save(tiff_filename, save_all=True, append_images=imlist[1:])

    def _save_metadata_txt_file(self, filenamestem, type, metadata):
        """"helper function to save a txt file containing the metadata

        @params: str filenamestem (example /home/barho/images/2020-12-16/samplename)
        @parms: str type: string identifier of the data type: _Movie or _Image
        @params: dict metadata: dictionary containing the annotations

        @returns None
        """
        complete_path = self._create_generic_filename(filenamestem, type, 'parameters', '.txt', addfile=True)
        with open(complete_path, 'w') as file:
            # file.write(str(metadata))  # for standard txt file
            yaml.dump(metadata, file, default_flow_style=False)  # yaml file. can use suffix .txt. change if .yaml preferred.
        self.log.info('Saved metadata to {}'.format(complete_path))

    def _save_to_fits(self, path, data, metadata):
        """ helper function to save the image data to a fits file.
        see also https://docs.astropy.org/en/latest/io/fits/index.html#creating-a-new-image-file

        Works for 2D data and stacks

        @params str path: complete path where the object is saved to, including the suffix .fits
        @params data: np.array (2D or 3D)

        @returns None
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

    def _add_fits_header(self, path, dictionary):
        """ After spooling to fits format, this method accesses the file and adds the metadata in the header
        @params str path: complete path where the object is saved to, including the suffix .fits
        @params dict dictionary: containing metadata with fits compatible keys and values
        """
        with fits.open(path, mode='update') as hdul:
            hdr = hdul[0].header
            for key in dictionary:
                hdr[key] = dictionary[key]

    def convert_to_fits_metadata(self, metadata):
        """ Convert a dictionary in arbitrary format to fits compatible format.
        :param dict metadata: dictionary to convert to fits compatible format
        :return dict fits_metadata: dictionary converted to fits compatible format """
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

# ----------------------------------------------------------------------------------------------------------------------
# Methods to handle the user interface state
# ----------------------------------------------------------------------------------------------------------------------

    def stop_live_mode(self):
        """ Allows to stop the live mode programmatically, for example in the preparation steps of a task
        where live mode would interfere with the new camera settings. """
        if self.enabled:
            self.stop_loop()
            self.sigLiveStopped.emit()  # to inform the GUI that live mode has been stopped programmatically

    def disable_camera_actions(self):
        """ This method provides a security to avoid all camera related actions from GUI, for example during Tasks. """
        self.sigDisableCameraActions.emit()

    def enable_camera_actions(self):
        """ This method resets all camera related actions from GUI to callable state, for example after Tasks. """
        self.sigEnableCameraActions.emit()
