## Cameras: 

| **Model and SN**     | ANDOR DU-897 (SN# ) and ANDOR  DU-897 (SN#)                  |
| -------------------- | ------------------------------------------------------------ |
| **Drivers location** | Installation disk in the RAMM microscope room (version 2.94.300007.0) - Later version could be granted access when contacting ANDOR. For 64bit Windows, the dll is called **atmcd64d.dll**. The complete path must be indicated in the local config file.<br />(dll file can also be found on github: https://github.com/SivyerLab/pyandor/blob/master/atmcd64d.dll) |
| **Software**         | SOLIS - /mnt/PALM_dataserv/DATA/Qudi_documentation/qudi_cbs_hardware/PALM |
| **Python**           | numpy, ctypes (available in qudi environment)<br />indicate the dll location in the config file for Qudi-CBS: <br />C:\Program Files\Andor SOLIS\Drivers\atmcd64d.dll |
| **Resources**        | Andor SDK (paper version) or https://neurophysics.ucsd.edu/Manuals/Andor%20Technology/Andor_Software_Development_Kit.pdf |



| **Model and SN**     | Thorlabs Camera DCC1545M???? (SN# ),                         |
| -------------------- | ------------------------------------------------------------ |
| **Drivers location** | Thorlabs website                                             |
| **Software**         | uc480 Camera Manager                                         |
| **Python**           | ctypes, numpy, uc480_h (thorlabs c dll header file translated to python, distributed by thorlabs), located at qudi-cbs/hardware/camera/thorlabs (same location as the camera module itself) |
| **Resources**        |                                                              |



## Piezo:

| **Model and SN**     | Mad City Labs NanoDrive (SN# )                               |
| -------------------- | ------------------------------------------------------------ |
| **Drivers location** | C:\Program Files\Mad City Labs\NanoDrive\Madlib.dll<br />Contacts : ferdi@madcitylabs.eu |
| **Software**         | No custom software provided                                  |
| **Python**           | ctypes<br />Specify the path to the dll in local configuration file for Qudi:<br />C:\Program Files\Mad City Labs\NanoDrive\Madlib.dll<br /><br />it is needed to define the return type for some dll functions |
| **Resources**        | https://labcit.ligo.caltech.edu/~costheld/photos/steve%27s_cable_folder/Altium-Ligo/Schematics/Mad%20City%20Labs%20MCL%20PZT%20Controller/T1100296_v1%20-%20Nano-Drive85%20Manual%20(NPS)%20v2_for_MTA2X.pdf<br />dll reference:<br />Madlib_1_8.doc [C:\Program Files\Mad City Labs\NanoDrive\Madlib_1_8.doc] |



## Translation stage:

| **Model and SN**     | PI Controler C-663.11 Mercury (SN# 0019550121, SN# 0019550124) 2 axes |
| -------------------- | ------------------------------------------------------------ |
| **Drivers location** | The drivers compatible with windows 10 can be found here : https://www.pifrance.fr/fr/produits/logiciels-dedies-au-positionnement/ |
| **Software**         | PI MikroMove - part of PI software suite (https://www.pifrance.fr/fr/produits/logiciels-dedies-au-positionnement/) |
| **Python**           | PIpython<br />Installation: <br />activate the conda environment (conda activate qudi) and navigate to the folder C:\Users\sCMOS-1\Desktop\PIPython-2.3.0.3 <br />(maybe change the location where the package is kept)<br />Run python setup.py install.<br />Check the installation (conda list), pipython should appear now. |



## DAQ: 

| **Model and SN**     | NI - PCIe-???? (X-Series) (SN#)                              |
| -------------------- | ------------------------------------------------------------ |
| **Drivers location** | NI-DAQmx version 15.0.0f2<br />C:\Program Files\National Instruments\MAX<br />install LabView academic license M77X00561 (NI-MAX module) available at the CBS |
| **Software**         | NI-MAX but requires a LabView license                        |
| **Python**           | PyDAQmx (already available in Qudi) (runs only on systems where NI-DAQ dll is available) |
| **Resources**        | Device manual: https://www.ni.com/pdf/manuals/375216c.pdf<br />Function reference: ftp://ftp.ni.com/support/daq/pc/ni-daq/5.1/documents/nidaqFRM.pdf<br />online help for ni DAQmx functions: https://documentation.help/NI-DAQmx-C-Functions/DAQmxStartTask.html |



## Filter wheel:

| **Model and SN**     | Thorlabs - FW-102C (??)                                      |
| -------------------- | ------------------------------------------------------------ |
| **Drivers location** | Thorlabs website                                             |
| **Software**         | https://www.thorlabs.com/software_pages/ViewSoftwarePage.cfm?Code=FW102C<br />FW102C |
| **Python**           | PyVisa<br />package is contained in Qudi environment         |
| **Resources**        | Operating manual https://www.thorlabs.com/drawings/8e3f2f1caffad674-4206500D-E04A-3264-0D3803EDD1833C73/FW102B-Manual.pdf |

