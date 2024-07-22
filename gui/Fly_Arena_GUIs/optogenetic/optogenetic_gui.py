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
import os
import sys
import time

from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QWidget
from PyQt5.QtGui import QPixmap, QScreen
from PyQt5.QtCore import Qt, QTimer
from PyQt5.uic.properties import QtWidgets
from qtpy import uic
from qtpy.QtCore import Signal

from core.configoption import ConfigOption
from core.connector import Connector
from gui.guibase import GUIBase
import logging

logging.basicConfig(filename='logfile.log', filemode='w', level=logging.DEBUG)
logger = logging.getLogger(__name__)


class ImageWindow(QMainWindow):
    """"""

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
    """ Class defined for the optogenetic window for odor control.
        """
    def __init__(self):
        super().__init__()
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'optogenetic_window.ui')
        uic.loadUi(ui_file, self)
        self.show()


class OptogeneticGUI(GUIBase):
    optogenetic_logic = Connector(interface='OptogeneticLogic')

    _noir_path = ConfigOption('noir_path', None)
    _quart1_path = ConfigOption('quart1_path', None)
    _quart2_path = ConfigOption('quart2_path', None)

    signoirClicked = Signal()
    sigquart1Clicked = Signal()
    sigquart2Clicked = Signal()

    screens = QApplication.screens()

    if len(screens) < 2:
        print("Error: There are not enough screens available.")
        sys.exit(1)

    second_screen = screens[1]

    screen_geometry = second_screen.geometry()



    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        self._optogenetic_logic = None

        self._ow = None
        self._iw = None
        self.noirmap = QPixmap(self._noir_path)
        self.quart1map = QPixmap(self._quart1_path)
        self.quart2map = QPixmap(self._quart2_path)
        self._ow = OptoWindow()
        self._iw = ImageWindow()
        self.noirmapscaled = self.noirmap.scaled(self.screen_geometry.width(), self.screen_geometry.height(), Qt.KeepAspectRatio)
        self.quart1mapscaled = self.quart1map.scaled(self.screen_geometry.width(), self.screen_geometry.height(), Qt.KeepAspectRatio)
        self.quart2mapscaled = self.quart2map.scaled(self.screen_geometry.width(), self.screen_geometry.height(), Qt.KeepAspectRatio)
        self._iw.label.setPixmap(self.noirmapscaled)
        self._ow.retour_2.setPixmap(self.noirmapscaled)



    def on_activate(self):
        """ Initialize all UI elements and establish signal connections.
        """
        self._optogenetic_logic = self.optogenetic_logic()

        self._ow.noir.clicked.connect(self.noirdisplay)
        self._ow.quart1.clicked.connect(self.quart1display)
        self._ow.quart2.clicked.connect(self.quart2display)
        self.signoirClicked.connect(lambda: self.noirdisplay())
        self.sigquart1Clicked.connect(lambda: self.sigButton1Clicked.emit())
        self.sigquart2Clicked.connect(lambda: self.sigButton1Clicked.emit())

    def on_deactivate(self):
        """ Perform required deactivation.
     """
        self._ow.close()
        self._iw.close()

    def noirdisplay(self):
        """"""
        im = self.noirmap.scaled(371, 271, Qt.KeepAspectRatio)
        self._ow.retour_2.setPixmap(im)
        self._optogenetic_logic.image_display(self.noirmapscaled, self._iw)


    def quart1display(self):
        """"""
        im = self.quart1map.scaled(371, 271, Qt.KeepAspectRatio)
        self._ow.retour_2.setPixmap(im)
        if self._ow.doubleSpinBox.value() == 0:
            self._optogenetic_logic.image_display(self.quart1mapscaled, self._iw)

        else:
            self._optogenetic_logic.image_display(self.quart1mapscaled, self._iw)
            QTimer.singleShot(self._ow.doubleSpinBox.value() * 60 * 1000, self.noirdisplay)


    def quart2display(self):
        """"""
        im = self.quart2map.scaled(371, 271, Qt.KeepAspectRatio)
        self._ow.retour_2.setPixmap(im)
        if self._ow.doubleSpinBox.value() == 0:
            self._optogenetic_logic.image_display(self.quart2mapscaled, self._iw)

        else:
            self._optogenetic_logic.image_display(self.quart2mapscaled, self._iw)
            QTimer.singleShot(self._ow.doubleSpinBox.value() * 60 * 1000, self.noirdisplay)
