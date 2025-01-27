# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains the ROI selection user interface.
It is inspired by the Qudi poimanager gui.

It would be a nice idea to have camera images superposed with the ROI markers.
In this version, everything camera image related has been commented out.

An extension to Qudi.

@author: F. Barho

Created on Thu Nov 5 2020
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
import os
import pyqtgraph as pg
import re

from core.connector import Connector
from core.util.units import ScaledFloat
from core.util.helpers import natural_sort
from gui.guibase import GUIBase
from qtpy import QtCore, QtGui
from qtpy import QtWidgets
from qtpy import uic
from qtwidgets.scan_plotwidget import ScanImageItem
from core.configoption import ConfigOption
from gui.validators import NameValidator


# ======================================================================================================================
# Classes for the ROI and stage markers
# ======================================================================================================================

# Class representing the marker.  # adapted from POI manager module of Qudi.
class RoiMarker(pg.RectROI):
    """
    Creates a square as marker.

    @param float[2] pos: The (x, y) position of the ROI.
    @param **args: All extra keyword arguments are passed to ROI()

    Have a look at:
    http://www.pyqtgraph.org/documentation/graphicsItems/roi.html
    """
    default_pen = {'color': '#FFFFFF', 'width': 2}  # white color as default
    select_pen = {'color': '#22FF33', 'width': 2}  # colored frame is the active one

    sigRoiSelected = QtCore.Signal(str)

    def __init__(self, position, width, roi_name=None, view_widget=None, **kwargs):
        """
        @param position:
        @param width:
        @param roi_name:
        @param view_widget:
        @param kwargs:
        """
        self._roi_name = '' if roi_name is None else roi_name
        self._view_widget = view_widget
        self._selected = False
        self._position = np.array(position, dtype=float)

        size = (width, width)
        super().__init__(pos=self._position, size=size, pen=self.default_pen, **kwargs)
        self.aspectLocked = True
        self.label = pg.TextItem(text=self._roi_name,
                                 anchor=(0, 1),
                                 color=self.default_pen['color'])
        self.setAcceptedMouseButtons(QtCore.Qt.LeftButton)
        self.sigClicked.connect(self._notify_clicked_roi_name)
        self.set_position(self._position)
        return

    def _addHandles(self):
        pass

    @property
    def width(self):
        return self.size()[0]

    @property
    def selected(self):
        return bool(self._selected)

    @property
    def roi_name(self):
        return str(self._roi_name)

    @property
    def position(self):
        return self._position

    @QtCore.Slot()
    def _notify_clicked_roi_name(self):
        self.sigRoiSelected.emit(self._roi_name)

    def add_to_view_widget(self, view_widget=None):
        if view_widget is not None:
            self._view_widget = view_widget
        self._view_widget.addItem(self)
        self._view_widget.addItem(self.label)
        return

    def delete_from_view_widget(self, view_widget=None):
        if view_widget is not None:
            self._view_widget = view_widget
        self._view_widget.removeItem(self.label)
        self._view_widget.removeItem(self)
        return

    def set_position(self, position):
        """
        Sets the ROI position and center the marker on that position.
        Also position the label accordingly.

        @param float[2] position: The (x,y) center position of the ROI marker
        """
        self._position = np.array(position, dtype=float)
        width = self.width
        label_offset = width / 2
        self.setPos(self._position[0] - width / 2, self._position[
            1] - width / 2)  # check if the origin is at the lower left corner, then this should be correct, else to be modified !!!
        self.label.setPos(self._position[0] + label_offset, self._position[1] + label_offset)
        return

    def set_name(self, name):
        """
        Set the roi_name of the marker and update tha label accordingly.

        @param str name:
        """
        self._roi_name = name
        self.label.setText(self._roi_name)
        return

    def set_width(self, width):
        """
        Set the size of the marker and reposition itself and the label to center it again.

        @param float width: Width of the square 
        """
        label_offset = width / 2  # to adjust
        self.setSize((width, width))
        self.setPos(self.position[0] - width / 2, self.position[1] - width / 2)
        self.label.setPos(self.position[0] + label_offset, self.position[1] + label_offset)
        return

    def select(self):
        """
        Set the markers _selected flag to True and change the marker appearance according to
        RoiMarker.select_pen.
        """
        self._selected = True
        self.setPen(self.select_pen)
        self.label.setColor(self.select_pen['color'])
        return

    def deselect(self):
        """
        Set the markers _selected flag to False and change the marker appearance according to
        RoiMarker.default_pen.
        """
        self._selected = False
        self.setPen(self.default_pen)
        self.label.setColor(self.default_pen['color'])
        return


# class representing the marker for the current stage position
class StageMarker(pg.RectROI):
    """
    Creates a square as marker for the stage.

    @param float[2] pos: The (x, y) position of the stage center.
    @param **args: All extra keyword arguments are passed to ROI()

    Have a look at:
    http://www.pyqtgraph.org/documentation/graphicsItems/roi.html
    """
    default_pen = {'color': '#00FFFF', 'width': 2}  # color settings

    def __init__(self, position, width, view_widget=None, **kwargs):
        """
        @param position:
        @param width:
        @param view_widget:
        @param kwargs:
        """
        self._view_widget = view_widget
        self._position = np.array(position, dtype=float)
        size = (width, width)
        super().__init__(pos=self._position, size=size, pen=self.default_pen, **kwargs)
        self.aspectLocked = True
        self.label = pg.TextItem(text='Stage',
                                 anchor=(0, 1),
                                 color=self.default_pen['color'])
        self.setAcceptedMouseButtons(QtCore.Qt.LeftButton)
        self.set_position(self._position)
        return

    @property
    def width(self):
        return self.size()[0]

    @property
    def position(self):
        return self._position

    def add_to_view_widget(self, view_widget=None):
        if view_widget is not None:
            self._view_widget = view_widget
        self._view_widget.addItem(self)
        self._view_widget.addItem(self.label)
        return

    def delete_from_view_widget(self, view_widget=None):
        if view_widget is not None:
            self._view_widget = view_widget
        self._view_widget.removeItem(self.label)
        self._view_widget.removeItem(self)
        return

    def set_position(self, position):
        """
        Sets the position and centers the marker on that position.
        Also positions the label accordingly.

        @param float[2] position: The (x,y) center position of the stage marker
        """
        self._position = np.array(position, dtype=float)
        width = self.width
        label_offset = 0
        self.setPos(self._position[0] - width / 2,
                    self._position[1] - width / 2)  # draw the marker from the lower left corner of the square
        self.label.setPos(self._position[0] + label_offset, self._position[1] + label_offset)
        return

    def set_width(self, width):
        """
        Set the size of the marker and reposition itself and the label to center it again.

        @param float width: Width of the square
        """
        label_offset = 0
        self.setSize((width, width))
        self.setPos(self.position[0] - width / 2, self.position[1] - width / 2)
        self.label.setPos(self.position[0] + label_offset, self.position[1] + label_offset)
        return


# ======================================================================================================================
# Classes for the dialog windows and main window
# ======================================================================================================================

class MosaicSettingDialog(QtWidgets.QDialog):
    """ Create the MosaicSettingsDialog window, based on the corresponding *.ui file."""
    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_mosaic_settings.ui')

        # Load it
        super(MosaicSettingDialog, self).__init__()
        uic.loadUi(ui_file, self)


class RoiMainWindow(QtWidgets.QMainWindow):
    """ Create the Mainwindow from the ui.file
    """
    def __init__(self):
        # Get the path to the *.ui file
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'ui_roi_gui.ui')

        # Load it
        super(RoiMainWindow, self).__init__()
        uic.loadUi(ui_file, self)
        self.show()


class RoiMainWindowCE(RoiMainWindow):
    """ RoiMainWindow child class that allows to stop the tracking mode when window is closed. """
    def __init__(self, close_function):
        super().__init__()
        self.close_function = close_function

    def closeEvent(self, event):
        self.close_function()
        event.accept()


# ======================================================================================================================
# GUI class
# ======================================================================================================================

class RoiGUI(GUIBase):
    """ This is the GUI Class for Roi selection.

    Example config for copy-paste:

    ROI Selector:
        module.Class: 'ROI.roi_gui.RoiGUI'
        default_path: '/home/barho/qudi_files/qudi_roi_lists'
        stagemarker_width: 50  # in um
        connect:
            roi_logic: 'roi_logic'
    """
    # declare connector to logic module
    roi_logic = Connector(interface='RoiLogic')
    
    # config options
    default_path = ConfigOption('default_path', missing='warn')
    stagemarker_width = ConfigOption('stagemarker_width', 50, missing='info')  # stagemarker width in um

    # signals
    sigRoiWidthChanged = QtCore.Signal(float)
    sigRoiFirstDigitChanged = QtCore.Signal(float)
    sigRoiListNameChanged = QtCore.Signal(str)
    sigStartTracking = QtCore.Signal()
    sigStopTracking = QtCore.Signal()
    sigAddInterpolation = QtCore.Signal(float)

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

        self._mw = None  # QMainWindow handle
        self._roi_logic = None
        self.roi_image = None  # ScanPlotImage (custom child of pyqtgraph PlotImage) for ROI overview image
        self._markers = {}  # dict to hold handles for the ROI markers
        self._mouse_moved_proxy = None  # Signal proxy to limit mousMoved event rate
        self.stagemarker = None
        self._mosaic_sd = None

    def on_activate(self):
        """
        Initializes the overall GUI, and establishes the connectors.
        """
        self._roi_logic = self.roi_logic()

        self._mw = RoiMainWindowCE(self.close_function)
        self._markers = {}

        # set the default save path before validator is applied: make sure that config is correct
        self._mw.save_path_LineEdit.setText(self.default_path)

        # Add validator to LineEdits
        self._mw.roi_list_name_LineEdit.setValidator(NameValidator())
        # self._mw.save_path_LineEdit.setValidator(NameValidator(path=True))  # to reactivate later !!!!!!!

        # Initialize plot
        self.__init_roi_map_image()

        # Initialize ROIs
        self._update_rois(self._roi_logic.roi_positions)
        # Initialize ROI list name
        self._update_roi_list_name(self._roi_logic.roi_list_name)
        # Initialize ROI width
        self._update_roi_width(self._roi_logic.roi_width)

        # add the stage marker and update the ROI width according to the value indicated in the parameters
        stage_pos = self._roi_logic.stage_position[:2]
        self._add_stage_marker(stage_pos)
        self._update_roi_width(self.stagemarker_width)
        self._roi_logic.set_roi_width(self.stagemarker_width)

        # Distance Measurement:
        # Introducing a SignalProxy will limit the rate of signals that get fired.
        self._mouse_moved_proxy = pg.SignalProxy(signal=self.roi_image.scene().sigMouseMoved,
                                                 rateLimit=30,
                                                 slot=self.mouse_moved_callback)

        # place this here so that the initialized values can be retrieved for the mosaic dialog
        self.init_mosaic_settings_ui()  # initialize the Mosaic settings window in the options menu
        
        # Connect signals
        self.__connect_internal_signals()
        self.__connect_update_signals_from_logic()
        self.__connect_control_signals_to_logic()

        self._mw.show()

    def on_deactivate(self):
        """
        De-initialisation performed during deactivation of the module.
        """
        self.__disconnect_control_signals_to_logic()
        self.__disconnect_update_signals_from_logic()
        self.__disconnect_internal_signals()
        self.close_function()

# ----------------------------------------------------------------------------------------------------------------------
# Helper methods called during activation / deactivation
# ----------------------------------------------------------------------------------------------------------------------

    def __init_roi_map_image(self):
        """ Initialize the ROI map. """
        self.roi_image = ScanImageItem(axisOrder='row-major')
        self._mw.roi_map_ViewWidget.addItem(self.roi_image)
        self._mw.roi_map_ViewWidget.setLabel('bottom', 'x position')  # units='um'  check units ..
        self._mw.roi_map_ViewWidget.setLabel('left', 'y position')  # , units='um
        self._mw.roi_map_ViewWidget.setAspectLocked(lock=True, ratio=1.0)
        # # Get camera image from logic and update initialize plot
        # self._update_cam_image(self._roi_logic.roi_list_cam_image, self._roi_logic.roi_list_cam_image_extent)

    def __connect_update_signals_from_logic(self):
        """ Establish the connections of signals emitted in logic module
        """
        self._roi_logic.sigRoiUpdated.connect(self.update_roi, QtCore.Qt.QueuedConnection)
        self._roi_logic.sigActiveRoiUpdated.connect(self.update_active_roi, QtCore.Qt.QueuedConnection)
        self._roi_logic.sigRoiListUpdated.connect(self.update_roi_list, QtCore.Qt.QueuedConnection)
        self._roi_logic.sigWidthUpdated.connect(self._update_roi_width, QtCore.Qt.QueuedConnection)
        self._roi_logic.sigStageMoved.connect(self.update_stage_position, QtCore.Qt.QueuedConnection)
        self._roi_logic.sigUpdateStagePosition.connect(self.update_stage_position, QtCore.Qt.QueuedConnection)
        self._roi_logic.sigTrackingModeStopped.connect(self.reset_tracking_mode_button, QtCore.Qt.QueuedConnection)
        self._roi_logic.sigDisableTracking.connect(self.disable_tracking_action, QtCore.Qt.QueuedConnection)
        self._roi_logic.sigEnableTracking.connect(self.enable_tracking_action, QtCore.Qt.QueuedConnection)
        self._roi_logic.sigDisableRoiActions.connect(self.disable_roi_actions, QtCore.Qt.QueuedConnection)
        self._roi_logic.sigEnableRoiActions.connect(self.enable_roi_actions, QtCore.Qt.QueuedConnection)

    def __disconnect_update_signals_from_logic(self):
        """ Disconnect signals emitted in logic module. """
        self._roi_logic.sigRoiUpdated.disconnect()
        self._roi_logic.sigActiveRoiUpdated.disconnect()
        self._roi_logic.sigRoiListUpdated.disconnect()
        self._roi_logic.sigWidthUpdated.disconnect()
        self._roi_logic.sigStageMoved.disconnect()
        self._roi_logic.sigUpdateStagePosition.disconnect()
        self._roi_logic.sigTrackingModeStopped.disconnect()
        self._roi_logic.sigDisableTracking.disconnect()
        self._roi_logic.sigEnableTracking.disconnect()
        self._roi_logic.sigDisableRoiActions.disconnect()
        self._roi_logic.sigEnableRoiActions.disconnect()

    def __connect_control_signals_to_logic(self):
        """ Establish the connections of signals emitted with slots in logic module. """
        # roi toolbar actions
        self._mw.new_roi_Action.triggered.connect(self._roi_logic.add_roi, QtCore.Qt.QueuedConnection)
        self._mw.go_to_roi_Action.triggered.connect(self._roi_logic.go_to_roi, QtCore.Qt.QueuedConnection)
        self._mw.delete_roi_Action.triggered.connect(self._roi_logic.delete_roi, QtCore.Qt.QueuedConnection)
        # roi list toolbar actions
        self._mw.new_list_Action.triggered.connect(self._roi_logic.reset_roi_list, QtCore.Qt.QueuedConnection)

        # signals
        self.sigRoiWidthChanged.connect(self._roi_logic.set_roi_width)
        self.sigRoiFirstDigitChanged.connect(self._roi_logic.set_roi_first_digit)
        self.sigRoiListNameChanged.connect(self._roi_logic.rename_roi_list, QtCore.Qt.QueuedConnection)
        self._mw.active_roi_ComboBox.activated[str].connect(self._roi_logic.set_active_roi, QtCore.Qt.QueuedConnection)
        self.sigAddInterpolation.connect(self._roi_logic.add_interpolation, QtCore.Qt.QueuedConnection)
        self.sigStartTracking.connect(self._roi_logic.start_tracking)
        self.sigStopTracking.connect(self._roi_logic.stop_tracking)

    def __disconnect_control_signals_to_logic(self):
        """ Disconnect signals from their slots in logic module. """
        self._mw.new_roi_Action.triggered.disconnect()
        self._mw.go_to_roi_Action.triggered.disconnect()
        self._mw.delete_roi_Action.triggered.disconnect()
        self._mw.new_list_Action.triggered.disconnect()
        self.sigRoiWidthChanged.disconnect()
        self.sigRoiListNameChanged.disconnect()
        self._mw.active_roi_ComboBox.activated[str].disconnect()
        self.sigAddInterpolation.disconnect()
        self.sigStartTracking.disconnect()
        self.sigStopTracking.disconnect()

        for marker in self._markers.values():
            marker.sigRoiSelected.disconnect()

    def __connect_internal_signals(self):
        """ Connect signals with slots within this module (internal signals). """
        self._mw.add_interpolation_Action.triggered.connect(self.add_interpolation_clicked, QtCore.Qt.QueuedConnection)
        self._mw.discard_all_roi_Action.triggered.connect(self.delete_all_roi_clicked, QtCore.Qt.QueuedConnection)

        # just emit one signal when finished and not at each modification of the value (valueChanged)
        self._mw.roi_width_doubleSpinBox.editingFinished.connect(self.roi_width_changed)
        self._mw.roi_starting_digit_spinBox.editingFinished.connect(self.roi_first_digit_changed)

        self._mw.save_list_Action.triggered.connect(self.save_roi_list)
        self._mw.load_list_Action.triggered.connect(self.load_roi_list)

        # tracking mode toolbutton
        self._mw.tracking_mode_Action.setEnabled(True)
        self._mw.tracking_mode_Action.setChecked(self._roi_logic.tracking)
        self._mw.tracking_mode_Action.triggered.connect(self.tracking_mode_clicked)

        # file menu
        self._mw.close_MenuAction.triggered.connect(self._mw.close)
        # options menu
        self._mw.mosaic_scan_MenuAction.triggered.connect(self.open_mosaic_settings)

    def __disconnect_internal_signals(self):
        """ Disconnect signals from slots within this module (internal signal). """
        self._mw.add_interpolation_Action.triggered.disconnect()
        self._mw.discard_all_roi_Action.triggered.disconnect()
        self._mw.roi_width_doubleSpinBox.editingFinished.disconnect()
        self._mw.save_list_Action.triggered.disconnect()
        self._mw.load_list_Action.triggered.disconnect()
        self._mw.tracking_mode_Action.triggered.disconnect()
        self._mw.close_MenuAction.triggered.disconnect()
        self._mw.mosaic_scan_MenuAction.triggered.disconnect()

    def show(self):
        """Make main window visible and put it above all other windows. """
        QtWidgets.QMainWindow.show(self._mw)
        self._mw.activateWindow()
        self._mw.raise_()

# ----------------------------------------------------------------------------------------------------------------------
# Methods belonging to the mosaic settings window in the options menu
# ----------------------------------------------------------------------------------------------------------------------

    def init_mosaic_settings_ui(self):
        """ Definition, configuration and initialisation of the mosaic settings GUI.
        """
        # Create the settings window
        self._mosaic_sd = MosaicSettingDialog()
        # Connect the action of the settings window with the code:
        self._mosaic_sd.accepted.connect(self.mosaic_update_settings)  # ok button
        self._mosaic_sd.rejected.connect(self.mosaic_default_settings)  # cancel button
        self._mosaic_sd.current_pos_CheckBox.stateChanged.connect(
            self.mosaic_position)  # current position checkbox updates position fields
        
        # set the default values
        self.mosaic_default_settings()

# slots of the mosaic settings window ----------------------------------------------------------------------------------
    def mosaic_update_settings(self):
        """ Write new settings from the gui to the roi logic 
        """
        self._roi_logic._mosaic_x_start = self._mosaic_sd.x_pos_DSpinBox.value()
        self._roi_logic._mosaic_y_start = self._mosaic_sd.y_pos_DSpinBox.value()
        self._roi_logic._mosaic_roi_width = self._mosaic_sd.mosaic_roi_width_DSpinBox.value()
        self._mw.roi_width_doubleSpinBox.setValue(
            self._mosaic_sd.mosaic_roi_width_DSpinBox.value())  # synchronize the roi width spinboxes so that the marker is drawn correctly
        if self._mosaic_sd.mosaic_size1_RadioButton.isChecked():
            self._roi_logic._mosaic_number_x = 9
            self._roi_logic._mosaic_number_y = 9
        if self._mosaic_sd.mosaic_size2_RadioButton.isChecked():
            self._roi_logic._mosaic_number_x = 25
            self._roi_logic._mosaic_number_y = 25
        if self._mosaic_sd.mosaic_userdefined_RadioButton.isChecked():
            self._roi_logic._mosaic_number_x = self._mosaic_sd.mosaic_width_SpinBox.value()
            self._roi_logic._mosaic_number_y = self._mosaic_sd.mosaic_height_SpinBox.value()
        add_to_list = self._mosaic_sd.mosaic_add_to_list_CheckBox.isChecked()

        self._roi_logic.add_mosaic(x_center_pos=self._roi_logic._mosaic_x_start,
                                    y_center_pos=self._roi_logic._mosaic_y_start,
                                    z_pos=self._roi_logic.stage_position[2],
                                    roi_width=self._roi_logic._mosaic_roi_width,
                                    width=self._roi_logic._mosaic_number_x,
                                    height=self._roi_logic._mosaic_number_y,
                                    add=add_to_list)

    def mosaic_default_settings(self):
        """ Restore default settings. 
        """
        self._mosaic_sd.current_pos_CheckBox.setChecked(False)
        self._mosaic_sd.x_pos_DSpinBox.setValue(0)
        self._mosaic_sd.y_pos_DSpinBox.setValue(0)
        roi_width = self._mw.roi_width_doubleSpinBox.value()
        self._mosaic_sd.mosaic_roi_width_DSpinBox.setValue(roi_width)  
        self._mosaic_sd.mosaic_size1_RadioButton.setAutoExclusive(False)
        self._mosaic_sd.mosaic_size1_RadioButton.setChecked(False)
        self._mosaic_sd.mosaic_size1_RadioButton.setAutoExclusive(True)
        self._mosaic_sd.mosaic_size2_RadioButton.setAutoExclusive(False)
        self._mosaic_sd.mosaic_size2_RadioButton.setChecked(False)
        self._mosaic_sd.mosaic_size2_RadioButton.setAutoExclusive(True)
        self._mosaic_sd.mosaic_userdefined_RadioButton.setAutoExclusive(False)
        self._mosaic_sd.mosaic_userdefined_RadioButton.setChecked(False)
        self._mosaic_sd.mosaic_userdefined_RadioButton.setAutoExclusive(True)
        self._mosaic_sd.mosaic_add_to_list_CheckBox.setChecked(False)

    def mosaic_position(self):
        """ Check state of the current position checkbox and handle position settings accordingly.
        """
        if self._mosaic_sd.current_pos_CheckBox.isChecked():
            # get current stage position from logic and fill this in, then disable spinboxes
            self._mosaic_sd.x_pos_DSpinBox.setValue(self._roi_logic.stage_position[0])
            self._mosaic_sd.y_pos_DSpinBox.setValue(self._roi_logic.stage_position[1])
            self._mosaic_sd.x_pos_DSpinBox.setEnabled(False)
            self._mosaic_sd.y_pos_DSpinBox.setEnabled(False)
        else:
            self._mosaic_sd.x_pos_DSpinBox.setEnabled(True)
            self._mosaic_sd.y_pos_DSpinBox.setEnabled(True)

    def open_mosaic_settings(self):
        """ Opens the settings menu. 
        """
        # retrieve the current position from the stage each time the dialog is opened and set the spinboxes accordingly
        self.mosaic_position()
        self._mosaic_sd.exec_()

# ----------------------------------------------------------------------------------------------------------------------
# Slots for ROI GUI actions
# ----------------------------------------------------------------------------------------------------------------------

# mouse movement on ROI overview image
    @QtCore.Slot(object)
    def mouse_moved_callback(self, event):
        """ Handles any mouse movements inside the ROI display image.
        :param event:   Event that signals the new mouse movement.
                       This should be of type QPointF.
        Gets the mouse position, converts it to a position scaled to the image axis
        and than calculates and updates the distance to the current ROI.
        """
        # converts the absolute mouse position to a position relative to the axis
        mouse_pos = self.roi_image.getViewBox().mapSceneToView(event[0])
        # only calculate distance if a ROI is selected
        active_roi = self._roi_logic.active_roi
        if active_roi:
            roi_pos = self._roi_logic.get_roi_position(active_roi)
            dx = ScaledFloat(mouse_pos.x() - roi_pos[0])
            dy = ScaledFloat(mouse_pos.y() - roi_pos[1])
            d_total = ScaledFloat(
                np.sqrt((mouse_pos.x() - roi_pos[0])**2 + (mouse_pos.y() - roi_pos[1])**2))
            self._mw.roi_distance_Label.setText(
                '{0:.2f} (dx = {1:.2f}, dy = {2:.2f})'.format(d_total, dx, dy))
        else:
            self._mw.roi_distance_Label.setText('? (?, ?)')
        pass

# toolbar actions ------------------------------------------------------------------------------------------------------
    @QtCore.Slot()
    def add_interpolation_clicked(self):
        """ This method is called when the add interpolation toolbutton is clicked.
        Retrieves the current roi width (better roi distance) and sends a signal to the logic module.
        :return: None
        """
        roi_distance = self._mw.roi_width_doubleSpinBox.value()
        self.sigAddInterpolation.emit(roi_distance)

    @QtCore.Slot()
    def delete_all_roi_clicked(self):
        """ This method is called when the discard all ROI toolbutton is clicked.
        Opens a message box to confirm deletion, and informs the logic module if confirmed.
        :return: None
        """
        result = QtWidgets.QMessageBox.question(self._mw, 'Qudi: Delete all ROIs?',
                                                'Are you sure to delete all ROIs?',
                                                QtWidgets.QMessageBox.Yes,
                                                QtWidgets.QMessageBox.No)
        if result == QtWidgets.QMessageBox.Yes:
            self._roi_logic.delete_all_roi()

    # To do: add a Validator on the save_path_LineEdit.
    @QtCore.Slot()
    def save_roi_list(self):
        """ This method is called when the save roi list toolbutton is clicked.
        Save ROI list to file, using filepath and filename given on the GUI.
        """
        roi_list_name = self._mw.roi_list_name_LineEdit.text()
        path = self._mw.save_path_LineEdit.text()
        self._roi_logic.rename_roi_list(roi_list_name)
        self._roi_logic.save_roi_list(path, roi_list_name)

    @QtCore.Slot()
    def load_roi_list(self):
        """ This method is called when the load roi list toolbutton is clicked.
        Opens a dialog to select the file. If a file is selected, the logic handles the loading of the information
        contained therein.
        """
        data_directory = self._mw.save_path_LineEdit.text()  # we will use this as default location to look for files
        this_file = QtWidgets.QFileDialog.getOpenFileName(self._mw,
                                                          'Open ROI list',
                                                          data_directory,
                                                          'json files (*.json)')[0]
        if this_file:
            self._roi_logic.load_roi_list(complete_path=this_file)

    @QtCore.Slot()
    def tracking_mode_clicked(self):
        """ Handles the state of the tracking mode toolbutton and emits a signal """
        if self._roi_logic.tracking:  # tracking mode already on
            self._mw.tracking_mode_Action.setText('Tracking mode')
            self._mw.tracking_mode_Action.setToolTip('Start tracking mode')
            self.sigStopTracking.emit()
        else:  # tracking mode off
            self._mw.tracking_mode_Action.setText('Tracking mode off')
            self._mw.tracking_mode_Action.setToolTip('Stop tracking mode')
            self.sigStartTracking.emit()

# actions on mainwindow widgets ----------------------------------------------------------------------------------------
    @QtCore.Slot()
    def roi_width_changed(self):
        """ This method is called when the spinbox value is changed. Sends a signal to logic informing about
        the new roi width (better: roi distance).
        :return: None
        """
        self.sigRoiWidthChanged.emit(self._mw.roi_width_doubleSpinBox.value())

    @QtCore.Slot()
    def roi_first_digit_changed(self):
        """ This method is called when the spinbox value is changed. Sends a signal to logic informing about
        the new digit to used for naming the ROI.
        :return: None
        """
        self.sigRoiFirstDigitChanged.emit(self._mw.roi_starting_digit_spinBox.value())

    @QtCore.Slot()
    def roi_list_name_changed(self):
        """ Set the name of the current roi list."""
        self.sigRoiListNameChanged.emit(self._mw.roi_list_name_LineEdit.text())

# callbacks of signals sent from the logic------------------------------------------------------------------------------
    @QtCore.Slot(str, str, np.ndarray)
    def update_roi(self, old_name, new_name, position):
        """ Callback of signal sigRoiUpdated sent from logic module.
        Adds information about a new ROI to the active roi combobox.
        :param: str old_name
        :param: str new_name
        :param: float tuple[3] position: position of the roi with new_name as name
        :return: None
        """
        # Handle changed names and deleted/added POIs
        if old_name != new_name:
            self._mw.active_roi_ComboBox.blockSignals(True)
            # Remember current text
            text_active_roi = self._mw.active_roi_ComboBox.currentText()
            # sort ROI names and repopulate ComboBoxes
            self._mw.active_roi_ComboBox.clear()
            roi_names = natural_sort(self._roi_logic.roi_names)
            self._mw.active_roi_ComboBox.addItems(roi_names)
            if text_active_roi == old_name:
                self._mw.active_roi_ComboBox.setCurrentText(new_name)
            else:
                self._mw.active_roi_ComboBox.setCurrentText(text_active_roi)
            self._mw.active_roi_ComboBox.blockSignals(False)

        # Delete/add/update ROI marker to image
        if not old_name:
            # ROI has been added
            self._add_roi_marker(name=new_name, position=position)
        elif not new_name:
            # ROI has been deleted
            self._remove_roi_marker(name=old_name)
        else:
            # ROI has been renamed and/or changed position
            size = self._roi_logic.roi_width  # check if width should be changed again
            self._markers[old_name].set_name(new_name)
            self._markers[new_name] = self._markers.pop(old_name)
            self._markers[new_name].setSize((size, size))
            self._markers[new_name].set_position(position[:2])

        active_roi = self._mw.active_roi_ComboBox.currentText()
        if active_roi:
            self._markers[active_roi].select()

    @QtCore.Slot(str)
    def update_active_roi(self, name):
        """ Callback of signal sigActiveRoiUpdated sent from logic module.
        Updates the active ROI with different marker color and as displayed value in the combobox.
        :param: str name: name of the ROI that is set as active one
        :return: None
        """
        # Deselect current marker
        for marker in self._markers.values():
            if marker.selected:
                marker.deselect()
                break

        # Unselect ROI if name is None or empty str
        self._mw.active_roi_ComboBox.blockSignals(True)
        if not name:
            self._mw.active_roi_ComboBox.setCurrentIndex(-1)
        else:
            self._mw.active_roi_ComboBox.setCurrentText(name)
        self._mw.active_roi_ComboBox.blockSignals(False)

        if name:
            active_roi_pos = self._roi_logic.get_roi_position(name)
            self._mw.roi_coords_label.setText(
                'x={0}, y={1}, z={2}'.format(active_roi_pos[0], active_roi_pos[1], active_roi_pos[2])
            )
        else:
            active_roi_pos = np.zeros(3)
            self._mw.roi_coords_label.setText('')

        if name in self._markers:
            self._markers[name].set_width(self._roi_logic.roi_width)
            self._markers[name].select()

    @QtCore.Slot(dict)
    def update_roi_list(self, roi_dict):
        """ Callback of signal sigRoiListUpdated sent from logic.
        :param: dict roi_dict
        :return None
        """
        if not isinstance(roi_dict, dict):
            self.log.error('ROI parameters to update must be given in a single dictionary.')
            return

        if 'name' in roi_dict:
            self._update_roi_list_name(name=roi_dict['name'])
        # put this in comments because it will reset the image with a None type object and lead to an error in the distance measurement
        # to be reactivated when the possibility of a camera image overlay is established
        # if 'cam_image' in roi_dict and 'cam_image_extent' in roi_dict:
        #     self._update_cam_image(cam_image=roi_dict['cam_image'], cam_image_extent=roi_dict['cam_image_extent'])
        if 'rois' in roi_dict:
            self._update_rois(roi_dict=roi_dict['rois'])

    @QtCore.Slot(np.ndarray)
    def update_stage_position(self, position):
        """ Callback of signals sigStageMoved and sigUpdateStagePosition sent from logic module.
        Updates the textlabel with the current stage position and moves the stage marker.
        :param: np.ndarray[3] position: new position
        :return: None
        """
        self._mw.stage_position_Label.setText('x={0}, y={1}, z={2}'.format(position[0], position[1], position[2]))
        self.stagemarker.set_position(position)

    @QtCore.Slot()
    def reset_tracking_mode_button(self):
        """ Callback of sigTrackingModeStopped.
        Resets tracking mode toolbutton state if tracking programmmatically stopped.
        """
        self._mw.tracking_mode_Action.setText('Tracking mode')
        self._mw.tracking_mode_Action.setToolTip('Start tracking mode')
        self._mw.tracking_mode_Action.setChecked(False)

# ----------------------------------------------------------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------------------------------------------------------

    def _update_cam_image(self, cam_image, cam_image_extent):
        """
        Currently not used
        :param cam_image:
        :param cam_image_extent:
        """
        if cam_image is None or cam_image_extent is None:
            self._mw.roi_map_ViewWidget.removeItem(self.roi_image)
            return
        elif self.roi_image not in self._mw.roi_map_ViewWidget.items():
            self._mw.roi_map_ViewWidget.addItem(self.roi_image)
        self.roi_image.setImage(image=cam_image)
        (x_min, x_max), (y_min, y_max) = cam_image_extent
        self.roi_image.getViewBox().enableAutoRange()
        self.roi_image.setRect(QtCore.QRectF(x_min, y_min, x_max - x_min, y_max - y_min))

    def _update_roi_list_name(self, name):
        """ Update the text in the lineedit in the mainwindow with the current name of the ROI list.
        :param: str name: new name that will be displayed in the lineedit
        :return: None
        """
        self._mw.roi_list_name_LineEdit.blockSignals(True)
        self._mw.roi_list_name_LineEdit.setText(name)
        self._mw.roi_list_name_LineEdit.blockSignals(False)

    def _update_roi_width(self, width):
        """ Update the ROI width spinbox with the new value.
        :param: float width: new width for the ROI marker
        :return: None
        """
        self._mw.roi_width_doubleSpinBox.setValue(width)

    def _update_rois(self, roi_dict):
        """ Populate the dropdown box for selecting a ROI.
        :param: dict roi_dict: dictionary containing the necessary information of the new ROIs that will be displayed
                                in the dropdown box.
        :return: None
        """
        self._mw.active_roi_ComboBox.blockSignals(True)
        self._mw.active_roi_ComboBox.clear()
        roi_names = natural_sort(roi_dict)
        self._mw.active_roi_ComboBox.addItems(roi_names)

        # Get two lists of ROI names. One of those to delete and one of those to add
        old_roi_names = set(self._markers)
        new_roi_names = set(roi_names)
        names_to_delete = list(old_roi_names.difference(new_roi_names))
        names_to_add = list(new_roi_names.difference(old_roi_names))

        # Delete markers accordingly
        for name in names_to_delete:
            self._remove_roi_marker(name)
        # Update positions of all remaining markers
        size = self._roi_logic.roi_width  # self._roi_logic.optimise_xy_size * np.sqrt(2)
        for name, marker in self._markers.items():
            marker.setSize((size, size))
            marker.set_position(roi_dict[name])
        # Add new markers
        for name in names_to_add:
            self._add_roi_marker(name=name, position=roi_dict[name])

        # If there is no active ROI, set the combobox to nothing (-1)
        active_roi = self._roi_logic.active_roi
        if active_roi in roi_names:
            self._mw.active_roi_ComboBox.setCurrentText(active_roi)
            self._markers[active_roi].select()
            active_roi_pos = roi_dict[active_roi]

            self._mw.roi_coords_label.setText(
                'x={0}, y={1}, z={2}'.format(active_roi_pos[0], active_roi_pos[1], active_roi_pos[2])
            )
        else:
            self._mw.active_roi_ComboBox.setCurrentIndex(-1)
            self._mw.roi_coords_label.setText('')  # no roi active

        self._mw.active_roi_ComboBox.blockSignals(False)

    def _add_roi_marker(self, name, position):
        """ Add a square ROI marker to the roi overview image.
        :param: str name: name of the current ROI
        :param: float tuple (3): position of the current ROI
        :return: None
        """
        if name:
            if name in self._markers:
                self.log.error('Unable to add ROI marker to image. ROI marker already present.')
                return
            marker = RoiMarker(position=position[:2],
                               view_widget=self._mw.roi_map_ViewWidget,
                               roi_name=name,
                               width=self._roi_logic._roi_width,
                               movable=False)
            # Add to the roi overview image widget
            marker.add_to_view_widget()
            # remove the handle that can be used to resize the roi as we do not want this functionality
            marker.removeHandle(marker.getHandles()[0])
            marker.sigRoiSelected.connect(self._roi_logic.set_active_roi, QtCore.Qt.QueuedConnection)
            self._markers[name] = marker

    def _remove_roi_marker(self, name):
        """ Remove the ROI marker for a ROI that was deleted.
        :param: str name: name of the current ROI
        :return: None
        """
        if name in self._markers:
            self._markers[name].delete_from_view_widget()
            self._markers[name].sigRoiSelected.disconnect()
            del self._markers[name]

    def _add_stage_marker(self, position=(0, 0)):
        """ Add a square marker for the current stage position to the roi overview image.
        :param: float tuple: position at which the marker center will be drawn
        :return: None
        """
        try:
            stagemarker = StageMarker(position=position,
                                      view_widget=self._mw.roi_map_ViewWidget,
                                      width=self.stagemarker_width,  # to be defined in config
                                      movable=False)
            # add the marker to the roi overview image
            stagemarker.add_to_view_widget()
            # remove the scaling handle
            stagemarker.removeHandle(stagemarker.getHandles()[0])
            self.stagemarker = stagemarker
        except Exception as e:
            self.log.warn(f'Unable to add stage marker to image due to the following error : {e}')

# ----------------------------------------------------------------------------------------------------------------------
# Functions to handle user interface state
# ----------------------------------------------------------------------------------------------------------------------

    @QtCore.Slot()
    def disable_tracking_action(self):
        """ This method provides a security to disable user interaction on tracking mode, for example during tasks. """
        self._mw.tracking_mode_Action.setDisabled(True)

    @QtCore.Slot()
    def enable_tracking_action(self):
        """ Enables user interaction on tracking mode, to reestablish the callable state for example after a task. """
        self._mw.tracking_mode_Action.setDisabled(False)

    @QtCore.Slot()
    def disable_roi_actions(self):
        """ This method provides a security to disable user interaction on roi and roi list actions,
        for example during tasks. """
        self._mw.new_roi_Action.setDisabled(True)
        self._mw.go_to_roi_Action.setDisabled(True)
        self._mw.delete_roi_Action.setDisabled(True)
        self._mw.add_interpolation_Action.setDisabled(True)

        self._mw.new_list_Action.setDisabled(True)
        self._mw.save_list_Action.setDisabled(True)
        self._mw.load_list_Action.setDisabled(True)
        self._mw.discard_all_roi_Action.setDisabled(True)

        self._mw.active_roi_ComboBox.setDisabled(True)

    @QtCore.Slot()
    def enable_roi_actions(self):
        """ Enables user interaction on ROIs and ROI lists, to reestablish the callable state for example after a task. """
        self._mw.new_roi_Action.setDisabled(False)
        self._mw.go_to_roi_Action.setDisabled(False)
        self._mw.delete_roi_Action.setDisabled(False)
        self._mw.add_interpolation_Action.setDisabled(False)

        self._mw.new_list_Action.setDisabled(False)
        self._mw.save_list_Action.setDisabled(False)
        self._mw.load_list_Action.setDisabled(False)
        self._mw.discard_all_roi_Action.setDisabled(False)

        self._mw.active_roi_ComboBox.setDisabled(False)

# ----------------------------------------------------------------------------------------------------------------------
# Close function: Stop all continuous actions.
# ----------------------------------------------------------------------------------------------------------------------

    def close_function(self):
        """ This method serves as a reimplementation of the close event. Continuous mode (tracking mode of stage
        position) is stopped when the main window is closed. """
        if self._roi_logic.tracking:
            self.sigStopTracking.emit()
