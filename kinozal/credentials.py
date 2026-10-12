"""Read Kinozal credentials when connecting, never at import time."""
import os


def get_login_payload(*, required=True):
    username = os.getenv("KINOZAL_USERNAME", "")
    password = os.getenv("KINOZAL_PASSWORD", "")
    if bool(username) != bool(password) or (required and not username):
        raise ValueError(
            "Set both KINOZAL_USERNAME and KINOZAL_PASSWORD in your environment "
            "or the selected VS Code launch configuration's env settings.")
    return {"action": "login", "username": username, "password": password}
