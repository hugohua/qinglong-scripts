import importlib.util
import unittest
import builtins
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "520switch-signin.py"


def load_script():
    spec = importlib.util.spec_from_file_location("switch520_signin_py", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Switch520PythonSignInTests(unittest.TestCase):
    def test_extract_zb_config_reads_ajax_nonce_and_url(self):
        module = load_script()
        html = """
        <script>
        var zb = {"ajax_url":"https://www.520switch.com/wp-admin/admin-ajax.php","ajax_nonce":"b16f4b3c1a"};
        </script>
        """

        config = module.extract_zb_config(html)

        self.assertEqual(config["ajax_nonce"], "b16f4b3c1a")
        self.assertEqual(config["ajax_url"], "https://www.520switch.com/wp-admin/admin-ajax.php")

    def test_recognize_captcha_returns_uppercase_text_from_base64_data_url(self):
        module = load_script()

        class FakeOcr:
            def classification(self, image_bytes):
                self.image_bytes = image_bytes
                return "irrd"

        data_url = "data:image/jpeg;base64,aW1hZ2UtYnl0ZXM="
        captcha = module.recognize_captcha(module.decode_image_data(data_url), FakeOcr)

        self.assertEqual(captcha, "IRRD")

    def test_run_sign_in_flow_uses_valid_cookie_without_login(self):
        module = load_script()
        session = FakeSession(sign_payloads=[{"status": 1, "msg": "签到成功"}])
        stdout = StringIO()

        with redirect_stdout(stdout):
            result = module.run_sign_in_flow(
                session,
                cookie_header="wordpress_logged_in_test=old-cookie",
                username="unused",
                password="unused",
            )

        self.assertEqual(result["message"], "签到成功")
        self.assertEqual(session.post_actions(), ["zb_user_qiandao"])
        self.assertEqual(session.cookies.values["wordpress_logged_in_test"], "old-cookie")
        self.assertIn("检测到 SWITCH520_COOKIE，优先使用 Cookie 签到", stdout.getvalue())
        self.assertIn("Cookie 正常，签到请求完成", stdout.getvalue())

    def test_run_sign_in_flow_logs_in_after_cookie_expires_and_updates_qinglong_cookie(self):
        module = load_script()
        session = FakeSession(
            sign_payloads=[
                {"status": 0, "msg": "请先登录"},
                {"status": 1, "msg": "签到成功"},
            ],
        )
        api = FakeQingLongApi(existing_cookie=True)
        stdout = StringIO()

        with redirect_stdout(stdout):
            result = module.run_sign_in_flow(
                session,
                cookie_header="wordpress_logged_in_test=expired-cookie",
                username="user@example.com",
                password="secret",
                ocr_factory=lambda: StaticOcr("irrd"),
                qlapi=api,
            )

        self.assertEqual(result["message"], "签到成功")
        self.assertEqual(
            session.post_actions(),
            [
                "zb_user_qiandao",
                "zb_get_captcha_img",
                "zb_user_login",
                "zb_user_qiandao",
            ],
        )
        login_payload = session.posts[2]["data"]
        self.assertEqual(login_payload["captcha_code"], "IRRD")
        self.assertEqual(login_payload["action"], "zb_user_login")
        self.assertEqual(api.updated_env["value"], "wordpress_logged_in_test=fresh-cookie")
        self.assertIn("Cookie 异常或已失效，开始重新登录", stdout.getvalue())
        self.assertIn("登录成功，已刷新 Cookie", stdout.getvalue())

    def test_run_sign_in_flow_logs_in_after_unauthenticated_sign_in_returns_http_400(self):
        module = load_script()
        session = FakeSession(
            sign_payloads=[
                FakeResponse(text="0", status_code=400),
                {"status": 1, "msg": "签到成功"},
            ],
        )
        stdout = StringIO()

        with redirect_stdout(stdout):
            result = module.run_sign_in_flow(
                session,
                cookie_header="wordpress_logged_in_test=expired-cookie",
                username="user@example.com",
                password="secret",
                ocr_factory=lambda: StaticOcr("irrd"),
            )

        self.assertEqual(result["message"], "签到成功")
        self.assertIn("Cookie 异常或已失效，开始重新登录", stdout.getvalue())
        self.assertEqual(
            session.post_actions(),
            [
                "zb_user_qiandao",
                "zb_get_captcha_img",
                "zb_user_login",
                "zb_user_qiandao",
            ],
        )

    def test_update_qinglong_cookie_creates_missing_env(self):
        module = load_script()
        api = FakeQingLongApi(existing_cookie=False)
        stdout = StringIO()

        with redirect_stdout(stdout):
            updated = module.update_qinglong_cookie("wordpress_logged_in_test=fresh-cookie", api)

        self.assertTrue(updated)
        self.assertEqual(
            api.created_env,
            {"name": "SWITCH520_COOKIE", "value": "wordpress_logged_in_test=fresh-cookie"},
        )
        self.assertEqual(stdout.getvalue(), "")

    def test_update_qinglong_cookie_reads_qlapi_from_builtins(self):
        module = load_script()
        api = FakeQingLongApi(existing_cookie=True)
        stdout = StringIO()

        original = getattr(builtins, "QLAPI", None)
        had_original = hasattr(builtins, "QLAPI")
        builtins.QLAPI = api
        try:
            with redirect_stdout(stdout):
                updated = module.update_qinglong_cookie("wordpress_logged_in_test=fresh-cookie")
        finally:
            if had_original:
                builtins.QLAPI = original
            else:
                del builtins.QLAPI

        self.assertTrue(updated)
        self.assertEqual(api.updated_env["value"], "wordpress_logged_in_test=fresh-cookie")
        self.assertEqual(stdout.getvalue(), "")

    def test_update_qinglong_cookie_logs_missing_qlapi(self):
        module = load_script()
        stdout = StringIO()

        with redirect_stdout(stdout):
            updated = module.update_qinglong_cookie("wordpress_logged_in_test=fresh-cookie")

        self.assertFalse(updated)
        self.assertIn("未检测到 QingLong QLAPI，无法自动更新 SWITCH520_COOKIE", stdout.getvalue())

    def test_login_with_captcha_logs_retry_after_login_failure(self):
        module = load_script()
        session = FakeSession(
            sign_payloads=[],
            login_payloads=[
                {"status": 0, "msg": "验证码错误"},
                {"status": 1, "msg": "登录成功"},
            ],
        )
        stdout = StringIO()

        with redirect_stdout(stdout):
            payload = module.login_with_captcha(
                session,
                "user@example.com",
                "secret",
                ocr_factory=lambda: StaticOcr("irrd"),
            )

        self.assertEqual(payload["msg"], "登录成功")
        self.assertEqual(
            session.post_actions(),
            [
                "zb_get_captcha_img",
                "zb_user_login",
                "zb_get_captcha_img",
                "zb_user_login",
            ],
        )
        logs = stdout.getvalue()
        self.assertIn("开始验证码登录，第 1/3 次", logs)
        self.assertIn("登录失败，准备重新获取验证码：验证码错误", logs)
        self.assertIn("开始验证码登录，第 2/3 次", logs)
        self.assertIn("验证码登录成功", logs)

    def test_login_with_captcha_retries_after_ocr_failure(self):
        module = load_script()
        session = FakeSession(
            sign_payloads=[],
            login_payloads=[
                {"status": 1, "msg": "登录成功"},
            ],
        )
        ocr = FlakyOcr(["bad", "irrd"])
        stdout = StringIO()

        with redirect_stdout(stdout):
            payload = module.login_with_captcha(
                session,
                "user@example.com",
                "secret",
                ocr_factory=lambda: ocr,
            )

        self.assertEqual(payload["msg"], "登录成功")
        self.assertEqual(ocr.calls, 2)
        self.assertEqual(
            session.post_actions(),
            [
                "zb_get_captcha_img",
                "zb_get_captcha_img",
                "zb_user_login",
            ],
        )
        logs = stdout.getvalue()
        self.assertIn("OCR 识别失败，准备重新获取验证码", logs)
        self.assertIn("开始验证码登录，第 2/3 次", logs)


class StaticOcr:
    def __init__(self, text):
        self.text = text

    def classification(self, image_bytes):
        if image_bytes != b"image-bytes":
            raise AssertionError("unexpected image bytes")
        return self.text


class FlakyOcr:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def classification(self, image_bytes):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if outcome == "bad":
            raise RuntimeError("ocr failed")
        return outcome


class FakeCookies:
    def __init__(self):
        self.values = {}

    def set(self, name, value, domain=None, path=None):
        self.values[name] = value

    def __iter__(self):
        for name, value in self.values.items():
            yield SimpleNamespace(name=name, value=value)


class FakeResponse:
    def __init__(self, text="", payload=None, status_code=200):
        self.text = text
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, sign_payloads, login_payloads=None):
        self.cookies = FakeCookies()
        self.sign_payloads = list(sign_payloads)
        self.login_payloads = list(login_payloads or [{"status": 1, "msg": "登录成功"}])
        self.gets = []
        self.posts = []

    def get(self, url, headers=None, timeout=None):
        self.gets.append({"url": url, "headers": headers, "timeout": timeout})
        return FakeResponse(text="""
        <script>
        var zb = {"ajax_url":"https://www.520switch.com/wp-admin/admin-ajax.php","ajax_nonce":"b16f4b3c1a"};
        </script>
        """)

    def post(self, url, headers=None, data=None, timeout=None):
        self.posts.append({"url": url, "headers": headers, "data": data, "timeout": timeout})
        action = data.get("action")
        if action == "zb_user_qiandao":
            payload = self.sign_payloads.pop(0)
            if isinstance(payload, FakeResponse):
                return payload
            return FakeResponse(payload=payload)
        if action == "zb_get_captcha_img":
            return FakeResponse(payload={
                "status": 1,
                "msg": "data:image/jpeg;base64,aW1hZ2UtYnl0ZXM=",
            })
        if action == "zb_user_login":
            payload = self.login_payloads.pop(0)
            if payload.get("status") == 1:
                self.cookies.values = {"wordpress_logged_in_test": "fresh-cookie"}
            return FakeResponse(payload=payload)
        raise AssertionError(f"unexpected action: {action}")

    def post_actions(self):
        return [item["data"].get("action") for item in self.posts]


class FakeQingLongApi:
    def __init__(self, existing_cookie):
        self.existing_cookie = existing_cookie
        self.updated_env = None
        self.created_env = None

    def getEnvs(self, payload):
        data = []
        if self.existing_cookie:
            data = [{"id": 1, "name": "SWITCH520_COOKIE", "value": "old-cookie"}]
        return {"code": 200, "data": data, "message": "ok"}

    def updateEnv(self, payload):
        self.updated_env = payload["env"]
        return {"code": 200, "data": self.updated_env, "message": "ok"}

    def createEnv(self, payload):
        self.created_env = payload["envs"][0]
        return {"code": 200, "data": payload["envs"], "message": "ok"}


if __name__ == "__main__":
    unittest.main()
