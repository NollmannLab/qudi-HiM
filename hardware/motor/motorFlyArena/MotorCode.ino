"""
Qudi-CBS

This script contains the code uploaded in the elegoo device.

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
#include <Wire.h>
#include <Adafruit_MotorShield.h>
#include "utility/Adafruit_MS_PWMServoDriver.h"

// Créer l'objet Adafruit Motor Shield
Adafruit_MotorShield AFMS = Adafruit_MotorShield(); 

// Connecter un moteur pas à pas (186 pas/révolution) au port M1 et M2
Adafruit_StepperMotor *myMotor = AFMS.getStepper(200, 1);

void setup() {
  Serial.begin(9600);           // Initialiser la communication série
  Serial.println("Stepper control ready!");

  AFMS.begin();  // Initialiser le shield

  myMotor->setSpeed(60);  // Définir la vitesse du moteur à 10 tr/min
}

void loop() {
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n'); // Lire la commande série
    command.trim(); // Supprimer les espaces blancs

    if (command == "forward") {
      myMotor->step(110, FORWARD, SINGLE);
      delay(1000);  // Attendre pour s'assurer que la commande est exécutée
      Serial.println("Command 'forward' executed");
    } else if (command == "backward") {
      myMotor->step(110, BACKWARD, SINGLE);
      delay(1000);  // Attendre pour s'assurer que la commande est exécutée
      Serial.println("Command 'backward' executed");
    } else {
      Serial.println("Unknown command");
    }
  }
}
