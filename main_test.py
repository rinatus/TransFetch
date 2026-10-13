
import argparse
import sys

from bs4 import BeautifulSoup
from kinozal.login_check import CheckKinozal, make_kinozal_check
from utils.utils import RED,ENDC
from config import KINOZAL_BASE

def main():
    parser = argparse.ArgumentParser(description="Test Kinozal login and scraping")
    parser.add_argument("--browser", action="store_true", help="Launch normal Chrome and attach for scraping")
    parser.add_argument("--headless", action="store_true", help="Hide the browser window")
    parser.add_argument("--manual-login", action="store_true",
                        help="Pause for Cloudflare verification, then submit credentials automatically (implies --browser)")
    parser.add_argument("--verification-wait", type=float, default=30,
                        help="Seconds to wait before attaching in --manual-login mode (default: 30)")
    parser.add_argument("--channel", default="chrome", choices=["chrome", "msedge", "chromium"])
    parser.add_argument("--timeout", type=float, default=180, help="Login timeout in seconds")
    parser.add_argument("--cdp-url", help="Attach to a browser, e.g. http://127.0.0.1:9222")
    parser.add_argument("--id", type=int, default=2090510, help="Details page to scrape")
    parser.add_argument("--download-dir", help="Browser torrent download folder (default: project torrents folder)")
    args = parser.parse_args()

    if args.browser or args.manual_login:
        check = CheckKinozal()
        try:
            page = check.connect2kinozal_alt(
                headless=args.headless, timeout=args.timeout,
                channel=None if args.channel == "chromium" else args.channel,
                cdp_url=args.cdp_url, manual_login=args.manual_login,
                verification_wait=args.verification_wait)
            details_url = f"{check.URL_BASE}/details.php?id={args.id}"
            if page.url != details_url:
                page.goto(details_url, wait_until="domcontentloaded", timeout=args.timeout * 1000)
            page.locator('a[href*="logout.php"]').first.wait_for(
                state="visible", timeout=args.timeout * 1000)
            soup = BeautifulSoup(page.content(), "html.parser")
            print(f"Browser scraping OK: {soup.title.get_text(strip=True) if soup.title else page.url}")
            check.download_torrent_file_alt(
                args.id, download_dir=args.download_dir, timeout=args.timeout)
            return 0
        except Exception as exc:
            print(f"{RED}Browser test failed: {exc}{ENDC}")
            return 1
        finally:
            check.close_browser()

    session = make_kinozal_check(True, args.id)
    if not session:
        print(f"{RED}make_kinozal_check ({args.id}): Connection failed, STOP.{ENDC}")
        print(f"{RED}Torrent site {KINOZAL_BASE} NOT working.{ENDC}")
        return 1
    session.close()
    return 0


if __name__ == "__main__":
    # Redirected Windows output may use a code page without Cyrillic characters.
    sys.stdout.reconfigure(errors="backslashreplace")
    raise SystemExit(main())
