## TO RUN WITH pyHIM env

import numpy as np
import os
import yaml
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from tifffile import imread
from photutils.detection import DAOStarFinder
# from astropy.visualization.mpl_normalize import ImageNormalize
# from photutils.aperture import CircularAperture
# from astropy.visualization import SqrtStretch

# define the geometry of the mosaic and where the data are stored
directory = r'/mnt/grey/DATA/users/JB/Test_FTL/2022_03_18/022_Hubble_test_jb'
n_roi = 200  # total number of rois
n_step = 1  # use only for the FTL to indicate the number of repeats
n_plane = 7  # indicate the number of planes for each stack
experiment = 'Hubble'  # 'FTL'

# ----------------------------------------------------------------------------------------------------------------------
# Code use to read the log file
# ----------------------------------------------------------------------------------------------------------------------

read_log_file = False
if read_log_file:

    log_path = os.path.join(directory, 'log_info.log')
    with open(log_path, 'r') as f:
        logs = f.readlines()

    # example of application : read the execution time for the function acquire_single_stack
    time = []
    for log in logs:
        if log.find('runTask') != -1:
            idx = log.find('execution time = ')
            time.append(float(log[idx+17:-2]))

    time = np.array(time)
    print(np.mean(time), np.std(time))

# ----------------------------------------------------------------------------------------------------------------------
# Code use to read the calibration file and plot the comparison between the fit and the autofocus measurements
# ----------------------------------------------------------------------------------------------------------------------

read_calibration_file = False
if read_calibration_file:

    fig = plt.figure(figsize=(16, 10))
    ax = fig.add_subplot()

    # open the calibration file and load the calibration data
    calibration_path = os.path.join(directory, 'tilt_surface_calibration.yml')
    with open(calibration_path, 'r') as stream:
        data = yaml.safe_load(stream)

    # load the data and convert them into numpy array (necessary if you need to perform calculation on them)
    z_compare_calibration = np.array(data['z_compare'])
    x_calibration = np.array(data['x'])
    y_calibration = np.array(data['y'])
    z_calibration = np.array(data['z'])

    # plot the results to inspect if the values were reproducible
    roi = np.linspace(1, len(x_calibration), len(x_calibration))
    plt.clf()
    plt.plot(roi, z_compare_calibration)
    plt.xlabel('ROI number')
    plt.ylabel('z (in µm)')
    plt.legend({'calibration'})
    ax.set_box_aspect(1)
    plt.show()

# ----------------------------------------------------------------------------------------------------------------------
# Code use to analyse the FTL or hubble stacks when working on a sample of fluorescent beads. A MIP is calculated and
# the positions of all the beads is inferred. Then, based on the maximum of intensity, the focal plane of each object is
# calculated. The results are compiled into a graph in order to check for the stability of the focal plane as a function
# of the roi position and the cycle number.
# ----------------------------------------------------------------------------------------------------------------------

plot_focal_plane = True
if plot_focal_plane:

    fig = plt.figure(figsize=(16, 10))
    ax = fig.add_subplot(1, 1, 1)

    focal_plane = np.zeros((n_roi, n_step))
    focal_plane_std = np.zeros((n_roi, n_step))

    for step in range(n_step):

        for roi in range(n_roi):

            roi_path = os.path.join(directory, "channel_0",  f"ROI_{str(roi+1).zfill(3)}")
            if experiment == 'Hubble':
                file_name = f"hubble_ROI_{str(roi+1).zfill(3)}_ch_000.tif"
            else:
                file_name = f"TL_ROI_{str(roi + 1).zfill(3)}_ch_000_step_{str(step + 1).zfill(3)}.tif"

            hubble_file = os.path.join(roi_path, file_name)
            print(file_name)
            stack = imread(hubble_file)

            stack_mip = np.max(stack, axis=0)
            daofind = DAOStarFinder(fwhm=3.0, threshold=500)
            sources = daofind(stack_mip - 100)
            positions = np.transpose((sources['xcentroid'], sources['ycentroid']))
            # apertures = CircularAperture(positions, r=4.)
            # norm = ImageNormalize(stretch=SqrtStretch())
            # plt.imshow(stack_mip, cmap='Greys', origin='lower', norm=norm, interpolation='nearest')
            # apertures.plot(color='blue', lw=1.5, alpha=0.5)
            # plt.show()
            x = positions[:, 1]
            y = positions[:, 0]
            intensity = stack[:, x.astype('int'), y.astype('int')]
            index = np.argmax(intensity, axis=0)
            focal_plane[roi, step] = np.mean(index)
            focal_plane_std[roi, step] = np.std(index)

        rois = np.linspace(1, n_roi, n_roi)
        plt.plot(rois, focal_plane[:, step], '-o')
        # plt.errorbar(rois, focal_plane[:, step], yerr=focal_plane_std[:, step])

    ax.set_xlabel('roi #')
    ax.set_ylabel('focal plane #')
    plt.ylim([0, n_plane-1])
    ax.set_box_aspect(1)
    plt.show()

# ----------------------------------------------------------------------------------------------------------------------
# Code use to analysis the calibration curve of the hubble or FTL and plot the 3D surface representation of the sample
# ----------------------------------------------------------------------------------------------------------------------

plot_calibration_surface = False
if plot_calibration_surface:

    # Calculate the dz plot
    file_path = r'/mnt/grey/DATA/RAMM/2022_03_01/003_Hubble_test_jb/tilt_surface_calibration.yml'
    with open(file_path, 'r') as stream:
        data = yaml.safe_load(stream)

    x = data['x']
    y = data['y']
    z = data['z_compare']
    coeff = data['coeff_fit']
    z_std = data['z_compare']
    x = np.asarray(x)
    y = np.asarray(y)
    z = np.asarray(z)
    z_std = np.asarray(z_std)

    z_std_min = np.min(z_std)
    z_std_max = np.max(z_std)
    z_std_average = np.mean(z_std)
    z_std_std = np.std(z_std)
    print(f'min: {z_std_min} - max : {z_std_max} - mean : {z_std_average} - std : {z_std_std}')

    x_min = np.min(x)
    x_max = np.max(x)
    y_min = np.min(y)
    y_max = np.max(y)

    x_mesh = np.linspace(x_min, x_max, num=10)
    y_mesh = np.linspace(y_min, y_max, num=10)
    x_mesh, y_mesh = np.meshgrid(x_mesh, y_mesh)

    A = np.array([x * 0 + 1, x, y, x ** 2, y ** 2, x * y ** 2, x * y]).T
    B = z
    coeff, r, rank, s = np.linalg.lstsq(A, B, rcond=None)
    z_fit = coeff[0] * ( x_mesh * 0 + 1 ) + coeff[1] * x_mesh + coeff[2] * y_mesh + coeff[3] * x_mesh**2 + \
            coeff[4] * y_mesh**2 + coeff[5] * x_mesh * y_mesh ** 2 + coeff[6] * x_mesh * y_mesh

    print(f'coeff : {coeff}')
    print(f'r : {r}')
    print(f'rank : {rank}')
    print(f's : {s}')

    fig = plt.figure()
    ax = fig.add_subplot(1, 1, 1, projection='3d')

    surf = ax.plot_surface(x_mesh, y_mesh, z_fit, rstride=1, cstride=1, cmap=cm.coolwarm,
                           linewidth=0, antialiased=False)
    fig.colorbar(surf, shrink=0.5, aspect=10)
    ax.set_xlabel('Position (µm)')
    ax.set_ylabel('Position (µm)')
    ax.set_zlabel('Focal plane (µm)')
    plt.show()

    z_fit = coeff[0] * (x * 0 + 1) + coeff[1] * x + coeff[2] * y + coeff[3] * x ** 2 + \
            coeff[4] * y ** 2 + coeff[5] * x * y ** 2 + coeff[5] * x * y
    z_compare = z - z_fit
    print(z_compare)