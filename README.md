# qinlong 脚本仓库

这个仓库用于存放可在本地或 QingLong 中运行的自动化脚本。

## 脚本清单

### 1. `520switch-signin.js`

用途：自动执行 `www.520switch.com` 的每日签到。

运行逻辑：

1. 优先读取环境变量 `SWITCH520_COOKIE`
2. 如果环境变量中没有 `SWITCH520_COOKIE`，则尝试读取本地 `.env`
3. 请求站点首页，提取当前页面里的 `zb.ajax_nonce`
4. 调用签到接口完成签到

返回规则：

- 签到成功：输出站点返回消息，退出码为 `0`
- 今天已经签到：输出站点返回消息，退出码为 `0`
- 配置缺失、Cookie 失效、页面结构变化或请求失败：输出错误信息，退出码为 `1`
- 在 QingLong 中如果可用 `QLAPI.systemNotify`，会对“签到成功 / 今日已签到 / 执行失败”三种结果发送系统通知

## 使用说明

### 环境要求

- Node.js 18 或更高版本

### 本地运行

1. 复制配置模板：

```bash
cp .env.example .env
```

2. 编辑 `.env`，填入浏览器登录后的 Cookie：

```dotenv
SWITCH520_COOKIE=这里替换成你的完整Cookie
```

3. 执行脚本：

```bash
node 520switch-signin.js
```

或者：

```bash
npm start
```

### QingLong 运行

1. 将脚本上传到 QingLong 脚本目录
2. 在 QingLong 环境变量中新增：

```bash
SWITCH520_COOKIE=这里替换成你的完整Cookie
```

3. 新建任务，命令可以使用：

```bash
task /ql/data/scripts/520switch-signin.js
```

如果你的 QingLong 环境没有给 `.js` 文件配置 `task` 直接执行，也可以用：

```bash
node /ql/data/scripts/520switch-signin.js
```

脚本在 QingLong 中运行时，会调用内置 `QLAPI.systemNotify` 发送通知：

- 标题：`520switch 签到成功`
- 标题：`520switch 今日已签到`
- 标题：`520switch 签到失败`

通知内容使用脚本实际运行返回的消息或错误信息。

## 开发与测试

运行测试：

```bash
npm test
```

当前测试覆盖：

- 页面中提取 `ajax_nonce`
- 成功签到结果判定
- 已签到结果判定
- 异常返回处理
