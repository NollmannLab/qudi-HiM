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
const int pin2 = 2;
const int pin3 = 3;
const int pin4 = 4;
const int pin5 = 5;
const int pin6 = 6;
const int pin7 = 7;
const int pin8 = 8;
const int pin9 = 9;
const int pin10 = 10;
const int pin11 = 11;
const int pin12 = 12;
const int pin13 = 13;

void setup() {
  Serial.begin(9600);
  pinMode(pin2, OUTPUT);
  pinMode(pin3, OUTPUT);
  pinMode(pin4, OUTPUT);
  pinMode(pin5, OUTPUT);
  pinMode(pin6, OUTPUT);
  pinMode(pin7, OUTPUT);
  pinMode(pin8, OUTPUT);
  pinMode(pin9, OUTPUT);
  pinMode(pin10, OUTPUT);
  pinMode(pin11, OUTPUT);
  pinMode(pin12, OUTPUT);
  pinMode(pin13, OUTPUT);

  digitalWrite(pin2, LOW);
  digitalWrite(pin3, LOW);
  digitalWrite(pin4, LOW);
  digitalWrite(pin5, LOW);
  digitalWrite(pin6, LOW);
  digitalWrite(pin7, LOW);
  digitalWrite(pin8, LOW);
  digitalWrite(pin9, LOW);
  digitalWrite(pin10, LOW);
  digitalWrite(pin11, LOW);
  digitalWrite(pin12, LOW);
  digitalWrite(pin13, LOW);
}

void loop() {
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    Serial.println("Received command: " + command); // Debugging line
    if (command.length() == 2 || command.length() == 3) {
      String pinStr = command.substring(0, command.length() - 1);
      char state = command.charAt(command.length() - 1);

      int pinNumber = pinStr.toInt();

      int arduinoPin;
      switch(pinNumber) {
        case 2: arduinoPin = pin2; break;
        case 3: arduinoPin = pin3; break;
        case 4: arduinoPin = pin4; break;
        case 5: arduinoPin = pin5; break;
        case 6: arduinoPin = pin6; break;
        case 7: arduinoPin = pin7; break;
        case 8: arduinoPin = pin8; break;
        case 9: arduinoPin = pin9; break;
        case 10: arduinoPin = pin10; break;
        case 11: arduinoPin = pin11; break;
        case 12: arduinoPin = pin12; break;
        case 13: arduinoPin = pin13; break;
        default: return;
      }

      if (state == '1') {
        digitalWrite(arduinoPin, HIGH);
        Serial.println("pin" + String(pinNumber) + " ON");
      } else if (state == '0') {
        digitalWrite(arduinoPin, LOW);
        Serial.println("pin" + String(pinNumber) + " OFF");
      }
    }
  }
}

