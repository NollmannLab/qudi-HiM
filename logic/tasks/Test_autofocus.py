import os
import numpy as np
from czifile import imread
import matplotlib.pyplot as plt
from scipy.signal import correlate
from scipy.ndimage import laplace
from tqdm import tqdm

dir = r"W:\Marion\2024-01-17"
ref_file = r"Test_focus_BF_ref.czi"
data_file = r"Test_focus_BF_ref-04.czi"
ref = os.path.join(dir, ref_file)
data = os.path.join(dir, data_file)
shape = (512, 4, 512, 4)

movie = imread(data)
print(f'movie shape is {movie.shape}')
n_channel = movie.shape[1]
n_z = movie.shape[2]

ref_movie = imread(ref)
ref_image = ref_movie[0, 0, 25, :, :, 0]
ref_image_bin = ref_image.reshape(shape).mean(-1).mean(1)
ref_image_bin_roi = ref_image_bin[128:384, 128:384]
correlation_ref = correlate(ref_image_bin_roi, ref_image_bin, mode='valid')

correlation_scores = np.zeros((n_z, 2))
for frame in tqdm(range(n_z)):
    new_image = movie[0, 0, frame, :, :, 0]
    new_image_bin = new_image.reshape(shape).mean(-1).mean(1)

    correlation_new = correlate(ref_image_bin_roi, new_image_bin, mode='valid')
    correlation_laplacian = laplace(correlation_new)
    idx = np.argmax(np.abs(correlation_laplacian))
    x, y = np.unravel_index(idx, correlation_laplacian.shape)
    correlation_scores[frame, 0] = frame
    correlation_scores[frame, 1] = correlation_new[x, y] / np.max(correlation_ref)

fig = plt.figure()
plt.plot(correlation_scores[:, 0], correlation_scores[:, 1], '-o')
plt.show()