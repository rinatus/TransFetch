import os
import sys
from utils.utils import RED, GREEN, CYAN, PURPLE, ENDC

KINOZAL_BASE = "kinozal.guru"
KINOZAL_F_BASE = "[kinozal]id{ID}.torrent"

# gio mount "afp://rinatb@NAS4.local/TORRENT"
# gio mount -u "afp://rinatb@NAS4.local/TORRENT"
"""
You may be prompted for a password. You can store credentials in the GNOME keyring or pass it with --password, though that's less secure.
s
Create a script, e.g. ~/mount_afp.sh:
#!/bin/bash
gio mount "afp://rinatb@NAS4.local/TORRENT"

chmod +x ~/mount_afp.sh

Add to startup:
Menu → "Startup Applications" → Add → Custom command:
/home/yourusername/mount_afp.sh

"""

# TARGET_BASE_DIR_A = "/run/user/1000/gvfs/afp-volume:host=NAS4.local,user=rinatb,volume=TORRENT"
TARGET_BASE_DIR_A = "\\\\nas4\\TORRENT"
TARGET_BASE_DIR_S = "/run/user/1000/gvfs/smb-share:server=nas4.local,share=torrent"

# TMP_DIR = "/run/user/1000/gvfs/smb-share:server=nas4.local,share=torrent/_KINO/$tmp"
# /run/user/1000/gvfs/smb-share:server=nas4.local,share=downloads/complete

# TMP_DIR = "/media/rinatb/SAMSUNG-4TB/KINO_TMP"
TMP_DIR = "X:\\$tmp"
WORK_DIR_BASE = "./torrents/"

# LOCAL_FILE_BASE == fully qualified path for WORK_DIR_BASE
# required only to feed torrent instance
LOCAL_FILE_BASE = "/home/rinatb/projects/transfetch/torrents"

if os.path.isdir(TARGET_BASE_DIR_A):
    TARGET_BASE_DIR = TARGET_BASE_DIR_A
    print(f"TARGET_BASE_DIR: {GREEN}faster:{ENDC} {TARGET_BASE_DIR}")
elif os.path.isdir(TARGET_BASE_DIR_S):
    TARGET_BASE_DIR = TARGET_BASE_DIR_S
    print(f"TARGET_BASE_DIR: {PURPLE}slower:{ENDC} {TARGET_BASE_DIR}")
else:
    print(f"Start check TARGET_BASE_DIR: {RED}not mounted:{ENDC} {TARGET_BASE_DIR_A}\n{TARGET_BASE_DIR_S}")
    sys.exit()