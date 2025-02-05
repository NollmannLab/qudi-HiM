# -*- coding: utf-8 -*-
"""
Qudi-CBS

This module contains a GUI for the odor circuit on the Fly Arena.

An extension to Qudi.

@author: D. Guerin, JB. Fiche

Created on Wen july 16, 2024
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
import logging
import os
import sys

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel
from PyQt5.uic.properties import QtWidgets
from qtpy import uic
from qtpy.QtCore import Signal
from time import time, sleep
from qtpy import QtCore, QtGui
from core.configoption import ConfigOption
from core.connector import Connector
from gui.guibase import GUIBase

logging.basicConfig(filename='logfile.log', filemode='w', level=logging.DEBUG)
logger = logging.getLogger(__name__)


class WorkerSignals(QtCore.QObject):
    """ Defines the signals available from a running worker thread """
    sigOptoStepFinished = QtCore.Signal(float, float, float, int, int, QtGui.QPixmap, QtGui.QPixmap)


class OptoWorker(QtCore.QRunnable):
    """ Worker thread to wait during an opto pulse. The worker handles only the waiting time.
    """
    def __init__(self, t_on, t_off, duration, n_step_on, n_step_off, im_off, im_on):
        super(OptoWorker, self).__init__()
        self.signals = WorkerSignals()
        self.t_on = t_on
        self.t_off = t_off
        self.duration = duration
        self.n_step_on = n_step_on
        self.n_step_off = n_step_off
        self.im_on = im_on
        self.im_off = im_off

    @QtCore.Slot()
    def run(self):
        """ """
        if self.n_step_on > self.n_step_off:
            sleep(self.t_on)
        else:
            sleep(self.t_off)
        self.signals.sigOptoStepFinished.emit(self.t_on, self.t_off,
                                              self.duration,
                                              self.n_step_on, self.n_step_off,
                                              self.im_off, self.im_on)


class ImageWindow(QMainWindow):
    """
    A window class for displaying images on the secondary screen.

    This class inherits from QMainWindow and sets up a full-screen window
    on the second available screen. It includes a QLabel centered in the
    window to display images.
    """

    def __init__(self):
        super().__init__()

        self.setWindowState(Qt.WindowFullScreen)  # Display in full screen

        screens = QApplication.screens()

        if len(screens) < 2:
            print("Error: There are not enough screens available.")
            sys.exit(1)

        second_screen = screens[1]
        screen_geometry = second_screen.geometry()
        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignCenter)
        self.setCentralWidget(self.label)
        self.setGeometry(screen_geometry)
        self.showFullScreen()


class OptoWindow(QtWidgets.QMainWindow):
    """
    Class defined for the optogenetic window for odor control.
    """

    def __init__(self):
        super().__init__()
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'optogenetic_window.ui')
        uic.loadUi(ui_file, self)
        self.show()


class OptogeneticGUI(GUIBase):
    """ Main GUI class to handle interactions with the shutter & the projector for optogenetic activation - since the
    projector cannot be controlled, a second screen is defined where the image will be displayed & project onto the
    FlyArena
    """
    # define variable from the config file
    optogenetic_logic = Connector(interface='OptogeneticLogic')
    _no_light_path = ConfigOption('no_light_path', None)
    _arena_red_path = ConfigOption('arena_red_path', None)
    _arena_green_path = ConfigOption('arena_green_path', None)

    # sig_map_off_Clicked = Signal()
    # sig_map_red_Clicked = Signal()
    # sigquart2Clicked = Signal()

    # define the screen
    screens = QApplication.screens()
    if len(screens) < 2:
        print("Error: There are not enough screens available.")
        sys.exit(1)
    second_screen = screens[1]
    screen_geometry = second_screen.geometry()

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self.threadpool = QtCore.QThreadPool()
        # self.p = False
        self._optogenetic_logic = None
        self.shutter_state: bool = False  # The state of the shutter is assumed Close / False when starting qudi

        self._ow = None
        self._iw = None
        self.map_off = QPixmap(self._no_light_path)
        self.map_red = QPixmap(self._arena_red_path)
        self.map_green = QPixmap(self._arena_green_path)
        self._ow = OptoWindow()
        self._iw = ImageWindow()
        self.map_off_scaled = self.map_off.scaled(self.screen_geometry.width(), self.screen_geometry.height(),
                                                 Qt.KeepAspectRatio)
        self.map_red_scaled = self.map_red.scaled(self.screen_geometry.width(), self.screen_geometry.height(),
                                                     Qt.KeepAspectRatio)
        self.map_green_scaled = self.map_green.scaled(self.screen_geometry.width(), self.screen_geometry.height(),
                                                     Qt.KeepAspectRatio)
        self._iw.label.setPixmap(self.map_off_scaled)
        self._ow.retour_2.setPixmap(self.map_off_scaled)

    def on_activate(self):
        """
        Initialize all UI elements and establish signal connections.
        """
        self._optogenetic_logic = self.optogenetic_logic()

        # connect signals to methods
        self._ow.arena_OFF_toolButton.clicked.connect(self.map_off_display)
        self._ow.arena_red_toolButton.clicked.connect(self.map_red_display)
        self._ow.arena_green_toolButton.clicked.connect(self.map_green_display)
        # self.sig_map_off_Clicked.connect(lambda: self.map_off_display())
        # self.sig_map_red_Clicked.connect(lambda: self.sigButton1Clicked.emit())
        # self.sigquart2Clicked.connect(lambda: self.sigButton1Clicked.emit())
        self._ow.shutter_toolButton.toggled.connect(self.change_shutter)

    def on_deactivate(self):
        """
        Perform required deactivation.
        """
        # if not self.p:
        #     pass
        # else:
        #     self.backward()
        self._iw.close()

    # def forward(self):
    #     """
    #     take a 180° step forward
    #     """
    #     self.p = True
    #     self._optogenetic_logic.forward()
    #     self._ow.toggleButton.setText('Close')
    #
    # def backward(self):
    #     """
    #     take a 180° step backward
    #     """
    #     self.p = False
    #     self._optogenetic_logic.backward()
    #     self._ow.toggleButton.setText('Open')

# ======================================================================================================================
# Specific methods handling image display and optogenetic pulses
# ======================================================================================================================

    def map_off_display(self):
        """
        Display the 'black' image
        """
        self.close_shutter()
        im = self.map_off.scaled(371, 271, Qt.KeepAspectRatio)
        self._ow.retour_2.setPixmap(im)
        self._optogenetic_logic.image_display(self.map_off_scaled, self._iw)

    def map_red_display(self):
        """
        Display the red_map image and update the optogenetic logic.
        """
        # set the image - if the duration is set to zero, no optogenetic pulse will be sent and the image is displayed
        # until another image is activated
        im = self.map_red_scaled
        self._ow.retour_2.setPixmap(im.scaled(371, 271, Qt.KeepAspectRatio))
        if self._ow.doubleSpinBox_opto_stimulation.value() == 0:
            self.open_shutter()
            self._optogenetic_logic.image_display(im, self._iw)

        else:
            im_off = self.map_off_scaled
            t_ON_pulse = self._ow.doubleSpinBox_opto_pulse_ON.value()
            t_OFF_pulse = self._ow.doubleSpinBox_opto_pulse_OFF.value()
            t_opto = self._ow.doubleSpinBox_opto_stimulation.value()
            self.open_shutter()
            self.opto(t_ON_pulse, t_OFF_pulse, t_opto, 0, 0, im_off, im)

    def map_green_display(self):
        """
        Display the 'green map' image and update the optogenetic logic.
        """
        # set the image - if the duration is set to zero, no optogenetic pulse will be sent and the image is displayed
        # until another image is activated
        im = self.map_green_scaled
        self._ow.retour_2.setPixmap(im.scaled(371, 271, Qt.KeepAspectRatio))
        if self._ow.doubleSpinBox_opto_stimulation.value() == 0:
            self.open_shutter()
            self._optogenetic_logic.image_display(im, self._iw)

        else:
            im_off = self.map_off_scaled
            t_ON_pulse = self._ow.doubleSpinBox_opto_pulse_ON.value()
            t_OFF_pulse = self._ow.doubleSpinBox_opto_pulse_OFF.value()
            t_opto = self._ow.doubleSpinBox_opto_stimulation.value()
            self.open_shutter()
            self.opto(t_ON_pulse, t_OFF_pulse, t_opto, 0, 0, im_off, im)

    def opto(self, t_on, t_off, duration, n_step_on, n_step_off, im_off, im_on):
        """ Launch an optogenetic excitation
        @param t_on: (float) indicate how long a single excitation should stay ON (during a pulse)
        @param t_off: (float) indicate how long a single excitation should stay OFF (during a pulse)
        @param duration: (float) total duration of the optogenetic cycle
        @param n_step_on: (int) number of ON_excitation pulse already sent
        @param n_step_off: (int) number of OFF_excitation pulse already sent
        @param im_off: (Qimage) image associated to the OFF state
        @param im_on: (Qimage) image associated to the ON state
        """
        dt = t_on * n_step_on + t_off * n_step_off
        if dt < duration:
            if n_step_on > n_step_off:
                # self._ow.retour_2.setPixmap(im_off)
                self._optogenetic_logic.image_display(im_off, self._iw)
                worker = OptoWorker(t_on, t_off, duration, n_step_on, n_step_off + 1, im_off, im_on)
            else:
                # self._ow.retour_2.setPixmap(im_on)
                self._optogenetic_logic.image_display(im_on, self._iw)
                worker = OptoWorker(t_on, t_off, duration, n_step_on + 1, n_step_off, im_off, im_on)

            worker.signals.sigOptoStepFinished.connect(self.opto)
            self.threadpool.start(worker)

        else:
            self.close_shutter()

    # ======================================================================================================================
    # Specific methods handling the shutter
    # ======================================================================================================================

    def change_shutter(self):
        """ Handle signal from the shutter_toolButton. Note that the state of the shutter is then changed in the logic
        """
        self.shutter_state = self._optogenetic_logic.send_trigger_to_shutter()

    def open_shutter(self):
        """ Open the shutter
        """
        if not self.shutter_state:
            self.change_shutter()

    def close_shutter(self):
        """ Close the shutter
        """
        if self.shutter_state:
            self.change_shutter()

    # def on_toggle(self, checked):
    #     """
    #     Check the state of the push Button
    #     @param checked : the state of the button
    #     """
    #     if checked:
    #         self.on_pressed()
    #     else:
    #         self.on_released()
    #
    # def on_pressed(self):
    #     """
    #     Open the projector
    #     """
    #     self.forward()
    #
    # def on_released(self):
    #     """
    #     Close the projector
    #     """
    #     self.backward()
    #
    # def infinite_time(self, state):
    #     """ """
    #     if state == 2:  # Checked
    #         self._ow.doubleSpinBox.setValue(0)
    #         self._ow.doubleSpinBox.setDisabled(True)
    #     else:  # Unchecked
    #         self._ow.doubleSpinBox.setDisabled(False)