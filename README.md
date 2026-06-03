# 🚀 Web2API - AI Web Interface to OpenAI API Gateway

**将各大AI聊天网页界面（如Gemini、OpenAI等）转换为兼容的OpenAI API**

Web2API是一个拟人化网页自动化中转网关，为期望将Web界面AI服务转换为标准API的开发者提供完整的解决方案。通过Playwright浏览器自动化和多账号沙盒架构，确保3天长会话的稳定运行，同时极致压低运营成本。

## 📋 版本历史

| 版本           | 日期    | 重点内容                                                                            |
| -------------- | ------- | ----------------------------------------------------------------------------------- |
| **V1.3** | 2026.06 | ✨ 12 平台支持 / Gemini Guest Mode / Web UI / Docker / SQLite 持久化 / 反自动化检测 |
| V1.2           | 2026.05 | 多账号沙盒 / 3天TTL                                                                 |
| V1.0-V1.1      | 2026.04 | 基础架构 / 有头集群 / 即用即删                                                      |

---

## 🎯 核心特性

### 1️⃣ 拟人化网页自动化 (Humanized Web Automation)

- **高斯分布随机抖动**：所有打字、鼠标移动、点击都带有数学维度的随机化
- **贝塞尔曲线平滑**：模拟人类加速/减速动作
- **偶尔输入错误纠正**：增加真实感

```python
# 例子：拟人化打字
await humanizer.humanized_type(page, "#input", "你好", delay_min=50, delay_max=200)

# 例子：拟人化点击
await humanizer.humanized_click(page, ".send-button")
```

### 2️⃣ 流量极简 (Traffic Optimization)

100%拦截与AI对话无关的资源，节约住宅代理流量：

- ✅ **拦截所有图片**：`*.png`, `*.jpg`, `*.gif`, `*.svg` 等
- ✅ **拦截样式和字体**：`*.css`, `*.woff2`, `*.ttf`
- ✅ **拦截第三方埋点**：`*analytics*`, `*sentry*`, `*mixpanel*` 等

**流量节省效果**：单次对话从 ~3-5MB → ~300KB

### 3️⃣ 多账号沙盒 (Multi-Account Sandbox)

- 每个账号独立的浏览器Context（完全隔离Cookie/Session）
- 最多5个常驻Worker，动态热启动
- 10分钟无请求自动Kill，释放内存

### 4️⃣ 官方配额动态感知 (Official Rate Limit Awareness)

SQLite 滑动窗口精准计数：

- 实时监听官方3小时内的请求限制（如40次/3h）
- 达到38次时自动冷却，智能负载均衡到其他账号
- 流式检测 `Rate Limit` 错误，立即降级状态

### 5️⃣ 长会话内存熔断 (Memory Circuit Breaker)

- 当单条对话交互超过40轮 **或** 进程内存超过1.5GB时触发
- 物理删除该对话，刷新SQLite映射
- 下次客户端再用该ID时，无感重建新对话

### 6️⃣ 异步URL捕获 (Async URL Capturing)

核心创新：首轮对话的流式完成后，Worker强制原地等待1-2秒，拦截并提取跳转后的最新URL：

```
用户消息 → Gemini流式返回 → [DONE] → 等待URL加载 → 提取 /c/uuid-8888 → 存库
```

### 7️⃣ Web UI 管理面板 (Dashboard)

内置暗色主题监控面板，访问 `http://localhost:8000/` 即可打开：

- **实时统计卡片**：Worker 数量、Account 状态、会话数、内存用量、池容量
- **账号池管理**：查看每个账号的状态、3h 配额用量条、冷却倒计时，支持一键 Reset / Force Cooldown
- **浏览器 Worker 监控**：Worker 状态、内存占用、PID 信息
- **会话列表**：所有活跃会话的 ID、绑定账号、Web URL、交互次数、TTL 剩余时间
- **Quick Chat 测试**：选择账号直接发送测试消息，查看 JSON 响应
- **Activity Log**：实时事件日志流
- **自动刷新**：可配置 2-60 秒轮询间隔，支持开关

### 8️⃣ Gemini Guest Mode (免登录)

经 2025年6月验证，**Gemini 在未登录状态下可正常使用**。系统自动检测 Guest Mode，无需 Google 账号认证即可通过 API 发送消息并接收回复。首次加载时使用 "撰写" 卡片按钮创建新对话。

### 9️⃣ 多平台支持 (12 Platforms)

| 平台                   | 免登录 | 已验证       | Model 映射                |
| ---------------------- | ------ | ------------ | ------------------------- |
| **Gemini**       | ✅     | ✅ 可用      | `gemini-*`              |
| **ChatGPT**      | ❌     | 选择器就绪   | `gpt-*`, `o1`, `o3` |
| **Claude**       | ❌     | 选择器就绪   | `claude-*`              |
| **DeepSeek**     | ❌     | 选择器就绪   | `deepseek-*`            |
| **Kimi**         | ❌     | 选择器已验证 | `kimi-*`, `moonshot`  |
| **Qwen 千问**    | ❌     | 选择器就绪   | `qwen-*`, `tongyi`    |
| **Doubao 豆包**  | ✅     | 选择器已验证 | `doubao`, `豆包`      |
| **GLM 智谱清言** | ❌     | 选择器就绪   | `glm-*`, `chatglm`    |
| **Copilot**      | ✅     | CAPTCHA 限制 | `copilot`, `bing`     |
| **Yuanbao 元宝** | ✅     | 选择器就绪   | `yuanbao`, `元宝`     |
| **Perplexity**   | ✅     | 选择器就绪   | `perplexity`            |
| **Grok**         | ❌     | 选择器就绪   | `grok-*`, `xai`       |

> **注意**：仅 Gemini 的 Guest Mode 经过完整测试验证。其他免登录平台（Copilot/Doubao）可能触发 CAPTCHA。

### 9️⃣ 反自动化检测 (Stealth)

通过 `context.add_init_script()` 在所有页面脚本之前注入反检测代码，覆盖 Playwright 暴露的自动化指纹：

| 指纹                      | 修复前      | 修复后             |
| ------------------------- | ----------- | ------------------ |
| `navigator.webdriver`   | `true`    | `false`          |
| `window.chrome.runtime` | 缺失        | 存在               |
| `navigator.plugins`     | 0           | 3                  |
| WebGL renderer            | SwiftShader | Intel Iris         |
| `navigator.languages`   | 可能为空    | `["zh-CN","zh"]` |

配合 Chrome 启动参数 `--disable-blink-features=AutomationControlled`，从引擎层面阻断自动化标记。

> **关于 `isTrusted`**：Playwright 的 `page.mouse.click()` 通过 CDP `Input.dispatchMouseEvent` 生成事件，在浏览器输入层产生，`isTrusted` 为 `true`，与真实用户点击无异。

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────┐
│        客户端 (ChatGPT Web / App)       │
└────────────────┬────────────────────────┘
                 │ HTTP/OpenAI API
                 ▼
┌─────────────────────────────────────────┐
│   Web2API Gateway (FastAPI)             │
│  ├─ API路由 & 会话映射                  │
│  ├─ 配额计数器 (Rate Limit Engine)      │
│  └─ 会话生命周期管理                    │
└────────┬────────────────┬───────────────┘
         │ 获取Worker     │ 查询配额
         ▼                 ▼
    ┌──────────┐    ┌──────────────┐
    │Browser   │    │ SQLite       │
    │Pool      │    │ Quota +      │
    │(5个Worker)   │    │ Session DB   │
    └────┬─────┘    └──────────────┘
         │
   ┌─────┴─────────────────┬────────────────┐
   ▼                       ▼                ▼
[Worker1]          [Worker2]        [Worker3...]
[Chrome] ────────► [Gemini.google.com]
[Playwright]       [Traffic Blocking]
[Flow Interception] [Humanized Typing]
                   [Memory Monitoring]
```

---

## 🔧 技术栈

| 组件                 | 技术                      | 说明                                          |
| -------------------- | ------------------------- | --------------------------------------------- |
| **网关层**     | FastAPI                   | 异步HTTP服务                                  |
| **浏览器**     | Playwright + Chromium     | 浏览器自动化 (支持系统Chrome, Stealth反检测)  |
| **数据存储**   | SQLite                    | 配额计数 + 会话映射 + 账号池 + Cookie持久化   |
| **日志**       | Loguru                    | 结构化日志                                    |

---

## 📦 安装与运行

### 前置条件

- Python >= 3.10
- 系统已安装的 Chrome 浏览器（推荐）或通过 `playwright install chromium` 安装
- Docker（可选，用于容器化部署）

### 安装

```bash
# 1. 克隆或下载项目
cd web2api

# 2. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. 安装依赖
pip install -e .

# 4. 下载Playwright浏览器驱动
playwright install chromium

# 5. 配置环境变量
cp .env.example .env
# 编辑 .env 填入配置信息
```

### 运行

### Docker 部署

```bash
# 一键启动
docker-compose up -d

# 访问 Dashboard
# http://localhost:8088/

# 查看日志
docker-compose logs -f web2api

# 停止
docker-compose down
```

# 启动后访问 Dashboard

http://localhost:8000/

```

## 🔌 API 文档

### 端点总览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | **Web UI 管理面板** |
| GET | `/health` | 健康检查 |
| POST | `/v1/chat/completions` | OpenAI 兼容接口 (stream + model 自动映射平台) |
| POST | `/api/v1/message` | 原生消息接口 (支持 `platform` 参数) |
| GET | `/v1/models` | 模型列表 (51 个模型, 自动映射到平台) |
| GET | `/api/v1/platforms` | 支持平台列表及元数据 |
| GET | `/api/v1/stats` | 网关统计信息 |
| GET | `/api/v1/admin/accounts` | 账号池状态 (按平台分组) |
| POST | `/api/v1/admin/accounts/add` | 添加账号 (支持 platform 参数) |
| POST | `/api/v1/admin/accounts/batch-add` | 批量添加账号 |
| POST | `/api/v1/admin/accounts/{id}/cooldown` | 强制账号冷却 |
| GET | `/api/v1/admin/quota/status` | 所有账号配额状态 |
| POST | `/api/v1/admin/quota/reset/{id}` | 重置账号配额 |
| GET | `/api/v1/admin/sessions` | 列出所有会话 |
| POST | `/api/v1/admin/workers/{id}/kill` | 终止指定 Worker |

### 1. Native Web2API接口

#### 创建新会话并发送消息

```bash
curl -X POST http://localhost:8000/api/v1/message \
  -H "Content-Type: application/json" \
  -d '{
    "conversation_id": null,  # 新建会话
    "message": "你好，请介绍一下你自己",
    "account_id": "account_01"
  }'
```

**响应：**

```json
{
  "status": "success",
  "conversation_id": "local_752f720d",
  "response": "1 + 1 = 2",
  "interaction_count": 1,
  "quota_info": {},
  "metadata": {
    "worker_id": "worker_1",
    "account_id": "account_03",
    "memory_mb": 74.3,
    "timestamp": "2026-06-03T13:00:37.208834"
  }
}
```

> **注意**：Gemini 支持 Guest Mode，无需登录即可使用。首次加载时 "发起新对话" 按钮为 disabled，系统自动使用 "撰写" 按钮创建新对话。

#### 继续已有会话

```bash
curl -X POST http://localhost:8000/api/v1/message \
  -H "Content-Type: application/json" \
  -d '{
    "conversation_id": "uuid-1234-5678",  # 使用已有会话
    "message": "继续上个话题",
    "account_id": "account_01"
  }'
```

### 2. OpenAI兼容接口

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-2.0-flash",
    "messages": [
      {"role": "user", "content": "你好"}
    ]
  }'
```

#### SSE 流式响应

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-2.0-flash",
    "messages": [{"role": "user", "content": "你好"}],
    "stream": true
  }'
```

流式响应格式：

```
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","model":"gemini-2.0-flash","choices":[{"index":0,"delta":{"content":"你"},"finish_reason":null}]}
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","model":"gemini-2.0-flash","choices":[{"index":0,"delta":{"content":"好"},"finish_reason":null}]}
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","model":"gemini-2.0-flash","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}
data: [DONE]
```

**响应：**

```json
{
  "id": "chatcmpl-local_e229f7f0",
  "object": "chat.completion",
  "created": 1780462878,
  "model": "gemini-2.0-flash",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "The capital of France is Paris."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 1,
    "completion_tokens": 6,
    "total_tokens": 7
  }
}
```

### 3. 管理接口

#### 查看配额状态

```bash
curl http://localhost:8000/api/v1/admin/quota/status
```

#### 重置账号配额

```bash
curl -X POST http://localhost:8000/api/v1/admin/quota/reset/account_01
```

#### 获取网关统计

```bash
curl http://localhost:8000/api/v1/stats
```

---

## 📊 监控与调试

### 日志输出示例

```
2026-06-03 10:00:01 | INFO | 🚀 Initializing Gemini at https://gemini.google.com
2026-06-03 10:00:02 | DEBUG | 📝 Typing: 你好，请介绍一下你自己...
2026-06-03 10:00:03 | DEBUG | 💬 Sending message...
2026-06-03 10:00:05 | INFO | ✅ Message sent, awaiting response...
2026-06-03 10:00:08 | INFO | ✅ Response received (1234 chars)
2026-06-03 10:00:09 | DEBUG | 📍 Captured conversation URL: c/1234567890abcdef
2026-06-03 10:00:09 | INFO | ✅ Message handled successfully for uuid-1234-5678
```

### 管理面板

打开 `http://localhost:8000/` 即可访问内置 Web UI 管理面板，实时查看：

- 账号状态、Worker 信息、活跃会话列表
- 内存用量、配额进度条
- 一键重置配额 / 强制冷却
- 内置 Quick Chat 测试功能

### API 统计接口

打开 `http://localhost:8000/api/v1/stats` 查看实时状态：

```json
{
  "status": "ok",
  "data": {
    "browser_pool": {
      "total_workers": 3,
      "idle_workers": 2,
      "busy_workers": 1,
      "cooldown_workers": 0,
      "total_memory_mb": 425.3,
      "max_workers": 5,
      "pool_usage": "3/5"
    },
    "timestamp": "2026-06-03T10:00:00"
  }
}
```

---

## 🛡️ 错误处理

### 常见错误码

| 状态码 | 含义         | 错误类型            | 解决方案                     |
| ------ | ------------ | ------------------- | ---------------------------- |
| 200    | 成功         | -                   | ✅                           |
| 400    | 内容被拦截   | `content_blocked` | 检查输入内容是否违反安全策略 |
| 429    | 配额限制     | `rate_limit`      | 等待冷却 (90min) 或切换账号  |
| 503    | 账号被封禁   | `banned`          | 联系管理员重置该账号         |
| 503    | 需要验证码   | `captcha`         | 等待冷却 (30min) 后重试      |
| 503    | 需要登录     | `login_required`  | 配置登录态 Cookie            |
| 503    | 服务维护中   | `maintenance`     | 等待恢复                     |
| 503    | 无可用Worker | -                   | 增加 MAX_WORKERS 或等待      |
| 500    | 内部错误     | `unknown`         | 查看日志                     |

**错误响应格式**：

```json
{
  "detail": "Rate limit exceeded",
  "error_type": "rate_limit",
  "account_id": "account_01"
}
```

**账号自动状态联动**：

| 错误类型            | 账号操作           | Worker 操作 |
| ------------------- | ------------------ | ----------- |
| `rate_limit`      | cooldown 90min     | release     |
| `banned`          | maintenance (永久) | kill        |
| `captcha`         | cooldown 30min     | release     |
| `login_required`  | maintenance (永久) | release     |
| `content_blocked` | cooldown 10min     | release     |

### 内存熔断触发

当会话被标记为 `MEMORY_BLOWN` 时：

```json
{
  "status": "success",
  "conversation_id": "uuid-xxxxx",
  "response": "最后一条回复...\n\n[Note: Session reset due to memory limit]",
  "interaction_count": 41
}
```

**客户端应该**：

- 使用新的 `conversation_id=null` 创建新会话
- 或向用户提示"由于内存限制已重置此对话"

---

## 🔐 安全注意事项

⚠️ **生产部署建议**：

1. **认证**：在API前加API Gateway（如Kong、Tyk）进行认证
2. **限流**：在代理层实施全局限流
3. **HTTPS**：生产环境必须用TLS加密
4. **账号隔离**：不同租户使用不同的account_id
5. **日志脱敏**：避免记录敏感信息（如Cookie、Token）

### 示例：API Key认证

```python
# 在 web2api/api/routes.py 中添加
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")

@app.post("/api/v1/message")
async def send_message(req: MessageRequest, api_key: str = Depends(api_key_header)):
    # 验证api_key
    if not verify_api_key(api_key):
        raise HTTPException(status_code=401, detail="Unauthorized")
    # ... 后续逻辑
```

---

## 🧪 测试

### 快速测试脚本

```python
import asyncio
import httpx

async def test_api():
    async with httpx.AsyncClient() as client:
        # 测试新会话
        response = await client.post(
            "http://localhost:8000/api/v1/message",
            json={
                "conversation_id": None,
                "message": "1+1等于几？",
                "account_id": "account_01"
            }
        )
        print(response.json())

asyncio.run(test_api())
```

## 🤝 贡献与反馈

本项目欢迎贡献！如有问题或建议：

1. 提交Issue描述问题
2. Fork项目并创建Pull Request
3. 遵循现有代码风格（Black + Ruff）

---

## 📄 许可证

MIT License - 见 [LICENSE](LICENSE) 文件

---

## 🙏 致谢

感谢以下开源项目的支持：

- [Playwright](https://playwright.dev) - 浏览器自动化
- [FastAPI](https://fastapi.tiangolo.com) - 现代Web框架
- [Loguru](https://github.com/Delgan/loguru) - 结构化日志

---

## ⚠️ 已知限制

| 限制                | 说明                                                    | 解决方法                                |
| ------------------- | ------------------------------------------------------- | --------------------------------------- |
| 多轮对话            | 每次请求新建独立对话，未实现 conversation_id 跨请求关联 | 需配合 conversation_id 映射表实现       |
| SSE 流式            | 当前为模拟分块发送，非真正的 Gemini 流式转发            | 需改进 DOM 监听器实时捕获增量文本       |
| Chrome 路径         | 硬编码 Windows Chrome 路径                              | 生产环境需配置 `CHROME_PATH` 环境变量 |
| Guest Mode 速率限制 | 未登录状态有官方速率限制                                | 生产环境建议配置登录态 Cookie           |

---
