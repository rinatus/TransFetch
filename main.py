import sys
import os
import shutil
from utils.utils import RED, GREEN, CYAN, PURPLE, ENDC, get_country_name
from transmission.transmission import CTorrent, squeeze_log_file
from config import TMP_DIR, TARGET_BASE_DIR, WORK_DIR_BASE, LOCAL_FILE_BASE, KINOZAL_BASE
import config as cfg
from kinozal.kinozal import CKinozal
from kinozal.login_check import make_kinozal_check
from datetime import datetime
from config import WORK_DIR_BASE, TMP_DIR



# gio mount "afp://rinatb@NAS4.local/TORRENT"

# Un-mount:
# gio mount -u "afp://rinatb@NAS4.local/TORRENT"
"""
You may be prompted for a password. You can store credentials in the GNOME keyring or pass it with --password, though that's less secure.

Create a script, e.g. ~/mount_afp.sh:
#!/bin/bash
gio mount "afp://rinatb@NAS4.local/TORRENT"

chmod +x ~/mount_afp.sh

Add to startup:
Menu → "Startup Applications" → Add → Custom command:
/home/yourusername/mount_afp.sh

"""



print(f'{GREEN}Start <{TMP_DIR}>{ENDC}')

print(get_country_name())   




# if not os.path.isdir(WORK_DIR_BASE):
#     print(f"Start check WORK_DIR_BASE: {RED}not mounted:{ENDC} {WORK_DIR_BASE}")
#     sys.exit()

# if not os.path.isdir(TMP_DIR):
#     print(f"Start check TMP_DIR: {RED}not mounted:{ENDC} {TMP_DIR}")
#     sys.exit()
# if not os.path.isdir(LOCAL_FILE_BASE):
#     print(f"Start check LOCAL_FILE_BASE: {RED}not mounted:{ENDC} {LOCAL_FILE_BASE}")
#     sys.exit()
# if not os.path.isdir(TARGET_BASE_DIR):
#     print(f"NAS4 TORRENT {RED}not mounted:{ENDC} {TARGET_BASE_DIR}")
#     sys.exit()


k_id = 2090510
session = make_kinozal_check(False, k_id)
if not session:
    print(f"{RED}make_kinozal_check ({k_id}): Connection failed, STOP.{ENDC}")
    print(f"{RED}Torrent site {KINOZAL_BASE} NOT working.{ENDC}")
    sys.exit()

sys.exit()


tr_client = CTorrent(TMP_DIR)
if tr_client.tc is None:
    print(f"{RED}Transmission is not running, STOP.{ENDC}")
    sys.exit(-1)

# full_target_dir:
# /run/user/1000/gvfs/afp-volume:host=NAS4.local,user=rinatb,volume=TORRENT/СЕРИАЛЫ/2025/Разящий%20луч
# TARGET_BASE_DIR_A = "/run/user/1000/gvfs/afp-volume:host=NAS4.local,user=rinatb,volume=TORRENT"
# TARGET_BASE_DIR_S = "/run/user/1000/gvfs/smb-share:server=nas4.local,share=torrent"

active_torrents_dict = tr_client.check_for_move("TORRENTS.json")
squeeze_log_file("TORRENTS.json", active_torrents_dict)

kinozal = CKinozal("kinozal.json", in_session=session)
cnt_new = kinozal.process_serials(tr_client)

now_str = str(datetime.now())
pos = now_str.rfind('.')
now_str = now_str[:pos]
if cnt_new:
    print(f"{CYAN}{now_str}  new items: {cnt_new}{ENDC}")
else:
    print(f"{now_str}  new items: {cnt_new}")


