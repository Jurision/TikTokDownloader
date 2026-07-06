import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from src.private_panel.auth import (
    extract_bearer_token,
    require_panel_user,
    token_matches,
    user_from_navi_headers,
)
from src.private_panel.models import JobKind, JobStatus, PanelUser


class PrivatePanelAuthTests(unittest.IsolatedAsyncioTestCase):
    def test_models_include_first_slice_job_kinds(self):
        self.assertEqual(JobKind.DOUYIN_SINGLE.value, "douyin_single")
        self.assertEqual(JobKind.DOUYIN_FAVORITES.value, "douyin_favorites")
        self.assertEqual(JobKind.TIKTOK_SINGLE.value, "tiktok_single")
        self.assertEqual(JobStatus.QUEUED.value, "queued")
        self.assertEqual(JobStatus.RUNNING.value, "running")
        self.assertEqual(JobStatus.SUCCEEDED.value, "succeeded")
        self.assertEqual(JobStatus.FAILED.value, "failed")

    def test_navi_headers_create_panel_user(self):
        user = user_from_navi_headers(
            "user-123",
            "owner@example.com",
            "Owner",
        )

        self.assertEqual(
            user,
            PanelUser(
                id="user-123",
                email="owner@example.com",
                name="Owner",
                via="navi",
            ),
        )

    def test_navi_header_values_are_sanitized(self):
        user = user_from_navi_headers(
            "user\r\nbad",
            "owner@example.com",
            "Owner\nName",
        )

        self.assertEqual(user.id, "user bad")
        self.assertEqual(user.name, "Owner Name")

    def test_missing_navi_user_returns_none(self):
        self.assertIsNone(user_from_navi_headers("", "", ""))

    def test_extract_bearer_token_accepts_bearer_header(self):
        self.assertEqual(extract_bearer_token("Bearer abc123"), "abc123")
        self.assertEqual(extract_bearer_token("bearer abc123"), "abc123")
        self.assertEqual(extract_bearer_token("Token abc123"), "")

    def test_token_matches_uses_constant_time_compare(self):
        with patch.dict(os.environ, {"DOUK_PRIVATE_TOKEN": "secret"}, clear=False):
            self.assertTrue(token_matches("secret"))
            self.assertFalse(token_matches("wrong"))
            self.assertFalse(token_matches(""))

    def test_token_matches_calls_compare_digest_when_tokens_exist(self):
        with patch.dict(os.environ, {"DOUK_PRIVATE_TOKEN": "secret"}, clear=False):
            with patch(
                "src.private_panel.auth.hmac.compare_digest",
                return_value=True,
            ) as compare_digest:
                self.assertTrue(token_matches("secret"))

        compare_digest.assert_called_once_with("secret", "secret")

    def test_token_auth_is_disabled_when_env_token_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(token_matches("secret"))

    async def test_require_panel_user_prefers_navi_identity(self):
        user = await require_panel_user(
            authorization="Bearer wrong",
            x_douk_token="wrong",
            x_tradedocs_user_id="user-123",
            x_tradedocs_user_email="owner@example.com",
            x_tradedocs_user_name="Owner",
        )

        self.assertEqual(user.via, "navi")
        self.assertEqual(user.id, "user-123")

    async def test_require_panel_user_accepts_private_token(self):
        with patch.dict(os.environ, {"DOUK_PRIVATE_TOKEN": "secret"}, clear=False):
            user = await require_panel_user(
                authorization="Bearer secret",
                x_douk_token="",
                x_tradedocs_user_id="",
                x_tradedocs_user_email="",
                x_tradedocs_user_name="",
            )

        self.assertEqual(user.via, "token")
        self.assertEqual(user.id, "token")

    async def test_require_panel_user_accepts_x_douk_token(self):
        with patch.dict(os.environ, {"DOUK_PRIVATE_TOKEN": "secret"}, clear=False):
            user = await require_panel_user(
                authorization="",
                x_douk_token="secret",
                x_tradedocs_user_id="",
                x_tradedocs_user_email="",
                x_tradedocs_user_name="",
            )

        self.assertEqual(user.via, "token")
        self.assertEqual(user.id, "token")

    async def test_require_panel_user_accepts_bearer_when_x_douk_token_is_wrong(self):
        with patch.dict(os.environ, {"DOUK_PRIVATE_TOKEN": "secret"}, clear=False):
            user = await require_panel_user(
                authorization="Bearer secret",
                x_douk_token="wrong",
                x_tradedocs_user_id="",
                x_tradedocs_user_email="",
                x_tradedocs_user_name="",
            )

        self.assertEqual(user.via, "token")
        self.assertEqual(user.id, "token")

    async def test_require_panel_user_accepts_x_douk_token_when_bearer_is_wrong(self):
        with patch.dict(os.environ, {"DOUK_PRIVATE_TOKEN": "secret"}, clear=False):
            user = await require_panel_user(
                authorization="Bearer wrong",
                x_douk_token="secret",
                x_tradedocs_user_id="",
                x_tradedocs_user_email="",
                x_tradedocs_user_name="",
            )

        self.assertEqual(user.via, "token")
        self.assertEqual(user.id, "token")

    async def test_require_panel_user_rejects_token_auth_when_env_token_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(HTTPException) as raised:
                await require_panel_user(
                    authorization="Bearer secret",
                    x_douk_token="secret",
                    x_tradedocs_user_id="",
                    x_tradedocs_user_email="",
                    x_tradedocs_user_name="",
                )

        self.assertEqual(raised.exception.status_code, 401)

    async def test_require_panel_user_rejects_unauthenticated_request(self):
        with patch.dict(os.environ, {"DOUK_PRIVATE_TOKEN": "secret"}, clear=False):
            with self.assertRaises(HTTPException) as raised:
                await require_panel_user(
                    authorization="Bearer wrong",
                    x_douk_token="",
                    x_tradedocs_user_id="",
                    x_tradedocs_user_email="",
                    x_tradedocs_user_name="",
                )

        self.assertEqual(raised.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
