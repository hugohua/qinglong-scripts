# IPZAN 金币领取脚本

用途：自动登录 `ipzan.com`，进入用户页并点击领取金币按钮。

## 脚本

`ipzan-receive-coins.py` 使用 Playwright 驱动 Chromium 完成浏览器登录流程。脚本支持单账号和多账号队列，会按配置重试失败账号，并在 QingLong 中通过 `QLAPI.systemNotify` 发送汇总通知。

脚本不会保存 Cookie，也不会把账号密码写回 `.env` 或 QingLong 环境变量。

## 运行逻辑

1. 从环境变量或本地 `.env` 读取 `IPZAN_ACCOUNTS`
2. 如果没有配置 `IPZAN_ACCOUNTS`，读取 `IPZAN_USERNAME`、`IPZAN_PASSWORD` 和可选的 `IPZAN_ACCOUNT_NAME`
3. 启动 headless Chromium
4. 打开 `https://ipzan.com/`
5. 点击首页登录按钮，填写账号、密码和页面验证码
6. 登录后进入 `https://ipzan.com/user`
7. 点击 `.user-box-body .el-button.receive-btn`
8. 捕获 `/home/userWallet-receive` 接口响应并汇总结果

## 返回规则

- 至少一个账号领取成功：退出码为 `0`
- 所有账号领取失败：退出码为 `1`
- 配置缺失、浏览器启动失败、登录失败、页面结构变化或请求失败：对应账号记为失败
- 如果按钮点击成功但未捕获到接口响应，按“按钮已点击，但未获取到API响应”记录为成功，和参考脚本行为保持一致

## 使用说明

### 环境要求

- Python 3.9 或更高版本
- Python 依赖：

```bash
python3 -m pip install -r requirements.txt
```

脚本需要 Chromium 浏览器。当前 QingLong 容器的 Linux 依赖里已经安装了 `chromium`，容器内实际路径是：

```bash
IPZAN_BROWSER_EXECUTABLE_PATH=/usr/bin/chromium
```

这种情况下不需要再执行 `python3 -m playwright install chromium`。如果容器里没有系统 Chromium，再用 Playwright 安装自带浏览器。

脚本也兼容参考 Node 脚本使用的 `PUPPETEER_EXECUTABLE_PATH`。

### 本地运行

1. 复制配置模板：

```bash
cp .env.example .env
```

2. 配置单账号：

```dotenv
IPZAN_USERNAME=这里替换成你的账号
IPZAN_PASSWORD=这里替换成你的密码
IPZAN_ACCOUNT_NAME=账号1
```

或配置多账号：

```dotenv
IPZAN_ACCOUNTS=[{"username":"账号1用户名","password":"账号1密码","name":"账号1"},{"username":"账号2用户名","password":"账号2密码","name":"账号2"}]
```

3. 执行脚本：

```bash
python3 ipzan-receive-coins.py
```

### QingLong 运行

1. 将 `ipzan-receive-coins.py` 和 `requirements.txt` 上传到 QingLong 脚本目录
2. 安装依赖：

```bash
python3 -m pip install --no-cache-dir \
  -i https://pypi.tuna.tsinghua.edu.cn/simple \
  -r requirements.txt
```

3. 确认 Chromium 路径：

当前 NAS 上的 QingLong 容器已经通过 Linux 依赖安装了 `chromium`，已验证 Playwright 可以用这个路径启动：

```bash
IPZAN_BROWSER_EXECUTABLE_PATH=/usr/bin/chromium
```

如果换了镜像或容器，可以在 QingLong 终端里确认路径：

```bash
which chromium
which chromium-browser
ls -l /usr/bin/chromium*
```

只有在容器里没有系统 Chromium 时，才需要安装 Playwright 自带浏览器：

```bash
python3 -m playwright install chromium
```

4. 在 QingLong 环境变量中新增：

```bash
IPZAN_USERNAME=这里替换成你的账号
IPZAN_PASSWORD=这里替换成你的密码
IPZAN_ACCOUNT_NAME=账号1
```

多账号时改用：

```bash
IPZAN_ACCOUNTS=[{"username":"账号1用户名","password":"账号1密码","name":"账号1"},{"username":"账号2用户名","password":"账号2密码","name":"账号2"}]
```

5. 可选队列配置：

```bash
IPZAN_DELAY_BETWEEN_ACCOUNTS_MS=5000
IPZAN_MAX_RETRIES=3
IPZAN_TIMEOUT_MS=30000
IPZAN_HEADLESS=true
IPZAN_BROWSER_EXECUTABLE_PATH=/usr/bin/chromium
```

6. 新建任务：

```bash
python3 /ql/data/scripts/ipzan-receive-coins.py
```

脚本在 QingLong 中运行时，只依赖可选的 `QLAPI.systemNotify` 发送汇总通知。如果 `QLAPI` 不存在，本地运行和普通容器运行不会因此失败。

## 开发与测试

运行 IPZAN 脚本测试：

```bash
python3 -m unittest tests/test_ipzan_receive_coins_py.py
```

当前测试覆盖：

- JSON 多账号配置解析
- 单账号环境变量回退
- 领取接口响应归一化
- 未捕获接口响应时的按钮点击成功结果
- 队列重试和账号间延迟
- QingLong 通知汇总内容
