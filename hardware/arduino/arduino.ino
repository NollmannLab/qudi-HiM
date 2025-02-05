// const int pin2 = 2;
// const int pin3 = 3;
// const int pin4 = 4;
// const int pin5 = 5;
// const int pin6 = 6;
// const int pin7 = 7;
// const int pin8 = 8;
// const int pin9 = 9;
// const int pin10 = 10;
// const int pin11 = 11;
// const int pin12 = 12;
// const int pin13 = 13;

void setup() {
  // Define the baud rate for the serial communication
  Serial.begin(9600);

  // Set pins 2 to 10 as output - meaning they will sent digital signal to another device (for example the opto-coupler)
    for (int i = 2; i <= 10; i++) {
        pinMode(i, OUTPUT);
        digitalWrite(i, LOW);  // Set all to LOW initially
    }

  // Set pins 11 to 13 as input - meaning they will read digital signal from another device (for example from another
  // channel of Arduino)
    for (int i = 11; i <= 13; i++) {
        pinMode(i, INPUT);
        digitalWrite(i, LOW);  // Set all to LOW initially
    }
}

void loop() {
  // Check if a command was sent from the computer
  if (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    char firstChar = command.charAt(0);

    // If command starts with a digit, the command will either control a digital pin if values are between 2 & 10
    // (change pin status) or read a digital pin if values are between 11 & 13
    if (isDigit(firstChar)) {
      String pinStr = command.substring(0, command.length() - 1);
      char state = command.charAt(command.length() - 1);
      int pin = pinStr.toInt();

      // If input pin is valid, switch its state according to the indicated value from input command
      if (pin >= 2 && pin <= 10) {
          if (state == '1') {
            digitalWrite(pin, HIGH);
            Serial.println("pin" + String(pin) + " ON");
          } else if (state == '0') {
            digitalWrite(pin, LOW);
            Serial.println("pin" + String(pin) + " OFF");
          }
      }

      // If input pin is valid, switch its state according to the indicated value from input command
      if (pin >= 11 && pin <= 13) {
        int digitalValue = digitalRead(pin);
        Serial.println(String(digitalValue));
      }
    }
      // If command starts with a 'A', the command will control an analog input pin = read pin status
    else if (firstChar == 'A') {
        int analogPin = command.substring(1).toInt();
        if (analogPin >= 0 && analogPin <= 5) {
            int analogValue = analogRead(analogPin);
            Serial.println(String(analogValue));
        }
        else {
            Serial.println("Invalid analog pin");
        }
    }
    else {
        Serial.println("Unknown command format");
    }
  }
}

//       // Match arduinoPin to the pinNumber indicated in the input command. If the pin does not exist, return nothing
//       int arduinoPin;
//       switch(pinNumber) {
//         case 2: arduinoPin = pin2; break;
//         case 3: arduinoPin = pin3; break;
//         case 4: arduinoPin = pin4; break;
//         case 5: arduinoPin = pin5; break;
//         case 6: arduinoPin = pin6; break;
//         case 7: arduinoPin = pin7; break;
//         case 8: arduinoPin = pin8; break;
//         case 9: arduinoPin = pin9; break;
//         case 10: arduinoPin = pin10; break;
//         case 11: arduinoPin = pin11; break;
//         case 12: arduinoPin = pin12; break;
//         case 13: arduinoPin = pin13; break;
//         default: return;
//       }
