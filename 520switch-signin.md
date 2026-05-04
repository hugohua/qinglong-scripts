# 520switch 签到脚本

用途：自动执行 `www.520switch.com` 的每日签到。

## 脚本

`520switch-signin.py` 会优先使用缓存的 `SWITCH520_COOKIE` 签到；如果 Cookie 缺失或失效，会用账号密码登录，自动获取验证码图片并用 `ddddocr` 识别，登录成功后刷新 Cookie，再继续签到。

## 运行逻辑

1. 读取环境变量或本地 `.env` 中的 `SWITCH520_COOKIE`
2. 如果 Cookie 可用，直接请求页面提取 `zb.ajax_nonce` 并调用签到接口
3. 如果 Cookie 缺失或失效，读取 `SWITCH520_USERNAME` 和 `SWITCH520_PASSWORD`
4. 请求登录页，从 `var zb = {...}` 中提取 `ajax_nonce` 和 `ajax_url`
5. 调用 `zb_get_captcha_img` 获取验证码图片 data URL
6. 使用 `ddddocr` 识别验证码，统一转成大写后提交登录
7. 登录成功后，在 QingLong 中通过 `QLAPI` 更新或创建 `SWITCH520_COOKIE`
8. 使用同一个会话调用签到接口

## 返回规则

- 签到成功：输出站点返回消息，退出码为 `0`
- 今天已经签到：输出站点返回消息，退出码为 `0`
- 配置缺失、登录失败、验证码识别失败、页面结构变化或请求失败：输出错误信息，退出码为 `1`
- 在 QingLong 中如果可用 `QLAPI.systemNotify`，会对“签到成功 / 今日已签到 / 执行失败”三种结果发送系统通知

## 使用说明

### 环境要求

- Python 3.9 或更高版本
- Python 依赖：

```bash
python3 -m pip install -r requirements.txt
```

国内网络环境建议使用 PyPI 镜像：

```bash
python3 -m pip install --no-cache-dir \
  -i https://pypi.tuna.tsinghua.edu.cn/simple \
  -r requirements.txt
```

### 本地运行

1. 复制配置模板：

```bash
cp .env.example .env
```

2. 编辑 `.env`，至少填入账号和密码：

```dotenv
SWITCH520_COOKIE=
SWITCH520_USERNAME=这里替换成你的账号
SWITCH520_PASSWORD=这里替换成你的密码
```

3. 执行脚本：

```bash
python3 520switch-signin.py
```

本地运行不会回写 `.env`。如果登录刷新了 Cookie，脚本只会在当前会话中继续签到。

### QingLong 运行

1. 将 `520switch-signin.py` 和 `requirements.txt` 上传到 QingLong 脚本目录
2. 确认 QingLong 使用 Debian 镜像
3. 安装 Python 依赖：

```bash
python3 -m pip install --no-cache-dir \
  -i https://pypi.tuna.tsinghua.edu.cn/simple \
  -r requirements.txt
```

4. 在 QingLong 环境变量中新增：

```bash
SWITCH520_USERNAME=这里替换成你的账号
SWITCH520_PASSWORD=这里替换成你的密码
SWITCH520_COOKIE=可留空，登录成功后会自动更新
```

5. 新建任务：

```bash
python3 /ql/data/scripts/520switch-signin.py
```

`ddddocr` 依赖 `onnxruntime`。QingLong 默认 `latest` 镜像通常基于 Alpine/musl，安装 `onnxruntime` 容易失败。建议使用：

```bash
docker pull whyour/qinglong:debian
```

如果使用 `docker compose`，建议将镜像设置为：

```yaml
image: whyour/qinglong:debian
```

脚本在 QingLong 中运行时，会调用内置 `QLAPI`：

- `getEnvs` / `updateEnv` / `createEnv`：刷新 `SWITCH520_COOKIE`
- `systemNotify`：发送签到成功、今日已签到或失败通知

不要提交浏览器导出的 HAR、`.env` 或任何明文账号密码。HAR 文件可能包含登录请求、验证码和敏感字段，仓库已通过 `.gitignore` 忽略 `*.har`。

## 开发与测试

运行 Python 测试：

```bash
python3 -m unittest tests/test_520switch_signin_py.py
```

当前测试覆盖：

- 页面中提取 `ajax_nonce`
- 解析验证码 data URL 并统一 OCR 结果大小写
- Cookie 可用时直接签到
- Cookie 失效时登录、刷新 Cookie、再签到
- 成功签到结果判定
- 已签到结果判定
- 异常返回处理
- QingLong 系统通知标题和内容映射
