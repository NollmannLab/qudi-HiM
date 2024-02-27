import numpy as np
from PIL import Image
import time
from tifffile import TiffWriter
import os
import cv2

n_frames = 60
n_repeat = 10
saving_time = np.zeros((n_repeat,))
size = (2048, 2048)
A = np.zeros((2048, 2048, n_frames))
os.chdir('/home/jb/Desktop/Data_HiM_Olivier/')

## Numpy method
# for n in range(n_repeat):
#     t0 = time.time()
#     np.save('test_full_matrix.npy', A)
#     t1 = time.time()
#     saving_time[n] = t1 - t0
# print(f'Saving time : {np.mean(saving_time)} +/- {np.std(saving_time)}')

##  pillow
A = A.astype(np.uint16)
for n in range(n_repeat):
    t0 = time.time()
    imlist = []  # this will be a list of pillow Image objects
    for i in range(n_frames):
        img_out = Image.new('I;16', size)  # initialize a new pillow object of the right size
        outpil = A[:,:,i].astype(
            A.dtype.newbyteorder("<")).tobytes()  # convert the i-th frame to bytes object
        img_out.frombytes(outpil)  # create pillow object from bytes
        imlist.append(img_out)  # create the list of pillow image objects
    imlist[0].save('test_full_matrix_PIL.tif', save_all=True, append_images=imlist[1:])
    t1 = time.time()
    saving_time[n] = t1 - t0
print(f'Saving time : {np.mean(saving_time)} +/- {np.std(saving_time)}')

## Tifffile
# for n in range(n_repeat):
#     t0 = time.time()
#     with TiffWriter('test_full_matrix_tifffile.tif') as tif:
#         tif.save(A)
#     t1 = time.time()
#     saving_time[n] = t1 - t0
# print(f'Saving time : {np.mean(saving_time)} +/- {np.std(saving_time)}')

## scikit
for n in range(n_repeat):
    t0 = time.time()

    t1 = time.time()
    saving_time[n] = t1 - t0
print(f'Saving time : {np.mean(saving_time)} +/- {np.std(saving_time)}')

## opencv
# for n in range(n_repeat):
#     t0 = time.time()
#     for i in range(n_frames):
#         im = A[:,:,i].astype(np.uint16)
#         cv2.imwrite('out.tif', im)
#     t1 = time.time()
#     saving_time[n] = t1 - t0
# print(f'Saving time : {np.mean(saving_time)} +/- {np.std(saving_time)}')

