# InRoom 后端

当前包含 FastAPI 基础服务、Worker 入口，以及 DeepSeek、Qwen TTS 和 Fun-ASR 接入探针。尚未实现面试业务、数据库和后台任务处理。

## 安装与配置

开发基线：Python 3.12.13、uv 0.11.21、Git。Python 版本固定在 `.python-version`，依赖版本固定在 `uv.lock`。

从 InRoom 仓库根目录执行：

```powershell
cd backend
uv python install
uv sync --locked
```

下文所有命令均在 `backend` 目录执行。首次配置时创建 `.env`；已有文件时保留原配置：

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

修改 `.env` 后手动重启程序。配置读取依赖当前工作目录，不要直接从仓库根目录启动后端命令。

| 变量 | 用途 |
|---|---|
| APP_ENV | development、test 或 production，默认 development |
| LOG_LEVEL | DEBUG、INFO、WARNING、ERROR、CRITICAL，默认 INFO |
| DEEPSEEK_API_KEY | 当前 DeepSeek 接入提供方的密钥；目前通过百炼调用 |
| DEEPSEEK_MODEL | 默认 deepseek-v4-flash |
| DEEPSEEK_URL | 聊天接口 Base URL，不包含末尾斜杠或 /chat/completions |
| DASHSCOPE_API_KEY | 北京地域百炼密钥，需要有对应语音模型的访问权限 |
| QWEN_TTS_MODEL | 默认 qwen3-tts-vd-realtime-2026-01-15 |
| QWEN_TTS_VOICE | 为上述模型创建的专属音色 ID |
| ASR_MODEL | 默认 fun-asr-realtime-2026-02-28 |

当前聊天 Base URL 的形状是 `https://<业务空间ID>.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`，使用控制台提供的实际地址。探针自行追加 `/chat/completions`。

默认开发环境可以不配置云服务凭据，启动健康接口和 Worker 入口。生产环境启动 API 或 Worker 时，检查 `DEEPSEEK_API_KEY`、`DEEPSEEK_URL`、`DASHSCOPE_API_KEY`、`QWEN_TTS_VOICE`，缺失时明确报错，不自动切换为 Mock。配置存在不代表凭据有效，服务可用性需通过真实探针验证。

`.env`、虚拟环境和 `probe-output/` 不提交到 Git；`.env.example` 仅保留无秘密的配置示例。

## 启动

API：

```powershell
uv run uvicorn backend.api:app --reload
```

- [健康检查](http://127.0.0.1:8000/health)：只检查应用是否能响应。
- [接口文档](http://127.0.0.1:8000/docs)。

`--reload` 仅用于开发。生产启动不带此参数；正式部署方案在后续阶段完成。

Worker：

```powershell
uv run inroom-worker
```

当前 Worker 完成配置检查和日志初始化后正常退出，尚无任务领取循环。

## 代码检查

```powershell
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
uv run pytest -q
```

整理格式会修改源码排版：

```powershell
uv run ruff format src tests
```

默认测试不访问真实付费 API。现有测试覆盖基础 API、配置读取、DeepSeek 结构化输出和流式探针；TTS、音色设计和 ASR 使用手动真实验证，尚无对应离线测试。

GitHub Actions 配置位于仓库根目录 `.github/workflows/backend-ci.yml`，在 `backend` 工作目录内安装锁定依赖并运行四项检查。一次旧提交的 CI 成功不代表后续未提交代码已通过。

## 真实接入探针

以下命令会访问云服务，可能产生费用，不属于默认测试。使用合成或获准使用的测试音频，不上传无授权的个人录音。

### DeepSeek

结构化输出：

```powershell
uv run python -m backend.probes.deepseek
```

流式输出与主动取消：

```powershell
uv run python -m backend.probes.deepseek_stream
uv run python -m backend.probes.deepseek_stream --cancel
```

取消模式在第 10 个正文片段后关闭流；如果响应提前完成，可能得到 completed，应以实际状态为准。用量缺失显示为 None，不代表零消耗。模型名是提供方别名，需在验收记录中保留调用日期和返回的模型信息。

### 创建 Qwen 专属音色

```powershell
uv run python -m backend.probes.qwen_voice_design
```

输出预览音频 `probe-output/voice-preview.wav`。试听后，将返回的 `voice` 填入 `.env` 的 `QWEN_TTS_VOICE`。

创建时的 `target_model` 必须与合成模型一致。音色可重复使用，每次执行该命令都会请求创建音色，不要为了试听重复创建。

### Qwen 实时 TTS

```powershell
uv run python -m backend.probes.qwen_tts
```

当前输出为 `probe-output/tts-05.wav`，具体路径以终端 `audio=` 为准。合成文本和输出文件名目前写在探针代码中，未提供命令行参数。试听确认内容完整、发音可理解、没有异常变速。

中英文混读使用 `language_type=Auto`。`src/backend/tts_terms.py` 保存已试听确认的术语替换，目前为 `PostgreSQL → Postgres`。替换只用于 TTS 输入；后续页面、全文记录和报告证据应保留原文。

### Fun-ASR

先生成上述 TTS 文件，再执行：

```powershell
uv run python -m backend.probes.fun_asr probe-output/tts-05.wav
```

最后一个参数可替换为其他实际存在的音频文件。探针按约 100 毫秒分块、以接近实时的速度发送音频，同时输出 partial 和 final；只拼接 final。发送 `finish-task` 后继续接收，直到 `task-finished`。

Part 01 要求至少三条中文技术音频，覆盖中文概念、中英文技术词、停顿与自我纠正。将最终转写与实际音频对照；status=completed 只证明任务正常结束，不证明转写准确。TTS 合成音频可用于协议验证，不能代替真人录音的识别质量评估。

## 音频与超时约定

- TTS：北京地域，24 kHz、单声道、16 位小端 PCM。探针添加 WAV 文件头后保存，没有重采样。
- ASR：北京地域，读取单声道、16 位 PCM WAV，发送原始 PCM，按文件头传入真实采样率；24 kHz 样例已由用户实测。探针不进行本地重采样，提供方内部如何处理采样率未做验证。
- 后续若前后端协商统一采样率，由音频输入适配层承担实际转换；不能只修改文件头或声明值。这一正式分工尚待 Part 10/14 落实。
- 探针音频是本地合成/测试产物，不表示产品会持久化用户录音。

| 探针 | 当前超时配置 |
|---|---|
| DeepSeek 普通/流式 | 连接等待 10 秒，读取等操作等待 60 秒；尚无整体 deadline |
| 音色创建 | 连接等待 10 秒，读取等操作等待 90 秒；尚无整体 deadline |
| 实时 TTS | 接收截止时间为调用开始后 60 秒；建连 10 秒，关闭握手 5 秒 |
| ASR | 异步操作预算为音频时长加 30 秒；建连 10 秒，关闭握手 5 秒 |

这些是探针基线，不是服务性能承诺；退出清理可能增加耗时。正式模型调用仍需统一预算和取消机制。

## 指标与验收边界

- DeepSeek 首文本时间：请求开始至首段非空正文到达。
- TTS 首音频时间：连接前开始计时，包含建连、配置和合成；不等于浏览器实际可听时间。
- ASR 整体耗时包含实时发送音频的时间；finish_wait_seconds 测量发送结束指令前到收到 task-finished 的收尾过程。
- 客户端关闭流不证明提供方立即停止生成或停止计费。
- 单次成功不代表长期稳定性、并发能力或内容质量全部通过。

Part 01 的真实调用结果、音色与环境、样例来源、检查结果及已知限制见 [验收与兼容性记录](docs/part-01.md)。README 用于说明运行方法，不替代验收记录。
