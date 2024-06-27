"""Qudi-CBS

This module contains the code that has to be on the arduino device to use the arduino hardware.

@author: D. Guerin, JB. Fiche

Created on Tue may 18 2024.
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
const int pin1 = 8;
const int pin2 = 9;
const int pin3 = 10;
const int pin4 = 11;

void setup() {
  Serial.begin(9600);
  pinMode(pin1, OUTPUT);
  pinMode(pin2, OUTPUT);
  pinMode(pin3, OUTPUT);
  pinMode(pin4, OUTPUT);
  digitalWrite(pin1, LOW);
  digitalWrite(pin2, LOW);
  digitalWrite(pin3, LOW);
  digitalWrite(pin4, LOW);
}

void loop() {
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    if (command.length() == 2) {
      char pin = command.charAt(0);
      char state = command.charAt(1);

      int pinNumber;
      if (pin == '1') pinNumber = pin1;
      else if (pin == '2') pinNumber = pin2;
      else if (pin == '3') pinNumber = pin3;
      else if (pin == '4') pinNumber = pin4;
      else return;

      if (state == '1') {
        digitalWrite(pinNumber, HIGH);
        Serial.println("Pin " + String(pin) + " ON");
      } else if (state == '0') {
        digitalWrite(pinNumber, LOW);
        Serial.println("Pin " + String(pin) + " OFF");
      }
    }
  }
}