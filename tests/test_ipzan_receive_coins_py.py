import importlib.util
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "ipzan-receive-coins.py"


def load_script():
    spec = importlib.util.spec_from_file_location("ipzan_receive_coins_py", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class IPZANReceiveCoinsTests(unittest.TestCase):
    def test_parse_accounts_reads_json_account_list(self):
        module = load_script()
        accounts = module.parse_accounts(
            """
            [
              {"username": "user-a", "password": "secret-a", "name": "主账号"},
              {"username": "user-b", "password": "secret-b"}
            ]
            """
        )

        self.assertEqual([account.username for account in accounts], ["user-a", "user-b"])
        self.assertEqual([account.password for account in accounts], ["secret-a", "secret-b"])
        self.assertEqual([account.name for account in accounts], ["主账号", "账号2"])

    def test_load_accounts_falls_back_to_single_account_env(self):
        module = load_script()
        accounts = module.load_accounts(
            env={
                "IPZAN_USERNAME": "single-user",
                "IPZAN_PASSWORD": "single-secret",
                "IPZAN_ACCOUNT_NAME": "单账号",
            },
            dotenv={},
        )

        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0].username, "single-user")
        self.assertEqual(accounts[0].password, "single-secret")
        self.assertEqual(accounts[0].name, "单账号")

    def test_normalize_receive_result_keeps_successful_api_response(self):
        module = load_script()

        result = module.normalize_receive_result(
            {
                "status": 200,
                "data": {"code": 0, "msg": "领取成功"},
                "url": "https://ipzan.com/home/userWallet-receive",
            }
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["message"], "领取成功")

    def test_normalize_receive_result_accepts_missing_api_response_after_click(self):
        module = load_script()

        result = module.normalize_receive_result(None)

        self.assertTrue(result["success"])
        self.assertEqual(result["message"], "按钮已点击，但未获取到API响应")

    def test_build_notification_summarizes_queue_results(self):
        module = load_script()

        notification = module.build_notification(
            [
                {"account": "账号1", "username": "13800138000", "success": True, "message": "领取成功"},
                {"account": "账号2", "username": "user@example.com", "success": False, "error": "登录失败"},
            ]
        )

        self.assertEqual(notification["title"], "IPZAN 金币领取：1/2 成功")
        self.assertIn("账号1 (138****8000): 成功 - 领取成功", notification["content"])
        self.assertIn("账号2 (us***@example.com): 失败 - 登录失败", notification["content"])


class IPZANQueueManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_process_single_account_retries_transient_failure(self):
        module = load_script()
        account = module.Account(username="user-a", password="secret", name="账号A")
        outcomes = [
            RuntimeError("临时失败"),
            {"success": True, "message": "领取成功", "data": {"msg": "领取成功"}},
        ]
        calls = []

        def runner_factory(received_account):
            class Runner:
                async def run(self):
                    calls.append(received_account.username)
                    outcome = outcomes.pop(0)
                    if isinstance(outcome, Exception):
                        raise outcome
                    return outcome

            return Runner()

        manager = module.AccountQueueManager(
            [account],
            queue_config=module.QueueConfig(max_retries=3, timeout_ms=1000),
            runner_factory=runner_factory,
            delay_func=lambda seconds: None,
        )
        stdout = StringIO()

        with redirect_stdout(stdout):
            result = await manager.process_single_account(account)

        self.assertTrue(result["success"])
        self.assertEqual(result["retryCount"], 2)
        self.assertEqual(calls, ["user-a", "user-a"])
        self.assertIn("第 1 次尝试失败", stdout.getvalue())

    async def test_process_all_accounts_waits_between_accounts(self):
        module = load_script()
        accounts = [
            module.Account(username="user-a", password="secret-a", name="账号A"),
            module.Account(username="user-b", password="secret-b", name="账号B"),
        ]
        delays = []

        def runner_factory(account):
            class Runner:
                async def run(self):
                    return {"success": True, "message": f"{account.name}领取成功"}

            return Runner()

        async def record_delay(seconds):
            delays.append(seconds)

        manager = module.AccountQueueManager(
            accounts,
            queue_config=module.QueueConfig(delay_between_accounts_ms=5000, max_retries=1),
            runner_factory=runner_factory,
            delay_func=record_delay,
        )
        stdout = StringIO()

        with redirect_stdout(stdout):
            results = await manager.process_all_accounts()

        self.assertEqual([result["account"] for result in results], ["账号A", "账号B"])
        self.assertEqual(delays, [5.0])
        self.assertIn("总账号数: 2", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
