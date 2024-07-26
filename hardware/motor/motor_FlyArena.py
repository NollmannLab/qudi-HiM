import serial
import time

from core.configoption import ConfigOption
from core.module import Base


class MotorControl(Base):

    _port = ConfigOption('port', 'COM14')

    def __init__(self, config, **kwargs):
        super().__init__(config=config, **kwargs)
        try:
            self.ser = serial.Serial(self._port, 9600, timeout=5)
            time.sleep(2)
        except serial.SerialException as e:
            print(f"Error communicating with the motor: {e}")

    def on_activate(self):
        """initialize the arduino uno device
        """
        pass

    def on_deactivate(self):
        self.ser.close()

    def send_command(self,command):
        """
        Send a command to the elegoo.
        typical command :
        send_command("forward")
        send_command("backward")
        """
        self.ser.flushInput()  # Vider le tampon d'entrée pour éviter les anciennes données
        self.ser.write((command + '\n').encode())
        print(f"Command sent: {command}")

        # Lecture de la réponse du moteur
        response = self.ser.readline().decode().strip()
        if response:
            print(f"Response received: {response}")
        else:
            print("No response received")







