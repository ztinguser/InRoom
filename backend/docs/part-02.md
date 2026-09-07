# Part 02 验收记录

日期：2026-09-06。状态：本地验收通过，可以进入 Part 03。本次代码尚未提交，更新后的远程 CI 尚未运行。

## 交付内容

- Alembic 配置、异步迁移入口和 0001/0002 迁移。
- users、preparations、login_sessions；必要身份唯一约束、外键、索引及 state_version。
- 请求级事务、带 owner 和版本条件的工作区查询/更新。
- Authlib OIDC 授权码登录、PKCE、签名 HttpOnly Cookie、会话过期、重新登录轮换和退出撤销。
- REST 写操作 Origin/CSRF 校验、统一错误响应；显式拒绝开发身份绕过配置。
- [数据所有权及 SessionStore.commit 约定](transactions.md)。
- PostgreSQL 与真实 Keycloak 集成测试、CI 服务准备和 README 运行说明。

## 环境与执行

Windows、Python 3.12.13、PostgreSQL 17.6、Keycloak 26.7.3。依赖以 uv.lock 为准，当前 SQLAlchemy 2.0.52、Psycopg 3.3.5、Authlib 1.8.0、joserfc 1.7.5。

集成测试只允许本地 `inroom_test`。测试启动真实 Uvicorn 子进程，指定 `--loop asyncio:SelectorEventLoop --no-access-log`，没有依赖 reload 模式。Psycopg 的异步连接需要该 Windows 兼容循环；迁移入口也单独选择 Selector。

本机执行使用 `.pytest_cache/structure-env`，避免原虚拟环境的文件权限限制。完整验收命令等效于：

```powershell
$env:TEST_DATABASE_URL = 'postgresql+psycopg://inroom:inroom@127.0.0.1:5432/inroom_test'
$env:RUN_OIDC_TESTS = '1'
uv run --locked pytest -q --tb=short
uv run --locked ruff check src tests migrations
uv run --locked ruff format --check src tests migrations
uv run --locked mypy src migrations
```

完整测试结果：38 passed，其中原有 13 项测试保留。没有调用付费模型服务。三条第三方弃用警告来自 Starlette/AnyIO 的测试兼容路径和 Authlib 的 HTTPX 路径，不影响当前结果。

Ruff 检查及格式检查通过，mypy 检查 30 个源码/迁移文件通过。清除集成测试环境变量后，默认离线运行结果为 22 passed、16 skipped；这 16 项是按设计跳过的集成测试，不替代上面的完整验收。

## 验收证据

| 门槛 | 实际验证 | 结果 |
|---|---|---|
| 空库迁移、旧数据保留 | 开发库空库迁移；测试库独立 schema 从 0001 升级到 0002，旧工作区保留且版本为 1 | 通过 |
| 非法迁移失败 | 不存在的 revision 返回失败；临时 0003 在建表后故意触发 DDL 错误，新增表回滚、版本仍为 0002、旧数据保留 | 通过 |
| 身份和数据隔离 | 两个用户创建/读取/修改工作区，跨用户读写均 404；匿名及伪造 Cookie 均 401 | 通过 |
| 事务原子性 | 请求中 flush 用户和工作区后注入异常，两条数据均不存在；最终提交外键失败返回 503 而非 201 | 通过 |
| 并发版本冲突 | 两个线程同时提交同版本更新，返回 200/409，最终版本只从 1 增到 2 | 通过 |
| 真实 OIDC | 两用户表单登录、真实 code 交换、ID Token 验证和本地登录记录建立；同账号重登复用 User 并轮换登录/CSRF | 通过 |
| 无效身份 | 无效 state、回调重放、过期登录、退出/重登后的旧 Cookie 均拒绝；joserfc 签名、过期、claim 异常映射单独测试 | 通过 |
| CSRF/Origin | 错误或缺失 Origin、null Origin、错误或缺失 CSRF 均 403 | 通过 |
| 生产配置 | HTTP origin/issuer、缺失客户端密钥、开发身份绕过配置被拒绝；HTTPS Cookie 设置 Secure/HttpOnly/SameSite=Lax | 通过 |

## 真实登录测试边界

测试在现有本地 Keycloak 中创建临时 `inroom-test-*` realm、独立客户端和 Alice/Bob，使用随机客户端密钥和密码，回调地址限定为本次本地测试 API。结束后删除 realm 及其本地数据库记录，不修改已有 inroom realm 或用户密码。

收尾已查询确认：测试库无残留测试用户或临时迁移 schema，Keycloak 只保留原有 master/inroom realm，开发库仍为 0002 且演示工作区版本仍为 1。

登录测试通过 HTTP 客户端提交 Keycloak 的真实 HTML 表单，并完成授权码回调；没有伪造 ID Token，也没有使用密码授权代替用户登录。仅管理临时 realm 使用 admin-cli 管理员令牌。

Keycloak 在本地 HTTP 返回 Secure Cookie，HTTPX 不会自动回传，因此测试夹具只对校验过地址的本地 Keycloak 表单显式回传其 Cookie。应用 Cookie 策略未放宽。此结果证明后端协议与身份链路，不声称浏览器 UI、浏览器 CSRF 行为或预发布 HTTPS 已实际验收；对应部署和前端门槛仍在 Part 11/13。

退出只撤销 InRoom 本地登录，Keycloak SSO 会话可能继续存在。后续 SessionStore、任务/Outbox、文件下载授权尚未实现，不属于本次已通过范围。开发库保留的迁移演示记录见 [迁移记录](part-02-migrations.md)。
