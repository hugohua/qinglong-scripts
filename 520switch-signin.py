#!/usr/bin/env python3
"""
520switch 自动登录与签到脚本。

用途：
- 优先使用缓存的 SWITCH520_COOKIE 执行每日签到。
- 当 Cookie 缺失或失效时，使用账号密码登录，自动获取验证码图片，
  通过 ddddocr 识别验证码，刷新 Cookie 后继续签到。
- 在 QingLong 环境中，登录成功后会尝试更新或创建 SWITCH520_COOKIE，
  并通过 QLAPI.systemNotify 发送签到结果通知。

依赖：
    python3 -m pip install -r requirements.txt

本地用法：
    cp .env.example .env
    # 在 .env 中填写 SWITCH520_USERNAME / SWITCH520_PASSWORD，
    # SWITCH520_COOKIE 可留空或填入已有 Cookie。
    python3 520switch-signin.py

QingLong 用法：
    1. 上传 520switch-signin.py 和 requirements.txt。
    2. 安装依赖：python3 -m pip install -r requirements.txt
    3. 新增环境变量：
       - SWITCH520_USERNAME：登录账号
       - SWITCH520_PASSWORD：登录密码
       - SWITCH520_COOKIE：可留空，登录成功后脚本会尝试自动更新
    4. 新建任务命令：python3 /ql/data/scripts/520switch-signin.py

退出码：
- 0：签到成功或今日已签到。
- 1：配置缺失、登录失败、验证码识别失败、请求失败或页面结构变化。

安全注意：
- 不要把真实账号、密码、Cookie、HAR 抓包文件提交到仓库。
- 本地运行不会回写 .env；QingLong 中仅通过 QLAPI 更新环境变量。
"""

import base64
import binascii
import builtins
import inspect
import json
import os
import re
import sys
import warnings
from pathlib import Path


HOME_URL = "https://www.520switch.com/"
LOGIN_URL = "https://www.520switch.com/login/"
DEFAULT_AJAX_URL = "https://www.520switch.com/wp-admin/admin-ajax.php"
USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1"
)
COOKIE_ENV = "SWITCH520_COOKIE"
USERNAME_ENV = "SWITCH520_USERNAME"
PASSWORD_ENV = "SWITCH520_PASSWORD"
INSTALL_HINT = "python3 -m pip install -r requirements.txt"


class Switch520Error(Exception):
    pass


class AuthenticationRequiredError(Switch520Error):
    pass


class LoginError(Switch520Error):
    pass


def parse_dotenv(text):
    result = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if (
            len(value) >= 2
            and ((value[0] == value[-1] == '"') or (value[0] == value[-1] == "'"))
        ):
            value = value[1:-1]
        result[key.strip()] = value
    return result


def load_dotenv(path=None):
    path = Path(path or ".env")
    if not path.exists():
        return {}
    return parse_dotenv(path.read_text(encoding="utf-8"))


def load_setting(name, env=None, dotenv=None):
    env = os.environ if env is None else env
    value = env.get(name)
    if value and value.strip():
        return value.strip()

    dotenv = load_dotenv() if dotenv is None else dotenv
    value = dotenv.get(name)
    if value and value.strip():
        return value.strip()
    return ""


def require_setting(name, env=None, dotenv=None):
    value = load_setting(name, env, dotenv)
    if not value:
        raise Switch520Error(f"Missing {name}")
    return value


def extract_zb_config(html):
    match = re.search(r"var\s+zb\s*=\s*(\{[\s\S]*?\});", html)
    if not match:
        raise Switch520Error("Unable to find zb config in HTML")

    try:
        config = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise Switch520Error(f"Unable to parse zb config JSON: {exc}") from exc

    ajax_nonce = config.get("ajax_nonce")
    ajax_url = config.get("ajax_url") or DEFAULT_AJAX_URL
    if not ajax_nonce:
        raise Switch520Error("Unable to find ajax_nonce in zb config")

    return {
        "ajax_nonce": str(ajax_nonce),
        "ajax_url": str(ajax_url),
    }


def decode_image_data(value):
    if not isinstance(value, str) or not value.strip():
        raise Switch520Error("Captcha image data is empty")

    raw_text = value.strip()
    payload = raw_text
    if raw_text.startswith("data:"):
        header, separator, body = raw_text.partition(",")
        if not separator or ";base64" not in header.lower():
            raise Switch520Error("Unsupported captcha image data URL")
        payload = body

    payload = "".join(payload.split())
    try:
        return base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise Switch520Error(f"Invalid captcha image base64: {exc}") from exc


def recognize_captcha(image_bytes, ocr_factory=None):
    if ocr_factory is None:
        try:
            import ddddocr
        except ModuleNotFoundError as exc:
            if exc.name == "ddddocr":
                raise Switch520Error(
                    f"Missing dependency: ddddocr. Install it with: {INSTALL_HINT}"
                ) from exc
            raise
        ocr_factory = lambda: ddddocr.DdddOcr(show_ad=False)

    try:
        text = ocr_factory().classification(image_bytes)
    except Exception as exc:
        raise Switch520Error(f"OCR failed: {exc}") from exc

    text = "" if text is None else str(text).strip().upper()
    if not text:
        raise Switch520Error("OCR returned an empty captcha")
    return text


def response_json(response, context):
    try:
        response.raise_for_status()
    except Exception as exc:
        raise Switch520Error(f"{context} failed: {exc}") from exc

    try:
        return response.json()
    except ValueError as exc:
        text = getattr(response, "text", "")
        raise Switch520Error(f"{context} returned non-JSON response: {text[:200]}") from exc


def ajax_headers(referer=LOGIN_URL):
    return {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://www.520switch.com",
        "Referer": referer,
        "X-Requested-With": "XMLHttpRequest",
    }


def page_headers():
    return {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }


def apply_cookie_header(session, cookie_header):
    for part in cookie_header.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        session.cookies.set(name.strip(), value.strip(), domain="www.520switch.com", path="/")


def cookie_header_from_session(session):
    pairs = []
    for cookie in session.cookies:
        if cookie.name and cookie.value:
            pairs.append(f"{cookie.name}={cookie.value}")
    return "; ".join(pairs)


def fetch_zb_config(session, url=LOGIN_URL):
    response = session.get(url, headers=page_headers(), timeout=30)
    try:
        response.raise_for_status()
    except Exception as exc:
        raise Switch520Error(f"Failed to fetch page config: {exc}") from exc
    return extract_zb_config(response.text)


def fetch_captcha_image(session, ajax_url, nonce):
    payload = {
        "action": "zb_get_captcha_img",
        "nonce": nonce,
    }
    response = session.post(
        ajax_url,
        headers=ajax_headers(LOGIN_URL),
        data=payload,
        timeout=30,
    )
    data = response_json(response, "Fetch captcha")
    if data.get("status") != 1:
        raise Switch520Error(str(data.get("msg") or "Failed to fetch captcha image"))
    return decode_image_data(data.get("msg"))


def post_login(session, ajax_url, nonce, username, password, captcha_code):
    payload = {
        "nonce": nonce,
        "user_name": username,
        "user_password": password,
        "captcha_code": captcha_code,
        "remember": "on",
        "action": "zb_user_login",
    }
    response = session.post(
        ajax_url,
        headers=ajax_headers(LOGIN_URL),
        data=payload,
        timeout=30,
    )
    return response_json(response, "Login")


def login_with_captcha(session, username, password, ocr_factory=None, max_attempts=3):
    config = fetch_zb_config(session, LOGIN_URL)
    last_message = "Login failed"

    for attempt in range(1, max_attempts + 1):
        log(f"开始验证码登录，第 {attempt}/{max_attempts} 次")
        image_bytes = fetch_captcha_image(session, config["ajax_url"], config["ajax_nonce"])
        try:
            captcha_code = recognize_captcha(image_bytes, ocr_factory)
        except Switch520Error as exc:
            last_message = str(exc)
            if attempt == max_attempts:
                break
            log(f"OCR 识别失败，准备重新获取验证码：{last_message}")
            continue
        log("验证码已识别，开始提交登录")
        payload = post_login(
            session,
            config["ajax_url"],
            config["ajax_nonce"],
            username,
            password,
            captcha_code,
        )

        if payload.get("status") == 1:
            log("验证码登录成功")
            return payload

        last_message = str(payload.get("msg") or last_message)
        if attempt == max_attempts:
            break
        log(f"登录失败，准备重新获取验证码：{last_message}")

    raise LoginError(last_message)


def classify_sign_result(payload):
    message = str(payload.get("msg") or "Unknown response")
    if payload.get("status") == 1:
        return {
            "ok": True,
            "already_signed": False,
            "message": message,
        }

    if payload.get("status") == 0 and re.search(r"已签到|明日再来", message):
        return {
            "ok": True,
            "already_signed": True,
            "message": message,
        }

    if re.search(r"请先登录|未登录|登录", message):
        raise AuthenticationRequiredError(message)

    raise Switch520Error(message)


def sign_in(session, ajax_url, nonce):
    response = session.post(
        ajax_url,
        headers=ajax_headers(HOME_URL),
        data={
            "action": "zb_user_qiandao",
            "nonce": nonce,
        },
        timeout=30,
    )
    if getattr(response, "status_code", None) == 400 and getattr(response, "text", "").strip() == "0":
        raise AuthenticationRequiredError("请先登录")
    return classify_sign_result(response_json(response, "Sign in"))


def call_api(method, payload):
    result = method(payload)
    if inspect.isawaitable(result):
        import asyncio

        return asyncio.run(result)
    return result


def resolve_qlapi(api=None):
    if api is not None:
        return api

    api = globals().get("QLAPI")
    if api is not None:
        return api

    api = getattr(builtins, "QLAPI", None)
    if api is not None:
        return api

    return None


def update_qinglong_cookie(cookie_header, api=None):
    api = resolve_qlapi(api)
    if not api:
        log("未检测到 QingLong QLAPI，无法自动更新 SWITCH520_COOKIE")
        return False

    get_envs = getattr(api, "getEnvs", None)
    update_env = getattr(api, "updateEnv", None)
    create_env = getattr(api, "createEnv", None)
    if not get_envs or not update_env:
        missing = []
        if not get_envs:
            missing.append("getEnvs")
        if not update_env:
            missing.append("updateEnv")
        log(f"QingLong QLAPI 缺少方法：{', '.join(missing)}")
        return False

    try:
        response = call_api(get_envs, {"searchValue": COOKIE_ENV})
    except Exception as exc:
        log(f"QLAPI getEnvs 调用失败：{exc}")
        return False

    env_items = response.get("data", []) if isinstance(response, dict) else []
    existing = next((item for item in env_items if item.get("name") == COOKIE_ENV), None)

    if existing:
        updated = dict(existing)
        updated["value"] = cookie_header
        try:
            response = call_api(update_env, {"env": updated})
        except Exception as exc:
            log(f"QLAPI updateEnv 调用失败：{exc}")
            return False
        return True

    if create_env:
        try:
            response = call_api(create_env, {"envs": [{"name": COOKIE_ENV, "value": cookie_header}]})
        except Exception as exc:
            log(f"QLAPI createEnv 调用失败：{exc}")
            return False
        return True

    log("QingLong QLAPI 缺少 createEnv，且未找到现有 SWITCH520_COOKIE")
    return False


def build_notification(result_or_error):
    if isinstance(result_or_error, Exception):
        return {
            "title": "520switch 签到失败",
            "content": str(result_or_error),
        }

    if result_or_error.get("ok") and result_or_error.get("already_signed"):
        return {
            "title": "520switch 今日已签到",
            "content": result_or_error.get("message", ""),
        }

    if result_or_error.get("ok"):
        return {
            "title": "520switch 签到成功",
            "content": result_or_error.get("message", ""),
        }

    return {
        "title": "520switch 签到失败",
        "content": str(result_or_error.get("message", "Unknown response")),
    }


def notify_qinglong(payload, api=None):
    api = resolve_qlapi(api)
    method = getattr(api, "systemNotify", None) if api else None
    if not method:
        return None

    try:
        return call_api(method, payload)
    except Exception:
        return None


def create_session():
    warnings.filterwarnings(
        "ignore",
        message="urllib3 v2 only supports OpenSSL",
        category=Warning,
    )
    try:
        import requests
    except ModuleNotFoundError as exc:
        if exc.name == "requests":
            raise Switch520Error(
                f"Missing dependency: requests. Install it with: {INSTALL_HINT}"
            ) from exc
        raise
    return requests.Session()


def log(message):
    print(f"[520switch] {message}", flush=True)


def run_sign_in_flow(session, cookie_header="", username="", password="", ocr_factory=None, qlapi=None):
    if cookie_header:
        log("检测到 SWITCH520_COOKIE，优先使用 Cookie 签到")
        apply_cookie_header(session, cookie_header)
    else:
        log("未检测到 SWITCH520_COOKIE，开始账号密码登录")

    try_login = not bool(cookie_header)
    config = fetch_zb_config(session, HOME_URL if cookie_header else LOGIN_URL)

    if cookie_header:
        try:
            result = sign_in(session, config["ajax_url"], config["ajax_nonce"])
            log("Cookie 正常，签到请求完成")
            return result
        except AuthenticationRequiredError:
            log("Cookie 异常或已失效，开始重新登录")
            try_login = True

    if try_login:
        if not username or not password:
            raise Switch520Error(f"Missing {USERNAME_ENV} or {PASSWORD_ENV}")
        login_with_captcha(session, username, password, ocr_factory=ocr_factory)
        refreshed_cookie = cookie_header_from_session(session)
        if refreshed_cookie:
            if update_qinglong_cookie(refreshed_cookie, qlapi):
                log("登录成功，已刷新 Cookie 并更新 QingLong 环境变量")
            else:
                log("登录成功，已刷新 Cookie")
        config = fetch_zb_config(session, HOME_URL)
        result = sign_in(session, config["ajax_url"], config["ajax_nonce"])
        log("重新登录后签到请求完成")
        return result

    raise Switch520Error("Unexpected sign-in flow state")


def main(env=None, qlapi=None):
    env = os.environ if env is None else env
    dotenv = load_dotenv()
    cookie_header = load_setting(COOKIE_ENV, env, dotenv)
    username = load_setting(USERNAME_ENV, env, dotenv)
    password = load_setting(PASSWORD_ENV, env, dotenv)

    session = create_session()
    result = run_sign_in_flow(
        session,
        cookie_header=cookie_header,
        username=username,
        password=password,
        qlapi=qlapi,
    )
    print(result["message"])
    notify_qinglong(build_notification(result), qlapi)
    return result


def run_cli():
    qlapi = globals().get("QLAPI")
    try:
        return main(qlapi=qlapi)
    except Exception as exc:
        normalized = exc if isinstance(exc, Exception) else Switch520Error(str(exc))
        print(str(normalized), file=sys.stderr)
        notify_qinglong(build_notification(normalized), qlapi)
        raise SystemExit(1)


if __name__ == "__main__":
    run_cli()
