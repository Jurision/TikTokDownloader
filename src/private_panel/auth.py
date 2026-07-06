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


def _env_csv_values(name: str, *, lower: bool = False) -> set[str]:
    values = set()
    for raw in os.environ.get(name, "").split(","):
        value = raw.strip()
        if value:
            values.add(value.lower() if lower else value)
    return values


def _trusted_proxy_header_matches(header_value: str) -> bool:
    expected = os.environ.get("DOUK_TRUSTED_PROXY_SECRET", "")
    if not expected:
        return False
    if not header_value:
        return False
    return hmac.compare_digest(header_value, expected)


def _navi_user_is_allowed(user: PanelUser) -> bool:
    allowed_ids = _env_csv_values("DOUK_ALLOWED_NAVI_USER_IDS")
    allowed_emails = _env_csv_values("DOUK_ALLOWED_NAVI_USER_EMAILS", lower=True)
    if not allowed_ids and not allowed_emails:
        return True
    return user.id in allowed_ids or user.email.lower() in allowed_emails


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
    x_douk_trusted_proxy: str = Header("", alias="X-Douk-Trusted-Proxy"),
    x_tradedocs_user_id: str = Header("", alias="X-Tradedocs-User-Id"),
    x_tradedocs_user_email: str = Header("", alias="X-Tradedocs-User-Email"),
    x_tradedocs_user_name: str = Header("", alias="X-Tradedocs-User-Name"),
) -> PanelUser:
    if user := user_from_navi_headers(
        x_tradedocs_user_id,
        x_tradedocs_user_email,
        x_tradedocs_user_name,
    ):
        if not _trusted_proxy_header_matches(x_douk_trusted_proxy):
            raise HTTPException(status_code=401, detail="Trusted proxy required")
        if not _navi_user_is_allowed(user):
            raise HTTPException(status_code=403, detail="Navi user not allowed")
        return user

    token_candidates = (
        x_douk_token,
        extract_bearer_token(authorization),
    )
    if any(token_matches(token) for token in token_candidates):
        return PanelUser(id="token", name="Private API", via="token")

    raise HTTPException(status_code=401, detail="Authentication required")
