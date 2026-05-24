#!/usr/bin/env python3
"""
IPZAN 自动登录并领取金币脚本。

用途：
- 读取一个或多个 IPZAN 账号。
- 使用 Playwright 驱动 Chromium 登录 `https://ipzan.com/`。
- 进入用户页并点击领取金币按钮。
- 捕获 `/home/userWallet-receive` 接口响应，输出每个账号的处理结果。
- 在 QingLong 中如果可用 `QLAPI.systemNotify`，发送汇总通知。

依赖：
    python3 -m pip install -r requirements.txt
    # QingLong Linux 依赖已安装 chromium 时，设置：
    # IPZAN_BROWSER_EXECUTABLE_PATH=/usr/bin/chromium
    # 只有容器内没有系统 Chromium 时，才执行：
    # python3 -m playwright install chromium

本地用法：
    cp .env.example .env
    # 在 .env 中配置 IPZAN_USERNAME / IPZAN_PASSWORD，或配置 IPZAN_ACCOUNTS。
    python3 ipzan-receive-coins.py

QingLong 用法：
    1. 上传 ipzan-receive-coins.py 和 requirements.txt。
    2. 安装依赖：python3 -m pip install -r requirements.txt
    3. 设置 IPZAN_BROWSER_EXECUTABLE_PATH=/usr/bin/chromium。
    4. 新建任务命令：python3 /ql/data/scripts/ipzan-receive-coins.py

安全注意：
- 不要把真实账号、密码、Cookie、HAR 抓包文件提交到仓库。
- 推荐使用 QingLong 环境变量或本地未提交的 `.env` 保存凭据。
"""

import asyncio
import builtins
import inspect
import json
import os
import re
import sys
import time
from pathlib import Path


LOGIN_URL = "https://ipzan.com/"
USER_URL = "https://ipzan.com/user"
RECEIVE_API_MARKER = "/home/userWallet-receive"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)
ACCOUNTS_ENV = "IPZAN_ACCOUNTS"
USERNAME_ENV = "IPZAN_USERNAME"
PASSWORD_ENV = "IPZAN_PASSWORD"
ACCOUNT_NAME_ENV = "IPZAN_ACCOUNT_NAME"
DELAY_ENV = "IPZAN_DELAY_BETWEEN_ACCOUNTS_MS"
MAX_RETRIES_ENV = "IPZAN_MAX_RETRIES"
TIMEOUT_ENV = "IPZAN_TIMEOUT_MS"
HEADLESS_ENV = "IPZAN_HEADLESS"
BROWSER_PATH_ENV = "IPZAN_BROWSER_EXECUTABLE_PATH"
INSTALL_HINT = (
    "python3 -m pip install -r requirements.txt && "
    "python3 -m playwright install chromium"
)


class IPZANError(Exception):
    pass


class Account:
    def __init__(self, username, password, name=""):
        self.username = str(username).strip()
        self.password = str(password).strip()
        self.name = str(name or "").strip()

        if not self.username:
            raise IPZANError("账号缺少 username")
        if not self.password:
            raise IPZANError("账号缺少 password")


class QueueConfig:
    def __init__(self, delay_between_accounts_ms=5000, max_retries=3, timeout_ms=30000):
        self.delay_between_accounts_ms = int(delay_between_accounts_ms)
        self.max_retries = int(max_retries)
        self.timeout_ms = int(timeout_ms)

        if self.delay_between_accounts_ms < 0:
            raise IPZANError(f"{DELAY_ENV} 不能小于 0")
        if self.max_retries < 1:
            raise IPZANError(f"{MAX_RETRIES_ENV} 必须大于等于 1")
        if self.timeout_ms < 1000:
            raise IPZANError(f"{TIMEOUT_ENV} 必须大于等于 1000")


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


def load_setting(name, env=None, dotenv=None, default=""):
    env = os.environ if env is None else env
    value = env.get(name)
    if value and str(value).strip():
        return str(value).strip()

    dotenv = load_dotenv() if dotenv is None else dotenv
    value = dotenv.get(name)
    if value and str(value).strip():
        return str(value).strip()
    return default


def parse_accounts(value):
    raw = "" if value is None else str(value).strip()
    if not raw:
        return []

    if raw.startswith("["):
        try:
            items = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise IPZANError(f"{ACCOUNTS_ENV} 不是有效 JSON：{exc}") from exc
        if not isinstance(items, list):
            raise IPZANError(f"{ACCOUNTS_ENV} 必须是 JSON 数组")

        accounts = []
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                raise IPZANError(f"{ACCOUNTS_ENV} 第 {index} 项必须是对象")
            name = item.get("name") or f"账号{index}"
            accounts.append(Account(item.get("username", ""), item.get("password", ""), name))
        return accounts

    accounts = []
    chunks = [chunk.strip() for chunk in re.split(r"[;\n]+", raw) if chunk.strip()]
    for index, chunk in enumerate(chunks, start=1):
        parts = [part.strip() for part in chunk.split(",")]
        if len(parts) < 2:
            raise IPZANError(f"{ACCOUNTS_ENV} 第 {index} 项格式应为 username,password[,name]")
        name = parts[2] if len(parts) >= 3 and parts[2] else f"账号{index}"
        accounts.append(Account(parts[0], parts[1], name))
    return accounts


def load_accounts(env=None, dotenv=None):
    env = os.environ if env is None else env
    dotenv = load_dotenv() if dotenv is None else dotenv

    accounts = parse_accounts(load_setting(ACCOUNTS_ENV, env, dotenv))
    if accounts:
        return accounts

    username = load_setting(USERNAME_ENV, env, dotenv)
    password = load_setting(PASSWORD_ENV, env, dotenv)
    name = load_setting(ACCOUNT_NAME_ENV, env, dotenv, default="账号1")
    if username or password:
        return [Account(username, password, name)]

    raise IPZANError(f"Missing {ACCOUNTS_ENV} or {USERNAME_ENV}/{PASSWORD_ENV}")


def load_queue_config(env=None, dotenv=None):
    env = os.environ if env is None else env
    dotenv = load_dotenv() if dotenv is None else dotenv
    return QueueConfig(
        delay_between_accounts_ms=load_setting(DELAY_ENV, env, dotenv, default="5000"),
        max_retries=load_setting(MAX_RETRIES_ENV, env, dotenv, default="3"),
        timeout_ms=load_setting(TIMEOUT_ENV, env, dotenv, default="30000"),
    )


def env_flag(name, env=None, dotenv=None, default=True):
    value = load_setting(name, env, dotenv, default="true" if default else "false")
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def extract_message(data):
    if isinstance(data, dict):
        for key in ("msg", "message", "text"):
            value = data.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return json.dumps(data, ensure_ascii=False)
    if data is None:
        return ""
    return str(data).strip()


def normalize_receive_result(api_response):
    if not api_response:
        return {
            "success": True,
            "data": {"message": "按钮已点击，但未获取到API响应"},
            "status": 200,
            "message": "按钮已点击，但未获取到API响应",
        }

    status = int(api_response.get("status") or 0)
    data = api_response.get("data")
    message = extract_message(data) or "领取接口已返回"
    success = status < 400
    result = {
        "success": success,
        "data": data,
        "status": status,
        "message": message,
    }
    if not success:
        result["error"] = message
    return result


def mask_username(username):
    value = str(username or "")
    if re.fullmatch(r"\d{7,}", value):
        return f"{value[:3]}****{value[-4:]}"
    if "@" in value:
        prefix, domain = value.split("@", 1)
        shown = prefix[:2] if len(prefix) >= 2 else prefix[:1]
        return f"{shown}***@{domain}"
    if len(value) <= 4:
        return "***"
    return f"{value[:2]}***{value[-2:]}"


def build_notification(results_or_error):
    if isinstance(results_or_error, Exception):
        return {
            "title": "IPZAN 金币领取失败",
            "content": str(results_or_error),
        }

    results = list(results_or_error)
    total = len(results)
    success_count = len([item for item in results if item.get("success")])
    title = f"IPZAN 金币领取：{success_count}/{total} 成功"
    lines = []
    for item in results:
        status = "成功" if item.get("success") else "失败"
        detail = item.get("message") or item.get("error") or "无返回消息"
        lines.append(
            f"{item.get('account')} ({mask_username(item.get('username'))}): {status} - {detail}"
        )
    return {
        "title": title,
        "content": "\n".join(lines),
    }


async def maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


def call_api(method, payload):
    result = method(payload)
    if inspect.isawaitable(result):
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


def notify_qinglong(payload, api=None):
    api = resolve_qlapi(api)
    method = getattr(api, "systemNotify", None) if api else None
    if not method:
        return None

    try:
        return call_api(method, payload)
    except Exception:
        return None


def log(message):
    print(f"[ipzan] {message}", flush=True)


class AccountQueueManager:
    def __init__(self, accounts, queue_config=None, runner_factory=None, delay_func=None):
        self.accounts = list(accounts)
        self.queue_config = queue_config or QueueConfig()
        self.runner_factory = runner_factory or (lambda account: IPZANCoinReceiver(account))
        self.delay_func = delay_func or asyncio.sleep
        self.results = []

    async def process_all_accounts(self):
        log(f"=== 开始处理 {len(self.accounts)} 个账号的队列 ===")
        log(f"启动时间: {format_now()}")

        for index, account in enumerate(self.accounts):
            log(f"--- 处理第 {index + 1}/{len(self.accounts)} 个账号: {account.name} ---")
            result = await self.process_single_account(account)
            self.results.append(result)

            if index < len(self.accounts) - 1:
                delay_seconds = self.queue_config.delay_between_accounts_ms / 1000
                log(f"等待 {self.queue_config.delay_between_accounts_ms}ms 后处理下一个账号")
                await maybe_await(self.delay_func(delay_seconds))

        self.print_summary()
        return self.results

    async def process_single_account(self, account):
        start_time = time.monotonic()
        last_error = None

        for attempt in range(1, self.queue_config.max_retries + 1):
            try:
                log(f"尝试第 {attempt} 次处理账号: {account.name}")
                runner = self.runner_factory(account)
                result = await asyncio.wait_for(
                    self.run_runner(runner),
                    timeout=self.queue_config.timeout_ms / 1000,
                )
                if result.get("success"):
                    return self.build_account_result(account, result, start_time, attempt)

                last_error = result.get("error") or result.get("message") or "领取失败"
                if attempt >= self.queue_config.max_retries:
                    break
                log(f"账号 {account.name} 第 {attempt} 次尝试失败: {last_error}")
                await maybe_await(self.delay_func(2))
            except Exception as exc:
                last_error = str(exc)
                if isinstance(exc, asyncio.TimeoutError):
                    last_error = "操作超时"
                log(f"账号 {account.name} 第 {attempt} 次尝试失败: {last_error}")
                if attempt >= self.queue_config.max_retries:
                    break
                await maybe_await(self.delay_func(2))

        duration = int((time.monotonic() - start_time) * 1000)
        return {
            "account": account.name,
            "username": account.username,
            "success": False,
            "error": f"重试 {self.queue_config.max_retries} 次后仍然失败: {last_error}",
            "duration": duration,
            "retryCount": self.queue_config.max_retries,
            "timestamp": format_now(),
        }

    async def run_runner(self, runner):
        return await maybe_await(runner.run())

    def build_account_result(self, account, result, start_time, retry_count):
        duration = int((time.monotonic() - start_time) * 1000)
        return {
            "account": account.name,
            "username": account.username,
            "success": bool(result.get("success")),
            "data": result.get("data"),
            "status": result.get("status"),
            "message": result.get("message"),
            "error": result.get("error"),
            "duration": duration,
            "retryCount": retry_count,
            "timestamp": format_now(),
        }

    def print_summary(self):
        log("=== 队列处理完成 ===")
        log(f"处理时间: {format_now()}")
        total = len(self.results)
        success_count = len([result for result in self.results if result.get("success")])
        fail_count = total - success_count
        success_rate = (success_count / total * 100) if total else 0

        log(f"总账号数: {total}")
        log(f"成功: {success_count}")
        log(f"失败: {fail_count}")
        log(f"成功率: {success_rate:.2f}%")
        log("详细结果:")
        for index, result in enumerate(self.results, start=1):
            status = "成功" if result.get("success") else "失败"
            log(
                f"{index}. {status} {result.get('account')} "
                f"({mask_username(result.get('username'))}) - {result.get('duration')}ms"
            )
            if result.get("error"):
                log(f"   错误: {result.get('error')}")


class IPZANCoinReceiver:
    def __init__(self, account, env=None, dotenv=None):
        self.account = account
        self.env = os.environ if env is None else env
        self.dotenv = load_dotenv() if dotenv is None else dotenv
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None

    async def init_browser(self):
        try:
            from playwright.async_api import async_playwright
        except ModuleNotFoundError as exc:
            if exc.name == "playwright":
                raise IPZANError(f"Missing dependency: playwright. Install it with: {INSTALL_HINT}") from exc
            raise

        log("正在启动浏览器")
        self.playwright = await async_playwright().start()
        launch_options = {
            "headless": env_flag(HEADLESS_ENV, self.env, self.dotenv, default=True),
            "args": browser_args(),
        }
        executable_path = (
            load_setting(BROWSER_PATH_ENV, self.env, self.dotenv)
            or load_setting("PUPPETEER_EXECUTABLE_PATH", self.env, self.dotenv)
        )
        if executable_path:
            launch_options["executable_path"] = executable_path

        self.browser = await self.playwright.chromium.launch(**launch_options)
        self.context = await self.browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent=USER_AGENT,
        )
        self.page = await self.context.new_page()
        log("浏览器启动成功")

    async def login(self):
        log("开始登录流程")
        await self.page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
        await self.page.wait_for_timeout(3000)

        clicked = await self.click_home_login_button()
        if not clicked:
            raise IPZANError("未找到登录按钮")

        log("等待登录对话框出现")
        await self.page.wait_for_timeout(5000)

        if await self.page.locator(".el-dialog").count():
            log("登录对话框已出现")
            return await self.fill_login_form()

        log("登录对话框未出现，尝试键盘导航")
        await self.try_alternative_login()
        if await self.page.locator(".el-dialog").count():
            return await self.fill_login_form()

        raise IPZANError("登录对话框未出现")

    async def click_home_login_button(self):
        log("正在查找登录按钮")
        return await self.page.evaluate(
            """
            () => {
                const registerBox = document.querySelector('.register-box');
                if (registerBox) {
                    const buttons = registerBox.querySelectorAll('.el-button.el-button--primary');
                    if (buttons.length >= 2) {
                        buttons[1].click();
                        return true;
                    }
                }

                const buttons = Array.from(document.querySelectorAll('button'));
                const loginButtons = buttons.filter((button) => {
                    const text = button.textContent.trim();
                    return text === '登 录' || text.includes('登录');
                });
                const target = loginButtons[1] || loginButtons[0];
                if (target) {
                    target.click();
                    return true;
                }
                return false;
            }
            """
        )

    async def fill_login_form(self):
        log("开始填写登录表单")
        await self.page.wait_for_selector("input", timeout=10000)
        inputs = self.page.locator("input")
        input_count = await inputs.count()
        log(f"找到 {input_count} 个输入框")
        if input_count < 2:
            raise IPZANError("登录表单输入框数量不足")

        await inputs.nth(0).click()
        await inputs.nth(0).fill(self.account.username)
        await inputs.nth(1).click()
        await inputs.nth(1).fill(self.account.password)

        if input_count >= 3:
            vcode_text = await self.page.evaluate(
                """
                () => {
                    const vcodeEl = document.querySelector('.vcode');
                    return vcodeEl ? vcodeEl.textContent.trim() : '1234';
                }
                """
            )
            await inputs.nth(2).click()
            await inputs.nth(2).fill(vcode_text or "1234")

        clicked = await self.click_dialog_login_button()
        if not clicked:
            raise IPZANError("未找到对话框中的登录按钮")

        log("等待登录完成")
        await self.page.wait_for_timeout(5000)
        await self.page.goto(USER_URL, wait_until="domcontentloaded", timeout=30000)
        await self.page.wait_for_timeout(3000)
        log("用户页面加载完成")
        return True

    async def click_dialog_login_button(self):
        log("查找对话框中的登录按钮")
        return await self.page.evaluate(
            """
            () => {
                const dialogWrapper = document.querySelector('.el-dialog__wrapper.login');
                if (dialogWrapper) {
                    const loginBtn = dialogWrapper.querySelector('.el-button.el-button--primary');
                    if (loginBtn) {
                        loginBtn.click();
                        return true;
                    }
                }

                const buttons = Array.from(document.querySelectorAll('button'));
                const target = buttons.find((button) => {
                    const text = button.textContent.trim();
                    return text === '登 录' || text.includes('登录');
                });
                if (target) {
                    target.click();
                    return true;
                }
                return false;
            }
            """
        )

    async def try_alternative_login(self):
        await self.page.keyboard.press("Tab")
        await self.page.keyboard.press("Tab")
        await self.page.keyboard.press("Enter")
        await self.page.wait_for_timeout(3000)

    async def checkin(self):
        log("开始执行金币领取")
        try:
            async with self.page.expect_response(
                lambda response: RECEIVE_API_MARKER in response.url,
                timeout=15000,
            ) as response_info:
                clicked = await self.click_receive_button()
                if not clicked["success"]:
                    return {
                        "success": False,
                        "error": clicked["message"],
                        "message": clicked["message"],
                    }

            response = await response_info.value
            api_response = await self.parse_api_response(response)
            result = normalize_receive_result(api_response)
            if result.get("success"):
                log(f"金币领取完成: {result.get('message')}")
            else:
                log(f"金币领取失败: {result.get('error')}")
            return result
        except Exception as exc:
            if exc.__class__.__name__ == "TimeoutError":
                log("领取接口响应超时，按钮已点击")
                return normalize_receive_result(None)
            return {
                "success": False,
                "error": str(exc),
                "message": str(exc),
            }

    async def click_receive_button(self):
        log("正在点击领取按钮")
        return await self.page.evaluate(
            """
            () => {
                const receiveBtn = document.querySelector('.user-box-body .el-button.receive-btn');
                if (receiveBtn) {
                    receiveBtn.click();
                    return { success: true, message: '领取按钮点击成功' };
                }
                return { success: false, message: '未找到领取按钮' };
            }
            """
        )

    async def parse_api_response(self, response):
        try:
            data = await response.json()
        except Exception:
            data = {"text": await response.text()}

        return {
            "status": response.status,
            "data": data,
            "url": response.url,
        }

    async def close_browser(self):
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        log("浏览器已关闭")

    async def run(self):
        try:
            log("=== IPZAN 金币领取脚本启动 ===")
            log(f"启动时间: {format_now()}")
            await self.init_browser()
            await self.login()
            return await self.checkin()
        finally:
            await self.close_browser()


def browser_args():
    return [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-web-security",
        "--disable-features=VizDisplayCompositor,TranslateUI",
        "--no-first-run",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-extensions",
        "--disable-plugins",
        "--disable-default-apps",
        "--disable-sync",
        "--disable-translate",
        "--hide-scrollbars",
        "--mute-audio",
        "--no-default-browser-check",
        "--disable-logging",
        "--disable-permissions-api",
        "--disable-presentation-api",
        "--disable-print-preview",
        "--disable-speech-api",
        "--disable-file-system",
        "--disable-directory-listing",
        "--disable-client-side-phishing-detection",
        "--disable-component-update",
        "--disable-domain-reliability",
        "--disable-ipc-flooding-protection",
        "--disable-hang-monitor",
        "--disable-prompt-on-repost",
        "--disable-background-networking",
        "--disable-background-mode",
        "--disable-component-extensions-with-background-pages",
        "--disable-popup-blocking",
        "--metrics-recording-only",
        "--safebrowsing-disable-auto-update",
        "--enable-automation",
        "--password-store=basic",
        "--use-mock-keychain",
    ]


def format_now():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


async def run_flow(env=None, qlapi=None):
    env = os.environ if env is None else env
    dotenv = load_dotenv()
    accounts = load_accounts(env, dotenv)
    queue_config = load_queue_config(env, dotenv)
    manager = AccountQueueManager(accounts, queue_config=queue_config)
    return await manager.process_all_accounts()


def main(env=None, qlapi=None):
    results = asyncio.run(run_flow(env=env, qlapi=qlapi))
    notify_qinglong(build_notification(results), qlapi)
    return results


def run_cli():
    qlapi = globals().get("QLAPI")
    try:
        results = main(qlapi=qlapi)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        notify_qinglong(build_notification(exc), qlapi)
        raise SystemExit(1)

    success_count = len([result for result in results if result.get("success")])
    if success_count > 0:
        raise SystemExit(0)
    raise SystemExit(1)


if __name__ == "__main__":
    run_cli()
