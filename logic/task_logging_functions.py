import yaml
from datetime import datetime
import pandas as pd


def write_status_dict_to_file(path, status_dict):
    """ Write the current status dictionary to a yaml file.
    :param: dict status_dict: dictionary containing a summary describing the current state of the experiment.
    """
    try:
        with open(path, 'w') as outfile:
            yaml.safe_dump(status_dict, outfile, default_flow_style=False)
    except OSError as error:
        print('An error occurred in logic.task_logging_functions : {}'.format(error))


def add_log_entry(path, cycle, process, event, level='info'):
    """ Append a log entry to the log.csv file.
    :param: str path: complete path to the log file
    :param: int cycle: number of the current cycle, or 0 if not in a cycle
    :param int process: number of the process, encoded using Hybridization: 1, Imaging: 2, Photobleaching: 3
    :param str event: message describing the logged event
    :param: str level: 'info', 'warning', 'error'
    """
    try:
        timestamp = datetime.now()
        entry = {'timestamp': [timestamp], 'cycle_no': [cycle], 'process': [process], 'event': [event], 'level': [level]}
        df_line = pd.DataFrame(entry, columns=['timestamp', 'cycle_no', 'process', 'event', 'level'])
        with open(path, 'a') as file:
            df_line.to_csv(file, index=False, header=False)
    except OSError as error:
        print('An error occurred in logic.task_logging_functions : {}'.format(error))


def update_default_info(path, user_param_dict, image_path, fileformat, probes_dict, num_roi, inj_hybr, inj_photobl):
    """ Create a dictionary with relevant entries for the default info file and save it under the specified path.

    :param: str path: complete path to the default_info file
    :param: dict: user_param_dict
    :param: str image_path: name of the path where the image data is saved
    :param: str fileformat: fileformat for the image data
    (:param: int num_cycles: number of cycles in the Hi-M experiment)
    :param: dict probes_dict : dictionary containing all the probes
    :param: int last_num_roi: highest ROI number defined in the list for the Hi-M experiment
    :param: int num_inj_hybr: number of injection steps during the hybridization sequence (excluding incubation steps)
    :param: int num_inj_photobl: number of injection steps during the photobleaching sequence (excluding incubation)

    :return: None
    """
    # if not os.path.exists(path):
    #     os.makedirs(path)  # recursive creation of all directories on the path

    num_cycles = len(probes_dict)
    num_inj_hybr = len(inj_hybr)
    num_inj_photobl = len(inj_photobl)
    info_dict = {'image_path': image_path, 'fileformat': fileformat, 'num_cycles': num_cycles, 'probes': probes_dict,
                 'last_num_roi': num_roi, 'num_injections_hybr': num_inj_hybr,
                 'num_injections_photobl': num_inj_photobl, 'injections_hybridization': inj_hybr,
                 'injections_photobleaching': inj_photobl}

    upper_dict = {'user_parameters': user_param_dict, 'exp_tracker_app_dict': info_dict}

    with open(path, 'w') as outfile:
        yaml.safe_dump(upper_dict, outfile, default_flow_style=False)


def write_dict_to_file(path, dictionary):
    """ Helper function, to write a dictionary to a file.
    Used for example to write the dapi channel info file, but can be used flexibly.
    Could replace write_status_didt_to_file method.
    :param: str path: complete path to the file
    :param: dict dictionary: dictionary that is to be saved
    :return: None
    """
    with open(path, 'w') as outfile:
        yaml.safe_dump(dictionary, outfile, default_flow_style=False)
