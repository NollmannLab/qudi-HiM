import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QWidget
from PyQt5.QtGui import QPixmap, QScreen
from PyQt5.QtCore import Qt

from logic.generic_logic import GenericLogic


class ImageWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowState(Qt.WindowFullScreen)  # Display in full screen

        screens = QApplication.screens()

        if len(screens) < 2:
            print("Error: There are not enough screens available.")
            sys.exit(1)

        second_screen = screens[1]

        screen_geometry = second_screen.geometry()

        image_path = 'C:/Users/sCMOS-1/qudi-cbs/gui/Fly_Arena_GUIs/optogenetic/Image/Black.PNG'
        pixmap = QPixmap(image_path)

        scaled_pixmap = pixmap.scaled(screen_geometry.width(), screen_geometry.height(), Qt.KeepAspectRatio)

        self.label = QLabel(self)
        self.label.setPixmap(scaled_pixmap)
        self.label.setAlignment(Qt.AlignCenter)
        self.setCentralWidget(self.label)

        self.setGeometry(screen_geometry)


class OptogeneticLogic (GenericLogic):

    def __init__(self):
        self._iw = None

    def on_activate(self):
        self._iw = ImageWindow()

    def on_deactivate(self):
        self._iw.close()

    def activate_window(self):
        """Activates and shows the window."""
        self.show()

    def deactivate_window(self):
        """Deactivates and hides the window."""
        self.hide()