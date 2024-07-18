import os
import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QWidget
from PyQt5.QtGui import QPixmap, QScreen
from PyQt5.QtCore import Qt
from qtpy import uic

from logic.generic_logic import GenericLogic


class OptoWindow(QMainWindow):
    """ Class defined for the optogenetic window for odor control.
        """

    def __init__(self, close_function):
        super().__init__()
        this_dir = os.path.dirname(__file__)
        ui_file = os.path.join(this_dir, 'odor_circuit_window.ui')
        uic.loadUi(ui_file, self)
        self.close_function = close_function
        self.show()

