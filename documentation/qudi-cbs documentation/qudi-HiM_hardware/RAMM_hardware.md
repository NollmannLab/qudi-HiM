## Cameras: 

| **Model and SN**     | Hamamatsu ORCA-Flash4.0 (SN# 300385)                                                                                                             |
| -------------------- |--------------------------------------------------------------------------------------------------------------------------------------------------|
| **Drivers location** | USB key or Hamamatsu website https://dcam-api.com/                                                                                               |
| **Software**         | HCImageLive (ready to install here:  PALM_dataserv\Commun\Resources_RAMM_HiM_setup\Hamamatsu)                                                    |
| **Python**           | ctypes<br />numpy<br />hamamatsu_python_driver module: from github ZhuangLab and modified to be used as python wrapper for dll<br />dll: dcamapi |
| **Resources**        | Instruction manual: CD ORCA-Flash4.0 V3<br                                                                                                       |



| **Model and SN**     | Thorlabs Camera DCC1545M (SN# 4002843525)                                                                                                                                                   |
| -------------------- |---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Drivers location** | Thorlabs website                                                                                                                                                                            |
| **Software**         | uc480 Camera Manager (ready to install here : PALM_dataserv\Commun\Resources_RAMM_HiM_setup\ThorCam_V3.6.2   )                                                                              |
| **Python**           | ctypes, numpy, uc480_h (thorlabs c dll header file translated to python, distributed by thorlabs), located at qudi-cbs/hardware/camera/thorlabs (same location as the camera module itself) |
| **Resources**        |                                                                         |


| **Model and SN**     | Teledyn Kinetix (SN# A22H723042)                                                                                                                                                                             |
| -------------------- |--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Drivers location** | Teledyne website (ready to install from here : PALM_dataserv\Commun\Resources_RAMM_HiM_setup\Kinetix)                                                                                                        |
| **Software**         | The PVCAM software for test should be used and can be downloaded from the wabsite ready to install from here : PALM_dataserv\Commun\Resources_RAMM_HiM_setup\Kinetix)                                        |
| **Python**           | Same for the python software (ready to install from here : PALM_dataserv\Commun\Resources_RAMM_HiM_setup\Kinetix). Note that PVCAM_SDK and Virtual C++ studio 14.0 are required for installation.            |
| **Resources**        | For PVCAM python see here: https://github.com/Photometrics/PyVCAM <br/> The manual for PVCAM SDK is directly accessible on the computer : C:\ProgramData\Microsoft\Windows\Start Menu\Programs\PVCam SDK |




## Piezo:

| **Model and SN**     | Mad City Labs NanoDrive (SN# 2133)                                                                                                                                                                              |
| -------------------- |-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Drivers location** | C:\Program Files\Mad City Labs\NanoDrive\Madlib.dll<br />Contacts : ferdi@madcitylabs.eu                                                                                                                        |
| **Software**         | No custom software provided                                                                                                                                                                                     |
| **Python**           | ctypes<br />Specify the path to the dll in local configuration file for Qudi:<br />C:\Program Files\Mad City Labs\NanoDrive\Madlib.dll<br /><br />it is needed to define the return type for some dll functions |
| **Resources**        | USB key with the software and manual is stored in the Airyscan room                                                                                                                                             |



## Translation stage:

| **Model and SN**     | ASI - MS-2000 (SN# 1404-2769-0000-000) 3 axes                |
| -------------------- | ------------------------------------------------------------ |
| **Drivers location** | CP210x Universal Windows Driver v1.0.1.10 - https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers |
| **Software**         | ASI-CONSOLE - http://www.asiimaging.com/support/downloads/asi-console/ ou /mnt/PALM_dataserv/DATA/Qudi_documentation/qudi_cbs_hardware/PALM/ASI_Console |
| **Python**           | Pyserial<br />Note: Pyserial is imported in a module using 'import serial'.<br />Pyserial is not contained in the original qudi environment. To add it, activate the environment and run conda install pyserial or create the qudi environment based on a yml file containing its current state. <br />In case methods from the pyserial namespace are not available, make sure that pyserial has higher priority than the serial package (contained in the qudi environment), both imported by 'import serial'. |
| **Resources**        | MS2000 Programming manual: http://www.asiimaging.com/downloads/manuals/MS2000%20Programming.pdf |



## FPGA:

| **Model and SN**     | NI - RIO FPGA Device NI PCIe-7841R "RIO0" (SN# 01CC37E6) carte RMI0                                                                                                                                                                                                                           |
| -------------------- |-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Drivers location** | install LabView academic license M77X00561 (FPGA module) available at the CBS - when installing, specifically check for the drivers fro Xilink and RIO-R serie. These drivers are essential for our FPGA.                                                                                     |
| **Software**         | NI-MAX (requires LabView license)                                                                                                                                                                                                                                                             |
| **Python**           | nifpga<br />install via pip install nifpga <br />(not found on default conda channels)<br />Specify the resource address in local configuration file for Qudi: RIO0<br />Specify bitfile path in local configuration file for Qudi. <br /><br />Labview 2015 (32-bit) needed to edit bitfiles |



## DAQ: 

| **Model and SN**     | NI - PCIe-6259 (SN# )                                        |
| -------------------- | ------------------------------------------------------------ |
| **Drivers location** | NI-DAQmx version 15.0.0f2<br />C:\Program Files\National Instruments\MAX<br />install LabView academic license M77X00561 (NI-MAX module) available at the CBS |
| **Software**         | NI-MAX but requires a LabView license                        |
| **Python**           | PyDAQmx (already available in Qudi) (runs only on systems where NI-DAQ dll is available) |
| **Resources**        | Device manual: https://www.ni.com/pdf/manuals/375216c.pdf<br />Data sheet NI6259: https://www.ni.com/pdf/manuals/375216c.pdf<br />Function reference: ftp://ftp.ni.com/support/daq/pc/ni-daq/5.1/documents/nidaqFRM.pdf<br />online help for ni DAQmx functions: https://documentation.help/NI-DAQmx-C-Functions/DAQmxStartTask.html |



## Fluigent Microfluidics:

| **Model and SN**     | Flowboard FLB (SN#818)<br />Pump MFCS-EZ (SN# 1241)  <br />Flowrate Sensor Flowunit L                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| -------------------- |----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Drivers location** | C:\Program Files (x86)\Fluigent_2021                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| **Software**         | Fluigent website (Software Platform is ready to install here : PALM_dataserv\Commun\Resources_RAMM_HiM_setup\Fluidgent)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| **Python**           | Download from Fluigent Software Platform (For Lineup & MFCS Series Setups), unzip and run FSP.exe. Select the default installation (tried to install only SDK but this never worked). Possibly more than one try is needed to achieve a correct installation. Default installation creates folder at C:\Program Files (x86)\Fluigent (renamed it in Fluigent_2021 because Fluigent existed already and is used by current Labview Program and/or some desktop shortcuts).<br /><br />Open the anaconda prompt and activate the qudi environment. Navigate to the folder of the Python SDK <br />C:\Program Files (x86)\Fluigent_2021\SDK\fgt-SDK\Python. <br />Run python -m pip install fluigent_sdk-19.0.0.zip. <br />(the command using python -m easy_install did not work)<br />do not use the -user option, installation for all users is fine. <br />Control that fluigent-sdk appears in the package list of qudi environment (conda list)<br /><br />*Note (from march 2, 2021): FSP.exe seems to give access to the version 19.0.0 of the SDK even though an update is proposed. I tried multiple times to rerun the installation with the update to have the latest version 20.0.0 but this always ended up in an incomplete installation with a missing SDK. As everything seems to work with the 19.0.0 version, this one can be used.* <br /><br />import Fluigent.SDK in the python file. |



## Physik Instrumente 3 axis translation stage:

| **Model and SN**     | PI Controler C-863 Mercury (SN# 0019550121, SN# 0019550124 , SN# 0019550119)                                                                                                                                                                                                                                                        |
| -------------------- |-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Drivers location** | The drivers compatible with windows 10 can be found here : https://www.pifrance.fr/fr/produits/logiciels-dedies-au-positionnement/                                                                                                                                                                                                  |
| **Software**         | PI MikroMove - part of PI software suite (https://www.pifrance.fr/fr/produits/logiciels-dedies-au-positionnement/) - As from 2024, you need to register first to PI before having access to the downloading page. The latest version of the software and drivers are stored here : PALM_dataserv\Commun\Resources_RAMM_HiM_setup\PI |
| **Python**           | PIpython<br />Installation: <br />activate the conda environment (conda activate qudi) and navigate to the folder C:\Users\sCMOS-1\Desktop\PIPython-2.3.0.3 <br />(maybe change the location where the package is kept)<br />Run python setup.py install.<br />Check the installation (conda list), pipython should appear now.     |



## Hamilton Modular Valve Positioner:

| **Model and SN**     | Hamilton Modular Valve Positioner                            |
| -------------------- | ------------------------------------------------------------ |
| **Drivers location** | Serial communication protocol in daisychain                  |
| **Software**         | None                                                         |
| **Python**           | Pyserial<br />Note: Pyserial is imported in a module using 'import serial'.<br />Pyserial is not contained in the original qudi environment. To add it, activate the environment and run conda install pyserial or create the qudi environment based on a yml file containing its current state. <br />In case methods from the pyserial namespace are not available, make sure that pyserial has higher priority than the serial package (contained in the qudi environment), both imported by 'import serial'. |
| **Resources**        | User's Manual paper version or pdf                           |


## Lumencor laser source

| **Model and SN**     | Lumencor celesta (SN#29108)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| -------------------- |--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Drivers location** | Ethernet communication (with a dedicated Ethernet card)                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| **Software**         | Web interface (see manual). To access it, the IP address of the ethernet card needs to be set to 192.168.201.201. To change it manually, use "parameters/network and  interfaces/Network center and sharing" or open a file explorer window, right-click on network and select properties. A new window opens. Select the network dedicated to the Lumencor and go to properties. Unselect internet protocol IPv6 and modify the properties associated to IPv4 (IP address 192.168.201.201 and sub-network mask 255.255.255.0) |                                                         |
| **Python**           | urllib : https://anaconda.org/anaconda/urllib3                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 
| **Resources**        | User's Manual paper (PALM_dataserv\Commun\Resources_RAMM_HiM_setup) version or on website https://lumencor.com/products/celesta-light-engine                                                                                                                                                                                                                                                                                                                                                                                   |