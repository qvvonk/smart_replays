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

import tkinter as tk
import time
import sys
import ctypes
import re
import json
import traceback
import webbrowser
import os
import winsound
import subprocess
from tkinter import font as f
from enum import Enum
from threading import Lock
from threading import Thread
from pathlib import Path
from collections import deque
from collections import defaultdict
from urllib.request import urlopen
from datetime import datetime
from ctypes import wintypes
from contextlib import suppress
from typing import Any

if __name__ != '__main__':
    import obspython as obs


# -------------------- ui.py --------------------
# This part of the script uses only when it is run as a main program, not imported by OBS.
#
# You can run this script to show notification:
# python smart_replays.py <Notification Title> <Notification Text> <Notification Color>
class ScrollingText:
    def __init__(self,
                 canvas: tk.Canvas,
                 text,
                 visible_area_width,
                 start_pos,
                 font,
                 delay: int = 10,
                 speed=1,
                 on_finish_callback=None):
        """
        Scrolling text widget.

        :param canvas: canvas
        :param text: text
        :param visible_area_width: width of the visible area of the text
        :param start_pos: text's start position (most likely padding from left border)
        :param font: font
        :param delay: Delay between text moves (in ms)
        :param speed: scrolling speed
        :param on_finish_callback: callback function when text animation is finished
        """

        self.canvas = canvas
        self.text = text
        self.area_width = visible_area_width
        self.start_pos = start_pos
        self.font = font
        self.delay = delay
        self.speed = speed
        self.on_finish_callback = on_finish_callback

        self.text_width = font.measure(text)
        self.text_height = font.metrics("ascent") + font.metrics("descent")
        self.text_id = self.canvas.create_text(0, round(self.text_height / 2),
                                               anchor=tk.NW, text=self.text, font=self.font, fill="#ffffff")
        self.text_curr_pos = start_pos

    def update_scroll(self):
        if self.text_curr_pos + self.text_width > self.area_width:
            self.canvas.move(self.text_id, -self.speed, 0)
            self.text_curr_pos -= self.speed

            self.canvas.after(self.delay, self.update_scroll)
        else:
            if self.on_finish_callback:
                self.on_finish_callback()


class NotificationWindow:
    def __init__(self,
                 title: str,
                 message: str,
                 primary_color: str = "#78B900"):
        self.title = title
        self.message = message
        self.primary_color = primary_color
        self.bg_color = "#000000"

        self.root = tk.Tk()
        self.root.withdraw()
        self.window = tk.Toplevel(bg="#000001")
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True, "-alpha", 0.99, "-transparentcolor", "#000001")

        self.scr_w, self.scr_h = self.window.winfo_screenwidth(), self.window.winfo_screenheight()
        self.wnd_w, self.wnd_h = round(self.scr_w / 6.4), round(self.scr_h / 12)
        self.wnd_x, self.wnd_y = self.scr_w - self.wnd_w, round(self.scr_h / 10)
        self.title_font_size = round(self.wnd_h / 5)
        self.message_font_size = round(self.wnd_h / 8)
        self.second_frame_padding_x = round(self.wnd_w / 40)
        self.message_right_padding = round(self.wnd_w / 40)
        self.content_frame_padding_x, self.content_frame_padding_y = (round(self.wnd_w / 40),
                                                                      round(self.wnd_h / 12))

        self.window.geometry(f"{self.wnd_w}x{self.wnd_h}+{self.wnd_x}+{self.wnd_y}")

        self.first_frame = tk.Frame(self.window, bg=self.primary_color, bd=0, width=1, height=self.wnd_h)
        self.first_frame.place(x=self.wnd_w-1, y=0)

        self.second_frame = tk.Frame(self.window, bg=self.bg_color, bd=0, width=1, height=self.wnd_h)
        self.second_frame.pack_propagate(False)
        self.second_frame.place(x=self.wnd_w-1, y=0)

        self.content_frame = tk.Frame(self.second_frame, bg=self.bg_color, bd=0, height=self.wnd_h)
        self.content_frame.pack(fill=tk.X,
                                padx=self.content_frame_padding_x,
                                pady=self.content_frame_padding_y)


        self.title_label = tk.Label(self.content_frame,
                                    text=self.title,
                                    font=("Bahnschrift", self.title_font_size, "bold"),
                                    bg=self.bg_color,
                                    fg=self.primary_color)
        self.title_label.pack(anchor=tk.W)


        self.canvas = tk.Canvas(self.content_frame, bg=self.bg_color, highlightthickness=0)
        self.canvas.pack()
        self.canvas.update()

        font = f.Font(family="Cascadia Mono", size=self.message_font_size)
        self.message = ScrollingText(canvas=self.canvas,
                                     text=message,
                                     visible_area_width=self.wnd_w - self.second_frame_padding_x,
                                     start_pos=self.second_frame_padding_x + self.message_right_padding,
                                     font=font,
                                     delay=10,
                                     speed=2,
                                     on_finish_callback=self.on_text_anim_finished_callback)


    def animate_frame(self, frame: tk.Frame, target_w, delay: float = 0.00001, speed: int = 3):
        init_w, init_h = frame.winfo_width(), self.wnd_h
        speed = speed if init_w < target_w else -speed

        for curr_w in range(init_w, target_w, speed):
            frame.config(width=curr_w)
            frame.place(x=self.wnd_w-curr_w, y=0)
            frame.update()
            time.sleep(delay)

        if frame.winfo_width() != target_w:
            frame.config(width=target_w)
            frame.place(x=self.wnd_w - target_w, y=0)
            frame.update()

    def show(self):
        self.animate_frame(self.first_frame, self.wnd_w)
        time.sleep(0.1)
        self.second_frame.lift()
        self.animate_frame(self.second_frame, self.wnd_w - self.second_frame_padding_x)
        self.root.after(1000, self.message.update_scroll)
        self.root.mainloop()

    def close(self):
        self.animate_frame(self.second_frame, 0)
        time.sleep(0.1)
        self.animate_frame(self.first_frame, 0)
        self.window.destroy()
        self.root.destroy()

    def on_text_anim_finished_callback(self):
        time.sleep(2.5)
        self.close()


if __name__ == '__main__':
    t = sys.argv[1] if len(sys.argv) > 1 else "Test Title"
    m = sys.argv[2] if len(sys.argv) > 2 else "Test Message"
    color = sys.argv[3] if len(sys.argv) > 3 else "#76B900"
    NotificationWindow(t, m, color).show()
    sys.exit(0)


# -------------------- globals.py --------------------
user32 = ctypes.windll.user32


class CONSTANTS:
    VERSION = "1.0.8.2"
    OBS_VERSION_STRING = obs.obs_get_version_string()
    OBS_VERSION_RE = re.compile(r'(\d+)\.(\d+)\.(\d+)')
    OBS_VERSION = [int(i) for i in OBS_VERSION_RE.match(OBS_VERSION_STRING).groups()]
    CLIPS_FORCE_MODE_LOCK = Lock()
    VIDEOS_FORCE_MODE_LOCK = Lock()
    FILENAME_PROHIBITED_CHARS = r'/\:"<>*?|%'
    PATH_PROHIBITED_CHARS = r'"<>*?|%'
    DEFAULT_FILENAME_FORMAT = "%NAME_%d.%m.%Y_%H-%M-%S"
    DEFAULT_ALIASES = (
        {"value": "C:\\Windows\\explorer.exe > Desktop", "selected": False, "hidden": False},
        {"value": f"{sys.executable} > OBS", "selected": False, "hidden": False}
    )


class VARIABLES:
    update_available: bool = False
    clip_exe_history: deque[Path, ...] | None = None
    video_exe_history: defaultdict[Path, int] | None = None  # {Path(path/to/executable): active_seconds_amount
    exe_path_on_video_stopping_event: Path | None = None
    aliases: dict[Path, str] = {}
    script_settings = None
    hotkey_ids: dict = {}
    force_mode = None


class ConfigTypes(Enum):
    PROFILE = 0
    APP = 1
    USER = 2


class ClipNamingModes(Enum):
    CURRENT_PROCESS = 0
    MOST_RECORDED_PROCESS = 1
    CURRENT_SCENE = 2
    PROCESS_DESCRIPTION = 3


class VideoNamingModes(Enum):
    CURRENT_PROCESS = 0
    MOST_RECORDED_PROCESS = 1
    CURRENT_SCENE = 2


class PopupPathDisplayModes(Enum):
    FULL_PATH = 0
    FOLDER_AND_FILE = 1
    JUST_FOLDER = 2
    JUST_FILE = 3


class PropertiesNames:
    # Prop groups
    GR_CLIPS_PATH_SETTINGS = "clips_path_settings"
    GR_VIDEOS_PATH_SETTINGS = "videos_path_settings"
    GR_SOUND_NOTIFICATION_SETTINGS = "sound_notification_settings"
    GR_POPUP_NOTIFICATION_SETTINGS = "popup_notification_settings"
    GR_ALIASES_SETTINGS = "aliases_settings"
    GR_OTHER_SETTINGS = "other_settings"

    # Clips path settings
    PROP_CLIPS_BASE_PATH = "clips_base_path"
    TXT_CLIPS_BASE_PATH_WARNING = "clips_base_path_warning"
    PROP_CLIPS_NAMING_MODE = "clips_naming_mode"
    TXT_CLIPS_HOTKEY_TIP = "clips_hotkey_tip"
    PROP_CLIPS_FILENAME_TEMPLATE = "clips_filename_template"
    TXT_CLIPS_FILENAME_TEMPLATE_ERR = "clips_filename_template_err"
    PROP_CLIPS_SAVE_TO_FOLDER = "clips_save_to_folder"
    PROP_CLIPS_ONLY_FORCE_MODE = "clips_only_force_mode" # todo
    PROP_CLIPS_CREATE_LINKS = "clips_create_links"
    PROP_CLIPS_LINKS_FOLDER_PATH = "clips_links_folder_path"
    TXT_CLIPS_LINKS_FOLDER_PATH_WARNING = "clips_links_folder_path_warning"

    # Videos path settings
    PROP_VIDEOS_NAMING_MODE = "videos_naming_mode"
    TXT_VIDEOS_HOTKEY_TIP = "videos_hotkey_tip"
    PROP_VIDEOS_FILENAME_FORMAT = "videos_filename_format"
    TXT_VIDEOS_FILENAME_FORMAT_ERR = "videos_filename_format_err"
    PROP_VIDEOS_SAVE_TO_FOLDER = "videos_save_to_folder"
    PROP_VIDEOS_ONLY_FORCE_MODE = "videos_only_force_mode"

    # Sound notification settings
    PROP_NOTIFY_CLIPS_ON_SUCCESS = "notify_clips_on_success"
    PROP_NOTIFY_CLIPS_ON_SUCCESS_PATH = "notify_clips_on_success_path"
    PROP_NOTIFY_CLIPS_ON_FAILURE = "notify_clips_on_failure"
    PROP_NOTIFY_CLIPS_ON_FAILURE_PATH = "notify_clips_on_failure_path"
    PROP_NOTIFY_VIDEOS_ON_SUCCESS = "notify_videos_on_success"
    PROP_NOTIFY_VIDEOS_ON_SUCCESS_PATH = "notify_videos_on_success_path"
    PROP_NOTIFY_VIDEOS_ON_FAILURE = "notify_videos_on_failure"
    PROP_NOTIFY_VIDEOS_ON_FAILURE_PATH = "notify_videos_on_failure_path"

    # Popup notification settings
    PROP_POPUP_CLIPS_ON_SUCCESS = "popup_clips_on_success"
    PROP_POPUP_CLIPS_ON_FAILURE = "popup_clips_on_failure"
    PROP_POPUP_VIDEOS_ON_SUCCESS = "popup_videos_on_success"
    PROP_POPUP_VIDEOS_ON_FAILURE = "popup_videos_on_failure"
    PROP_POPUP_PATH_DISPLAY_MODE = "prop_popup_path_display_mode"

    # Aliases settings
    PROP_ALIASES_LIST = "aliases_list"
    TXT_ALIASES_DESC = "aliases_desc"

    # Aliases parsing error texts
    TXT_ALIASES_PATH_EXISTS = "aliases_path_exists_err"
    TXT_ALIASES_INVALID_FORMAT = "aliases_invalid_format_err"
    TXT_ALIASES_INVALID_CHARACTERS = "aliases_invalid_characters_err"

    # Export / Import aliases section
    PROP_ALIASES_EXPORT_PATH = "aliases_export_path"
    BTN_ALIASES_EXPORT = "aliases_export_btn"
    PROP_ALIASES_IMPORT_PATH = "aliases_import_path"
    BTN_ALIASES_IMPORT = "aliases_import_btn"

    # Other section
    PROP_RESTART_BUFFER = "restart_buffer"
    PROP_RESTART_BUFFER_LOOP = "restart_buffer_loop"
    TXT_RESTART_BUFFER_LOOP = "restart_buffer_loop_desc"

    # Hotkeys
    HK_SAVE_BUFFER_MODE_1 = "save_buffer_force_mode_1"
    HK_SAVE_BUFFER_MODE_2 = "save_buffer_force_mode_2"
    HK_SAVE_BUFFER_MODE_3 = "save_buffer_force_mode_3"
    HK_SAVE_BUFFER_MODE_4 = "save_buffer_force_mode_4"
    HK_SAVE_VIDEO_MODE_1 = "save_video_force_mode_1"
    HK_SAVE_VIDEO_MODE_2 = "save_video_force_mode_2"
    HK_SAVE_VIDEO_MODE_3 = "save_video_force_mode_3"

PN = PropertiesNames


# -------------------- exceptions.py --------------------
class AliasParsingError(Exception):
    """
    Base exception for all alias related exceptions.
    """
    def __init__(self, index):
        """
        :param index: alias index.
        """
        super(Exception).__init__()
        self.index = index


class AliasPathAlreadyExists(AliasParsingError):
    """
    Exception raised when an alias is already exists.
    """


class AliasInvalidCharacters(AliasParsingError):
    """
    Exception raised when an alias has invalid characters.
    """


class AliasInvalidFormat(AliasParsingError):
    """
    Exception raised when an alias is invalid format.
    """


# -------------------- updates_check.py --------------------
def get_latest_release_tag() -> dict | None:  # todo: for future updates
    url = "https://api.github.com/repos/qvvonk/smart_replays/releases/latest"

    try:
        with urlopen(url, timeout=2) as response:
            if response.status == 200:
                data = json.load(response)
                return data.get('tag_name')
    except:
        _print(f"Failed to check updates.")
        _print(traceback.format_exc())
    return None


def check_updates(current_version: str):  # todo: for future updates
    latest_version = get_latest_release_tag()
    _print(latest_version)
    if latest_version and f'v{current_version}' != latest_version:
        return True
    return False


# -------------------- properties.py --------------------
variables_tip = """<table>
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
</table>"""


def setup_clip_paths_settings(group_obj):
    # ----- Clips base path -----
    base_path_prop = obs.obs_properties_add_path(
        props=group_obj,
        name=PN.PROP_CLIPS_BASE_PATH,
        description="Base path for clips",
        type=obs.OBS_PATH_DIRECTORY,
        filter=None,
        default_path=str(get_base_path())
    )

    t = obs.obs_properties_add_text(
        props=group_obj,
        name=PN.TXT_CLIPS_BASE_PATH_WARNING,
        description="The path must be on the same disk as the path for OBS records "
                    "(File -> Settings -> Output -> Recording -> Recording Path).\n"
                    "Otherwise, the script will not be able to move the clip to the correct folder.",
        type=obs.OBS_TEXT_INFO
    )

    obs.obs_property_text_set_info_type(t, obs.OBS_TEXT_INFO_WARNING)

    # ----- Clip naming mode -----
    clip_naming_mode_prop = obs.obs_properties_add_list(
        props=group_obj,
        name=PN.PROP_CLIPS_NAMING_MODE,
        description="Clip name based on",
        type=obs.OBS_COMBO_TYPE_RADIO,
        format=obs.OBS_COMBO_FORMAT_INT
    )
    obs.obs_property_list_add_int(
        p=clip_naming_mode_prop,
        name="the name of an active app (.exe file name) at the moment of clip saving;",
        val=ClipNamingModes.CURRENT_PROCESS.value
    )
    obs.obs_property_list_add_int(
        p=clip_naming_mode_prop,
        name="the name of an app (.exe file name) that was active most of the time during the clip recording;",
        val=ClipNamingModes.MOST_RECORDED_PROCESS.value
    )
    obs.obs_property_list_add_int(
        p=clip_naming_mode_prop,
        name="the name of the current scene;",
        val=ClipNamingModes.CURRENT_SCENE.value
    )
    obs.obs_property_list_add_int(
        p=clip_naming_mode_prop,
        name="the program name as shown in Task Manager (cleaned of special characters);",
        val=ClipNamingModes.PROCESS_DESCRIPTION.value
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
        name=PN.PROP_CLIPS_FILENAME_TEMPLATE,
        description="File name format",
        type=obs.OBS_TEXT_DEFAULT
    )
    obs.obs_property_set_long_description(
        filename_format_prop,
        variables_tip)

    t = obs.obs_properties_add_text(
        props=group_obj,
        name=PN.TXT_CLIPS_FILENAME_TEMPLATE_ERR,
        description="<font color=\"red\"><pre> Invalid format!</pre></font>",
        type=obs.OBS_TEXT_INFO
    )
    obs.obs_property_set_visible(t, False)

    # ----- Save to folders checkbox -----
    obs.obs_properties_add_bool(
        props=group_obj,
        name=PN.PROP_CLIPS_SAVE_TO_FOLDER,
        description="Sort clips into folders by application or scene",
    )

    # ----- Create links -----
    create_links_prop = obs.obs_properties_add_bool(
        props=group_obj,
        name=PN.PROP_CLIPS_CREATE_LINKS,
        description="Create hard links for clips",
    )

    links_path_prop = obs.obs_properties_add_path(
        props=group_obj,
        name=PN.PROP_CLIPS_LINKS_FOLDER_PATH,
        description="Links folder",
        type=obs.OBS_PATH_DIRECTORY,
        filter=None,
        default_path=str(get_base_path())
    )
    links_path_warn = obs.obs_properties_add_text(
        props=group_obj,
        name=PN.TXT_CLIPS_LINKS_FOLDER_PATH_WARNING,
        description="The path must be on the same disk as the path for OBS records "
                    "(File -> Settings -> Output -> Recording -> Recording Path).\n"
                    "Otherwise, the script will not be able to create link to the file.",
        type=obs.OBS_TEXT_INFO
    )
    obs.obs_property_text_set_info_type(links_path_warn, obs.OBS_TEXT_INFO_WARNING)

    obs.obs_property_set_visible(links_path_prop,
                                 obs.obs_data_get_bool(VARIABLES.script_settings,
                                                       PN.PROP_CLIPS_CREATE_LINKS))
    obs.obs_property_set_visible(links_path_warn,
                                 obs.obs_data_get_bool(VARIABLES.script_settings,
                                                       PN.PROP_CLIPS_CREATE_LINKS))

    # ----- Callbacks -----
    obs.obs_property_set_modified_callback(base_path_prop, check_base_path_callback)
    obs.obs_property_set_modified_callback(filename_format_prop, check_filename_template_callback)
    obs.obs_property_set_modified_callback(create_links_prop, update_links_path_prop_visibility)
    obs.obs_property_set_modified_callback(links_path_prop, check_clips_links_folder_path_callback)


def setup_video_paths_settings(group_obj):
    # ----- Video name condition -----
    filename_condition = obs.obs_properties_add_list(
        props=group_obj,
        name=PN.PROP_VIDEOS_NAMING_MODE,
        description="Video name based on",
        type=obs.OBS_COMBO_TYPE_RADIO,
        format=obs.OBS_COMBO_FORMAT_INT
    )
    obs.obs_property_list_add_int(
        p=filename_condition,
        name="the name of an active app (.exe file name) at the moment of video saving",
        val=1
    )
    obs.obs_property_list_add_int(
        p=filename_condition,
        name="the name of an app (.exe file name) that was active most of the time during the video recording",
        val=2
    )
    obs.obs_property_list_add_int(
        p=filename_condition,
        name="the name of the current scene",
        val=3
    )

    t = obs.obs_properties_add_text(
        props=group_obj,
        name=PN.TXT_VIDEOS_HOTKEY_TIP,
        description="You can set up hotkeys for each mode in File -> Settings -> Hotkeys",
        type=obs.OBS_TEXT_INFO
    )
    obs.obs_property_text_set_info_type(t, obs.OBS_TEXT_INFO_WARNING)

    # ----- Video file name format -----
    filename_format_prop = obs.obs_properties_add_text(
        props=group_obj,
        name=PN.PROP_VIDEOS_FILENAME_FORMAT,
        description="File name format",
        type=obs.OBS_TEXT_DEFAULT
    )
    obs.obs_property_set_long_description(
        filename_format_prop,
        variables_tip)

    t = obs.obs_properties_add_text(
        props=group_obj,
        name=PN.TXT_VIDEOS_FILENAME_FORMAT_ERR,
        description="<font color=\"red\"><pre> Invalid format!</pre></font>",
        type=obs.OBS_TEXT_INFO
    )
    obs.obs_property_set_visible(t, False)

    # ----- Save to folders checkbox -----
    obs.obs_properties_add_bool(
        props=group_obj,
        name=PN.PROP_VIDEOS_SAVE_TO_FOLDER,
        description="Create different folders for different video names",
    )

    # ----- Rename only if force mode -----
    obs.obs_properties_add_bool(
        props=group_obj,
        name=PN.PROP_VIDEOS_ONLY_FORCE_MODE,
        description="Rename and move the video only if it was saved using the script's hotkeys"
    )


def setup_notifications_settings(group_obj):
    notification_success_prop = obs.obs_properties_add_bool(
        props=group_obj,
        name=PN.PROP_NOTIFY_CLIPS_ON_SUCCESS,
        description="On success"
    )
    success_path_prop = obs.obs_properties_add_path(
        props=group_obj,
        name=PN.PROP_NOTIFY_CLIPS_ON_SUCCESS_PATH,
        description="",
        type=obs.OBS_PATH_FILE,
        filter=None,
        default_path="C:\\"
    )

    notification_failure_prop = obs.obs_properties_add_bool(
        props=group_obj,
        name=PN.PROP_NOTIFY_CLIPS_ON_FAILURE,
        description="On failure"
    )
    failure_path_prop = obs.obs_properties_add_path(
        props=group_obj,
        name=PN.PROP_NOTIFY_CLIPS_ON_FAILURE_PATH,
        description="",
        type=obs.OBS_PATH_FILE,
        filter=None,
        default_path="C:\\"
    )

    obs.obs_property_set_visible(success_path_prop,
                                 obs.obs_data_get_bool(VARIABLES.script_settings, PN.PROP_NOTIFY_CLIPS_ON_SUCCESS))
    obs.obs_property_set_visible(failure_path_prop,
                                 obs.obs_data_get_bool(VARIABLES.script_settings, PN.PROP_NOTIFY_CLIPS_ON_FAILURE))

    # ----- Callbacks ------
    obs.obs_property_set_modified_callback(notification_success_prop, update_notifications_menu_callback)
    obs.obs_property_set_modified_callback(notification_failure_prop, update_notifications_menu_callback)


def setup_popup_notification_settings(group_obj):
    obs.obs_properties_add_bool(
        props=group_obj,
        name=PN.PROP_POPUP_CLIPS_ON_SUCCESS,
        description="On success"
    )

    obs.obs_properties_add_bool(
        props=group_obj,
        name=PN.PROP_POPUP_CLIPS_ON_FAILURE,
        description="On failure"
    )

    popup_path_type = obs.obs_properties_add_list(
        props=group_obj,
        name=PN.PROP_POPUP_PATH_DISPLAY_MODE,
        description="Show",
        type=obs.OBS_COMBO_TYPE_RADIO,
        format=obs.OBS_COMBO_FORMAT_INT
    )
    obs.obs_property_list_add_int(
        p=popup_path_type,
        name="full path",
        val=PopupPathDisplayModes.FULL_PATH.value
    )
    obs.obs_property_list_add_int(
        p=popup_path_type,
        name="folder and file name",
        val=PopupPathDisplayModes.FOLDER_AND_FILE.value
    )
    obs.obs_property_list_add_int(
        p=popup_path_type,
        name="just folder",
        val=PopupPathDisplayModes.JUST_FOLDER.value
    )

    obs.obs_property_list_add_int(
        p=popup_path_type,
        name="just file name",
        val=PopupPathDisplayModes.JUST_FILE.value
    )


def setup_aliases_settings(group_obj):
    obs.obs_properties_add_text(
        props=group_obj,
        name=PN.TXT_ALIASES_DESC,
        description="Executable (.exe) files often have names that don't match the actual game title "
                    "(e.g., the game is called Deadlock, but the .exe file is named project8.exe)."
                    "You can create an alias for the executable file or folder. "
                    "Smart Replays will use this alias for renaming, rather than the .exe file name.",
        type=obs.OBS_TEXT_INFO
    )

    err_text_1 = obs.obs_properties_add_text(
        props=group_obj,
        name=PN.TXT_ALIASES_INVALID_CHARACTERS,
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
        props=group_obj,
        name=PN.TXT_ALIASES_PATH_EXISTS,
        description="""<div style="font-size: 14px; color: red">This path has already been added to the list.</div>""",
        type=obs.OBS_TEXT_INFO
    )

    err_text_3 = obs.obs_properties_add_text(
        props=group_obj,
        name=PN.TXT_ALIASES_INVALID_FORMAT,
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

    aliases_list = obs.obs_properties_add_editable_list(
        props=group_obj,
        name=PN.PROP_ALIASES_LIST,
        description="",
        type=obs.OBS_EDITABLE_LIST_TYPE_STRINGS,
        filter=None,
        default_path=None
    )

    t = obs.obs_properties_add_text(
        props=group_obj,
        name="temp",
        description="Format:  DISK:\\path\\to\\folder\\or\\executable > ClipName\n"
                    f"Example: {sys.executable} > OBS",
        type=obs.OBS_TEXT_INFO
    )
    obs.obs_property_text_set_info_type(t, obs.OBS_TEXT_INFO_WARNING)

    obs.obs_properties_add_path(
        props=group_obj,
        name=PN.PROP_ALIASES_IMPORT_PATH,
        description="",
        type=obs.OBS_PATH_FILE,
        filter=None,
        default_path="C:\\"
    )

    obs.obs_properties_add_button(
        group_obj,
        PN.BTN_ALIASES_IMPORT,
        "Import aliases",
        import_aliases_from_json_callback,
    )

    obs.obs_properties_add_path(
        props=group_obj,
        name=PN.PROP_ALIASES_EXPORT_PATH,
        description="",
        type=obs.OBS_PATH_DIRECTORY,
        filter=None,
        default_path="C:\\"
    )

    obs.obs_properties_add_button(
        group_obj,
        PN.BTN_ALIASES_EXPORT,
        "Export aliases",
        export_aliases_to_json_callback,
    )

    # ----- Callbacks -----
    obs.obs_property_set_modified_callback(aliases_list, update_aliases_callback)


def setup_other_settings(group_obj):
    obs.obs_properties_add_text(
        props=group_obj,
        name=PN.TXT_RESTART_BUFFER_LOOP,
        description="""If replay buffering runs too long without a restart, saving clips may become slow, and bugs can occur (thanks, OBS).
It's recommended to restart it every 1-2 hours (3600-7200 seconds). Before restarting, the script checks OBS's max clip length and detects keyboard or mouse input. If input is detected, the restart is delayed by the max clip length; otherwise, it proceeds immediately.
To disable scheduled restarts, set the value to 0.""",
        type=obs.OBS_TEXT_INFO
    )

    obs.obs_properties_add_int(
        props=group_obj,
        name=PN.PROP_RESTART_BUFFER_LOOP,
        description="Restart every (s)",
        min=0, max=7200,
        step=10
    )

    obs.obs_properties_add_bool(
        props=group_obj,
        name=PN.PROP_RESTART_BUFFER,
        description="Restart replay buffer after clip saving"
    )


def script_properties():
    p = obs.obs_properties_create()  # main properties object

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
    clip_path_gr = obs.obs_properties_create()
    # video_path_gr = obs.obs_properties_create()  # todo: for future updates
    notification_gr = obs.obs_properties_create()
    popup_gr = obs.obs_properties_create()
    aliases_gr = obs.obs_properties_create()
    other_gr = obs.obs_properties_create()

    obs.obs_properties_add_group(p, PN.GR_CLIPS_PATH_SETTINGS, "Clip path settings", obs.OBS_GROUP_NORMAL, clip_path_gr)
    # obs.obs_properties_add_group(p, PN.GR_VIDEOS_PATH_SETTINGS, "Video path settings", obs.OBS_GROUP_NORMAL, video_path_gr)   # todo: for future updates
    obs.obs_properties_add_group(p, PN.GR_SOUND_NOTIFICATION_SETTINGS, "Sound notifications", obs.OBS_GROUP_CHECKABLE, notification_gr)
    obs.obs_properties_add_group(p, PN.GR_POPUP_NOTIFICATION_SETTINGS, "Popup notifications", obs.OBS_GROUP_CHECKABLE, popup_gr)
    obs.obs_properties_add_group(p, PN.GR_ALIASES_SETTINGS, "Aliases", obs.OBS_GROUP_NORMAL, aliases_gr)
    obs.obs_properties_add_group(p, PN.GR_OTHER_SETTINGS, "Other", obs.OBS_GROUP_NORMAL, other_gr)

    # ------ Setup properties ------
    setup_clip_paths_settings(clip_path_gr)
    # setup_video_paths_settings(video_path_gr)   # todo: for future updates
    setup_notifications_settings(notification_gr)
    setup_popup_notification_settings(popup_gr)
    setup_aliases_settings(aliases_gr)
    setup_other_settings(other_gr)

    return p


# -------------------- properties_callbacks.py --------------------
# All UI callbacks have the same parameters:
# p: properties object (controls the properties UI)
# prop: property that changed
# data: script settings
# Usually I don't use `data`, cuz we have script_settings global variable.
def open_github_callback(*args):
    webbrowser.open("https://github.com/qvvonk/smart_replays", 1)


def update_aliases_callback(p, prop, data):
    """
    Checks the list of aliases and updates aliases menu (shows / hides error texts).
    """
    invalid_format_err_text = obs.obs_properties_get(p, PN.TXT_ALIASES_INVALID_FORMAT)
    invalid_chars_err_text = obs.obs_properties_get(p, PN.TXT_ALIASES_INVALID_CHARACTERS)
    path_exists_err_text = obs.obs_properties_get(p, PN.TXT_ALIASES_PATH_EXISTS)

    settings_json: dict = json.loads(obs.obs_data_get_json(data))
    if not settings_json:
        return False

    try:
        load_aliases(settings_json)
        obs.obs_property_set_visible(invalid_format_err_text, False)
        obs.obs_property_set_visible(invalid_chars_err_text, False)
        obs.obs_property_set_visible(path_exists_err_text, False)
        return True

    except AliasInvalidCharacters as e:
        obs.obs_property_set_visible(invalid_format_err_text, False)
        obs.obs_property_set_visible(invalid_chars_err_text, True)
        obs.obs_property_set_visible(path_exists_err_text, False)
        index = e.index

    except AliasInvalidFormat as e:
        obs.obs_property_set_visible(invalid_format_err_text, True)
        obs.obs_property_set_visible(invalid_chars_err_text, False)
        obs.obs_property_set_visible(path_exists_err_text, False)
        index = e.index

    except AliasPathAlreadyExists as e:
        obs.obs_property_set_visible(invalid_format_err_text, False)
        obs.obs_property_set_visible(invalid_chars_err_text, False)
        obs.obs_property_set_visible(path_exists_err_text, True)
        index = e.index

    except AliasParsingError as e:
        index = e.index

    # If error in parsing
    settings_json[PN.PROP_ALIASES_LIST].pop(index)
    new_aliases_array = obs.obs_data_array_create()

    for index, alias in enumerate(settings_json[PN.PROP_ALIASES_LIST]):
        alias_data = obs.obs_data_create_from_json(json.dumps(alias))
        obs.obs_data_array_insert(new_aliases_array, index, alias_data)

    obs.obs_data_set_array(data, PN.PROP_ALIASES_LIST, new_aliases_array)
    obs.obs_data_array_release(new_aliases_array)
    return True


def check_filename_template_callback(p, prop, data):
    """
    Checks filename template.
    If template is invalid, shows warning.
    """
    error_text = obs.obs_properties_get(p, PN.TXT_CLIPS_FILENAME_TEMPLATE_ERR)

    try:
        gen_filename("clipname", obs.obs_data_get_string(data, PN.PROP_CLIPS_FILENAME_TEMPLATE))
        obs.obs_property_set_visible(error_text, False)
    except:
        obs.obs_property_set_visible(error_text, True)
    return True


def update_links_path_prop_visibility(p, prop, data):
    path_prop = obs.obs_properties_get(p, PN.PROP_CLIPS_LINKS_FOLDER_PATH)
    path_warn_prop = obs.obs_properties_get(p, PN.TXT_CLIPS_LINKS_FOLDER_PATH_WARNING)
    is_visible = obs.obs_data_get_bool(data, obs.obs_property_name(prop))

    obs.obs_property_set_visible(path_prop, is_visible)
    obs.obs_property_set_visible(path_warn_prop, is_visible)
    return True


def check_clips_links_folder_path_callback(p, prop, data):
    """
    Checks clips links folder path is in the same disk as OBS recordings path.
    If it's not - sets OBS records path as base path for clips + '_links' and shows warning.
    """
    warn_text = obs.obs_properties_get(p, PN.TXT_CLIPS_LINKS_FOLDER_PATH_WARNING)

    obs_records_path = Path(get_base_path())
    curr_path = Path(obs.obs_data_get_string(data, PN.PROP_CLIPS_LINKS_FOLDER_PATH))

    if not len(curr_path.parts) or obs_records_path.parts[0] == curr_path.parts[0]:
        obs.obs_property_text_set_info_type(warn_text, obs.OBS_TEXT_INFO_WARNING)
    else:
        obs.obs_property_text_set_info_type(warn_text, obs.OBS_TEXT_INFO_ERROR)
        obs.obs_data_set_string(data,
                                PN.PROP_CLIPS_LINKS_FOLDER_PATH,
                                str(obs_records_path / '_links'))
    return True


def update_notifications_menu_callback(p, prop, data):
    """
    Updates notifications settings menu.
    If notification is enabled, shows path widget.
    """
    success_path_prop = obs.obs_properties_get(p, PN.PROP_NOTIFY_CLIPS_ON_SUCCESS_PATH)
    failure_path_prop = obs.obs_properties_get(p, PN.PROP_NOTIFY_CLIPS_ON_FAILURE_PATH)

    on_success = obs.obs_data_get_bool(data, PN.PROP_NOTIFY_CLIPS_ON_SUCCESS)
    on_failure = obs.obs_data_get_bool(data, PN.PROP_NOTIFY_CLIPS_ON_FAILURE)

    obs.obs_property_set_visible(success_path_prop, on_success)
    obs.obs_property_set_visible(failure_path_prop, on_failure)
    return True


def check_base_path_callback(p, prop, data):
    """
    Checks base path is in the same disk as OBS recordings path.
    If it's not - sets OBS records path as base path for clips and shows warning.
    """
    warn_text = obs.obs_properties_get(p, PN.TXT_CLIPS_BASE_PATH_WARNING)

    obs_records_path = Path(get_base_path())
    curr_path = Path(obs.obs_data_get_string(data, PN.PROP_CLIPS_BASE_PATH))

    if not len(curr_path.parts) or obs_records_path.parts[0] == curr_path.parts[0]:
        obs.obs_property_text_set_info_type(warn_text, obs.OBS_TEXT_INFO_WARNING)
    else:
        obs.obs_property_text_set_info_type(warn_text, obs.OBS_TEXT_INFO_ERROR)
        obs.obs_data_set_string(data, PN.PROP_CLIPS_BASE_PATH, str(obs_records_path))
        print("WARN")
    return True


def import_aliases_from_json_callback(*args):
    """
    Imports aliases from JSON file.
    """
    path = obs.obs_data_get_string(VARIABLES.script_settings, PN.PROP_ALIASES_IMPORT_PATH)
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

    obs.obs_data_set_array(VARIABLES.script_settings, PN.PROP_ALIASES_LIST, arr)
    return True


def export_aliases_to_json_callback(*args):
    """
    Exports aliases to JSON file.
    """
    path = obs.obs_data_get_string(VARIABLES.script_settings, PN.PROP_ALIASES_EXPORT_PATH)
    if not path or not os.path.exists(path) or not os.path.isdir(path):
        return False

    aliases_dict = json.loads(obs.obs_data_get_last_json(VARIABLES.script_settings))
    aliases_dict = aliases_dict.get(PN.PROP_ALIASES_LIST) or CONSTANTS.DEFAULT_ALIASES

    with open(os.path.join(path, "obs_smart_replays_aliases.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps(aliases_dict, ensure_ascii=False))


# -------------------- tech.py --------------------
GetTickCount64 = ctypes.windll.kernel32.GetTickCount64
GetTickCount64.restype = ctypes.c_ulonglong


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT),
                ("dwTime", wintypes.DWORD)]


def _print(*values, sep: str | None = None, end: str | None = None, file=None, flush: bool = False):
    str_time = datetime.now().strftime(f"%d.%m.%Y %H:%M:%S")
    print(f"[{str_time}]", *values, sep=sep, end=end, file=file, flush=flush)


def get_active_window_pid() -> int | None:
    """
    Gets process ID of the current active window.
    """
    hwnd = user32.GetForegroundWindow()
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def get_process_description(executable_path: Path) -> str:
    """
    Gets the process description from the executable's file version info.
    Falls back to the executable name if no description is available.
    
    :param executable_path: Path to the executable file
    :return: Process description or executable name
    """
    try:
        print("Using win32api to get process description.")
        import win32api
        try:
            info = win32api.GetFileVersionInfo(str(executable_path), "\\")
            ms = info['FileVersionMS']
            ls = info['FileVersionLS']
            
            lang, codepage = win32api.VerQueryValue(info, '\\VarFileInfo\\Translation')[0]
            string_file_info = f'\\StringFileInfo\\{lang:04x}{codepage:04x}\\'
            
            description = win32api.VerQueryValue(info, string_file_info + 'FileDescription')
            if description and description.strip():
                return description.strip()
                
        except (ImportError, Exception):
            print("Failed to get process description using win32api, falling back to ctypes method.")
            pass
            
    except Exception:
        print("Failed to import win32api, falling back to ctypes method.")
        pass
    
    # Fallback: try using ctypes method
    try:
        print("Using ctypes to get process description.")
        import ctypes
        from ctypes import wintypes
        
        size = ctypes.windll.version.GetFileVersionInfoSizeW(str(executable_path), None)
        if size == 0:
            return executable_path.stem
            
        buffer = ctypes.create_string_buffer(size)
        ctypes.windll.version.GetFileVersionInfoW(str(executable_path), 0, size, buffer)
        
        value = ctypes.c_void_p()
        value_size = wintypes.UINT()
        
        if ctypes.windll.version.VerQueryValueW(
            buffer, 
            "\\StringFileInfo\\040904b0\\FileDescription",
            ctypes.byref(value), 
            ctypes.byref(value_size)
        ):
            description = ctypes.wstring_at(value, value_size.value - 1)
            if description and description.strip():
                return description.strip()
    except Exception:
        print("Failed to get process description using ctypes, falling back to executable name.")
        pass
    
    return executable_path.stem


def get_executable_path(pid: int) -> Path:
    """
    Gets path of process's executable.

    :param pid: process ID.
    :return: Executable path.
    """
    process_handle = ctypes.windll.kernel32.OpenProcess(0x0400 | 0x0010, False, pid)
    # PROCESS_QUERY_INFORMATION | PROCESS_VM_READ

    if not process_handle:
        raise OSError(f"Process {pid} does not exist.")

    filename_buffer = ctypes.create_unicode_buffer(260)  # Windows path is 260 characters max.
    result = ctypes.windll.psapi.GetModuleFileNameExW(process_handle, None, filename_buffer, 260)
    ctypes.windll.kernel32.CloseHandle(process_handle)
    if result:
        return Path(filename_buffer.value)
    else:
        raise RuntimeError(f"Cannot get executable path for process {pid}.")


def play_sound(path: str | Path):
    """
    Plays sound using windows engine.

    :param path: path to sound (.wav)
    """
    with suppress(Exception):
        winsound.PlaySound(str(path), winsound.SND_ASYNC)


def get_time_since_last_input() -> int:
    """
    Gets the time (in seconds) since the last mouse or keyboard input.
    """
    last_input_info = LASTINPUTINFO()
    last_input_info.cbSize = ctypes.sizeof(LASTINPUTINFO)

    if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(last_input_info)):
        current_time = GetTickCount64()
        idle_time_ms = current_time - last_input_info.dwTime
        return idle_time_ms // 1000
    return 0


def create_hard_link(file_path: Path | str, links_folder: Path | str) -> None:
    """
    Creates a hard link for `file_path`.

    :param file_path: Original file path.
    :param links_folder: Folder where the link will be created.
    """
    link_path = Path(links_folder) / Path(file_path).name

    os.makedirs(str(links_folder), exist_ok=True)
    os.link(str(file_path), link_path)


# -------------------- obs_related.py --------------------
def get_obs_config(section_name: str | None = None,
                   param_name: str | None = None,
                   value_type: type[str, int, bool, float] = str,
                   config_type: ConfigTypes = ConfigTypes.PROFILE):
    """
    Gets a value from OBS config.
    If the value is not set, it will use the default value. If there is no default value, it will return NULL.
    If section_name or param_name are not specified, returns OBS config obj.

    :param section_name: Section name. If not specified, returns the OBS config.
    :param param_name: Parameter name. If not specified, returns the OBS config.
    :param value_type: Type of value (str, int, bool, float).
    :param config_type: Which config search in? (global / profile / user (obs v31 or higher)
    """
    if config_type is ConfigTypes.PROFILE:
        cfg = obs.obs_frontend_get_profile_config()
    elif config_type is ConfigTypes.APP:
        cfg = obs.obs_frontend_get_global_config()
    else:
        if CONSTANTS.OBS_VERSION[0] < 31:
            cfg = obs.obs_frontend_get_global_config()
        else:
            cfg = obs.obs_frontend_get_user_config()

    if not section_name or not param_name:
        return cfg

    functions = {
        str: obs.config_get_string,
        int: obs.config_get_int,
        bool: obs.config_get_bool,
        float: obs.config_get_double
    }

    if value_type not in functions.keys():
        raise ValueError("Unsupported type.")

    return functions[value_type](cfg, section_name, param_name)


def get_last_replay_file_name() -> str:
    """
    Returns the last saved buffer file name.
    """
    replay_buffer = obs.obs_frontend_get_replay_buffer_output()
    cd = obs.calldata_create()
    proc_handler = obs.obs_output_get_proc_handler(replay_buffer)
    obs.proc_handler_call(proc_handler, 'get_last_replay', cd)
    path = obs.calldata_string(cd, 'path')
    obs.calldata_destroy(cd)
    obs.obs_output_release(replay_buffer)
    return path


def get_current_scene_name() -> str:
    """
    Returns the current OBS scene name.
    """
    current_scene = obs.obs_frontend_get_current_scene()
    name = obs.obs_source_get_name(current_scene)
    obs.obs_source_release(current_scene)
    return name


def get_replay_buffer_max_time() -> int:
    """
    Returns replay buffer max time from OBS config (in seconds).
    """
    config_mode = get_obs_config("Output", "Mode")
    if config_mode == "Simple":
        return get_obs_config("SimpleOutput", "RecRBTime", int)
    else:
        return get_obs_config("AdvOut", "RecRBTime", int)


def get_base_path(script_settings: Any | None = None) -> Path:
    """
    Returns the base path for clips, either from the script settings or OBS config.

    :param script_settings: Script config. If not provided, base path returns from OBS config.
    :return: The base path as a `Path` object.
    """
    if script_settings is not None:
        script_path = obs.obs_data_get_string(script_settings, PN.PROP_CLIPS_BASE_PATH)
        # If PN.PROP_CLIPS_BASE_PATH is not saved in the script config, then it has a default value,
        # which is the value from the OBS config.
        if script_path:
            return Path(script_path)

    config_mode = get_obs_config("Output", "Mode")
    if config_mode == "Simple":
        return Path(get_obs_config("SimpleOutput", "FilePath"))
    else:
        return Path(get_obs_config("AdvOut", "RecFilePath"))


def restart_replay_buffering():
    """
    Restarts replay buffering, obviously -_-
    """
    _print("Stopping replay buffering...")
    replay_output = obs.obs_frontend_get_replay_buffer_output()
    obs.obs_frontend_replay_buffer_stop()

    while not obs.obs_output_can_begin_data_capture(replay_output, 0):
        time.sleep(0.1)
    _print("Replay buffering stopped.")
    _print("Starting replay buffering...")
    obs.obs_frontend_replay_buffer_start()
    _print("Replay buffering started.")


# -------------------- script_helpers.py --------------------
def notify(success: bool, clip_path: Path, path_display_mode: PopupPathDisplayModes):
    """
    Plays and shows success / failure notification if it's enabled in notifications settings.
    """
    sound_notifications = obs.obs_data_get_bool(VARIABLES.script_settings, PN.GR_SOUND_NOTIFICATION_SETTINGS)
    popup_notifications = obs.obs_data_get_bool(VARIABLES.script_settings, PN.GR_POPUP_NOTIFICATION_SETTINGS)
    python_exe = os.path.join(get_obs_config("Python", "Path64bit", str, ConfigTypes.USER), "pythonw.exe")

    if path_display_mode == PopupPathDisplayModes.JUST_FILE:
        clip_path = clip_path.name
    elif path_display_mode == PopupPathDisplayModes.JUST_FOLDER:
        clip_path = clip_path.parent.name
    elif path_display_mode == PopupPathDisplayModes.FOLDER_AND_FILE:
        clip_path = Path(clip_path.parent.name) / clip_path.name

    if success:
        if sound_notifications and obs.obs_data_get_bool(VARIABLES.script_settings, PN.PROP_NOTIFY_CLIPS_ON_SUCCESS):
            path = obs.obs_data_get_string(VARIABLES.script_settings, PN.PROP_NOTIFY_CLIPS_ON_SUCCESS_PATH)
            play_sound(path)

        if popup_notifications and obs.obs_data_get_bool(VARIABLES.script_settings, PN.PROP_POPUP_CLIPS_ON_SUCCESS):
            subprocess.Popen([python_exe, __file__, "Clip saved", f"Clip saved to {clip_path}"])
    else:
        if sound_notifications and obs.obs_data_get_bool(VARIABLES.script_settings, PN.PROP_NOTIFY_CLIPS_ON_FAILURE):
            path = obs.obs_data_get_string(VARIABLES.script_settings, PN.PROP_NOTIFY_CLIPS_ON_FAILURE_PATH)
            play_sound(path)

        if popup_notifications and obs.obs_data_get_bool(VARIABLES.script_settings, PN.PROP_POPUP_CLIPS_ON_FAILURE):
            subprocess.Popen([python_exe, __file__, "Clip not saved", f"More in the logs.", "#C00000"])


def load_aliases(script_settings_dict: dict):
    """
    Loads aliases to `VARIABLES.aliases`.
    Raises exception if path or name are invalid.

    :param script_settings_dict: Script settings as dict.
    """
    _print("Loading aliases...")

    new_aliases = {}
    aliases_list = script_settings_dict.get(PN.PROP_ALIASES_LIST)
    if aliases_list is None:
        aliases_list = CONSTANTS.DEFAULT_ALIASES

    for index, i in enumerate(aliases_list):
        value = i.get("value")
        spl = value.split(">", 1)
        try:
            path, name = spl[0].strip(), spl[1].strip()
        except IndexError:
            raise AliasInvalidFormat(index)

        path = os.path.expandvars(path)
        if any(i in path for i in CONSTANTS.PATH_PROHIBITED_CHARS) or any(i in name for i in CONSTANTS.FILENAME_PROHIBITED_CHARS):
            raise AliasInvalidCharacters(index)

        if Path(path) in new_aliases.keys():
            raise AliasPathAlreadyExists(index)

        new_aliases[Path(path)] = name

    VARIABLES.aliases = new_aliases
    _print(f"{len(VARIABLES.aliases)} aliases are loaded.")


# -------------------- clipname_gen.py --------------------
def gen_clip_base_name(mode: ClipNamingModes | None = None) -> str:
    """
    Generates the base name of the clip based on the selected naming mode.
    It does NOT generate a new path for the clip or filename, only its base name.

    :param mode: Clip naming mode. If None, the mode is fetched from the script config.
                 If a value is provided, it overrides the configs value.
    :return: The base name of the clip based on the selected naming mode.
    """
    _print("Generating clip base name...")
    mode = obs.obs_data_get_int(VARIABLES.script_settings, PN.PROP_CLIPS_NAMING_MODE) if mode is None else mode
    mode = ClipNamingModes(mode)

    if mode == ClipNamingModes.PROCESS_DESCRIPTION:
        _print("Clip file name depends on the process description (Task Manager name).")
        pid = get_active_window_pid()
        executable_path = get_executable_path(pid)
        description = get_process_description(executable_path)
        
        # Clean the description of prohibited characters
        for char in CONSTANTS.FILENAME_PROHIBITED_CHARS:
            description = description.replace(char, '')
        
        # Replace multiple spaces with single space and strip
        description = ' '.join(description.split())
        
        _print(f"Process description (cleaned): {description}")
        return description if description else executable_path.stem

    elif mode in [ClipNamingModes.CURRENT_PROCESS, ClipNamingModes.MOST_RECORDED_PROCESS]:
        if mode is ClipNamingModes.CURRENT_PROCESS:
            _print("Clip file name depends on the name of an active app (.exe file name) at the moment of clip saving.")
            pid = get_active_window_pid()
            executable_path = get_executable_path(pid)
            _print(f"Current active window process ID: {pid}")
            _print(f"Current active window executable: {executable_path}")

        else:
            _print("Clip file name depends on the name of an app (.exe file name) "
                   "that was active most of the time during the clip recording.")
            if VARIABLES.clip_exe_history:
                executable_path = max(VARIABLES.clip_exe_history, key=VARIABLES.clip_exe_history.count)
            else:
                executable_path = get_executable_path(get_active_window_pid())

        _print(f'Searching for {executable_path} in aliases list...')
        if alias := get_alias(executable_path, VARIABLES.aliases):
            _print(f'Alias found: {alias}.')
            return alias
        else:
            _print(f"{executable_path} or its parents weren't found in aliases list. "
                   f"Assigning the name of the executable: {executable_path.stem}")
            return executable_path.stem

    else:
        _print("Clip filename depends on the name of the current scene name.")
        return get_current_scene_name()


def get_alias(executable_path: str | Path, aliases_dict: dict[Path, str]) -> str | None:
    """
    Retrieves an alias for the given executable path from the provided dictionary.

    The function first checks if the exact `executable_path` exists in `aliases_dict`.
    If not, it searches for the closest parent directory that is present in the dictionary.

    :param executable_path: A file path or string representing the executable.
    :param aliases_dict: A dictionary where keys are `Path` objects representing executable file paths
                         or directories, and values are their corresponding aliases.
    :return: The corresponding alias if found, otherwise `None`.
    """
    exe_path = Path(executable_path)
    if exe_path in aliases_dict:
        return aliases_dict[exe_path]

    for parent in exe_path.parents:
        if parent in aliases_dict:
            return aliases_dict[parent]



def gen_filename(base_name: str, template: str, dt: datetime | None = None) -> str:
    """
    Generates a file name based on the template.
    If the template is invalid or formatting fails, raises ValueError.
    If the generated name contains prohibited characters, raises SyntaxError.

    :param base_name: Base name for the file.
    :param template: Template for generating the file name.
    :param dt: Optional datetime object; uses current time if None.
    :return: Formatted file name.
    """
    if not template:
        raise ValueError

    dt = dt or datetime.now()
    filename = template.replace("%NAME", base_name)

    try:
        filename = dt.strftime(filename)
    except Exception as e:
        _print(f"An error occurred while generating the file name using the template {template}.")
        _print(traceback.format_exc())
        raise ValueError from e

    if any(i in filename for i in CONSTANTS.FILENAME_PROHIBITED_CHARS):
        raise SyntaxError
    return filename


def ensure_unique_filename(file_path: str | Path) -> Path:
    """
    Generates a unique filename by adding a numerical suffix if the file already exists.

    :param file_path: A string or Path object representing the target file.
    :return: A unique Path object with a modified name if necessary.
    """
    file_path = Path(file_path)
    parent, stem, suffix = file_path.parent, file_path.stem, file_path.suffix
    counter = 1

    while file_path.exists():
        file_path = parent / f"{stem} ({counter}){suffix}"
        counter += 1

    return file_path


# -------------------- save_buffer.py --------------------
def move_clip_file(mode: ClipNamingModes | None = None) -> tuple[str, Path]:
    old_file_path = get_last_replay_file_name()
    _print(f"Old clip file path: {old_file_path}")

    clip_name = gen_clip_base_name(mode)
    ext = old_file_path.split(".")[-1]
    filename_template = obs.obs_data_get_string(VARIABLES.script_settings,
                                                PN.PROP_CLIPS_FILENAME_TEMPLATE)
    filename = gen_filename(clip_name, filename_template) + f".{ext}"

    new_folder = Path(get_base_path(script_settings=VARIABLES.script_settings))
    if obs.obs_data_get_bool(VARIABLES.script_settings, PN.PROP_CLIPS_SAVE_TO_FOLDER):
        new_folder = new_folder / clip_name

    os.makedirs(str(new_folder), exist_ok=True)
    new_path = new_folder / filename
    new_path = ensure_unique_filename(new_path)
    _print(f"New clip file path: {new_path}")

    os.rename(old_file_path, str(new_path))
    _print("Clip file successfully moved.")
    os.utime(new_folder)

    if obs.obs_data_get_bool(VARIABLES.script_settings, PN.PROP_CLIPS_CREATE_LINKS):
        links_folder = obs.obs_data_get_string(VARIABLES.script_settings, PN.PROP_CLIPS_LINKS_FOLDER_PATH)
        create_hard_link(new_path, links_folder)
    return clip_name, new_path


def save_buffer_with_force_mode(mode: ClipNamingModes):
    """
    Sends a request to save the replay buffer and setting a specific clip naming mode.
    Can only be called using hotkeys.
    """
    if not obs.obs_frontend_replay_buffer_active():
        return

    if CONSTANTS.CLIPS_FORCE_MODE_LOCK.locked():
        return

    CONSTANTS.CLIPS_FORCE_MODE_LOCK.acquire()
    VARIABLES.force_mode = mode
    obs.obs_frontend_replay_buffer_save()


# -------------------- obs_events_callbacks.py --------------------
def on_buffer_recording_started_callback(event):
    """
    Resets and starts recording executables history.
    Starts replay buffer auto restart loop.
    """
    if event is not obs.OBS_FRONTEND_EVENT_REPLAY_BUFFER_STARTED:
        return

    # Reset and restart exe history
    VARIABLES.clip_exe_history = deque([], maxlen=get_replay_buffer_max_time())
    _print(f"Exe history deque created. Maxlen={VARIABLES.clip_exe_history.maxlen}.")
    obs.timer_add(append_clip_exe_history, 1000)

    # Start replay buffer auto restart loop.
    if restart_loop_time := obs.obs_data_get_int(VARIABLES.script_settings, PN.PROP_RESTART_BUFFER_LOOP):
        obs.timer_add(restart_replay_buffering_callback, restart_loop_time * 1000)


def on_buffer_recording_stopped_callback(event):
    """
    Stops recording executables history.
    Stops replay buffer auto restart loop.
    """
    if event is not obs.OBS_FRONTEND_EVENT_REPLAY_BUFFER_STOPPED:
        return

    obs.timer_remove(append_clip_exe_history)
    obs.timer_remove(restart_replay_buffering_callback)
    VARIABLES.clip_exe_history.clear()


def on_buffer_save_callback(event):
    if event is not obs.OBS_FRONTEND_EVENT_REPLAY_BUFFER_SAVED:
        return

    path_display_type = obs.obs_data_get_int(VARIABLES.script_settings,
                                             PN.PROP_POPUP_PATH_DISPLAY_MODE)
    path_display_type = PopupPathDisplayModes(path_display_type)

    _print(f"{'SAVING BUFFER':->50}")

    try:
        clip_name, path = move_clip_file(mode=VARIABLES.force_mode)
        if obs.obs_data_get_bool(VARIABLES.script_settings, PN.PROP_RESTART_BUFFER):
            # IMPORTANT
            # I don't know why, but it seems like stopping and starting replay buffering should be in the separate thread.
            # Otherwise it can "stuck" on stopping.
            Thread(target=restart_replay_buffering, daemon=True).start()

        if VARIABLES.force_mode:
            VARIABLES.force_mode = None
            CONSTANTS.CLIPS_FORCE_MODE_LOCK.release()

        notify(True, path, path_display_mode=path_display_type)
    except:
        _print("An error occurred while moving file to the new destination.")
        _print(traceback.format_exc())
        notify(False, Path(), path_display_mode=path_display_type)
    _print("-" * 50)


def on_video_recording_started_callback(event):  # todo: for future updates
    if event is not obs.OBS_FRONTEND_EVENT_RECORDING_STARTED:
        return

    VARIABLES.video_exe_history = defaultdict(int)
    obs.timer_add(append_video_exe_history, 1000)


def on_video_recording_stopping_callback(event):  # todo: for future updates
    if event is not obs.OBS_FRONTEND_EVENT_RECORDING_STOPPING:
        return

    obs.timer_remove(append_video_exe_history)


def on_video_recording_stopped_callback(event):  # todo: for future updates
    if event is not obs.OBS_FRONTEND_EVENT_RECORDING_STOPPED:
        return

    VARIABLES.video_exe_history = None


# -------------------- other_callbacks.py --------------------
def restart_replay_buffering_callback():
    """
    Restarts replay buffering and adds itself to obs timer.

    This callback is only called by the obs timer.
    """
    _print("Restart replay buffering callback.")
    obs.timer_remove(restart_replay_buffering_callback)

    replay_length = get_replay_buffer_max_time()
    last_input_time = get_time_since_last_input()
    if last_input_time < replay_length:
        next_call = int((replay_length - last_input_time) * 1000)
        next_call = next_call if next_call >= 2000 else 2000

        _print(f"Replay length ({replay_length}s) is greater then time since last input ({last_input_time}s). Next call in {next_call / 1000}s.")
        obs.timer_add(restart_replay_buffering_callback, next_call)
        return

    # IMPORTANT
    # I don't know why, but it seems like stopping and starting replay buffering should be in the separate thread.
    # Otherwise it can "stuck" at stopping state.
    Thread(target=restart_replay_buffering, daemon=True).start()
    # I don't re-add this callback to timer again, cz it will be automatically added in on buffering start callback.


def append_clip_exe_history():
    """
    Adds current active executable path in clip exe history.
    """
    with suppress(Exception):
        pid = get_active_window_pid()
        exe = get_executable_path(pid)
        VARIABLES.clip_exe_history.appendleft(exe)


def append_video_exe_history():
    """
    Adds current active executable path in video exe history.
    """
    with suppress(Exception):
        pid = get_active_window_pid()
        exe = get_executable_path(pid)
        VARIABLES.video_exe_history[exe] += 1


# -------------------- hotkeys.py --------------------
def load_hotkeys():
    keys = (
        (PN.HK_SAVE_BUFFER_MODE_1, "[Smart Replays] Save buffer (active exe)",
         lambda pressed: save_buffer_with_force_mode(ClipNamingModes.CURRENT_PROCESS) if pressed else None),

        (PN.HK_SAVE_BUFFER_MODE_2, "[Smart Replays] Save buffer (most recorded exe)",
         lambda pressed: save_buffer_with_force_mode(ClipNamingModes.MOST_RECORDED_PROCESS) if pressed else None),

        (PN.HK_SAVE_BUFFER_MODE_3, "[Smart Replays] Save buffer (active scene)",
         lambda pressed: save_buffer_with_force_mode(ClipNamingModes.CURRENT_SCENE) if pressed else None),

        (PN.HK_SAVE_BUFFER_MODE_4, "[Smart Replays] Save buffer (program description)",
         lambda pressed: save_buffer_with_force_mode(ClipNamingModes.PROCESS_DESCRIPTION) if pressed else None)
    )

    for key_name, key_desc, key_callback in keys:
        key_id = obs.obs_hotkey_register_frontend(key_name, key_desc, key_callback)
        VARIABLES.hotkey_ids.update({key_name: key_id})
        key_data = obs.obs_data_get_array(VARIABLES.script_settings, key_name)
        obs.obs_hotkey_load(key_id, key_data)
        obs.obs_data_array_release(key_data)


# -------------------- obs_script_other.py --------------------
def script_defaults(s):
    _print("Loading default values...")
    obs.obs_data_set_default_string(s, PN.PROP_CLIPS_BASE_PATH, str(get_base_path()))
    obs.obs_data_set_default_int(s, PN.PROP_CLIPS_NAMING_MODE, ClipNamingModes.CURRENT_PROCESS.value)
    obs.obs_data_set_default_string(s, PN.PROP_CLIPS_FILENAME_TEMPLATE, CONSTANTS.DEFAULT_FILENAME_FORMAT)
    obs.obs_data_set_default_bool(s, PN.PROP_CLIPS_SAVE_TO_FOLDER, True)
    obs.obs_data_set_default_string(s, PN.PROP_CLIPS_LINKS_FOLDER_PATH, str(get_base_path() / '_links'))

    # obs.obs_data_set_default_int(s, PN.PROP_VIDEOS_NAMING_MODE, VideoNamingModes.MOST_RECORDED_PROCESS.value)
    # obs.obs_data_set_default_string(s, PN.PROP_VIDEOS_FILENAME_FORMAT, CONSTANTS.DEFAULT_FILENAME_FORMAT)
    # obs.obs_data_set_default_bool(s, PN.PROP_VIDEOS_SAVE_TO_FOLDER, True)

    obs.obs_data_set_default_bool(s, PN.PROP_NOTIFY_CLIPS_ON_SUCCESS, False)
    obs.obs_data_set_default_bool(s, PN.PROP_NOTIFY_CLIPS_ON_FAILURE, False)
    obs.obs_data_set_default_bool(s, PN.PROP_POPUP_CLIPS_ON_SUCCESS, False)
    obs.obs_data_set_default_bool(s, PN.PROP_POPUP_CLIPS_ON_FAILURE, False)
    obs.obs_data_set_default_int(s, PN.PROP_POPUP_PATH_DISPLAY_MODE, PopupPathDisplayModes.FULL_PATH.value)

    obs.obs_data_set_default_int(s, PN.PROP_RESTART_BUFFER_LOOP, 3600)
    obs.obs_data_set_default_bool(s, PN.PROP_RESTART_BUFFER, True)

    arr = obs.obs_data_array_create()
    for index, i in enumerate(CONSTANTS.DEFAULT_ALIASES):
        data = obs.obs_data_create_from_json(json.dumps(i))
        obs.obs_data_array_insert(arr, index, data)

    obs.obs_data_set_default_array(s, PN.PROP_ALIASES_LIST, arr)
    _print("The default values are set.")


def script_update(settings):
    _print("Updating script...")

    VARIABLES.script_settings = settings
    _print(obs.obs_data_get_json(VARIABLES.script_settings))
    _print("Script updated")


def script_save(settings):
    _print("Saving script...")

    for key_name in VARIABLES.hotkey_ids:
        k = obs.obs_hotkey_save(VARIABLES.hotkey_ids[key_name])
        obs.obs_data_set_array(settings, key_name, k)
    _print("Script saved")


def script_load(script_settings):
    _print("Loading script...")
    VARIABLES.script_settings = script_settings
    # VARIABLES.update_available = check_updates(CONSTANTS.VERSION)  # todo: for future updates

    json_settings = json.loads(obs.obs_data_get_json(script_settings))
    load_aliases(json_settings)

    obs.obs_frontend_add_event_callback(on_buffer_save_callback)
    obs.obs_frontend_add_event_callback(on_buffer_recording_started_callback)
    obs.obs_frontend_add_event_callback(on_buffer_recording_stopped_callback)

    # obs.obs_frontend_add_event_callback(on_video_recording_started_callback)  # todo: for future updates
    # obs.obs_frontend_add_event_callback(on_video_recording_stopping_callback)  # todo: for future updates
    # obs.obs_frontend_add_event_callback(on_video_recording_stopped_callback)  # todo: for future updates
    load_hotkeys()

    if obs.obs_frontend_replay_buffer_active():
        on_buffer_recording_started_callback(obs.OBS_FRONTEND_EVENT_REPLAY_BUFFER_STARTED)

    _print("Script loaded.")


def script_unload():
    obs.timer_remove(append_clip_exe_history)
    obs.timer_remove(restart_replay_buffering_callback)

    _print("Script unloaded.")


def script_description():
    return f"""
<div style="font-size: 60pt; text-align: center;">
Smart Replays 
</div>

<div style="font-size: 12pt; text-align: left;">
Smart Replays is an OBS script whose main purpose is to save clips with different names and to separate folders depending on the application being recorded (imitating NVIDIA Shadow Play functionality). This script also has additional functionality, such as sound and pop-up notifications, auto-restart of the replay buffer, etc.
</div>

<div style="font-size: 10pt; text-align: left; margin-top: 20px;">
Version: {CONSTANTS.VERSION}<br/>
Developed by: Qvvonk<br/>
</div>
"""