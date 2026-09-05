# Part 01 验收与接入兼容性记录

验收日期：2026-09-06。状态：本地工程和用户真实接入验收通过；本次提交的远程 CI 以 GitHub Actions 运行结果为准。

本记录区分代理执行的离线检查与用户手动执行的真实调用。没有为补记录重复发起付费请求，没有新增 TTS/ASR 离线测试。

## 交付内容

- API、健康检查、配置和启动日志：`src/backend/api.py`、`config.py`、`log.py`。
- Worker 初始化入口：`src/backend/worker.py`，尚不承担 Part 03 的任务处理。
- 真实探针：`src/backend/probes/`。
- 发音修正：`src/backend/tts_terms.py`，仅用于朗读输入。
- 环境与检查：`pyproject.toml`、`uv.lock`、`.python-version`、`.env.example`、`tests/`。
- 复现说明：`README.md`；CI：仓库根目录 `.github/workflows/backend-ci.yml`。

## 工程检查：代理实际执行

环境：Windows、Python 3.12.13、uv 0.11.21。精确依赖以本提交的 `uv.lock` 为准；主要依赖为 FastAPI 0.141.1、Pydantic 2.13.5、pydantic-settings 2.15.0、HTTPX 0.28.1、websockets 17.1。

在原开发环境和新建独立虚拟环境中均得到：

| 检查 | 结果 |
|---|---|
| Ruff lint | 通过 |
| Ruff 格式检查 | 17 个文件通过；收尾仅整理格式 |
| mypy | 12 个源码文件通过 |
| pytest | 13 passed，2 条第三方弃用警告 |
| Worker 开发环境启动 | 初始化并正常退出 |
| 生产配置缺失 | 抛出 RuntimeError，仅列缺失变量名 |

独立环境使用已安装的 Python 3.12.13，重新从锁文件下载、构建并安装依赖；并非重装操作系统。为避开执行账户的用户缓存权限限制，使用项目内缓存：

```powershell
# 在 backend 目录执行
$env:UV_CACHE_DIR = Join-Path (Get-Location) '.pytest_cache/uv-cache'
$env:UV_PROJECT_ENVIRONMENT = Join-Path (Get-Location) '.pytest_cache/part01-clean-env'
uv sync --locked --python .venv/Scripts/python.exe
.\.pytest_cache\part01-clean-env\Scripts\python.exe -m pytest -q --basetemp=.pytest_cache/part01-clean-tests
.\.pytest_cache\part01-clean-env\Scripts\ruff.exe check src tests
.\.pytest_cache\part01-clean-env\Scripts\ruff.exe format --check src tests
.\.pytest_cache\part01-clean-env\Scripts\mypy.exe src
```

API 健康检查和 lifespan 通过 TestClient 在独立环境执行；实际 HTTP 服务此前由用户启动并确认。测试通过临时目录与环境变量隔离本地配置，不访问付费服务。两条警告分别来自 Starlette 的 HTTPX 测试客户端兼容路径和 AnyIO BlockingPortal 别名，不影响当前通过结果。

首次提交 `f96ab3c3697771bbc9ab65f05ac069962c923df5` 的 [CI 已通过](https://github.com/ztinguser/InRoom/actions/runs/33977337714)。它不代表当前新增代码；本记录随本次代码提交，当前版本可通过包含本文件的提交及 [Actions](https://github.com/ztinguser/InRoom/actions) 对照。

## DeepSeek：用户真实执行

- 提供方：阿里云百炼，北京业务空间 OpenAI 兼容 HTTP 接口。
- 模型 ID 与返回模型：`deepseek-v4-flash`，别名并非不可变快照。
- 接入：HTTPX；Base URL 后追加 `/chat/completions`；流式协议为 SSE。
- 非流式：结构化 JSON 通过 Question 字段校验；耗时 1.40 秒；输入 50 tokens、输出 34 tokens、总计 84 tokens、缓存命中 0。
- 输出问题：async/await 在 Python 中如何实现异步编程？请解释其工作原理并给出一个简单示例。topic 为 Python。
- 流式：用户确认 `status=completed`；主动取消确认 `status=cancelled, close_seconds=0.0004`。
- 流式用量代码会读取并打印，用户未保留本次具体数值，不能据此声称实际收到完整流式用量。已验证真实非流式用量；流式尾部用量处理有离线覆盖。

## Qwen TTS：用户真实执行与试听

- 地域：北京。
- 模型：`qwen3-tts-vd-realtime-2026-01-15`。
- 已创建音色：`qwen-tts-vd-inroom-voice-20260906014032023-f829`。音色 ID 不是密钥；其他账户应按 README 创建自己的兼容音色。
- 音色创建：HTTPX 调用声音设计 HTTP 接口；合成：websockets 直连 `/api-ws/v1/realtime`，`server_commit` 模式。
- 生成音频：PCM signed 16-bit little-endian、单声道、24 kHz，添加 WAV 文件头。代理读取了真实输出文件头；`tts.wav` 为 186240 帧，即 7.76 秒，`tts-05.wav` 为 101760 帧，即 4.24 秒。
- 用户确认 WAV 可正常生成、试听可用。PostgreSQL 发音不自然，Auto 未彻底解决；仅朗读输入替换为 Postgres 后用户确认自然，模型未更换。
- 首包延迟和 TTS 用量的具体实测值未回传，不虚构指标，不影响本 Part 的基本可用性判断。

## Fun-ASR：用户真实执行

- 采用提供方：阿里云百炼，北京；模型：`fun-asr-realtime-2026-02-28`。
- 接入：websockets，`/api-ws/v1/inference`；JSON 控制事件与二进制 PCM 音频。
- 流程：run-task → task-started → 分块发送/接收 → finish-task → 最终转写 → task-finished。
- 已回传完整样例：24 kHz、PCM16、单声道；7.76 秒音频；整体耗时 10.08 秒；finish_wait_seconds=0.321；status=completed。
- 样例 task_id：`501e5dde-81e4-4423-96f5-e46e6847889b`。
- 样例转写：我看到你的简历中提到了数据库优化，请解释数据库索引的作用，以及它为什么会影响写入性能。
- 用户在三条中文技术音频验收步骤后确认“全部测试过了”，覆盖中文概念、中英文技术词、停顿与纠正；报告的问题是 TTS 术语读音，随后已采取替换。
- 其余样例逐条日志和录音来源未单独留存，本项依据用户手动验收确认，不冒充代理复跑或量化准确率评测。已展示样例来源为项目 TTS 合成音频；不声称真人、噪声或浏览器麦克风效果已验证。

## 采样率和超时基线

当前探针不做本地重采样：TTS 固定输出 24 kHz，ASR 按 WAV 文件头声明原始采样率。正式接入若需转换，责任归音频输入适配层；不得只修改采样率声明。浏览器采集侧与后端的具体格式协商在 Part 10/14 实现。

| 操作 | 当前配置 |
|---|---|
| DeepSeek | connect=10 秒，其他 HTTPX 操作等待=60 秒；没有整体 deadline |
| 创建音色 | connect=10 秒，其他操作等待=90 秒 |
| TTS | 从连接前计时，接收 deadline=60 秒，建连=10 秒，关闭=5 秒 |
| ASR | 音频时长+30 秒异步预算，建连=10 秒，关闭=5 秒 |

关闭清理可能额外耗时；这些是初始探针基线，不是服务 SLA。客户端停止接收不证明服务端停止生成或计费；TTS 首包不是实际可听时间。正式统一模型预算与取消仍属于后续 Part。

## 验收结论

- [x] 独立依赖环境可安装并执行检查；API/Worker 基础可运行；默认测试不付费。
- [x] DeepSeek 真实结构化输出与用量、流式与客户端取消通过；TTS 真实可播放输出通过；ASR 三条样例由用户确认通过。
- [x] 已记录模型、提供方、地域、音色、格式和超时基线。
- [x] 凭据保留于被忽略的本地配置，音频不提交；探针不打印密钥或 Authorization。日志脱敏的全面加固仍属 Part 11。

本结论仅针对 Part 01，允许进入 Part 02；不表示后端或正式实时语音业务已完成。后续模型接入应保留以上兼容性限制与尚未量化的指标。
