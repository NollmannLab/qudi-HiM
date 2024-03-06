import os
import numpy as np
from czifile import imread
import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1 import make_axes_locatable
from scipy.signal import correlate
from scipy.ndimage import laplace, gaussian_filter, median_filter
from tqdm import tqdm
from time import time

dir = r"W:\jb\2024-03-06\test-9.czi\test-9_AcquisitionBlock1.czi"
data_file = r"test-9_AcquisitionBlock1_pt5.czi"
data = os.path.join(dir, data_file)
ref_file = r"W:\jb\2024-03-06\test-9.czi\metadata\autofocus_reference.npy"
ref_number = 2
shape = (1024, 2, 1024, 2)
# shape = (512, 4, 512, 4)

movie = imread(data)
print(f'movie shape is {movie.shape}')
n_channel = movie.shape[1]
if len(movie.shape) == 6:
    n_z = movie.shape[2]
elif len(movie.shape) == 5:
    n_z = 1

ref = np.load(ref_file)
ref_image = ref[ref_number, :, :]
ref_image_bin = ref_image.reshape(shape).mean(-1).mean(1)
ref_image_bin = ref_image_bin - gaussian_filter(ref_image_bin, sigma=10)
ref_image_bin_roi = ref_image_bin[262:762, 262:762]
# ref_image_bin_roi = ref_image_bin[128:384, 128:384]
correlation_ref = correlate(ref_image_bin_roi, ref_image_bin, mode='valid')
# correlation_ref = correlation_ref - gaussian_filter(correlation_ref, sigma=10)

correlation_scores = np.zeros((n_z, 2))
correlation_new_all = np.zeros((n_z, 525, 525))
for frame in tqdm(range(n_z)):
    if len(movie.shape) == 6:
        new_image = movie[0, 0, frame, :, :, 0]
    elif len(movie.shape) == 5:
        new_image = movie[0, 0, :, :, 0]
    new_image_bin = new_image.reshape(shape).mean(-1).mean(1)
    new_image_bin = new_image_bin - gaussian_filter(new_image_bin, sigma=10)

    correlation_new = correlate(ref_image_bin_roi, new_image_bin, mode='valid')
    # correlation_new = correlation_new - gaussian_filter(correlation_new, sigma=10)
    correlation_new_all[frame, :, :] = correlation_new
    correlation_laplacian = laplace(correlation_new)
    idx = np.argmax(np.abs(correlation_laplacian))
    x, y = np.unravel_index(idx, correlation_laplacian.shape)
    correlation_scores[frame, 0] = frame
    correlation_scores[frame, 1] = correlation_new[x, y] / np.max(correlation_ref)

best_frame = np.argmax(correlation_scores[:, 1])

fig, axs = plt.subplots(2, 2)
im0 = axs[0, 0].imshow(correlation_ref)
axs[0, 0].set_title('Correlation map ref')
divider = make_axes_locatable(axs[0, 0])
cax = divider.append_axes('right', size='5%', pad=0.05)
fig.colorbar(im0, cax=cax, orientation='vertical')

im0_ref = axs[0, 1].imshow(ref_image_bin)
axs[0, 1].set_title('reference image')
divider = make_axes_locatable(axs[0, 1])
cax = divider.append_axes('right', size='5%', pad=0.05)
fig.colorbar(im0, cax=cax, orientation='vertical')

im1 = axs[1, 0].imshow(correlation_new_all[best_frame, :, :])
axs[1, 0].set_title('Correlation map new')
divider = make_axes_locatable(axs[1, 0])
cax = divider.append_axes('right', size='5%', pad=0.05)
fig.colorbar(im1, cax=cax, orientation='vertical')

if len(movie.shape) == 6:
    im2 = axs[1, 1].imshow(movie[0, 0, best_frame, :, :, 0])
elif len(movie.shape) == 5:
    im2 = axs[1, 1].imshow(movie[0, 0, :, :, 0])
im2 = axs[1, 1].imshow(new_image_bin)
axs[1, 1].set_title('In focus image')
divider = make_axes_locatable(axs[1, 1])
cax = divider.append_axes('right', size='5%', pad=0.05)
fig.colorbar(im2, cax=cax, orientation='vertical')
plt.show()

fig = plt.figure()
plt.plot(correlation_scores[:, 0], correlation_scores[:, 1], '-o')
plt.show()