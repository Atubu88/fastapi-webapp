from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any, Dict
from urllib.parse import parse_qs

import httpx
from fastapi import HTTPException
from core.config import get_bot_token

def _calc_hmacs(token: str, data_check_string: str) -> Dict[str, str]:
    secret_webapp = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()
    hash_webapp = hmac.new(secret_webapp, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    secret_login = hashlib.sha256(token.encode("utf-8")).digest()
    hash_login = hmac.new(secret_login, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    return {"webapp": hash_webapp, "login": hash_login}

def validate_init_data(init_data: str) -> Dict[str, Any]:
    if not init_data:
        raise HTTPException(status_code=400, detail="initData is required")

    token = get_bot_token()
    parsed = {k: v[0] for k, v in parse_qs(init_data, strict_parsing=True).items()}

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=400, detail="hash is missing from initData")

    data_check_string = "\n".join(f"{k}={parsed[k]}" for k in sorted(parsed.keys()))
    h1 = _calc_hmacs(token, data_check_string)

    parsed_legacy = dict(parsed)
    parsed_legacy.pop("signature", None)
    data_check_string_legacy = "\n".join(f"{k}={parsed_legacy[k]}" for k in sorted(parsed_legacy.keys()))
    h2 = _calc_hmacs(token, data_check_string_legacy)

    if received_hash not in {h1["webapp"], h1["login"], h2["webapp"], h2["login"]}:
        try:
            r = httpx.get(f"https://api.telegram.org/bot{token}/getMe", timeout=5)
            bot_info = r.json()
            print("getMe:", bot_info)
        except Exception as e:
            print("getMe error:", repr(e))
        raise HTTPException(status_code=401, detail="Invalid initData hash")

    try:
        auth_ts = int(parsed.get("auth_date", "0"))
        if abs(datetime.now(timezone.utc).timestamp() - auth_ts) > 86400:
            print("Warning: initData auth_date looks older than 24h.")
    except ValueError:
        pass

    user_raw = parsed.get("user")
    if not user_raw:
        raise HTTPException(status_code=400, detail="user payload is missing")

    try:
        user_payload = json.loads(user_raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid user JSON in initData")

    if "id" not in user_payload:
        raise HTTPException(status_code=400, detail="user.id is required in initData")

    print("Validated user:", user_payload)

    return {
        "auth_date": parsed.get("auth_date"),
        "query_id": parsed.get("query_id"),
        "user": user_payload,
    }
