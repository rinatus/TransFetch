from utils.utils import RED, GREEN, CYAN, PURPLE, ENDC,YELLOW
from transmission.transmission import CTorrent, squeeze_log_file
from config import TMP_DIR, WORK_DIR_BASE, TARGET_BASE_DIR, LOCAL_FILE_BASE

# from utils.utils import copy_with_progress
import shutil
from timeit import default_timer as timer
import os
from tqdm import tqdm
import sys



def copy_with_progress(src_file_path_name: str, dst_file_path_name: str):
    total_size = os.path.getsize(src_file_path_name)
    with open(src_file_path_name, 'rb') as fsrc, open(dst_file_path_name, 'wb') as fdst:
        # with tqdm(total=total_size, unit='B', unit_scale=True, desc=dst) as pbar:
        with tqdm(total=total_size, unit='B', unit_scale=True) as pbar:
            for chunk in iter(lambda: fsrc.read(1024 * 1024), b''):
                fdst.write(chunk)
                pbar.update(len(chunk))

print(f"{RED}RED{ENDC}")
print(f"{GREEN}GREEN{ENDC}")
print(f"{CYAN}CYAN{ENDC}")
print(f"{PURPLE}PURPLE{ENDC}")
print(f"{YELLOW}YELLOW{ENDC}")

tr_nas = CTorrent(TMP_DIR)
if tr_nas.tc is None:
    print(f"{RED}Transmission is not running, STOP.{ENDC}")

conn = {
    "host": os.environ["TRANSMISSION_HOST"],
    "user": os.environ["TRANSMISSION_USERNAME"],
    "pwd": os.environ["TRANSMISSION_PASSWORD"],
}
tr_nas = CTorrent(TMP_DIR, conn)
if tr_nas.tc is None:
    print(f"{RED}Transmission is not running, STOP.{ENDC}")

# torrent_url = "magnet:?xt=urn:btih:e84213a794f3ccd890382a54a64ca68b7e925433&dn=ubuntu-18.04.1-desktop-amd64.iso"
# tr_nas.tc.add_torrent(torrent_url)

with open("torrents/[kinozal.tv]id1930991.torrent", "rb") as f:
    binary_data = f.read()
    tr_nas.tc.add_torrent(binary_data)

sys.exit()


TMP_DIR_REMOTE = "/run/user/1000/gvfs/smb-share:server=nas4.local,share=downloads/complete"

file_name = "ubuntu-18.04.1-desktop-amd64.iso"
src_path_name = os.path.join(TMP_DIR_REMOTE, file_name)
if not os.path.isfile(src_path_name):
    print(f"{RED}Invalid source file {src_path_name}{ENDC}")
    sys.exit()

dst_path = os.path.join(TARGET_BASE_DIR, "NEW/СЕРИАЛЫ/РУС/2024/Трасса")
if not os.path.isdir(dst_path):
    print(f"{RED}Invalid destination directory {dst_path}{ENDC}")
    sys.exit()

dst_path_name = os.path.join(dst_path, file_name)

start = timer()
copy_with_progress(src_path_name, dst_path_name)
# shutil.move(src_path_name, dst_path)
# shutil.move(dst_path, src_path_name)
end = timer()
print(end - start)