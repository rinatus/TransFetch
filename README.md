# Windows (PowerShell)

Run from the project directory. The environment was verified with Python 3.13.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements\base.txt
```

Select `.venv\Scripts\python.exe` as the Python interpreter in VS Code.
If PowerShell blocks activation, use the environment directly without changing
the execution policy:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements\base.txt
.\.venv\Scripts\python.exe main.py
```

Use `deactivate` to leave an activated environment.

## Credentials and VS Code debugging

Credentials are read from environment variables when needed; Python source files
have no built-in account passwords or API tokens.

| Variable | Used by |
| --- | --- |
| `KINOZAL_USERNAME`, `KINOZAL_PASSWORD` | Both requests login paths and browser login |
| `IPINFO_TOKEN` | IPinfo country lookup |
| `TRANSMISSION_HOST`, `TRANSMISSION_USERNAME`, `TRANSMISSION_PASSWORD` | Remote connection in `test_transmission.py` |

The local `.vscode/launch.json` has these values under `env` for both debug
configurations. Select **Python: Kinozal browser login** in Run and Debug, then
press **F5** to run `main_test.py --manual-login`. **Python: Current File** also
receives the variables. Complete Cloudflare verification during the 30-second
pause; the script then submits your credentials automatically. No Enter is needed.

`.vscode/launch.json` contains local secrets and is excluded from Git. The
placeholder-only `.vscode/launch.example.json` can be committed. On a new checkout,
copy the example to `launch.json` and fill in your own values.

Launch configuration `env` values apply to the debugged process, not to commands
typed into an ordinary terminal. For a terminal run, set the environment there:

```powershell
$env:KINOZAL_USERNAME = Read-Host 'Kinozal username'
$kinozalPassword = Read-Host 'Kinozal password' -AsSecureString
$env:KINOZAL_PASSWORD = [System.Net.NetworkCredential]::new('', $kinozalPassword).Password
.\.venv\Scripts\python.exe main_test.py --manual-login
```

Set `IPINFO_TOKEN` separately when running code that performs the country lookup.
Missing credentials produce a message naming the required variables; the browser
path can still reuse saved cookies or accept a fully manual login without them.
Setting just one of the two Kinozal variables is an error. No `.env` loader or
machine-wide environment change is made by this project.
See [VS Code's environment settings](https://code.visualstudio.com/docs/python/debugging#_env).

## Browser login test (Cloudflare)

The launcher now selects an explicit nonzero debugging port. Earlier versions
passed `--remote-debugging-port=0`, which Chrome treats as automation
(`navigator.webdriver` becomes true), even before Playwright attaches. Close any
Chrome/Edge windows started by the older script before testing this correction.
The launcher refuses to reuse a still-running browser from the old port=0 mode.
See the [browser API documentation](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/webdriver).

If the checkbox repeats, use manual verification mode:

```powershell
.\.venv\Scripts\python.exe main_test.py --manual-login
```

Stop any other running scraper first. In the Chrome window opened/reused by this
command, open `https://kinozal.guru/` and complete Cloudflare verification. The
script waits **30 seconds without attaching Playwright**, then continues
automatically. It borrows the existing login tab without
reloading it, fills and submits the configured credentials, waits for confirmed
login, scrapes the requested details page, and downloads its `.torrent` file. If you already logged in, it skips
form submission and reuses that session. You may open that
details page manually during the pause to avoid another navigation. This
mode keeps your tab open when the script finishes, including on errors.

For more time, use `--manual-login --verification-wait 60`. This delay is separate
from `--timeout`, which controls the subsequent login wait. If verification is
still unfinished after the pause, the script disconnects and leaves your tabs
open so you can finish the check and retry.

This is a diagnostic fallback, not guaranteed clearance. If verification loops
during the pause, this script's Playwright connection is not active. If it
loops only after the pause or after navigating to details, browser scraping is still
being challenged. Cloudflare lists browser automation as unsupported for solving
[production challenges](https://developers.cloudflare.com/cloudflare-challenges/reference/supported-browsers/).
For loops even with the script stopped, follow Cloudflare's
[browser/network troubleshooting](https://developers.cloudflare.com/cloudflare-challenges/troubleshooting/challenge-solve-issues/).

Install the optional browser dependency and use installed Chrome:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements\browser.txt
.\.venv\Scripts\python.exe main_test.py --browser
```

This launches normal installed Chrome and automatically attaches to its local
debugging port. It does not use Playwright's automated browser launch flags.
Complete login and any Cloudflare check in the window. The test waits up to
180 seconds, checks for the site's logout link, then scrapes a details page.
Use `--timeout 300` for more time, `--channel msedge` for Edge, or `--id 2090510`
to select the details page. The scraping tab closes after the test; Chrome stays
open and is reused on the next run. Cookies are retained in `.kinozal-chrome/`
(`.kinozal-msedge/` for Edge); these contain login data and are excluded from Git.
These profiles are separate from the earlier automated `.kinozal-browser/`
profile, so sign in again on the first run. Use one script at a time per profile.
If login times out, the normal browser's verification tab stays open. Complete
verification and login there, then rerun the same command. A fresh normal-browser
profile can still require a manual check; launching normally is not a guarantee
that Cloudflare will accept the session.

Both browser modes read **both** `KINOZAL_USERNAME` and `KINOZAL_PASSWORD`
from the environment, or accept explicit `username` and `password` arguments. Pass
two empty strings (or set both environment variables empty) to disable automatic
submission; in that case, finish login yourself during the pause.
Try `--browser --headless` for unattended use with credentials or a saved login.
If Cloudflare does not finish in headless mode, run without `--headless`.
Browser automation can still be challenged; it does not guarantee access.

`CheckKinozal.connect2kinozal_alt()` returns a live Playwright `Page` for scraping:

```python
from bs4 import BeautifulSoup
from kinozal.login_check import CheckKinozal

check = CheckKinozal()
try:
    page = check.connect2kinozal_alt()
    page.goto(f"{check.URL_BASE}/details.php?id=2090510")
    page.locator('a[href*="logout.php"]').first.wait_for(timeout=180_000)
    soup = BeautifulSoup(page.content(), "html.parser")
    print(soup.title.get_text())
finally:
    check.close_browser()
```

This test path uses browser navigation throughout. The original `connect2kinozal`
and `main.py` still use requests. The returned Page cannot be passed to the old
methods that expect `m_session.get(...)`. Use Playwright's `expect_download()`
and `download.save_as(...)` via `check.download_torrent_file_alt(2090510)` to save
a torrent using the same browser session before closing the browser.

Both `--browser` and `--manual-login` automatically download the selected `--id`
after printing the page title. The file is saved as `torrents/[kinozal]id<ID>.torrent`
and its size in **bytes** is printed. This is the torrent metadata file, not the
media it describes. Use `--download-dir D:\Downloads` to choose another folder.
Empty or invalid torrent responses fail the test without replacing an existing
file. `torrents/` is excluded from Git. `--timeout` also controls how long to wait
for the download to start; saving then waits for the transfer to finish.

To manage the browser launch yourself, start normal Chrome with a separate
debugging profile, log in there, and attach:

```powershell
& 'C:\Program Files\Google\Chrome\Application\chrome.exe' --remote-debugging-port=9222 --user-data-dir="$PWD\.kinozal-chrome" https://kinozal.guru/
.\.venv\Scripts\python.exe main_test.py --browser --cdp-url http://127.0.0.1:9222
```

Close any previous browser using this profile first. `close_browser()` closes
only the new scraping tab when attached this way, leaving your browser open.
In live testing, attaching to normal Chrome successfully logged in and loaded
a protected details page; both headless and automatically launched visible
Chrome timed out before login. The basic `--browser` test now uses this normal
Chrome attachment approach automatically, discovering the port on each run.
Alternatively, install bundled Chromium with `python -m playwright install chromium`
and test with `--browser --channel chromium`.

# Linux

python3.12 -m venv ve
source ve/bin/activate

# gio mount "afp://rinatb@NAS4.local/TORRENT"
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
