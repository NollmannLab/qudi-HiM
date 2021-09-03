import yaml
from datetime import datetime
import pandas as pd


def write_status_dict_to_file(path, status_dict):
    """ Write the current status dictionary to a yaml file.
    :param: dict status_dict: dictionary containing a summary describing the current state of the experiment.
    """
    with open(path, 'w') as outfile:
        yaml.safe_dump(status_dict, outfile, default_flow_style=False)


def add_log_entry(path, cycle, process, event, level='info'):
    """ Append a log entry to the log.csv file.
    :param: str path: complete path to the log file
    :param: int cycle: number of the current cycle, or 0 if not in a cycle
    :param int process: number of the process, encoded using Hybridization: 1, Imaging: 2, Photobleaching: 3
    :param str event: message describing the logged event
    :param: str level: 'info', 'warning', 'error'
    """
    timestamp = datetime.now()
    entry = {'timestamp': [timestamp], 'cycle_no': [cycle], 'process': [process], 'event': [event], 'level': [level]}
    df_line = pd.DataFrame(entry, columns=['timestamp', 'cycle_no', 'process', 'event', 'level'])
    with open(path, 'a') as file:
        df_line.to_csv(file, index=False, header=False)


def update_default_info(path, user_param_dict, image_path, fileformat, num_cycles, num_roi, num_inj_hybr, num_inj_photobl):
    """ Create a dictionary with relevant entries for the default info file and save it under the specified path.

    :param: str path: complete path to the default_info file
    :param: dict: user_param_dict
    :param: str image_path: name of the path where the image data is saved
    :param: str fileformat: fileformat for the image data
    :param: int num_cycles: number of cycles in the Hi-M experiment
    :param: int last_num_roi: highest ROI number defined in the list for the Hi-M experiment
    :param: int num_inj_hybr: number of injection steps during the hybridization sequence (excluding incubation steps)
    :param: int num_inj_photobl: number of injection steps during the photobleaching sequence (excluding incubation)

    :return: None
    """
    # if not os.path.exists(path):
    #     os.makedirs(path)  # recursive creation of all directories on the path

    info_dict = {'image_path': image_path, 'fileformat': fileformat, 'num_cycles': num_cycles, 'last_num_roi': num_roi, 'num_injections_hybr': num_inj_hybr, 'num_injections_photobl': num_inj_photobl}

    upper_dict = {'user_parameters': user_param_dict, 'exp_tracker_app_dict': info_dict}

    with open(path, 'w') as outfile:
        yaml.safe_dump(upper_dict, outfile, default_flow_style=False)