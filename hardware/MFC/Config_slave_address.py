import time
from sensirion_shdlc_driver import ShdlcSerialPort
from sensirion_shdlc_driver.errors import ShdlcDeviceError
from sensirion_driver_adapters.shdlc_adapter.shdlc_channel import ShdlcChannel
from sensirion_uart_sfx6xxx.device import Sfx6xxxDevice
from sensirion_uart_sfx6xxx.commands import StatusCode

Slave_address = 0

with ShdlcSerialPort(port='COM2', baudrate=115200) as port:
    channel = ShdlcChannel(port)
    sensor = Sfx6xxxDevice(channel)
    sensor.device_reset()
    time.sleep(2)
    sensor.set_slave_address(Slave_address)
