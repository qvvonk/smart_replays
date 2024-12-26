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

from .globals import VARIABLES, PN
from .properties_callbacks import (open_github_callback,
                                   update_notifications_menu_callback,
                                   import_custom_names_from_json_callback,
                                   export_custom_names_to_json_callback,
                                   check_base_path_callback,
                                   check_filename_template_callback,
                                   update_custom_names_callback)

import obspython as obs
import sys


def setup_clip_paths_settings(group_obj):
    # ----- Clips base path -----
    base_path_prop = obs.obs_properties_add_path(
        props=group_obj,
        name=PN.PROP_CLIPS_BASE_PATH,
        description="Base path for clips",
        type=obs.OBS_PATH_DIRECTORY,
        filter=None,
        default_path="C:\\"
    )
    t = obs.obs_properties_add_text(
        props=group_obj,
        name=PN.TEXT_BASE_PATH_INFO,
        description="The path must be on the same disk as the path for OBS records "
                    "(File -> Settings -> Output -> Recording -> Recording Path).\n"
                    "Otherwise, the script will not be able to move the clip to the correct folder.",
        type=obs.OBS_TEXT_INFO
    )
    obs.obs_property_text_set_info_type(t, obs.OBS_TEXT_INFO_WARNING)

    # ----- Clips name condition -----
    filename_condition = obs.obs_properties_add_list(
        props=group_obj,
        name=PN.PROP_CLIPS_FILENAME_CONDITION,
        description="Clip name depends on",
        type=obs.OBS_COMBO_TYPE_RADIO,
        format=obs.OBS_COMBO_FORMAT_INT
    )
    obs.obs_property_list_add_int(
        p=filename_condition,
        name="the name of an active app (.exe file name) at the moment of clip saving",
        val=1
    )
    obs.obs_property_list_add_int(
        p=filename_condition,
        name="the name of an app (.exe file name) that was active most of the time during the clip recording",
        val=2
    )
    obs.obs_property_list_add_int(
        p=filename_condition,
        name="the name of the current scene",
        val=3
    )

    t = obs.obs_properties_add_text(
        props=group_obj,
        name=PN.TXT_CLIPS_HOTKEY_TIP,
        description="You can set up hotkeys for each mode in File -> Settings -> Hotkeys",
        type=obs.OBS_TEXT_INFO
    )
    obs.obs_property_text_set_info_type(t, obs.OBS_TEXT_INFO_WARNING)

    # ----- Clip file name format -----
    filename_format_prop = obs.obs_properties_add_text(
        props=group_obj,
        name=PN.PROP_CLIPS_FILENAME_FORMAT,
        description="File name format",
        type=obs.OBS_TEXT_DEFAULT
    )
    obs.obs_property_set_long_description(
        filename_format_prop,
        """<table>
<tr><th align='left'>%NAME</th><td> - name of the clip.</td></tr>

<tr><th align='left'>%a</th><td> - Weekday as locale’s abbreviated name.<br/>
Example: Sun, Mon, …, Sat (en_US); So, Mo, …, Sa (de_DE)</td></tr>

<tr><th align='left'>%A</th><td> - Weekday as locale’s full name.<br/>
Example: Sunday, Monday, …, Saturday (en_US); Sonntag, Montag, …, Samstag (de_DE)</td></tr>

<tr><th align='left'>%w</th><td> - Weekday as a decimal number, where 0 is Sunday and 6 is Saturday.<br/>
Example: 0, 1, …, 6</td></tr>

<tr><th align='left'>%d</th><td> - Day of the month as a zero-padded decimal number.<br/>
Example: 01, 02, …, 31</td></tr>

<tr><th align='left'>%b</th><td> - Month as locale’s abbreviated name.<br/>
Example: Jan, Feb, …, Dec (en_US); Jan, Feb, …, Dez (de_DE)</td></tr>

<tr><th align='left'>%B</th><td> - Month as locale’s full name.<br/>
Example: January, February, …, December (en_US); Januar, Februar, …, Dezember (de_DE)</td></tr>

<tr><th align='left'>%m</th><td> - Month as a zero-padded decimal number.<br/>
Example: 01, 02, …, 12</td></tr>

<tr><th align='left'>%y</th><td> - Year without century as a zero-padded decimal number.<br/>
Example: 00, 01, …, 99</td></tr>

<tr><th align='left'>%Y</th><td> - Year with century as a decimal number.<br/>
Example: 0001, 0002, …, 2013, 2014, …, 9998, 9999</td></tr>

<tr><th align='left'>%H</th><td> - Hour (24-hour clock) as a zero-padded decimal number.<br/>
Example: 00, 01, …, 23</td></tr>

<tr><th align='left'>%I</th><td> - Hour (12-hour clock) as a zero-padded decimal number.<br/>
Example: 01, 02, …, 12</td></tr>

<tr><th align='left'>%p</th><td> - Locale’s equivalent of either AM or PM.<br/>
Example: AM, PM (en_US); am, pm (de_DE)</td></tr>

<tr><th align='left'>%M</th><td> - Minute as a zero-padded decimal number.<br/>
Example: 00, 01, …, 59</td></tr>

<tr><th align='left'>%S</th><td> - Second as a zero-padded decimal number.<br/>
Example: 00, 01, …, 59</td></tr>

<tr><th align='left'>%f</th><td> - Microsecond as a decimal number, zero-padded to 6 digits.<br/>
Example: 000000, 000001, …, 999999</td></tr>

<tr><th align='left'>%z</th><td> - UTC offset in the form ±HHMM[SS[.ffffff]]<br/>
Example: +0000, -0400, +1030, +063415, -030712.345216</td></tr>

<tr><th align='left'>%Z</th><td> - Time zone name<br/>
Example: UTC, GMT</td></tr>

<tr><th align='left'>%j</th><td> - Day of the year as a zero-padded decimal number.<br/>
Example: 001, 002, …, 366</td></tr>

<tr><th align='left'>%U</th><td> - Week number of the year (Sunday as the first day of the week) as a zero-padded decimal number. All days in a new year preceding the first Sunday are considered to be in week 0.<br/>
Example: 00, 01, …, 53</td></tr>

<tr><th align='left'>%W</th><td> - Week number of the year (Monday as the first day of the week) as a zero-padded decimal number. All days in a new year preceding the first Monday are considered to be in week 0.<br/>
Example: 00, 01, …, 53</td></tr>

<tr><th align='left'>%%</th><td> - A literal '%' character.</td></tr>
</table>""")

    t = obs.obs_properties_add_text(
        props=group_obj,
        name=PN.TXT_CLIPS_FILENAME_FORMAT_ERR,
        description="<font color=\"red\"><pre> Invalid format!</pre></font>",
        type=obs.OBS_TEXT_INFO
    )
    obs.obs_property_set_visible(t, False)

    # ----- Save to folders checkbox -----
    obs.obs_properties_add_bool(
        props=group_obj,
        name=PN.PROP_CLIPS_SAVE_TO_FOLDER,
        description="Create different folders for different clip names",
    )

    # ----- Callbacks -----
    obs.obs_property_set_modified_callback(base_path_prop, check_base_path_callback)
    obs.obs_property_set_modified_callback(filename_format_prop, check_filename_template_callback)


def script_properties():
    p = obs.obs_properties_create()  # main properties object
    clip_path_gr = obs.obs_properties_create()
    notification_props = obs.obs_properties_create()
    popup_props = obs.obs_properties_create()
    custom_names_props = obs.obs_properties_create()
    other_props = obs.obs_properties_create()

    # ----- Ungrouped properties -----
    # Updates text
    t = obs.obs_properties_add_text(p, 'check_updates', 'New update available', obs.OBS_TEXT_INFO)
    obs.obs_property_set_visible(t, VARIABLES.update_available)

    # Like btn
    obs.obs_properties_add_button(
        p,
        "like_btn",
        "🌟 Like this script? Star it! 🌟",
        open_github_callback
    )

    # ----- Groups -----
    obs.obs_properties_add_group(p, PN.GR_CLIPS_PATHS, "Clip path settings", obs.OBS_PROPERTY_GROUP, clip_path_gr)
    obs.obs_properties_add_group(p, PN.GR_NOTIFICATIONS, "Sound notifications", obs.OBS_GROUP_CHECKABLE, notification_props)
    obs.obs_properties_add_group(p, PN.GR_POPUP, "Popup notifications", obs.OBS_GROUP_CHECKABLE, popup_props)
    obs.obs_properties_add_group(p, PN.GR_CUSTOM_NAMES, "Custom names", obs.OBS_GROUP_NORMAL, custom_names_props)
    obs.obs_properties_add_group(p, PN.GR_OTHER, "Other", obs.OBS_GROUP_NORMAL, other_props)

    # ------ Setup properties ------
    setup_clip_paths_settings(clip_path_gr)

    # ------ Notification Settings ------
    notification_success_prop = obs.obs_properties_add_bool(
        props=notification_props,
        name=PN.PROP_NOTIFICATION_ON_SUCCESS,
        description="On success"
    )
    obs.obs_properties_add_path(
        props=notification_props,
        name=PN.PROP_NOTIFICATION_ON_SUCCESS_PATH,
        description="",
        type=obs.OBS_PATH_FILE,
        filter=None,
        default_path="C:\\"
    )

    notification_failure_prop = obs.obs_properties_add_bool(
        props=notification_props,
        name=PN.PROP_NOTIFICATION_ON_FAILURE,
        description="On failure"
    )
    obs.obs_properties_add_path(
        props=notification_props,
        name=PN.PROP_NOTIFICATION_ON_FAILURE_PATH,
        description="",
        type=obs.OBS_PATH_FILE,
        filter=None,
        default_path="C:\\"
    )

    update_notifications_menu_callback(p, None, VARIABLES.script_settings)

    # ------ Popup notifications ------
    obs.obs_properties_add_bool(
        props=popup_props,
        name=PN.PROP_POPUP_ON_SUCCESS,
        description="On success"
    )

    obs.obs_properties_add_bool(
        props=popup_props,
        name=PN.PROP_POPUP_ON_FAILURE,
        description="On failure"
    )
    # ------ Custom names settings ------
    obs.obs_properties_add_text(
        props=custom_names_props,
        name=PN.TXT_CUSTOM_NAME_DESC,
        description="Since the executable name doesn't always match the name of the application/game "
                    "(e.g. the game is called Deadlock, but the executable is project8.exe), "
                    "you can set custom names for clips based on the name of the executable / folder "
                    "where the executable is located.",
        type=obs.OBS_TEXT_INFO
    )

    err_text_1 = obs.obs_properties_add_text(
        props=custom_names_props,
        name=PN.TXT_CUSTOM_NAMES_INVALID_CHARACTERS,
        description="""
<div style="font-size: 14px">
<span style="color: red">Invalid path or clip name value.<br></span>
<span style="color: orange">Clip name cannot contain <code style="color: cyan">&lt; &gt; / \\ | * ? : " %</code> characters.<br>
Path cannot contain <code style="color: cyan">&lt; &gt; | * ? " %</code> characters.</span>
</div>
""",
        type=obs.OBS_TEXT_INFO
    )

    err_text_2 = obs.obs_properties_add_text(
        props=custom_names_props,
        name=PN.TXT_CUSTOM_NAMES_PATH_EXISTS,
        description="""<div style="font-size: 14px; color: red">This path has already been added to the list.</div>""",
        type=obs.OBS_TEXT_INFO
    )

    err_text_3 = obs.obs_properties_add_text(
        props=custom_names_props,
        name=PN.TXT_CUSTOM_NAMES_INVALID_FORMAT,
        description="""
<div style="font-size: 14px">
<span style="color: red">Invalid format.<br></span>
<span style="color: orange">Required format: DISK:\\path\\to\\folder\\or\\executable > ClipName<br></span>
<span style="color: lightgreen">Example: C:\\Program Files\\Minecraft > Minecraft</span>
</div>""",
        type=obs.OBS_TEXT_INFO
    )

    obs.obs_property_set_visible(err_text_1, False)
    obs.obs_property_set_visible(err_text_2, False)
    obs.obs_property_set_visible(err_text_3, False)

    custom_names_list = obs.obs_properties_add_editable_list(
        props=custom_names_props,
        name=PN.PROP_CUSTOM_NAMES_LIST,
        description="",
        type=obs.OBS_EDITABLE_LIST_TYPE_STRINGS,
        filter=None,
        default_path=None
    )

    t = obs.obs_properties_add_text(
        props=custom_names_props,
        name="temp",
        description="Format:  DISK:\\path\\to\\folder\\or\\executable > ClipName\n"
                    f"Example: {sys.executable} > OBS",
        type=obs.OBS_TEXT_INFO
    )
    obs.obs_property_text_set_info_type(t, obs.OBS_TEXT_INFO_WARNING)

    obs.obs_properties_add_path(
        props=custom_names_props,
        name=PN.PROP_CUSTOM_NAMES_IMPORT_PATH,
        description="",
        type=obs.OBS_PATH_FILE,
        filter=None,
        default_path="C:\\"
    )

    obs.obs_properties_add_button(
        custom_names_props,
        PN.BTN_CUSTOM_NAMES_IMPORT,
        "Import custom names",
        import_custom_names_from_json_callback,
    )

    obs.obs_properties_add_path(
        props=custom_names_props,
        name=PN.PROP_CUSTOM_NAMES_EXPORT_PATH,
        description="",
        type=obs.OBS_PATH_DIRECTORY,
        filter=None,
        default_path="C:\\"
    )

    obs.obs_properties_add_button(
        custom_names_props,
        PN.BTN_CUSTOM_NAMES_EXPORT,
        "Export custom names",
        export_custom_names_to_json_callback,
    )

    # ------ Other ------
    obs.obs_properties_add_text(
        props=other_props,
        name=PN.TXT_RESTART_BUFFER_LOOP,
        description="""If you don't restart replay buffering for a long time, saving clips can take a very long time and other bugs can happen (thanks, OBS).
It is recommended to keep the value within 1-2 hours (3600-7200 seconds).
Before a scheduled restart of replay buffering, script looks at the max clip length in the OBS settings and checks if keyboard or mouse input was made at that time. If input was made, the restart will be delayed for the time of max clip length, otherwise it restarts replay baffering.
If you want to disable scheduled restart of replay buffering, set the value to 0.
""",
        type=obs.OBS_TEXT_INFO
    )

    obs.obs_properties_add_int(
        props=other_props,
        name=PN.PROP_RESTART_BUFFER_LOOP,
        description="Restart every (s)",
        min=0, max=7200,
        step=10
    )

    obs.obs_properties_add_bool(
        props=other_props,
        name=PN.PROP_RESTART_BUFFER,
        description="Restart replay buffer after clip saving"
    )

    obs.obs_property_set_modified_callback(notification_success_prop, update_notifications_menu_callback)
    obs.obs_property_set_modified_callback(notification_failure_prop, update_notifications_menu_callback)
    obs.obs_property_set_modified_callback(custom_names_list, update_custom_names_callback)
    return p