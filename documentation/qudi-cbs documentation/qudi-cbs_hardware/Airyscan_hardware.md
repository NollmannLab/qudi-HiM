## Camera: 

| **Model and SN**     | Hamamatsu ORCA-Flash4.0 (SN# )                               |
| -------------------- | ------------------------------------------------------------ |
| **Drivers location** | USB key or Hamamatsu website https://dcam-api.com/           |
| **Software**         | HCImageLive                                                  |
| **Python**           | ctypes<br />numpy<br />hamamatsu_python_driver module: from github ZhuangLab and modified to be used as python wrapper for dll<br />dll: dcamapi |
| **Resources**        | Instruction manual: CD ORCA-Flash4.0 V3<br />/mnt/PALM_dataserv/DATA/Qudi_documentation/qudi_cbs_hardware/Hardware_Manuals/Hamamatsu_Camera |



## Translation stage:

| **Model and SN**     | ASI - MS-2000 (SN# ) 2 axes                                  |
| -------------------- | ------------------------------------------------------------ |
| **Drivers location** | CP210x Universal Windows Driver v1.0.1.10 - https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers |
| **Software**         | ASI-CONSOLE - http://www.asiimaging.com/support/downloads/asi-console/ ou /mnt/PALM_dataserv/DATA/Qudi_documentation/qudi_cbs_hardware/PALM/ASI_Console |
| **Python**           | Pyserial<br />Note: Pyserial is imported in a module using 'import serial'.<br />Pyserial is not contained in the original qudi environment. To add it, activate the environment and run conda install pyserial or create the qudi environment based on a yml file containing its current state. <br />In case methods from the pyserial namespace are not available, make sure that pyserial has higher priority than the serial package (contained in the qudi environment), both imported by 'import serial'.<br />Note from 2/09/2021: When installing qudi environment from updated file, pyserial has lower priority because pyserial is installed before serial package. Use conda remove pyserial and then add it again, conda install pyserial, then it takes priority over serial package. |
| **Resources**        | MS2000 Programming manual: http://www.asiimaging.com/downloads/manuals/MS2000%20Programming.pdf |



## DAQ: 

| **Model and SN**     | Measurement Computing DAQ - USB 3104 |
| -------------------- | ------------------------- |
| **Drivers location** | See website                          |
| **Software**         | InstaCal - https://www.mccdaq.com/usb-data-acquisition/USB-3100-Series.aspx                          |
| **Python**           | mcculw package : https://pypi.org/project/mcculw/ or https://anaconda.org/conda-forge/mcculw - this package is not installed by default in qudi                          |
| **Resources**        | Documentation can be found on the measurement computing website : https://www.mccdaq.com/usb-data-acquisition/USB-3100-Series.aspx                          |



## Fluigent Microfluidics:

| **Model and SN**     | Flowboard FLB (SN#)<br />Flowrate Sensor Flowunit L          |
| -------------------- | ------------------------------------------------------------ |
| **Drivers location** | C:\Program Files (x86)\Fluigent_2021                         |
| **Software**         | Fluigent website (Software Platform)                         |
| **Python**           | Download from Fluigent Software Platform (For Lineup & MFCS Series Setups), unzip and run FSP.exe. Default installation creates folder at C:\Program Files (x86)\Fluigent (renamed it in Fluigent_2021 because Fluigent existed already and is used by current Labview Program and/or some desktop shortcuts).<br /><br />Open the anaconda prompt and activate the qudi environment. Navigate to the folder of the Python SDK <br />C:\Program Files (x86)\Fluigent_2021\SDK\fgt-SDK\Python. <br />Run python -m pip install fluigent_sdk-21.0.0.zip. <br />(the command using python -m easy_install did not work)<br />do not use the -user option, installation for all users is fine. <br />Control that fluigent-sdk appears in the package list of qudi environment (conda list)<br />import Fluigent.SDK in the python file. |



## Physik Instrumente 3 axis translation stage:

| **Model and SN**     | PI Controler C-863 Mercury 1-axis translation stage (Z:SN#0185500777 , R:SN#0105500972 ) and C-867 for the rotation stage (SN#111005330)     |
| -------------------- | ------------------------------------------------------------ |
| **Drivers location** | The drivers compatible with windows 10 can be found here : https://www.pifrance.fr/fr/produits/logiciels-dedies-au-positionnement/ |
| **Software**         | PI MikroMove - part of PI software suite (https://www.pifrance.fr/fr/produits/logiciels-dedies-au-positionnement/) |
| **Python**           | PIpython<br />Installation: <br />activate the conda environment (conda activate qudi) and navigate to the folder C:\Users\sCMOS-1\Desktop\PIPython-2.3.0.3 <br />(maybe change the location where the package is kept)<br />Run python setup.py install.<br />Check the installation (conda list), pipython should appear now. |



## Hamilton Modular Valve Positioner:

| **Model and SN**     | Hamilton Modular Valve Positioner                            |
| -------------------- | ------------------------------------------------------------ |
| **Drivers location** | Serial communication protocol in daisychain                  |
| **Software**         | None                                                         |
| **Python**           | Pyserial<br />Note: Pyserial is imported in a module using 'import serial'.<br />Pyserial is not contained in the original qudi environment. To add it, activate the environment and run conda install pyserial or create the qudi environment based on a yml file containing its current state. <br />In case methods from the pyserial namespace are not available, make sure that pyserial has higher priority than the serial package (contained in the qudi environment), both imported by 'import serial'. |
| **Resources**        | User's Manual paper version or pdf                           |


## Lumencor laser source

| **Model and SN**     | Lumencor celesta (SN#18824)                            |
| -------------------- | ------------------------------------------------------------ |
| **Drivers location** | Ethernet communication - an adapter from RJ45 to USB3.0 is used                  |
| **Software**         | Web interface (see website) |                                                         |
| **Python**           | urllib : https://anaconda.org/anaconda/urllib3
| **Resources**        | User's Manual paper version or on website https://lumencor.com/products/celesta-light-engine                           |