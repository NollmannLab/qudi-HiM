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
| **Resources**        | Device manual papersheet<br />Get started : https://docs.arduino.cc/hardware/uno-rev3/ |

## Mass Flow Controller: 

| **Model and SN**     | SFC6000D-5slm (SN#000000000DFEC391, SN#000000000DFEC3A6)     |
| -------------------- | ------------------------------------------------------------ |
| **Drivers location** | pip install sensirion_uart_sfx6xxx                           |
| **Software**         | ControlCenter (available on their site : https://sensirion.com/products/sensor-evaluation/control-center/ ) |
| **Python**           | Python package (pip install sensirion_uart_sfx6xxx) or git (https://github.com/Sensirion/python-uart-sfx6xxx/tree/master) Implemented on qudi-HiM |
| **Resources**        | User instruction:https://github.com/Sensirion/python-uart-sfx6xxx/blob/master/examples/DIY-SFx6xxx-Evaluation-Kit/DIY%20SFx6xxx%20User%20Instructions.pdf<br />Data sheet : https://sensirion.com/resource/datasheet/sfc6000d_sfm6000d<br /> |

## Valves: 

| **Model and SN** | Inline 4 x 2-way Normally Closed 225T082 (SN#1348134, SN#1348135) |
| ---------------- | ------------------------------------------------------------ |
| **Ressources**   | Datasheet : https://www.nresearch.com/Images/Valves/PDF/225T082.pdf |
| **Model and SN** | **3-ways isolation Normally Closed 360T031 (SN#1258142)**    |
| **Ressources**   | Datasheet : https://www.nresearch.com/Images/Valves/PDF/360T031.pdf |
| **Model and SN** | **Double 3-way 360T042 (SN#1348076)**                        |
| **Ressources**   | Datasheet : https://www.nresearch.com/Images/Valves/PDF/NRCatalogPage07.pdf |
| **Python**       | All Implemented on qudi-HiM                                  |

## Optocouleur: 

| **Model and SN** | Power Optocoupleur 4-channel OK4-2 (x3)           |
| ---------------- | ------------------------------------------------- |
| **Python**       | Implemented on qudi-HiM                           |
| **Resources**    | Datasheet : https://www.leg-gmbh.de/en/OK4-en.pdf |

