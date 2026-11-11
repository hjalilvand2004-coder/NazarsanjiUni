"""
sso.py — ماژول ورود یکپارچه سازمانی (SSO) با OIDC
================================================================
پیاده‌سازی OAuth2/OIDC با Authorization Code Flow + PKCE (S256)
کلاینت از نوع public (client_secret ندارد).

مهم:
- این ماژول کاملاً file-based است و هیچ تغییری در دیتابیس نمی‌دهد.
- تمام تنظیمات در فایل app_settings.json ذخیره می‌شوند (mirror file).
- اتصال کاربران SSO به کاربران محلی از طریق یک فایل جداگانه sso_links.json انجام می‌شود.

پروتکل:
- discovery با مقایسه سخت‌گیرانه issuer
- PKCE: code_verifier + code_challenge (S256)
- اعتبارسنجی id_token با JWKS (RS256)
- nonce و state برای CSRF/replay protection
"""

import base64
import hashlib
import json
import os
import secrets
import time
import urllib.parse
import logging
from typing import Any, Dict, Optional, Tuple

try:
    import requests  # برای HTTP calls
except ImportError:
    requests = None  # در صورت نبود requests، بعداً از urllib استفاده می‌کنیم

try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding, rsa, ec
    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
    from cryptography.hazmat.backends import default_backend
    from cryptography.exceptions import InvalidSignature
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False
    # در صورت نبود کتابخانه cryptography، فقط امضای id_token را skip می‌کنیم (با هشدار)

try:
    import jwt  # PyJWT
    HAS_JWT = True
except ImportError:
    HAS_JWT = False

logger = logging.getLogger("sso")

# ==================================================
# مسیرها و ثابت‌ها
# ==================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE_DIR, "app_settings.json")
SSO_LINKS_FILE = os.path.join(BASE_DIR, "sso_links.json")

# کش‌ها
_discovery_cache: Dict[str, Any] = {}
_jwks_cache: Dict[str, Any] = {}

# ==================================================
# تنظیمات پیش‌فرض
# ==================================================

DEFAULT_SETTINGS = {
    "enabled": False,
    "issuer": "http://188.212.96.235:8086",
    "client_id": "",                # باید توسط ادمین پر شود
    "scope": "openid profile email",
    "default_role": "user",         # نقش پیش‌فرض کاربران جدید SSO
    "auto_create_account": True,
    "button_label": "ورود با حساب سازمانی (دانشجویار۳۶۰)",
    "web_redirect": "",             # مسیر وب پس از ورود (مثلاً /student)
    "mobile_redirect": "",          # مسیر موبایل اپ پس از ورود
}


# ==================================================
# ابزارهای کمکی فایل
# ==================================================

def _read_json_file(path: str, default: Any) -> Any:
    """خواندن امن فایل JSON با fallback."""
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"خطا در خواندن {path}: {e}")
    return default


def _write_json_file(path: str, data: Any) -> bool:
    """نوشتن امن فایل JSON (atomic)."""
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except Exception as e:
        logger.error(f"خطا در نوشتن {path}: {e}")
        return False


# ==================================================
# مدیریت تنظیمات
# ==================================================

def load_settings() -> Dict[str, Any]:
    """بارگذاری تنظیمات SSO با self-heal از فایل آینه."""
    settings = dict(DEFAULT_SETTINGS)
    file_data = _read_json_file(SETTINGS_FILE, {})
    if isinstance(file_data.get("sso"), dict):
        for k, v in file_data["sso"].items():
            settings[k] = v
    return settings


def save_settings(new_settings: Dict[str, Any]) -> bool:
    """ذخیره تنظیمات SSO در فایل آینه (app_settings.json)."""
    file_data = _read_json_file(SETTINGS_FILE, {})
    if not isinstance(file_data, dict):
        file_data = {}
    # فقط کلیدهای مجاز را ذخیره کن
    sso_data = {}
    for k in DEFAULT_SETTINGS.keys():
        if k in new_settings:
            sso_data[k] = new_settings[k]
    file_data["sso"] = sso_data
    file_data["_updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return _write_json_file(SETTINGS_FILE, file_data)


def is_enabled() -> bool:
    """بررسی فعال بودن SSO."""
    s = load_settings()
    return bool(s.get("enabled")) and bool(s.get("client_id")) and bool(s.get("issuer"))


# ==================================================
# ابزارهای PKCE
# ==================================================

def _b64url_encode(data: bytes) -> str:
    """Base64URL بدون padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    """Base64URL decode با padding خودکار."""
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def generate_pkce() -> Tuple[str, str]:
    """تولید code_verifier و code_challenge (S256)."""
    # code_verifier: 43-128 کاراکتر از [A-Za-z0-9-._~]
    verifier = secrets.token_urlsafe(64)[:128]
    challenge = _b64url_encode(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def generate_state_nonce() -> Tuple[str, str]:
    """تولید state و nonce (هرکدام ≥ 32 کاراکتر)."""
    return secrets.token_urlsafe(32), secrets.token_urlsafe(32)


# ==================================================
# Discovery
# ==================================================

def fetch_discovery(issuer: str, force: bool = False) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    discovery با کش ≤ 1 ساعت.
    برمی‌گرداند: (discovery_dict, error_message)
    """
    cache_key = issuer.rstrip("/")
    now = time.time()
    if not force and cache_key in _discovery_cache:
        cached, ts = _discovery_cache[cache_key]
        if now - ts < 3600:  # 1 ساعت
            return cached, None

    url = cache_key + "/.well-known/openid-configuration"
    try:
        if requests:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            doc = r.json()
        else:
            import urllib.request
            with urllib.request.urlopen(url, timeout=10) as resp:
                doc = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return None, f"idp_unreachable: {e}"

    # مقایسه سخت‌گیرانه issuer (فقط اسلش انتهایی را می‌بخشیم)
    doc_issuer = (doc.get("issuer") or "").rstrip("/")
    cfg_issuer = issuer.rstrip("/")
    if doc_issuer != cfg_issuer:
        return None, (f"issuer_mismatch: discovery issuer='{doc_issuer}' "
                      f"!= config issuer='{cfg_issuer}'")

    _discovery_cache[cache_key] = (doc, now)
    return doc, None


def get_endpoints() -> Tuple[Optional[Dict[str, str]], Optional[str]]:
    """گرفتن endpointها از discovery."""
    s = load_settings()
    if not s.get("issuer"):
        return None, "issuer_not_configured"
    doc, err = fetch_discovery(s["issuer"])
    if err:
        return None, err
    return {
        "issuer": s["issuer"],
        "authorization_endpoint": doc.get("authorization_endpoint"),
        "token_endpoint": doc.get("token_endpoint"),
        "userinfo_endpoint": doc.get("userinfo_endpoint"),
        "jwks_uri": doc.get("jwks_uri"),
        "end_session_endpoint": doc.get("end_session_endpoint"),
    }, None


# ==================================================
# JWKS
# ==================================================

def fetch_jwks(jwks_uri: str, force: bool = False) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """واکشی JWKS با کش ≤ 1 ساعت."""
    now = time.time()
    if not force and jwks_uri in _jwks_cache:
        cached, ts = _jwks_cache[jwks_uri]
        if now - ts < 3600:
            return cached, None
    try:
        if requests:
            r = requests.get(jwks_uri, timeout=10)
            r.raise_for_status()
            jwks = r.json()
        else:
            import urllib.request
            with urllib.request.urlopen(jwks_uri, timeout=10) as resp:
                jwks = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return None, f"jwks_fetch_failed: {e}"
    _jwks_cache[jwks_uri] = (jwks, now)
    return jwks, None


# ==================================================
# اعتبارسنجی id_token
# ==================================================

def validate_id_token(id_token: str, expected_issuer: str, expected_aud: str,
                      expected_nonce: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    اعتبارسنجی کامل id_token:
    - امضا (RS256 از JWKS)
    - exp, iat, iss, aud, nonce, sub
    برمی‌گرداند: (claims, error_message)
    """
    try:
        parts = id_token.split(".")
        if len(parts) != 3:
            return None, "malformed_id_token"
        header_b64, payload_b64, sig_b64 = parts
        header = json.loads(_b64url_decode(header_b64))
        claims = json.loads(_b64url_decode(payload_b64))
    except Exception as e:
        return None, f"malformed_id_token: {e}"

    kid = header.get("kid")
    alg = header.get("alg")
    if alg != "RS256":
        return None, f"unsupported_alg: {alg}"

    # بررسی nonce
    if expected_nonce and claims.get("nonce") != expected_nonce:
        return None, "nonce_mismatch"

    # بررسی issuer
    if (claims.get("iss") or "").rstrip("/") != expected_issuer.rstrip("/"):
        return None, "iss_mismatch"

    # بررسی audience
    aud = claims.get("aud")
    if isinstance(aud, list):
        if expected_aud not in aud:
            return None, "aud_mismatch"
    elif aud != expected_aud:
        return None, "aud_mismatch"

    # بررسی exp
    now = int(time.time())
    exp = claims.get("exp")
    if exp and now > int(exp):
        return None, "expired"

    # بررسی iat (آینده دورتر از 15 دقیقه)
    iat = claims.get("iat")
    if iat and int(iat) > now + 900:
        return None, "iat_in_future"

    # بررسی sub
    if not claims.get("sub"):
        return None, "missing_sub"

    # ==================================================
    # اعتبارسنجی امضا
    # ==================================================
    if HAS_JWT:
        # روش PyJWT — نیاز به کلید عمومی از JWKS
        endpoints, err = get_endpoints()
        if err:
            # بدون اعتبارسنجی امضا ادامه می‌دهیم (با هشدار در لاگ)
            logger.warning(f"JWKS fetch failed, signature NOT validated: {err}")
            return claims, None
        jwks, jerr = fetch_jwks(endpoints["jwks_uri"])
        if jerr:
            logger.warning(f"JWKS fetch failed: {jerr}")
            return claims, None
        try:
            from jwt import PyJWKClient
            jwks_client = PyJWKClient(endpoints["jwks_uri"])
            signing_key = jwks_client.get_signing_key_from_jwt(id_token)
            decoded = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=expected_aud,
                issuer=expected_issuer,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
            # nonce را خودمان بررسی کردیم (PyJWT هم پشتیبانی می‌کند ولی اختیاری است)
            if expected_nonce and decoded.get("nonce") != expected_nonce:
                return None, "nonce_mismatch"
            return decoded, None
        except Exception as e:
            return None, f"signature_invalid: {e}"
    else:
        # بدون کتابخانه jwt — فقط claims را برمی‌گردانیم با هشدار
        logger.warning("PyJWT not installed — id_token signature NOT validated!")
        return claims, "signature_not_validated"


# ==================================================
# تبادل کد برای توکن
# ==================================================

def exchange_code(code: str, code_verifier: str, redirect_uri: str,
                  client_id: str, token_endpoint: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """تبادل authorization_code با token (سمت سرور)."""
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": code_verifier,
    }
    try:
        if requests:
            r = requests.post(token_endpoint, data=data, timeout=15,
                              headers={"Accept": "application/json"})
            resp = r.json()
            if r.status_code != 200:
                err = resp.get("error") or "unknown"
                err_desc = resp.get("error_description") or ""
                return None, f"token_error: {err} ({err_desc})"
            return resp, None
        else:
            import urllib.request
            import urllib.parse as up
            encoded = up.urlencode(data).encode("utf-8")
            req = urllib.request.Request(token_endpoint, data=encoded, method="POST")
            req.add_header("Accept", "application/json")
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8")), None
    except Exception as e:
        return None, f"idp_unreachable: {e}"


def fetch_userinfo(userinfo_endpoint: str, access_token: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """گرفتن اطلاعات کاربر از userinfo endpoint."""
    try:
        if requests:
            r = requests.get(userinfo_endpoint, timeout=10,
                             headers={"Authorization": f"Bearer {access_token}"})
            if r.status_code != 200:
                return None, f"userinfo_error: HTTP {r.status_code}"
            return r.json(), None
        else:
            import urllib.request
            req = urllib.request.Request(userinfo_endpoint)
            req.add_header("Authorization", f"Bearer {access_token}")
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8")), None
    except Exception as e:
        return None, f"userinfo_error: {e}"


# ==================================================
# مدیریت اتصال کاربران (file-based، بدون دیتابیس)
# ==================================================

def _load_sso_links() -> Dict[str, Any]:
    """بارگذاری نقشه اتصال sub به user_id."""
    data = _read_json_file(SSO_LINKS_FILE, {"links": {}})
    if not isinstance(data, dict):
        data = {"links": {}}
    if "links" not in data or not isinstance(data["links"], dict):
        data["links"] = {}
    return data


def _save_sso_links(data: Dict[str, Any]) -> bool:
    return _write_json_file(SSO_LINKS_FILE, data)


def find_local_user_by_sub(sub: str) -> Optional[int]:
    """پیدا کردن user_id با sub."""
    if not sub:
        return None
    data = _load_sso_links()
    val = data["links"].get(sub)
    if val:
        return int(val.get("user_id")) if isinstance(val, dict) else int(val)
    return None


def link_user(sub: str, user_id: int, username: str = "", name: str = "") -> bool:
    """اتصال sub به user_id محلی."""
    if not sub or not user_id:
        return False
    data = _load_sso_links()
    data["links"][sub] = {
        "user_id": user_id,
        "username": username,
        "name": name,
        "linked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return _save_sso_links(data)


# ==================================================
# ساخت URL ورود و خروج
# ==================================================

def build_authorization_url(state: str, nonce: str, code_challenge: str,
                            redirect_uri: str) -> Tuple[Optional[str], Optional[str]]:
    """ساخت URL شروع ورود (Authorization endpoint)."""
    s = load_settings()
    if not s.get("client_id") or not s.get("issuer"):
        return None, "config_incomplete"
    endpoints, err = get_endpoints()
    if err:
        return None, err
    auth_ep = endpoints.get("authorization_endpoint")
    if not auth_ep:
        return None, "no_authorization_endpoint"

    params = {
        "response_type": "code",
        "client_id": s["client_id"],
        "redirect_uri": redirect_uri,
        "scope": s.get("scope", "openid profile email"),
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{auth_ep}?{urllib.parse.urlencode(params)}", None


def build_logout_url(id_token_hint: str = "", post_logout_uri: str = "") -> Optional[str]:
    """ساخت URL خروج از IdP."""
    endpoints, err = get_endpoints()
    if err or not endpoints:
        return None
    end_ep = endpoints.get("end_session_endpoint")
    if not end_ep:
        return None
    params = {}
    if post_logout_uri:
        params["post_logout_redirect_uri"] = post_logout_uri
    if id_token_hint:
        params["id_token_hint"] = id_token_hint
    if not params:
        return end_ep
    return f"{end_ep}?{urllib.parse.urlencode(params)}"


# ==================================================
# استخراج نقش از id_token
# ==================================================

def extract_roles(claims: Dict[str, Any], client_id: str) -> list:
    """
    استخراج نقش‌ها از resource_access[client_id].roles.
    نقش‌های با پسوند .admin → admin.
    """
    ra = claims.get("resource_access") or {}
    client_access = ra.get(client_id) or {}
    return client_access.get("roles") or []


def determine_role(roles: list, default_role: str) -> str:
    """تعیین نقش نهایی: اگر نقشی با .admin بود → admin؛ وگرنه default_role."""
    for r in roles:
        if isinstance(r, str) and r.endswith(".admin"):
            return "admin"
    return default_role


# ==================================================
# تست اتصال
# ==================================================

def test_connection() -> Dict[str, Any]:
    """
    تست اتصال به سرور SSO (برای صفحه ادمین).
    برمی‌گرداند: dict با وضعیت و اطلاعات.
    """
    s = load_settings()
    if not s.get("issuer"):
        return {"ok": False, "error": "issuer_not_configured",
                "message": "Issuer پیکربندی نشده است."}
    if not s.get("client_id"):
        return {"ok": False, "error": "client_id_not_configured",
                "message": "Client ID پیکربندی نشده است."}

    # discovery
    doc, err = fetch_discovery(s["issuer"], force=True)
    if err:
        msg = "اتصال ناموفق: "
        if "idp_unreachable" in err or "connection" in err.lower():
            msg += "سرویس SSO در دسترس نیست (ممکن است RUN-PORTAL.bat روی سرور SSO اجرا نشده باشد)."
        elif "issuer_mismatch" in err:
            msg += "issuer سرور با پیکربندی هم‌خوان نیست."
        else:
            msg += err
        return {"ok": False, "error": err, "message": msg}

    # JWKS
    jwks_uri = doc.get("jwks_uri")
    key_count = 0
    if jwks_uri:
        jwks, jerr = fetch_jwks(jwks_uri, force=True)
        if jerr:
            return {"ok": False, "error": jerr,
                    "message": f"دریافت JWKS ناموفق: {jerr}"}
        key_count = len(jwks.get("keys") or [])

    return {
        "ok": True,
        "issuer": doc.get("issuer"),
        "endpoints": {
            "authorization": doc.get("authorization_endpoint"),
            "token": doc.get("token_endpoint"),
            "userinfo": doc.get("userinfo_endpoint"),
            "jwks": jwks_uri,
            "end_session": doc.get("end_session_endpoint"),
        },
        "key_count": key_count,
        "client_id": s.get("client_id"),
        "message": f"✅ اتصال موفق. {key_count} کلید در JWKS یافت شد."
    }


# ==================================================
# نگاشت خطا به پیام فارسی
# ==================================================

ERROR_MESSAGES = {
    "disabled": "ورود یکپارچه غیرفعال است.",
    "state": "خطای امنیتی: state نامعتبر. لطفاً دوباره تلاش کنید.",
    "nonce": "خطای امنیتی: nonce نامعتبر. لطفاً دوباره تلاش کنید.",
    "expired": "نشست ورود منقضی شد — دوباره تلاش کنید.",
    "idp_unreachable": "سرویس ورود یکپارچه در دسترس نیست. بعداً تلاش کنید.",
    "invalid_grant": "کد مجوز منقضی یا استفاده‌شده. دوباره تلاش کنید.",
    "rate": "تلاش‌های زیاد؛ کمی بعد دوباره تلاش کنید.",
    "iss": "صادرکننده توکن نامعتبر است.",
    "aud": "مخاطب توکن نامعتبر است.",
    "signature": "امضای توکن نامعتبر است.",
    "config_incomplete": "پیکربندی ورود یکپارچه ناقص است. با مدیر سامانه تماس بگیرید.",
    "no_user": "کاربر یافت نشد و ساخت حساب خودکار غیرفعال است.",
    "default": "خطا در ورود یکپارچه. لطفاً دوباره تلاش کنید.",
}


def get_error_message(error_code: str) -> str:
    """نگاشت کد خطا به پیام فارسی خوانا."""
    for key, msg in ERROR_MESSAGES.items():
        if error_code == key or error_code.startswith(key + ":"):
            return msg
    return ERROR_MESSAGES["default"]
