from typing import Dict
import sys
import os
import re
import requests
from requests import sessions
from kinozal.credentials import get_login_payload

from bs4 import BeautifulSoup
from utils.utils import GREEN, RED, PURPLE, YELLOW, ENDC, get_country_name
from utils.utils import read_JSON_from_file, read_text_file, write_text_file

from transmission.transmission import CTorrent, make_torrent_file_full_path_name

from config import KINOZAL_F_BASE, KINOZAL_BASE, WORK_DIR_BASE, TARGET_BASE_DIR

print('__file__={0:<35} | __name__={1:<20} | __package__={2:<20}'.format(__file__, __name__, str(__package__)))


def kinozal():
    print("kinozal imported successfully")


def _get_total_episodes_from_web_descr(text_descr: str) -> int:
    """
     Беезумие (1-8 серии из 8) / 2020 / РУ / WEBRip (1080p) => 8
     Stand Up (7 сезон: 1-23 выпуски) / 2019 / РУ / WEB-DL (720p) => -1
     Окаянные дни (1 сезон: 1-7 серии из 10) / 2020 / РУ / WEB-DL (1080p) => 10
    """
    # https://github.com/PyCQA/pycodestyle/issues/766
    _a = re.split(r';|,|\ |\(|\)|\n|\*|/|\.|\[|\]|#|\^|\+|:|=|!|\'|\?|\"|\@|>|%|_|&|\||~|<|\$|{|}', text_descr)
    # remove all but - (minus)
    # [Дылды,1,сезон,1-7,серии,из,21,2019,РУ,WEB-DL,1080p]

    sz: int = len(_a)
    for i in range(sz):
        sub_str = _a[i]
        sub_str = sub_str.strip()
        if len(sub_str) > 0:
            if sub_str == "из":
                if i < sz-1:
                    next_word: str = _a[i+1]
                    if next_word.isdigit():
                        return int(next_word)
    return -1


def _get_last_episode_from_web_descr(text_descr: str) -> int:
    """
        extract last episode from the text_descr like
        Дылды (1 сезон: 1-7 серии из 21) / 2019 / РУ / WEB-DL (1080p)
    """
    # https://github.com/PyCQA/pycodestyle/issues/766
    _a = re.split(r';|,|\ |\(|\)|\n|\*|/|\.|\[|\]|#|\^|\+|:|=|!|\'|\?|\"|\@|>|%|_|&|\||~|<|\$|{|}', text_descr)
    # remove all but - (minus)
    # [Дылды,1,сезон,1-7,серии,из,21,2019,РУ,WEB-DL,1080p]
    words_list: list = []
    for sub_str in _a:
        sub_str = sub_str.strip()
        if len(sub_str) > 0:
            words_list.append(sub_str)

        pos = sub_str.find('-')  # u'1-16'
        if pos > 0:
            _a1 = sub_str.split('-')
            if len(_a1) == 2 and _a1[0].isdigit() and _a1[1].isdigit():
                return int(_a1[1])

    # not found, but it could be like
    # "СидЯдома (1 серия) / 2020 / РУ / WEB-DL (1080p)"
    for word in words_list:
        if word.isdigit():
            n = int(word)
            if n == 1:
                return 1
    return 0


def _extract_episode_number_start(fileName: str, str_from_start: str, N: int) -> int:
    if fileName.startswith(str_from_start):
        s_tmp = fileName.replace(str_from_start, '')
        s_episode = s_tmp[0:N]
        if s_episode.isdigit():
            return int(s_episode)
    return 0

def _extract_episode_number_pattern(fileName: str, pattern: str, N: int) -> int:
    pos = fileName.upper().find(pattern.upper())
    if pos != -1:
        slice_start = pos + len(pattern)
        ep_num_str = fileName[slice_start:slice_start + N]
        if ep_num_str.isdigit():
            return int(ep_num_str)
    return 0

def _extract_episode_number(fileName: str, str_to_find: str, N: int) -> int:
    if str_to_find and str_to_find[0] == '|': # str from start
        str_pattern = str_to_find.strip('|')
        return _extract_episode_number_pattern(fileName, str_pattern, N)
    else:
        return _extract_episode_number_start(fileName, str_to_find, N)

def _find_last_episode(work_dir: str, parse_file_name: Dict) -> int:
    """
     "parse_file_name": {
         "str_from_start": "257.prichin.chtoby.zhit.s01e",
         "digits": 2
       }

     "parse_file_name": {
         "str_from_start": "",
         "digits": 0
       }

        extracts last episode from the actal files in the target folder
       files like 257.prichin.chtoby.zhit.s01e03.2020.WEB-DL.(1080p).Getty.mkv
    """
    last_episode: int = 0
    str_from_start = parse_file_name["str_from_start"]
    N: int = parse_file_name["digits"]
    for root, dirs, filenames in os.walk(work_dir):
        for fileName in filenames:
            # print(fileName)
            n = _extract_episode_number(fileName, str_from_start, N)
            if n > last_episode:
                last_episode = n
        break  # prevent descending into subfolders
    return last_episode


def decide_download_torrent_file(kin_ID: int, was_descr_updated: bool):
    torrent_fname = KINOZAL_F_BASE.format(ID=kin_ID)  # [kinozal.tv]id12345.torrent
    # ./torrents/[kinozal.tv]id12345.torrent
    torrent_pathname = os.path.join(WORK_DIR_BASE, torrent_fname)
    # if torrent file not exist, always download. If exist, only when description was updated
    return was_descr_updated if os.path.isfile(torrent_pathname) else True


def create_update_serial_description_file(kin_ID: int, web_descr: str) -> bool:
    descr_fname = f'{kin_ID}.txt'
    descr_pathname = os.path.join(WORK_DIR_BASE, descr_fname)
    if not os.path.isfile(descr_pathname):
        # create
        write_text_file(descr_pathname, web_descr)
        return True

    text_descr = read_text_file(descr_pathname)
    if text_descr != web_descr:  # new description
        # update
        write_text_file(descr_pathname, web_descr)
        return True

    return False


def owerwrite_file(response, path_name):
    with open(path_name, 'wb') as handle:
        for block in response.iter_content(1024):
            if not block:
                break
            handle.write(block)


class CKinozal:
    def __init__(self, serials_json_file: str, in_session = None):
        self.serials_map = read_JSON_from_file(serials_json_file)

        if in_session is None:
            self.m_session = self.__connect2kinozal()
        else:
            self.m_session = in_session

    serials_map: Dict = None
    m_session = None
    URL_BASE = f'https://{KINOZAL_BASE}'
    DL_URL_BASE = f'https://dl.{KINOZAL_BASE}'

    def __connect2kinozal(self):
        payload = get_login_payload()

        try:
            with sessions.Session() as session:
                session.post(f'{self.URL_BASE}/takelogin.php', data=payload)
                return session
        except requests.exceptions.ConnectionError as ex:
            print(f'connection error: {ex}')
            sys.exit()
            return None

    def download_torrent_file(self, kin_ID: int):
        """[summary]

        Args:
            kin_ID (int): [description]

        Returns:
            [type]: [description]
        """
        down_url = f'{self.DL_URL_BASE}/download.php?id={kin_ID}'
        response = self.m_session.get(down_url, stream=False)

        if not response.ok:
            # Something went wrong
            print(f'DOWNLOAD attempt failed, {response.status_code} {down_url}')
            sys.exit()

        torrent_sz = len(response.content)
        if torrent_sz == 0:
            print("unknown error  1")
            sys.exit()

        if 'text/html' in response.headers['content-type'] and response.text[0:15] == '<!DOCTYPE HTML>':
            print(RED + 'download prohibited, response is not a binary torrent :-(' + ENDC)
            return

        # "E:\\DEV\\python\\transfer_scripts\\torrents\\[kinozal.tv]id1761504.torrent"
        torrent_file_full_path_name = make_torrent_file_full_path_name(kin_ID)

        if os.path.isfile(torrent_file_full_path_name):
            statinfo = os.stat(torrent_file_full_path_name)
            cur_size = statinfo.st_size
            if cur_size != torrent_sz:  # new torrent
                if 'text/html' in response.headers['content-type'] and response.text[0:15] == '<!DOCTYPE HTML>':
                    print(RED + 'download prohibited' + ENDC)
                    return None
                owerwrite_file(response, torrent_file_full_path_name)
                # writes response content to torr_path_name (like "./torrents/[kinozal.tv]id1319399.torrent")
            else:
                # print 'no changes %s'%torr_path_name
                return
        else:
            print(f"Torrent ({torrent_file_full_path_name}) not exist, download for the 1st time.")
            owerwrite_file(response, torrent_file_full_path_name)

    def process_serials(self, transmission_client: CTorrent) -> int:
        current_country_name = get_country_name()

        cnt_new = 0
        for k_id, serial in self.serials_map.items():
            ignore = serial.get("IGNORE", False)
            if ignore:
                continue

            # by default - do download
            do_download = serial.get("DOWNLOAD_VPN_ONLY", True)
            if not do_download and current_country_name in ["Sweden"]:
                do_download = True
            

            target_path = serial["target_dir"]  # "NEW/СЕРИАЛЫ/РУС"
            target_dir_name = serial["name"]  # "Оптимисты"
            target_dir_print = f"{target_path}/{target_dir_name}"

            base_dir = TARGET_BASE_DIR  # "V:\\"
            if "TARGET_BASE_DIR" in serial:
                base_dir = serial["TARGET_BASE_DIR"]
                print(YELLOW + f"  --- override base_dir: {base_dir}" + ENDC)


            full_target_dir = os.path.join(base_dir, target_path, target_dir_name)

            print(f"\n{k_id} {target_dir_print}")
            if not os.path.isdir(base_dir):
                ip = requests.get("https://api.ipify.org/").content.decode('utf8')
                print(f"{RED}Недоступна базовая директория {base_dir}, возможно включен VPN {ip}{ENDC}")
                continue

            if not os.path.isdir(full_target_dir) and do_download:
                print(f"Новый сериал, попытка создать фолдер {target_dir_print}")
                os.mkdir(full_target_dir)

            parse_dict = serial["parse_file_name"]
            n_last_episode_from_files = _find_last_episode(full_target_dir, parse_dict)
            web_serial_descr = self.__get_serial_description(k_id)
            if web_serial_descr == "":
                print(RED + "Empty serial description! Skip." + ENDC)
                continue

            web_last_episode = _get_last_episode_from_web_descr(web_serial_descr)
            web_total_episodes = _get_total_episodes_from_web_descr(web_serial_descr)

            if web_last_episode != web_total_episodes:
                print(web_serial_descr)
            else:
                print(PURPLE + web_serial_descr + ENDC + " : сериал загружен полностью, можно удалить.")

            was_updated: bool = create_update_serial_description_file(k_id, web_serial_descr)
            is_new_torrent_needed = decide_download_torrent_file(k_id, was_updated)
            print(is_new_torrent_needed)

            if n_last_episode_from_files >= web_last_episode:
                print(f"Изменений нет, есть {n_last_episode_from_files} серий\n")
            else:
                if is_new_torrent_needed:
                    cnt_new += 1
                    print(f"{GREEN}Появилось {web_last_episode - n_last_episode_from_files} новых серий{ENDC}")
                    if not do_download:
                        print((f"{PURPLE}Download under VPN only!\n{ENDC}\n"))
                    else:
                        print()
                else:
                    err_str = f"Появилось {web_last_episode - n_last_episode_from_files} новых серий,\n\
но описание уже обновлено - похоже, торрент-файл был поврежден\
 (web: {web_last_episode}, files physical: {n_last_episode_from_files})"
                    print(YELLOW + err_str + ENDC)
                    if n_last_episode_from_files == 0:
                        print(RED + ' *** CHECK "parse_file_name" section in kinozal.json ***' + ENDC)

            if not do_download:
                continue

            if is_new_torrent_needed:
                self.download_torrent_file(k_id)
                ok = transmission_client.start_download(k_id, full_target_dir)
                if not ok:
                    # restore description text file (rollback)
                    pass
        return cnt_new

    def __get_serial_description(self, kin_id: int) -> str:
        """
            find text from the webpage like
            Дылды (1 сезон: 1-7 серии из 21) / 2019 / РУ / WEB-DL (1080p)
        """
        url = f'{self.URL_BASE}/details.php?id={kin_id}'
        response = self.m_session.get(url, stream=False)
        if not response.ok:
            # Something went wrong
            print(RED + f'__get_serial_description, error {response.status_code}' + ENDC)
            return ""

        html_doc = response.text
        soup = BeautifulSoup(html_doc, features="html.parser")
        # href='https://kinozal.tv/details.php?id=1273598'
        # href='//kinozal.tv/details.php?id=1273598'
        url2find = url.replace('https:', '')
        arr = soup.findAll('a', attrs={'href': url2find})
        if len(arr) == 1:
            text = arr[0].string
            return text.strip()
        return ""
