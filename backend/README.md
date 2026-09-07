# InRoom 后端

当前包含 FastAPI 服务、数据库模型与事务基础、身份及准备工作区接口、Worker 入口，以及 DeepSeek、Qwen TTS 和 Fun-ASR 接入探针。Part 02 本地验收已通过，见 [验收记录](docs/part-02.md)；面试业务和后台任务处理尚未实现。

## 代码组织

`src/backend/api.py` 只负责组装应用，`worker.py` 是 Worker 入口。其余代码按职责分包：

- `core/`：配置、日志、应用异常、HTTP 配置及资源生命周期。
- `db/`：表模型、请求级数据库事务。
- `auth/`：身份依赖、登录业务及登录路由。
- `preparations/`：工作区请求结构、数据库操作及路由。
- `probes/`：独立接入探针及当前探针使用的发音替换。

路由处理 HTTP，数据库事务由 `db/session.py` 统一提交或回滚。新增功能放入所属业务包，不继续堆入入口文件。

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
| DATABASE_URL | PostgreSQL 连接地址，使用 postgresql+psycopg 驱动 |
| APP_ORIGIN | 应用同源地址，本地为 http://127.0.0.1:8000 |
| SESSION_SECRET | API 必填的 Cookie 签名密钥 |
| OIDC_ISSUER | OIDC 身份提供方 issuer |
| OIDC_CLIENT_ID | 身份提供方中的客户端 ID |
| OIDC_CLIENT_SECRET | 身份提供方中的客户端密钥 |
| LOGIN_MAX_AGE | 登录有效期秒数，默认 28800 |
| DEV_IDENTITY_ENABLED | 默认 false；设置 true 会拒绝启动，本项目只使用 OIDC 身份 |

当前聊天 Base URL 的形状是 `https://<业务空间ID>.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`，使用控制台提供的实际地址。探针自行追加 `/chat/completions`。

默认开发环境可以不配置云服务凭据，启动健康接口和 Worker 入口。生产环境启动 API 或 Worker 时，检查 `DEEPSEEK_API_KEY`、`DEEPSEEK_URL`、`DASHSCOPE_API_KEY`、`QWEN_TTS_VOICE`，缺失时明确报错，不自动切换为 Mock。配置存在不代表凭据有效，服务可用性需通过真实探针验证。

API 现在还要求设置 `SESSION_SECRET`。可用 `uv run python -c "import secrets; print(secrets.token_urlsafe(32))"` 生成并保存到本地 `.env`。生产 API 还要求 HTTPS 的 `APP_ORIGIN`、`OIDC_ISSUER` 以及 `OIDC_CLIENT_SECRET`。健康检查不连接数据库；使用身份和工作区接口前需要完成迁移及 OIDC 配置。

## 数据库迁移

在 `backend` 目录执行，数据库连接读取 `.env` 的 `DATABASE_URL`：

```powershell
docker compose -f ..\compose.yaml up -d postgres
uv run alembic upgrade head
uv run alembic current
uv run alembic check
```

当前最新版本为 `0002`。`0001` 创建 users、preparations、login_sessions；`0002` 为 preparations 添加 state_version，已有记录默认获得版本 1。不要重复运行 `alembic init`，也不要改写已经应用的迁移。

修改模型后，用 `uv run alembic revision --autogenerate -m "describe change"` 生成迁移，检查脚本后再升级。迁移脚本固定记录结构变化，不调用当前模型的 `create_all()`。Windows 迁移入口使用 Selector 事件循环以兼容 Psycopg 异步连接。

执行 `uv run alembic upgrade does_not_exist` 应失败，表示非法目标被拒绝，不是正常升级步骤。迁移实际验证结果见 [Part 02 数据库迁移记录](docs/part-02-migrations.md)。

`.env`、虚拟环境和 `probe-output/` 不提交到 Git；`.env.example` 仅保留无秘密的配置示例。

## 启动

API：

```powershell
uv run uvicorn backend.api:app --host 127.0.0.1 --loop asyncio:SelectorEventLoop --no-access-log --reload
```

- [健康检查](http://127.0.0.1:8000/health)：只检查应用是否能响应。
- [接口文档](http://127.0.0.1:8000/docs)。

`--reload` 仅用于开发。不使用 reload 时也保留 `--loop asyncio:SelectorEventLoop`，确保 Windows 上 Psycopg 异步连接可用。`--no-access-log` 避免 Uvicorn 原样记录含授权码的回调查询字符串。正式部署方案在后续阶段完成。

本地登录地址为 `/auth/login`。配置 Keycloak 的 inroom realm、机密客户端和精确回调 `http://127.0.0.1:8000/auth/callback` 后，设置 `.env` 中的 OIDC_CLIENT_SECRET。`/auth/me` 返回 user_id 和 csrf_token；写操作需要同源 Origin 及 X-CSRF-Token。`/auth/logout` 只撤销 InRoom 登录，不退出 Keycloak SSO。

Worker：

```powershell
uv run inroom-worker
```

当前 Worker 完成配置检查和日志初始化后正常退出，尚无任务领取循环。

## 代码检查

```powershell
uv run ruff check src tests migrations
uv run ruff format --check src tests migrations
uv run mypy src migrations
uv run pytest -q
```

整理格式会修改源码排版：

```powershell
uv run ruff format src tests migrations
```

默认测试不访问外部服务；未配置 TEST_DATABASE_URL 时跳过集成测试。离线测试覆盖基础 API、配置、OIDC 错误处理和生产配置，以及 DeepSeek 探针。TTS、音色设计和 ASR 仍使用手动真实验证。

## Part 02 完整验收

首先启动 Compose 服务。独立测试库只需创建一次，已存在时跳过 createdb：

```powershell
docker compose -f ..\compose.yaml up -d
docker compose -f ..\compose.yaml exec postgres createdb -U inroom inroom_test
```

待 PostgreSQL 和 Keycloak 就绪，在 backend 目录执行：

```powershell
$env:TEST_DATABASE_URL = 'postgresql+psycopg://inroom:inroom@127.0.0.1:5432/inroom_test'
$env:RUN_OIDC_TESTS = '1'
uv run --locked pytest -q --tb=short
```

测试启动真实 API 子进程并自动迁移测试库。只允许本地 inroom_test，禁止指向开发库或生产库。测试创建自己的数据、临时 schema 和 Keycloak realm，结束后清理这些测试资源。已有 inroom realm 和开发数据不受影响。Keycloak 管理员默认使用 Compose 中的本地 admin/admin；若自行修改过，可通过 KEYCLOAK_ADMIN_USER、KEYCLOAK_ADMIN_PASSWORD 环境变量提供，不要写入仓库。

不设置 RUN_OIDC_TESTS 时仅跳过真实 OIDC 成功链路；不能将有跳过的运行当成完整 Part 02 验收。测试不访问付费模型服务。当前全量结果为 38 passed。

开发环境原 .venv 因权限问题不可更新时，可指定 `UV_PROJECT_ENVIRONMENT=.pytest_cache/structure-env` 后执行 `uv sync --locked`，再在同一终端运行上述 uv 命令。清除 TEST_DATABASE_URL 和 RUN_OIDC_TESTS 环境变量即可恢复默认离线测试。

后续会话的事务、owner 引用与版本冲突规则见 [原子提交约定](docs/transactions.md)。

GitHub Actions 配置位于仓库根目录 `.github/workflows/backend-ci.yml`，准备 PostgreSQL 和 Keycloak 后安装锁定依赖、运行检查与完整集成测试。当前更新后的 CI 尚未远程执行，一次旧提交的成功不代表后续未提交代码已通过。

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
