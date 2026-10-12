from transmission_rpc import Client, error, Torrent
import os
import sys
from pprint import pprint
import requests
import shutil
from utils.utils import RED, GREEN, CYAN, GRAY, ENDC
from utils.utils import read_JSON_from_file, write_JSON_to_file
from utils.utils import move_file
from config import KINOZAL_F_BASE, LOCAL_FILE_BASE, TMP_DIR
from utils.torrent_decode import TDecoder


from typing import List, Dict



# def move_file_old(src_path_name: str, dst_path: str) -> str:
#     norm_src_path_name = os.path.normpath(src_path_name)
#     norm_target_path = os.path.normpath(dst_path)

#     try:
#         shutil.copy(norm_src_path_name, norm_target_path)
#     except OSError:
#         pass
    
#     file_name = os.path.basename(norm_src_path_name)
#     norm_dst_path_name = os.path.normpath(os.path.join(dst_path, file_name))
#     if not os.path.isfile(norm_dst_path_name):
#         print(f"{RED}incorrect target file: {norm_dst_path_name}{ENDC}")
#         return None
#     else:
#         print(f"{GREEN}file {norm_dst_path_name} was copied OK.{ENDC}")
#         os.remove(norm_src_path_name)
#         return norm_dst_path_name


def get_transmission_client(host: str = None, user: str = None, pwd: str = None) -> Client:
    try:
        # Client(host="localhost", port=9091, username="transmission", password="password")
        # http://192.168.1.244:9091/transmission/web/
        # tc = Client(host="192.168.1.244", port=9091, username='admin', password='admin')

        tc = None
        if not host:
            tc = Client()
        else:
            tc = Client(host=host, port=9091, username=user, password=pwd)
        return tc
    except error.TransmissionError as ex:
        print(f"transmission_rpc error: {ex}")
    except requests.exceptions.ConnectionError:
        print(f"transmission_rpc connection error")
    except requests.exceptions.ReadTimeout as ex:
        print(f"transmission_rpc error: {ex}")
    return None


def get_files_from_torrent_file(torrent_file_path_name: str) -> List:

    try:
        meta_info = open(torrent_file_path_name, "rb").read()
        torrent = TDecoder(meta_info).decode()

        files_list = []
        tr_files = torrent[b"info"][b'files']
        for file in tr_files:
            fname = file[b"path"][0].decode("utf-8")
            files_list.append(fname)
        return files_list
    except IndexError as ex:
        print(RED + f"{ex}" + ENDC)
        return None


# initiate torrent object only with fully-qualified path to downloaded torrent file
# because transmission doesn't know about realtive pathes
def make_torrent_file_full_path_name(k_id: int):
    torrent_fname = KINOZAL_F_BASE.format(ID=k_id)  # [kinozal.tv]id12345.torrent
    # "E:\\DEV\\python\\transfer_scripts\\torrents\\[kinozal.tv]id1761504.torrent"
    torrent_file_full_path_name = os.path.join(LOCAL_FILE_BASE, torrent_fname)
    return torrent_file_full_path_name


def add_new_record_JSON(json_log_file: str, hash: str, rec: Dict):
    if os.path.isfile(json_log_file):
        map = read_JSON_from_file(json_log_file)  # map hashstring -> other torrent data
        if hash not in map:
            map[hash] = rec
            write_JSON_to_file(map, json_log_file)
        else:
            print(f"add_new_record_JSON key error {hash}")
    else:
        map = {hash: rec}
        write_JSON_to_file(map, json_log_file)


def squeeze_log_file(json_log_file: str, active_torrents_dict: Dict):
    if os.path.isfile(json_log_file):
        map = read_JSON_from_file(json_log_file)  # map hashstring -> other torrent data
        for k, value in map.copy().items():
            if k not in active_torrents_dict:
                del map[k]
        write_JSON_to_file(map, json_log_file)


# https://github.com/Trim21/transmission-rpc/blob/master/doc/rpc-spec.txt
class CTorrent():
    tc = None
    tmp_dir = ""

    def __init__(self, tmp_dir: str, conn: dict = None):
        last_char = tmp_dir[-1]
        if last_char in ['/', '\\']:
            print(f"{RED}no slashes allowed at the end of the tmp_dir - transmission behaves weird.{ENDC}")
            return
        if conn:
            self.tc = get_transmission_client(host=conn['host'],
                                              user=conn['user'],
                                              pwd = conn['pwd'])
        else:
            self.tc = get_transmission_client()

        self.tmp_dir = tmp_dir

        if self.tc is not None:
            torrents_list = self.tc.get_torrents()
            print(f"Transmission is running, {len(torrents_list)} torrents\n")
            for tr in torrents_list:
                prc = tr.percent_done*100
                st_col = GREEN if prc == 100 else GRAY
                col = st_col if TMP_DIR in tr.download_dir else RED
                print(f"{col}{tr.name} {tr.status} {prc:.2f}%  [{tr.download_dir}]{ENDC}")

    def get_torrent_info(tr: Torrent) -> tuple:
        return tr.percent_done, tr.download_dir, tr.name


    def _delete_torrent_and_tmp_dir(self, torrent_hash: str, in_tmp_dir_full_path: str):
        """
        чтобы успешно удалить временную папку с файлами, надо сначала остановить и удалить торрент из transmission
        moved_files - list of moved_file_path_name
        """
        if os.path.isdir(in_tmp_dir_full_path):
            print(f"deleting folder [{in_tmp_dir_full_path}] …")

            col = GREEN if TMP_DIR in in_tmp_dir_full_path else RED
            print(col + f"Attempt to delete [{in_tmp_dir_full_path}]." + ENDC)
            self.tc.stop_torrent(torrent_hash)
            print(CYAN + "Attempt to remove torrent." + ENDC)
            self.tc.remove_torrent(torrent_hash)
            print(col + f"rmtree {in_tmp_dir_full_path}" + ENDC)
            shutil.rmtree(in_tmp_dir_full_path, ignore_errors=True)

    def _move_completed_files_from_tmp(self, tr_files_list, in_full_target_dir) -> bool:
        """
        """
        #  # full_target_dir - V:\NEW\СЕРИАЛЫ\РУС\Гранд
        # moved_files = []
        cnt_moved: int = 0
        cnt_selected: int = 0
        for file_attr in tr_files_list:
            if file_attr.selected:  # move only checked for download files
                cnt_selected += 1
                file_name_from_transmission = file_attr.name
                full_src_path_name = os.path.join(self.tmp_dir, file_name_from_transmission)
                if os.path.isfile(full_src_path_name):
                    _dir, _fname = os.path.split(full_src_path_name)
                    print(f" MOVE {full_src_path_name} to {in_full_target_dir}")
                    # MOVE
                    # /media/rinatb/I7-2TB/DEV/KINO_TMP/Kombinaciya.S01.2024.WEB-DL.1080p.ExKinoRay/Kombinaciya.S01.E06.2024.WEB-DL.1080p.ExKinoRay.mkv
                    # to
                    # smb://nas4.local/torrent/NEW/СЕРИАЛЫ/РУС/2024/Комбинация
                    moved_file_path_name = os.path.join(in_full_target_dir, _fname)
                    if not os.path.isfile(moved_file_path_name):  # if not exist on destination
                        shutil_move_dst = move_file(full_src_path_name, in_full_target_dir)

                        if shutil_move_dst == moved_file_path_name:
                            cnt_moved += 1
                        else:
                            col = GREEN if TMP_DIR in full_src_path_name else RED
                            print(col + f"{full_src_path_name}\n was moved to {in_full_target_dir} OK." + ENDC)
                    else:
                        print(f"WARNING: {moved_file_path_name} already exist.")

        all_moved_OK = cnt_moved == cnt_selected
        _txt = "Looks like all files moved OK"
        col = GREEN
        if not all_moved_OK:
            _txt = "Move FAILED."
            col = RED

        print(col + f"{_txt} moved: {cnt_moved} selected: {cnt_selected}" + ENDC)
        return all_moved_OK

    def check_for_move(self, json_log_file: str) -> Dict:
        torrents_list = self.tc.get_torrents()
        js = read_JSON_from_file(json_log_file)
        active_torrents_dict = {}
        for tr in torrents_list:
            prc_done = tr.percent_done
            active_torrents_dict[tr.hashString] = prc_done
            if prc_done == 1:  # torrent completed
                print(f"\nCheck for move: {tr.name} {tr.status} {tr.hashString} {prc_done}")
                if tr.error != 0:
                    print(RED + f"{tr.name} has error [{tr.error}] [{tr.error_string}]" + ENDC)
                    continue

                tmp_dir_full_path = os.path.join(tr.download_dir, tr.name)
                files_list = tr.get_files()
                # item: attributes map
                # {'selected': True, 'priority': 'normal', 'size': 1734862464,
                #
                # 'name':
                # 'Mir.druzba.zvacka.2020.WEB-DL.(1080p).Getty/Mir.druzba.zvacka.e01.2020.WEB-DL.(1080p).Getty.mkv',
                #
                # 'completed': 1734862464}

                if tr.hash_string in js:  # нужен только (пока) для "target_dir"
                    full_target_dir = js[tr.hash_string]["target_dir"]
                    if not os.path.isdir(full_target_dir):
                        print(f"NAS4 target {RED}not found:{ENDC} {full_target_dir}")
                        continue

                    all_ok = self._move_completed_files_from_tmp(files_list, full_target_dir)
                    print(all_ok)
                    if all_ok:
                        self._delete_torrent_and_tmp_dir(tr.hash_string, tmp_dir_full_path)

        return active_torrents_dict

    def start_download(self, kin_id: int, target_dir: str) -> bool:
        idx_dont = self._get_files_dont_download(kin_id, target_dir)
        if idx_dont is None:
            print(RED + f"torrent file for {kin_id} looks damaged." + ENDC)
            # idx_dont = list(range(n_last_episode))
            # print(RED + f"Attempt from last episode: {idx_dont}." + ENDC)
            return False

        new_torrent = self._start_kinozal_torrent(kin_id, idx_dont)
        json_rec = {'kinozalID': kin_id, 'target_dir': target_dir, 'torrent_id': new_torrent.id,
                    'torrent_name': new_torrent.name, 'completed': False,
                    'moved': False}
        add_new_record_JSON('TORRENTS.json', new_torrent.hashString, json_rec)
        return True

    def _start_kinozal_torrent(self, kin_id: int, idx_dont):
        torrent_file_full_path_name = make_torrent_file_full_path_name(kin_id)

        new_torrent = self.tc.add_torrent(torrent_file_full_path_name, paused=False, download_dir=self.tmp_dir)
        # new_torrent = self.tc.add_torrent(torrent_file_full_path_name, paused=False)
        print(new_torrent.hashString)
        if len(idx_dont) > 0:
            self.tc.change_torrent(new_torrent.hashString, files_unwanted=idx_dont)
        return new_torrent

    def _get_files_dont_download(self, kin_id: int, target_dir: str):
        torrent_file_full_path_name = make_torrent_file_full_path_name(kin_id)

        list_of_files = get_files_from_torrent_file(torrent_file_full_path_name)
        if list_of_files is None:
            # attempt to create indices 'do not' from the files in target dir
            return None

        idx_dont = []
        idx: int = 0
        for file_name in list_of_files:
            episode_path_name = os.path.join(target_dir, file_name)
            if os.path.isfile(episode_path_name):
                idx_dont.append(idx)
            idx += 1
        return idx_dont
