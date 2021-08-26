import numpy as np
import yaml


# used in multicolor_imaging_task_PALM
def get_entry_nested_dict(nested_dict, val, entry):
    """ Helper function that searches for 'val' as value in a nested dictionary and returns the corresponding value in the category 'entry'
    example: search in laser_dict (nested_dict) for the label (entry) corresponding to a given wavelength (val)
    search in filter_dict (nested_dict) for the label (entry) corresponding to a given filter position (val)

    :param: dict nested dict
    :param: val: any data type, value that is searched for in the dictionary
    :param: str entry: key in the inner dictionary whose value needs to be accessed

    :return: list entrylist: list (typically of length 1) with the found entries

    Note that this function is not the typical way how dictionaries should be used.
    Due to the bijectivity of the dictionaries used here, it can however be useful to try to find a key given a value.
    Hence, in practical cases, the return value 'list' will consist of a single element only. """
    entrylist = []
    for outer_key in nested_dict:
        item = [nested_dict[outer_key][entry] for inner_key, value in nested_dict[outer_key].items() if val == value]
        if item:
            entrylist.append(*item)
    return entrylist


def save_z_positions_to_file(z_target_positions, z_actual_positions, path):
    z_data_dict = {'z_target_positions': z_target_positions, 'z_positions': z_actual_positions}
    with open(path, 'w') as outfile:
        yaml.safe_dump(z_data_dict, outfile, default_flow_style=False)

def save_roi_start_times_to_file(roi_start_times, path):
    data_dict = {'roi_start_times': roi_start_times}
    with open(path, 'w') as outfile:
        yaml.safe_dump(data_dict, outfile, default_flow_style=False)
