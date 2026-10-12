import os
import unittest
from unittest.mock import patch

from kinozal.credentials import get_login_payload
from kinozal.kinozal import CKinozal
from kinozal.login_check import CheckKinozal
from utils.utils import get_country_name_from_ip


class CredentialTests(unittest.TestCase):
    def test_credentials_are_read_at_connection_time(self):
        with patch.dict(os.environ, {"KINOZAL_USERNAME": "user-one", "KINOZAL_PASSWORD": "pass-one"}):
            self.assertEqual(CheckKinozal._login_payload(), {
                "action": "login", "username": "user-one", "password": "pass-one"})
            os.environ["KINOZAL_PASSWORD"] = "pass-two"
            self.assertEqual(get_login_payload()["password"], "pass-two")

    def test_missing_credentials_do_not_send_requests(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch("kinozal.login_check.requests.Session") as check_session, \
                patch("kinozal.kinozal.sessions.Session") as scraper_session:
            for connect in (CheckKinozal().connect2kinozal,
                            CKinozal.__new__(CKinozal)._CKinozal__connect2kinozal):
                with self.assertRaisesRegex(ValueError, "KINOZAL_USERNAME and KINOZAL_PASSWORD"):
                    connect()
            check_session.assert_not_called()
            scraper_session.assert_not_called()
            self.assertEqual(get_login_payload(required=False)["password"], "")

    def test_partial_environment_is_rejected_even_for_browser_login(self):
        for env in ({"KINOZAL_USERNAME": "example"}, {"KINOZAL_PASSWORD": "example"}):
            with self.subTest(variable=next(iter(env))), patch.dict(os.environ, env, clear=True):
                with self.assertRaisesRegex(ValueError, "Set both"):
                    CheckKinozal().connect2kinozal_alt()

    def test_ipinfo_requires_environment_token_before_contacting_service(self):
        with patch.dict(os.environ, {}, clear=True), patch("utils.utils.ipinfo.getHandler") as handler:
            with self.assertRaisesRegex(ValueError, "IPINFO_TOKEN"):
                get_country_name_from_ip("192.0.2.1")
            handler.assert_not_called()
            os.environ["IPINFO_TOKEN"] = "test-token"
            handler.return_value.getDetails.return_value.country_name = "Example"
            self.assertEqual(get_country_name_from_ip("192.0.2.1"), "Example")
            handler.assert_called_once_with("test-token")


if __name__ == "__main__":
    unittest.main()
