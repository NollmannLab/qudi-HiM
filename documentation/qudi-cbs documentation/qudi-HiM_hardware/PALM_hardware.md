## Cameras: 

| **Model and SN**     | ANDOR DU-897 (SN# X-5607)                                    |
| -------------------- | ------------------------------------------------------------ |
| **Drivers location** | Installation disk in the RAMM microscope room (version 2.94.300007.0) - Later version could be granted access when contacting ANDOR. For 64bit Windows, the dll is called **atmcd64d.dll**. The complete path must be indicated in the local config file. |
| **Software**         | SOLIS - /mnt/PALM_dataserv/DATA/Qudi_documentation/qudi_cbs_hardware/PALM |
| **Python**           | numpy, ctypes (available in qudi environment)<br />indicate the dll location in the config file for Qudi-CBS: <br />C:\Program Files\Andor SOLIS\Drivers\atmcd64d.dll |
| **Resources**        | Andor SDK (paper version)                                    |


| **Model and SN**     | ANDOR ULTRA-888 (SN# X-9986)                                                                                                                                                                                      |
| -------------------- |-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Drivers location** | Latest version downloaded after granted acces from ANDOR. local version can be found "C:\Users\admin\Desktop\Programmes et drivers\ANDOR" and after installation "C:\Program Files\Andor SDK\Python\pyAndorSDK2". |
| **Software**         | SOLIS - /mnt/PALM_dataserv/DATA/Qudi_documentation/qudi_cbs_hardware/PALM                                                                                                                                         |
| **Python**           | Latest SDK is already written in python (see instructions at "C:\Program Files\Andor SDK\Python\pyAndorSDK2")                                                                                                     |
| **Resources**        | pdf file in the same folder                                                                                                                                                                                       |


| **Model and SN**     | Thorlabs Camera DCC1545M (SN# 4002843525)                    |
| -------------------- | ------------------------------------------------------------ |
| **Drivers location** | Thorlabs website                                             |
| **Software**         | uc480 Camera Manager                                         |
| **Python**           | ctypes, numpy, uc480_h (thorlabs c dll header file translated to python, distributed by thorlabs), located at qudi-cbs/hardware/camera/thorlabs (same location as the camera module itself) |
| **Resources**        |                                                              |



## Piezo:

| **Model and SN**     | PI Controler E-625 (SN# 110059675) + PIFOC stage (SN# 110060915) |
| -------------------- | ------------------------------------------------------------ |
| **Drivers location** | The drivers compatible with windows 10 can be found here : https://www.pifrance.fr/fr/produits/logiciels-dedies-au-positionnement/ |
| **Software**         | PIMikroMove - part of PI software suite (https://www.pifrance.fr/fr/produits/logiciels-dedies-au-positionnement/) |
| **Python**           | pip install PIPython |
| **Resources **       | https://github.com/PI-PhysikInstrumente/PIPython|



## Translation stage:

| **Model and SN**     | ASI - MS-2000 (SN# 1104-2018-3291)                           |
| -------------------- | ------------------------------------------------------------ |
| **Drivers location** | CP210x Universal Windows Driver v1.0.1.10 - https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers |
| **Software**         | ASI-CONSOLE - http://www.asiimaging.com/support/downloads/asi-console/ ou /mnt/PALM_dataserv/DATA/Qudi_documentation/qudi_cbs_hardware/PALM/ASI_Console |
| **Python**           | Pyserial<br />Note: Pyserial is imported in a module using 'import serial'.<br />Pyserial is not contained in the original qudi environment. To add it, activate the environment and run conda install pyserial or create the qudi environment based on a yml file containing its current state. <br />In case methods from the pyserial namespace are not available, make sure that pyserial has higher priority than the serial package (contained in the qudi environment), both imported by 'import serial'.<br />Note from 2/09/2021: When installing qudi environment from updated file, pyserial has lower priority because pyserial is installed before serial package. Use conda remove pyserial and then add it again, conda install pyserial, then it takes priority over serial package. |
| **Resources**        | MS2000 Programming manual: http://www.asiimaging.com/downloads/manuals/MS2000%20Programming.pdf |



## DAQ: 

| **Model and SN**     | NI - PCIe-6259 (SN# 0154CEE7)                                |
| -------------------- | ------------------------------------------------------------ |
| **Drivers location** | NI-DAQmx version 15.0.0f2<br />C:\Program Files\National Instruments\MAX<br />install LabView academic license M77X00561 (NI-MAX module) available at the CBS |
| **Software**         | NI-MAX but requires a LabView license                        |
| **Python**           | PyDAQmx (already available in Qudi) (runs only on systems where NI-DAQ dll is available) |
| **Resources**        | Device manual: https://www.ni.com/pdf/manuals/375216c.pdf<br />Data sheet NI6259: https://www.ni.com/pdf/manuals/375216c.pdf<br />Function reference: ftp://ftp.ni.com/support/daq/pc/ni-daq/5.1/documents/nidaqFRM.pdf<br />online help for ni DAQmx functions: https://documentation.help/NI-DAQmx-C-Functions/DAQmxStartTask.html |



## Filter wheels:

| **Model and SN**     | Thorlabs - FW-102C                                           |
| -------------------- | ------------------------------------------------------------ |
| **Drivers location** | Thorlabs website                                             |
| **Software**         | https://www.thorlabs.com/software_pages/ViewSoftwarePage.cfm?Code=FW102C<br />FW102C |
| **Python**           | PyVisa<br />package is contained in Qudi environment         |
| **Resources**        | Operating manual https://www.thorlabs.com/drawings/8e3f2f1caffad674-4206500D-E04A-3264-0D3803EDD1833C73/FW102B-Manual.pdf |

| **Model and SN**     | Thorlabs FW-103 High-Speed Motorized Filter Wheel and Thorlabs APT Motor BSC201 (SN # 40846334) |
| -------------------- | ------------------------------------------------------------ |
| **Drivers location** | Thorlabs website                                             |
| **Software**         | https://www.thorlabs.com/software_pages/ViewSoftwarePage.cfm?Code=Motion_Control<br /> |
| **Python**           | thorlabs_apt (Python wrapper for APT.dll on Windows)<br />Installation: <br />Activate the qudi environment (in an Anaconda prompt)<br />run: pip install thorlabs-apt<br />Install the Thorlabs' APT software: https://www.thorlabs.com/software_pages/ViewSoftwarePage.cfm?Code=Motion_Control<br />Copy the file APT.dll from Apt installation path\APT Server to Windows\System32 <br />(copying in the anaconda3 thorlabs_apt folder resulted in file not found error) |
| **Resources**        | https://github.com/qpit/thorlabs_apt                         |

