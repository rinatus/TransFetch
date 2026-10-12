"""Start installed Chrome/Edge normally, then expose its local CDP endpoint."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from time import monotonic, sleep
from urllib.request import ProxyHandler, build_opener
from urllib.parse import urlsplit


def _browser_executable(channel):
    if sys.platform == "win32":
        relative = ("Google/Chrome/Application/chrome.exe" if channel == "chrome"
                    else "Microsoft/Edge/Application/msedge.exe")
        candidates = [Path(root) / relative for name in
                      ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")
                      if (root := os.getenv(name))]
    elif sys.platform == "darwin":
        app = "Google Chrome" if channel == "chrome" else "Microsoft Edge"
        candidates = [Path(f"/Applications/{app}.app/Contents/MacOS/{app}")]
    else:
        names = (("google-chrome", "google-chrome-stable") if channel == "chrome"
                 else ("microsoft-edge", "microsoft-edge-stable"))
        candidates = [Path(found) for name in names if (found := shutil.which(name))]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    raise RuntimeError(f"Installed {channel} was not found. Install it or use cdp_url.")


def start_normal_browser(channel, profile_dir, timeout=30, start_url="about:blank"):
    """Launch or reuse a dedicated browser; deliberately leave it open on exit.

    Select an explicit nonzero port: Chrome's special port=0 mode sets
    navigator.webdriver=True even before an automation client attaches.
    Save and verify the browser ID so stale metadata cannot select another server.
    HTTP here is used only for the localhost debugging endpoint, never scraping.
    """
    profile_dir = Path(profile_dir).resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)
    endpoint_file = profile_dir / "transfetch-cdp.json"
    opener = build_opener(ProxyHandler({}))

    def browser_id(port):
        if not 0 < int(port) < 65536:
            raise ValueError("Invalid debugging port")
        endpoint = f"http://127.0.0.1:{int(port)}"
        with opener.open(endpoint + "/json/version", timeout=0.5) as response:
            version = json.load(response)
        path = urlsplit(version.get("webSocketDebuggerUrl", "")).path
        if not path.startswith("/devtools/browser/"):
            raise ValueError("Not a browser debugging endpoint")
        return endpoint, path

    def active_endpoint():
        try:
            saved = json.loads(endpoint_file.read_text(encoding="utf-8"))
            endpoint, identity = browser_id(saved["port"])
            if identity == saved["browser_path"]:
                return endpoint
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return None

    endpoint = active_endpoint()
    if endpoint:
        return endpoint

    # Do not silently reuse a running browser from the old port=0 launcher.
    try:
        old_port, old_identity = (profile_dir / "DevToolsActivePort").read_text(
            encoding="utf-8").splitlines()[:2]
        _, identity = browser_id(old_port)
    except (OSError, ValueError):
        pass
    else:
        if identity == old_identity:
            raise RuntimeError(
                "An older browser launched with port=0 is still using this profile. "
                "Close its Chrome/Edge windows, then rerun so the corrected launcher can start.")

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

    # Do not use Playwright's launch flags (including --no-sandbox and
    # --enable-automation). Keep this an ordinary installed browser window.
    process = subprocess.Popen(
        [_browser_executable(channel), f"--remote-debugging-port={port}",
         f"--user-data-dir={profile_dir}", start_url],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        try:
            endpoint, identity = browser_id(port)
        except (OSError, ValueError):
            pass
        else:
            endpoint_file.write_text(json.dumps({"port": port, "browser_path": identity}),
                                     encoding="utf-8")
            return endpoint
        if process.poll() is not None:
            break
        sleep(0.1)
    raise RuntimeError(
        f"Could not start {channel} with debugging enabled. Close browser windows "
        f"using profile {profile_dir} and retry, or supply cdp_url.")
