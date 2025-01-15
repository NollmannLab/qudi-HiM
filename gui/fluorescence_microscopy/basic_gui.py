# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains a GUI for the basic functions of the fluorescence microscopy setup.
Camera image, camera status control, laser and filter settings.

An extension to Qudi.

@author: F. Barho - JB. Fiche for updates and later modifications

Created on Thu Oct 29 2020
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
from datetime import datetime
import numpy as np
from time import sleep

from qtpy import QtCore
# from qtpy import QtGui
from qtpy import QtWidgets
from qtpy import uic
import pyqtgraph as pg

from gui.guibase import GUIBase
from core.connector import Connector
from core.configoption import ConfigOption
# from qtwidgets.scan_plotwidget import ScanImageItem, ScanViewBox
from gui.validators import NameValidator
from ruamel.yaml import YAML

verbose = True


# ======================================================================================================================
# Decorator (for debugging)
# ======================================================================================================================
def decorator_print_function(function):
    global verbose

    def new_function(*args, **kwargs):
        if verbose:
            print(f'*** DEBUGGING *** Executing {function.__name__} from basic_gui.py')
        return function(*args, **kwargs)
    return new_function


# ======================================================================================================================
# YAML file editor function for editing metadata
# ======================================================================================================================
def update_metadata(metadata, key_path, value, action="set"):
    """
    Generalized function to update nested metadata fields, including lists.
    @param: metadata: The metadata structure (OrderedDict or dict).
    @param: key_path: A list representing the nested path to the key.
    @param: value: The value to set, append, or remove.
    @param: action: The action to perform: "set", "append", or "remove".
            - "set" (default): Replaces the value.
            - "append": Adds to the list if it doesn't already exist.
    @return: The updated metadata structure.
    """
    current = metadata
    # Navigate to the parent of the target key
    for key in key_path[:-1]:
        if isinstance(current, list):
            # Look for the key in a list of dictionaries or OrderedDicts
            for item in current:
                if key in item:
                    current = item[key]
                    break
        else:
            current = current[key]

    # Perform the specified action on the target key
    target_key = key_path[-1]
    if isinstance(current, list):
        # Handle lists of dictionaries
        for item in current:
            if target_key in item:
                if action == "set":
                    item[target_key] = value
                elif action == "append":
                    if isinstance(item[target_key], list):
                        item[target_key].append(value)
                break
        else:
            # If key not found in list, create it (for append action)
            if action == "append":
                current.append({target_key: [value]})
    else:
        # Handle direct dictionary updates
        if action == "set":
            current[target_key] = value
        elif action == "append":
            if target_key not in current:
                current[target_key] = [value]
            elif isinstance(current[target_key], list):
                current[target_key].append(value)

    return metadata


# ======================================================================================================================
# Classes for the workers
# ======================================================================================================================
class WorkerSignals(QtCore.QObject):
    sigAcquisitionProgress = QtCore.Signal(str, str, list, bool, dict, int, str)


class AcquisitionProgressWorker(QtCore.QRunnable):
    """ Worker thread to monitor the acquisition process.
    The worker handles only the waiting time, and emits a signal that serves to trigger the update indicators. """

    def __init__(self, path, fileformat, acquisition_blocks, is_display, metadata, block, method):
        super(AcquisitionProgressWorker, self).__init__()
        self.signals = WorkerSignals()
        self.path = path
        self.fileformat = fileformat
        self.is_display = is_display
        self.metadata = metadata
        self.block = block
        self.acquisition_blocks = acquisition_blocks
        self.method = method

    @QtCore.Slot()
    def run(self):
        """ """
        sleep(0.5)
        self.signals.sigAcquisitionProgress.emit(self.path, self.fileformat, self.acquisition_blocks, self.is_display,
                                                 self.metadata, self.block, self.method)


# ======================================================================================================================
# Classes for the dialog windows and main window
# ======================================================================================================================
class CameraSettingDialog(QtWidgets.QDialog):
    """ Create the SettingsDialog window, based on the corresponding *.ui file.

    This dialog window allows to define camera settings such as exposure time, gain, etc. """
    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_camera_settings.ui')

        # Load it
        super(CameraSettingDialog, self).__init__()
        uic.loadUi(ui_file, self)


class SaveSettingDialog(QtWidgets.QDialog):
    """ Create the SaveDialog window, based on the corresponding *.ui file.

    This dialog pops up on click of the save video toolbuttons.
    """
    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_save_settings.ui')

        # Load it
        super(SaveSettingDialog, self).__init__()
        uic.loadUi(ui_file, self)


class BasicWindow(QtWidgets.QMainWindow):
    """ Class defined for the main window (not the module).
    """
    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_basic.ui')

        # Load it
        super().__init__()
        uic.loadUi(ui_file, self)

        # Statusbar   # this can not be done in qt designer and must be handcoded
        # this label is used to display the progress during spooling and video saving
        self.progress_label = QtWidgets.QLabel('')
        self.statusBar().addPermanentWidget(self.progress_label)
        self.show()


class BasicWindowCE(BasicWindow):
    """ Basic Window child class that allows to stop the live mode when window is closed,
    using a reimplemented closeEvent. """
    def __init__(self, close_function):
        super().__init__()
        self.close_function = close_function

    def closeEvent(self, event):
        self.close_function()
        event.accept()


# ======================================================================================================================
# GUI class
# ======================================================================================================================
class BasicGUI(GUIBase):
    """ Main window containing the basic tools for the fluorescence microscopy setup

    Example config for copy-paste:

    Basic Imaging:
        module.Class: 'fluorescence_microscopy.basic_gui.BasicGUI'
        default_path: 'E:\DATA'
        brightfield_control: True
        Setup: 'RAMM'
        connect:
            camera_logic: 'camera_logic'
            laser_logic: 'lasercontrol_logic'
            filterwheel_logic: 'filterwheel_logic'
            brightfield_logic: 'brightfield_logic'
    """
    # define connectors to logic modules
    camera_logic = Connector(interface='CameraLogic')
    laser_logic = Connector(interface='LaserControlLogic')
    filterwheel_logic = Connector(interface='FilterwheelLogic')
    brightfield_logic = Connector(interface='BrightfieldLogic', optional=True)

    # define the default language option as English (to make sure all float have a point as a separator)
    QtCore.QLocale.setDefault(QtCore.QLocale("English"))

    # config options
    default_path = ConfigOption('default_path', missing='error')
    brightfield_control = ConfigOption('brightfield_control', False)
    setup = ConfigOption('Setup', False)
    metadata_template_path = ConfigOption('metadata_template', missing='error')

    # signals
    # signals to camera logic
    sigVideoStart = QtCore.Signal()
    sigVideoStop = QtCore.Signal()
    sigImageStart = QtCore.Signal()

    sigVideoSavingStart = QtCore.Signal(str, str, str, int, bool, dict, bool)
    sigSpoolingStart = QtCore.Signal(str, str, str, int, bool, dict, bool)
    
    sigInterruptLive = QtCore.Signal()
    sigResumeLive = QtCore.Signal()
    
    sigSetSensor = QtCore.Signal(int, int, int, int, int, int, float)
    sigResetSensor = QtCore.Signal(float)
    
    sigReadTemperature = QtCore.Signal()

    # signals to laser control logic
    sigLaserOn = QtCore.Signal()
    sigLaserOff = QtCore.Signal()

    # signals to brightfield control logic
    sigBFOn = QtCore.Signal(int)
    sigBFOff = QtCore.Signal()
    
    # signals to filterwheel logic
    sigFilterChanged = QtCore.Signal(int)

    # attributes
    _image = []
    _camera_logic = None
    _laser_logic = None
    _filterwheel_logic = None
    _brightfield_logic = None
    _mw = None
    region_selector_enabled = False
    imageitem = None

    # flags that enable to reuse the save settings dialog for both save video and spooling
    _video = False
    _spooling = False
    _aborted = False

    # flags for rotation settings
    rotation_cw = False
    rotation_ccw = False
    rot180 = False

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self.laser_Labels = []
        self.laser_DSpinBoxes = []
        self.bf_Label = None
        self.bf_control_DSpinBox = None
        self.brightfield_on_Action = None
        self._cam_sd = None
        self._save_sd = None
        self._max_frames_movie = None
        self._max_frames_spool = None
        self.threadpool = QtCore.QThreadPool()
        self.metadata_template = None

    def on_activate(self):
        """ Initializes all needed UI files and establishes the connectors.
        """
        self._camera_logic = self.camera_logic()
        self._laser_logic = self.laser_logic()
        self._filterwheel_logic = self.filterwheel_logic()

        if self.brightfield_control:
            self._brightfield_logic = self.brightfield_logic()

        # Inquire the max number of images that the camera can handle for a single acquisition
        self._max_frames_movie, self._max_frames_spool = self._camera_logic.get_max_frames()

        # Load the metadata template
        self.yaml = YAML()
        with open(self.metadata_template_path, "r", encoding='utf-8') as file:
            self.metadata_template = self.yaml.load(file)
        self.metadata_template = dict(self.metadata_template)

        # Windows
        self._mw = BasicWindowCE(self.close_function)
        self._mw.centralwidget.hide()  # everything is in dockwidgets
        # self._mw.setDockNestingEnabled(True)
        self.init_camera_settings_ui()

        # make sure that the flags for image rotation are initially false and toggle buttons in options menu unchecked
        self.rotation_cw = False
        self.rotation_ccw = False
        self.rot180 = False
        self._mw.rotate_image_cw_MenuAction.setChecked(False)
        self._mw.rotate_image_ccw_MenuAction.setChecked(False)
        self._mw.rot180_image_MenuAction.setChecked(False)

        # adapt the windows according to the setup
        if self.setup == "Airyscan":
            self._mw.camera_DockWidget.hide()
            self._mw.camera_status_DockWidget.hide()
            self._mw.toolBar.close()
        elif self.setup == "RAMM":
            self._mw.camera_status_DockWidget.hide()

        # Menu bar actions
        # File menu
        self._mw.close_MenuAction.triggered.connect(self._mw.close)
        # Options menu
        self._mw.camera_settings_Action.triggered.connect(self.open_camera_settings)
        self._mw.rotate_image_cw_MenuAction.toggled.connect(self.rotate_image_cw_toggled)
        self._mw.rotate_image_ccw_MenuAction.toggled.connect(self.rotate_image_ccw_toggled)
        self._mw.rot180_image_MenuAction.toggled.connect(self.rot180_image_toggled)
        
        # initialize functionality of the camera dockwidget and its toolbar
        self.init_camera_dockwidget()

        # initialize functionality of the camera status dockwidget
        self.init_camera_status_dockwidget()

        # initialize functionality of the laser dockwidget and its toolbar
        self.init_laser_dockwidget()

        # initialize functionality of the filter dockwidget
        self.init_filter_dockwidget()

        # connect signals for status bar
        self._camera_logic.sigProgress.connect(self.update_statusbar)
        self._camera_logic.sigSaving.connect(self.update_statusbar_saving)

        # initialize the save settings dialog
        # after initializing the camera dockwidget because some of the values there are needed
        self.init_save_settings_ui()

    def on_deactivate(self):
        """ Deinitialisation performed during deactivation of the module.
        """
        self._mw.close()

    def show(self):
        """Make window visible and put it above all other windows.
        """
        QtWidgets.QMainWindow.show(self._mw)
        self._mw.activateWindow()
        self._mw.raise_()

# ----------------------------------------------------------------------------------------------------------------------
# Methods to initialize the dockwidgets and their associated toolbar if there is one
# ----------------------------------------------------------------------------------------------------------------------

# camera dockwidget ----------------------------------------------------------------------------------------------------
    def init_camera_dockwidget(self):
        """ Initializes the image item and the indicators on the GUI.
        Connects signals for the camera dockwidget and the camera toolbar.
        """
        # initialize the imageitem (display of camera image) qnd its histogram
        self.imageitem = pg.ImageItem(axisOrder='row-major', invertY=True)
        self._mw.camera_ScanPlotWidget.addItem(self.imageitem)
        self._mw.camera_ScanPlotWidget.setAspectLocked(True)
        self._mw.camera_ScanPlotWidget.sigMouseAreaSelected.connect(self.mouse_area_selected)
        self._mw.histogram_Widget.setImageItem(self.imageitem)

        # set the default path
        self._mw.save_path_LineEdit.setText(self.default_path)
        # add validators to the sample name and the default path lineedits
        self._mw.save_path_LineEdit.setValidator(NameValidator(path=True))
        self._mw.samplename_LineEdit.setValidator(NameValidator(empty_allowed=False))
        # synchronize the samplename_LineEdit with the LineEdit in the save settings dialog
        self._mw.samplename_LineEdit.textChanged[str].connect(self.update_sample_name)

        # initialize the camera setting indicators on the GUI
        # use the kinetic time for andor camera, exposure time for all others
        if (self._camera_logic.get_name() == 'iXon Ultra 897') or (self._camera_logic.get_name() == 'iXon Ultra 888'):
            self._mw.exposure_LineEdit.setText('{:0.5f}'.format(self._camera_logic.get_kinetic_time()))
            self._mw.exposure_Label.setText('Kinetic time (s):')
        else:
            self._mw.exposure_LineEdit.setText('{:0.5f}'.format(self._camera_logic.get_exposure()))
            self._mw.exposure_Label.setText('Exposure time (s):')

        self._mw.gain_LineEdit.setText(str(self._camera_logic.get_gain()))

        if not self._camera_logic.has_temp:
            self._mw.temp_setpoint_LineEdit.setText('')
            self._mw.temp_setpoint_LineEdit.setEnabled(False)
            self._mw.temp_setpoint_Label.setEnabled(False)
        else:
            self._mw.temp_setpoint_LineEdit.setText(str(self._camera_logic.temperature_setpoint))

        # camera toolbar
        # configure the toolbar action buttons and connect internal signals
        self._mw.take_image_Action.setEnabled(True)
        self._mw.take_image_Action.setChecked(self._camera_logic.live_enabled)
        self._mw.take_image_Action.triggered.connect(self.take_image_clicked)

        self._mw.start_video_Action.setEnabled(True)
        self._mw.start_video_Action.setChecked(self._camera_logic.live_enabled)
        self._mw.start_video_Action.triggered.connect(self.start_video_clicked)

        self._mw.save_last_image_Action.triggered.connect(self.save_last_image_clicked)

        self._mw.save_video_Action.setEnabled(True)
        self._mw.save_video_Action.setChecked(self._camera_logic.saving)
        self._mw.save_video_Action.triggered.connect(self.save_video_clicked)

        self._mw.video_quickstart_Action.triggered.connect(self.video_quickstart_clicked)

        self._mw.abort_video_Action.triggered.connect(self.abort_video_clicked)
        self._mw.abort_video_Action.setEnabled(False)

        self._mw.set_sensor_Action.setEnabled(True)
        self._mw.set_sensor_Action.setChecked(self.region_selector_enabled)
        self._mw.set_sensor_Action.triggered.connect(self.select_sensor_region)

        # signals
        self._mw.select_folder_pushButton.clicked.connect(self.load_saving_path_clicked)

        # signals to logic
        self.sigImageStart.connect(self._camera_logic.start_single_acquisition)
        self.sigVideoStart.connect(self._camera_logic.start_loop)
        self.sigVideoStop.connect(self._camera_logic.stop_loop)
        self.sigVideoSavingStart.connect(self._camera_logic.start_save_video)
        self.sigSpoolingStart.connect(self._camera_logic.start_spooling)
        # self.sigInterruptLive.connect(self._camera_logic.interrupt_live)
        # self.sigResumeLive.connect(self._camera_logic.resume_live)
        self.sigSetSensor.connect(self._camera_logic.set_sensor_region)
        self.sigResetSensor.connect(self._camera_logic.reset_sensor_region)
        self.sigReadTemperature.connect(self._camera_logic.get_temperature)

        # signals from logic
        # update the camera setting indicators when value changed (via settings window or iPython console)
        self._camera_logic.sigExposureChanged.connect(self.update_exposure)
        self._camera_logic.sigGainChanged.connect(self.update_gain)
        self._camera_logic.sigTemperatureChanged.connect(self.update_temperature)
        self._camera_logic.sigDisableFrameTransfer.connect(self.disable_frame_transfer)

        # data acquisition signals
        self._camera_logic.sigUpdateDisplay.connect(self.update_data)
        self._camera_logic.sigAcquisitionFinished.connect(self.acquisition_finished)  # for single acquisition
        self._camera_logic.sigVideoFinished.connect(self.enable_camera_toolbuttons)
        self._camera_logic.sigVideoSavingFinished.connect(self.video_saving_finished)
        self._camera_logic.sigSpoolingFinished.connect(self.video_saving_finished)
        self._camera_logic.sigCleanStatusbar.connect(self.clean_statusbar)

        # control of the UI state by logic
        self._camera_logic.sigLiveStopped.connect(self.reset_start_video_button)
        self._camera_logic.sigLiveStarted.connect(self.start_video_clicked)
        self._camera_logic.sigDisableCameraActions.connect(self.disable_camera_toolbuttons)
        self._camera_logic.sigEnableCameraActions.connect(self.enable_camera_toolbuttons)

# camera status dockwidget ---------------------------------------------------------------------------------------------
    def init_camera_status_dockwidget(self):
        """ Initializes the indicators and connects signals for the camera status dockwidget. """
        # initialize the camera status indicators on the GUI
        self._mw.camera_status_LineEdit.setText(self._camera_logic.get_ready_state())
        if not self._camera_logic.has_shutter:
            self._mw.shutter_status_LineEdit.setText('')
            self._mw.shutter_status_LineEdit.setEnabled(False)
            self._mw.shutter_Label.setEnabled(False)
        else:
            self._mw.shutter_status_LineEdit.setText(self._camera_logic.get_shutter_state())

        if not self._camera_logic.has_temp:
            self._mw.cooler_status_LineEdit.setText('')
            self._mw.cooler_status_LineEdit.setEnabled(False)
            self._mw.cooler_Label.setEnabled(False)
            self._mw.temperature_LineEdit.setText('')
            self._mw.temperature_LineEdit.setEnabled(False)
            self._mw.temperature_Label.setEnabled(False)
        else:
            self._mw.cooler_status_LineEdit.setText(self._camera_logic.get_cooler_state())
            self._mw.temperature_LineEdit.setText(str(self._camera_logic.get_temperature()))

        # signals
        # update the indicators when pushbutton is clicked
        self._mw.cam_status_pushButton.clicked.connect(self._camera_logic.update_camera_status)

        # connect signal from logic
        self._camera_logic.sigUpdateCamStatus.connect(self.update_camera_status_display)

# laser dockwidget ---------------------------------------------------------------------------------------------
    def init_laser_dockwidget(self):
        """ initializes the labels for the lasers given in config and connects signals for the laser control toolbar.
        """
        # create the laser labels and spinboxes according to number of elements given in config file
        self.laser_Labels = []
        self.laser_DSpinBoxes = []

        for key in self._laser_logic._laser_dict.keys():
            laser_label = QtWidgets.QLabel(self._laser_logic._laser_dict[key]['wavelength'])
            self.laser_Labels.append(laser_label)

            laser_spinbox = QtWidgets.QDoubleSpinBox()
            laser_spinbox.setMaximum(100.00)
            laser_spinbox.setDecimals(1)
            locale = QtCore.QLocale('English')
            laser_spinbox.setLocale(locale)
            self.laser_DSpinBoxes.append(laser_spinbox)

            self._mw.formLayout_3.addRow(laser_label, laser_spinbox)

        # add brightfield control widgets if applicable
        if self.brightfield_control:
            self.bf_Label = QtWidgets.QLabel('BF')
            self.bf_control_DSpinBox = QtWidgets.QDoubleSpinBox()
            self._mw.formLayout_3.addRow(self.bf_Label, self.bf_control_DSpinBox)

            self.brightfield_on_Action = self._mw.toolBar_2.addAction('Brightfield on')
            self.brightfield_on_Action.setCheckable(True)
            self.brightfield_on_Action.setChecked(False)

            self.brightfield_on_Action.triggered.connect(self.brightfield_on_clicked)

            self.sigBFOn.connect(self._brightfield_logic.led_control)
            self.sigBFOff.connect(self._brightfield_logic.led_off)

            # update the physical output when the spinbox value is changed
            self.bf_control_DSpinBox.valueChanged.connect(self._brightfield_logic.update_intensity)
            self._brightfield_logic.sigBrightfieldStopped.connect(self.reset_brightfield_toolbutton)

        # toolbar actions
        self._mw.laser_on_Action.setEnabled(True)
        self._mw.laser_on_Action.setChecked(self._laser_logic.enabled)
        self._mw.laser_on_Action.triggered.connect(self.laser_on_clicked)

        self._mw.laser_zero_Action.setEnabled(True)
        self._mw.laser_zero_Action.triggered.connect(self.laser_set_to_zero)

        # Signals to logic
        # starting / stopping the analog output
        self.sigLaserOn.connect(self._laser_logic.apply_voltage)
        self.sigLaserOff.connect(self._laser_logic.voltage_off)

        # internal signals
        # putting this in a loop did not work (only last element is then correctly connected) .. a less elegant alternative :
        if len(self.laser_DSpinBoxes) > 0:
            self.laser_DSpinBoxes[0].valueChanged.connect(lambda: self._laser_logic.update_intensity_dict(self._laser_logic._laser_dict['laser1']['label'], self.laser_DSpinBoxes[0].value()))
        if len(self.laser_DSpinBoxes) > 1:
            self.laser_DSpinBoxes[1].valueChanged.connect(lambda: self._laser_logic.update_intensity_dict(self._laser_logic._laser_dict['laser2']['label'], self.laser_DSpinBoxes[1].value()))
        if len(self.laser_DSpinBoxes) > 2:
            self.laser_DSpinBoxes[2].valueChanged.connect(lambda: self._laser_logic.update_intensity_dict(self._laser_logic._laser_dict['laser3']['label'], self.laser_DSpinBoxes[2].value()))
        if len(self.laser_DSpinBoxes) > 3:
            self.laser_DSpinBoxes[3].valueChanged.connect(lambda: self._laser_logic.update_intensity_dict(self._laser_logic._laser_dict['laser4']['label'], self.laser_DSpinBoxes[3].value()))
        if len(self.laser_DSpinBoxes) > 4:
            self.laser_DSpinBoxes[4].valueChanged.connect(lambda: self._laser_logic.update_intensity_dict(self._laser_logic._laser_dict['laser5']['label'], self.laser_DSpinBoxes[4].value()))
        if len(self.laser_DSpinBoxes) > 5:
            self.laser_DSpinBoxes[5].valueChanged.connect(lambda: self._laser_logic.update_intensity_dict(self._laser_logic._laser_dict['laser6']['label'], self.laser_DSpinBoxes[5].value()))
        if len(self.laser_DSpinBoxes) > 6:
            self.laser_DSpinBoxes[6].valueChanged.connect(lambda: self._laser_logic.update_intensity_dict(self._laser_logic._laser_dict['laser7']['label'], self.laser_DSpinBoxes[6].value()))
        if len(self.laser_DSpinBoxes) > 7:
            self.laser_DSpinBoxes[7].valueChanged.connect(lambda: self._laser_logic.update_intensity_dict(self._laser_logic._laser_dict['laser8']['label'], self.laser_DSpinBoxes[7].value()))

        # for i, item in enumerate(self.laser_DSpinBoxes):
        #     item.valueChanged.connect(lambda: self._laser_logic.update_intensity_dict(self._laser_logic._laser_dict[f'laser{i+1}']['label'], item.value()))
        # lambda function is used to pass in an additional argument.

        # Signals from logic
        # update GUI when intensity is changed programatically
        self._laser_logic.sigIntensityChanged.connect(self.update_laser_spinbox)
        self._laser_logic.sigLaserStopped.connect(self.reset_laser_toolbutton)
        self._laser_logic.sigDisableLaserActions.connect(self.disable_laser_toolbuttons)
        self._laser_logic.sigEnableLaserActions.connect(self.enable_laser_toolbuttons)

# filter dockwidget ---------------------------------------------------------------------------------------------
    def init_filter_dockwidget(self):
        """ initializes the filter selection combobox and connects signals.
        """
        # initialize the combobox displaying the available filters
        self.init_filter_selection()

        # internal signals
        self._mw.filter_ComboBox.activated[str].connect(self.change_filter)
        # remark: signals currentIndexChanged vs activated:
        # currentIndexChanged is sent regardless of being done programmatically or by user interaction whereas
        # activated is only sent on user interaction.
        # activated seems the better option, then the signal is only sent when a new value is selected,
        # whereas the slot change_filter is called twice when using currentIndexChanged, once for the old index,
        # once for the new one.
        # comparable to radiobutton toggled vs clicked

        # signals to logic
        self.sigFilterChanged.connect(self._filterwheel_logic.set_position)

        # signals from logic
        # update GUI when filter was manually changed
        self._filterwheel_logic.sigNewFilterSetting.connect(self.update_filter_display)
        self._filterwheel_logic.sigDisableFilterActions.connect(self.disable_filter_selection)
        self._filterwheel_logic.sigEnableFilterActions.connect(self.enable_filter_selection)

# ----------------------------------------------------------------------------------------------------------------------
# Methods belonging to the camera settings window in the options menu
# ----------------------------------------------------------------------------------------------------------------------
    def init_camera_settings_ui(self):
        """ Definition, configuration and initialisation of the camera settings GUI.
        """
        # Create the Camera settings window
        self._cam_sd = CameraSettingDialog()

        # Connect the action of the settings window with the code:
        self._cam_sd.accepted.connect(self.cam_update_settings)  # ok button
        self._cam_sd.rejected.connect(self.cam_keep_former_settings)  # cancel buttons
        
        # frame transfer settings and gain limits
        self._cam_sd.frame_transfer_CheckBox.toggled[bool].connect(self._camera_logic.set_frametransfer)
        
        if not self._camera_logic.has_temp:
            self._cam_sd.temp_spinBox.setEnabled(False)
            self._cam_sd.label_temperature.setEnabled(False)

        if not self._camera_logic.has_gain:
            self._cam_sd.gain_spinBox.setEnabled(False)
            self._cam_sd.label_gain.setEnabled(False)

        if (self._camera_logic.get_name() == 'iXon Ultra 897') or (self._camera_logic.get_name() == 'iXon Ultra 888'):
            self._cam_sd.frame_transfer_CheckBox.setEnabled(False)
            low, high = self._camera_logic.get_gain_range()
            self._cam_sd.label_gain.setText(f"Gain [{low} - {high}]")

        # write the configuration to the settings window of the GUI.
        self.cam_keep_former_settings()

    @decorator_print_function
    def cam_update_settings(self):
        """ Write new settings from the gui to the logic module.
        """
        # interrogate the acquisition status of the camera
        live_enabled = self._camera_logic.live_enabled

        # stop live display if it is on - a sleep delay is used to make sure the signal was properly emitted and the
        # acquisition stopped before attempting to change the parameters
        if live_enabled:  # camera is acquiring
            # self.sigInterruptLive.emit()
            self.sigVideoStop.emit()
            sleep(1)

        # update camera settings
        self._camera_logic.set_exposure(self._cam_sd.exposure_doubleSpinBox.value())
        self._camera_logic.set_gain(self._cam_sd.gain_spinBox.value())
        self._camera_logic.set_temperature(int(self._cam_sd.temp_spinBox.value()))
        self._mw.temp_setpoint_LineEdit.setText(str(self._cam_sd.temp_spinBox.value()))

        # if the camera was in live acquisition, re-launch it
        #if self._camera_logic.live_enabled:
        if live_enabled:
            self.sigVideoStart.emit()
            # self.sigResumeLive.emit()

    def cam_keep_former_settings(self):
        """ Keep the old settings and restores them in the gui. 
        """
        # interrupt live display
        if self._camera_logic.live_enabled:  # camera is acquiring
            self.sigInterruptLive.emit()
        self._cam_sd.exposure_doubleSpinBox.setValue(self._camera_logic._exposure)
        self._cam_sd.gain_spinBox.setValue(self._camera_logic._gain)
        self._cam_sd.temp_spinBox.setValue(self._camera_logic.temperature_setpoint)
        self._cam_sd.frame_transfer_CheckBox.setChecked(False)  # as default value
        if self._camera_logic.live_enabled:
            self.sigResumeLive.emit()

    def open_camera_settings(self):
        """ Opens the settings menu. 
        """
        self._cam_sd.exec_()

# ----------------------------------------------------------------------------------------------------------------------
# Methods belonging to the save settings window
# ----------------------------------------------------------------------------------------------------------------------
    def init_save_settings_ui(self):
        """ Definition, configuration and initialisation of the dialog window which allows to configure the
        video saving.
        """
        # Create the camera settings window
        self._save_sd = SaveSettingDialog()
        # Connect the action of the settings window with the code:
        self._save_sd.accepted.connect(self.save_video_accepted)  # ok button
        self._save_sd.rejected.connect(self.cancel_save)  # cancel buttons

        # add a validator to the folder name lineedit
        self._save_sd.foldername_LineEdit.setValidator(NameValidator(empty_allowed=True))  # empty_allowed=True should be set or not ?

        # populate the file format combobox
        self._save_sd.file_format_ComboBox.addItems(self._camera_logic.fileformat_list)

        # connect the lineedit with the path label
        self._save_sd.foldername_LineEdit.textChanged.connect(self.update_path_label)
        # link the number of frames to the acquisition time
        self._save_sd.n_frames_SpinBox.valueChanged.connect(self.update_acquisition_time)
        # link the acquisition time to the number of frames
        self._save_sd.acquisition_time_DoubleSpinBox.valueChanged.connect(self.update_n_frames)

        # set default values on start
        self.set_default_values()

    @staticmethod
    def calculate_blocks(N, b):
        """
        Calculate the number of blocks and images in each block for acquiring N images.
        @arguments:
            N (int): Total number of images to acquire.
            b (int): Number of images per block.
        @returns:
            list: A list where each element is the number of images in that block.
        """
        num_full_blocks = N // b  # Number of full blocks
        remainder = N % b  # Remaining images after full blocks
        # Create a list with `b` images for each full block
        blocks = [b] * num_full_blocks
        # If there's a remainder, add it as an additional block
        if remainder > 0:
            blocks.append(remainder)
        return blocks

    @decorator_print_function
    def save_video_accepted(self):
        """ Callback of the ok button.
        Retrieves the information given by the user and transfers them by the signal which will start the physical
        measurement.
        """
        folder_name = self._save_sd.foldername_LineEdit.text()
        default_path = self._mw.save_path_LineEdit.text()
        today = datetime.today().strftime('%Y_%m_%d')
        path = os.path.join(default_path, today, folder_name)
        fileformat = '.'+str(self._save_sd.file_format_ComboBox.currentText())
        n_frames = self._save_sd.n_frames_SpinBox.value()
        display = self._save_sd.enable_display_CheckBox.isChecked()
        metadata = self._create_metadata_dict(n_frames)

        # For the Andor camera 888, display does not work properly when the spooling mode is ON. Therefore, if display
        # is ON, the acquisition mode is automatically switch to video.
        if (self._camera_logic.get_name() == 'iXon Ultra 897') or (self._camera_logic.get_name() == 'iXon Ultra 888'):
            if not display and fileformat in ['.tif', '.fits']:
                self._spooling = True
                self._video = False
            else:
                self._spooling = False
                self._video = True
        else:
            self._video = True

        # Depending on the number of images, several consecutive acquisitions will be required. Below, the acquisition
        # is divided in blocks, according to the maximum number of frames the camera & computer can handle.
        if self._video:
            acquisition_blocks = self.calculate_blocks(n_frames, self._max_frames_movie)
            acq_method = "video"
        elif self._spooling:
            acquisition_blocks = self.calculate_blocks(n_frames, self._max_frames_spool)
            acq_method = "spool"
        else:
            self.log.error('For some unknown reason, none of the two acquisition methods (video or spool) were properly'
                           ' set. The error was detected in the "save_video_accepted" in basic_gui.py')

        # Launch the first acquisition
        filename = f'movie_{"{:02d}".format(0)}'
        print(f'path : {path} in save_video_accepted')
        print(f'filename : {filename} in save_video_accepted')
        if self._video:
            self.sigVideoSavingStart.emit(path, filename, fileformat, acquisition_blocks[0], display, metadata, False)
        elif self._spooling:
            self.sigSpoolingStart.emit(path, filename, fileformat, acquisition_blocks[0], display, metadata, False)

        # Launch a worker thread that will monitor the saving procedures - this is required since having a while loop
        # waiting for the end of the acquisition is freezing the GUI...
        self.disable_camera_toolbuttons()
        worker = AcquisitionProgressWorker(path, fileformat, acquisition_blocks, display, metadata, 0, acq_method)
        worker.signals.sigAcquisitionProgress.connect(self.monitor_acquisition)
        self.threadpool.start(worker)

    @decorator_print_function
    def monitor_acquisition(self, path, fileformat, acquisition_blocks, display, metadata, n_block, acq_method):
        """ This method is used to monitor a current acquisition (block by block).
        @param path: (str) path to the folder where the data are saved
        @param fileformat: (str) indicates the selected format for the images
        @param acquisition_blocks: (list) contains the number of frames for each acquisition block
        @param display: (bool) indicate whether the acquisition mode is spooling or video
        @param metadata: (dic) contains the metadata
        @param n_block: (int) indicate which block is being processed
        @param acq_method: (int) indicated which acquisition method is used
        """
        if self._video or self._spooling:
            pass
        elif self._aborted:
            self.log.warn("Acquisition was aborted by user.")
            self.enable_camera_toolbuttons()
            self._mw.progress_label.setText('')
            self._aborted = False
            return
        else:
            n_block = n_block + 1
            if n_block < len(acquisition_blocks):
                n_frames_block = acquisition_blocks[n_block]

                # Reset the variable indicating that an acquisition is being processed
                if acq_method == "video":
                    self._video = True
                elif acq_method == "spool":
                    self._spooling = True

                # Launch the acquisition
                filename = f'movie_{"{:02d}".format(n_block)}'
                if self._video:
                    self.sigVideoSavingStart.emit(path, filename, fileformat, n_frames_block, display, metadata, True)
                elif self._spooling:
                    self.sigSpoolingStart.emit(path, filename, fileformat, n_frames_block, display, metadata, True)
            else:
                self.log.info("Acquisition is finished!")
                # reset the toolbuttons and clear the status bar
                self.enable_camera_toolbuttons()
                self._mw.save_video_Action.setChecked(False)
                self._mw.progress_label.setText('')
                return

        # Launch a worker thread that will monitor the saving procedures
        worker = AcquisitionProgressWorker(path, fileformat, acquisition_blocks, display, metadata, n_block, acq_method)
        worker.signals.sigAcquisitionProgress.connect(self.monitor_acquisition)
        self.threadpool.start(worker)

    def cancel_save(self):
        """ Callback of the cancel button of the video save settings dialog.
        """
        self.set_default_values()
        self.reset_toolbuttons()  # this resets the toolbar buttons to callable state
        self._video = False
        self._spooling = False

    def set_default_values(self):
        """ (Re)sets the default values for the field of the dialog.
        """
        self._save_sd.foldername_LineEdit.setText(self._mw.samplename_LineEdit.text())
        self.update_path_label()
        self._save_sd.n_frames_SpinBox.setValue(1)
        self.update_acquisition_time()
        self._save_sd.enable_display_CheckBox.setChecked(True)
        self._save_sd.file_format_ComboBox.setCurrentIndex(0)

    def update_path_label(self):
        """ Generates the informative text indicating the complete path,
        displayed below the folder name specified by the user. """
        folder_name = self._save_sd.foldername_LineEdit.text()
        default_path = self._mw.save_path_LineEdit.text()
        today = datetime.today().strftime('%Y_%m_%d')
        path = os.path.join(default_path, today, folder_name)  #
        self._save_sd.complete_path_Label.setText('Save to: {}'.format(path))

    def update_acquisition_time(self):
        """ Calculates the displayed acquisition duration given the number of frames indicated by the user. """
        exp_time = float(self._mw.exposure_LineEdit.text())  # if andor cam is used, the kinetic_time is retrieved here
        n_frames = self._save_sd.n_frames_SpinBox.value()
        acq_time = exp_time * n_frames
        self._save_sd.acquisition_time_DoubleSpinBox.setValue(acq_time)

    def update_n_frames(self):
        """ Calcuates the number of frames given the selected total acquisition time,
        if the user prefers indicating the duration of the video to be saved. """
        exp_time = float(self._mw.exposure_LineEdit.text())  # if andor cam is used, the kinetic_time is retrieved here
        acq_time = self._save_sd.acquisition_time_DoubleSpinBox.value()
        n_frames = int(round(acq_time / exp_time))
        self._save_sd.n_frames_SpinBox.setValue(n_frames)
        self.update_acquisition_time()  # call this to adapt the acquisition time to the nearest possible value according to n_frames

    def open_save_settings(self):
        """ Opens the settings menu.
        """
        self._save_sd.exec_()

# ----------------------------------------------------------------------------------------------------------------------
# Slots for the camera dockwidget and its associated toolbar and menu actions
# ----------------------------------------------------------------------------------------------------------------------

# updating elements on the camera dockwidget ---------------------------------------------------------------------------
    @QtCore.Slot(float)
    def update_exposure(self, exposure):
        """ Updates the displayed value of exposure time in the corresponding read-only lineedit.
        Indicates the kinetic time instead of the user defined exposure time in case of andor camera.
        @param: float exposure
        @return: None
        """
        # indicate the kinetic time instead of the exposure time for andor ixon camera
        if (self._camera_logic.get_name() == 'iXon Ultra 897') or (self._camera_logic.get_name() == 'iXon Ultra 888'):
            self._mw.exposure_LineEdit.setText('{:0.5f}'.format(self._camera_logic.get_kinetic_time()))
        else:
            self._mw.exposure_LineEdit.setText('{:0.5f}'.format(exposure))

    @QtCore.Slot(float)
    def update_gain(self, gain):
        """ Updates the read-only lineedit showing the applied gain.
        @param: float gain
        @return: None
        """
        self._mw.gain_LineEdit.setText(str(gain))

    @QtCore.Slot(float)
    def update_temperature(self, temp):
        """ Updates the read-only lineedit showing the current sensor temperature.
        @param: float temperature
        @return: None
        """
        self._mw.temperature_LineEdit.setText(str(temp))

    @QtCore.Slot(str)
    def update_sample_name(self, samplename):
        """ Updates the folder name lineedit in the save settings dialog when the sample name on the gui was modified.
        @param: str samplename
        @return: None
        """
        self._save_sd.foldername_LineEdit.setText(samplename)

    @QtCore.Slot()
    def load_saving_path_clicked(self):
        """ Callback of select_folder_pushButton. Opens a dialog to select the complete path to the folder where the
        data will be saved.
        """
        default_path = self._mw.save_path_LineEdit.text()
        this_dir = QtWidgets.QFileDialog.getExistingDirectory(self._mw, 'Select saving directory', default_path)
        if this_dir:
            self._mw.save_path_LineEdit.setText(this_dir)

    @QtCore.Slot()
    def update_data(self):
        """ Callback of sigUpdateDisplay in the camera_logic module.
        Get the image data from the logic and show it in the image item.
        """
        image_data = self._camera_logic.get_last_image()
        # handle the rotation that occurs due to the image formatting conventions
        # (see also https://github.com/pyqtgraph/pyqtgraph/issues/315)
        # this could be improved by another method ?! though reversing the y axis did not work.
        image_data = np.rot90(image_data, 3)  # 90 deg clockwise

        # handle the user defined rotation settings
        if self.rotation_cw:
            image_data = np.rot90(image_data, 3)
        if self.rotation_ccw:
            image_data = np.rot90(image_data, 1)  # eventually replace by faster rotation method T and invert
        if self.rot180:
            image_data = np.rot90(image_data, 2)
        self.imageitem.setImage(image_data.T)
        # transposing the data makes the rotations behave as they should when axisOrder row-major is used (set in
        # initialization of ImageItem). See also https://github.com/pyqtgraph/pyqtgraph/issues/315

# camera dockwidget toolbar --------------------------------------------------------------------------------------------
    @QtCore.Slot()
    def take_image_clicked(self):
        """ Callback of take_image_Action (take and display a single image, without saving).
        Emits a signal that is connected to the logic module, and disables the tool buttons.
        """
        self.sigImageStart.emit()
        self.disable_camera_toolbuttons()
        self.imageitem.getViewBox().rbScaleBox.hide()  # hide the rubberband tool used for roi selection on sensor

    @decorator_print_function
    @QtCore.Slot()
    def acquisition_finished(self):
        """ Callback of sigAcquisitionFinished. Resets all tool buttons to callable state.
        """
        self._mw.take_image_Action.setChecked(False)
        self.enable_camera_toolbuttons()

    @QtCore.Slot()
    def start_video_clicked(self):
        """ Callback of start_video_Action. (start and display a continuous image from the camera, without saving)
        Handles the state of the start button and emits a signal (connected to logic) to start the live loop.
        """
        if self._camera_logic.live_enabled:  # video already running
            self._mw.take_image_Action.setDisabled(False)  # snap and live are mutually exclusive
            self._mw.start_video_Action.setText('Live')
            self._mw.start_video_Action.setToolTip('Start live video')
            self.sigVideoStop.emit()
        else:
            self._mw.take_image_Action.setDisabled(True)  # snap and live are mutually exclusive
            self._mw.start_video_Action.setText('Stop Live')
            self._mw.start_video_Action.setToolTip('Stop live video')
            self.sigVideoStart.emit()
        self.imageitem.getViewBox().rbScaleBox.hide()  # hide the rubberband tool used for roi selection on sensor

    @QtCore.Slot()
    def reset_start_video_button(self):
        """ Callback of the signal sigLiveStopped from logic, emitted when live mode is programmatically stopped
        (for example to prepare a task). """
        self._mw.start_video_Action.setText('Live')
        self._mw.start_video_Action.setToolTip('Start live video')
        self._mw.start_video_Action.setChecked(False)

    @QtCore.Slot()
    def save_last_image_clicked(self):
        """ Callback of save_last_image_Action.
        Saves the last image (the one currently displayed on the image widget), using the following format
        (analogously to video saving procedures)
        images are saved to:
        filenamestem/num_type/file.tiff
        example: /home/barho/images/2020-12-16/samplename/000_Image/image.tif
        filenamestem is generated below, example /home/barho/images/2020-12-16/foldername
        folder_name is taken from the field on GUI.
        num_type is an incremental number followed by _Image
        """
        # save data
        default_path = self._mw.save_path_LineEdit.text()
        today = datetime.today().strftime('%Y_%m_%d')
        folder_name = self._mw.samplename_LineEdit.text()
        filenamestem = os.path.join(default_path, today, folder_name)
        metadata = self._create_metadata_dict(1)
        self._camera_logic.save_last_image(filenamestem, metadata)

    @QtCore.Slot()
    def abort_video_clicked(self):
        """ Callback of abort_video_Action. Handles toolbutton state and allow the use to stop an acquisition before
        its end.
        """
        self._camera_logic.acquisition_aborted = True
        self._aborted = True

    @QtCore.Slot()
    def save_video_clicked(self):
        """ Callback of save_video_Action. Handles toolbutton state, and opens the save settings dialog. Note that two
        acquisition modes are available, depending on the type of cameras. Spooling only exists for Andor.
        """
        # disable camera related toolbuttons
        self.disable_camera_toolbuttons()
        # set the flag to True so that the dialog knows that is was called from save video button
        if (self._camera_logic.get_name() == 'iXon Ultra 897') or (self._camera_logic.get_name() == 'iXon Ultra 888'):
            self._spooling = True
        else:
            self._video = True
        # open the save settings window
        self.open_save_settings()
        # hide the rubberband tool used for roi selection on sensor
        self.imageitem.getViewBox().rbScaleBox.hide()

    @QtCore.Slot()
    def video_quickstart_clicked(self):
        """ Callback of video quickstart action
        (uses last parameters written in the settings dialog which will not be opened again).
        Handles toolbutton state and calls the save_video_accepted method. """
        # disable camera related toolbuttons
        self.disable_camera_toolbuttons()
        # decide depending on camera which signal has to be emitted in save_video_accepted method
        # same approach can later be used to regroup save_video and save_long_video buttons into one action. Note that
        # display does not work properly in spooling mode (at least for the 888 model). Therefore, when display is ON,
        # the camera will acquire is video mode.
        display = self._save_sd.enable_display_CheckBox.isChecked()
        if (self._camera_logic.get_name() == 'iXon Ultra 897') or (self._camera_logic.get_name() == 'iXon Ultra 888'):
            if display:
                self._video = True
            else:
                self._spooling = True
        else:
            self._video = True
        self.save_video_accepted()

    @decorator_print_function
    @QtCore.Slot()
    def video_saving_finished(self):
        """ Callback of signal sigVideoSavingFinished or sigSpoolingFinished sent from logic.
        Resets the toolbuttons to callable state and clears up the flag and statusbar.
        """
        # reset the flags
        self._video = False
        self._spooling = False
        # # toolbuttons
        # self.enable_camera_toolbuttons()
        # self._mw.save_video_Action.setChecked(False)
        # # clear the statusbar
        # self._mw.progress_label.setText('')

    @QtCore.Slot()
    @decorator_print_function
    def select_sensor_region(self):
        """ Callback of set_sensor_Action.
        Enables or disables (according to initial state) the rubberband selection tool on the camera image. """
        # area selection initially off
        if not self.region_selector_enabled:
            self._mw.camera_ScanPlotWidget.toggle_selection(True)
            self.region_selector_enabled = True
            self._mw.set_sensor_Action.setText('Reset sensor to default size')
        else:  # area selection is initially on:
            self._mw.camera_ScanPlotWidget.toggle_selection(False)
            self.reset_sensor_region()
            self.region_selector_enabled = False
            self._mw.set_sensor_Action.setText('Set sensor region')

            # # Recalculate the camera settings (in particular the exposure time) according to the new size of the FoV
            # self.cam_update_settings()

    def reset_sensor_region(self):
        """ Reset the sensor to its default size
        """
        exposure_time = self._cam_sd.exposure_doubleSpinBox.value()
        live_enabled = self._camera_logic.live_enabled

        # if live acquisition, stop the live in order to update the parameters
        if live_enabled:
            self.sigVideoStop.emit()
            sleep(1)

        # reset the sensor to its original size
        self.sigResetSensor.emit(exposure_time)

        # if the camera was in live mode, launch it again
        if live_enabled:
            self.sigVideoStart.emit()
            self.imageitem.getViewBox().rbScaleBox.hide()

    @QtCore.Slot(QtCore.QRectF)
    @decorator_print_function
    def mouse_area_selected(self, rect):
        """ This slot is called when the user has selected an area of the camera image using the rubberband tool.
        Allows to reduce the used area of the camera sensor.
        @param: (QRectF) rect: Qt object defining the corners of a rectangle selected in an image item.
        """
        exposure_time = self._cam_sd.exposure_doubleSpinBox.value()
        live_enabled = self._camera_logic.live_enabled

        # read the coordinates of the selected region
        hstart, vstart, hend, vend = rect.getCoords()
        hstart = round(hstart)
        vstart = round(vstart)
        hend = round(hend)
        vend = round(vend)
        # order the values so that they can be used as arguments for the set_sensor_region function
        hstart_ = min(hstart, hend)
        hend_ = max(hstart, hend)
        vstart_ = min(vstart, vend)
        vend_ = max(vstart, vend)
        self.log.info('hstart={}, hend={}, vstart={}, vend={}'.format(hstart_, hend_, vstart_, vend_))
        # inversion along the y axis:
        # it is needed to call the function set_sensor_region(hbin, vbin, hstart, hend, vstart, vend)
        # using the following arguments: set_sensor_region(hbin, vbin, start, hend, num_px_y - vend, num_px_y - vstart)
        # ('vstart' needs to be smaller than 'vend')
        num_px_y = self._camera_logic.get_max_size()[1]  # height is stored in the second return value of get_size

        # if live acquisition, stop the live in order to update the parameters
        if live_enabled:
            self.sigVideoStop.emit()
            sleep(1)

        # update the new sensor size
        self.sigSetSensor.emit(1, 1, hstart_, hend_, num_px_y - vend_, num_px_y - vstart_, exposure_time)

        # if the camera was in live mode, launch it
        if live_enabled:
            self.sigVideoStart.emit()
            self.imageitem.getViewBox().rbScaleBox.hide() # hide rubberband selector directly

        # # Recalculate the camera settings (in particular the exposure time) according to the new size of the FoV
        # self.cam_update_settings()

# menubar options belonging to camera image ---------------------------------------------------------------------------
    @QtCore.Slot()
    def rotate_image_cw_toggled(self):
        """ Callback of the rotate image 90 deg clockwise menu action. """
        if self.rotation_cw:  # rotation is already applied. Toggle button has just been unchecked by user
            self.rotation_cw = False
        else:  # rotation not yet applied. Toggle button has just been checked by user
            self.rotation_cw = True
            # automatically uncheck the rotate ccw and rotate 180deg button (make them mutually exclusive)
            self._mw.rotate_image_ccw_MenuAction.setChecked(False)
            self._mw.rot180_image_MenuAction.setChecked(False)
            self.rotation_ccw = False
            self.rot180 = False

    @QtCore.Slot()
    def rotate_image_ccw_toggled(self):
        """ Callback of the rotate image 90 deg counter clockwise menu action. """
        if self.rotation_ccw:  # rotation is already applied. Toggle button has just been unchecked by user
            self.rotation_ccw = False
        else:  # rotation not yet applied. Toggle button has just been checked by user
            self.rotation_ccw = True
            # automatically uncheck the rotate cw button and rotate 180deg button (make them mutually exclusive)
            self._mw.rotate_image_cw_MenuAction.setChecked(False)
            self._mw.rot180_image_MenuAction.setChecked(False)
            self.rotation_cw = False
            self.rot180 = False

    @QtCore.Slot()
    def rot180_image_toggled(self):
        """ Callback of the rotate image 180 deg menu action. """
        if self.rot180:  # rotation is already applied. Toggle button has just been unchecked by user
            self.rot180 = False
        else:  # rotation not yet applied. Toggle button has just been checked by user
            self.rot180 = True
            # automatically uncheck the rotate cw button and rotate 180deg button (make them mutually exclusive)
            self._mw.rotate_image_cw_MenuAction.setChecked(False)
            self._mw.rotate_image_ccw_MenuAction.setChecked(False)
            self.rotation_cw = False
            self.rotation_ccw = False

# statusbar ------------------------------------------------------------------------------------------------------------
    @QtCore.Slot(int)
    def update_statusbar(self, number_images):
        """ Callback of sigProgress sent by logic. Displays the integer value indicating how many images were already
        acquired in the field in the statusbar.

        :param: int number_images: number of images already acquired
        :return: None
        """
        # total = self._save_sd.n_frames_SpinBox.value()
        # progress = number_images / total * 100
        # try first with the simple version, maybe use later rescaling in %
        self._mw.progress_label.setText('{} images saved'.format(number_images))
        
    @QtCore.Slot()
    def update_statusbar_saving(self):
        """ Callback of sigSaving sent by logic. Displays the text 'Saving...' in the status bar. """
        self._mw.progress_label.setText('Saving..')

    @QtCore.Slot()
    def clean_statusbar(self):
        """ Callback of sigCleanStatusbar sent by logic. Reset the status bar text to default after saving is finished.
        """
        self._mw.progress_label.setText('')

# handle the state of toolbuttons / disable & enable user interface actions --------------------------------------------
    @decorator_print_function
    def reset_toolbuttons(self):
        """ This slot is called when save dialog is canceled.

        Sets the camera toolbuttons to callable state, and unchecks the save video action button. """
        self.enable_camera_toolbuttons()
        self._mw.save_video_Action.setChecked(False)

    @decorator_print_function
    def disable_camera_toolbuttons(self):
        """ Disables all toolbuttons of the camera toolbar. """
        self._mw.take_image_Action.setDisabled(True)
        self._mw.start_video_Action.setDisabled(True)
        self._mw.save_last_image_Action.setDisabled(True)
        self._mw.save_video_Action.setDisabled(True)
        self._mw.video_quickstart_Action.setDisabled(True)
        self._mw.set_sensor_Action.setDisabled(True)
        self._mw.abort_video_Action.setDisabled(False)
        self._mw.abort_video_Action.setChecked(False)

    def disable_frame_transfer(self):
        """ Disables the frame transfer checkbox. """
        self._cam_sd.frame_transfer_CheckBox.setChecked(False)

    @decorator_print_function
    def enable_camera_toolbuttons(self):
        """
        Enables all toolbuttons of the camera toolbar. Serves also as callback of SigVideoFinished.
        """
        if not self._camera_logic.live_enabled:  # do not reset to active state if live mode is on
            self._mw.take_image_Action.setDisabled(False)
        self._mw.start_video_Action.setDisabled(False)
        self._mw.save_last_image_Action.setDisabled(False)
        self._mw.save_video_Action.setDisabled(False)
        self._mw.video_quickstart_Action.setDisabled(False)
        self._mw.set_sensor_Action.setDisabled(False)
        self._mw.abort_video_Action.setDisabled(True)
        self._mw.abort_video_Action.setChecked(False)

# helper functions -----------------------------------------------------------------------------------------------------
    def _create_metadata_dict(self, n_frames):
        """ create a dictionary containing the metadata.
        @param: (int) number of frames required for the acquisition
        @return: (dict) metadata
        """
        metadata = self.metadata_template
        # ----general----------------------------------------------------------------------------
        metadata['Time'] = datetime.now().strftime('%m-%d-%Y, %H:%M:%S')

        # ----camera-----------------------------------------------------------------------------
        metadata = update_metadata(metadata, ['Acquisition', 'number_frames'], n_frames)
        folder_name = self._save_sd.foldername_LineEdit.text()
        metadata = update_metadata(metadata, ['Acquisition', 'sample_name'], folder_name)
        metadata = update_metadata(metadata, ['Acquisition', 'exposure_time_(s)'], self._camera_logic.get_exposure())
        if (self._camera_logic.get_name() == 'iXon Ultra 897') or (self._camera_logic.get_name() == 'iXon Ultra 888'):
            metadata = update_metadata(metadata, ['Acquisition', 'kinetic_time_(s)'],
                                       self._camera_logic.get_kinetic_time())
            parameters = self._camera_logic.get_non_interfaced_parameters()
            for key, value in parameters.items():
                metadata = update_metadata(metadata, ['Camera', 'specific_parameters', key], value)
        metadata = update_metadata(metadata, ['Acquisition', 'gain'], self._camera_logic.get_gain())
        if self._camera_logic.has_temp:
            self.sigReadTemperature.emit()  # short interruption of live mode to read temperature
            metadata = update_metadata(metadata, ['Acquisition', 'sensor_temperature_setpoint_(°C)'],
                                       self._camera_logic.get_temperature())
        else:
            metadata = update_metadata(metadata, ['Acquisition', 'sensor_temperature_setpoint_(°C)'],
                                       "Not available")

        # ----filter------------------------------------------------------------------------------
        filterpos = self._filterwheel_logic.get_position()
        filterdict = self._filterwheel_logic.get_filter_dict()
        label = 'filter{}'.format(filterpos)
        metadata = update_metadata(metadata, ['Acquisition', 'filter'], filterdict[label]['name'])

        # ----laser-------------------------------------------------------------------------------
        intensity_dict = self._laser_logic._intensity_dict
        keylist = [key for key in intensity_dict if intensity_dict[key] != 0]
        laser_dict = self._laser_logic.get_laser_dict()
        for key in keylist:
            metadata = update_metadata(metadata, ['Acquisition', 'laser_lines'], laser_dict[key]['wavelength'],
                                       action="append")
            metadata = update_metadata(metadata, ['Acquisition', 'laser_power_(%)'], intensity_dict[key],
                                       action="append")
        # if not metadata['Acquisition']['laser_lines']:  # for compliance with fits header conventions ([] is forbidden)
        #     metadata['Acquisition']['laser_lines'] = None
        # if not metadata['Acquisition']['laser_power_(%)']:
        #     metadata['Acquisition']['laser_power_(%)'] = None

        return metadata

# ----------------------------------------------------------------------------------------------------------------------
# Slots for the camera status dockwidget
# ----------------------------------------------------------------------------------------------------------------------

    @QtCore.Slot(str, str, str, str)  # temperature already converted into str
    def update_camera_status_display(self, ready_state, shutter_state='', cooler_state='', temperature=''):
        """ Updates the indicators in the camera status dockwidget using the information retrieved by the logic module.
        """
        self._mw.camera_status_LineEdit.setText(ready_state)
        self._mw.shutter_status_LineEdit.setText(shutter_state)
        self._mw.cooler_status_LineEdit.setText(cooler_state)
        self._mw.temperature_LineEdit.setText(temperature)

# ----------------------------------------------------------------------------------------------------------------------
# Slots for the laser dockwidget
# ----------------------------------------------------------------------------------------------------------------------

# toolbar --------------------------------------------------------------------------------------------------------------
    @QtCore.Slot()
    def laser_on_clicked(self):
        """ Callback of laser_on_Action.
        Handles the state of the toolbutton and emits a signal that is connected to the physical output.
        Handles also the state of the filter selection combobox to avoid changing filter while lasers are on.
        """
        if self._laser_logic.enabled:
            # laser is initially on
            self._mw.laser_on_Action.setText('Laser On')
            self.sigLaserOff.emit()
            # enable filter setting again
            self._mw.filter_ComboBox.setEnabled(True)
        else:
            # laser is initially off
            self._mw.laser_on_Action.setText('Laser Off')
            self.sigLaserOn.emit()
            # do not change filters while laser is on
            self._mw.filter_ComboBox.setEnabled(False)

    @QtCore.Slot()
    def laser_set_to_zero(self):
        """ Callback of laser_zero_Action.
        """
        for item in self.laser_DSpinBoxes:
            item.setValue(0)
        # also set brightfield control to zero in case it is available
        if self.brightfield_control:
            self.bf_control_DSpinBox.setValue(0)

    @QtCore.Slot()
    def brightfield_on_clicked(self):
        """ Callback of brightfield_on_Action.
        Handles the state of the toolbutton and emits a signal that is in turn connected to the physical output.
        """
        if self._brightfield_logic.enabled:
            # brightfield is initially on
            self.brightfield_on_Action.setText('Brightfield On')
            self.sigBFOff.emit()
        else:
            # brightfield is initially off
            self.brightfield_on_Action.setText('Brightfield Off')
            intensity = self.bf_control_DSpinBox.value()
            self.sigBFOn.emit(intensity)

# callbacks of signals from logic --------------------------------------------------------------------------------------
    def update_laser_spinbox(self):
        """ Update values in laser spinboxes if the intensity dictionary in the logic module was changed """
        for index, item in enumerate(self.laser_DSpinBoxes):
            label = 'laser'+str(index + 1)  # create the label to address the corresponding laser
            item.setValue(self._laser_logic._intensity_dict[label])

    @QtCore.Slot()
    def reset_laser_toolbutton(self):
        """ Callback of the signal sigLaserStopped from logic, emitted when laser output is programmatically stopped
        (for example to prepare a task). """
        self._mw.laser_on_Action.setText('Laser On')
        self._mw.laser_on_Action.setChecked(False)
        # enable filter setting again
        self._mw.filter_ComboBox.setEnabled(True)

    @QtCore.Slot()
    def reset_brightfield_toolbutton(self):
        """ Callback of the signal sigBrightfieldStopped from brightfield logic,
        emitted when brightfield output is programmatically stopped
        (for example to prepare a task). """
        self.brightfield_on_Action.setText('Brightfield On')
        self.brightfield_on_Action.setChecked(False)

# disable/enable user interface actions --------------------------------------------------------------------------------
    @QtCore.Slot()
    def disable_laser_toolbuttons(self):
        """ disables all toolbuttons of the laser toolbar"""
        self._mw.laser_on_Action.setDisabled(True)
        self._mw.laser_zero_Action.setDisabled(True)
        if self.brightfield_control:
            self.brightfield_on_Action.setDisabled(True)

    @QtCore.Slot()
    def enable_laser_toolbuttons(self):
        """ enables all toolbuttons of the camera toolbar"""
        self._mw.laser_on_Action.setDisabled(False)
        self._mw.laser_zero_Action.setDisabled(False)
        if self.brightfield_control:
            self.brightfield_on_Action.setDisabled(False)

# ----------------------------------------------------------------------------------------------------------------------
# Slots for the filter dockwidget
# ----------------------------------------------------------------------------------------------------------------------

    def init_filter_selection(self):
        """ Initializes the filter selection combobox with the available filters.
        """
        filter_dict = self._filterwheel_logic.filter_dict
        for key in filter_dict:
            text = str(filter_dict[key]['position'])+': '+filter_dict[key]['name']
            self._mw.filter_ComboBox.addItem(text)

        # set the active filter position in the list
        current_filter_position = self._filterwheel_logic.get_position()  # returns an int: position
        index = current_filter_position - 1  # zero indexing
        self._mw.filter_ComboBox.setCurrentIndex(index)

        # disable the laser control spinboxes of lasers that are not allowed to be used with the selected filter
        key = 'filter'+str(current_filter_position)  # create key which allows to access the corresponding entry in the filter_dict
        self._disable_laser_control(self._filterwheel_logic.filter_dict[key]['lasers'])  # get the corresponding bool list from the logic module

    def change_filter(self):
        """ Slot connected to the filter selection combobox. It sends the (int) number of the selected filter to the
        filterwheel logic. Triggers also the deactivation of forbidden laser control spinboxes for the given filter.
        """
        # get current index of the filter selection combobox
        index = self._mw.filter_ComboBox.currentIndex()
        filter_pos = index + 1  # zero indexing
        self.sigFilterChanged.emit(filter_pos)

        # disable the laser control spinboxes of lasers that are not allowed to be used with the selected filter
        key = 'filter'+str(filter_pos)  # create key which allows to access the corresponding entry in the filter_dict
        self._disable_laser_control(self._filterwheel_logic.filter_dict[key]['lasers'])  # get the corresponding bool list from the logic module

    def update_filter_display(self, position):
        """ Refresh the Combobox entry to ensure that after manually modifying the filter
        (for example using the iPython console) the GUI displays the correct filter.
        """
        index = position - 1  # zero indexing
        self._mw.filter_ComboBox.setCurrentIndex(index)

    def _disable_laser_control(self, bool_list):        
        """ Disables the control spinboxes of the lasers which are not allowed for a given filter
        
        :param: bool_list: list with entries corresponding to laser1 - laserN [True False True False ... True] means
        that Laser1, laser3 and laserN are allowed, laser2 and laser4 are forbidden.
        
        :return: None
        """
        for i in range(len(self.laser_DSpinBoxes)):
            self.laser_DSpinBoxes[i].setEnabled(bool_list[i])

# disable/enable user interface actions --------------------------------------------------------------------------------
    @QtCore.Slot()
    def disable_filter_selection(self):
        """ Disables filter combobox (for example as safety during tasks). """
        self._mw.filter_ComboBox.setDisabled(True)
        sleep(0.5)

    @QtCore.Slot()
    def enable_filter_selection(self):
        """ Enables filter combobox. """
        self._mw.filter_ComboBox.setDisabled(False)
        sleep(0.5)

# ----------------------------------------------------------------------------------------------------------------------
# Close function: Stop all continuous actions.
# ----------------------------------------------------------------------------------------------------------------------

    def close_function(self):
        """ This method serves as a reimplementation of the close event. Continuous modes (such as camera live,
        laser on, etc. are stopped) when the main window is closed. """
        # stop live mode when window is closed
        if self._camera_logic.live_enabled:
            self.start_video_clicked()
            self.reset_start_video_button()
        # switch laser off when window is closed
        if self._laser_logic.enabled:
            self._laser_logic.voltage_off()
            self.reset_laser_toolbutton()
        # switch brightfield off when window is closed
        if self.brightfield_control:
            if self._brightfield_logic.enabled:
                self._brightfield_logic.led_off()
                self.reset_brightfield_toolbutton()
