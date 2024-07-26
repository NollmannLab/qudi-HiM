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
from PyQt5.QtCore import Qt

from logic.generic_logic import GenericLogic


class OptogeneticLogic(GenericLogic):

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)

    def on_activate(self):
        pass

    def on_deactivate(self):
        """ Perform required deactivation. """
        pass

    @staticmethod
    def image_display(image, window):
        """Display the given image in the specified window.

            @param image: The QPixmap image to be displayed.
            @param window: The window object that contains the label where the image will be displayed.
        """

        window.label.setPixmap(image)
        window.label.setAlignment(Qt.AlignCenter)
