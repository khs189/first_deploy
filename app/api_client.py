from __future__ import annotations

import configparser
from typing import Tuple

import requests


def call_juso_api(api_url: str, confm_key: str, keyword: str, first_sort: str = "location"):
    params = {
        "confmKey": confm_key,
        "currentPage": 1,
        "countPerPage": 1,
        "keyword": keyword,
        "resultType": "json",
        "firstSort": first_sort,
    }
    response = requests.get(api_url, params=params, timeout=10)
    response.raise_for_status()
    return response.json()


def verify_credentials(cfg: configparser.ConfigParser, username: str, password: str) -> Tuple[bool, str]:
    if not username or not password:
        return False, "아이디와 비밀번호를 모두 입력하세요."

    mode = cfg.get("auth", "mode", fallback="local").strip().lower()
    if mode == "api":
        return _verify_with_api(cfg, username, password)
    return _verify_local(cfg, username, password)


def _verify_local(cfg: configparser.ConfigParser, username: str, password: str) -> Tuple[bool, str]:
    # users 형식: "user1:pass1, user2:pass2"
    raw_users = cfg.get("auth", "users", fallback="admin:1234")
    users = {}
    for item in raw_users.replace("\n", ",").split(","):
        pair = item.strip()
        if not pair or ":" not in pair:
            continue
        user, pw = pair.split(":", 1)
        users[user.strip()] = pw.strip()

    if not users:
        return False, "설정된 계정 정보가 없습니다."

    if users.get(username) == password:
        return True, "인증 성공"
    return False, "계정 정보가 일치하지 않습니다."


def _verify_with_api(cfg: configparser.ConfigParser, username: str, password: str) -> Tuple[bool, str]:
    auth_url = cfg.get("auth", "auth_url", fallback="").strip()
    if not auth_url:
        return False, "auth_url 설정이 필요합니다."

    method = cfg.get("auth", "method", fallback="post").strip().lower()
    request_format = cfg.get("auth", "request_format", fallback="json").strip().lower()
    timeout_seconds = cfg.getfloat("auth", "timeout_seconds", fallback=10.0)

    username_field = cfg.get("auth", "username_field", fallback="username").strip()
    password_field = cfg.get("auth", "password_field", fallback="password").strip()
    success_field = cfg.get("auth", "success_field", fallback="success").strip()
    message_field = cfg.get("auth", "message_field", fallback="message").strip()

    payload = {
        username_field: username,
        password_field: password,
    }

    try:
        if method == "get":
            response = requests.get(auth_url, params=payload, timeout=timeout_seconds)
        elif request_format == "form":
            response = requests.post(auth_url, data=payload, timeout=timeout_seconds)
        else:
            response = requests.post(auth_url, json=payload, timeout=timeout_seconds)
        response.raise_for_status()
    except requests.RequestException as exc:
        return False, f"인증 서버 요청 실패: {exc}"

    try:
        body = response.json()
    except ValueError:
        return False, "인증 서버 응답이 JSON 형식이 아닙니다."

    authorized = _extract_success(body, success_field)
    if authorized:
        return True, "인증 성공"

    message = _extract_message(body, message_field)
    if message:
        return False, message
    return False, "인증 실패"


def _extract_success(body: dict, success_field: str) -> bool:
    if success_field in body:
        return _to_bool(body.get(success_field))

    for key in ("authorized", "auth", "ok", "result"):
        if key in body:
            return _to_bool(body.get(key))
    return False


def _extract_message(body: dict, message_field: str) -> str:
    value = body.get(message_field)
    if isinstance(value, str):
        return value.strip()

    for key in ("detail", "error", "errorMessage"):
        value = body.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "t", "yes", "y", "ok", "success"}
    return False
