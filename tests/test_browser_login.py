"""Local browser integration tests; requires Playwright and installed Chrome."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs

from kinozal.login_check import CheckKinozal
from kinozal.browser import start_normal_browser

TORRENT_BYTES = (b'd4:infod6:lengthi1e4:name4:test12:piece lengthi16384e'
                 b'6:pieces20:12345678901234567890ee')


class BrowserLauncherTests(unittest.TestCase):
    def test_explicit_nonzero_port_and_reuse(self):
        with TemporaryDirectory() as profile, \
                patch("kinozal.browser._browser_executable", return_value="chrome"), \
                patch("kinozal.browser.subprocess.Popen") as launch, \
                patch("kinozal.browser.build_opener") as opener:
            opener.return_value.open.side_effect = lambda *a, **kw: BytesIO(
                b'{"webSocketDebuggerUrl":"ws://127.0.0.1/devtools/browser/test"}')
            endpoint = start_normal_browser("chrome", profile)
            command = launch.call_args.args[0]
            port_flag = next(arg for arg in command if arg.startswith("--remote-debugging-port="))
            port = int(port_flag.split("=")[1])
            self.assertGreater(port, 0)
            self.assertEqual(endpoint, f"http://127.0.0.1:{port}")
            self.assertEqual(start_normal_browser("chrome", profile), endpoint)
            launch.assert_called_once()

    def test_old_port_zero_browser_requires_restart(self):
        with TemporaryDirectory() as profile, \
                patch("kinozal.browser.subprocess.Popen") as launch, \
                patch("kinozal.browser.build_opener") as opener:
            (Path(profile) / "DevToolsActivePort").write_text("9222\n/devtools/browser/old\n")
            opener.return_value.open.side_effect = lambda *a, **kw: BytesIO(
                b'{"webSocketDebuggerUrl":"ws://127.0.0.1:9222/devtools/browser/old"}')
            with self.assertRaisesRegex(RuntimeError, "older browser"):
                start_normal_browser("chrome", profile)
            launch.assert_not_called()


class LoginHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        logged_in = "test_login=yes" in self.headers.get("Cookie", "")
        if logged_in and self.path.startswith("/download.php?"):
            torrent_id = parse_qs(self.path.split("?", 1)[1])["id"][0]
            body = {"2": b"<html>Login required</html>", "3": b"",
                    "4": b"d4:info"}.get(torrent_id, TORRENT_BYTES)
            self.send_response(200)
            self.send_header("Content-Type", "application/x-bittorrent")
            self.send_header("Content-Disposition", 'attachment; filename="server-name.torrent"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        # Like the live site, the login page can still show a form even with
        # valid cookies. Saved sessions must be checked on the home page.
        if logged_in and self.path != "/login.php":
            body = '<title>Logged in</title><a href="/logout.php">Log out</a>'
            status = 200
        elif not logged_in and self.path in ("/", "/login.php"):
            # Model a challenge which initially returns 403, then navigates
            # after JavaScript has run. No network outside localhost is used.
            body = '<script>setTimeout(() => location.href="/form", 200)</script>'
            status = 403
        else:
            body = '''<form method="post" action="/takelogin.php">
                <input name="username"><input name="password" type="password">
                <input type="submit" value="Login"></form>'''
            status = 200
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode())

    def do_POST(self):
        fields = parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
        self.send_response(303)
        if fields == {"username": ["test-user"], "password": ["test-password"]}:
            self.send_header("Set-Cookie", "test_login=yes; Path=/; Max-Age=3600")
        self.send_header("Location", "/form")
        self.end_headers()


class BrowserLoginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), LoginHandler)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.env = patch.dict("os.environ", {"KINOZAL_USERNAME": "", "KINOZAL_PASSWORD": ""})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.profile = TemporaryDirectory()
        self.addCleanup(self.profile.cleanup)
        self.check = CheckKinozal()
        self.check.URL_BASE = f"http://127.0.0.1:{self.server.server_port}"
        self.check.DL_URL_BASE = self.check.URL_BASE
        self.addCleanup(self.check.close_browser)

    def connect(self, **kwargs):
        return self.check.connect2kinozal_alt(
            headless=True, profile_dir=self.profile.name, **kwargs)

    def test_javascript_challenge_login_scraping_and_saved_session(self):
        page = self.connect(username="test-user", password="test-password", timeout=10)
        self.assertFalse(page.is_closed())
        page.goto(f"{self.check.URL_BASE}/details.php?id=1")
        self.assertIn("Logged in", page.content())
        self.check.close_browser()
        self.assertTrue(page.is_closed())
        # No credentials: reuse the persisted browser cookies.
        reused_page = self.connect(timeout=10)
        self.assertEqual(reused_page.title(), "Logged in")
        self.check.close_browser()
        self.check.close_browser()  # Cleanup is safe more than once.

    def test_failed_login_is_not_reported_as_success_and_cleans_up(self):
        with self.assertRaisesRegex(TimeoutError, "not confirmed"):
            self.connect(username="test-user", password="wrong", timeout=2)
        self.assertIsNone(self.check.browser_page)
        self.assertIsNone(self.check._playwright)
        # The profile lock must have been released after the failure.
        page = self.connect(username="test-user", password="test-password", timeout=10)
        self.assertEqual(page.title(), "Logged in")

    def test_download_uses_login_cookies_and_file_survives_browser_close(self):
        page = self.connect(username="test-user", password="test-password", timeout=10)
        page.goto(f"{self.check.URL_BASE}/details.php?id=1")
        with TemporaryDirectory() as directory:
            size = self.check.download_torrent_file_alt(1, download_dir=directory, timeout=5)
            self.check.close_browser()
            saved = Path(directory) / "[kinozal]id1.torrent"
            self.assertEqual(size, len(TORRENT_BYTES))
            self.assertEqual(saved.read_bytes(), TORRENT_BYTES)
            self.assertEqual(list(Path(directory).iterdir()), [saved])

    def test_invalid_download_preserves_existing_file(self):
        self.connect(username="test-user", password="test-password", timeout=10)
        with TemporaryDirectory() as directory:
            for torrent_id in (2, 3, 4):
                with self.subTest(torrent_id=torrent_id):
                    saved = Path(directory) / f"[kinozal]id{torrent_id}.torrent"
                    saved.write_bytes(TORRENT_BYTES)
                    with self.assertRaisesRegex(RuntimeError, "empty|not torrent metadata"):
                        self.check.download_torrent_file_alt(
                            torrent_id, download_dir=directory, timeout=5)
                    self.assertEqual(saved.read_bytes(), TORRENT_BYTES)
            self.assertFalse(list(Path(directory).glob(".download-*")))

    def test_download_html_navigation_reports_timeout(self):
        page = self.connect(username="test-user", password="test-password", timeout=10)
        page.context.clear_cookies()
        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(TimeoutError, "download did not start"):
                self.check.download_torrent_file_alt(1, download_dir=directory, timeout=1)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_invalid_options_fail_before_browser_start(self):
        with self.assertRaises(ValueError):
            self.connect(timeout=0)
        with self.assertRaises(ValueError):
            self.connect(username="test-user")
        for delay in (-1, float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                self.connect(verification_wait=delay)
        self.assertIsNone(self.check._playwright)

    def test_manual_login_waits_before_attach_and_preserves_existing_tab(self):
        page = MagicMock()
        page.url = f"{self.check.URL_BASE}/details.php?id=1"
        page.locator.return_value.first.is_visible.return_value = True
        with patch("kinozal.browser.start_normal_browser", return_value="http://127.0.0.1:9222"), \
                patch("playwright.sync_api.sync_playwright") as factory, \
                patch("kinozal.login_check.sleep") as pause:
            driver = factory.return_value.start.return_value
            context = driver.chromium.connect_over_cdp.return_value.contexts[0]
            context.pages = [page]

            def finish_pause(seconds):
                self.assertEqual(seconds, 30)
                factory.assert_not_called()
                return ""

            pause.side_effect = finish_pause
            result = self.check.connect2kinozal_alt(
                manual_login=True, profile_dir=self.profile.name)
            self.assertIs(result, page)
            pause.assert_called_once_with(30)
            page.goto.assert_not_called()
            context.new_page.assert_not_called()
            self.check.close_browser()
            page.close.assert_not_called()
            context.close.assert_not_called()
            driver.stop.assert_called_once()

    def test_manual_login_rejects_unverified_tab_without_navigating_or_closing_it(self):
        page = MagicMock()
        page.url = f"{self.check.URL_BASE}/login.php"
        page.locator.return_value.first.is_visible.return_value = False
        with patch("kinozal.login_check.sleep"), \
                patch("playwright.sync_api.sync_playwright") as factory:
            driver = factory.return_value.start.return_value
            context = driver.chromium.connect_over_cdp.return_value.contexts[0]
            context.pages = [page]
            with self.assertRaisesRegex(RuntimeError, "No Kinozal login form"):
                self.check.connect2kinozal_alt(manual_login=True, cdp_url="http://127.0.0.1:9222")
            page.goto.assert_not_called()
            page.close.assert_not_called()
            context.new_page.assert_not_called()
            driver.stop.assert_called_once()

    def test_manual_verification_submits_environment_credentials_in_borrowed_login_tab(self):
        page = MagicMock()
        page.url = f"{self.check.URL_BASE}/login.php?m=5"
        form = MagicMock()
        form.is_visible.return_value = True
        logout = MagicMock()
        logout.is_visible.return_value = False
        page.locator.side_effect = lambda selector: MagicMock(
            first=logout if selector == 'a[href*="logout.php"]' else form)
        unrelated = MagicMock()
        unrelated.url = "https://unrelated.example/login.php"
        with patch.dict("os.environ", {
                "KINOZAL_USERNAME": "test-user", "KINOZAL_PASSWORD": "test-password"}), \
                patch("kinozal.login_check.sleep"), \
                patch("playwright.sync_api.sync_playwright") as factory:
            driver = factory.return_value.start.return_value
            context = driver.chromium.connect_over_cdp.return_value.contexts[0]
            context.pages = [page, unrelated]
            result = self.check.connect2kinozal_alt(
                manual_login=True, cdp_url="http://127.0.0.1:9222")
            self.assertIs(result, page)
            self.assertEqual([call.args[0] for call in form.locator.return_value.fill.call_args_list],
                             ["test-user", "test-password"])
            form.locator.return_value.first.click.assert_called_once()
            logout.wait_for.assert_called_once()
            unrelated.locator.assert_not_called()
            page.goto.assert_not_called()
            context.new_page.assert_not_called()
            self.check.close_browser()
            page.close.assert_not_called()

    def test_manual_verification_needs_credentials_for_a_login_form(self):
        page = MagicMock()
        page.url = f"{self.check.URL_BASE}/login.php"
        page.locator.side_effect = lambda selector: MagicMock(
            first=MagicMock(is_visible=MagicMock(return_value=selector != 'a[href*="logout.php"]')))
        with patch("kinozal.login_check.sleep"), \
                patch("playwright.sync_api.sync_playwright") as factory:
            driver = factory.return_value.start.return_value
            context = driver.chromium.connect_over_cdp.return_value.contexts[0]
            context.pages = [page]
            with self.assertRaisesRegex(ValueError, "no credentials"):
                self.check.connect2kinozal_alt(
                    username="", password="", manual_login=True, cdp_url="http://127.0.0.1:9222")
            page.goto.assert_not_called()
            page.close.assert_not_called()
            driver.stop.assert_called_once()


if __name__ == "__main__":
    unittest.main()
