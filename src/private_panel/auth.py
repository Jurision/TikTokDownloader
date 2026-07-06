import hmac
import os

from fastapi import Header, HTTPException

from .models import PanelUser


def _clean_header(value: str, fallback: str = "") -> str:
    text = str(value or fallback).replace("\r", " ").replace("\n", " ").strip()
    text = " ".join(text.split())
    return text[:160]


def user_from_navi_headers(
    user_id: str = "",
    user_email: str = "",
    user_name: str = "",
) -> PanelUser | None:
    clean_id = _clean_header(user_id)
    if not clean_id:
        return None
    return PanelUser(
        id=clean_id,
        email=_clean_header(user_email),
        name=_clean_header(user_name),
        via="navi",
    )


def extract_bearer_token(authorization: str = "") -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        return ""
    return token.strip()


def token_matches(token: str) -> bool:
    expected = os.environ.get("DOUK_PRIVATE_TOKEN", "")
    if not expected or not token:
        return False
    return hmac.compare_digest(token, expected)


async def require_panel_user(
    authorization: str = Header("", alias="Authorization"),
    x_douk_token: str = Header("", alias="X-Douk-Token"),
    x_tradedocs_user_id: str = Header("", alias="X-Tradedocs-User-Id"),
    x_tradedocs_user_email: str = Header("", alias="X-Tradedocs-User-Email"),
    x_tradedocs_user_name: str = Header("", alias="X-Tradedocs-User-Name"),
) -> PanelUser:
    if user := user_from_navi_headers(
        x_tradedocs_user_id,
        x_tradedocs_user_email,
        x_tradedocs_user_name,
    ):
        return user

    token_candidates = (
        x_douk_token,
        extract_bearer_token(authorization),
    )
    if any(token_matches(token) for token in token_candidates):
        return PanelUser(id="token", name="Private API", via="token")

    raise HTTPException(status_code=401, detail="Authentication required")
