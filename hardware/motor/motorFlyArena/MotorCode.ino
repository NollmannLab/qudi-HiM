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
