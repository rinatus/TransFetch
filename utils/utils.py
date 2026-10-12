import json
import io
import os
import tqdm
import ipinfo
import urllib.request

GRAY = '\033[1;30m'
RED = '\033[1;31m'
YELLOW = '\033[1,33m'
CYAN = '\033[1;36m'
PURPLE = '\033[1;35m'
GREEN = '\033[0;32m'

BGRN = '\033[1;32m'
HGRN = '\033[1;42m'

ENDC = "\033[0;m"


def copy_with_progress(src, dst):
    total_size = os.path.getsize(src)
    with open(src, 'rb') as fsrc, open(dst, 'wb') as fdst:
        # with tqdm(total=total_size, unit='B', unit_scale=True, desc=dst) as pbar:
        with tqdm.tqdm(total=total_size, unit='B', unit_scale=True) as pbar:
            for chunk in iter(lambda: fsrc.read(1024 * 1024), b''):
                fdst.write(chunk)
                pbar.update(len(chunk))

def move_file(src_path_name: str, dst_path: str) -> str:
    norm_src_path_name = os.path.normpath(src_path_name)
    norm_target_path = os.path.normpath(dst_path)

    # try:
    #     shutil.copy(norm_src_path_name, norm_target_path)
    # except OSError:
    #     pass
    
    file_name = os.path.basename(norm_src_path_name)
    norm_dst_path_name = os.path.normpath(os.path.join(dst_path, file_name))
    copy_with_progress(norm_src_path_name, norm_dst_path_name)

    if not os.path.isfile(norm_dst_path_name):
        print(f"{RED}incorrect target file: {norm_dst_path_name}{ENDC}")
        return None
    else:
        print(f"{GREEN}file {norm_dst_path_name} was copied OK.{ENDC}")
        os.remove(norm_src_path_name)
        return norm_dst_path_name

def read_JSON_from_file(path_name: str):
    ret = None
    with io.open(path_name, 'r', encoding='utf-8') as f:
        text = f.read()
        ret = json.loads(text)
    return ret


def write_JSON_to_file(data,  path_name: str):
    with open(path_name, 'wt', encoding='utf-8') as outfile:
        json.dump(data, outfile, sort_keys=False, indent=2, ensure_ascii=False)


def read_text_file(file_path_name: str) -> str:
    with io.open(file_path_name, 'r', encoding='utf-8') as f:
        file_text = f.read()
        return file_text.strip()


def write_text_file(file_path_name: str, text: str):
    with io.open(file_path_name, 'w', encoding='utf-8') as f:
        f.write(text.strip())


def get_country_name_from_ip(ip_address: str) -> str:
    access_token = os.getenv("IPINFO_TOKEN")
    if not access_token:
        raise ValueError("Set IPINFO_TOKEN in your environment or VS Code launch configuration's env settings.")
    handler = ipinfo.getHandler(access_token)

    details = handler.getDetails(ip_address)
    return details.country_name

def get_country_name() -> str:
    external_ip = None
    services = [
        "https://icanhazip.com",
        "https://ipify.org",
        "https://ident.me"
    ]

    for url in services:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                external_ip = response.read().decode("utf-8").strip()
                break  # Stop searching once we successfully get the IP
        except Exception:
            continue  # Try the next service if this one fails

    if external_ip:
        country_name = get_country_name_from_ip(str(external_ip))
        return country_name
    else:
        print("Could not retrieve external IP. Check your internet connection.")
        return None
