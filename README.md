# qinlong 脚本仓库

这个仓库用于存放可在本地或 QingLong 中运行的自动化脚本。

## 脚本清单

### 1. `520switch-signin.py`

- 用途：自动执行 `www.520switch.com` 的每日签到
- 文档：[520switch-signin.md](./520switch-signin.md)
- 本地运行：`python3 520switch-signin.py`
- 测试：`python3 -m unittest tests/test_520switch_signin_py.py`

### 2. `ipzan-receive-coins.py`

- 用途：自动登录 `ipzan.com` 并领取用户页金币
- 文档：[ipzan-receive-coins.md](./ipzan-receive-coins.md)
- 本地运行：`python3 ipzan-receive-coins.py`
- 测试：`python3 -m unittest tests/test_ipzan_receive_coins_py.py`

## 开发测试

运行全部 Python 测试：

```bash
python3 -m unittest discover tests
```
