from config import TMP_DIR, KINOZAL_BASE
import sys
from kinozal.kinozal import CKinozal
from kinozal.credentials import get_login_payload
from bs4 import BeautifulSoup
from utils.utils import GREEN, RED, ENDC
from datetime import datetime
import requests
from pathlib import Path
from time import monotonic, sleep
from math import isfinite
from urllib.parse import urlsplit
from tempfile import TemporaryDirectory
from utils.torrent_decode import TDecoder
# import requests
# from requests import sessions


print(GREEN + f'Check login to kinozal' + ENDC)

class CheckKinozal:
    URL_BASE = f'https://{KINOZAL_BASE}'
    DL_URL_BASE = f'https://{KINOZAL_BASE}'
    m_session = None

    def __init__(self):
        self._playwright = None
        self._browser_context = None
        self._attached_browser = None
        self.browser_page = None
        self._owns_browser_page = False

    def connect2kinozal_alt(self, username=None, password=None, *,
                           headless=False, channel="chrome", timeout=180,
                           profile_dir=None, cdp_url=None, manual_login=False,
                           verification_wait=30):
        """Return a logged-in Playwright Page for browser-based scraping.

        Credentials use KINOZAL_USERNAME / KINOZAL_PASSWORD from the environment.
        Without credentials, reuse a saved login or log in manually. Pass two empty
        strings to disable automatic login. A separate browser
        profile retains cookies between runs. Cloudflare may still require a
        manual check; this method waits for login, it does not solve CAPTCHAs.

        By default, start normal installed Chrome and attach to it. Its window
        stays open after close_browser(); later calls reuse it and its cookies.
        timeout is in seconds. Use channel=None for Playwright's Chromium, or
        cdp_url to attach to a browser started with remote debugging enabled.
        The returned Page is not a requests.Session: use goto(), content(),
        locator(), and expect_download(). Call close_browser() when finished.
        With manual_login=True, wait verification_wait seconds (default 30)
        before attaching, without a terminal prompt. This pause is separate from
        the login timeout. Borrow the existing login tab and submit credentials there,
        or reuse an already logged-in tab. That tab is left open.
        """
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        if not isfinite(verification_wait) or verification_wait < 0:
            raise ValueError("verification_wait must be a finite, non-negative number of seconds")
        if manual_login and (headless or (not cdp_url and channel not in ("chrome", "msedge"))):
            raise ValueError("manual_login needs visible Chrome/Edge or a visible browser's cdp_url")
        if username is None and password is None:
            payload = get_login_payload(required=False)
            username, password = payload["username"], payload["password"]
        if bool(username) != bool(password):
            raise ValueError("Supply both username and password, or neither for manual login")
        try:
            from playwright.sync_api import sync_playwright, TimeoutError as BrowserTimeout, Error as BrowserError
        except ImportError as exc:
            raise RuntimeError(
                "Install browser support: python -m pip install -r requirements/browser.txt"
            ) from exc

        self.close_browser()
        logged_in = 'a[href*="logout.php"]'
        login_form = 'form:has(input[name="username"]):has(input[name="password"])'
        try:
            if not cdp_url and not headless and channel in ("chrome", "msedge"):
                from kinozal.browser import start_normal_browser
                normal_profile = profile_dir if profile_dir is not None else (
                    Path(__file__).resolve().parents[1] / f".kinozal-{channel}")
                cdp_url = start_normal_browser(
                    channel, normal_profile, timeout=min(timeout, 30),
                    start_url=f"{self.URL_BASE}/" if manual_login else "about:blank")
                print(f"Using normal {channel} window: {cdp_url}")
            if manual_login:
                print(f"Scraper is disconnected. In that Chrome/Edge window, open {self.URL_BASE}/")
                print("Complete Cloudflare verification. Leave the Kinozal login form or logged-in page open.")
                if username and password:
                    print("After the pause, the script will fill and submit your configured credentials if needed.")
                print(f"Continuing automatically in {verification_wait:g} seconds (Ctrl+C to cancel).", flush=True)
                sleep(verification_wait)
            self._playwright = sync_playwright().start()
            if cdp_url:
                self._attached_browser = self._playwright.chromium.connect_over_cdp(
                    cdp_url, timeout=timeout * 1000)
                context = self._attached_browser.contexts[0]
                if manual_login:
                    origin = urlsplit(self.URL_BASE)
                    site_pages = []
                    for candidate in reversed(context.pages):
                        candidate_url = urlsplit(candidate.url)
                        if (candidate_url.scheme, candidate_url.netloc) != (origin.scheme, origin.netloc):
                            continue
                        site_pages.append(candidate)
                        if candidate.locator(logged_in).first.is_visible():
                            self.browser_page = candidate
                            print(f"OK: attached to logged-in tab at {candidate.url}")
                            return candidate
                    page = next((candidate for candidate in site_pages
                                 if candidate.locator(login_form).first.is_visible()), None)
                    if page is None:
                        raise RuntimeError(
                            "No Kinozal login form or logged-in tab was found. Finish Cloudflare "
                            "verification in this browser and retry, or increase --verification-wait. "
                            "The scraper will disconnect and leave your tabs open.")
                    if not username or not password:
                        raise ValueError(
                            "The login form is ready, but no credentials were supplied. Set both "
                            "KINOZAL_USERNAME and KINOZAL_PASSWORD, or log in manually during the pause.")
                else:
                    # Own only this tab; leave the user's other tabs/browser open.
                    page = context.new_page()
            else:
                profile_dir = Path(profile_dir) if profile_dir is not None else (
                    Path(__file__).resolve().parents[1] / ".kinozal-browser")
                self._browser_context = self._playwright.chromium.launch_persistent_context(
                    str(profile_dir.resolve()), channel=channel, headless=headless,
                    accept_downloads=True, timeout=timeout * 1000)
                context = self._browser_context
                page = context.pages[0] if context.pages else context.new_page()
            self.browser_page = page
            self._owns_browser_page = not manual_login
            deadline = monotonic() + timeout

            def remaining_ms():
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise BrowserTimeout("Login deadline expired")
                return remaining * 1000

            # A challenge response can be HTTP 403 and later navigate to the
            # real page. Wait for site elements, not the initial HTTP status.
            if not headless or cdp_url:
                print("Waiting for browser login. Complete any Cloudflare check or login in the window.")
            # The dedicated login page may show its form even when cookies
            # already authenticate us. Check the home page before logging in.
            if not manual_login:
                page.goto(f"{self.URL_BASE}/", wait_until="domcontentloaded",
                          timeout=remaining_ms())
                page.locator(
                    f'{logged_in}, {login_form}, a[href*="login.php"]'
                ).first.wait_for(state="visible", timeout=remaining_ms())
                if (not page.locator(logged_in).first.is_visible()
                        and not page.locator(login_form).first.is_visible()):
                    page.goto(f"{self.URL_BASE}/login.php", wait_until="domcontentloaded",
                              timeout=remaining_ms())
            if username and password:
                page.locator(f'{logged_in}, {login_form}').first.wait_for(
                    state="visible", timeout=remaining_ms())
                if not page.locator(logged_in).first.is_visible():
                    print("Submitting Kinozal login form...")
                    form = page.locator(login_form).first
                    form.locator('input[name="username"]').fill(username, timeout=remaining_ms())
                    form.locator('input[name="password"]').fill(password, timeout=remaining_ms())
                    form.locator(
                        'input[type="submit"], button[type="submit"], button:not([type])'
                    ).first.click(timeout=remaining_ms())
            page.locator(logged_in).first.wait_for(state="visible", timeout=remaining_ms())
            print(f"OK: browser logged in to {self.URL_BASE}")
            return page
        except BrowserTimeout as exc:
            last_title = ""
            if self.browser_page is not None:
                try:
                    last_title = self.browser_page.title()
                except BrowserError:
                    pass
            attached = self._attached_browser is not None
            self.close_browser(keep_tab=attached)
            raise TimeoutError(
                f"Browser login was not confirmed before timeout. Last page: {last_title!r}. "
                + ("The tab is still open: complete verification/login there, then rerun the script."
                   if attached else "Try headless=False to complete verification/login manually.")
            ) from exc
        except BaseException:
            self.close_browser()
            raise

    def download_torrent_file_alt(self, kin_ID: int, *, download_dir=None, timeout=180) -> int:
        """Save a torrent using the connected browser and return its size in bytes.

        timeout limits the wait for the download to start. Saving waits for the
        transfer to finish. Existing files are replaced only after validation.
        """
        if not isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be a finite, positive number of seconds")
        if not isinstance(kin_ID, int) or kin_ID <= 0:
            raise ValueError("kin_ID must be a positive integer")
        page = self.browser_page
        if page is None or page.is_closed():
            raise RuntimeError("Connect with connect2kinozal_alt() before downloading")
        from playwright.sync_api import TimeoutError as BrowserTimeout

        down_url = f"{self.DL_URL_BASE}/download.php?id={kin_ID}"
        directory = (Path(download_dir) if download_dir is not None else
                     Path(__file__).resolve().parents[1] / "torrents")
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory.resolve() / f"[kinozal]id{kin_ID}.torrent"
        try:
            with page.expect_download(timeout=timeout * 1000) as pending:
                # An ordinary browser link preserves cookies and the referring
                # details page. Do not force HTML responses into a download.
                page.evaluate("""url => {
                    const link = document.createElement('a');
                    link.href = url;
                    document.body.appendChild(link);
                    link.click();
                    link.remove();
                }""", down_url)
            download = pending.value
        except BrowserTimeout as exc:
            raise TimeoutError(
                "Torrent download did not start. The download page may require "
                "verification/login, or the torrent may be unavailable. "
                "Check the browser and retry."
            ) from exc

        # save_as also works over CDP; download.path() does not work remotely.
        with TemporaryDirectory(prefix=".download-", dir=directory) as temporary:
            candidate = Path(temporary) / "download.torrent"
            download.save_as(str(candidate))
            size = candidate.stat().st_size
            if not size:
                raise RuntimeError("Torrent download is empty")
            try:
                metadata = TDecoder(candidate.read_bytes()).decode()
                if not isinstance(metadata, dict) or not isinstance(metadata.get(b"info"), dict):
                    raise ValueError("Missing torrent info dictionary")
            except (ValueError, TypeError, RuntimeError, EOFError, IndexError) as exc:
                raise RuntimeError(
                    "Downloaded response is not torrent metadata; it may be a login or error page"
                ) from exc
            candidate.replace(destination)
        print(f"OK: browser torrent download, size: {size} bytes, saved: {destination}")
        return size

    def close_browser(self, *, keep_tab=False):
        """Close the owned browser, or our attached tab unless kept for manual login."""
        try:
            if self._browser_context is not None:
                self._browser_context.close()
            elif (self._owns_browser_page and not keep_tab and self.browser_page is not None
                  and not self.browser_page.is_closed()):
                self.browser_page.close()
        finally:
            try:
                if self._playwright is not None:
                    self._playwright.stop()
            finally:
                self._playwright = None
                self._browser_context = None
                self._attached_browser = None
                self.browser_page = None
                self._owns_browser_page = False

    @staticmethod
    def _login_payload():
        return get_login_payload()

    def connect2kinozal(self):
        payload = self._login_payload()

        try:
            a_session = requests.Session()
            with a_session as session:
                url = f"{self.URL_BASE}/takelogin.php"
                resp = session.post(url, data=payload, timeout=100)
                if resp.ok:
                    print(f"OK connecting to {self.URL_BASE}: {resp.ok}, status_code: {resp.status_code}")
                    self.m_session = session
                else:
                    print(f"{RED}FAIL [connect2kinozal], status_code: {resp.status_code}{ENDC}")
                self.m_session = a_session
        except requests.exceptions.ConnectionError as ex:
            print(f'connection error: {ex}')


    def get_profile(self, user_id: int) -> bool:
        """
            get user profile - must be logged in
        """
        # https://kinozal.tv/userdetails.php?id=2120987
        url = f'{self.URL_BASE}/userdetails.php?id={user_id}'
        response = self.m_session.get(url, stream=False)
        if not response.ok:
            # Something went wrong
            print(RED + f'get_profile, error {response.status_code}' + ENDC)
            return False

        html_doc = response.text
        str2find_bad = "Чтобы просматривать эту страницу, нужно зайти на сайт"
        if str2find_bad in html_doc:
            return False
        
        str2find_ok = "12 марта 2009"
        if str2find_ok in html_doc:
            return True

        return False

    def get_serial_name_description(self, kin_id: int) -> str:
        """
            find text from the webpage like
            Дылды (1 сезон: 1-7 серии из 21) / 2019 / РУ / WEB-DL (1080p)
        """
        url = f'{self.URL_BASE}/details.php?id={kin_id}'
        if not self.m_session:
            return None

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


    def download_torrent_file(self, kin_ID: int) -> int:
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
        print(torrent_sz)
        if torrent_sz == 0:
            print(f"{RED}unknown error -2{ENDC}")
            return -2

        if 'text/html' in response.headers['content-type'] and response.text[0:15] == '<!DOCTYPE HTML>':
            print(RED + 'download prohibited, response is not a binary torrent :-(' + ENDC)
            return -1
        return torrent_sz



def make_kinozal_check(check_download: bool, kino_id: int):

    kz_check = CheckKinozal()
    print("Connecting to Kinozal...")
    kz_check.connect2kinozal()

    # kino_id = 1836772
    descr_txt = kz_check.get_serial_name_description(kino_id)
    if not descr_txt:
        return None

    print(descr_txt)
    if not "Тюремный дневник" in descr_txt:
        print(f"{RED}Error: get_serial_description mismatch.{ENDC}: {descr_txt}")

    user_id = 2120987
    if logged_ok := kz_check.get_profile(2120987):
        print(GREEN + f'OK: you are logged in. Torrent site: {KINOZAL_BASE}' + ENDC)
    else:
        print(RED + f'Error: you are not logged in.' + ENDC)
        sys.exit(0)

    if not check_download:
        return kz_check.m_session

    torrent_sz_OK = 31892
    sz = kz_check.download_torrent_file(kino_id)
    if sz == torrent_sz_OK:
        print(GREEN + f'OK: download_torrent_file, size: {sz}' + ENDC)
    else:
        print(RED + f'FAIL: download_torrent_file, size: {sz}' + ENDC)
    return kz_check.m_session

# make_kinozal_check(True)
