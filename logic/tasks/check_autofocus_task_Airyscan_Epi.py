# -*- coding: utf-8 -*-
"""
Qudi-CBS

An extension to Qudi.

This module contains a task to check that the autofocus is properly calibrated and will work correctly for the selected
sample.

@author: JB. Fiche

Created on Wed July 31 2024
-----------------------------------------------------------------------------------

Qudi is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Qudi is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Qudi. If not, see <http://www.gnu.org/licenses/>.

Copyright (c) the Qudi Developers. See the COPYRIGHT.txt file at the
top-level directory of this distribution and at <https://github.com/Ulm-IQO/qudi/>
-----------------------------------------------------------------------------------
"""
import numpy as np
import os
import yaml
import re
import matplotlib.pyplot as plt
from time import sleep
from datetime import datetime
from logic.generic_task import InterruptableTask
from logic.task_helper_functions import get_entry_nested_dict
from logic.task_logging_functions import write_dict_to_file
from glob import glob
from tqdm import tqdm
from czifile import imread
from scipy.signal import correlate
from scipy.ndimage import laplace, gaussian_filter


class Task(InterruptableTask):  # do not change the name of the class. it is always called Task !
    """ This task iterates over all roi given in a file and acquires a series of planes in z direction
    using a sequence of lightsources for each plane, for each roi.

    Config example pour copy-paste:

        ROIMulticolorScanTask:
            module: 'roi_multicolor_scan_task_AIRYSCAN'
            needsmodules:
                laser: 'lasercontrol_logic'
                daq: 'daq_logic'
                roi: 'roi_logic'
            config:
                path_to_user_config: 'C:/Users/MFM/qudi_files/qudi_task_config_files/ROI_multicolor_scan_task_AIRYSCAN.yml'
                IN7_ZEN : 0
                OUT7_ZEN : 1
                OUT8_ZEN : 3
                camera_global_exposure : 2
    """
    # ==================================================================================================================
    # Generic Task methods
    # ==================================================================================================================

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.user_config_path = self.config['path_to_user_config']
        print("Path to user config file : {}".format(self.user_config_path))
        self.roi_counter = None
        self.directory = None
        self.user_param_dict = {}
        self.sample_name = None
        self.num_z_planes = None
        self.roi_list_path = None
        self.roi_names = []
        self.IN7_ZEN = self.config['IN7_ZEN']
        self.OUT7_ZEN = self.config['OUT7_ZEN']
        self.OUT8_ZEN = self.config['OUT8_ZEN']
        self.prefix = None
        self.zen_directory: str = ""
        self.zen_ref_images_path: str = ""
        self.zen_saving_path: str = ""
        self.focus_ref_images: iter = None

    def startTask(self):
        """ """
        self.log.info('started Task')

        # stop all interfering modes on GUIs and disable GUI actions
        self.ref['roi'].disable_tracking_mode()
        self.ref['roi'].disable_roi_actions()

        self.ref['laser'].stop_laser_output()
        self.ref['laser'].disable_laser_actions()  # includes also disabling of brightfield on / off button

        # set stage velocity
        self.ref['roi'].set_stage_velocity({'x': 1, 'y': 1})

        # create the daq channels
        self.ref['daq'].initialize_digital_channel(self.OUT7_ZEN, 'input')
        self.ref['daq'].initialize_digital_channel(self.OUT8_ZEN, 'input')
        self.ref['daq'].initialize_digital_channel(self.IN7_ZEN, 'output')

        # read all user parameters from config
        self.load_user_parameters()

        # return the list of immediate subdirectories in self.zen_saving_path (this is important since ZEN will
        # automatically create a folder at the start of a new acquisition)
        zen_folder_list_before = glob(os.path.join(self.zen_saving_path, '*'))

        # indicate to the user that QUDI is ready and the acquisition can be launched for ZEN
        self.launch_zen_acquisition()

        # return the list of immediate subdirectories in self.zen_saving_path and compare it to the previous list. When
        # ZEN starts the experiment, it automatically creates a new data folder. The two lists are compared and the
        # folder where the czi data will be saved is defined.
        self.zen_directory = self.find_new_zen_data_directory(zen_folder_list_before)
        self.metadata_dir = os.path.join(self.zen_directory, "metadata")
        os.makedirs(self.metadata_dir)

        # initialize the parameters required for the autofocus safety (where to locate the reference images, the
        # correlation, etc.)
        self.init_autofocus_safety()

        # initialize the list containing the name of all the in-focus images. During an experiment, ZEN will acquire a
        # single brightfield image before launching the acquisition of the stack. This image will be acquired at the end
        # of the focus search procedure and will be used to check the sample is still in-focus.
        self.focus_folder_content = []
        self.stack_folder_content = []

        # initialize a counter to iterate over the ROIs and an array where the correlation score will be saved
        self.roi_counter = 0
        # set the active_roi to none to avoid having two active rois displayed
        self.ref['roi'].active_roi = None

    def runTaskStep(self):
        """ Implement one work step of your task here.
        :return bool: True if the task should continue running, False if it should finish.
        """

        # --------------------------------------------------------------------------------------------------------------
        # move to the first ROI
        # --------------------------------------------------------------------------------------------------------------
        # define the name of the file according to the roi number and cycle
        scan_name = self.file_name(self.roi_names[self.roi_counter])

        # go to roi
        self.ref['roi'].set_active_roi(name=self.roi_names[self.roi_counter])
        self.ref['roi'].go_to_roi_xy()
        self.log.info('Moved to {} xy position'.format(self.roi_names[self.roi_counter]))
        self.ref['roi'].stage_wait_for_idle()

        # --------------------------------------------------------------------------------------------------------------
        # autofocus (ZEN)
        # --------------------------------------------------------------------------------------------------------------
        # send trigger to ZEN to start the autofocus search
        sleep(5)
        self.ref['daq'].write_to_do_channel(self.IN7_ZEN, 1, 1)
        sleep(0.1)
        self.ref['daq'].write_to_do_channel(self.IN7_ZEN, 1, 0)

        # wait for ZEN trigger indicating the task is completed
        trigger = self.ref['daq'].read_di_channel(self.OUT8_ZEN, 1)
        while trigger == 0 and not self.aborted:
            sleep(.1)
            trigger = self.ref['daq'].read_di_channel(self.OUT8_ZEN, 1)

        # # --------------------------------------------------------------------------------------------------------------
        # # check the correlation for the new focus image
        # # --------------------------------------------------------------------------------------------------------------
        # self.check_focus(self.roi_names[self.roi_counter], self.roi_counter)
        #
        # # --------------------------------------------------------------------------------------------------------------
        # # launch the stack acquisition (ZEN)
        # # --------------------------------------------------------------------------------------------------------------
        # # send trigger to ZEN to start the autofocus search
        # sleep(5)
        # self.ref['daq'].write_to_do_channel(self.IN7_ZEN, 1, 1)
        # sleep(0.1)
        # self.ref['daq'].write_to_do_channel(self.IN7_ZEN, 1, 0)
        #
        # # wait for ZEN trigger indicating the task is completed
        # trigger = self.ref['daq'].read_di_channel(self.OUT8_ZEN, 1)
        # while trigger == 0 and not self.aborted:
        #     sleep(.1)
        #     trigger = self.ref['daq'].read_di_channel(self.OUT8_ZEN, 1)

        # --------------------------------------------------------------------------------------------------------------
        # compute the correlation curve
        # --------------------------------------------------------------------------------------------------------------
        self.compute_correlation_curve(self.roi_names[self.roi_counter], self.roi_counter)

        self.roi_counter += 1
        return self.roi_counter < len(self.roi_names)

    def pauseTask(self):
        """ """
        self.log.info('pauseTask called')

    def resumeTask(self):
        """ """
        self.log.info('resumeTask called')

    def cleanupTask(self):
        """ """
        self.log.info('cleanupTask called')

        # go back to first ROI
        self.ref['roi'].set_active_roi(name=self.roi_names[0])
        self.ref['roi'].go_to_roi_xy()

        # reset the lumencor state
        self.ref['laser'].lumencor_set_ttl(False)
        self.ref['laser'].voltage_off()

        # reset stage velocity to default
        self.ref['roi'].set_stage_velocity({'x': 6, 'y': 6})  # 5.74592

        # enable gui actions
        # roi gui
        self.ref['roi'].enable_tracking_mode()
        self.ref['roi'].enable_roi_actions()

        self.log.info('cleanupTask finished')

    # ==================================================================================================================
    # Helper functions
    # ==================================================================================================================

    # ------------------------------------------------------------------------------------------------------------------
    # user parameters
    # ------------------------------------------------------------------------------------------------------------------

    def load_user_parameters(self):
        """ This function is called from startTask() to load the parameters given by the user in a specific format.

        Specify the path to the user defined config for this task in the (global) config of the experimental setup.

        user must specify the following dictionary (here with example entries):
            sample_name: 'Mysample'
            dapi: False
            rna: False
            exposure: 0.05  # in s
            num_z_planes: 50
            z_step: 0.25  # in um
            centered_focal_plane: False
            save_path: 'E:\'
            file_format: 'tif'
            imaging_sequence: [('488 nm', 3), ('561 nm', 3), ('641 nm', 10)]
            roi_list_path: 'pathstem/qudi_files/qudi_roi_lists/roilist_20210101_1128_23_123243.json'
        """
        try:
            with open(self.user_config_path, 'r') as stream:
                self.user_param_dict = yaml.safe_load(stream)
                self.sample_name = self.user_param_dict['sample_name']
                self.num_z_planes = self.user_param_dict['num_z_planes']
                self.roi_list_path = self.user_param_dict['roi_list_path']
                self.zen_ref_images_path = self.user_param_dict['zen_ref_images_path']
                self.zen_saving_path = self.user_param_dict['zen_saving_path']

        except Exception as e:  # add the type of exception
            self.log.warning(f'Could not load user parameters for task {self.name}: {e}')

        # establish further user parameters derived from the given ones:
        # create a list of roi names
        self.ref['roi'].load_roi_list(self.roi_list_path)
        # get the list of the roi names
        self.roi_names = self.ref['roi'].roi_names

    # ------------------------------------------------------------------------------------------------------------------
    # communication with ZEN
    # ------------------------------------------------------------------------------------------------------------------
    def launch_zen_acquisition(self):
        """ Instruct the use that QUDI is ready and ZEN acquisition can be launched. Wait for the trigger indicating
        that ZEN was also launched.
        """
        # indicate to the user the parameters he should use for zen configuration
        self.log.warning('############ ZEN PARAMETERS ############')
        self.log.warning('This task is ONLY compatible with experiment ZEN/HiM_celesta_autofocus_check')
        self.log.warning(f'Number of acquisition loops in ZEN experiment designer : 'f'{len(self.roi_names)}')
        self.log.warning('Select the autofocus block and hit "Start Experiment"')
        self.log.warning('########################################')

        # wait for the trigger from ZEN indicating that the experiment is starting
        trigger = self.ref['daq'].read_di_channel(self.OUT7_ZEN, 1)
        while trigger == 0 and not self.aborted:
            sleep(.5)
            trigger = self.ref['daq'].read_di_channel(self.OUT7_ZEN, 1)

    def find_new_zen_data_directory(self, ref_list):
        """ Compare the list of data folders before and after ZEN experiment was launched. The most recent folder will
        be the one where the new data will be saved by ZEN.

        @param: ref_list (list): list of all the folders found before ZEN acquisition was launched
        """
        attempt = 0
        while attempt < 10:
            attempt = attempt + 1
            zen_folder_list_after = glob(os.path.join(self.zen_saving_path, '*'))
            new_zen_directory = list(set(zen_folder_list_after) - set(ref_list))

            if len(new_zen_directory) == 1:
                new_zen_directory = new_zen_directory[0]
                self.log.info(f'ZEN will save the data in the following folder : {new_zen_directory}')
                return new_zen_directory
            elif len(new_zen_directory) == 0:
                sleep(1)
            else:
                self.log.error('More than one folder were found. The acquisition is aborted')
                self.aborted = True
                return ""

        if attempt == 10:
            self.log.error('No new file was created by ZEN - check if the reference folder indicated in the parameters '
                           'is correct')
            self.log.error('The acquisition is aborted')
            self.aborted = True
            return ""

    def wait_for_camera_trigger(self, value):
        """ This method contains a loop to wait for the camera exposure starts or stops.

        :return: bool ready: True: trigger was received, False: experiment cannot be started because ZEN is not ready
        """
        bit_value = self.ref['daq'].read_di_channel(self.camera_global_exposure, 1)
        counter = 0
        error = False

        while bit_value != value and error is False and not self.aborted:
            counter += 1
            bit_value = self.ref['daq'].read_di_channel(self.camera_global_exposure, 1)
            if counter > 10000:
                self.log.warning(
                    'No trigger was detected during the past 60s... experiment is aborted')
                error = True

        return error

    def check_focus(self, roi, roi_number):
        """  Check the autofocus image is in focus. This is performed as follows :
                1- wait for a new autofocus output image to be saved by ZEN
                2- calculate the correlation score between the new image and the reference
                3- if the correlation score is too low, the experiment is put on hold
                4- if the correlation score is OK, the new image will replace the previous one and the file is updated

            @return (bool) indicate if an error was encountered (the correlation score is lower than expected)
        """
        ref_image = self.focus_ref_images[roi_number]

        # compute the correlation between the reference image and the new in-focus image
        new_autofocus_image_path = self.check_for_new_autofocus_images()
        new_image = imread(new_autofocus_image_path[0])
        correlation_score = self.calculate_correlation_score(ref_image, new_image[0, 0, :, :, 0])
        self.correlation_score[roi_number] = correlation_score

        # plot and save the two images
        fig, axs = plt.subplots(1, 2)
        im0 = axs[0].imshow(ref_image, cmap='gray')
        axs[0].set_title('Raw ref image')
        im1 = axs[1].imshow(new_image[0, 0, :, :, 0], cmap='gray')
        axs[1].set_title('Raw in focus image')
        fig_saving_path = os.path.join(self.zen_directory, f'in_focus_images_{roi}.png')
        plt.savefig(fig_saving_path, dpi=150)
        plt.close(fig)

        self.log.info(f'The correlation score for {roi} was {correlation_score}')

    def compute_correlation_curve(self, roi, roi_number):
        """  Check the autofocus image is in focus. This is performed as follows :
                1- wait for a new autofocus output image to be saved by ZEN
                2- calculate the correlation score between the new image and the reference
                3- if the correlation score is too low, the experiment is put on hold
                4- if the correlation score is OK, the new image will replace the previous one and the file is updated

            @return (bool) indicate if an error was encountered (the correlation score is lower than expected)
        """
        ref_image = self.focus_ref_images[roi_number]

        # compute the correlation curve for all the plane of the stack (sanity check in case the sample is new or
        # something went wrong)
        new_autofocus_stack_path = self.check_for_new_autofocus_stack()
        new_stack = imread(new_autofocus_stack_path[0])
        n_frame = new_stack.shape[2]
        correlation_curve = np.zeros((n_frame,2))
        for frame in tqdm(range(n_frame)):
            correlation_curve[frame, 0] = frame
            correlation_curve[frame, 1] = self.calculate_correlation_score(ref_image, new_stack[0, 0, frame, :, :, 0])

        # plot the correlation curve and save it
        fig_saving_path = os.path.join(self.zen_directory, f'correlation_curve_{roi}.png')
        fig = plt.figure()
        plt.plot(correlation_curve[:, 0], correlation_curve[:, 1], '-o')
        plt.xlabel('plane (around the focus')
        plt.ylabel('correlation')
        plt.savefig(fig_saving_path, dpi=150)
        plt.close(fig)

    # ------------------------------------------------------------------------------------------------------------------
    # autofocus check helper functions
    # ------------------------------------------------------------------------------------------------------------------
    def init_autofocus_safety(self):
        """ Initialize the data for the autofocus safety procedure (comparing reference images with the newest ones).
        From the folder containing all the reference images for the focus (brightfield images acquired during a first
        acquisition for the DAPI), open all the images in the order of acquisition and store them in a numpy array.
        """
        # define the path where the reference images (for the autofocus) will be saved
        self.ref_filepath = os.path.join(self.metadata_dir, "autofocus_reference.npy")

        # check whether a numpy reference file already exists in the reference folder indicated in the HiM parameters
        init_ref_filepath = os.path.join(self.zen_ref_images_path, "autofocus_reference.npy")
        ref_files = glob(init_ref_filepath)
        print(f"ref_files : {ref_files}")

        if len(ref_files) == 1:
            self.focus_ref_images = np.load(init_ref_filepath)
            np.save(self.ref_filepath, self.focus_ref_images)

        elif len(ref_files) == 0:
            # check the reference image for the autofocus - sort them in the right acquisition order and store them in a
            # list
            ref_im_name_list = self.sort_czi_path_list(self.zen_ref_images_path)
            focus_ref_images = []
            for im_name in ref_im_name_list:
                ref_image = imread(im_name)
                ref_image = ref_image[0, 0, :, :, 0]
                focus_ref_images.append(ref_image)

            # convert the list into a numpy array and save it
            self.focus_ref_images = np.array(focus_ref_images)
            np.save(self.ref_filepath, self.focus_ref_images)

        else:
            self.log.error(f'There is an error with the reference folder, too many reference files '
                           f'(autofocus_reference.npy) were found. The experiment is aborted. ')
            self.aborted = True
            return

        # define the correlation array where the data will be saved
        self.correlation_score = np.zeros((len(self.roi_names),))

    @staticmethod
    def sort_czi_path_list(folder):
        """ Specific function sorting the name of the czi file in "human" order, that is in the order of acquisition.

        @param folder: folder where to look for the czi files
        @return: list the content of the folder in the acquisition order
        """
        path_list = glob(os.path.join(folder, '*.czi'))
        file_list = [os.path.basename(path) for path in path_list]
        print(f"file_list : {file_list}")

        pt_list = np.zeros((len(file_list),))
        sorted_path_list = [""] * len(file_list)

        for n, file in enumerate(file_list):
            digit = re.findall('\d+', file)
            print(f"digit : {digit}")
            pt_list[n] = int(digit[-1])

        for n, idx in enumerate(np.argsort(pt_list)):
            sorted_path_list[n] = path_list[idx]

        print(f"sorted_path_list : {sorted_path_list}")

        return sorted_path_list

    def check_for_new_autofocus_images(self):
        """ Check whether a new autofocus image was saved by ZEN by comparing the content of the folder before and after
        launching the autofocus procedure. When the autofocus procedure is performed, two new files are added : a
        temporary file and an empty image. When the procedure is completed, the temporary file will be destroyed.

        @return: the path pointing toward the newly acquired autofocus images
        """
        # analyze the content of the folder until a new autofocus image is detected
        new_focus_folder_content = []
        new_autofocus_image_path = []
        new_image_found = False
        while not new_image_found:
            new_focus_folder_content = glob(os.path.join(self.zen_directory, '**', '*_AcquisitionBlock1_pt*.czi'),
                                            recursive=True)
            new_autofocus_image_path = list(set(new_focus_folder_content) - set(self.focus_folder_content))

            if len(new_autofocus_image_path) > 1:
                sleep(0.5)  # temporary files are still detected, indicating that the procedure is still on going
            elif len(new_autofocus_image_path) == 0:
                sleep(0.5)  # no file found, indicating the procedure did not start yet
            else:
                new_image_found = True

        # update the content of the folder for the next acquisition
        self.focus_folder_content = new_focus_folder_content

        return new_autofocus_image_path

    def check_for_new_autofocus_stack(self):
        """ Check whether a new autofocus stack was saved by ZEN by comparing the content of the folder before and after
        launching the acquisition procedure. While the acquisition procedure is performed, two new files are added : a
        temporary file and an empty image. When the procedure is completed, the temporary file will be destroyed.

        @return: the path pointing toward the newly acquired stack
        """
        # analyze the content of the folder until a new autofocus image is detected
        new_stack_folder_content = []
        new_stack_image_path = []
        new_stack_found = False
        while not new_stack_found:
            new_stack_folder_content = glob(os.path.join(self.zen_directory, '**', '*_AcquisitionBlock2_pt*.czi'),
                                            recursive=True)
            new_stack_image_path = list(set(new_stack_folder_content) - set(self.stack_folder_content))

            if len(new_stack_image_path) > 1:
                sleep(0.5)  # temporary files are still detected, indicating that the procedure is still on going
            elif len(new_stack_image_path) == 0:
                sleep(0.5)  # no file found, indicating the procedure did not start yet
            else:
                new_stack_found = True

        # update the content of the folder for the next acquisition
        self.stack_folder_content = new_stack_folder_content

        return new_stack_image_path

    @staticmethod
    def calculate_correlation_score(ref_image, new_image):
        """ Compute a correlation score (1 = perfectly correlated - 0 = no correlation) between two images

        @param ref_image: reference image (specific of the roi)
        @param new_image: newly acquired autofocus image
        @return: correlation score
        """
        # bin the two images from 2048x2048 to 1024x1024
        shape = (1024, 2, 1024, 2)
        # shape = (512, 4, 512, 4)
        ref_image_bin = ref_image.reshape(shape).mean(-1).mean(1)
        new_image_bin = new_image.reshape(shape).mean(-1).mean(1)

        # apply a gaussian blur in order to remove the background
        ref_image_bin = ref_image_bin - gaussian_filter(ref_image_bin, sigma=10)
        new_image_bin = new_image_bin - gaussian_filter(new_image_bin, sigma=10)

        # select the central portion of the reference image. The idea is to use a smaller image to compute the
        # correlation faster but also to be less sensitive to any translational variations between the two images.
        ref_image_bin_roi = ref_image_bin[262:762, 262:762]
        # ref_image_bin_roi = ref_image_bin[128:384, 128:384]

        # calculate the correlation between the two images
        correlation_ref = correlate(ref_image_bin_roi, ref_image_bin, mode='valid')
        correlation_new = correlate(ref_image_bin_roi, new_image_bin, mode='valid')

        # compute the position where the maximum of correlation was detected (where the laplacian is the highest) - this
        # was introduced since local maxima where sometimes observed but on quite large area. The Laplacian is used to
        # detect the bins where the variation of correlation is the highest.
        correlation_laplacian = laplace(correlation_new)
        idx = np.argmax(np.abs(correlation_laplacian))
        x, y = np.unravel_index(idx, correlation_laplacian.shape)

        # compute a score (with respect to the reference)
        correlation_score = correlation_new[x, y] / np.max(correlation_ref)

        return correlation_score

    # ------------------------------------------------------------------------------------------------------------------
    # file path handling
    # ------------------------------------------------------------------------------------------------------------------
    def create_directory(self, path_stem):
        """ Create the directory (based on path_stem given as user parameter),
        in which the folders for the ROI will be created
        Example: path_stem/YYYY_MM_DD/001_Scan_samplename (default)
        or path_stem/YYYY_MM_DD/001_Scan_samplename_dapi (option dapi)
        or path_stem/YYYY_MM_DD/001_Scan_samplename_rna (option rna)

        @param: str path_stem: base name of the path that will be created
        @return: str path (see example above)
        """
        cur_date = datetime.today().strftime('%Y_%m_%d')

        path_stem_with_date = os.path.join(path_stem, cur_date)

        # check if folder path_stem_with_date exists, if not: create it
        if not os.path.exists(path_stem_with_date):
            try:
                os.makedirs(path_stem_with_date)  # recursive creation of all directories on the path
            except Exception as e:
                self.log.error('Error {0}'.format(e))

        # count the subdirectories in the directory path (non recursive !) to generate an incremental prefix
        dir_list = [folder for folder in os.listdir(path_stem_with_date) if
                    os.path.isdir(os.path.join(path_stem_with_date, folder))]
        number_dirs = len(dir_list)

        prefix = str(number_dirs + 1).zfill(3)
        # make prefix accessible to include it in the filename generated in the method get_complete_path
        self.prefix = prefix

        foldername = f'{prefix}_Scan_{self.sample_name}'
        path = os.path.join(path_stem_with_date, foldername)

        # create the path  # no need to check if it already exists due to incremental prefix
        try:
            os.makedirs(path)  # recursive creation of all directories on the path
        except Exception as e:
            self.log.error('Error {0}'.format(e))

        return path

    def file_name(self, roi_number):
        """ Define the complete name of the image data file.

        :param: str roi_number: string identifier of the current ROI for which a complete path shall be created
        :return: str complete_path: such as directory/ROI_001/scan_001_004_ROI.tif (experiment nb. 001, ROI nb. 004)
        """

        roi_number_inv = roi_number.strip('ROI_') + '_ROI'  # for compatibility with analysis format
        file_name = f'scan_{self.prefix}_{roi_number_inv}'
        return file_name

    @staticmethod
    def save_file_name(file, movie_name):
        with open(file, 'a+') as outfile:
            outfile.write(movie_name)
            outfile.write("\n")

    # ------------------------------------------------------------------------------------------------------------------
    # metadata
    # ------------------------------------------------------------------------------------------------------------------

    def get_metadata(self):
        """ Get a dictionary containing the metadata in a plain text easy readable format.

        :return: dict metadata
        """
        metadata = {'Sample name': self.sample_name, 'Scan number of planes (um)': self.num_z_planes,
                    'Number laserlines': self.num_laserlines}
        for i in range(self.num_laserlines):
            metadata[f'Laser line {i + 1}'] = self.imaging_sequence[i][0]
            metadata[f'Laser intensity {i + 1} (%)'] = self.imaging_sequence[i][1]

        for roi in self.roi_names:
            pos = self.ref['roi'].get_roi_position(roi)
            metadata[roi] = f'X = {pos[0]} - Y = {pos[1]}'

        return metadata

    def save_metadata_file(self, metadata, path):
        """ Save a txt file containing the metadata dictionary.

        :param dict metadata: dictionary containing the metadata
        :param str path: pathname
        """
        with open(path, 'w') as outfile:
            yaml.safe_dump(metadata, outfile, default_flow_style=False)
        self.log.info('Saved metadata to {}'.format(path))
