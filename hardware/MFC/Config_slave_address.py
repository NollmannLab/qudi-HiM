import time
from sensirion_shdlc_driver import ShdlcSerialPort
from sensirion_shdlc_driver.errors import ShdlcDeviceError
from sensirion_driver_adapters.shdlc_adapter.shdlc_channel import ShdlcChannel
from sensirion_uart_sfx6xxx.device import Sfx6xxxDevice
from sensirion_uart_sfx6xxx.commands import StatusCode

Slave_address = 3

# The following piece of code is used to test the communication with a MFC
with ShdlcSerialPort(port='COM12', baudrate=115200) as port:
    channel = ShdlcChannel(port, shdlc_address=Slave_address)
    sensor = Sfx6xxxDevice(channel)
    sensor.device_reset()
    print(f'slave address : {sensor.get_slave_address()}')
    Z = sensor.set_setpoint_and_read_measured_value(2)
    time.sleep(2)
    print(Z)
    sensor.device_reset()

# # The following piece of code is used to change the slave_address of a MFC
# with ShdlcSerialPort(port='COM12', baudrate=115200) as port:
#     channel = ShdlcChannel(port, shdlc_address=Slave_address)
#     sensor = Sfx6xxxDevice(channel)
#     sensor.device_reset()
#     print(f'old slave address : {sensor.get_slave_address()}')
#     sensor.set_slave_address(Slave_address)
#     time.sleep(2)
#     print(f'new slave address : {sensor.get_slave_address()}')
