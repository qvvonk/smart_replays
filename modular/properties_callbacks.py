#  OBS Smart Replays is an OBS script that allows more flexible replay buffer management:
#  set the clip name depending on the current window, set the file name format, etc.
#  Copyright (C) 2024 qvvonk
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.

from .exceptions import (CustomNameInvalidCharacters,
                         CustomNameInvalidFormat,
                         CustomNamePathAlreadyExists,
                         CustomNameParsingError)
from .globals import script_settings, PN, DEFAULT_CUSTOM_NAMES
from .clipname_gen import format_filename
from .obs_related import get_base_path
from .script_helpers import load_custom_names

from datetime import datetime
from pathlib import Path
import obspython as obs
import webbrowser
import json
import os


def open_github_callback(*args):
    webbrowser.open("https://github.com/qvvonk/smart_replays", 1)


def update_custom_names_callback(p, prop, data):
    """
    Checks the list of custom names and updates custom names menu (shows / hides error texts).

    :param p: properties.
    :param prop: updated property.
    :param data: config settings.
    :return: True if settings window needs to be updated, otherwise False.
    """
    invalid_format_err_text = obs.obs_properties_get(p, PN.TXT_CUSTOM_NAMES_INVALID_FORMAT)
    invalid_chars_err_text = obs.obs_properties_get(p, PN.TXT_CUSTOM_NAMES_INVALID_CHARACTERS)
    path_exists_err_text = obs.obs_properties_get(p, PN.TXT_CUSTOM_NAMES_PATH_EXISTS)

    settings_json: dict = json.loads(obs.obs_data_get_json(data))
    if not settings_json:
        return False

    try:
        load_custom_names(settings_json)
        obs.obs_property_set_visible(invalid_format_err_text, False)
        obs.obs_property_set_visible(invalid_chars_err_text, False)
        obs.obs_property_set_visible(path_exists_err_text, False)
        return True

    except CustomNameInvalidCharacters as e:
        obs.obs_property_set_visible(invalid_format_err_text, False)
        obs.obs_property_set_visible(invalid_chars_err_text, True)
        obs.obs_property_set_visible(path_exists_err_text, False)
        index = e.index

    except CustomNameInvalidFormat as e:
        obs.obs_property_set_visible(invalid_format_err_text, True)
        obs.obs_property_set_visible(invalid_chars_err_text, False)
        obs.obs_property_set_visible(path_exists_err_text, False)
        index = e.index

    except CustomNamePathAlreadyExists as e:
        obs.obs_property_set_visible(invalid_format_err_text, False)
        obs.obs_property_set_visible(invalid_chars_err_text, False)
        obs.obs_property_set_visible(path_exists_err_text, True)
        index = e.index

    except CustomNameParsingError as e:
        index = e.index

    # If error in parsing
    settings_json[PN.PROP_CUSTOM_NAMES_LIST].pop(index)
    new_custom_names_array = obs.obs_data_array_create()

    for index, custom_name in enumerate(settings_json[PN.PROP_CUSTOM_NAMES_LIST]):
        custom_name_data = obs.obs_data_create_from_json(json.dumps(custom_name))
        obs.obs_data_array_insert(new_custom_names_array, index, custom_name_data)

    obs.obs_data_set_array(data, PN.PROP_CUSTOM_NAMES_LIST, new_custom_names_array)
    obs.obs_data_array_release(new_custom_names_array)
    return True


def check_filename_template_callback(p, prop, data):
    """
    Checks filename template.
    If template is invalid, shows warning.
    """
    error_text = obs.obs_properties_get(p, PN.TXT_FILENAME_FORMAT_ERR)
    dt = datetime.now()

    try:
        format_filename("clipname", dt, raise_exception=True)
        obs.obs_property_set_visible(error_text, False)
    except:
        obs.obs_property_set_visible(error_text, True)
    return True


def update_notifications_menu_callback(p, prop, data):
    """
    Updates notifications settings menu.
    If notification is enabled, shows path widget.
    """
    success_path_prop = obs.obs_properties_get(p, PN.PROP_NOTIFICATION_ON_SUCCESS_PATH)
    failure_path_prop = obs.obs_properties_get(p, PN.PROP_NOTIFICATION_ON_FAILURE_PATH)

    on_success = obs.obs_data_get_bool(data, PN.PROP_NOTIFICATION_ON_SUCCESS)
    on_failure = obs.obs_data_get_bool(data, PN.PROP_NOTIFICATION_ON_FAILURE)

    obs.obs_property_set_visible(success_path_prop, on_success)
    obs.obs_property_set_visible(failure_path_prop, on_failure)
    return True


def check_base_path_callback(p, prop, data):
    """
    Checks base path is in the same disk as OBS recordings path.
    If it's not - sets OBS records path as base path for clips.
    """
    warn_text = obs.obs_properties_get(p, PN.TEXT_BASE_PATH_INFO)

    obs_records_path = Path(get_base_path(from_obs_config=True))
    curr_path = Path(obs.obs_data_get_string(data, PN.PROP_BASE_PATH))

    if not len(curr_path.parts) or obs_records_path.parts[0] == curr_path.parts[0]:
        obs.obs_property_text_set_info_type(warn_text, obs.OBS_TEXT_INFO_WARNING)
    else:
        obs.obs_property_text_set_info_type(warn_text, obs.OBS_TEXT_INFO_ERROR)
        obs.obs_data_set_string(data, PN.PROP_BASE_PATH, str(obs_records_path))
    return True


def import_custom_names(*args):
    path = obs.obs_data_get_string(script_settings, PN.PROP_CUSTOM_NAMES_IMPORT_PATH)
    if not path or not os.path.exists(path) or not os.path.isfile(path):
        return False

    with open(path, "r") as f:
        data = f.read()

    try:
        data = json.loads(data)
    except:
        return False

    arr = obs.obs_data_array_create()
    for index, i in enumerate(data):
        item = obs.obs_data_create_from_json(json.dumps(i))
        obs.obs_data_array_insert(arr, index, item)

    obs.obs_data_set_array(script_settings, PN.PROP_CUSTOM_NAMES_LIST, arr)
    return True


def export_custom_names(*args):
    path = obs.obs_data_get_string(script_settings, PN.PROP_CUSTOM_NAMES_EXPORT_PATH)
    if not path or not os.path.exists(path) or not os.path.isdir(path):
        return False

    custom_names_dict = json.loads(obs.obs_data_get_last_json(script_settings))
    custom_names_dict = custom_names_dict.get(PN.PROP_CUSTOM_NAMES_LIST) or DEFAULT_CUSTOM_NAMES

    with open(os.path.join(path, "obs_smartreplays_sutom_names.json"), "w") as f:
        f.write(json.dumps(custom_names_dict, ensure_ascii=False))