## Cameras: 

| **Model and SN**     | Blackfly S USB3 BFS-U3-200S6M-C (SN#23503851)                |
| -------------------- | ------------------------------------------------------------ |
| **Drivers location** | Spinnaker SDK - Need to create an account to get the .exe file ( https://www.flir.eu/products/spinnaker-sdk/?vertical=machine+vision&segment=iis) |
| **Software**         | SpinView - contained in the spinnaker.exe                    |
| **Python**           |                                                              |
| **Resources**        | Spinnaker SDK documentation (http://softwareservices.flir.com/Spinnaker/latest/index.html) |

## Arduino uno: 

| **Model and SN**     | Arduino uno rev3 SMD                                         |
| -------------------- | ------------------------------------------------------------ |
| **Drivers location** | [Sensirion SFX6XXX SHDLC Python Driver — sensirion_uart_sfx6xxx 1.0.0 documentation](https://sensirion.github.io/python-uart-sfx6xxx/) |
| **Software**         | Arduino IDE (https://www.arduino.cc/en/software)             |
| **Python**           | Implemented on qudi-HiM                                      |
| **Resources**        | Device manual: https://www.ni.com/pdf/manuals/375216c.pdf<br />Data sheet NI6259: https://www.ni.com/pdf/manuals/375216c.pdf<br />Function reference: ftp://ftp.ni.com/support/daq/pc/ni-daq/5.1/documents/nidaqFRM.pdf<br />online help for ni DAQmx functions: https://documentation.help/NI-DAQmx-C-Functions/DAQmxStartTask.html |

## Mass Flow Controller: 

| **Model and SN**     | SFC6000D-5slm (000000000DFEC391, 000000000DFEC3A6)           |
| -------------------- | ------------------------------------------------------------ |
| **Drivers location** | pip install sensirion_uart_sfx6xxx                           |
| **Software**         | ControlCenter (available on their site : https://sensirion.com/products/sensor-evaluation/control-center/ ) |
| **Python**           | Python package (pip install sensirion_uart_sfx6xxx) or git (https://github.com/Sensirion/python-uart-sfx6xxx/tree/master) |
| **Resources**        | User instruction:https://github.com/Sensirion/python-uart-sfx6xxx/blob/master/examples/DIY-SFx6xxx-Evaluation-Kit/DIY%20SFx6xxx%20User%20Instructions.pdf<br />Data sheet : https://sensirion.com/resource/datasheet/sfc6000d_sfm6000d<br /> |

